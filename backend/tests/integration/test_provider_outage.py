"""Integration tests for provider outage handling (WP-REC-03D).

Tests the real RetryingChatProvider wrapper + existing WorkflowEngine +
real PostgreSQL contract.  This is an integration test of the
wrapper/engine/database contract — it does NOT prove an active production
worker path (that wiring belongs to WP-REC-03F).

Coverage:

1. Transient failures → exhaustion → FAILED_PROVIDER persisted;
2. Transient failure → later success → existing success transition
   (AWAITING_VALIDATION);
3. Permanent failure → exactly one provider call;
4. Persisted error fields contain safe type-based values;
5. Successful retry metadata reaches WorkflowStep.step_metadata;
6. Conditional transition behavior remains intact.

All tests use a fake sleeper — no real backoff waiting.
Requires a live PostgreSQL database for persistence verification.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import (
    PermanentChatProviderError,
    TransientChatProviderError,
)
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.outage_handler import RetryingChatProvider
from app.ai.workflow.retry_policy import RetryPolicy
from app.ai.workflow.state_machine import WorkflowState
from app.models.workflow import WorkflowStep

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)


# ---------------------------------------------------------------------------\
# Test doubles
# ---------------------------------------------------------------------------


class _ScriptedProvider(ChatProvider):
    """Fake provider that follows a scripted sequence."""

    def __init__(
        self,
        *,
        script: list[ChatResult | BaseException],
    ) -> None:
        self._script = list(script)
        self.call_count: int = 0

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        self.call_count += 1
        item = self._script.pop(0) if self._script else _make_chat_result()
        if isinstance(item, BaseException):
            raise item
        return item


class _NoOpSleeper:
    """Sleeper that records delays without waiting."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.sleeps.append(delay)


def _make_chat_result(**kwargs: Any) -> ChatResult:
    defaults: dict[str, Any] = {
        "content": '{"test": true}',
        "model": "fake-model",
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "metadata": {"latency_ms": 42.0, "provider": "fake"},
    }
    defaults.update(kwargs)
    return ChatResult(**defaults)


def _make_wrapper(
    provider: ChatProvider,
    *,
    max_retries: int = 3,
) -> RetryingChatProvider:
    return RetryingChatProvider(
        delegate=provider,
        policy=RetryPolicy(max_retries=max_retries),
        sleeper=_NoOpSleeper(),
    )


