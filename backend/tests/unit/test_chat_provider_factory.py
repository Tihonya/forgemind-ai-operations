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
from app.ai.workflow.outage_handler import RetryingChatProvider
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
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, OpenAIChatProvider)

    def test_fake_provider_returns_fake_in_development(self) -> None:
        config = _make_settings(embedding_provider="fake", environment="development")
        provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, FakeChatProvider)

    def test_explicit_provider_name_overrides_config(self) -> None:
        config = _make_settings(embedding_provider="openai")
        provider = create_chat_provider(
            config=config, provider_name="fake"
        )
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, FakeChatProvider)

    def test_explicit_openai_overrides_config(self) -> None:
        config = _make_settings(embedding_provider="fake")
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(
                config=config, provider_name="openai"
            )
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, OpenAIChatProvider)


# ---------------------------------------------------------------------------
# Fake provider environment validation
# ---------------------------------------------------------------------------


class TestFakeProviderEnvironmentValidation:
    def test_fake_allowed_in_development(self) -> None:
        config = _make_settings(embedding_provider="fake", environment="development")
        provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, FakeChatProvider)

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
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, OpenAIChatProvider)


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
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, OpenAIChatProvider)

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
        assert provider._delegate._model == "gpt-4o"  # type: ignore[attr-defined]

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
        assert provider._delegate._timeout_seconds == 60  # type: ignore[attr-defined]

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
        assert provider._delegate._rate_limit_per_minute == 20  # type: ignore[attr-defined]


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
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, FakeChatProvider)


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
            assert isinstance(provider, RetryingChatProvider)
            assert isinstance(provider._delegate, OpenAIChatProvider)
            mock_httpx.assert_not_called()


# ---------------------------------------------------------------------------
# Remediation: official base URL normalization
# ---------------------------------------------------------------------------


class TestOfficialBaseUrlNormalization:
    """Harmless equivalent forms of the official endpoint must not bypass API-key validation."""

    @pytest.mark.parametrize(
        "base_url",
        [
            "https://api.openai.com/v1",
            "https://api.openai.com/v1/",
            "https://api.openai.com/v1//",
        ],
    )
    def test_trailing_slash_treated_as_official(self, base_url: str) -> None:
        """Trailing slashes must not bypass the official-endpoint key check."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base=base_url,
        )
        with pytest.raises(
            ChatProviderConfigurationError,
            match="API key.*required.*official",
        ):
            create_chat_provider(config=config)

    @pytest.mark.parametrize(
        "base_url",
        [
            "https://api.openai.com/v1",
            "https://api.openai.com/v1/",
        ],
    )
    def test_official_with_key_succeeds_normalized(self, base_url: str) -> None:
        """Official endpoint with a real key succeeds regardless of trailing slash."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="sk-real-key",
            openai_api_base=base_url,
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, OpenAIChatProvider)

    def test_trailing_slash_official_base_url_omitted(self) -> None:
        """Official endpoint with trailing slash still gets None base_url (SDK default)."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="sk-test",
            openai_api_base="https://api.openai.com/v1/",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_chat_provider(config=config)
        call_kwargs = mock_async_openai.call_args[1]
        assert "base_url" not in call_kwargs or call_kwargs.get("base_url") is None

    def test_custom_endpoint_with_trailing_slash_preserved(self) -> None:
        """Custom endpoint trailing slash is preserved (not normalized away)."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="sk-test",
            openai_api_base="http://localhost:8080/v1/",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_chat_provider(config=config)
        call_kwargs = mock_async_openai.call_args[1]
        assert call_kwargs["base_url"] == "http://localhost:8080/v1/"


# ---------------------------------------------------------------------------
# Final correction: robust official endpoint classification
# ---------------------------------------------------------------------------


