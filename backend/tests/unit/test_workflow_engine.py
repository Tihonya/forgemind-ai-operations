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
- Conditional UPDATE concurrency safety (DEC-013 §5)

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
from app.ai.workflow.state_machine import TransitionConflictError, WorkflowState
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
        self.call_count: int = 0

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        self.received_contexts.append(context or {})
        self.call_count += 1
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
async def db_engine() -> AsyncIterator[Any]:
    """Shared async engine for tests that need independent sessions."""
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    yield engine
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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

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
        """Caller rollback should undo engine transition changes.

        The run is committed (PENDING), then execute_provider_call
        transitions it to AWAITING_VALIDATION. Rolling back should
        revert the state to PENDING — the caller owns the transaction
        boundary.
        """
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()
        run_id = run.id

        await engine.execute_provider_call(run, prompt="test")
        # At this point the run is at AWAITING_VALIDATION (uncommitted)

        await db_session.rollback()

        # After rollback, the run should still exist (it was committed)
        # but its state should be reverted to PENDING
        reloaded = await db_session.get(WorkflowRun, run_id)
        assert reloaded is not None
        assert reloaded.state == WorkflowState.PENDING.value


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
        await db_session.commit()

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
        await db_session.commit()

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
        await db_session.commit()

        await engine.execute_provider_call(run, prompt="test")

        result = await db_session.execute(select(Recommendation))
        recommendations = result.scalars().all()
        assert len(recommendations) == 0


# ---------------------------------------------------------------------------
# No secret leakage — error detail safety
# ---------------------------------------------------------------------------


