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
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider.acceptance_scenarios import InvalidOutputProvider
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

    async def test_factory_returns_at008_provider_with_env_var(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """R5: Verify factory selects AT008 scenario via FORGEMIND_ACCEPTANCE_SCENARIO."""
        from app.ai.provider.acceptance_scenarios import InvalidOutputProvider
        from app.ai.provider.factory import create_chat_provider

        # Set environment variable to trigger factory selection
        monkeypatch.setenv("FORGEMIND_ACCEPTANCE_SCENARIO", "AT008_INVALID_OUTPUT")

        # Create provider through factory (real production path)
        provider = create_chat_provider()

        # Verify it's wrapped in RetryingChatProvider
        from app.ai.workflow.outage_handler import RetryingChatProvider
        assert isinstance(provider, RetryingChatProvider)

        # Verify the wrapped provider is InvalidOutputProvider
        assert isinstance(provider._delegate, InvalidOutputProvider)

        # Verify it produces invalid output
        result = await provider.complete("test prompt")
        assert "invalid" in result.content or "INVALID" in result.content

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
