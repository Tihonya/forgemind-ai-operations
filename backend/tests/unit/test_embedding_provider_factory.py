"""Unit tests for the embedding provider factory.

Covers the factory contract defined by WP-4.3B1:
- provider selection (openai -> OpenAIEmbeddingProvider, fake -> FakeEmbeddingProvider)
- environment-aware fake-provider validation (allowed in dev/tests, rejected in staging/prod)
- unknown provider rejection
- official endpoint API key requirement
- custom endpoint without API key (uses sentinel)
- configuration preservation (base_url, model, dimension, timeout)
- EmbeddingProviderConfigurationError for all configuration errors
- no API key leakage in error messages
- no mutation of the passed-in settings
- config=None falls back to the application_settings singleton
- no external network requests
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from app.config import Settings
from app.services.embedding_provider import (
    EmbeddingProviderConfigurationError,
    FakeEmbeddingProvider,
    OpenAIEmbeddingProvider,
)
from app.services.embedding_provider_factory import create_embedding_provider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(**overrides: object) -> Settings:
    """Build a Settings instance from keyword overrides."""
    defaults: dict[str, object] = {
        "environment": "development",
        "embedding_provider": "openai",
        "openai_api_key": "sk-test-1234",
        "openai_api_base": "https://api.openai.com/v1",
        "openai_embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 1536,
        "embedding_timeout_seconds": 30,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


class TestProviderSelection:
    """Factory returns the correct provider type for each name."""

    def test_openai_provider_returns_openai(self) -> None:
        config = _make_settings(embedding_provider="openai")
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_embedding_provider(config=config)
        assert isinstance(provider, OpenAIEmbeddingProvider)

    def test_fake_provider_returns_fake_in_development(self) -> None:
        config = _make_settings(embedding_provider="fake", environment="development")
        provider = create_embedding_provider(config=config)
        assert isinstance(provider, FakeEmbeddingProvider)


class TestFakeProviderEnvironmentValidation:
    """Fake provider is rejected in staging and production."""

    def test_fake_rejected_in_staging(self) -> None:
        config = _make_settings(embedding_provider="fake", environment="staging")
        with pytest.raises(EmbeddingProviderConfigurationError):
            create_embedding_provider(config=config)

    def test_fake_rejected_in_production(self) -> None:
        config = _make_settings(embedding_provider="fake", environment="production")
        with pytest.raises(EmbeddingProviderConfigurationError):
            create_embedding_provider(config=config)


# ---------------------------------------------------------------------------
# Unknown provider
# ---------------------------------------------------------------------------


class TestUnknownProvider:
    """Unknown provider names are rejected via a defensive cast."""

    def test_unknown_provider_raises(self) -> None:
        invalid_config = cast(
            Settings,
            SimpleNamespace(
                embedding_provider="unknown",
                environment="development",
                openai_api_key="",
                openai_api_base="https://api.openai.com/v1",
                openai_embedding_model="text-embedding-3-small",
                embedding_dimensions=1536,
                embedding_timeout_seconds=30,
            ),
        )
        with pytest.raises(
            EmbeddingProviderConfigurationError,
            match="Unknown embedding provider",
        ):
            create_embedding_provider(config=invalid_config)


# ---------------------------------------------------------------------------
# OpenAI endpoint and API key validation
# ---------------------------------------------------------------------------


class TestOfficialEndpointApiKey:
    """Official OpenAI endpoint requires a real API key."""

    def test_official_endpoint_without_key_raises(self) -> None:
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base="https://api.openai.com/v1",
        )
        with pytest.raises(
            EmbeddingProviderConfigurationError,
            match="API key.*required.*official",
        ):
            create_embedding_provider(config=config)

    def test_official_endpoint_with_key_succeeds(self) -> None:
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="sk-real-key",
            openai_api_base="https://api.openai.com/v1",
        )
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_embedding_provider(config=config)
        assert isinstance(provider, OpenAIEmbeddingProvider)


class TestCustomEndpoint:
    """Custom/local OpenAI-compatible endpoints may omit the API key."""

    def test_custom_endpoint_without_key_succeeds(self) -> None:
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base="http://localhost:8080/v1",
        )
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_embedding_provider(config=config)
        assert isinstance(provider, OpenAIEmbeddingProvider)

    def test_sentinel_key_passed_only_for_custom_endpoint(self) -> None:
        """When no API key is set for a custom endpoint, a sentinel is used."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base="http://localhost:8080/v1",
        )
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_embedding_provider(config=config)

        call_kwargs = mock_async_openai.call_args[1]
        assert call_kwargs["api_key"] == "sentinel-not-a-real-key"

    def test_sentinel_not_used_for_official_endpoint(self) -> None:
        """Official endpoint without key raises — no sentinel fallback."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base="https://api.openai.com/v1",
        )
        with pytest.raises(EmbeddingProviderConfigurationError):
            create_embedding_provider(config=config)


# ---------------------------------------------------------------------------
# Configuration preservation
# ---------------------------------------------------------------------------


class TestConfigurationPreservation:
    """Factory preserves all configured values."""

    def test_base_url_preserved(self) -> None:
        """Custom base_url is passed through to the provider."""
        config = _make_settings(
            openai_api_base="http://localhost:8080/v1",
            openai_api_key="sk-test",
        )
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_embedding_provider(config=config)

        call_kwargs = mock_async_openai.call_args[1]
        assert call_kwargs["base_url"] == "http://localhost:8080/v1"

    def test_official_base_url_omitted(self) -> None:
        """Official base_url is not passed (None), keeping SDK default."""
        config = _make_settings(
            openai_api_base="https://api.openai.com/v1",
            openai_api_key="sk-test",
        )
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_embedding_provider(config=config)

        call_kwargs = mock_async_openai.call_args[1]
        assert "base_url" not in call_kwargs or call_kwargs.get("base_url") is None

    def test_model_preserved(self) -> None:
        config = _make_settings(
            openai_embedding_model="text-embedding-3-large",
            openai_api_key="sk-test",
        )
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_embedding_provider(config=config)
        assert provider._model == "text-embedding-3-large"  # type: ignore[attr-defined]

    def test_dimension_preserved(self) -> None:
        config = _make_settings(
            embedding_dimensions=768,
            openai_api_key="sk-test",
        )
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_embedding_provider(config=config)
        assert provider.dimension() == 768

    def test_timeout_preserved(self) -> None:
        config = _make_settings(
            embedding_timeout_seconds=60,
            openai_api_key="sk-test",
        )
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_embedding_provider(config=config)
        assert provider._timeout_seconds == 60  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Error message safety
# ---------------------------------------------------------------------------


class TestErrorMessageSafety:
    """API keys must never appear in error messages."""

    def test_no_api_key_in_official_error(self) -> None:
        """Error for missing API key does not contain key fragments."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base="https://api.openai.com/v1",
        )
        with pytest.raises(EmbeddingProviderConfigurationError) as exc_info:
            create_embedding_provider(config=config)
        error_msg = str(exc_info.value)
        assert "sk-" not in error_msg

    def test_no_api_key_in_unknown_provider_error(self) -> None:
        """Error for unknown provider does not leak secrets."""
        invalid_config = cast(
            Settings,
            SimpleNamespace(
                embedding_provider="mystery",
                environment="development",
                openai_api_key="super-secret-key-value",
                openai_api_base="https://api.openai.com/v1",
                openai_embedding_model="text-embedding-3-small",
                embedding_dimensions=1536,
                embedding_timeout_seconds=30,
            ),
        )
        with pytest.raises(EmbeddingProviderConfigurationError) as exc_info:
            create_embedding_provider(config=invalid_config)
        error_msg = str(exc_info.value)
        assert "super-secret-key-value" not in error_msg


