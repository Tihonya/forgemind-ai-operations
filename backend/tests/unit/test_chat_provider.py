"""Unit tests for the chat provider abstraction.

Tests cover:
- ChatResult contract: frozen dataclass, required fields, defaults
- ChatProvider ABC: abstract, cannot be instantiated directly
- FakeChatProvider: determinism, schema flag, metadata, empty prompt
- OpenAIChatProvider: mocked API responses, error classification,
  timeout/retry configuration, base URL/model propagation,
  correlation/model/latency metadata, token usage, cancellation,
  no secrets in logs, no real network calls
- Exception hierarchy: correct subclass relationships
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import (
    ChatProviderConfigurationError,
    ChatProviderError,
    PermanentChatProviderError,
    TransientChatProviderError,
)
from app.ai.provider.fake_chat_provider import FakeChatProvider
from app.ai.provider.openai_chat_provider import OpenAIChatProvider

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Verify the chat provider exception class hierarchy."""

    def test_base_is_exception(self) -> None:
        assert issubclass(ChatProviderError, Exception)

    def test_transient_is_subclass_of_base(self) -> None:
        assert issubclass(TransientChatProviderError, ChatProviderError)

    def test_permanent_is_subclass_of_base(self) -> None:
        assert issubclass(PermanentChatProviderError, ChatProviderError)

    def test_configuration_is_subclass_of_base(self) -> None:
        assert issubclass(ChatProviderConfigurationError, ChatProviderError)

    def test_transient_not_subclass_of_permanent(self) -> None:
        assert not issubclass(TransientChatProviderError, PermanentChatProviderError)

    def test_permanent_not_subclass_of_transient(self) -> None:
        assert not issubclass(PermanentChatProviderError, TransientChatProviderError)


# ---------------------------------------------------------------------------
# ChatResult contract
# ---------------------------------------------------------------------------


class TestChatResultContract:
    """ChatResult is a frozen dataclass with the right fields and defaults."""

    def test_minimal_construction(self) -> None:
        result = ChatResult(content="hello", model="gpt-4o-mini", finish_reason="stop")
        assert result.content == "hello"
        assert result.model == "gpt-4o-mini"
        assert result.finish_reason == "stop"
        assert result.usage == {}
        assert result.metadata == {}

    def test_full_construction(self) -> None:
        result = ChatResult(
            content="response",
            model="gpt-4o-mini",
            finish_reason="length",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            metadata={"latency_ms": 42.0, "correlation_id": "abc"},
        )
        assert result.usage["total_tokens"] == 15
        assert result.metadata["correlation_id"] == "abc"

    def test_frozen_immutable(self) -> None:
        result = ChatResult(content="x", model="m", finish_reason="stop")
        with pytest.raises(AttributeError):
            result.content = "y"  # type: ignore[misc]

    def test_default_usage_is_independent(self) -> None:
        r1 = ChatResult(content="a", model="m", finish_reason="stop")
        r2 = ChatResult(content="b", model="m", finish_reason="stop")
        r1.usage["x"] = 1
        assert "x" not in r2.usage


# ---------------------------------------------------------------------------
# ChatProvider ABC
# ---------------------------------------------------------------------------


class TestChatProviderABC:
    """ChatProvider is abstract and cannot be instantiated directly."""

    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            ChatProvider()  # type: ignore[abstract]

    def test_subclass_with_complete_works(self) -> None:
        class MyProvider(ChatProvider):
            async def complete(
                self,
                prompt: str,
                schema: dict[str, Any] | None = None,
                context: dict[str, Any] | None = None,
            ) -> ChatResult:
                return ChatResult(content="ok", model="test", finish_reason="stop")

        provider = MyProvider()
        assert isinstance(provider, ChatProvider)


# ---------------------------------------------------------------------------
# FakeChatProvider
# ---------------------------------------------------------------------------


