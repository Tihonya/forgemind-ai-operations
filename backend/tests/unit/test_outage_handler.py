"""Unit tests for RetryingChatProvider (WP-REC-03D).

Tests cover:

- immediate success (zero retries);
- transient failure then success;
- multiple transient failures then success;
- transient exhaustion;
- permanent failure without retry;
- configuration failure without retry;
- cancellation during provider call;
- cancellation during backoff sleep;
- unknown exception without retry;
- context passthrough;
- schema and prompt passthrough;
- safe logging fields;
- absence of raw exception messages and sensitive context;
- 1-based attempt numbering;
- delegate metadata preservation;
- deterministic metadata collision behavior;
- no real sleeping.

All tests use fake providers and a recording sleeper — no real network
calls, no real waiting.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import (
    ChatProviderConfigurationError,
    PermanentChatProviderError,
    TransientChatProviderError,
)
from app.ai.workflow.outage_handler import RetryingChatProvider
from app.ai.workflow.retry_policy import RetryPolicy

# ---------------------------------------------------------------------------\
# Test doubles
# ---------------------------------------------------------------------------


class _ScriptedProvider(ChatProvider):
    """Fake provider that follows a scripted sequence of results/exceptions.

    Records every call for assertion: prompt, schema, context.
    """

    def __init__(
        self,
        *,
        script: list[ChatResult | BaseException],
        result: ChatResult | None = None,
    ) -> None:
        self._script = list(script)
        self._fallback_result = result
        self.calls: list[dict[str, Any]] = []
        self.call_count: int = 0

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        self.calls.append({
            "prompt": prompt,
            "schema": schema,
            "context": dict(context) if context else {},
        })
        self.call_count += 1
        if self._script:
            item = self._script.pop(0)
        elif self._fallback_result is not None:
            return self._fallback_result
        else:
            item = _make_chat_result()
        if isinstance(item, BaseException):
            raise item
        return item


class _RecordingSleeper:
    """Records sleep durations without actually waiting."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []
        self._fail_on_next: BaseException | None = None

    def set_fail_on_next(self, exc: BaseException) -> None:
        self._fail_on_next = exc

    async def __call__(self, delay: float) -> None:
        self.sleeps.append(delay)
        if self._fail_on_next is not None:
            exc = self._fail_on_next
            self._fail_on_next = None
            raise exc


def _make_chat_result(
    *,
    content: str = '{"test": true}',
    model: str = "fake-model",
    finish_reason: str = "stop",
    usage: dict[str, int] | None = None,
    metadata: dict[str, Any] | None = None,
) -> ChatResult:
    return ChatResult(
        content=content,
        model=model,
        finish_reason=finish_reason,
        usage=usage or {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        metadata=metadata or {"latency_ms": 42.0, "provider": "fake"},
    )


def _make_policy(max_retries: int = 3) -> RetryPolicy:
    return RetryPolicy(max_retries=max_retries)


def _make_context() -> dict[str, Any]:
    return {
        "correlation_id": str(uuid4()),
        "run_id": str(uuid4()),
    }


# ---------------------------------------------------------------------------\
# Immediate success
# ---------------------------------------------------------------------------


class TestImmediateSuccess:
    async def test_zero_retries_on_success(self) -> None:
        provider = _ScriptedProvider(script=[_make_chat_result()])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        assert provider.call_count == 1
        assert result.metadata["retry_count"] == 0

    async def test_no_sleep_on_immediate_success(self) -> None:
        sleeper = _RecordingSleeper()
        provider = _ScriptedProvider(script=[_make_chat_result()])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=sleeper,
        )
        await wrapper.complete("test", context=_make_context())
        assert sleeper.sleeps == []


# ---------------------------------------------------------------------------\
# Transient failure then success
# ---------------------------------------------------------------------------