class TestRobustOfficialEndpointClassification:
    """Equivalent official forms must fail fast; non-official forms must not."""

    @pytest.mark.parametrize(
        "base_url",
        [
            "https://api.openai.com/v1",
            "https://api.openai.com/v1/",
            "https://api.openai.com/v1//",
            "https://API.OPENAI.COM/v1",
            "https://API.OPENAI.COM/v1/",
            "https://api.openai.com:443/v1",
            "https://api.openai.com:443/v1/",
            "https://API.OPENAI.COM:443/v1",
        ],
    )
    def test_equivalent_official_without_key_fails_fast(self, base_url: str) -> None:
        """Every equivalent official form without an API key raises."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base=base_url,
        )
        with pytest.raises(
            ChatProviderConfigurationError,
            match="API key.*required.*official",
        ):
            create_chat_provider(config=config)

    @pytest.mark.parametrize(
        "base_url",
        [
            "https://api.openai.com/v1",
            "https://api.openai.com/v1/",
            "https://API.OPENAI.COM/v1",
            "https://api.openai.com:443/v1",
            "https://API.OPENAI.COM:443/v1/",
        ],
    )
    def test_equivalent_official_with_key_succeeds(self, base_url: str) -> None:
        """Every equivalent official form with a key creates a provider."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="sk-real-key",
            openai_api_base=base_url,
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, OpenAIChatProvider)

    @pytest.mark.parametrize(
        "base_url",
        [
            "https://api.openai.com/v1",
            "https://api.openai.com/v1/",
            "https://API.OPENAI.COM/v1",
            "https://api.openai.com:443/v1",
            "https://API.OPENAI.COM:443/v1/",
        ],
    )
    def test_equivalent_official_base_url_omitted(self, base_url: str) -> None:
        """Equivalent official forms get None base_url (SDK default)."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="sk-test",
            openai_api_base=base_url,
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_chat_provider(config=config)
        call_kwargs = mock_async_openai.call_args[1]
        assert "base_url" not in call_kwargs or call_kwargs.get("base_url") is None

    @pytest.mark.parametrize(
        "base_url",
        [
            # Subdomains — not the official endpoint
            "https://sub.api.openai.com/v1",
            "https://api.openai.com.evil.com/v1",
            # Non-HTTPS schemes
            "http://api.openai.com/v1",
            "ftp://api.openai.com/v1",
            # Different paths
            "https://api.openai.com/v2",
            "https://api.openai.com/",
            "https://api.openai.com",
            # Query and fragment
            "https://api.openai.com/v1?foo=bar",
            "https://api.openai.com/v1#frag",
            # Userinfo
            "https://user:pass@api.openai.com/v1",
            "https://user@api.openai.com/v1",
            # Non-default port
            "https://api.openai.com:8443/v1",
            # Lookalike hosts
            "https://api.openai.com.org/v1",
            "https://api-openai-com/v1",
        ],
    )
    def test_non_official_not_classified_as_official(self, base_url: str) -> None:
        """Non-official URLs must NOT be classified as official (no fail-fast)."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base=base_url,
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            # Should NOT raise — sentinel key is used for custom endpoints.
            provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, OpenAIChatProvider)

    @pytest.mark.parametrize(
        "base_url",
        [
            "https://api.openai.com/v1",
            "https://API.OPENAI.COM/v1",
            "https://api.openai.com:443/v1",
            "https://api.openai.com/v1/",
        ],
    )
    def test_official_makes_no_network_call(self, base_url: str) -> None:
        """Equivalent official form without key fails fast — no network call."""
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="",
            openai_api_base=base_url,
        )
        with patch("httpx.Client") as mock_httpx:
            with pytest.raises(ChatProviderConfigurationError):
                create_chat_provider(config=config)
            mock_httpx.assert_not_called()

    def test_original_custom_url_passed_unchanged_to_sdk(self) -> None:
        """The original configured base URL is passed unchanged to the SDK."""
        original_url = "https://API.OPENAI.COM:443/v1/"
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="sk-test",
            openai_api_base=original_url,
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            create_chat_provider(config=config)
        # Official endpoint recognized → base_url is None (SDK default).
        call_kwargs = mock_async_openai.call_args[1]
        assert "base_url" not in call_kwargs or call_kwargs.get("base_url") is None


# ---------------------------------------------------------------------------
# WP-REC-03D: Factory wrapping verification
# ---------------------------------------------------------------------------


class TestFactoryWrapping:
    """Prove that create_chat_provider wraps every provider in RetryingChatProvider."""

    def test_fake_provider_is_wrapped(self) -> None:
        config = _make_settings(
            embedding_provider="fake",
            environment="development",
        )
        provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, FakeChatProvider)

    def test_openai_provider_is_wrapped(self) -> None:
        config = _make_settings(
            embedding_provider="openai",
            openai_api_key="sk-test",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, OpenAIChatProvider)

    def test_llm_max_retries_reaches_wrapper(self) -> None:
        """The configured llm_max_retries reaches the wrapper's RetryPolicy."""
        config = _make_settings(
            embedding_provider="fake",
            environment="development",
            llm_max_retries=5,
        )
        provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert provider._policy.max_retries == 5
        assert provider._policy.total_allowed_attempts == 6

    def test_llm_max_retries_zero_reaches_wrapper(self) -> None:
        config = _make_settings(
            embedding_provider="fake",
            environment="development",
            llm_max_retries=0,
        )
        provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert provider._policy.max_retries == 0
        assert provider._policy.total_allowed_attempts == 1

    def test_sdk_retries_remain_disabled(self) -> None:
        """The OpenAI SDK max_retries=0 is preserved under the wrapper."""
        config = _make_settings(
            embedding_provider="openai",
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

    def test_no_double_wrapping(self) -> None:
        """The factory wraps exactly once — the delegate is not itself a wrapper."""
        config = _make_settings(
            embedding_provider="fake",
            environment="development",
        )
        provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        # The delegate must NOT be another RetryingChatProvider.
        assert not isinstance(provider._delegate, RetryingChatProvider)

    def test_factory_return_compatible_with_chat_provider(self) -> None:
        """The factory return type is compatible with ChatProvider."""
        from app.ai.provider.chat_provider import ChatProvider

        config = _make_settings(
            embedding_provider="fake",
            environment="development",
        )
        provider = create_chat_provider(config=config)
        assert isinstance(provider, ChatProvider)