class TestFakeChatProviderConfiguration:
    def test_default_model(self) -> None:
        provider = FakeChatProvider()
        assert provider._model == "fake-chat-model"

    def test_custom_model(self) -> None:
        provider = FakeChatProvider(model="my-fake")
        assert provider._model == "my-fake"

    def test_empty_model_raises(self) -> None:
        with pytest.raises(ChatProviderConfigurationError, match="model"):
            FakeChatProvider(model="")


class TestFakeChatProviderDeterminism:
    """Same prompt must produce the same ChatResult content across calls."""

    @pytest.mark.asyncio
    async def test_same_prompt_same_content(self) -> None:
        provider = FakeChatProvider()
        r1 = await provider.complete("test prompt")
        r2 = await provider.complete("test prompt")
        assert r1.content == r2.content

    @pytest.mark.asyncio
    async def test_same_prompt_across_instances(self) -> None:
        p1 = FakeChatProvider()
        p2 = FakeChatProvider()
        r1 = await p1.complete("cross instance")
        r2 = await p2.complete("cross instance")
        assert r1.content == r2.content

    @pytest.mark.asyncio
    async def test_different_prompt_different_content(self) -> None:
        provider = FakeChatProvider()
        r1 = await provider.complete("prompt A")
        r2 = await provider.complete("prompt B")
        assert r1.content != r2.content

    @pytest.mark.asyncio
    async def test_content_contains_prompt_hash(self) -> None:
        import hashlib

        provider = FakeChatProvider()
        result = await provider.complete("hashable prompt")
        body = json.loads(result.content)
        expected = hashlib.sha256(b"hashable prompt").hexdigest()
        assert body["prompt_hash"] == expected

    @pytest.mark.asyncio
    async def test_schema_flag_reflected(self) -> None:
        provider = FakeChatProvider()
        r1 = await provider.complete("p", schema={"type": "object"})
        r2 = await provider.complete("p")
        body1 = json.loads(r1.content)
        body2 = json.loads(r2.content)
        assert body1["schema_requested"] is True
        assert body2["schema_requested"] is False

    @pytest.mark.asyncio
    async def test_finish_reason_is_stop(self) -> None:
        provider = FakeChatProvider()
        result = await provider.complete("p")
        assert result.finish_reason == "stop"


class TestFakeChatProviderMetadata:
    @pytest.mark.asyncio
    async def test_metadata_has_latency(self) -> None:
        provider = FakeChatProvider()
        result = await provider.complete("p")
        assert "latency_ms" in result.metadata
        assert result.metadata["provider"] == "fake"

    @pytest.mark.asyncio
    async def test_metadata_has_correlation_id_when_provided(self) -> None:
        provider = FakeChatProvider()
        result = await provider.complete(
            "p", context={"correlation_id": "corr-123"}
        )
        assert result.metadata["correlation_id"] == "corr-123"

    @pytest.mark.asyncio
    async def test_metadata_no_correlation_id_when_absent(self) -> None:
        provider = FakeChatProvider()
        result = await provider.complete("p")
        assert "correlation_id" not in result.metadata

    @pytest.mark.asyncio
    async def test_usage_empty_for_fake(self) -> None:
        provider = FakeChatProvider()
        result = await provider.complete("p")
        assert result.usage == {}

    @pytest.mark.asyncio
    async def test_empty_prompt_raises(self) -> None:
        provider = FakeChatProvider()
        with pytest.raises(ChatProviderConfigurationError, match="prompt"):
            await provider.complete("")


class TestFakeChatProviderClockInjection:
    """Clock injection produces deterministic latency."""

    @pytest.mark.asyncio
    async def test_clock_injection(self) -> None:
        times = iter([100.0, 100.05])
        provider = FakeChatProvider(clock=lambda: next(times))
        result = await provider.complete("p")
        assert result.metadata["latency_ms"] == 50.0

    @pytest.mark.asyncio
    async def test_no_network_calls(self) -> None:
        provider = FakeChatProvider()
        with patch("httpx.Client") as mock_client:
            await provider.complete("p")
            mock_client.assert_not_called()


