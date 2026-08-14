"""Unit tests for chat/embedding configuration separation (WP-REC-05 §3, §9.A).

Covers:

- chat-provider selection is independent of ``embedding_provider``;
- fake mode requires no API key;
- external mode validates only its own required configuration;
- chain order is exact and server-configured;
- OpenRouter paid model must be explicitly pinned (never guessed);
- secrets never appear in provider ``repr`` or error output.

All tests are offline: the OpenAI SDK client is patched out, so no external
provider is ever constructed for real, and no credentials are required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.ai.provider.exceptions import ChatProviderConfigurationError
from app.ai.provider.factory import _parse_chain_order, create_chat_provider
from app.ai.provider.fake_chat_provider import FakeChatProvider
from app.ai.provider.fallback_chain import FallbackChatProvider
from app.ai.provider.openai_chat_provider import OpenAIChatProvider
from app.ai.workflow.outage_handler import RetryingChatProvider
from app.config import Settings


def _make_settings(**overrides: object) -> Settings:
    """Build a Settings instance with chat/embedding fields covered."""
    defaults: dict[str, object] = {
        "environment": "development",
        "chat_provider_mode": "fake",
        "embedding_provider": "openai",
        "chat_provider_chain": "groq,openrouter",
        "openai_api_key": "",
        "openai_api_base": "https://api.openai.com/v1",
        "openai_chat_model": "gpt-4o-mini",
        "groq_api_key": "",
        "groq_api_base": "https://api.groq.com/openai/v1",
        "groq_chat_model": "openai/gpt-oss-120b",
        "openrouter_api_key": "",
        "openrouter_api_base": "https://openrouter.ai/api/v1",
        "openrouter_chat_model": "",
        "llm_timeout_seconds": 30,
        "llm_max_retries": 3,
        "ai_rate_limit_per_minute": 10,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


class TestChatEmbeddingIndependence:
    def test_chat_fake_embedding_openai_are_independent(self) -> None:
        config = _make_settings(
            chat_provider_mode="fake", embedding_provider="openai"
        )
        provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, FakeChatProvider)
        # Embedding provider remains independently selectable.
        assert config.embedding_provider == "openai"

    def test_chat_openai_embedding_fake_are_independent(self) -> None:
        config = _make_settings(
            chat_provider_mode="openai",
            embedding_provider="fake",
            openai_api_key="sk-test",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, OpenAIChatProvider)
        assert config.embedding_provider == "fake"

    def test_changing_embedding_provider_does_not_change_chat(self) -> None:
        config_openai_embedding = _make_settings(
            chat_provider_mode="fake", embedding_provider="openai"
        )
        config_fake_embedding = _make_settings(
            chat_provider_mode="fake", embedding_provider="fake"
        )
        p1 = create_chat_provider(config=config_openai_embedding)
        p2 = create_chat_provider(config=config_fake_embedding)
        assert isinstance(p1, RetryingChatProvider)
        assert isinstance(p2, RetryingChatProvider)
        assert isinstance(p1._delegate, FakeChatProvider)
        assert isinstance(p2._delegate, FakeChatProvider)


class TestFakeModeRequiresNoKey:
    def test_fake_mode_with_no_keys_succeeds(self) -> None:
        config = _make_settings(chat_provider_mode="fake")
        provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, FakeChatProvider)


class TestExternalModeValidatesOwnConfig:
    def test_chain_requires_groq_key(self) -> None:
        config = _make_settings(
            chat_provider_mode="chain",
            groq_api_key="",
            openrouter_api_key="or-key",
            openrouter_chat_model="meta-llama/llama-3.3-70b-instruct",
        )
        with pytest.raises(ChatProviderConfigurationError, match="Groq API key"):
            create_chat_provider(config=config)

    def test_chain_requires_openrouter_key(self) -> None:
        config = _make_settings(
            chat_provider_mode="chain",
            groq_api_key="groq-key",
            openrouter_api_key="",
            openrouter_chat_model="meta-llama/llama-3.3-70b-instruct",
        )
        with pytest.raises(
            ChatProviderConfigurationError, match="OpenRouter API key"
        ):
            create_chat_provider(config=config)

    def test_chain_requires_openrouter_model_pinned(self) -> None:
        config = _make_settings(
            chat_provider_mode="chain",
            groq_api_key="groq-key",
            openrouter_api_key="or-key",
            openrouter_chat_model="",
        )
        with pytest.raises(
            ChatProviderConfigurationError, match="explicitly pinned"
        ):
            create_chat_provider(config=config)

    def test_chain_with_complete_config_succeeds(self) -> None:
        config = _make_settings(
            chat_provider_mode="chain",
            groq_api_key="groq-key",
            openrouter_api_key="or-key",
            openrouter_chat_model="meta-llama/llama-3.3-70b-instruct",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert isinstance(provider, FallbackChatProvider)
        assert provider.provider_count == 2

    def test_openai_mode_does_not_require_groq_config(self) -> None:
        """OpenAI mode validates only OpenAI config, not Groq/OpenRouter."""
        config = _make_settings(
            chat_provider_mode="openai",
            openai_api_key="sk-test",
            groq_api_key="",
            openrouter_api_key="",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert isinstance(provider, RetryingChatProvider)
        assert isinstance(provider._delegate, OpenAIChatProvider)


class TestChainOrderExact:
    def test_parse_default_order(self) -> None:
        assert _parse_chain_order("groq,openrouter") == ["groq", "openrouter"]

    def test_parse_reordered(self) -> None:
        assert _parse_chain_order("openrouter,groq") == ["openrouter", "groq"]

    def test_parse_whitespace_and_empty_tokens(self) -> None:
        assert _parse_chain_order(" groq , openrouter ") == ["groq", "openrouter"]

    def test_parse_unknown_provider_rejected(self) -> None:
        with pytest.raises(ChatProviderConfigurationError, match="Unknown chain"):
            _parse_chain_order("groq,openai")

    def test_parse_duplicate_rejected(self) -> None:
        with pytest.raises(ChatProviderConfigurationError, match="Duplicate"):
            _parse_chain_order("groq,groq")

    def test_parse_empty_rejected(self) -> None:
        with pytest.raises(ChatProviderConfigurationError, match="must not be empty"):
            _parse_chain_order("")

    def test_chain_member_order_matches_config(self) -> None:
        config = _make_settings(
            chat_provider_mode="chain",
            chat_provider_chain="openrouter,groq",
            groq_api_key="groq-key",
            openrouter_api_key="or-key",
            openrouter_chat_model="meta-llama/llama-3.3-70b-instruct",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert isinstance(provider, FallbackChatProvider)
        assert provider._providers[0][0] == "openrouter"
        assert provider._providers[1][0] == "groq"


class TestSecretsAbsentFromOutput:
    def test_secret_key_not_in_repr(self) -> None:
        secret = "sk-super-secret-groq-key-12345"
        config = _make_settings(
            chat_provider_mode="chain",
            groq_api_key=secret,
            openrouter_api_key="or-key",
            openrouter_chat_model="meta-llama/llama-3.3-70b-instruct",
        )
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = create_chat_provider(config=config)
        assert secret not in repr(provider)

    def test_secret_key_not_in_config_error(self) -> None:
        secret = "sk-super-secret-groq-key-12345"
        config = _make_settings(
            chat_provider_mode="chain",
            groq_api_key="",
            openrouter_api_key=secret,
            openrouter_chat_model="",
        )
        with pytest.raises(ChatProviderConfigurationError) as exc_info:
            create_chat_provider(config=config)
        assert secret not in str(exc_info.value)


class TestGroqDefaultConfiguration:
    """Bounded WP-REC-05 remediation — Groq default model/mode/base URL.

    Pins the production defaults so the deprecated Groq model
    (``llama-3.3-70b-versatile``) cannot silently regress. All offline:
    no API key, no network, no ``.env`` file.
    """

    def test_default_groq_chat_model_is_gpt_oss_120b(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GROQ_CHAT_MODEL", raising=False)
        assert Settings().groq_chat_model == "openai/gpt-oss-120b"

    def test_default_groq_structured_output_mode_is_json_schema(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GROQ_STRUCTURED_OUTPUT_MODE", raising=False)
        assert Settings().groq_structured_output_mode == "json_schema"

    def test_default_groq_base_url_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("GROQ_API_BASE", raising=False)
        assert (
            Settings().groq_api_base == "https://api.groq.com/openai/v1"
        )

    def test_groq_chat_model_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GROQ_CHAT_MODEL", "custom-groq-model")
        assert Settings().groq_chat_model == "custom-groq-model"

    def test_groq_base_url_env_override(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("GROQ_API_BASE", "https://custom.groq/v1")
        assert Settings().groq_api_base == "https://custom.groq/v1"


class TestOpenRouterConfigurationUnchanged:
    """OpenRouter configuration and chain order remain unchanged."""

    def test_openrouter_chat_model_has_no_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENROUTER_CHAT_MODEL", raising=False)
        assert Settings().openrouter_chat_model == ""

    def test_openrouter_structured_output_mode_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENROUTER_STRUCTURED_OUTPUT_MODE", raising=False)
        assert (
            Settings().openrouter_structured_output_mode
            == "json_object"
        )

    def test_openrouter_base_url_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENROUTER_API_BASE", raising=False)
        assert (
            Settings().openrouter_api_base
            == "https://openrouter.ai/api/v1"
        )

    def test_default_chain_order_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CHAT_PROVIDER_CHAIN", raising=False)
        config = Settings()
        assert config.chat_provider_chain == "groq,openrouter"
        assert _parse_chain_order(config.chat_provider_chain) == [
            "groq",
            "openrouter",
        ]


class TestNoApiKeyNeededForConfiguration:
    """Configuration import/instantiation requires no API key (offline)."""

    def test_settings_instantiation_without_any_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        config = Settings()
        assert config.groq_api_key == ""
        assert config.openrouter_api_key == ""
        assert config.openai_api_key == ""