# ---------------------------------------------------------------------------
# Global settings safety
# ---------------------------------------------------------------------------


class TestGlobalSettingsSafety:
    """Factory must not mutate the passed-in settings object."""

    def test_passed_settings_not_mutated(self) -> None:
        """Calling the factory does not change settings attributes."""
        original_config = _make_settings(
            embedding_provider="fake",
            environment="development",
            embedding_dimensions=512,
        )
        original_dims = original_config.embedding_dimensions
        original_provider = original_config.embedding_provider

        create_embedding_provider(config=original_config)

        assert original_config.embedding_dimensions == original_dims
        assert original_config.embedding_provider == original_provider


# ---------------------------------------------------------------------------
# Config=None fallback
# ---------------------------------------------------------------------------


class TestConfigNoneFallback:
    """When config is None, the factory falls back to application_settings."""

    def test_config_none_uses_application_settings(self) -> None:
        """Explicit None should fall back to the global singleton."""
        fallback_config = _make_settings(
            embedding_provider="fake",
            environment="development",
            embedding_dimensions=128,
        )
        with patch(
            "app.services.embedding_provider_factory.application_settings",
            fallback_config,
        ):
            provider = create_embedding_provider(config=None)
        assert isinstance(provider, FakeEmbeddingProvider)
        assert provider.dimension() == 128


# ---------------------------------------------------------------------------
# No network requests
# ---------------------------------------------------------------------------


class TestNoNetworkRequests:
    """Factory and fake provider must not make network calls."""

    @pytest.mark.asyncio
    async def test_fake_provider_no_network(self) -> None:
        """Fake provider embeds without any HTTP calls."""
        config = _make_settings(
            embedding_provider="fake",
            environment="development",
        )
        with patch("httpx.Client") as mock_client:
            provider = create_embedding_provider(config=config)
            result = await provider.embed_text(["hello"])
            mock_client.assert_not_called()
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Fake provider dimension preservation
# ---------------------------------------------------------------------------


class TestFakeDimensionPreserved:
    """Fake provider dimension from settings is preserved."""

    def test_fake_uses_settings_dimension(self) -> None:
        config = _make_settings(
            embedding_provider="fake",
            environment="development",
            embedding_dimensions=256,
        )
        provider = create_embedding_provider(config=config)
        assert provider.dimension() == 256


# ---------------------------------------------------------------------------
# Max retries zero
# ---------------------------------------------------------------------------


class TestMaxRetriesZero:
    """OpenAIEmbeddingProvider must disable SDK retries."""

    def test_max_retries_zero_passed(self) -> None:
        """The factory-created provider has max_retries=0."""
        config = _make_settings(openai_api_key="sk-test")
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_embedding_provider(config=config)

        call_kwargs = mock_async_openai.call_args[1]
        assert call_kwargs["max_retries"] == 0
