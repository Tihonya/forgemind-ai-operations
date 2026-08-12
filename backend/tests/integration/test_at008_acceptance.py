"""AT-008 acceptance harness — implementation-verification test (WP-REC-03H Phase B).

Exercises the real workflow vertical through the acceptance-scenario
provider ``AT008_INVALID_OUTPUT``, verifying:

1. Provider returns invalid (schema-incompatible) output.
2. ``validate_structured_output`` raises ``StructuredOutputValidationError``.
3. Workflow transitions to ``FAILED_VALIDATION``.
4. Workflow-step trace records the validation failure.
5. No ``Recommendation`` row is persisted.
6. Deterministic risk data remains available independently.

This is an **implementation-verification** test — it proves the harness
mechanics are correct.  It does NOT declare AT-008 PASS.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider.acceptance_scenarios import InvalidOutputProvider
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.state_machine import WorkflowState
from app.ai.workflow.vertical import execute_workflow
from app.models.workflow import Recommendation, WorkflowRun, WorkflowStep

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)


async def _get_plan_id(session: AsyncSession):
    from tests.integration.conftest import _get_seed_plan_id
    return await _get_seed_plan_id(session)


class TestAT008AcceptanceInvalidOutput:
    """AT-008: Invalid provider output → FAILED_VALIDATION via real vertical."""

    async def test_invalid_output_reaches_failed_validation(
        self, acceptance_db_session: AsyncSession
    ) -> None:
        """Full AT-008 path: invalid output → FAILED_VALIDATION, no recommendation."""
        session = acceptance_db_session
        plan_id = await _get_plan_id(session)

        provider = InvalidOutputProvider()
        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()

        result = await execute_workflow(
            session=session,
            provider=provider,
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()

        # 1. Final state is FAILED_VALIDATION.
        assert result.success is False
        assert result.final_state == WorkflowState.FAILED_VALIDATION.value

        # 2. WorkflowRun persisted in FAILED_VALIDATION.
        db_run = await session.execute(
            select(WorkflowRun).where(WorkflowRun.id == run.id)
        )
        run_row = db_run.scalar_one()
        assert run_row.state == WorkflowState.FAILED_VALIDATION.value
        assert run_row.error_code == "VALIDATION_FAILED"

        # 3. Workflow steps include a failed validation step.
        steps_result = await session.execute(
            select(WorkflowStep)
            .where(WorkflowStep.run_id == run.id)
            .order_by(WorkflowStep.seq)
        )
        steps = list(steps_result.scalars().all())
        assert len(steps) >= 2, f"Expected >= 2 steps, got {len(steps)}"

        # Provider call step completed (provider returned output).
        provider_steps = [s for s in steps if s.step_name == "provider_call"]
        assert len(provider_steps) == 1
        assert provider_steps[0].status == "completed"

        # Validation step failed.
        validation_steps = [s for s in steps if s.step_name == "validation"]
        assert len(validation_steps) == 1
        assert validation_steps[0].status == "failed"
        assert validation_steps[0].error_code == "VALIDATION_FAILED"

        # 4. No recommendation persisted.
        rec_count = await session.execute(
            select(Recommendation).where(Recommendation.run_id == run.id)
        )
        assert len(list(rec_count.scalars().all())) == 0

    async def test_at008_deterministic_risk_available_after_validation_failure(
        self, acceptance_db_session: AsyncSession
    ) -> None:
        """Deterministic risks remain queryable after FAILED_VALIDATION."""
        session = acceptance_db_session
        plan_id = await _get_plan_id(session)

        # Get plan code for risk query.
        plan_result = await session.execute(
            text("SELECT code FROM production_plans WHERE id = :id"),
            {"id": plan_id},
        )
        plan_row = plan_result.fetchone()
        assert plan_row is not None
        plan_code = plan_row[0]

        provider = InvalidOutputProvider()
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

        # Verify risks are still available (deterministic calculation
        # is independent of provider outcome).
        from app.services.risk_engine import analyze_plan
        risks = await analyze_plan(session, plan_code)
        assert len(risks) > 0, "Deterministic risks must remain available"