class TestTransientThenSuccess:
    async def test_one_transient_then_success(self) -> None:
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("timeout"),
            _make_chat_result(),
        ])
        sleeper = _RecordingSleeper()
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=sleeper,
        )
        result = await wrapper.complete("test", context=_make_context())
        assert provider.call_count == 2
        assert result.metadata["retry_count"] == 1
        assert len(sleeper.sleeps) == 1
        assert sleeper.sleeps[0] == pytest.approx(1.0)

    async def test_multiple_transients_then_success(self) -> None:
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("timeout 1"),
            TransientChatProviderError("timeout 2"),
            TransientChatProviderError("timeout 3"),
            _make_chat_result(),
        ])
        sleeper = _RecordingSleeper()
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=sleeper,
        )
        result = await wrapper.complete("test", context=_make_context())
        assert provider.call_count == 4
        assert result.metadata["retry_count"] == 3
        assert sleeper.sleeps == [pytest.approx(1.0), pytest.approx(2.0), pytest.approx(4.0)]


# ---------------------------------------------------------------------------\
# Transient exhaustion
# ---------------------------------------------------------------------------


class TestTransientExhaustion:
    async def test_exhaustion_raises_transient(self) -> None:
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("fail 1"),
            TransientChatProviderError("fail 2"),
            TransientChatProviderError("fail 3"),
            TransientChatProviderError("fail 4"),
        ])
        sleeper = _RecordingSleeper()
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=sleeper,
        )
        with pytest.raises(TransientChatProviderError):
            await wrapper.complete("test", context=_make_context())
        assert provider.call_count == 4
        assert sleeper.sleeps == [pytest.approx(1.0), pytest.approx(2.0), pytest.approx(4.0)]

    async def test_max_retries_zero_no_retry_on_transient(self) -> None:
        provider = _ScriptedProvider(script=[TransientChatProviderError("fail")])
        sleeper = _RecordingSleeper()
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=0),
            sleeper=sleeper,
        )
        with pytest.raises(TransientChatProviderError):
            await wrapper.complete("test", context=_make_context())
        assert provider.call_count == 1
        assert sleeper.sleeps == []


# ---------------------------------------------------------------------------\
# Permanent failure without retry
# ---------------------------------------------------------------------------


class TestPermanentFailure:
    async def test_permanent_failure_no_retry(self) -> None:
        provider = _ScriptedProvider(script=[PermanentChatProviderError("bad request")])
        sleeper = _RecordingSleeper()
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=sleeper,
        )
        with pytest.raises(PermanentChatProviderError):
            await wrapper.complete("test", context=_make_context())
        assert provider.call_count == 1
        assert sleeper.sleeps == []


# ---------------------------------------------------------------------------\
# Configuration failure without retry
# ---------------------------------------------------------------------------


class TestConfigurationFailure:
    async def test_config_error_no_retry(self) -> None:
        provider = _ScriptedProvider(script=[ChatProviderConfigurationError("missing key")])
        sleeper = _RecordingSleeper()
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=sleeper,
        )
        with pytest.raises(ChatProviderConfigurationError):
            await wrapper.complete("test", context=_make_context())
        assert provider.call_count == 1
        assert sleeper.sleeps == []


# ---------------------------------------------------------------------------\
# Cancellation
# ---------------------------------------------------------------------------


class TestCancellation:
    async def test_cancellation_during_provider_call(self) -> None:
        """CancelledError from provider call propagates immediately."""
        provider = _ScriptedProvider(script=[asyncio.CancelledError()])
        sleeper = _RecordingSleeper()
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=sleeper,
        )
        with pytest.raises(asyncio.CancelledError):
            await wrapper.complete("test", context=_make_context())
        assert provider.call_count == 1
        assert sleeper.sleeps == []

    async def test_cancellation_during_backoff_sleep(self) -> None:
        """CancelledError from sleeper propagates immediately, no further retries."""
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("timeout"),
            _make_chat_result(),  # Never reached
        ])
        sleeper = _RecordingSleeper()
        sleeper.set_fail_on_next(asyncio.CancelledError())
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=sleeper,
        )
        with pytest.raises(asyncio.CancelledError):
            await wrapper.complete("test", context=_make_context())
        assert provider.call_count == 1
        assert len(sleeper.sleeps) == 1  # One sleep attempted


