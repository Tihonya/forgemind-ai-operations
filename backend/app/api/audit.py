"""Read-only audit-event API (WP-REC-04B).

Exposes the Phase 6 audit trail required by AT-012 via two read
endpoints:

- ``GET /audit-events`` — paginated list, deterministic ordering.
- ``GET /audit-events/{event_id}`` — single event detail.

There is deliberately NO POST/PUT/PATCH/DELETE endpoint: audit events are
created only through the internal append-only service
(``app/services/audit_service.py``) invoked by future Phase 6 services
(WP-REC-04A approval, WP-REC-04C procurement).

Authorization (canonical roles, DEC-052 M1):
- ``AUDITOR``: read-only audit access.
- ``AI_ADMINISTRATOR``: administrative read access.
- ``PRODUCTION_MANAGER``, ``PROCUREMENT_SPECIALIST``, ``ENGINEER``: no
  audit-read authority.
- ``platform_admin`` does not exist in the canonical role model.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database import get_async_session
from app.dependencies import require_role
from app.models.audit import AuditEvent
from app.models.workflow import WorkflowRun, WorkflowStep
from app.schemas.audit import AuditEventListResponse, AuditEventResponse
from app.schemas.trace import (
    TRACE_CATEGORY_ORDER,
    AuditTraceResponse,
    TraceCategory,
    TraceItem,
    sanitize_trace_summary,
)
from app.services.auth_service import AuthenticatedUser

router = APIRouter(tags=["Audit"])
logger = get_logger("app.api.audit")

# Canonical read roles (DEC-052 M1, decomposition §3.6): the auditor is
# the read-only audit role; the AI administrator has administrative read
# access. No other canonical role may read the audit log.
_AUDIT_READ_ROLES: set[str] = {"AUDITOR", "AI_ADMINISTRATOR"}


@router.get(
    "/audit-events/{event_id}",
    response_model=AuditEventResponse,
    status_code=status.HTTP_200_OK,
)
async def get_audit_event(
    event_id: UUID,
    current_user: AuthenticatedUser = Depends(require_role(_AUDIT_READ_ROLES)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> AuditEventResponse:
    """Return a single audit event by ID.

    Raises:
        HTTPException(401): Unauthenticated.
        HTTPException(403): Missing AUDITOR/AI_ADMINISTRATOR role.
        HTTPException(404): Event not found.
    """
    result = await session.execute(
        select(AuditEvent).where(AuditEvent.id == event_id)
    )
    event = result.scalars().one_or_none()

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "audit_event_not_found", "event_id": str(event_id)},
        )

    return AuditEventResponse.model_validate(event)


@router.get(
    "/audit-events",
    response_model=AuditEventListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_audit_events(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(require_role(_AUDIT_READ_ROLES)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> AuditEventListResponse:
    """Return a paginated list of audit events.

    Ordering: created_at DESC, id DESC (deterministic tie-breaker).

    Raises:
        HTTPException(401): Unauthenticated.
        HTTPException(403): Missing AUDITOR/AI_ADMINISTRATOR role.
    """
    total_stmt = select(func.count(AuditEvent.id))
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(AuditEvent)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    events = result.scalars().all()

    items = [AuditEventResponse.model_validate(event) for event in events]

    return AuditEventListResponse(items=items, limit=limit, offset=offset, total=total)


# ---------------------------------------------------------------------------
# Normalized nine-item trace (AT-012 complete-trace remediation)
# ---------------------------------------------------------------------------

# Phase 5 ``workflow_steps.step_name`` → canonical trace category.
_STEP_NAME_TO_CATEGORY: dict[str, TraceCategory] = {
    "user_action": "user_action",
    "deterministic_calculation": "deterministic_calculation",
    "retrieval": "retrieval",
    "provider_call": "model_call",
    "validation": "structured_validation",
    "recommendation": "recommendation",
}

# Phase 6 ``audit_events.event_type`` → canonical trace category. The
# attempt/failure event types are deliberately NOT part of the nine-item
# surface and are therefore not mapped (they remain readable via the raw
# /audit-events endpoints).
_EVENT_TYPE_TO_CATEGORY: dict[str, TraceCategory] = {
    "APPROVAL_REQUEST_CREATED": "approval_request",
    "APPROVAL_APPROVED": "human_decision",
    "APPROVAL_REJECTED": "human_decision",
    "PROCUREMENT_TASK_CREATED": "write_action",
}


def _canonical_step(steps: list[WorkflowStep]) -> WorkflowStep | None:
    """Select the canonical step for a category.

    Prefers ``completed`` steps; among those, the highest ``seq`` (the latest
    successful attempt). If no step completed, falls back to the highest-seq
    step of any status so a failed attempt is represented truthfully. This is
    deterministic and never deletes or rewrites the underlying attempts.
    """
    if not steps:
        return None
    completed = [step for step in steps if step.status == "completed"]
    pool = completed or steps
    return max(pool, key=lambda step: step.seq)


def _canonical_event(events: list[AuditEvent]) -> AuditEvent | None:
    """Select the canonical event for a category (latest, then id)."""
    if not events:
        return None
    return max(events, key=lambda event: (event.created_at, event.id))


def _step_actor(step: WorkflowStep) -> str | None:
    """Return the human actor for a ``user_action`` step, else None."""
    metadata = step.step_metadata or {}
    username = metadata.get("username")
    return username if isinstance(username, str) else None


def _build_step_item(
    category: TraceCategory,
    category_order: int,
    step: WorkflowStep,
) -> TraceItem:
    return TraceItem(
        category=category,
        category_order=category_order,
        occurred_at=step.started_at,
        source="workflow_step",
        source_id=step.id,
        actor=_step_actor(step),
        entity_type=None,
        entity_id=None,
        risk_id=None,
        summary=sanitize_trace_summary(step.step_metadata),
    )


def _build_event_item(
    category: TraceCategory,
    category_order: int,
    event: AuditEvent,
) -> TraceItem:
    summary_source = (
        event.after_summary if event.after_summary is not None else event.before_summary
    )
    return TraceItem(
        category=category,
        category_order=category_order,
        occurred_at=event.created_at,
        source="audit_event",
        source_id=event.id,
        actor=event.actor_username,
        entity_type=event.entity_type,
        entity_id=str(event.entity_id) if event.entity_id is not None else None,
        risk_id=event.risk_id,
        summary=sanitize_trace_summary(summary_source),
    )


@router.get(
    "/audit-trace/{correlation_id}",
    response_model=AuditTraceResponse,
    status_code=status.HTTP_200_OK,
)
async def get_audit_trace(
    correlation_id: UUID,
    current_user: AuthenticatedUser = Depends(require_role(_AUDIT_READ_ROLES)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> AuditTraceResponse:
    """Return the normalized nine-item trace for a correlation ID.

    Read-only. Combines Phase 5 ``workflow_steps`` (items 1-6) with Phase 6
    ``audit_events`` (items 7-9) into a single correlation lineage. A
    completed approved run exposes exactly one canonical item per category,
    ordered 1-9. Legacy runs expose ``complete=false`` with the exact missing
    categories; no category is ever fabricated or backfilled.

    Raises:
        HTTPException(401): Unauthenticated.
        HTTPException(403): Missing AUDITOR/AI_ADMINISTRATOR role.
        HTTPException(404): Unknown correlation (audit_trace_not_found).
    """
    run_result = await session.execute(
        select(WorkflowRun).where(WorkflowRun.correlation_id == correlation_id)
    )
    run = run_result.scalars().one_or_none()

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "audit_trace_not_found"},
        )

    steps_result = await session.execute(
        select(WorkflowStep).where(WorkflowStep.run_id == run.id)
    )
    steps = steps_result.scalars().all()

    events_result = await session.execute(
        select(AuditEvent).where(AuditEvent.correlation_id == correlation_id)
    )
    events = events_result.scalars().all()

    steps_by_category: dict[TraceCategory, list[WorkflowStep]] = {}
    for step in steps:
        category = _STEP_NAME_TO_CATEGORY.get(step.step_name)
        if category is not None:
            steps_by_category.setdefault(category, []).append(step)

    events_by_category: dict[TraceCategory, list[AuditEvent]] = {}
    for event in events:
        category = _EVENT_TYPE_TO_CATEGORY.get(event.event_type)
        if category is not None:
            events_by_category.setdefault(category, []).append(event)

    items: list[TraceItem] = []
    for order, category in enumerate(TRACE_CATEGORY_ORDER, start=1):
        if category in steps_by_category:
            canonical_step = _canonical_step(steps_by_category[category])
            if canonical_step is not None:
                items.append(_build_step_item(category, order, canonical_step))
        elif category in events_by_category:
            canonical_event = _canonical_event(events_by_category[category])
            if canonical_event is not None:
                items.append(_build_event_item(category, order, canonical_event))

    present = {item.category for item in items}
    missing_categories = [
        category for category in TRACE_CATEGORY_ORDER if category not in present
    ]

    # AT-012 complete-trace remediation (R-1): classify legacy vs current
    # incompleteness from durable capture markers, never from timestamps.
    # A run is legacy only when it carries NEITHER post-remediation marker
    # (user_action, deterministic_calculation). A current PENDING/RUNNING/
    # FAILED_* run carries at least one marker, so it is never mislabelled
    # as pre-remediation.
    is_legacy = (
        "user_action" not in present
        and "deterministic_calculation" not in present
    )

    return AuditTraceResponse(
        correlation_id=run.correlation_id,
        workflow_run_id=run.id,
        triggered_by=run.triggered_by,
        final_state=run.state,
        complete=not missing_categories,
        is_legacy=is_legacy,
        missing_categories=list(missing_categories),
        items=items,
    )
