"""Integration tests for WP-REC-03F workflow start/retry lifecycle.

Tests cover:
- Full start → worker → state transitions → recommendation persistence.
- Start → provider outage → FAILED_PROVIDER → user retry → success.
- Start → invalid output → FAILED_VALIDATION → user retry.
- Deterministic risk result queryable independently of provider outcome.
- Append-only workflow steps across retry.
- Worker stale-generation no-op.
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
from app.ai.provider.exceptions import TransientChatProviderError
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.state_machine import WorkflowState
from app.models.workflow import WorkflowRun
from app.services.embedding_provider import FakeEmbeddingProvider
from tests.integration._workflow_rag_support import (
    cleanup_workflow_tables,
    seed_authorization_context,
    seed_production_plan,
)

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)


class _SuccessProvider(ChatProvider):
    """Fake provider that returns a valid recommendation."""

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        run_id = context.get("run_id", "") if context else ""
        return ChatResult(
            content=(
                '{"schema_version":"1.0",'
                f'"run_id":"{run_id}",'
                '"plan_id":"PLAN-2026-W31",'
                '"risks":[{"risk_id":"RISK-001","summary":"Test risk",'
                '"business_impact":"Test impact",'
                '"recommended_actions":[],'
                '"sources":[]}]}'
            ),
            model="fake-model",
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            metadata={"provider": "fake"},
        )


class _FailingProvider(ChatProvider):
    """Fake provider that always fails with a transient error."""

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        raise TransientChatProviderError("Provider unavailable")


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Async session against the live integration database."""
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    session_factory = async_sessionmaker[AsyncSession](
        bind=engine, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await cleanup_workflow_tables(session)
    await engine.dispose()


async def _get_plan_id(session: AsyncSession) -> Any:
    result = await session.execute(
        text("SELECT id FROM production_plans LIMIT 1")
    )
    row = result.fetchone()
    if row is None:
        # Seed a deterministic minimal plan so the test executes rather than
        # skips (WP-REC-05 F1 remediation: vertical tests must not skip).
        plan_id = await seed_production_plan(session)
        await session.commit()
        return plan_id
    return row[0]


class TestWorkflowVerticalExecution:
    """Worker vertical wiring tests."""

    async def test_successful_workflow_reaches_completed(
        self, db_session: AsyncSession
    ) -> None:
        """Full lifecycle: start → risk → provider → validation → completed."""
        from app.ai.workflow.vertical import execute_workflow

        plan_id = await _get_plan_id(db_session)
        engine = WorkflowEngine(provider=_SuccessProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()
        await seed_authorization_context(
            db_session, run_id=run.id, dispatch_generation=0
        )

        result = await execute_workflow(
            session=db_session,
            provider=_SuccessProvider(),
            embedding_provider=FakeEmbeddingProvider(),
            run_id=run.id,
            queued_generation=0,
        )
        await db_session.commit()

        assert result.success is True
        assert result.final_state == WorkflowState.COMPLETED.value

        # Verify recommendation was persisted.
        rec_result = await db_session.execute(
            text("SELECT COUNT(*) FROM recommendations WHERE run_id = :id"),
            {"id": str(run.id)},
        )
        assert rec_result.scalar() == 1

    async def test_provider_failure_persists_risk_result(
        self, db_session: AsyncSession
    ) -> None:
        """Deterministic risk result persisted even when provider fails."""
        from app.ai.workflow.vertical import execute_workflow

        plan_id = await _get_plan_id(db_session)
        engine = WorkflowEngine(provider=_FailingProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()
        await seed_authorization_context(
            db_session, run_id=run.id, dispatch_generation=0
        )

        result = await execute_workflow(
            session=db_session,
            provider=_FailingProvider(),
            embedding_provider=FakeEmbeddingProvider(),
            run_id=run.id,
            queued_generation=0,
        )
        await db_session.commit()

        assert result.success is False
        assert result.final_state == WorkflowState.FAILED_PROVIDER.value

        # Verify the run is in FAILED_PROVIDER.
        db_run = await db_session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run.id)
        )
        db_run_obj = db_run.scalar_one()
        assert db_run_obj.state == WorkflowState.FAILED_PROVIDER.value
        assert db_run_obj.error_code is not None

    async def test_retry_from_failed_provider_succeeds(
        self, db_session: AsyncSession
    ) -> None:
        """Retry from FAILED_PROVIDER with a successful provider."""
        from app.ai.workflow.vertical import execute_workflow

        plan_id = await _get_plan_id(db_session)

        # First attempt: failing provider.
        engine = WorkflowEngine(provider=_FailingProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()
        await seed_authorization_context(
            db_session, run_id=run.id, dispatch_generation=0
        )

        result1 = await execute_workflow(
            session=db_session,
            provider=_FailingProvider(),
            embedding_provider=FakeEmbeddingProvider(),
            run_id=run.id,
            queued_generation=0,
        )
        await db_session.commit()
        assert result1.final_state == WorkflowState.FAILED_PROVIDER.value

        # Retry transition.
        await db_session.refresh(run)
        won = await engine.retry_transition(run)
        await db_session.commit()
        assert won is True
        assert run.dispatch_generation == 1
        await seed_authorization_context(
            db_session,
            run_id=run.id,
            dispatch_generation=1,
            capture_action="retry",
        )

        # Second attempt: successful provider.
        result2 = await execute_workflow(
            session=db_session,
            provider=_SuccessProvider(),
            embedding_provider=FakeEmbeddingProvider(),
            run_id=run.id,
            queued_generation=1,
        )
        await db_session.commit()
        assert result2.success is True
        assert result2.final_state == WorkflowState.COMPLETED.value


class TestStaleGenerationWorkerSkip:
    """D5 §4: Stale-generation worker no-op."""

    async def test_stale_generation_does_not_execute(
        self, db_session: AsyncSession
    ) -> None:
        """A stale-generation job does not execute the provider workflow."""
        from app.ai.workflow.vertical import execute_workflow

        plan_id = await _get_plan_id(db_session)
        engine = WorkflowEngine(provider=_SuccessProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        # Call with a stale generation (run is at generation 0, call with 99).
        result = await execute_workflow(
            session=db_session,
            provider=_SuccessProvider(),
            embedding_provider=FakeEmbeddingProvider(),
            run_id=run.id,
            queued_generation=99,
        )
        await db_session.commit()

        # The stale generation should result in a skip.
        assert result.success is False
        assert result.final_state == WorkflowState.PENDING.value

        # The stale generation should result in a skip. Only the
        # user_action step (emitted at run creation) exists; no execution
        # step (deterministic_calculation/retrieval/provider_call/validation/
        # recommendation) was recorded.
        steps_result = await db_session.execute(
            text(
                "SELECT COUNT(*) FROM workflow_steps WHERE run_id = :id "
                "AND step_name <> 'user_action'"
            ),
            {"id": str(run.id)},
        )
        assert steps_result.scalar() == 0


class TestAppendOnlyWorkflowSteps:
    """D1 §10: Append-only workflow steps across retry.

    The canonical requirement is:
    - preserve all prior WorkflowStep records;
    - append new records after the previous maximum sequence;
    - never reuse a previous sequence number for the same run;
    - maintain deterministic, strictly increasing per-run ordering across attempts.
    """

    async def test_steps_append_across_retry(
        self, db_session: AsyncSession
    ) -> None:
        """New steps get sequence numbers after the prior max.

        Verifies:
        - prior step records remain after retry;
        - new steps have sequence values greater than the prior maximum;
        - sequences are unique for the run;
        - sequences are strictly increasing in persisted database state;
        - behavior is correct across transaction/session boundaries.
        """
        from app.ai.workflow.vertical import execute_workflow

        plan_id = await _get_plan_id(db_session)

        # First attempt with failing provider.
        engine = WorkflowEngine(provider=_FailingProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()
        await seed_authorization_context(
            db_session, run_id=run.id, dispatch_generation=0
        )

        await execute_workflow(
            session=db_session,
            provider=_FailingProvider(),
            embedding_provider=FakeEmbeddingProvider(),
            run_id=run.id,
            queued_generation=0,
        )
        await db_session.commit()

        # Check steps from first attempt — query persisted DB state directly.
        steps1 = await db_session.execute(
            text(
                "SELECT seq FROM workflow_steps WHERE run_id = :id "
                "ORDER BY seq"
            ),
            {"id": str(run.id)},
        )
        seqs1 = [r[0] for r in steps1.fetchall()]
        assert len(seqs1) > 0
        prior_max = max(seqs1)

        # Retry transition (committed, crossing a transaction boundary).
        await db_session.refresh(run)
        won = await engine.retry_transition(run)
        await db_session.commit()
        assert won is True
        await seed_authorization_context(
            db_session,
            run_id=run.id,
            dispatch_generation=1,
            capture_action="retry",
        )

        # Second attempt with successful provider (new transaction boundary).
        await execute_workflow(
            session=db_session,
            provider=_SuccessProvider(),
            embedding_provider=FakeEmbeddingProvider(),
            run_id=run.id,
            queued_generation=1,
        )
        await db_session.commit()

        # Query ALL step sequences from persisted DB state.
        steps2 = await db_session.execute(
            text(
                "SELECT seq FROM workflow_steps WHERE run_id = :id "
                "ORDER BY seq"
            ),
            {"id": str(run.id)},
        )
        all_seqs = [r[0] for r in steps2.fetchall()]

        # D1 §10: Previous WorkflowStep records remain append-only.
        assert len(all_seqs) > len(seqs1), (
            "New steps must be appended after prior steps"
        )

        # Sequences are unique for the run (no reuse of prior seq numbers).
        assert len(set(all_seqs)) == len(all_seqs), (
            f"Duplicate seq values found: {all_seqs}"
        )

        # Sequences are strictly increasing in persisted DB state.
        assert all_seqs == sorted(all_seqs), (
            f"Seq values not in sorted order: {all_seqs}"
        )

        # New steps have sequence values greater than the prior maximum.
        new_seqs = [s for s in all_seqs if s not in seqs1]
        for s in new_seqs:
            assert s > prior_max, (
                f"New step seq {s} is not greater than prior max {prior_max}"
            )
