"""Vertical workflow wiring executed inside the ARQ worker (WP-REC-03F).

This module owns the complete long-running workflow execution sequence:

1. Load the durable run and related production plan.
2. Generation-guarded PENDING → RUNNING transition (D6 §5).
3. Deterministic risk calculation (persisted independently of provider).
4. Provider invocation through the existing WP-REC-03A abstraction.
5. Existing WP-REC-03D provider retry/outage handling (via RetryingChatProvider).
6. Validation through the existing WP-REC-03C validator.
7. Recommendation persistence through the existing WP-REC-03B model.
8. State-machine transitions (AWAITING_VALIDATION → COMPLETED or FAILED_VALIDATION).
9. Workflow-step trace persistence.
10. Correct terminal failure categorization.

Design contract (WP-REC-03F):

- The vertical wiring reuses the existing implementation boundaries:
  - ChatProvider from 03A (wrapped in RetryingChatProvider from 03D)
  - WorkflowEngine from 03B
  - validate_structured_output from 03C
  - Recommendation ORM model from 03B
  - analyze_plan risk engine from WP-2.9

- Deterministic risk results are persisted independently of provider
  success. If the provider fails after the risk engine succeeds, the
  deterministic risk result remains persisted and available.

- No secrets are exposed in error messages, logs, or responses.
- Correlation ID is propagated through all steps.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import (
    ChatProviderError,
    PermanentChatProviderError,
    TransientChatProviderError,
)
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.prompts import build_system_prompt
from app.ai.workflow.schema_validator import (
    StructuredOutputValidationError,
    validate_structured_output,
)
from app.ai.workflow.state_machine import WorkflowState
from app.core.logging import get_logger
from app.models.production import ProductionPlan
from app.models.workflow import Recommendation, WorkflowRun, WorkflowStep
from app.schemas.recommendation import RECOMMENDATION_SCHEMA_VERSION
from app.services.risk_engine import analyze_plan

_logger = get_logger(__name__)

# Safe error codes for step-level recording.
_ERROR_CODE_PROVIDER_TRANSIENT = "PROVIDER_TRANSIENT"
_ERROR_CODE_PROVIDER_PERMANENT = "PROVIDER_PERMANENT"
_ERROR_CODE_VALIDATION = "VALIDATION_FAILED"
_ERROR_CODE_INTERNAL = "INTERNAL_ERROR"


class VerticalExecutionResult:
    """Result of vertical workflow execution.

    Attributes:
        final_state: The final WorkflowState of the run.
        success: True if the run reached COMPLETED.
    """

    __slots__ = ("final_state", "success")

    def __init__(self, final_state: str, success: bool) -> None:
        self.final_state = final_state
        self.success = success


async def execute_workflow(
    *,
    session: AsyncSession,
    provider: ChatProvider,
    run_id: UUID,
    queued_generation: int,
) -> VerticalExecutionResult:
    """Execute the complete workflow vertical wiring.

    This function is called by the ARQ worker functions
    (``workflow_start`` and ``workflow_retry``) after the generation
    guard has been validated.

    The caller owns the transaction boundary. This function flushes
    changes but does NOT commit — the worker commits after success or
    rolls back after failure.

    Args:
        session: Async database session.
        provider: ChatProvider instance (already wrapped in
            RetryingChatProvider if applicable).
        run_id: Workflow run UUID.
        queued_generation: The dispatch generation from the ARQ job
            identity (D5 §4).

    Returns:
        VerticalExecutionResult with the final state and success flag.
    """
    engine = WorkflowEngine(provider=provider, session=session)

    # 1. Load the durable run.
    result = await session.execute(
        select(WorkflowRun).where(WorkflowRun.id == run_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        _logger.error(
            "workflow.vertical.run_not_found",
            run_id=str(run_id),
        )
        return VerticalExecutionResult(
            WorkflowState.FAILED_INTERNAL.value, False
        )

    # 2. Generation-guarded PENDING → RUNNING transition (D6 §5).
    transitioned = await engine.transition_to_running_with_generation(
        run,
        expected_generation=queued_generation,
    )
    if not transitioned:
        _logger.info(
            "workflow.vertical.stale_generation_skip",
            run_id=str(run_id),
            queued_generation=queued_generation,
            actual_state=run.state,
            actual_generation=run.dispatch_generation,
        )
        return VerticalExecutionResult(run.state, False)

    # 3. Load the related production plan to get the plan code.
    plan_result = await session.execute(
        select(ProductionPlan).where(ProductionPlan.id == run.plan_id)
    )
    plan = plan_result.scalar_one_or_none()
    if plan is None:
        _logger.error(
            "workflow.vertical.plan_not_found",
            run_id=str(run_id),
            plan_id=str(run.plan_id),
        )
        await engine.transition_to_failed_internal(
            run,
            error_detail="INTERNAL_ERROR",
        )
        return VerticalExecutionResult(
            WorkflowState.FAILED_INTERNAL.value, False
        )

    plan_code = plan.code

    # 4. Deterministic risk calculation — persisted independently of
    #    provider success (D1/C1 contract).
    risk_data_json = "[]"
    try:
        risks = await analyze_plan(session, plan_code)
        risk_data_json = json.dumps(
            [
                {
                    "risk_id": f"RISK-{i + 1:03d}",
                    "component_code": r.component_code,
                    "component_name": r.component_name,
                    "affected_wo_code": r.affected_wo_code,
                    "required": str(r.required),
                    "available": str(r.available),
                    "confirmed_early": str(r.confirmed_early),
                    "confirmed_late": str(r.confirmed_late),
                    "shortage": str(r.shortage),
                    "severity": r.severity,
                    "has_approved_alternative": r.has_approved_alternative,
                    "has_proposed_alternative": r.has_proposed_alternative,
                    "need_date": r.need_date.isoformat(),
                    "plan_code": r.plan_code,
                }
                for i, r in enumerate(risks)
            ],
            default=str,
        )
        _logger.info(
            "workflow.vertical.risk_calculated",
            run_id=str(run_id),
            plan_code=plan_code,
            risk_count=len(risks),
        )
    except Exception:
        _logger.error(
            "workflow.vertical.risk_engine_failed",
            run_id=str(run_id),
            plan_code=plan_code,
        )
        await engine.transition_to_failed_internal(
            run,
            error_detail="INTERNAL_ERROR",
        )
        return VerticalExecutionResult(
            WorkflowState.FAILED_INTERNAL.value, False
        )

    # 5. Build the prompt and call the provider.
    #    The engine's execute_provider_call transitions PENDING → RUNNING
    #    → AWAITING_VALIDATION (or FAILED_PROVIDER/FAILED_INTERNAL).
    #    Since we already transitioned to RUNNING via the generation
    #    guard, we call the provider directly and manage transitions
    #    manually to avoid a double PENDING → RUNNING attempt.
    prompt = build_system_prompt(
        plan_id=plan_code,
        run_id=str(run_id),
        risk_data=risk_data_json,
    )

    # Record the provider-call step.
    step = WorkflowStep(
        run_id=run.id,
        correlation_id=run.correlation_id,
        seq=await engine._next_step_seq(run.id),
        step_name="provider_call",
        status="started",
    )
    session.add(step)
    await session.flush()

    import time
    start = time.monotonic()
    chat_result: ChatResult | None = None
    provider_error_code: str | None = None

    try:
        context: dict[str, Any] = {
            "correlation_id": str(run.correlation_id),
            "run_id": str(run.id),
            "dispatch_generation": queued_generation,
        }
        chat_result = await provider.complete(
            prompt=prompt,
            schema=None,
            context=context,
        )
    except TransientChatProviderError:
        provider_error_code = _ERROR_CODE_PROVIDER_TRANSIENT
    except (PermanentChatProviderError, ChatProviderError):
        provider_error_code = _ERROR_CODE_PROVIDER_PERMANENT
    except Exception:
        provider_error_code = _ERROR_CODE_INTERNAL

    latency_ms = int((time.monotonic() - start) * 1000)

    if chat_result is not None:
        # Provider succeeded — record step and transition to AWAITING_VALIDATION.
        step.status = "completed"
        step.model_name = chat_result.model
        step.latency_ms = latency_ms
        step.token_usage = chat_result.usage if chat_result.usage else None
        step.step_metadata = dict(chat_result.metadata)
        step.completed_at = datetime.now(UTC)

        # Transition RUNNING → AWAITING_VALIDATION.
        await engine._transition_run(run, WorkflowState.AWAITING_VALIDATION)
        await session.flush()

        _logger.info(
            "workflow.vertical.provider_succeeded",
            run_id=str(run_id),
            model=chat_result.model,
            latency_ms=latency_ms,
        )

        # 6. Validate structured output (03C).
        try:
            recommendation_data = validate_structured_output(
                chat_result.content
            )
        except StructuredOutputValidationError:
            # Validation failed — transition to FAILED_VALIDATION.
            step_record = WorkflowStep(
                run_id=run.id,
                correlation_id=run.correlation_id,
                seq=await engine._next_step_seq(run.id),
                step_name="validation",
                status="failed",
                error_code=_ERROR_CODE_VALIDATION,
                error_detail="StructuredOutputValidationError",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
            session.add(step_record)
            await session.flush()

            await engine.transition_to_failed_validation(
                run,
                error_code=_ERROR_CODE_VALIDATION,
                error_detail="StructuredOutputValidationError",
            )
            _logger.warning(
                "workflow.vertical.validation_failed",
                run_id=str(run_id),
            )
            return VerticalExecutionResult(
                WorkflowState.FAILED_VALIDATION.value, False
            )

        # 7. Persist recommendation (03B model, 03F write path).
        recommendation = Recommendation(
            run_id=run.id,
            plan_id=run.plan_id,
            status="VALIDATED",
            content=recommendation_data.model_dump(mode="json"),
            schema_version=RECOMMENDATION_SCHEMA_VERSION,
        )
        session.add(recommendation)
        await session.flush()

        # Record validation step.
        val_step = WorkflowStep(
            run_id=run.id,
            correlation_id=run.correlation_id,
            seq=await engine._next_step_seq(run.id),
            step_name="validation",
            status="completed",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        session.add(val_step)
        await session.flush()

        # 8. Transition AWAITING_VALIDATION → COMPLETED.
        await engine.transition_to_completed(run)

        _logger.info(
            "workflow.vertical.completed",
            run_id=str(run_id),
            plan_code=plan_code,
            risk_count=len(risks),
        )
        return VerticalExecutionResult(
            WorkflowState.COMPLETED.value, True
        )
    # Provider failed — record step and transition to FAILED_PROVIDER
    # or FAILED_INTERNAL.
    step.status = "failed"
    step.latency_ms = latency_ms
    step.error_code = provider_error_code
    step.error_detail = "ProviderError"
    step.completed_at = datetime.now(UTC)

    if provider_error_code == _ERROR_CODE_INTERNAL:
        target_state = WorkflowState.FAILED_INTERNAL
    else:
        target_state = WorkflowState.FAILED_PROVIDER

    await engine._transition_run(
        run,
        target_state,
        error_code=provider_error_code,
        error_detail="ProviderError",
    )
    await session.flush()

    _logger.warning(
        "workflow.vertical.provider_failed",
        run_id=str(run_id),
        error_code=provider_error_code,
        latency_ms=latency_ms,
    )
    return VerticalExecutionResult(target_state.value, False)
