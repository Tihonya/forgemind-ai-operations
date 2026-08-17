"""Environment-aware chat provider factory.

Creates the correct ChatProvider instance based on a provider name and
configuration, applying environment-specific rules:
- Fake provider is blocked in staging and production.
- Official OpenAI endpoint requires a real API key.
- Custom/local endpoints may omit the API key (sentinel is used).

Follows the same pattern as embedding_provider_factory.py.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.ai.workflow.outage_handler import RetryingChatProvider
from app.ai.workflow.retry_policy import RetryPolicy
from app.config import Settings
from app.config import settings as application_settings

from .chat_provider import ChatProvider
from .exceptions import (
    ChatProviderConfigurationError,
)
from .fake_chat_provider import FakeChatProvider
from .fallback_chain import FallbackChatProvider
from .openai_chat_provider import OpenAIChatProvider

# Sentinel value used only when the OpenAI SDK requires a non-empty
# api_key but the user is pointing at a local/custom endpoint that does
# not enforce authentication.  This string is never a real secret.
_SENTINEL_API_KEY = "sentinel-not-a-real-key"

# The canonical official OpenAI chat endpoint.
_OFFICIAL_OPENAI_BASE_URL = "https://api.openai.com/v1"

# Provider names accepted in the configured fallback chain order.
_CHAIN_PROVIDER_GROQ = "groq"
_CHAIN_PROVIDER_OPENROUTER = "openrouter"

_KNOWN_CHAIN_PROVIDERS: frozenset[str] = frozenset({
    _CHAIN_PROVIDER_GROQ,
    _CHAIN_PROVIDER_OPENROUTER,
})


def _normalize_base_url(url: str) -> str:
    """Normalize a base URL for official-endpoint comparison.

    Applies the following normalizations so equivalent forms of the
    official OpenAI endpoint compare equal:
    - lowercase the scheme;
    - lowercase the hostname;
    - strip explicit default HTTPS port ``:443``;
    - strip trailing slashes from the path;
    - preserve query and fragment for non-official comparison.

    This function is used ONLY for comparison — the original configured
    base URL is passed unchanged to the SDK.
    """
    if not url:
        return url
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    # Lowercase hostname (case-insensitive DNS). Port is preserved unless
    # it is the default HTTPS port (443), which is stripped for comparison.
    hostname = parts.hostname or ""
    hostname = hostname.lower()
    port = parts.port
    netloc = hostname
    if port is not None and port != 443:
        netloc = f"{hostname}:{port}"
    elif port is not None and port == 443:
        # Explicit :443 is equivalent to omitting it for HTTPS.
        netloc = hostname
    elif ":" in parts.netloc and parts.netloc.split(":")[-1] == "443":
        # Handle case where hostname is uppercase and port is :443.
        netloc = hostname
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parts.query, parts.fragment))


def _is_official_endpoint(base_url: str) -> bool:
    """Check if the base URL points to the official OpenAI endpoint.

    Comparison is semantically normalized so that equivalent forms —
    trailing slashes, uppercase scheme/hostname, explicit default port
    ``:443`` — cannot bypass fail-fast API-key validation.

    Strictly checks: scheme=https, host=api.openai.com, path=/v1, no
    query, no fragment, no userinfo. Subdomains, lookalike hosts,
    non-HTTPS schemes, different paths, query-bearing URLs, and
    fragments are NOT classified as official.
    """
    if not base_url:
        return False
    parts = urlsplit(base_url)
    # Must be HTTPS.
    if parts.scheme.lower() != "https":
        return False
    # Hostname must be exactly api.openai.com (case-insensitive).
    hostname = parts.hostname or ""
    if hostname.lower() != "api.openai.com":
        return False
    # Port must be default (None) or 443.
    if parts.port is not None and parts.port != 443:
        return False
    # Path must be /v1 (with optional trailing slashes).
    if parts.path.rstrip("/") != "/v1":
        return False
    # No query or fragment allowed for the official endpoint.
    if parts.query or parts.fragment:
        return False
    # No userinfo allowed (user:pass@host).
    return not (parts.username or parts.password)


_SHARED_LIMITER_CACHE: dict[tuple[Any, ...], Any] = {}


def _build_shared_rate_limiter(cfg: Settings) -> Any | None:
    """Create (or reuse) the Redis-backed shared limiter for the AI boundary.

    Returns ``None`` when distributed limiting is disabled, in which
    case providers retain their process-local windows. Builds are cached
    per effective configuration so long-running workers reuse one client
    pool instead of accumulating one per workflow job.

    Enabling in a shared deployment is the production-safe path required
    by the Phase 7 contract.
    """
    if not cfg.distributed_rate_limit_enabled:
        return None
    if cfg.environment not in ("staging", "production"):
        # Development/tests keep baseline process-local behavior.
        return None
    from app.core.rate_limit import RedisRateLimiter

    cache_key = (
        "ai-provider",
        cfg.ai_rate_limit_per_minute,
        cfg.rate_limit_window_seconds,
        cfg.rate_limit_redis_url or cfg.redis_url,
        cfg.rate_limit_degraded_mode,
    )
    limiter = _SHARED_LIMITER_CACHE.get(cache_key)
    if limiter is None:
        limiter = RedisRateLimiter(
            scope="ai-provider",
            max_calls=cfg.ai_rate_limit_per_minute,
            window_seconds=cfg.rate_limit_window_seconds,
            fail_closed=(cfg.rate_limit_degraded_mode == "fail_closed"),
        )
        _SHARED_LIMITER_CACHE[cache_key] = limiter
    return limiter


def create_chat_provider(
    config: Settings | None = None,
    *,
    provider_name: str | None = None,
) -> ChatProvider:
    """Create a chat provider based on configuration.

    Every provider returned by this function is wrapped in a
    :class:`RetryingChatProvider` (WP-REC-03D) that performs bounded
    exponential backoff retry for transient failures.  The wrapper is
    the sole application-level retry owner — SDK retries remain
    disabled (``max_retries=0``).

    Arguments:
        config: Explicit settings object. When ``None``, falls back to the
            global :data:`app.config.settings` singleton.
        provider_name: Explicit provider name override (``"fake"``,
            ``"openai"``, or ``"chain"``). When ``None``, the provider is
            selected from ``config.chat_provider_mode`` — the dedicated
            chat-provider field (independent of ``embedding_provider``).

    Returns:
        An instance implementing :class:`ChatProvider`. Single providers are
        wrapped in :class:`RetryingChatProvider`; ``chain`` returns a
        :class:`FallbackChatProvider` whose members are individually wrapped.

    Raises:
        ChatProviderConfigurationError: When the provider name is unknown,
            when the fake provider is requested outside development/test
            environments, when the official OpenAI endpoint is used without
            an API key, or when external chain configuration is missing.
    """
    effective_config = config if config is not None else application_settings

    name = provider_name if provider_name is not None else effective_config.chat_provider_mode

    # --- Acceptance scenario override (development-only, positive allowlist). ---
    # When FORGEMIND_ACCEPTANCE_SCENARIO is set and the environment is
    # exactly "development", return a deterministic scenario provider.
    # All other environments fail closed.
    import os as _os
    _acceptance_scenario = _os.environ.get("FORGEMIND_ACCEPTANCE_SCENARIO")
    if _acceptance_scenario:
        # Positive allowlist: only "development" environment permitted
        if effective_config.environment != "development":
            raise ChatProviderConfigurationError(
                "Acceptance scenarios require environment='development', "
                f"got '{effective_config.environment}'"
            )
        # Lazy import — the acceptance module is never loaded in
        # non-development environments or when the env var is absent.
        from app.ai.provider.acceptance_scenarios import get_acceptance_provider
        delegate = get_acceptance_provider(_acceptance_scenario, effective_config)
        return _wrap_with_retry(delegate, effective_config)
    # --- End acceptance override. ---

    if name == "fake":
        if effective_config.environment in ("production", "staging"):
            raise ChatProviderConfigurationError(
                "Fake chat provider is not allowed in production or staging"
            )
        delegate = FakeChatProvider()
        return _wrap_with_retry(delegate, effective_config)

    if name == "openai":
        delegate = _create_openai_provider(effective_config)
        return _wrap_with_retry(delegate, effective_config)

    if name == "openrouter":
        # OpenRouter only, no fallback chain (WP-P7-02 / PD-3).
        delegate = _create_openrouter_provider(effective_config)
        return _wrap_with_retry(delegate, effective_config)

    if name == "chain":
        return _create_chain_provider(effective_config)

    raise ChatProviderConfigurationError(
        f"Unknown chat provider: {name!r}"
    )


def _wrap_with_retry(
    delegate: ChatProvider,
    cfg: Settings,
) -> RetryingChatProvider:
    """Wrap a concrete ChatProvider in a RetryingChatProvider.

    Every provider returned by :func:`create_chat_provider` is wrapped
    exactly once.  The retry policy uses ``cfg.llm_max_retries``
    (retries after the initial attempt; total calls =
    ``1 + llm_max_retries``).

    Args:
        delegate: The concrete provider (FakeChatProvider or
            OpenAIChatProvider).
        cfg: Application settings supplying ``llm_max_retries``.

    Returns:
        A :class:`RetryingChatProvider` wrapping the delegate.
    """
    policy = RetryPolicy(max_retries=cfg.llm_max_retries)
    return RetryingChatProvider(delegate=delegate, policy=policy)


def _create_openai_provider(
    cfg: Settings,
) -> OpenAIChatProvider:
    """Build and return an :class:`OpenAIChatProvider` from settings.

    Validation rules:
    - The official OpenAI endpoint (``api.openai.com/v1``) requires a real
      API key. The comparison is normalized so trailing slashes and
      equivalent forms cannot bypass this check.
    - Custom/local endpoints may omit the key; in that case a non-secret
      sentinel value is supplied to satisfy the SDK.
    - The configured base URL, model, and timeout are preserved exactly.
    """
    api_key = cfg.openai_api_key
    base_url = cfg.openai_api_base

    # Official endpoint requires a real API key (normalized comparison).
    if _is_official_endpoint(base_url) and not api_key:
        raise ChatProviderConfigurationError(
            "API key is required for the official OpenAI endpoint"
        )

    # For custom/local endpoints, use sentinel if no key provided.
    effective_api_key = api_key if api_key else _SENTINEL_API_KEY

    # Preserve the base_url only when it differs from the official default.
    # The OpenAI SDK treats a None base_url as the official endpoint.
    effective_base_url: str | None
    effective_base_url = None if _is_official_endpoint(base_url) else base_url

    return OpenAIChatProvider(
        api_key=effective_api_key,
        model=cfg.openai_chat_model,
        base_url=effective_base_url,
        timeout_seconds=cfg.llm_timeout_seconds,
        rate_limit_per_minute=cfg.ai_rate_limit_per_minute,
        provider_name="openai",
        structured_output_mode=cfg.openai_structured_output_mode,
        shared_rate_limiter=_build_shared_rate_limiter(cfg),
    )


def _create_groq_provider(
    cfg: Settings,
) -> OpenAIChatProvider:
    """Build the Groq (free primary) OpenAI-compatible provider.

    Groq always requires a real API key (no sentinel — it is an external
    authenticated provider). The pinned model and base URL are preserved
    exactly from configuration.
    """
    if not cfg.groq_api_key:
        raise ChatProviderConfigurationError(
            "Groq API key is required for the Groq provider"
        )
    return OpenAIChatProvider(
        api_key=cfg.groq_api_key,
        model=cfg.groq_chat_model,
        base_url=cfg.groq_api_base,
        timeout_seconds=cfg.llm_timeout_seconds,
        rate_limit_per_minute=cfg.ai_rate_limit_per_minute,
        provider_name=_CHAIN_PROVIDER_GROQ,
        structured_output_mode=cfg.groq_structured_output_mode,
        shared_rate_limiter=_build_shared_rate_limiter(cfg),
    )


def _create_openrouter_provider(
    cfg: Settings,
) -> OpenAIChatProvider:
    """Build the OpenRouter (paid fallback) OpenAI-compatible provider.

    OpenRouter always requires a real API key and an explicitly pinned paid
    model (the model has no default — it is never guessed). The application
    does not enforce the external budget; that is an OpenRouter account/key
    control (HTTP 402 on exhaustion).
    """
    if not cfg.openrouter_api_key:
        raise ChatProviderConfigurationError(
            "OpenRouter API key is required for the OpenRouter provider"
        )
    if not cfg.openrouter_chat_model:
        raise ChatProviderConfigurationError(
            "OpenRouter chat model must be explicitly pinned "
            "(openrouter_chat_model has no default)"
        )
    return OpenAIChatProvider(
        api_key=cfg.openrouter_api_key,
        model=cfg.openrouter_chat_model,
        base_url=cfg.openrouter_api_base,
        timeout_seconds=cfg.llm_timeout_seconds,
        rate_limit_per_minute=cfg.ai_rate_limit_per_minute,
        provider_name=_CHAIN_PROVIDER_OPENROUTER,
        structured_output_mode=cfg.openrouter_structured_output_mode,
        shared_rate_limiter=_build_shared_rate_limiter(cfg),
    )


def _parse_chain_order(raw: str) -> list[str]:
    """Parse and validate the configured fallback chain order.

    The order is server-configured and exact. A client cannot choose or
    reorder providers. Duplicate entries and unknown providers are rejected
    (fail fast).

    Args:
        raw: Comma-separated provider order (e.g. ``"groq,openrouter"``).

    Returns:
        The ordered list of known provider names.

    Raises:
        ChatProviderConfigurationError: If the order is empty, contains an
            unknown provider, or contains duplicates.
    """
    parts = [p.strip() for p in raw.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        raise ChatProviderConfigurationError(
            "chat_provider_chain must not be empty"
        )
    seen: set[str] = set()
    order: list[str] = []
    for name in parts:
        if name not in _KNOWN_CHAIN_PROVIDERS:
            raise ChatProviderConfigurationError(
                f"Unknown chain provider: {name!r}. "
                f"Known providers: {sorted(_KNOWN_CHAIN_PROVIDERS)}"
            )
        if name in seen:
            raise ChatProviderConfigurationError(
                f"Duplicate chain provider: {name!r}"
            )
        seen.add(name)
        order.append(name)
    return order


def _create_chain_provider(
    cfg: Settings,
) -> FallbackChatProvider:
    """Build the ordered fallback chain from configuration.

    Each member is a concrete adapter wrapped exactly once in a
    :class:`RetryingChatProvider` (bounded retry). The chain itself performs
    no retry and is NOT wrapped again — avoiding nested retry loops.

    Total provider calls are bounded by ``len(chain) × (1 + llm_max_retries)``.

    Raises:
        ChatProviderConfigurationError: If the chain order is invalid or any
            member's required external configuration is missing (fail early,
            only when external mode is actually selected).
    """
    order = _parse_chain_order(cfg.chat_provider_chain)
    providers: list[tuple[str, ChatProvider]] = []
    for name in order:
        if name == _CHAIN_PROVIDER_GROQ:
            delegate = _create_groq_provider(cfg)
        elif name == _CHAIN_PROVIDER_OPENROUTER:
            delegate = _create_openrouter_provider(cfg)
        else:  # pragma: no cover - unreachable after _parse_chain_order
            raise ChatProviderConfigurationError(
                f"Unknown chain provider: {name!r}"
            )
        providers.append((name, _wrap_with_retry(delegate, cfg)))
    return FallbackChatProvider(providers=providers)