class TestNoSecretLeakage:
    """Verify that error_detail never contains secrets or credentials."""

    async def test_error_detail_does_not_contain_api_key(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Error details must not contain API keys."""
        secret_key = "sk-proj-abc123XYZdef456GHIjkl"
        provider = _RecordingFakeProvider(
            exc=PermanentChatProviderError(
                f"Request failed with api_key={secret_key}"
            )
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        await engine.execute_provider_call(run, prompt="test")

        step = (
            await db_session.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        assert step.error_detail is not None
        # The safe summary is the exception TYPE NAME only — no message.
        assert secret_key not in step.error_detail
        assert "api_key" not in step.error_detail.lower()
        # Verify it's just the type name
        assert step.error_detail == "PermanentChatProviderError"

    async def test_error_detail_does_not_contain_bearer_token(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Error details must not contain bearer tokens."""
        bearer = "Bearer dGhpcyBpcyBhIHNlY3JldCB0b2tlbg=="
        provider = _RecordingFakeProvider(
            exc=TransientChatProviderError(
                f"Auth failed: {bearer} rejected"
            )
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        await engine.execute_provider_call(run, prompt="test")

        step = (
            await db_session.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        assert step.error_detail is not None
        assert bearer not in step.error_detail
        assert "Bearer" not in step.error_detail
        assert step.error_detail == "TransientChatProviderError"

    async def test_error_detail_does_not_contain_password(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Error details must not contain passwords or credentials."""
        password = "SuperSecret123!"
        provider = _RecordingFakeProvider(
            exc=ChatProviderConfigurationError(
                f"Config error: password={password} is invalid"
            )
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        await engine.execute_provider_call(run, prompt="test")

        step = (
            await db_session.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        assert step.error_detail is not None
        assert password not in step.error_detail
        assert "password" not in step.error_detail.lower()
        assert step.error_detail == "ChatProviderConfigurationError"

    async def test_error_detail_is_bounded(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Error detail must be bounded in length (type name only)."""
        long_message = "x" * 1000
        provider = _RecordingFakeProvider(
            exc=TransientChatProviderError(long_message)
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        await engine.execute_provider_call(run, prompt="test")

        step = (
            await db_session.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run.id)
            )
        ).scalar_one()
        assert step.error_detail is not None
        assert len(step.error_detail) < 200
        # The long message must not appear in the detail
        assert long_message not in step.error_detail
        assert step.error_detail == "TransientChatProviderError"

    async def test_error_detail_on_run_also_safe(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """WorkflowRun.error_detail must also not contain secrets."""
        secret = "sk-test-key-1234567890abcdef"
        provider = _RecordingFakeProvider(
            exc=PermanentChatProviderError(f"api_key={secret} invalid")
        )
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        await engine.execute_provider_call(run, prompt="test")

        assert run.error_detail is not None
        assert secret not in run.error_detail
        assert "api_key" not in run.error_detail.lower()

    async def test_prompt_not_stored_in_step(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """The prompt text must not be stored in step metadata."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

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
        await db_session.commit()

        # Transition to RUNNING first (fail_internal is for errors during execution)
        await engine._transition_run(run, WorkflowState.RUNNING)
        await db_session.commit()

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
        await db_session.commit()

        # Transition to RUNNING then AWAITING_VALIDATION
        await engine._transition_run(run, WorkflowState.RUNNING)
        await db_session.commit()
        await engine._transition_run(run, WorkflowState.AWAITING_VALIDATION)
        await db_session.commit()

        await engine.fail_internal(run, error_detail="validation phase error")

        assert run.state == WorkflowState.FAILED_INTERNAL.value
        assert run.error_detail == "validation phase error"

    async def test_fail_internal_redacts_secret_in_detail(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """fail_internal must redact secrets from caller-provided detail."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        await engine._transition_run(run, WorkflowState.RUNNING)
        await db_session.commit()

        secret_detail = "Internal error: api_key=sk-secret-12345 was exposed"
        await engine.fail_internal(run, error_detail=secret_detail)

        assert run.state == WorkflowState.FAILED_INTERNAL.value
        assert run.error_detail is not None
        assert "«redacted:sk-…»" not in run.error_detail
        assert "api_key" not in (run.error_detail or "").lower()
        assert run.error_detail == "UNSAFE_ERROR_DETAIL_REDACTED"


# ---------------------------------------------------------------------------
# Conditional UPDATE concurrency safety (DEC-013 §5)
# ---------------------------------------------------------------------------


class TestConditionalTransitionConcurrency:
    """Real database tests proving concurrent transitions are serialized.

    These tests use independent sessions to simulate concurrent workers
    attempting to transition the same run from the same expected state.
    Only one can win; the other gets TransitionConflictError.
    """

    async def test_two_contenders_cannot_both_transition(
        self, db_engine: Any, plan_id: Any
    ) -> None:
        """Two contenders cannot both transition the same run from PENDING."""
        # Create the run in session A, commit it
        factory = async_sessionmaker[AsyncSession](
            bind=db_engine, expire_on_commit=False
        )
        async with factory() as session_a:
            engine_a = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_a,
            )
            run = await engine_a.create_run(plan_id=plan_id)
            await session_a.commit()
            run_id = run.id

        # Now two independent sessions both try PENDING → RUNNING
        async with factory() as session_winner, factory() as session_loser:
            # Reload the run in each session
            run_winner = await session_winner.get(WorkflowRun, run_id)
            run_loser = await session_loser.get(WorkflowRun, run_id)
            assert run_winner is not None
            assert run_loser is not None
            assert run_winner.state == WorkflowState.PENDING.value
            assert run_loser.state == WorkflowState.PENDING.value

            engine_winner = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_winner,
            )
            engine_loser = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_loser,
            )

            # Winner transitions first
            await engine_winner._transition_run(
                run_winner, WorkflowState.RUNNING
            )
            await session_winner.commit()

            # Loser must get TransitionConflictError
            with pytest.raises(TransitionConflictError):
                await engine_loser._transition_run(
                    run_loser, WorkflowState.RUNNING
                )

            # Verify the loser's ORM instance was refreshed
            assert run_loser.state == WorkflowState.RUNNING.value

    async def test_exactly_one_transition_succeeds(
        self, db_engine: Any, plan_id: Any
    ) -> None:
        """Exactly one of two concurrent transitions succeeds."""
        factory = async_sessionmaker[AsyncSession](
            bind=db_engine, expire_on_commit=False
        )
        async with factory() as session_a:
            engine_a = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_a,
            )
            run = await engine_a.create_run(plan_id=plan_id)
            await session_a.commit()
            run_id = run.id

        successes = 0
        conflicts = 0

        async with factory() as session_1, factory() as session_2:
            run_1 = await session_1.get(WorkflowRun, run_id)
            run_2 = await session_2.get(WorkflowRun, run_id)
            assert run_1 is not None
            assert run_2 is not None

            engine_1 = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_1,
            )
            engine_2 = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_2,
            )

            # First transition succeeds
            await engine_1._transition_run(run_1, WorkflowState.RUNNING)
            await session_1.commit()
            successes += 1

            # Second transition must fail
            try:
                await engine_2._transition_run(run_2, WorkflowState.RUNNING)
                await session_2.commit()
                successes += 1
            except TransitionConflictError:
                conflicts += 1

        assert successes == 1
        assert conflicts == 1

    async def test_loser_does_not_overwrite_winner(
        self, db_engine: Any, plan_id: Any
    ) -> None:
        """The losing transition must not overwrite the winner's state."""
        factory = async_sessionmaker[AsyncSession](
            bind=db_engine, expire_on_commit=False
        )
        async with factory() as session_a:
            engine_a = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_a,
            )
            run = await engine_a.create_run(plan_id=plan_id)
            await session_a.commit()
            run_id = run.id

        async with factory() as session_winner, factory() as session_loser:
            run_winner = await session_winner.get(WorkflowRun, run_id)
            run_loser = await session_loser.get(WorkflowRun, run_id)
            assert run_winner is not None
            assert run_loser is not None

            engine_winner = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_winner,
            )
            engine_loser = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_loser,
            )

            # Winner: PENDING → RUNNING
            await engine_winner._transition_run(
                run_winner, WorkflowState.RUNNING
            )
            await session_winner.commit()

            # Loser: PENDING → RUNNING (must fail)
            with pytest.raises(TransitionConflictError):
                await engine_loser._transition_run(
                    run_loser, WorkflowState.RUNNING
                )

        # Verify in a fresh session that the DB state is RUNNING (winner's)
        async with factory() as verify_session:
            db_run = await verify_session.get(WorkflowRun, run_id)
            assert db_run is not None
            assert db_run.state == WorkflowState.RUNNING.value
            assert db_run.started_at is not None

    async def test_losing_execute_does_not_invoke_provider(
        self, db_engine: Any, plan_id: Any
    ) -> None:
        """A losing execute_provider_call must NOT invoke the provider.

        The loser may fail either via TransitionConflictError (if the
        ORM still sees the old state) or via StateMachineError (if the
        ORM sees the winner's new state and the transition is invalid).
        In both cases the provider must NOT be called.
        """
        from app.ai.workflow.state_machine import StateMachineError

        factory = async_sessionmaker[AsyncSession](
            bind=db_engine, expire_on_commit=False
        )

        # Create run
        async with factory() as session_a:
            engine_a = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_a,
            )
            run = await engine_a.create_run(plan_id=plan_id)
            await session_a.commit()
            run_id = run.id

        # Winner transitions PENDING → RUNNING first
        provider_winner = _RecordingFakeProvider(result=_make_chat_result())
        async with factory() as session_winner:
            run_winner = await session_winner.get(WorkflowRun, run_id)
            assert run_winner is not None
            engine_winner = WorkflowEngine(
                provider=provider_winner,
                session=session_winner,
            )
            await engine_winner._transition_run(
                run_winner, WorkflowState.RUNNING
            )
            await session_winner.commit()

        # Loser tries execute_provider_call — must raise and NOT call provider
        provider_loser = _RecordingFakeProvider(result=_make_chat_result())
        async with factory() as session_loser:
            run_loser = await session_loser.get(WorkflowRun, run_id)
            assert run_loser is not None
            engine_loser = WorkflowEngine(
                provider=provider_loser,
                session=session_loser,
            )

            # The loser should get either TransitionConflictError (ORM
            # still sees PENDING, conditional UPDATE returns 0 rows) or
            # StateMachineError (ORM sees RUNNING, self-transition
            # rejected). Both are valid — the key assertion is that the
            # provider is NOT called.
            with pytest.raises((TransitionConflictError, StateMachineError)):
                await engine_loser.execute_provider_call(
                    run_loser, prompt="test"
                )

            # Provider was NOT called
            assert provider_loser.call_count == 0
            assert len(provider_loser.received_contexts) == 0

    async def test_different_runs_remain_independent(
        self, db_engine: Any, plan_id: Any
    ) -> None:
        """Transitions on different runs do not interfere."""
        factory = async_sessionmaker[AsyncSession](
            bind=db_engine, expire_on_commit=False
        )

        # Create two runs
        async with factory() as session_a:
            engine_a = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_a,
            )
            run1 = await engine_a.create_run(plan_id=plan_id)
            run2 = await engine_a.create_run(plan_id=plan_id)
            await session_a.commit()

        # Transition both in independent sessions — both should succeed
        async with factory() as session_1, factory() as session_2:
            r1 = await session_1.get(WorkflowRun, run1.id)
            r2 = await session_2.get(WorkflowRun, run2.id)
            assert r1 is not None
            assert r2 is not None

            engine_1 = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_1,
            )
            engine_2 = WorkflowEngine(
                provider=_RecordingFakeProvider(),
                session=session_2,
            )

            await engine_1._transition_run(r1, WorkflowState.RUNNING)
            await session_1.commit()

            await engine_2._transition_run(r2, WorkflowState.RUNNING)
            await session_2.commit()

            assert r1.state == WorkflowState.RUNNING.value
            assert r2.state == WorkflowState.RUNNING.value

    async def test_invalid_transition_no_partial_persistence(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Invalid transitions have no partial persistence side effects."""
        provider = _RecordingFakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()
        original_state = run.state

        # Attempt an invalid transition: PENDING → COMPLETED (not allowed)
        from app.ai.workflow.state_machine import StateMachineError

        with pytest.raises(StateMachineError):
            await engine._transition_run(run, WorkflowState.COMPLETED)

        # State must be unchanged
        assert run.state == original_state

        # Verify the DB state is also unchanged
        await db_session.commit()
        await db_session.refresh(run, ["state"])
        assert run.state == WorkflowState.PENDING.value