# ---------------------------------------------------------------------------\
# Unknown exception without retry
# ---------------------------------------------------------------------------


class TestUnknownException:
    async def test_runtime_error_not_retried(self) -> None:
        provider = _ScriptedProvider(script=[RuntimeError("unexpected")])
        sleeper = _RecordingSleeper()
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=sleeper,
        )
        with pytest.raises(RuntimeError):
            await wrapper.complete("test", context=_make_context())
        assert provider.call_count == 1
        assert sleeper.sleeps == []


# ---------------------------------------------------------------------------\
# Context / schema / prompt passthrough
# ---------------------------------------------------------------------------


class TestPassthrough:
    async def test_context_passed_unchanged(self) -> None:
        ctx = _make_context()
        ctx["extra_key"] = "extra_value"
        provider = _ScriptedProvider(script=[_make_chat_result()])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=0),
            sleeper=_RecordingSleeper(),
        )
        await wrapper.complete("test", context=ctx)
        assert provider.calls[0]["context"] == ctx

    async def test_schema_passed_unchanged(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        provider = _ScriptedProvider(script=[_make_chat_result()])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=0),
            sleeper=_RecordingSleeper(),
        )
        await wrapper.complete("test", schema=schema)
        assert provider.calls[0]["schema"] == schema

    async def test_prompt_passed_unchanged(self) -> None:
        prompt = "Analyze supply risks for PLAN-2026-W31"
        provider = _ScriptedProvider(script=[_make_chat_result()])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=0),
            sleeper=_RecordingSleeper(),
        )
        await wrapper.complete(prompt)
        assert provider.calls[0]["prompt"] == prompt

    async def test_context_passed_through_on_retry(self) -> None:
        ctx = _make_context()
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("timeout"),
            _make_chat_result(),
        ])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        await wrapper.complete("test", context=ctx)
        assert provider.calls[0]["context"] == ctx
        assert provider.calls[1]["context"] == ctx


# ---------------------------------------------------------------------------\
# 1-based attempt numbering
# ---------------------------------------------------------------------------


class TestAttemptNumbering:
    async def test_attempt_history_uses_1_based_numbering(self) -> None:
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("fail 1"),
            TransientChatProviderError("fail 2"),
            _make_chat_result(),
        ])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        history = result.metadata["attempt_history"]
        assert len(history) == 2
        assert history[0]["attempt_number"] == 1
        assert history[0]["outcome"] == "retrying"
        assert history[1]["attempt_number"] == 2
        assert history[1]["outcome"] == "retrying"

    async def test_success_on_first_attempt_has_no_history(self) -> None:
        provider = _ScriptedProvider(script=[_make_chat_result()])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        assert result.metadata["attempt_history"] == []
        assert result.metadata["retry_count"] == 0


# ---------------------------------------------------------------------------\
# Delegate metadata preservation
# ---------------------------------------------------------------------------


class TestDelegateMetadataPreservation:
    async def test_delegate_metadata_preserved(self) -> None:
        delegate_metadata = {
            "latency_ms": 99.0,
            "provider": "openai",
            "response_id": "resp-abc123",
        }
        provider = _ScriptedProvider(script=[_make_chat_result(metadata=delegate_metadata)])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        assert result.metadata["latency_ms"] == 99.0
        assert result.metadata["provider"] == "openai"
        assert result.metadata["response_id"] == "resp-abc123"
        assert result.metadata["retry_count"] == 0

    async def test_delegate_content_preserved(self) -> None:
        content = '{"schema_version": "1.0", "risks": []}'
        provider = _ScriptedProvider(script=[_make_chat_result(content=content)])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        assert result.content == content

    async def test_delegate_model_preserved(self) -> None:
        provider = _ScriptedProvider(script=[_make_chat_result(model="gpt-4o-mini")])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        assert result.model == "gpt-4o-mini"

    async def test_delegate_usage_preserved(self) -> None:
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        provider = _ScriptedProvider(script=[_make_chat_result(usage=usage)])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        assert result.usage == usage


