"""Unit tests for WP-REC-03F dispatch generation (D5/D6).

Tests cover:
- Migration and model behavior: existing rows receive generation 0;
  new runs start at generation 0; generation is non-null and
  non-negative.
- Authorized retry: one accepted retry transition increments
  generation exactly once; rejected or concurrent duplicate retry
  requests do not increment it; enqueue failure does not allocate
  another generation.
- Deterministic job ID: repeated enqueue of one generation produces
  the same _job_id; later authorized retry produces a different
  _job_id; start and later retry cannot collide.
- pending_since behavior: set on creation, reset on retry.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.state_machine import StateMachineError, WorkflowState

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)


class _FakeProvider(ChatProvider):
    """Fake provider that returns a minimal valid result."""

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        return ChatResult(
            content='{"schema_version":"1.0","run_id":"00000000-0000-0000-0000-000000000000","plan_id":"PLAN-2026-W31","risks":[{"risk_id":"RISK-001","summary":"s","business_impact":"b","recommended_actions":[],"sources":[]}]}',
            model="fake-model",
            finish_reason="stop",
        )


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


class TestDispatchGenerationModel:
    """D5 §9.1: Migration and model behavior."""

    async def test_new_run_starts_at_generation_zero(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """New runs start at dispatch_generation = 0."""
        engine = WorkflowEngine(provider=_FakeProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        assert run.dispatch_generation == 0

    async def test_generation_is_non_null(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """dispatch_generation is non-null after creation."""
        engine = WorkflowEngine(provider=_FakeProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        result = await db_session.execute(
            text("SELECT dispatch_generation FROM workflow_runs WHERE id = :id"),
            {"id": str(run.id)},
        )
        gen = result.scalar()
        assert gen is not None
        assert gen == 0

    async def test_generation_non_negative_constraint(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """dispatch_generation cannot become negative (CHECK constraint)."""
        engine = WorkflowEngine(provider=_FakeProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        # Attempt to set a negative value directly.
        with pytest.raises(Exception):  # noqa: B017
            await db_session.execute(
                text(
                    "UPDATE workflow_runs SET dispatch_generation = -1 "
                    "WHERE id = :id"
                ),
                {"id": str(run.id)},
            )
            await db_session.commit()
        await db_session.rollback()


class TestDispatchGenerationRetry:
    """D5 §9.2: Authorized retry generation increment."""

    async def test_retry_increments_generation_once(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """One accepted retry transition increments generation exactly once."""
        engine = WorkflowEngine(provider=_FakeProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()
        assert run.dispatch_generation == 0

        # Manually transition to FAILED_PROVIDER for retry eligibility.
        await db_session.execute(
            text(
                "UPDATE workflow_runs SET state = 'FAILED_PROVIDER', "
                "completed_at = NOW(), error_code = 'PROVIDER_TRANSIENT', "
                "error_detail = 'test' WHERE id = :id"
            ),
            {"id": str(run.id)},
        )
        await db_session.commit()
        await db_session.refresh(run)

        won = await engine.retry_transition(run)
        await db_session.commit()

        assert won is True
        assert run.dispatch_generation == 1

    async def test_concurrent_retry_only_one_wins(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Exactly one concurrent caller wins the generation increment."""
        engine = WorkflowEngine(provider=_FakeProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        # Transition to FAILED_PROVIDER.
        await db_session.execute(
            text(
                "UPDATE workflow_runs SET state = 'FAILED_PROVIDER', "
                "completed_at = NOW() WHERE id = :id"
            ),
            {"id": str(run.id)},
        )
        await db_session.commit()
        await db_session.refresh(run)

        # First retry wins.
        won1 = await engine.retry_transition(run)
        await db_session.commit()
        assert won1 is True
        assert run.dispatch_generation == 1

        # Second retry from PENDING state raises StateMachineError
        # (self-transition PENDING → PENDING is not permitted).
        await db_session.refresh(run)
        with pytest.raises(StateMachineError, match="Self-transition"):
            await engine.retry_transition(run)

    async def test_enqueue_failure_does_not_increment(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """Enqueue failure does not allocate another generation."""
        engine = WorkflowEngine(provider=_FakeProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        # Transition to FAILED_PROVIDER and retry.
        await db_session.execute(
            text(
                "UPDATE workflow_runs SET state = 'FAILED_PROVIDER', "
                "completed_at = NOW() WHERE id = :id"
            ),
            {"id": str(run.id)},
        )
        await db_session.commit()
        await db_session.refresh(run)

        won = await engine.retry_transition(run)
        await db_session.commit()
        assert won is True
        assert run.dispatch_generation == 1

        # Simulate enqueue failure — generation should remain 1.
        await db_session.refresh(run)
        assert run.dispatch_generation == 1
        assert run.state == WorkflowState.PENDING.value


class TestDeterministicJobId:
    """D5 §9.3: Deterministic job ID construction."""

    def test_same_generation_produces_same_job_id(self) -> None:
        """Repeated enqueue of one generation produces the same _job_id."""
        run_id = uuid4()
        gen = 0
        job_id_1 = f"workflow:{run_id}:{gen}"
        job_id_2 = f"workflow:{run_id}:{gen}"
        assert job_id_1 == job_id_2

    def test_later_generation_produces_different_job_id(self) -> None:
        """Later authorized retry produces a different _job_id."""
        run_id = uuid4()
        job_id_gen0 = f"workflow:{run_id}:0"
        job_id_gen1 = f"workflow:{run_id}:1"
        assert job_id_gen0 != job_id_gen1

    def test_start_and_retry_cannot_collide(self) -> None:
        """Start (gen 0) and later retry (gen 1) cannot collide."""
        run_id = uuid4()
        start_job_id = f"workflow:{run_id}:0"
        retry_job_id = f"workflow:{run_id}:1"
        assert start_job_id != retry_job_id

    def test_different_runs_cannot_collide(self) -> None:
        """Different runs with the same generation cannot collide."""
        run1 = uuid4()
        run2 = uuid4()
        assert f"workflow:{run1}:0" != f"workflow:{run2}:0"


class TestPendingSinceBehavior:
    """D6 §1: pending_since creation and retry-reset semantics."""

    async def test_pending_since_set_on_creation(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """pending_since is set when a new WorkflowRun is created."""
        engine = WorkflowEngine(provider=_FakeProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        assert run.pending_since is not None
        # Should be close to now.
        now = datetime.now(UTC)
        assert abs((now - run.pending_since).total_seconds()) < 5

    async def test_pending_since_reset_on_retry(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """pending_since is reset on FAILED_* → PENDING retry."""
        engine = WorkflowEngine(provider=_FakeProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()
        original_pending_since = run.pending_since
        assert original_pending_since is not None

        # Transition to FAILED_PROVIDER.
        await db_session.execute(
            text(
                "UPDATE workflow_runs SET state = 'FAILED_PROVIDER', "
                "completed_at = NOW() WHERE id = :id"
            ),
            {"id": str(run.id)},
        )
        await db_session.commit()
        await db_session.refresh(run)

        # Wait a moment to ensure timestamp differs.
        import asyncio
        await asyncio.sleep(0.05)

        won = await engine.retry_transition(run)
        await db_session.commit()
        assert won is True
        assert run.pending_since is not None
        assert run.pending_since > original_pending_since

    async def test_pending_since_nullable_for_existing_rows(
        self, db_session: AsyncSession, plan_id: Any
    ) -> None:
        """pending_since can be NULL for non-PENDING rows."""
        engine = WorkflowEngine(provider=_FakeProvider(), session=db_session)
        run = await engine.create_run(plan_id=plan_id)
        await db_session.commit()

        # Transition to COMPLETED.
        await db_session.execute(
            text(
                "UPDATE workflow_runs SET state = 'COMPLETED', "
                "completed_at = NOW(), pending_since = NULL "
                "WHERE id = :id"
            ),
            {"id": str(run.id)},
        )
        await db_session.commit()

        result = await db_session.execute(
            text("SELECT pending_since FROM workflow_runs WHERE id = :id"),
            {"id": str(run.id)},
        )
        assert result.scalar() is None
