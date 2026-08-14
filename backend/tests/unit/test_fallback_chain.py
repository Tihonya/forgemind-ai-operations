"""Unit tests for the ordered chat-provider fallback chain (WP-REC-05).

Covers the bounded fallback semantics (§5, §9.B):

- first-provider success → later providers not invoked;
- transient exhaustion → advance to the next provider exactly once;
- all providers exhausted → terminal ``TransientChatProviderError``
  (the existing ``FAILED_PROVIDER`` path);
- permanent error → no fallback;
- HTTP 402 (budget/credit exhaustion) equivalent → permanent → no fallback;
- configuration error → no fallback;
- attempt history is safe and ordered;
- total calls are bounded by chain length.

All tests are offline: no external provider, no network, no credentials.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import (
    ChatProviderConfigurationError,
    PermanentChatProviderError,
    TransientChatProviderError,
)
from app.ai.provider.fallback_chain import FallbackChatProvider


class _SuccessProvider(ChatProvider):
    """Deterministic provider that returns a successful ChatResult."""

    def __init__(self, name: str = "success") -> None:
        self._name = name
        self.calls = 0

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        self.calls += 1
        return ChatResult(
            content="ok",
            model=f"{self._name}-model",
            finish_reason="stop",
            metadata={"provider": self._name},
        )


class _TransientProvider(ChatProvider):
    """Provider that always raises a transient error (retry budget exhausted)."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        self.calls += 1
        raise TransientChatProviderError("transient failure")


class _PermanentProvider(ChatProvider):
    """Provider that always raises a permanent error."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        self.calls += 1
        raise PermanentChatProviderError("permanent failure")


class _ConfigErrorProvider(ChatProvider):
    """Provider that raises a configuration error at call time."""

    def __init__(self) -> None:
        self.calls = 0

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        self.calls += 1
        raise ChatProviderConfigurationError("config failure")


class TestChainConstruction:
    def test_empty_chain_raises(self) -> None:
        with pytest.raises(ChatProviderConfigurationError, match="at least one"):
            FallbackChatProvider(providers=[])

    def test_provider_count(self) -> None:
        chain = FallbackChatProvider(
            providers=[("groq", _SuccessProvider()), ("openrouter", _SuccessProvider())]
        )
        assert chain.provider_count == 2


class TestChainOrdering:
    @pytest.mark.asyncio
    async def test_first_success_no_fallback(self) -> None:
        first = _SuccessProvider("groq")
        second = _SuccessProvider("openrouter")
        chain = FallbackChatProvider(
            providers=[("groq", first), ("openrouter", second)]
        )
        result = await chain.complete("p")

        assert first.calls == 1
        assert second.calls == 0
        assert result.metadata["chain_position"] == 0
        assert result.metadata["chain_provider"] == "groq"
        assert result.metadata["chain_provider_count"] == 2
        assert result.metadata["chain_attempt_history"] == []

    @pytest.mark.asyncio
    async def test_transient_then_fallback_invoked_once(self) -> None:
        transient = _TransientProvider()
        fallback = _SuccessProvider("openrouter")
        chain = FallbackChatProvider(
            providers=[("groq", transient), ("openrouter", fallback)]
        )
        result = await chain.complete("p")

        assert transient.calls == 1
        assert fallback.calls == 1
        assert result.metadata["chain_position"] == 1
        assert result.metadata["chain_provider"] == "openrouter"
        history = result.metadata["chain_attempt_history"]
        assert len(history) == 1
        assert history[0]["chain_position"] == 0
        assert history[0]["provider"] == "groq"
        assert history[0]["outcome"] == "exhausted"
        assert history[0]["error_type"] == "TransientChatProviderError"

    @pytest.mark.asyncio
    async def test_all_exhausted_raises_transient(self) -> None:
        t1 = _TransientProvider()
        t2 = _TransientProvider()
        chain = FallbackChatProvider(
            providers=[("groq", t1), ("openrouter", t2)]
        )
        with pytest.raises(TransientChatProviderError):
            await chain.complete("p")
        assert t1.calls == 1
        assert t2.calls == 1


class TestNoFallbackOnPermanent:
    @pytest.mark.asyncio
    async def test_permanent_error_no_fallback(self) -> None:
        permanent = _PermanentProvider()
        fallback = _SuccessProvider("openrouter")
        chain = FallbackChatProvider(
            providers=[("groq", permanent), ("openrouter", fallback)]
        )
        with pytest.raises(PermanentChatProviderError):
            await chain.complete("p")
        assert permanent.calls == 1
        assert fallback.calls == 0

    @pytest.mark.asyncio
    async def test_config_error_no_fallback(self) -> None:
        config_error = _ConfigErrorProvider()
        fallback = _SuccessProvider("openrouter")
        chain = FallbackChatProvider(
            providers=[("groq", config_error), ("openrouter", fallback)]
        )
        with pytest.raises(ChatProviderConfigurationError):
            await chain.complete("p")
        assert config_error.calls == 1
        assert fallback.calls == 0

    @pytest.mark.asyncio
    async def test_http_402_equivalent_no_fallback(self) -> None:
        """OpenRouter HTTP 402 (budget/credit exhaustion) → permanent → no fallback.

        The OpenAI SDK maps an HTTP 402 ``APIStatusError`` to a
        ``PermanentChatProviderError`` (4xx → permanent). The chain must not
        advance past it and must not route to another provider.
        """
        from openai import APIStatusError

        from app.ai.provider.openai_chat_provider import OpenAIChatProvider

        mock_response = MagicMock()
        mock_response.status_code = 402
        mock_response.headers = {}
        mock_response.request = MagicMock()
        original = APIStatusError(
            message="Payment required", response=mock_response, body=None
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=original)
        openrouter = OpenAIChatProvider(
            api_key="test-key",
            provider_name="openrouter",
            client=mock_client,
        )
        fallback = _SuccessProvider("groq")
        chain = FallbackChatProvider(
            providers=[("openrouter", openrouter), ("groq", fallback)]
        )
        with pytest.raises(PermanentChatProviderError):
            await chain.complete("p")
        assert fallback.calls == 0


class TestAttemptHistorySafety:
    @pytest.mark.asyncio
    async def test_attempt_history_safe_and_ordered(self) -> None:
        """Attempt history is ordered and contains only safe bounded fields."""
        t1 = _TransientProvider()
        t2 = _TransientProvider()
        success = _SuccessProvider("third")
        chain = FallbackChatProvider(
            providers=[("groq", t1), ("openrouter", t2), ("third", success)]
        )
        result = await chain.complete("PROMPT-SECRET-VALUE-12345")

        history = result.metadata["chain_attempt_history"]
        assert [h["chain_position"] for h in history] == [0, 1]
        assert [h["provider"] for h in history] == ["groq", "openrouter"]
        for record in history:
            assert set(record.keys()) == {
                "chain_position",
                "provider",
                "outcome",
                "error_type",
            }
        # Never contains prompt text, response content, or context values.
        assert "PROMPT-SECRET-VALUE-12345" not in str(history)

    @pytest.mark.asyncio
    async def test_total_calls_bounded_by_chain_length(self) -> None:
        """Each provider is invoked at most once by the chain (no nested retry)."""
        providers = [_TransientProvider() for _ in range(3)]
        chain = FallbackChatProvider(
            providers=[
                ("p0", providers[0]),
                ("p1", providers[1]),
                ("p2", providers[2]),
            ]
        )
        with pytest.raises(TransientChatProviderError):
            await chain.complete("p")
        assert [p.calls for p in providers] == [1, 1, 1]