# ---------------------------------------------------------------------------
# OpenAIChatProvider construction
# ---------------------------------------------------------------------------


class TestOpenAIChatProviderInit:
    def test_default_construction(self) -> None:
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = OpenAIChatProvider(api_key="test-key")
        assert provider._model == "gpt-4o-mini"

    def test_custom_model(self) -> None:
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = OpenAIChatProvider(api_key="test-key", model="custom-model")
        assert provider._model == "custom-model"

    def test_empty_api_key_raises(self) -> None:
        with pytest.raises(ChatProviderConfigurationError, match="api_key"):
            OpenAIChatProvider(api_key="")

    def test_empty_model_raises(self) -> None:
        with pytest.raises(ChatProviderConfigurationError, match="model"):
            OpenAIChatProvider(api_key="test-key", model="")

    def test_zero_timeout_raises(self) -> None:
        with pytest.raises(ChatProviderConfigurationError, match="timeout"):
            OpenAIChatProvider(api_key="test-key", timeout_seconds=0)

    def test_negative_timeout_raises(self) -> None:
        with pytest.raises(ChatProviderConfigurationError, match="timeout"):
            OpenAIChatProvider(api_key="test-key", timeout_seconds=-1)

    def test_zero_rate_limit_raises(self) -> None:
        with pytest.raises(ChatProviderConfigurationError, match="rate_limit"):
            OpenAIChatProvider(api_key="test-key", rate_limit_per_minute=0)

    def test_max_retries_zero_is_passed(self) -> None:
        """AsyncOpenAI must be constructed with max_retries=0."""
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            OpenAIChatProvider(api_key="test-key")
            call_kwargs = mock_async_openai.call_args[1]
            assert call_kwargs["max_retries"] == 0

    def test_timeout_passed_to_client(self) -> None:
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            OpenAIChatProvider(api_key="test-key", timeout_seconds=45)
            call_kwargs = mock_async_openai.call_args[1]
            assert call_kwargs["timeout"] == 45.0

    def test_base_url_passed_to_client(self) -> None:
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            OpenAIChatProvider(
                api_key="test-key", base_url="http://localhost:8080/v1"
            )
            call_kwargs = mock_async_openai.call_args[1]
            assert call_kwargs["base_url"] == "http://localhost:8080/v1"

    def test_client_injection_bypasses_asyncopenai(self) -> None:
        mock_client = AsyncMock()
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        assert provider._client is mock_client


# ---------------------------------------------------------------------------
# OpenAIChatProvider.complete — successful responses
# ---------------------------------------------------------------------------


def _make_mock_response(
    content: str = "Hello!",
    finish_reason: str = "stop",
    model: str = "gpt-4o-mini",
    usage: dict[str, int] | None = None,
    response_id: str = "resp-123",
) -> Any:
    """Build a mock ChatCompletion response object."""
    mock_message = MagicMock()
    mock_message.content = content
    mock_message.role = "assistant"

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = finish_reason
    mock_choice.index = 0

    mock_usage = None
    if usage is not None:
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = usage.get("prompt_tokens", 0)
        mock_usage.completion_tokens = usage.get("completion_tokens", 0)
        mock_usage.total_tokens = usage.get("total_tokens", 0)

    mock_response = MagicMock()
    mock_response.id = response_id
    mock_response.choices = [mock_choice]
    mock_response.model = model
    mock_response.usage = mock_usage
    return mock_response


