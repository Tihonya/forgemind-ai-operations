"""Unit tests for the chat provider factory.

Covers:
- Factory provider selection (openai -> OpenAIChatProvider, fake -> FakeChatProvider)
- Fake provider permitted in test/development
- Fake provider rejected in staging/production
- Missing/invalid production configuration fails closed
- OpenAI-compatible base URL and model propagation
- Timeout configuration
- Provider retry configuration (max_retries=0)
- Unknown provider rejection
- Custom endpoint without API key (uses sentinel)
- Official endpoint without API key raises
- No API key leakage in error messages
- No mutation of the passed-in settings
- config=None fallback to application_settings singleton
- No external network requests
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.provider.exceptions import ChatProviderConfigurationError
from app.ai.provider.factory import create_chat_provider
from app.ai.provider.fake_chat_provider import FakeChatProvider
from app.ai.provider.openai_chat_provider import OpenAIChatProvider
from app.config import Settings

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
        "openai_chat_model": "gpt-4o-mini",
        "llm_timeout_seconds": 30,
        "llm_max_retries": 3,
        "ai_rate_limit_per_minute": 10,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


class TestProviderSelection:
    def test_openai_provider_returns_openai(self) -> None:
        config = _make_settings(embedding_provider="openai")
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert isinstance(provider, OpenAIChatProvider)

    def test_fake_provider_returns_fake_in_development(self) -> None:
        config = _make_settings(embedding_provider="fake", environment="development")
        provider = create_chat_provider(config=config)
        assert isinstance(provider, FakeChatProvider)

    def test_explicit_provider_name_overrides_config(self) -> None:
        config = _make_settings(embedding_provider="openai")
        provider = create_chat_provider(
            config=config, provider_name="fake"
        )
        assert isinstance(provider, FakeChatProvider)

    def test_explicit_openai_overrides_config(self) -> None:
        config = _make_settings(embedding_provider="fake")
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(
                config=config, provider_name="openai"
            )
        assert isinstance(provider, OpenAIChatProvider)


# ---------------------------------------------------------------------------
# Fake provider environment validation
# ---------------------------------------------------------------------------


class TestFakeProviderEnvironmentValidation:
    def test_fake_allowed_in_development(self) -> None:
        config = _make_settings(embedding_provider="fake", environment="development")
        provider = create_chat_provider(config=config)
        assert isinstance(provider, FakeChatProvider)

    def test_fake_rejected_in_staging(self) -> None:
        config = _make_settings(embedding_provider="fake", environment="staging")
        with pytest.raises(ChatProviderConfigurationError, match="not allowed"):
            create_chat_provider(config=config)

    def test_fake_rejected_in_production(self) -> None:
        config = _make_settings(embedding_provider="fake", environment="production")
        with pytest.raises(ChatProviderConfigurationError, match="not allowed"):
            create_chat_provider(config=config)


# ---------------------------------------------------------------------------
# Unknown provider
# ---------------------------------------------------------------------------


class TestUnknownProvider:
    def test_unknown_provider_raises(self) -> None:
        invalid_config = cast(
            Settings,
            SimpleNamespace(
                embedding_provider="unknown",
                environment="development",
                openai_api_key="",
                openai_api_base="https://api.openai.com/v1",
                openai_chat_model="gpt-4o-mini",
                llm_timeout_seconds=30,
                ai_rate_limit_per_minute=10,
            ),
        )
        with pytest.raises(
            ChatProviderConfigurationError,
            match="Unknown chat provider",
        ):
            create_chat_provider(config=invalid_config)


# ---------------------------------------------------------------------------
# Official endpoint API key validation
# ---------------------------------------------------------------------------


class TestOfficialEndpointApiKey:
    def test_official_endpoint_without_key_raises(self) -> None:
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base="https://api.openai.com/v1",
        )
        with pytest.raises(
            ChatProviderConfigurationError,
            match="API key.*required.*official",
        ):
            create_chat_provider(config=config)

    def test_official_endpoint_with_key_succeeds(self) -> None:
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="sk-real-key",
            openai_api_base="https://api.openai.com/v1",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert isinstance(provider, OpenAIChatProvider)


# ---------------------------------------------------------------------------
# Custom endpoint
# ---------------------------------------------------------------------------


class TestCustomEndpoint:
    def test_custom_endpoint_without_key_succeeds(self) -> None:
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base="http://localhost:8080/v1",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert isinstance(provider, OpenAIChatProvider)

    def test_sentinel_key_passed_for_custom_endpoint(self) -> None:
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base="http://localhost:8080/v1",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_chat_provider(config=config)
        call_kwargs = mock_async_openai.call_args[1]
        assert call_kwargs["api_key"] == "sentinel-not-a-real-key"

    def test_sentinel_not_used_for_official_endpoint(self) -> None:
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base="https://api.openai.com/v1",
        )
        with pytest.raises(ChatProviderConfigurationError):
            create_chat_provider(config=config)


# ---------------------------------------------------------------------------
# Configuration preservation
# ---------------------------------------------------------------------------


class TestConfigurationPreservation:
    def test_base_url_preserved(self) -> None:
        config = _make_settings(
            openai_api_base="http://localhost:8080/v1",
            openai_api_key="sk-test",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_chat_provider(config=config)
        call_kwargs = mock_async_openai.call_args[1]
        assert call_kwargs["base_url"] == "http://localhost:8080/v1"

    def test_official_base_url_omitted(self) -> None:
        config = _make_settings(
            openai_api_base="https://api.openai.com/v1",
            openai_api_key="sk-test",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_chat_provider(config=config)
        call_kwargs = mock_async_openai.call_args[1]
        assert "base_url" not in call_kwargs or call_kwargs.get("base_url") is None

    def test_model_preserved(self) -> None:
        config = _make_settings(
            openai_chat_model="gpt-4o",
            openai_api_key="sk-test",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert provider._model == "gpt-4o"  # type: ignore[attr-defined]

    def test_timeout_preserved(self) -> None:
        config = _make_settings(
            llm_timeout_seconds=60,
            openai_api_key="sk-test",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert provider._timeout_seconds == 60  # type: ignore[attr-defined]

    def test_rate_limit_preserved(self) -> None:
        config = _make_settings(
            ai_rate_limit_per_minute=20,
            openai_api_key="sk-test",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert provider._rate_limit_per_minute == 20  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Retry configuration
# ---------------------------------------------------------------------------


class TestRetryConfiguration:
    def test_max_retries_zero_passed(self) -> None:
        """The factory-created provider has max_retries=0 (SDK disabled)."""
        config = _make_settings(
            openai_api_key="sk-test",
            llm_max_retries=5,
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_chat_provider(config=config)
        call_kwargs = mock_async_openai.call_args[1]
        assert call_kwargs["max_retries"] == 0

    def test_llm_max_retries_not_used_by_adapter(self) -> None:
        """llm_max_retries is owned by 03D, not the adapter.

        The adapter always sets max_retries=0 regardless of
        llm_max_retries value.
        """
        for retries_val in (0, 1, 3, 5, 10):
            config = _make_settings(
                openai_api_key="sk-test",
                llm_max_retries=retries_val,
            )
            with patch(
                "app.ai.provider.openai_chat_provider.AsyncOpenAI",
                return_value=AsyncMock(),
            ) as mock_async_openai:
                create_chat_provider(config=config)
            call_kwargs = mock_async_openai.call_args[1]
            assert call_kwargs["max_retries"] == 0


# ---------------------------------------------------------------------------
# Error message safety
# ---------------------------------------------------------------------------


class TestErrorMessageSafety:
    def test_no_api_key_in_official_error(self) -> None:
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base="https://api.openai.com/v1",
        )
        with pytest.raises(ChatProviderConfigurationError) as exc_info:
            create_chat_provider(config=config)
        error_msg = str(exc_info.value)
        assert "sk-" not in error_msg

    def test_no_api_key_in_unknown_provider_error(self) -> None:
        invalid_config = cast(
            Settings,
            SimpleNamespace(
                embedding_provider="mystery",
                environment="development",
                openai_api_key="super-secret-key-value",
                openai_api_base="https://api.openai.com/v1",
                openai_chat_model="gpt-4o-mini",
                llm_timeout_seconds=30,
                ai_rate_limit_per_minute=10,
            ),
        )
        with pytest.raises(ChatProviderConfigurationError) as exc_info:
            create_chat_provider(config=invalid_config)
        error_msg = str(exc_info.value)
        assert "super-secret-key-value" not in error_msg


# ---------------------------------------------------------------------------
# Settings mutation safety
# ---------------------------------------------------------------------------


class TestSettingsMutationSafety:
    def test_passed_settings_not_mutated(self) -> None:
        original_config = _make_settings(
            embedding_provider="fake",
            environment="development",
        )
        original_provider = original_config.embedding_provider
        original_key = original_config.openai_api_key

        create_chat_provider(config=original_config)

        assert original_config.embedding_provider == original_provider
        assert original_config.openai_api_key == original_key


# ---------------------------------------------------------------------------
# Config=None fallback
# ---------------------------------------------------------------------------


class TestConfigNoneFallback:
    def test_config_none_uses_application_settings(self) -> None:
        fallback_config = _make_settings(
            embedding_provider="fake",
            environment="development",
        )
        with patch(
            "app.ai.provider.factory.application_settings",
            fallback_config,
        ):
            provider = create_chat_provider(config=None)
        assert isinstance(provider, FakeChatProvider)


# ---------------------------------------------------------------------------
# No network requests
# ---------------------------------------------------------------------------


class TestNoNetworkRequests:
    @pytest.mark.asyncio
    async def test_fake_provider_no_network(self) -> None:
        config = _make_settings(
            embedding_provider="fake",
            environment="development",
        )
        with patch("httpx.Client") as mock_client:
            provider = create_chat_provider(config=config)
            result = await provider.complete("hello")
            mock_client.assert_not_called()
        assert isinstance(result.content, str)

    def test_factory_creation_no_network(self) -> None:
        """Factory creating an OpenAI provider with injected mock makes no real HTTP."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="sk-test",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ), patch("httpx.Client") as mock_httpx:
            provider = create_chat_provider(config=config)
            assert isinstance(provider, OpenAIChatProvider)
            mock_httpx.assert_not_called()
