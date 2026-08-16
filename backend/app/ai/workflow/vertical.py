"""Vertical workflow wiring executed inside the ARQ worker (WP-REC-03F).

This module owns the complete long-running workflow execution sequence:

1. Load the durable run and related production plan.
2. Generation-guarded PENDING → RUNNING transition (D6 §5).
3. Deterministic risk calculation, snapshotted as a durable
   ``deterministic_calculation`` workflow step (AT-012 complete-trace
   remediation).
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

- The deterministic risk result is snapshotted into a durable
  ``deterministic_calculation`` workflow step immediately after the risk
  engine succeeds and before retrieval/provider processing. The snapshot
  is the point-in-time result and is never recomputed from later mutable
  plan/BOM/inventory/purchase-order state.

- No secrets are exposed in error messages, logs, or responses.
- Correlation ID is propagated through all steps.
"""

from __future__ import annotations

import json
import time
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
from app.ai.rag.orchestration import (
    WORKFLOW_TOP_K,
    FabricatedCitationError,
    build_citation_allow_list,
    build_per_risk_citation_allow_lists,
    build_retrieval_query_text,
    serialize_retrieval_context,
    validate_per_risk_sources,
)
from app.ai.rag.retriever import RetrievalResult, RetrievalService
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.prompts import build_system_prompt
from app.ai.workflow.schema_validator import (
    StructuredOutputValidationError,
    validate_structured_output,
)
from app.ai.workflow.state_machine import WorkflowState
from app.core.logging import get_logger
from app.models.production import ProductionPlan
from app.models.user import User, UserRole
from app.models.workflow import (
    Recommendation,
    WorkflowAuthorizationRecord,
    WorkflowRun,
    WorkflowStep,
)
from app.schemas.recommendation import (
    RECOMMENDATION_SCHEMA_VERSION,
    RecommendationData,
)
from app.services.embedding_provider import EmbeddingProvider
from app.services.risk_engine import analyze_plan

_logger = get_logger(__name__)

# Safe error codes for step-level recording.
_ERROR_CODE_PROVIDER_TRANSIENT = "PROVIDER_TRANSIENT"
_ERROR_CODE_PROVIDER_PERMANENT = "PROVIDER_PERMANENT"
_ERROR_CODE_VALIDATION = "VALIDATION_FAILED"
_ERROR_CODE_INTERNAL = "INTERNAL_ERROR"
_ERROR_CODE_RETRIEVAL = "RETRIEVAL_FAILED"

# Authoritative Recommendation JSON Schema passed through the provider
# contract for capability-aware structured output (§6). Computed once from
# the wire schema (deterministic, no side effects). Server-side validation
# remains authoritative regardless of the provider's structured-output mode.
RECOMMENDATION_JSON_SCHEMA: dict[str, Any] = RecommendationData.model_json_schema()


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


