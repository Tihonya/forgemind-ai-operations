"""Cross-session WorkflowStep sequencing tests (WP-REC-03F D1 §10).

Verifies that WorkflowStep.seq values remain unique and strictly increasing
across retry attempts when each attempt uses an independent database session
(simulating separate ARQ worker invocations).

The canonical requirement (D1 §10):
- preserve all prior WorkflowStep records;
- append new records after the previous maximum sequence;
- never reuse a previous sequence number for the same run;
- maintain deterministic, strictly increasing per-run ordering across attempts;
- the test does not pass merely because the ORM identity map contains objects.
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
from app.ai.workflow.vertical import execute_workflow
from app.models.workflow import WorkflowRun

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)


class _FailingProvider(ChatProvider):
    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        raise TransientChatProviderError("fail")


class _SuccessProvider(ChatProvider):
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
                '"risks":[{"risk_id":"RISK-001","summary":"Test",'
                '"business_impact":"Test",'
                '"recommended_actions":[],'
                '"sources":[]}]}'
            ),
            model="fake-model",
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            metadata={"provider": "fake"},
        )


@pytest.fixture
async def db_engine() -> AsyncIterator[Any]:
    """Create an engine shared across sessions in the test."""
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    yield engine
    async with async_sessionmaker(bind=engine, expire_on_commit=False)() as session:
        await session.execute(text("DELETE FROM recommendations"))
        await session.execute(text("DELETE FROM workflow_steps"))
        await session.execute(text("DELETE FROM workflow_runs"))
        await session.commit()
    await engine.dispose()


async def _get_plan_id(session: AsyncSession) -> Any:
    result = await session.execute(text("SELECT id FROM production_plans LIMIT 1"))
    row = result.fetchone()
    if row is None:
        pytest.skip("No production plans in database")
    return row[0]


class TestCrossSessionStepSequencing:
    """Verify step sequences across independent sessions (separate worker invocations).

    Each phase uses a fresh session to simulate separate ARQ worker invocations.
    All seq value queries use raw SQL against persisted DB state — the test does
    not pass merely because the ORM identity map contains objects.
    """

    async def test_step_sequences_unique_and_increasing_across_sessions(
        self, db_engine: Any
    ) -> None:
        """Sequences must be unique and strictly increasing across independent
        sessions (simulating separate ARQ worker invocations).
        """
        session_factory = async_sessionmaker(
            bind=db_engine, expire_on_commit=False
        )

        # Phase 1: Session 1 — create run + first attempt (failing provider).
        async with session_factory() as session1:
            plan_id = await _get_plan_id(session1)
            engine = WorkflowEngine(provider=_FailingProvider(), session=session1)
            run = await engine.create_run(plan_id=plan_id)
            await session1.commit()
            run_id = str(run.id)

            await execute_workflow(
                session=session1,
                provider=_FailingProvider(),
                run_id=run.id,
                queued_generation=0,
            )
            await session1.commit()

        # Phase 2: Fresh session — query seq values after attempt 1.
        async with session_factory() as session_q:
            steps1 = await session_q.execute(
                text(
                    "SELECT seq FROM workflow_steps WHERE run_id = :id "
                    "ORDER BY seq"
                ),
                {"id": run_id},
            )
            seqs1 = [r[0] for r in steps1.fetchall()]
            assert len(seqs1) > 0, "First attempt must produce steps"
            prior_max = max(seqs1)

        # Phase 3: Session 2 — retry transition.
        async with session_factory() as session2:
            run_result = await session2.execute(
                select(WorkflowRun).where(WorkflowRun.id == run.id)
            )
            run_obj = run_result.scalar_one()
            engine2 = WorkflowEngine(
                provider=_FailingProvider(), session=session2
            )
            won = await engine2.retry_transition(run_obj)
            await session2.commit()
            assert won is True

        # Phase 4: Session 3 — second attempt (successful provider).
        async with session_factory() as session3:
            run_result = await session3.execute(
                select(WorkflowRun).where(WorkflowRun.id == run.id)
            )
            run_obj = run_result.scalar_one()
            await execute_workflow(
                session=session3,
                provider=_SuccessProvider(),
                run_id=run_obj.id,
                queued_generation=1,
            )
            await session3.commit()

        # Phase 5: Fresh session — query ALL seq values from persisted DB state.
        async with session_factory() as session_q2:
            steps2 = await session_q2.execute(
                text(
                    "SELECT seq FROM workflow_steps WHERE run_id = :id "
                    "ORDER BY seq"
                ),
                {"id": run_id},
            )
            all_seqs = [r[0] for r in steps2.fetchall()]

        # D1 §10: prior step records remain.
        assert len(all_seqs) > len(seqs1), "New steps must be appended"

        # Sequences are unique for the run.
        assert len(set(all_seqs)) == len(all_seqs), (
            f"Duplicate seq values found: {all_seqs}"
        )

        # Sequences are strictly increasing in persisted DB state.
        assert all_seqs == sorted(all_seqs), (
            f"Seq values not in sorted order: {all_seqs}"
        )

        # New steps have seq > prior max.
        new_seqs = [s for s in all_seqs if s not in seqs1]
        for s in new_seqs:
            assert s > prior_max, (
                f"New step seq {s} is not greater than prior max {prior_max}"
            )
