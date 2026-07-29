"""Embedding provider factory with environment-aware validation.

Creates the correct EmbeddingProvider instance based on configuration,
applying environment-specific rules (fake provider blocked in staging/production,
official OpenAI endpoint requires a real API key, etc.).
"""

from __future__ import annotations

from app.config import Settings
from app.config import settings as application_settings
from app.services.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderConfigurationError,
    FakeEmbeddingProvider,
    OpenAIEmbeddingProvider,
)

# Sentinel value used only when the OpenAI SDK requires a non-empty
# api_key but the user is pointing at a local/custom endpoint that does
# not enforce authentication.  This string is never a real secret.
_SENTINEL_API_KEY = "sentinel-not-a-real-key"

# The canonical official OpenAI embedding endpoint.
_OFFICIAL_OPENAI_BASE_URL = "https://api.openai.com/v1"


def create_embedding_provider(
    config: Settings | None = None,
) -> EmbeddingProvider:
    """Create an embedding provider based on configuration.

    Arguments:
        config: Explicit settings object. When ``None``, falls back to the
            global :data:`app.config.settings` singleton.

    Returns:
        An instance implementing :class:`EmbeddingProvider`.

    Raises:
        EmbeddingProviderConfigurationError: When the provider name is unknown,
            when the fake provider is requested outside development/test
            environments, or when the official OpenAI endpoint is used without
            an API key.
    """
    effective_config = config if config is not None else application_settings

    name = effective_config.embedding_provider

    if name == "fake":
        if effective_config.environment in ("production", "staging"):
            raise EmbeddingProviderConfigurationError(
                "Fake embedding provider is not allowed in production or staging"
            )
        return FakeEmbeddingProvider(dimension=effective_config.embedding_dimensions)

    if name == "openai":
        return _create_openai_provider(effective_config)

    raise EmbeddingProviderConfigurationError(
        f"Unknown embedding provider: {name!r}"
    )


def _create_openai_provider(
    cfg: Settings,
) -> OpenAIEmbeddingProvider:
    """Build and return an :class:`OpenAIEmbeddingProvider` from settings.

    Validation rules:
    - The official OpenAI endpoint (``api.openai.com/v1``) requires a real
      API key.
    - Custom/local endpoints may omit the key; in that case a non-secret
      sentinel value is supplied to satisfy the SDK.
    - The configured base URL, model, dimension, and timeout are preserved
      exactly.
    """
    api_key = cfg.openai_api_key
    base_url = cfg.openai_api_base

    # Official endpoint requires a real API key.
    if base_url == _OFFICIAL_OPENAI_BASE_URL and not api_key:
        raise EmbeddingProviderConfigurationError(
            "API key is required for the official OpenAI endpoint"
        )

    # For custom/local endpoints, use sentinel if no key provided.
    effective_api_key = api_key if api_key else _SENTINEL_API_KEY

    # Preserve the base_url only when it differs from the official default.
    # The OpenAI SDK treats a None base_url as the official endpoint, so
    # passing None here keeps the default behavior.
    effective_base_url: str | None
    effective_base_url = None if base_url == _OFFICIAL_OPENAI_BASE_URL else base_url

    return OpenAIEmbeddingProvider(
        api_key=effective_api_key,
        model=cfg.openai_embedding_model,
        dimension=cfg.embedding_dimensions,
        base_url=effective_base_url,
        timeout_seconds=cfg.embedding_timeout_seconds,
    )