async def _resolve_effective_role_ids(
    session: AsyncSession,
    run_id: UUID,
    dispatch_generation: int,
) -> set[UUID] | None:
    """Resolve the effective role IDs for a dispatch generation (M1).

    Implements the WP-REC-05 M1 worker-execution contract: load the
    authorization record for the exact claimed dispatch generation, resolve
    the user's currently active role UUIDs, and compute
    ``effective_role_ids = captured_role_snapshot ∩ current_role_ids``.

    Returns ``None`` to signal a fail-closed authorization failure in any
    of the M1 fail-closed conditions: authorization record absent,
    generation mismatch, user absent/deleted/disabled, malformed captured
    snapshot, current-role resolution failure, or empty effective role set.

    Args:
        session: Async database session.
        run_id: Workflow run UUID.
        dispatch_generation: The exact dispatch generation to authorize.

    Returns:
        The non-empty effective role-ID set, or ``None`` if the
        authorization context must fail closed.
    """
    result = await session.execute(
        select(WorkflowAuthorizationRecord).where(
            WorkflowAuthorizationRecord.run_id == run_id,
            WorkflowAuthorizationRecord.dispatch_generation
            == dispatch_generation,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return None

    user_result = await session.execute(
        select(User).where(User.id == record.user_id)
    )
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None

    try:
        captured_role_ids = {
            UUID(raw) for raw in (record.role_snapshot or [])
        }
    except (TypeError, ValueError, AttributeError):
        return None

    current_result = await session.execute(
        select(UserRole.role_id).where(UserRole.user_id == record.user_id)
    )
    current_role_ids: set[UUID] = {
        UUID(str(row[0])) for row in current_result.fetchall()
    }

    effective = captured_role_ids & current_role_ids
    if not effective:
        return None
    return effective


async def execute_workflow(
    *,
    session: AsyncSession,
    provider: ChatProvider,
    embedding_provider: EmbeddingProvider,
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
        embedding_provider: EmbeddingProvider instance used for
            server-derived retrieval query embeddings (WP-REC-05).
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
    risk_items: list[dict[str, Any]] = []
    try:
        risks = await analyze_plan(session, plan_code)
        risk_items = [
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
        ]
        risk_data_json = json.dumps(risk_items, default=str)
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

    # 4.1 Snapshot the deterministic risk result as a durable
    #     ``deterministic_calculation`` workflow step (AT-012 complete-trace
    #     remediation, item 2). The snapshot is the point-in-time result
    #     captured immediately after analyze_plan succeeds and before
    #     retrieval/provider processing; it is never recomputed from later
    #     mutable plan/BOM/inventory/purchase-order state. The emit-once
    #     guard applies ONLY to this new step: on retry the original snapshot
    #     is preserved and never overwritten or duplicated. The legacy
    #     append-on-retry behavior of retrieval/provider_call/validation is
    #     unaffected.
    dc_existing = await session.execute(
        select(WorkflowStep.id).where(
            WorkflowStep.run_id == run.id,
            WorkflowStep.step_name == "deterministic_calculation",
        )
    )
    if dc_existing.scalar_one_or_none() is None:
        dc_step = WorkflowStep(
            run_id=run.id,
            correlation_id=run.correlation_id,
            seq=await engine._next_step_seq(run.id),
            step_name="deterministic_calculation",
            status="completed",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            step_metadata={
                "plan_code": plan_code,
                "risk_count": len(risks),
                "risks": [
                    {
                        "risk_id": item["risk_id"],
                        "component_code": item["component_code"],
                        "severity": item["severity"],
                        "shortage": item["shortage"],
                    }
                    for item in risk_items
                ],
            },
        )
        session.add(dc_step)
        await session.flush()

    # 4.5 Retrieval orchestration (WP-REC-05) — inserted after deterministic
    #     risk calculation and before prompt construction. Resolves the
    #     generation-specific authorization context, computes
    #     effective_role_ids, performs bounded per-risk retrieval, and
    #     builds the citation allow-list and prompt context.
    retrieval_start = time.monotonic()
    effective_role_ids = await _resolve_effective_role_ids(
        session, run.id, queued_generation
    )

    retrieval_results: list[RetrievalResult] = []
    citation_allow_list: frozenset[tuple[str, str, UUID]] = frozenset()
    results_by_risk: dict[str, list[RetrievalResult]] = {}
    per_risk_allow_lists: dict[str, frozenset[tuple[str, str, UUID]]] = {}
    retrieval_context_json = "[]"

    if effective_role_ids is None:
        # Fail-closed authorization failure (M1/DEC-046): record absent,
        # generation mismatch, user absent/deleted/disabled, malformed
        # snapshot, or empty effective role set. Retrieval is not executed
        # and no Recommendation is created.
        failed_step = WorkflowStep(
            run_id=run.id,
            correlation_id=run.correlation_id,
            seq=await engine._next_step_seq(run.id),
            step_name="retrieval",
            status="failed",
            error_code=_ERROR_CODE_RETRIEVAL,
            error_detail="AUTHORIZATION_CONTEXT_EMPTY",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        session.add(failed_step)
        await session.flush()

        await engine.transition_to_failed_retrieval(
            run,
            error_code=_ERROR_CODE_RETRIEVAL,
            error_detail="AUTHORIZATION_CONTEXT_EMPTY",
        )
        _logger.warning(
            "workflow.vertical.retrieval_authorization_empty",
            run_id=str(run_id),
            plan_code=plan_code,
            dispatch_generation=queued_generation,
        )
        return VerticalExecutionResult(
            WorkflowState.FAILED_RETRIEVAL.value, False
        )

    try:
        retrieval_service = RetrievalService()
        seen: set[tuple[UUID, UUID, UUID]] = set()
        for risk_item in risk_items:
            risk_id = risk_item["risk_id"]
            query_text = build_retrieval_query_text(risk_item)
            query_embedding = (
                await embedding_provider.embed_text([query_text])
            )[0]
            risk_results = await retrieval_service.retrieve(
                session=session,
                query_embedding=query_embedding,
                allowed_role_ids=effective_role_ids,
                top_k=WORKFLOW_TOP_K,
            )
            # Preserve per-risk retrieval provenance (§7): each risk keeps its
            # own results so its allow-list is authoritative for that risk only.
            results_by_risk[risk_id] = list(risk_results)
            for retrieved in risk_results:
                identity = (
                    retrieved.document_id,
                    retrieved.version_id,
                    retrieved.chunk_id,
                )
                if identity not in seen:
                    seen.add(identity)
                    retrieval_results.append(retrieved)
    except Exception:
        # Retrieval execution failure → FAILED_RETRIEVAL (M2). No
        # Recommendation is created for the failed attempt.
        failed_step = WorkflowStep(
            run_id=run.id,
            correlation_id=run.correlation_id,
            seq=await engine._next_step_seq(run.id),
            step_name="retrieval",
            status="failed",
            error_code=_ERROR_CODE_RETRIEVAL,
            error_detail="RETRIEVAL_FAILED",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
        )
        session.add(failed_step)
        await session.flush()

        await engine.transition_to_failed_retrieval(
            run,
            error_code=_ERROR_CODE_RETRIEVAL,
            error_detail="RETRIEVAL_FAILED",
        )
        _logger.warning(
            "workflow.vertical.retrieval_failed",
            run_id=str(run_id),
            plan_code=plan_code,
            dispatch_generation=queued_generation,
        )
        return VerticalExecutionResult(
            WorkflowState.FAILED_RETRIEVAL.value, False
        )

    retrieval_latency_ms = int((time.monotonic() - retrieval_start) * 1000)
    citation_allow_list = build_citation_allow_list(retrieval_results)
    per_risk_allow_lists = build_per_risk_citation_allow_lists(results_by_risk)
    retrieval_context_json = serialize_retrieval_context(retrieval_results)

    # Record the successful retrieval step (§I observability contract).
    retrieval_step = WorkflowStep(
        run_id=run.id,
        correlation_id=run.correlation_id,
        seq=await engine._next_step_seq(run.id),
        step_name="retrieval",
        status="completed",
        latency_ms=retrieval_latency_ms,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        step_metadata={
            "result_count": len(retrieval_results),
            "accessible_document_count": len(
                {r.document_id for r in retrieval_results}
            ),
            "citation_count": len(citation_allow_list),
            "citation_ids": sorted(
                [
                    {
                        "document_id": doc_id,
                        "version": version,
                        "chunk_id": str(chunk_id),
                    }
                    for doc_id, version, chunk_id in citation_allow_list
                ],
                key=lambda c: (c["document_id"], c["version"], c["chunk_id"]),
            ),
            "risk_ids_queried": [item["risk_id"] for item in risk_items],
        },
    )
    session.add(retrieval_step)
    await session.flush()

    _logger.info(
        "workflow.vertical.retrieval_completed",
        run_id=str(run_id),
        plan_code=plan_code,
        result_count=len(retrieval_results),
        accessible_document_count=len(
            {r.document_id for r in retrieval_results}
        ),
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
        retrieval_context=retrieval_context_json,
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
            schema=RECOMMENDATION_JSON_SCHEMA,
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

        # 6.5 Citation-integrity validation (§7): every persisted Source is
        #     validated against ITS OWN risk's allow-list (per-risk, not
        #     run-global). A fabricated, cross-risk, or duplicate citation is a
        #     validation failure (never a retrieval execution failure, per
        #     M2). Raw model output and the offending identity are never
        #     logged or returned.
        try:
            for rec_risk in recommendation_data.risks:
                validate_per_risk_sources(
                    rec_risk.sources,
                    risk_id=rec_risk.risk_id,
                    allow_lists_by_risk=per_risk_allow_lists,
                )
        except FabricatedCitationError as exc:
            step_record = WorkflowStep(
                run_id=run.id,
                correlation_id=run.correlation_id,
                seq=await engine._next_step_seq(run.id),
                step_name="validation",
                status="failed",
                error_code=_ERROR_CODE_VALIDATION,
                error_detail=type(exc).__name__,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
            )
            session.add(step_record)
            await session.flush()

            await engine.transition_to_failed_validation(
                run,
                error_code=_ERROR_CODE_VALIDATION,
                error_detail=type(exc).__name__,
            )
            _logger.warning(
                "workflow.vertical.citation_validation_failed",
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

        # 7.5 Record the recommendation step (AT-012 complete-trace
        #     remediation, item 6), immediately after the Recommendation row
        #     is flushed and validation has succeeded. It binds to the same
        #     run_id and correlation_id and carries only the safe minimum
        #     metadata — never the full recommendation payload. Because
        #     ``recommendations.run_id`` is unique and retry-eligible states
        #     never persist a recommendation, this step is emitted exactly
        #     once per run with no additional guard.
        recommendation_step = WorkflowStep(
            run_id=run.id,
            correlation_id=run.correlation_id,
            seq=await engine._next_step_seq(run.id),
            step_name="recommendation",
            status="completed",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            step_metadata={
                "recommendation_id": str(recommendation.id),
                "plan_id": str(run.plan_id),
                "schema_version": RECOMMENDATION_SCHEMA_VERSION,
                "status": "VALIDATED",
                "risk_ids": [risk.risk_id for risk in recommendation_data.risks],
                "action_types": sorted(
                    {
                        action.action_type
                        for risk in recommendation_data.risks
                        for action in risk.recommended_actions
                    }
                ),
                "requires_approval": any(
                    action.requires_approval
                    for risk in recommendation_data.risks
                    for action in risk.recommended_actions
                ),
            },
        )
        session.add(recommendation_step)
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
