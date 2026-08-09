"""Environment-aware chat provider factory.

Creates the correct ChatProvider instance based on a provider name and
configuration, applying environment-specific rules:
- Fake provider is blocked in staging and production.
- Official OpenAI endpoint requires a real API key.
- Custom/local endpoints may omit the API key (sentinel is used).

Follows the same pattern as embedding_provider_factory.py.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from app.config import Settings
from app.config import settings as application_settings

from .chat_provider import ChatProvider
from .exceptions import ChatProviderConfigurationError
from .fake_chat_provider import FakeChatProvider
from .openai_chat_provider import OpenAIChatProvider

# Sentinel value used only when the OpenAI SDK requires a non-empty
# api_key but the user is pointing at a local/custom endpoint that does
# not enforce authentication.  This string is never a real secret.
_SENTINEL_API_KEY = "sentinel-not-a-real-key"

# The canonical official OpenAI chat endpoint.
_OFFICIAL_OPENAI_BASE_URL = "https://api.openai.com/v1"


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


def create_chat_provider(
    config: Settings | None = None,
    *,
    provider_name: str | None = None,
) -> ChatProvider:
    """Create a chat provider based on configuration.

    Arguments:
        config: Explicit settings object. When ``None``, falls back to the
            global :data:`app.config.settings` singleton.
        provider_name: Explicit provider name override (``"openai"`` or
            ``"fake"``). When ``None``, the provider is selected from
            ``config.embedding_provider`` — the existing config field —
            since Settings does not yet have a dedicated ``chat_provider``
            field. This avoids modifying config.py (out of scope for 03A).

    Returns:
        An instance implementing :class:`ChatProvider`.

    Raises:
        ChatProviderConfigurationError: When the provider name is unknown,
            when the fake provider is requested outside development/test
            environments, or when the official OpenAI endpoint is used
            without an API key.
    """
    effective_config = config if config is not None else application_settings

    name = provider_name if provider_name is not None else effective_config.embedding_provider

    if name == "fake":
        if effective_config.environment in ("production", "staging"):
            raise ChatProviderConfigurationError(
                "Fake chat provider is not allowed in production or staging"
            )
        return FakeChatProvider()

    if name == "openai":
        return _create_openai_provider(effective_config)

    raise ChatProviderConfigurationError(
        f"Unknown chat provider: {name!r}"
    )


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
    )