# ---------------------------------------------------------------------------\
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    session_factory = async_sessionmaker[AsyncSession](
        bind=engine, expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.execute(text("DELETE FROM recommendations"))
        await session.execute(text("DELETE FROM workflow_steps"))
        await session.execute(text("DELETE FROM workflow_runs"))
        await session.commit()
    await engine.dispose()


@pytest.fixture
async def plan_id(db_session: AsyncSession) -> Any:
    result = await db_session.execute(
        text("SELECT id FROM production_plans LIMIT 1")
    )
    row = result.fetchone()
    if row is None:
        pytest.skip("No production plans in database")
    return row[0]


# ---------------------------------------------------------------------------\
# 1. Transient failures → exhaustion → FAILED_PROVIDER
# ---------------------------------------------------------------------------


class TestTransientExhaustionIntegration:
    async def test_transient_exhaustion_reaches_failed_provider(
        self, db_session: AsyncSession, plan_id: Any,
    ) -> None:
        """Transient failures exhausted → FAILED_PROVIDER persisted."""
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("timeout 1"),
            TransientChatProviderError("timeout 2"),
            TransientChatProviderError("timeout 3"),
            TransientChatProviderError("timeout 4"),
        ])
        wrapper = _make_wrapper(provider, max_retries=3)
        engine = WorkflowEngine(provider=wrapper, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        result = await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        assert result is None
        assert run.state == WorkflowState.FAILED_PROVIDER.value
        assert run.error_code == "PROVIDER_TRANSIENT"
        assert run.error_detail == "TransientChatProviderError"
        assert run.completed_at is not None
        assert provider.call_count == 4  # 1 initial + 3 retries


# ---------------------------------------------------------------------------\
# 2. Transient failure → later success → AWAITING_VALIDATION
# ---------------------------------------------------------------------------


class TestTransientThenSuccessIntegration:
    async def test_transient_then_success_reaches_awaiting_validation(
        self, db_session: AsyncSession, plan_id: Any,
    ) -> None:
        """Transient failure → retry → success → AWAITING_VALIDATION."""
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("timeout"),
            _make_chat_result(),
        ])
        wrapper = _make_wrapper(provider, max_retries=3)
        engine = WorkflowEngine(provider=wrapper, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        result = await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        assert result is not None
        assert run.state == WorkflowState.AWAITING_VALIDATION.value
        assert run.completed_at is None
        assert provider.call_count == 2


# ---------------------------------------------------------------------------\
# 3. Permanent failure → exactly one call
# ---------------------------------------------------------------------------


class TestPermanentFailureIntegration:
    async def test_permanent_failure_exactly_one_call(
        self, db_session: AsyncSession, plan_id: Any,
    ) -> None:
        """Permanent failure → no retry → FAILED_PROVIDER immediately."""
        provider = _ScriptedProvider(script=[
            PermanentChatProviderError("bad request"),
        ])
        wrapper = _make_wrapper(provider, max_retries=3)
        engine = WorkflowEngine(provider=wrapper, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        result = await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        assert result is None
        assert run.state == WorkflowState.FAILED_PROVIDER.value
        assert run.error_code == "PROVIDER_PERMANENT"
        assert run.error_detail == "PermanentChatProviderError"
        assert provider.call_count == 1


# ---------------------------------------------------------------------------\
# 4. Persisted error fields contain safe type-based values
# ---------------------------------------------------------------------------


class TestSafeErrorPersistenceIntegration:
    async def test_error_detail_contains_type_name_not_message(
        self, db_session: AsyncSession, plan_id: Any,
    ) -> None:
        """error_detail must be the exception type name, not the message."""
        secret_message = "Bearer sk-secret-key-12345 rate limited"
        provider = _ScriptedProvider(script=[
            TransientChatProviderError(secret_message),
            TransientChatProviderError(secret_message),
            TransientChatProviderError(secret_message),
            TransientChatProviderError(secret_message),
        ])
        wrapper = _make_wrapper(provider, max_retries=3)
        engine = WorkflowEngine(provider=wrapper, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        assert run.error_detail == "TransientChatProviderError"
        assert secret_message not in (run.error_detail or "")
        assert "sk-secret" not in (run.error_detail or "")
        assert "Bearer" not in (run.error_detail or "")

    async def test_step_error_code_is_safe(
        self, db_session: AsyncSession, plan_id: Any,
    ) -> None:
        provider = _ScriptedProvider(script=[
            PermanentChatProviderError("bad"),
        ])
        wrapper = _make_wrapper(provider, max_retries=3)
        engine = WorkflowEngine(provider=wrapper, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        steps_result = await db_session.execute(
            select(WorkflowStep).where(WorkflowStep.run_id == run.id)
        )
        step = steps_result.scalar_one()
        assert step.error_code == "PROVIDER_PERMANENT"
        assert step.error_detail == "PermanentChatProviderError"


# ---------------------------------------------------------------------------\
# 5. Successful retry metadata reaches WorkflowStep.step_metadata
# ---------------------------------------------------------------------------


class TestRetryMetadataPersistenceIntegration:
    async def test_retry_count_in_step_metadata(
        self, db_session: AsyncSession, plan_id: Any,
    ) -> None:
        """On success after retry, retry_count is in step_metadata."""
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("timeout 1"),
            TransientChatProviderError("timeout 2"),
            _make_chat_result(),
        ])
        wrapper = _make_wrapper(provider, max_retries=3)
        engine = WorkflowEngine(provider=wrapper, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        steps_result = await db_session.execute(
            select(WorkflowStep).where(WorkflowStep.run_id == run.id)
        )
        step = steps_result.scalar_one()
        assert step.status == "completed"
        assert step.step_metadata is not None
        assert step.step_metadata["retry_count"] == 2
        assert "attempt_history" in step.step_metadata
        history = step.step_metadata["attempt_history"]
        assert len(history) == 2
        assert history[0]["attempt_number"] == 1
        assert history[0]["outcome"] == "retrying"

    async def test_zero_retry_count_on_immediate_success(
        self, db_session: AsyncSession, plan_id: Any,
    ) -> None:
        provider = _ScriptedProvider(script=[_make_chat_result()])
        wrapper = _make_wrapper(provider, max_retries=3)
        engine = WorkflowEngine(provider=wrapper, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        steps_result = await db_session.execute(
            select(WorkflowStep).where(WorkflowStep.run_id == run.id)
        )
        step = steps_result.scalar_one()
        assert step.step_metadata is not None
        assert step.step_metadata["retry_count"] == 0


# ---------------------------------------------------------------------------\
# 6. Conditional transition behavior remains intact
# ---------------------------------------------------------------------------


class TestConditionalTransitionIntactIntegration:
    async def test_run_reaches_correct_terminal_state(
        self, db_session: AsyncSession, plan_id: Any,
    ) -> None:
        """The engine's conditional UPDATE still serializes transitions.

        This test verifies that the wrapper does not interfere with the
        engine's state-machine guarantees.  A single run transitions
        correctly to FAILED_PROVIDER after exhaustion.
        """
        provider = _ScriptedProvider(script=[
            TransientChatProviderError("timeout"),
            TransientChatProviderError("timeout"),
        ])
        wrapper = _make_wrapper(provider, max_retries=1)
        engine = WorkflowEngine(provider=wrapper, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        # max_retries=1: 2 total calls, both fail → FAILED_PROVIDER.
        assert run.state == WorkflowState.FAILED_PROVIDER.value
        assert run.error_code == "PROVIDER_TRANSIENT"
        assert provider.call_count == 2

    async def test_no_double_wrap_in_factory(
        self, db_session: AsyncSession, plan_id: Any,
    ) -> None:
        """Factory-wrapped provider does not nest wrappers.

        This is a smoke test that the factory produces a single
        RetryingChatProvider, not a nested chain.
        """
        from app.ai.provider.factory import create_chat_provider
        from app.config import Settings

        # Create a fake provider via the real factory.
        test_settings = Settings(
            environment="development",
            secret_key="test_secret_key_for_ci_only_32_chars_minimum",
            embedding_provider="fake",
            llm_max_retries=2,
        )
        provider = create_chat_provider(config=test_settings)

        # Verify it's a RetryingChatProvider, not nested.
        assert isinstance(provider, RetryingChatProvider)
        # The delegate should be a FakeChatProvider, not another wrapper.
        from app.ai.provider.fake_chat_provider import FakeChatProvider
        assert isinstance(provider._delegate, FakeChatProvider)
        assert not isinstance(provider._delegate, RetryingChatProvider)