# ---------------------------------------------------------------------------\
# Metadata collision behavior
# ---------------------------------------------------------------------------


class TestMetadataCollision:
    async def test_wrapper_keys_override_delegate_keys(self) -> None:
        """If delegate supplies 'retry_count' or 'attempt_history',
        the wrapper's values take precedence."""
        delegate_metadata = {
            "retry_count": 999,
            "attempt_history": ["delegate_data"],
            "provider": "fake",
        }
        provider = _ScriptedProvider(script=[_make_chat_result(metadata=delegate_metadata)])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        assert result.metadata["retry_count"] == 0
        assert result.metadata["attempt_history"] == []
        # Delegate's other metadata is preserved.
        assert result.metadata["provider"] == "fake"

    async def test_wrapper_keys_override_after_retry(self) -> None:
        delegate_metadata = {
            "retry_count": 999,
            "provider": "fake",
        }
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("fail"),
            _make_chat_result(metadata=delegate_metadata),
        ])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        assert result.metadata["retry_count"] == 1
        assert result.metadata["provider"] == "fake"


# ---------------------------------------------------------------------------\
# Safe logging
# ---------------------------------------------------------------------------


class TestSafeLogging:
    async def test_no_raw_exception_message_in_attempt_history(self) -> None:
        """Attempt history must not contain raw exception messages."""
        secret_message = "Bearer sk-secret-key-12345 connection timeout"
        provider = _ScriptedProvider(script=[
            TransientChatProviderError(secret_message),
            _make_chat_result(),
        ])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        history = result.metadata["attempt_history"]
        for entry in history:
            assert "error_type" in entry
            assert entry["error_type"] == "TransientChatProviderError"
            # No raw message in any field.
            for value in entry.values():
                assert secret_message not in str(value)
            assert "sk-secret" not in str(entry)

    async def test_no_sensitive_context_values_logged(self) -> None:
        """Only correlation_id and run_id are read from context."""
        ctx = _make_context()
        ctx["api_key"] = "sk-secret-key"
        ctx["authorization"] = "Bearer token123"
        ctx["password"] = "SuperSecret123!"
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("fail"),
            _make_chat_result(),
        ])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=ctx)
        # Metadata should not contain sensitive context values.
        metadata_str = str(result.metadata)
        assert "sk-secret" not in metadata_str
        assert "Bearer token123" not in metadata_str
        assert "SuperSecret" not in metadata_str

    async def test_attempt_history_contains_only_safe_fields(self) -> None:
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("fail"),
            _make_chat_result(),
        ])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=_RecordingSleeper(),
        )
        result = await wrapper.complete("test", context=_make_context())
        history = result.metadata["attempt_history"]
        assert len(history) == 1
        entry = history[0]
        # Only safe fields.
        assert set(entry.keys()) == {
            "attempt_number",
            "outcome",
            "error_type",
            "backoff_delay_seconds",
        }


# ---------------------------------------------------------------------------\
# No real sleeping
# ---------------------------------------------------------------------------


class TestNoRealSleeping:
    async def test_fake_sleeper_records_no_real_wait(self) -> None:
        """The recording sleeper records delays without waiting."""
        sleeper = _RecordingSleeper()
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("fail"),
            TransientChatProviderError("fail"),
            _make_chat_result(),
        ])
        wrapper = RetryingChatProvider(
            delegate=provider,
            policy=_make_policy(max_retries=3),
            sleeper=sleeper,
        )
        await wrapper.complete("test", context=_make_context())
        # Two sleeps: 1.0 and 2.0 seconds — recorded, not waited.
        assert sleeper.sleeps == [pytest.approx(1.0), pytest.approx(2.0)]
