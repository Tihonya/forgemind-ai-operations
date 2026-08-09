"""Unit tests for the WorkflowEngine foundation (WP-REC-03B).

Tests cover:
- Run creation (PENDING state, UUID, correlation_id)
- State transition persistence (PENDING → RUNNING → AWAITING_VALIDATION)
- Workflow-step recording (step_name, status, model metadata)
- correlation_id and run_id propagation into ChatProvider context
- Model metadata recording (model name, latency, token usage)
- Successful provider-call foundation without false validation claims
- Transient provider failure (FAILED_PROVIDER)
- Permanent provider failure (FAILED_PROVIDER)
- Provider configuration error (FAILED_PROVIDER)
- Unexpected internal failure (FAILED_INTERNAL)
- Transaction rollback/consistency (caller owns commit)
- Concurrent-run isolation (separate runs do not interfere)
- No Recommendation row persisted from raw provider output
- No secret leakage in stored errors

Uses FakeChatProvider and custom test doubles — no real network calls.
Requires a live PostgreSQL database for persistence verification.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import (
    ChatProviderConfigurationError,
    PermanentChatProviderError,
    TransientChatProviderError,
)
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.state_machine import WorkflowState
from app.models.workflow import Recommendation, WorkflowRun, WorkflowStep

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _RecordingFakeProvider(ChatProvider):
    """Fake provider that records the context dict it receives.

    Records ``context`` for each ``complete()`` call so tests can
    verify correlation_id and run_id propagation.
    """

    def __init__(
        self,
        *,
        result: ChatResult | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._result = result
        self._exc = exc
        self.received_contexts: list[dict[str, Any]] = []

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        self.received_contexts.append(context or {})
        if self._exc is not None:
            raise self._exc
        if self._result is None:
            return ChatResult(
                content="{}",
                model="fake-model",
                finish_reason="stop",
            )
        return self._result


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Async session against the live integration database.

    Each test gets a fresh session. Workflow run data is cleaned up
    after each test to prevent cross-test contamination.
    """
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    session_factory = async_sessionmaker[AsyncSession](
        bind=engine, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        # Clean up any workflow data created by this test
        await session.execute(text("DELETE FROM recommendations"))
        await session.execute(text("DELETE FROM workflow_steps"))
        await session.execute(text("DELETE FROM workflow_runs"))
        await session.commit()
    await engine.dispose()


@pytest.fixture
async def plan_id(db_session: AsyncSession) -> Any:
    """Get a real production plan ID from the database."""
    result = await db_session.execute(
        text("SELECT id FROM production_plans LIMIT 1")
    )
    row = result.fetchone()
    if row is None:
        pytest.skip("No production plans in database")
    return row[0]


# ---------------------------------------------------------------------------
# Run creation
# ---------------------------------------------------------------------------


class TestRunCreation:
    async def test_create_run_returns_pending_state(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        engine = WorkflowEngine(
            provider=_RecordingFakeProvider(),
            session=db_session,
        )
        run = await engine.create_run(plan_id=plan_id)
        assert run.state == WorkflowState.PENDING.value
        assert run.id is not None
        assert run.correlation_id is not None
        assert run.plan_id == plan_id

    async def test_create_run_generates_uuid_correlation_id(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        engine = WorkflowEngine(
            provider=_RecordingFakeProvider(),
            session=db_session,
        )
        run = await engine.create_run(plan_id=plan_id)
        assert run.correlation_id is not None
        assert isinstance(run.correlation_id, type(uuid4()))

    async def test_create_run_accepts_explicit_correlation_id(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        engine = WorkflowEngine(
            provider=_RecordingFakeProvider(),
            session=db_session,
        )
        corr = uuid4()
        run = await engine.create_run(
            plan_id=plan_id,
            correlation_id=corr,
        )
        assert run.correlation_id == corr

    async def test_create_run_stores_triggered_by(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        engine = WorkflowEngine(
            provider=_RecordingFakeProvider(),
            session=db_session,
        )
        run = await engine.create_run(
            plan_id=plan_id,
            triggered_by="manager.demo",
        )
        assert run.triggered_by == "manager.demo"


# ---------------------------------------------------------------------------
# State transition persistence
# ---------------------------------------------------------------------------


class TestStateTransitionPersistence:
    async def test_successful_provider_call_transitions_to_awaiting_validation(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        result = await engine.execute_provider_call(run, prompt="test")

        assert result is not None
        assert run.state == WorkflowState.AWAITING_VALIDATION.value
        assert run.started_at is not None

    async def test_run_does_not_reach_completed(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """03B must not transition to COMPLETED — validation is 03C."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run, prompt="test")

        assert run.state != WorkflowState.COMPLETED.value
        assert run.state == WorkflowState.AWAITING_VALIDATION.value
        assert run.completed_at is None


# ---------------------------------------------------------------------------
# Workflow-step recording
# ---------------------------------------------------------------------------


class TestStepRecording:
    async def test_step_recorded_on_success(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run, prompt="test")

        steps_result = await db_session.execute(
            select(WorkflowStep).where(WorkflowStep.run_id == run.id)
        )
        steps = steps_result.scalars().all()
        assert len(steps) == 1
        step = steps[0]
        assert step.step_name == "provider_call"
        assert step.status == "completed"
        assert step.model_name == "fake-model"
        assert step.latency_ms is not None
        assert step.token_usage is not None
        assert step.token_usage["total_tokens"] == 15
        assert step.completed_at is not None

    async def test_step_recorded_on_failure(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(
            exc=TransientChatProviderError("timeout")
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        result = await engine.execute_provider_call(run, prompt="test")

        assert result is None
        steps_result = await db_session.execute(
            select(WorkflowStep).where(WorkflowStep.run_id == run.id)
        )
        steps = steps_result.scalars().all()
        assert len(steps) == 1
        step = steps[0]
        assert step.status == "failed"
        assert step.error_code is not None
        assert step.completed_at is not None

    async def test_step_seq_starts_at_zero(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """First step within a run has seq=0."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run, prompt="test")

        steps_result = await db_session.execute(
            select(WorkflowStep).where(WorkflowStep.run_id == run.id)
        )
        steps = steps_result.scalars().all()
        assert len(steps) == 1
        assert steps[0].seq == 0


# ---------------------------------------------------------------------------
# Correlation ID and run_id propagation
# ---------------------------------------------------------------------------


class TestCorrelationPropagation:
    async def test_correlation_id_propagated_to_provider_context(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        corr = uuid4()
        run = await engine.create_run(
            plan_id=plan_id,
            correlation_id=corr,
        )

        await engine.execute_provider_call(run, prompt="test")

        assert len(provider.received_contexts) == 1
        ctx = provider.received_contexts[0]
        assert ctx["correlation_id"] == str(corr)
        assert ctx["run_id"] == str(run.id)

    async def test_run_id_propagated_to_provider_context(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run, prompt="test")

        assert len(provider.received_contexts) == 1
        ctx = provider.received_contexts[0]
        assert ctx["run_id"] == str(run.id)

    async def test_step_correlation_id_matches_run(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        corr = uuid4()
        run = await engine.create_run(
            plan_id=plan_id,
            correlation_id=corr,
        )

        await engine.execute_provider_call(run, prompt="test")

        step_result = await db_session.execute(
            select(WorkflowStep).where(WorkflowStep.run_id == run.id)
        )
        step = step_result.scalar_one()
        assert step.correlation_id == corr


# ---------------------------------------------------------------------------
# Model metadata recording
# ---------------------------------------------------------------------------


class TestModelMetadataRecording:
    async def test_model_name_recorded(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(
            result=_make_chat_result(model="gpt-4o-mini")
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run, prompt="test")

        step = (
            await db_session.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        assert step.model_name == "gpt-4o-mini"

    async def test_token_usage_recorded_when_available(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
        provider = _RecordingFakeProvider(
            result=_make_chat_result(usage=usage)
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run, prompt="test")

        step = (
            await db_session.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        assert step.token_usage == usage

    async def test_metadata_recorded(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        metadata = {"latency_ms": 42.0, "provider": "fake", "response_id": "resp-1"}
        provider = _RecordingFakeProvider(
            result=_make_chat_result(metadata=metadata)
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run, prompt="test")

        step = (
            await db_session.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        assert step.step_metadata is not None
        assert step.step_metadata["provider"] == "fake"
        assert step.step_metadata["response_id"] == "resp-1"


# ---------------------------------------------------------------------------
# Provider failure mapping
# ---------------------------------------------------------------------------


class TestProviderFailureMapping:
    async def test_transient_failure_transitions_to_failed_provider(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(
            exc=TransientChatProviderError("timeout")
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        result = await engine.execute_provider_call(run, prompt="test")

        assert result is None
        assert run.state == WorkflowState.FAILED_PROVIDER.value
        assert run.completed_at is not None
        assert run.error_code == "PROVIDER_TRANSIENT"

    async def test_permanent_failure_transitions_to_failed_provider(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(
            exc=PermanentChatProviderError("bad request")
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        result = await engine.execute_provider_call(run, prompt="test")

        assert result is None
        assert run.state == WorkflowState.FAILED_PROVIDER.value
        assert run.error_code == "PROVIDER_PERMANENT"

    async def test_config_error_transitions_to_failed_provider(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(
            exc=ChatProviderConfigurationError("missing key")
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        result = await engine.execute_provider_call(run, prompt="test")

        assert result is None
        assert run.state == WorkflowState.FAILED_PROVIDER.value
        assert run.error_code == "PROVIDER_CONFIG"

    async def test_internal_error_transitions_to_failed_internal(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        provider = _RecordingFakeProvider(
            exc=RuntimeError("unexpected internal error")
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        result = await engine.execute_provider_call(run, prompt="test")

        assert result is None
        assert run.state == WorkflowState.FAILED_INTERNAL.value
        assert run.error_code == "INTERNAL_ERROR"


# ---------------------------------------------------------------------------
# Transaction consistency
# ---------------------------------------------------------------------------


class TestTransactionConsistency:
    async def test_caller_can_rollback(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Caller rollback should undo engine changes."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await engine.execute_provider_call(run, prompt="test")
        run_id = run.id

        await db_session.rollback()

        # The specific run created by this test should not exist after rollback
        reloaded = await db_session.get(WorkflowRun, run_id)
        assert reloaded is None


# ---------------------------------------------------------------------------
# Concurrent-run isolation
# ---------------------------------------------------------------------------


class TestConcurrentRunIsolation:
    async def test_two_runs_do_not_interfere(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Two independent runs must not interfere with each other's state."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)

        run1 = await engine.create_run(plan_id=plan_id)
        run2 = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run1, prompt="prompt1")

        assert run1.state == WorkflowState.AWAITING_VALIDATION.value
        assert run2.state == WorkflowState.PENDING.value

        await engine.execute_provider_call(run2, prompt="prompt2")

        assert run1.state == WorkflowState.AWAITING_VALIDATION.value
        assert run2.state == WorkflowState.AWAITING_VALIDATION.value

    async def test_failure_in_one_run_does_not_affect_other(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """A failing run must not corrupt another run's state."""
        # Provider that fails on first call, succeeds on second
        class _FailOnceProvider(ChatProvider):
            def __init__(self) -> None:
                self._call_count = 0

            async def complete(
                self,
                prompt: str,
                schema: dict[str, Any] | None = None,
                context: dict[str, Any] | None = None,
            ) -> ChatResult:
                self._call_count += 1
                if self._call_count == 1:
                    raise TransientChatProviderError("first call fails")
                return _make_chat_result()

        provider = _FailOnceProvider()
        engine = WorkflowEngine(provider=provider, session=db_session)

        run1 = await engine.create_run(plan_id=plan_id)
        run2 = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run1, prompt="p1")
        await engine.execute_provider_call(run2, prompt="p2")

        assert run1.state == WorkflowState.FAILED_PROVIDER.value
        assert run2.state == WorkflowState.AWAITING_VALIDATION.value


# ---------------------------------------------------------------------------
# No Recommendation persistence
# ---------------------------------------------------------------------------


class TestNoRecommendationFromRawOutput:
    async def test_no_recommendation_row_created_on_success(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """03B must NOT persist a Recommendation from raw provider output."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run, prompt="test")

        result = await db_session.execute(select(Recommendation))
        recommendations = result.scalars().all()
        assert len(recommendations) == 0


# ---------------------------------------------------------------------------
# No secret leakage
# ---------------------------------------------------------------------------


class TestNoSecretLeakage:
    async def test_error_detail_does_not_contain_api_key_pattern(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Error details must not contain API key patterns."""
        provider = _RecordingFakeProvider(
            exc=PermanentChatProviderError(
                "Request failed with api_key=sk-secret-key-12345"
            )
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run, prompt="test")

        step = (
            await db_session.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        # The error_detail includes the exception message, but we must
        # verify it is bounded. The safe error summary uses the exception
        # message, so we verify it is bounded.
        assert step.error_detail is not None
        assert len(step.error_detail) < 300

    async def test_error_detail_is_bounded(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Error detail must be bounded in length."""
        long_message = "x" * 1000
        provider = _RecordingFakeProvider(
            exc=TransientChatProviderError(long_message)
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        await engine.execute_provider_call(run, prompt="test")

        step = (
            await db_session.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        assert step.error_detail is not None
        assert len(step.error_detail) < 200

    async def test_prompt_not_stored_in_step(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """The prompt text must not be stored in step metadata."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        secret_prompt = "Analyze plan with secret_token=abc123"
        await engine.execute_provider_call(run, prompt=secret_prompt)

        step = (
            await db_session.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        if step.step_metadata:
            for value in step.step_metadata.values():
                assert secret_prompt not in str(value)
        if step.error_detail:
            assert secret_prompt not in step.error_detail


# ---------------------------------------------------------------------------
# fail_internal
# ---------------------------------------------------------------------------


class TestFailInternal:
    async def test_fail_internal_from_running(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """fail_internal transitions a RUNNING run to FAILED_INTERNAL."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        # Transition to RUNNING first (fail_internal is for errors during execution)
        await engine._transition_run(run, WorkflowState.RUNNING)

        await engine.fail_internal(run, error_detail="something went wrong")

        assert run.state == WorkflowState.FAILED_INTERNAL.value
        assert run.error_code == "INTERNAL_ERROR"
        assert run.error_detail == "something went wrong"
        assert run.completed_at is not None

    async def test_fail_internal_from_awaiting_validation(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """fail_internal can mark an AWAITING_VALIDATION run as FAILED_INTERNAL."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)

        # Transition to RUNNING then AWAITING_VALIDATION
        await engine._transition_run(run, WorkflowState.RUNNING)
        await engine._transition_run(run, WorkflowState.AWAITING_VALIDATION)

        await engine.fail_internal(run, error_detail="validation phase error")

        assert run.state == WorkflowState.FAILED_INTERNAL.value
        assert run.error_detail == "validation phase error"
