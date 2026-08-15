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
from app.schemas.audit import AuditEventListResponse, AuditEventResponse
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
