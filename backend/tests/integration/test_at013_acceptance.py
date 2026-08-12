"""AT-013 acceptance harness — implementation-verification test (WP-REC-03H Phase B).

Exercises the real workflow vertical through the acceptance-scenario
provider ``AT013_OUTAGE_UNTIL_RETRY``, verifying:

1. Provider outage on generation 0 → ``FAILED_PROVIDER``.
2. Workflow-step trace records the provider failure.
3. User Retry increments ``dispatch_generation``.
4. Post-retry execution on generation 1 → ``COMPLETED``.
5. Recommendation row persisted after retry success.
6. Workflow steps are append-only (prior steps preserved).
7. Deterministic risks remain available throughout.

This is an **implementation-verification** test — it proves the harness
mechanics are correct.  It does NOT declare AT-013 PASS.
"""

from __future__ import annotations

import os
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider.acceptance_scenarios import OutageUntilRetryProvider
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.state_machine import WorkflowState
from app.ai.workflow.vertical import execute_workflow
from app.models.workflow import Recommendation, WorkflowRun, WorkflowStep

pytestmark = pytest.mark.acceptance

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

# Note: No module-level skipif. Tests requiring acceptance_db_session will fail
# fast via the fixture's database URL validation. Factory-only tests (test_factory_*)
# do not require a database and should always run.


async def _get_plan_id(session: AsyncSession) -> UUID:
    """Get the first plan ID from the database for testing."""
    from tests.integration.conftest import _get_seed_plan_id
    return cast(UUID, await _get_seed_plan_id(session))


class TestAT013AcceptanceOutageRetry:
    """AT-013: Provider outage → FAILED_PROVIDER → user Retry → COMPLETED."""

    async def test_outage_then_retry_succeeds(
        self, acceptance_db_session: AsyncSession
    ) -> None:
        """Full AT-013 path: outage gen 0 → FAILED_PROVIDER → retry gen 1 → COMPLETED."""
        session = acceptance_db_session
        plan_id = await _get_plan_id(session)

        provider = OutageUntilRetryProvider()
        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()

        # --- Generation 0: provider outage ---
        result0 = await execute_workflow(
            session=session,
            provider=provider,
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()

        # 1. FAILED_PROVIDER after outage.
        assert result0.success is False
        assert result0.final_state == WorkflowState.FAILED_PROVIDER.value

        # 2. Verify run state in database.
        db_run = await session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run.id)
        )
        run_row = db_run.scalar_one()
        assert run_row.state == WorkflowState.FAILED_PROVIDER.value
        assert run_row.error_code == "PROVIDER_TRANSIENT"

        # 3. Workflow steps record provider failure.
        steps_result = await session.execute(
            select(WorkflowStep)
            .where(WorkflowStep.run_id == run.id)
            .order_by(WorkflowStep.seq)
        )
        gen0_steps = list(steps_result.scalars().all())
        assert len(gen0_steps) >= 1, "Expected at least 1 step after outage"

        provider_steps_gen0 = [s for s in gen0_steps if s.step_name == "provider_call"]
        assert len(provider_steps_gen0) == 1
        assert provider_steps_gen0[0].status == "failed"
        assert provider_steps_gen0[0].error_code == "PROVIDER_TRANSIENT"

        gen0_step_count = len(gen0_steps)

        # --- User Retry (authorised application path) ---
        await session.refresh(run_row)
        won = await engine.retry_transition(run_row)
        await session.commit()
        assert won is True
        assert run_row.dispatch_generation == 1

        # --- Generation 1: post-retry success ---
        # Create a fresh provider instance (as the real worker does).
        retry_provider = OutageUntilRetryProvider()
        result1 = await execute_workflow(
            session=session,
            provider=retry_provider,
            run_id=run.id,
            queued_generation=1,
        )
        await session.commit()

        # 4. COMPLETED after retry.
        assert result1.success is True
        assert result1.final_state == WorkflowState.COMPLETED.value

        # 5. Recommendation row persisted.
        rec_result = await session.execute(
            select(Recommendation).where(Recommendation.run_id == run.id)
        )
        recommendations = list(rec_result.scalars().all())
        assert len(recommendations) == 1
        assert recommendations[0].status == "VALIDATED"

        # 6. Append-only workflow steps: prior steps preserved, new appended.
        all_steps_result = await session.execute(
            select(WorkflowStep)
            .where(WorkflowStep.run_id == run.id)
            .order_by(WorkflowStep.seq)
        )
        all_steps = list(all_steps_result.scalars().all())
        assert len(all_steps) > gen0_step_count, (
            "Post-retry must append new steps, not replace prior ones"
        )

        # Verify post-retry steps include completed provider_call + validation.
        post_retry_provider_steps = [
            s for s in all_steps[gen0_step_count:]
            if s.step_name == "provider_call"
        ]
        assert len(post_retry_provider_steps) == 1
        assert post_retry_provider_steps[0].status == "completed"

        post_retry_validation_steps = [
            s for s in all_steps[gen0_step_count:]
            if s.step_name == "validation"
        ]
        assert len(post_retry_validation_steps) == 1
        assert post_retry_validation_steps[0].status == "completed"

        # Sequences are strictly increasing.
        all_seqs = [s.seq for s in all_steps]
        assert all_seqs == sorted(all_seqs)
        assert len(set(all_seqs)) == len(all_seqs)

    async def test_at013_risk_available_during_outage(
        self, acceptance_db_session: AsyncSession
    ) -> None:
        """Deterministic risks remain queryable even after provider outage."""
        session = acceptance_db_session
        plan_id = await _get_plan_id(session)

        # Get plan code.
        plan_result = await session.execute(
            text("SELECT code FROM production_plans WHERE id = :id"),
            {"id": plan_id},
        )
        plan_row = plan_result.fetchone()
        assert plan_row is not None
        plan_code = plan_row[0]

        provider = OutageUntilRetryProvider()
        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()

        await execute_workflow(
            session=session,
            provider=provider,
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()

        # Verify risks are still available after provider outage.
        from app.services.risk_engine import analyze_plan
        risks = await analyze_plan(session, plan_code)
        assert len(risks) > 0, "Deterministic risks must remain available"

    async def test_factory_returns_at013_provider_with_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R5: Verify factory selects AT013 scenario via FORGEMIND_ACCEPTANCE_SCENARIO."""
        from app.ai.provider.acceptance_scenarios import OutageUntilRetryProvider
        from app.ai.provider.exceptions import TransientChatProviderError
        from app.ai.provider.factory import create_chat_provider

        # Set environment variable to trigger factory selection
        monkeypatch.setenv("FORGEMIND_ACCEPTANCE_SCENARIO", "AT013_OUTAGE_UNTIL_RETRY")

        # Create provider through factory (real production path)
        provider = create_chat_provider()

        # Verify it's wrapped in RetryingChatProvider
        from app.ai.workflow.outage_handler import RetryingChatProvider
        assert isinstance(provider, RetryingChatProvider)

        # Verify the wrapped provider is OutageUntilRetryProvider
        assert isinstance(provider._delegate, OutageUntilRetryProvider)

        # Verify it raises TransientChatProviderError on generation 0
        # (RetryingChatProvider will retry and eventually exhaust retries)
        with pytest.raises(TransientChatProviderError):
            await provider.complete(
                "test prompt",
                context={"run_id": "test", "dispatch_generation": 0},
            )

        # Verify it succeeds on generation 1
        result = await provider.complete(
            "test prompt",
            context={"run_id": "test", "dispatch_generation": 1},
        )
        assert result.content is not None
        assert len(result.content) > 0