class TestOpenAIChatProviderComplete:
    @pytest.mark.asyncio
    async def test_successful_completion(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(content="Hello!")
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        result = await provider.complete("Say hello")

        assert result.content == "Hello!"
        assert result.model == "gpt-4o-mini"
        assert result.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_empty_prompt_raises(self) -> None:
        mock_client = AsyncMock()
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(ChatProviderConfigurationError, match="prompt"):
            await provider.complete("")

    @pytest.mark.asyncio
    async def test_correlation_id_in_metadata(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response()
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        result = await provider.complete(
            "p", context={"correlation_id": "corr-abc"}
        )
        assert result.metadata["correlation_id"] == "corr-abc"

    @pytest.mark.asyncio
    async def test_latency_in_metadata(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response()
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        result = await provider.complete("p")
        assert "latency_ms" in result.metadata
        assert isinstance(result.metadata["latency_ms"], float)

    @pytest.mark.asyncio
    async def test_response_id_in_metadata(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(response_id="resp-xyz")
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        result = await provider.complete("p")
        assert result.metadata["response_id"] == "resp-xyz"

    @pytest.mark.asyncio
    async def test_token_usage_when_available(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
            )
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        result = await provider.complete("p")
        assert result.usage["prompt_tokens"] == 10
        assert result.usage["completion_tokens"] == 5
        assert result.usage["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_token_usage_empty_when_not_available(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(usage=None)
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        result = await provider.complete("p")
        assert result.usage == {}

    @pytest.mark.asyncio
    async def test_model_name_in_result(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(model="custom-model")
        )
        provider = OpenAIChatProvider(
            api_key="test-key", model="custom-model", client=mock_client
        )
        result = await provider.complete("p")
        assert result.model == "custom-model"

    @pytest.mark.asyncio
    async def test_finish_reason_propagated(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(finish_reason="length")
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        result = await provider.complete("p")
        assert result.finish_reason == "length"

    @pytest.mark.asyncio
    async def test_null_content_becomes_empty_string(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(content=None)  # type: ignore[arg-type]
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        result = await provider.complete("p")
        assert result.content == ""


# ---------------------------------------------------------------------------
# Error classification — transient
# ---------------------------------------------------------------------------


class TestTransientErrorMapping:
    @pytest.mark.asyncio
    async def test_api_connection_error_raises_transient(self) -> None:
        from openai import APIConnectionError

        original = APIConnectionError(message="Connection refused", request=MagicMock())
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(TransientChatProviderError) as exc_info:
            await provider.complete("p")
        assert exc_info.value.__cause__ is original

    @pytest.mark.asyncio
    async def test_api_timeout_error_raises_transient(self) -> None:
        from openai import APITimeoutError

        original = APITimeoutError(request=MagicMock())
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(TransientChatProviderError) as exc_info:
            await provider.complete("p")
        assert exc_info.value.__cause__ is original

    @pytest.mark.asyncio
    async def test_rate_limit_error_raises_transient(self) -> None:
        from openai import RateLimitError

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = RateLimitError(
            message="Rate limit exceeded", response=mock_response, body=None
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(TransientChatProviderError) as exc_info:
            await provider.complete("p")
        assert exc_info.value.__cause__ is original

    @pytest.mark.asyncio
    async def test_internal_server_error_raises_transient(self) -> None:
        from openai import InternalServerError

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = InternalServerError(
            message="Internal server error", response=mock_response, body=None
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(TransientChatProviderError) as exc_info:
            await provider.complete("p")
        assert exc_info.value.__cause__ is original

    @pytest.mark.asyncio
    async def test_5xx_api_status_error_raises_transient(self) -> None:
        from openai import APIStatusError

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = APIStatusError(
            message="Service unavailable", response=mock_response, body=None
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(TransientChatProviderError):
            await provider.complete("p")


# ---------------------------------------------------------------------------
# Error classification — permanent
# ---------------------------------------------------------------------------


class TestPermanentErrorMapping:
    @pytest.mark.asyncio
    async def test_authentication_error_raises_permanent(self) -> None:
        from openai import AuthenticationError

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = AuthenticationError(
            message="Invalid API key", response=mock_response, body=None
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(PermanentChatProviderError) as exc_info:
            await provider.complete("p")
        assert exc_info.value.__cause__ is original

    @pytest.mark.asyncio
    async def test_permission_denied_error_raises_permanent(self) -> None:
        from openai import PermissionDeniedError

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = PermissionDeniedError(
            message="Permission denied", response=mock_response, body=None
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(PermanentChatProviderError):
            await provider.complete("p")

    @pytest.mark.asyncio
    async def test_bad_request_error_raises_permanent(self) -> None:
        from openai import BadRequestError

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = BadRequestError(
            message="Bad request", response=mock_response, body=None
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(PermanentChatProviderError):
            await provider.complete("p")

    @pytest.mark.asyncio
    async def test_4xx_api_status_error_raises_permanent(self) -> None:
        from openai import APIStatusError

        mock_response = MagicMock()
        mock_response.status_code = 418
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = APIStatusError(
            message="I'm a teapot", response=mock_response, body=None
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(PermanentChatProviderError):
            await provider.complete("p")

    @pytest.mark.asyncio
    async def test_no_choices_raises_permanent(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = []
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(PermanentChatProviderError, match="no choices"):
            await provider.complete("p")


# ---------------------------------------------------------------------------
# Error classification — unrecognised
# ---------------------------------------------------------------------------


class TestUnrecognisedErrorMapping:
    @pytest.mark.asyncio
    async def test_unrecognised_error_raises_permanent(self) -> None:
        original = RuntimeError("Unknown SDK error")
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(PermanentChatProviderError) as exc_info:
            await provider.complete("p")
        assert exc_info.value.__cause__ is original


# ---------------------------------------------------------------------------
# Configuration error mapping
# ---------------------------------------------------------------------------


class TestConfigurationErrorMapping:
    def test_empty_api_key(self) -> None:
        with pytest.raises(ChatProviderConfigurationError):
            OpenAIChatProvider(api_key="")

    def test_empty_model(self) -> None:
        with pytest.raises(ChatProviderConfigurationError):
            OpenAIChatProvider(api_key="test-key", model="")

    def test_invalid_timeout(self) -> None:
        with pytest.raises(ChatProviderConfigurationError):
            OpenAIChatProvider(api_key="test-key", timeout_seconds=0)

    @pytest.mark.asyncio
    async def test_empty_prompt(self) -> None:
        mock_client = AsyncMock()
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(ChatProviderConfigurationError, match="prompt"):
            await provider.complete("")


# ---------------------------------------------------------------------------
# No secrets in logs
# ---------------------------------------------------------------------------


class TestNoSecretsInLogs:
    """API keys and response content must never appear in log output."""

    @pytest.mark.asyncio
    async def test_no_api_key_in_success_log(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response(content="sensitive response")
        )
        provider = OpenAIChatProvider(api_key="sk-super-secret-key", client=mock_client)
        with patch("app.ai.provider.openai_chat_provider._logger") as mock_logger:
            await provider.complete("p")
            # Check the success log call
            success_call = mock_logger.info.call_args
            assert success_call is not None
            log_str = str(success_call)
            assert "sk-super-secret-key" not in log_str
            assert "sensitive response" not in log_str

    @pytest.mark.asyncio
    async def test_no_api_key_in_error_log(self) -> None:
        from openai import AuthenticationError

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = AuthenticationError(
            message="Invalid API key sk-super-secret-key",
            response=mock_response,
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="sk-super-secret-key", client=mock_client)
        with patch("app.ai.provider.openai_chat_provider._logger") as mock_logger:
            with pytest.raises(PermanentChatProviderError):
                await provider.complete("p")
            warning_call = mock_logger.warning.call_args
            assert warning_call is not None
            log_str = str(warning_call)
            assert "sk-super-secret-key" not in log_str


# ---------------------------------------------------------------------------
# Cancellation propagation
# ---------------------------------------------------------------------------


class TestCancellationPropagation:
    @pytest.mark.asyncio
    async def test_asyncio_cancellation_propagates(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=asyncio.CancelledError()
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with pytest.raises(asyncio.CancelledError):
            await provider.complete("p")


# ---------------------------------------------------------------------------
# No real network calls
# ---------------------------------------------------------------------------


class TestNoRealNetworkCalls:
    @pytest.mark.asyncio
    async def test_no_httpx_call_during_complete(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response()
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with patch("httpx.Client") as mock_httpx:
            await provider.complete("p")
            mock_httpx.assert_not_called()

    @pytest.mark.asyncio
    async def test_fake_provider_no_network(self) -> None:
        provider = FakeChatProvider()
        with patch("httpx.Client") as mock_httpx:
            await provider.complete("p")
            mock_httpx.assert_not_called()


# ---------------------------------------------------------------------------
# Remediation: run_id propagation
# ---------------------------------------------------------------------------


class TestRunIdPropagation:
    """run_id from context must appear in logs and ChatResult metadata."""

    @pytest.mark.asyncio
    async def test_openai_run_id_in_metadata(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response()
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        result = await provider.complete("p", context={"run_id": "run-xyz"})
        assert result.metadata["run_id"] == "run-xyz"

    @pytest.mark.asyncio
    async def test_openai_run_id_in_success_log(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response()
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with patch("app.ai.provider.openai_chat_provider._logger") as mock_logger:
            await provider.complete("p", context={"run_id": "run-abc"})
            log_str = str(mock_logger.info.call_args)
            assert "run-abc" in log_str

    @pytest.mark.asyncio
    async def test_openai_run_id_absent_when_not_provided(self) -> None:
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response()
        )
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        result = await provider.complete("p")
        assert "run_id" not in result.metadata

    @pytest.mark.asyncio
    async def test_openai_run_id_in_error_log(self) -> None:
        from openai import AuthenticationError

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = AuthenticationError(
            message="Invalid key", response=mock_response, body=None
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with patch("app.ai.provider.openai_chat_provider._logger") as mock_logger:
            with pytest.raises(PermanentChatProviderError):
                await provider.complete("p", context={"run_id": "run-err"})
            log_str = str(mock_logger.warning.call_args)
            assert "run-err" in log_str

    @pytest.mark.asyncio
    async def test_fake_run_id_in_metadata(self) -> None:
        provider = FakeChatProvider()
        result = await provider.complete("p", context={"run_id": "run-fake"})
        assert result.metadata["run_id"] == "run-fake"

    @pytest.mark.asyncio
    async def test_fake_run_id_in_success_log(self) -> None:
        provider = FakeChatProvider()
        with patch("app.ai.provider.fake_chat_provider._logger") as mock_logger:
            await provider.complete("p", context={"run_id": "run-fk2"})
            log_str = str(mock_logger.info.call_args)
            assert "run-fk2" in log_str


# ---------------------------------------------------------------------------
# Remediation: sanitized error log for response-processing failures
# ---------------------------------------------------------------------------


class TestResponseProcessingErrorLog:
    """Failures while processing a returned response must produce a sanitized error log."""

    @pytest.mark.asyncio
    async def test_no_choices_produces_error_log(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = []
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with patch("app.ai.provider.openai_chat_provider._logger") as mock_logger:
            with pytest.raises(PermanentChatProviderError, match="no choices"):
                await provider.complete("p", context={"run_id": "run-r1"})
            # Error log must be produced
            assert mock_logger.warning.called
            log_str = str(mock_logger.warning.call_args)
            assert "error" in log_str
            assert "run-r1" in log_str

    @pytest.mark.asyncio
    async def test_no_message_produces_error_log(self) -> None:
        mock_choice = MagicMock()
        mock_choice.message = None
        mock_choice.finish_reason = "stop"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.id = "resp-1"
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with patch("app.ai.provider.openai_chat_provider._logger") as mock_logger:
            with pytest.raises(PermanentChatProviderError, match="no message"):
                await provider.complete("p", context={"run_id": "run-r2"})
            assert mock_logger.warning.called
            log_str = str(mock_logger.warning.call_args)
            assert "run-r2" in log_str

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "response_content,should_not_appear",
        [
            ("sensitive-response-content", "sensitive-response-content"),
            ("sk-secret-key-in-response", "sk-secret-key-in-response"),
        ],
    )
    async def test_no_response_content_in_error_log(
        self,
        response_content: str,
        should_not_appear: str,
    ) -> None:
        """Error log for response-processing failures must not contain response content."""
        mock_choice = MagicMock()
        mock_choice.message = None
        mock_choice.finish_reason = "stop"
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.id = response_content  # inject sensitive content into response
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        provider = OpenAIChatProvider(api_key="test-key", client=mock_client)
        with patch("app.ai.provider.openai_chat_provider._logger") as mock_logger:
            with pytest.raises(PermanentChatProviderError):
                await provider.complete("p")
            log_str = str(mock_logger.warning.call_args)
            assert should_not_appear not in log_str


# ---------------------------------------------------------------------------
# Remediation: rate limiter
# ---------------------------------------------------------------------------


class TestRateLimiter:
    """Process-local sliding-window rate limiter tests."""

    def test_rate_limiter_stored_on_provider(self) -> None:
        with patch(
            "app.ai.provider.openai_chat_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = OpenAIChatProvider(
                api_key="test-key", rate_limit_per_minute=5
            )
        assert provider._rate_limiter._max_calls == 5

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_after_max(self) -> None:
        """Calls beyond the limit block until the window slides."""
        from app.ai.provider.openai_chat_provider import _SlidingWindowRateLimiter

        # Use a manual clock to control time.
        current_time = [100.0]
        clock = lambda: current_time[0]  # noqa: E731

        limiter = _SlidingWindowRateLimiter(max_calls=2, clock=clock)

        # First two calls acquire immediately.
        await limiter.acquire()
        await limiter.acquire()

        # Third call should block. Use asyncio.wait_for with a short timeout
        # to verify it does NOT acquire immediately.
        try:
            await asyncio.wait_for(limiter.acquire(), timeout=0.1)
            # If it acquired, the test fails — limit not enforced.
            raise AssertionError("Rate limiter did not block third call")
        except TimeoutError:
            pass  # Expected: third call blocked.

        # Advance time past the window; third call should now succeed.
        current_time[0] = 161.0  # 61 seconds later
        await asyncio.wait_for(limiter.acquire(), timeout=0.5)

    @pytest.mark.asyncio
    async def test_rate_limit_cancellation_does_not_consume_slot(self) -> None:
        """If the rate limiter wait is cancelled, no slot is consumed."""
        from app.ai.provider.openai_chat_provider import _SlidingWindowRateLimiter

        current_time = [100.0]
        clock = lambda: current_time[0]  # noqa: E731

        limiter = _SlidingWindowRateLimiter(max_calls=1, clock=clock)

        # Consume the one available slot.
        await limiter.acquire()

        # Start a second acquire that will block, then cancel it.
        task = asyncio.create_task(limiter.acquire())
        await asyncio.sleep(0.05)  # Let it start waiting.
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Advance time — the cancelled acquire should NOT have consumed a slot.
        # The next acquire should succeed immediately (the first slot expired).
        current_time[0] = 161.0
        await asyncio.wait_for(limiter.acquire(), timeout=0.5)

    @pytest.mark.asyncio
    async def test_rate_limiter_enforced_before_api_call(self) -> None:
        """The provider calls the rate limiter before the API client."""
        from app.ai.provider.openai_chat_provider import _SlidingWindowRateLimiter

        current_time = [100.0]
        clock = lambda: current_time[0]  # noqa: E731

        limiter = _SlidingWindowRateLimiter(max_calls=1, clock=clock)
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_mock_response()
        )
        provider = OpenAIChatProvider(
            api_key="test-key", client=mock_client, rate_limiter=limiter
        )

        # First call succeeds.
        await provider.complete("p")
        assert mock_client.chat.completions.create.call_count == 1

        # Second call should block because rate limit is exhausted.
        try:
            await asyncio.wait_for(provider.complete("p"), timeout=0.1)
            raise AssertionError("Second call was not rate-limited")
        except TimeoutError:
            pass

        # API client should not have been called a second time.
        assert mock_client.chat.completions.create.call_count == 1
