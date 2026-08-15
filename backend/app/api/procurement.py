"""Procurement-task API (WP-REC-04C).

Backend REST API for the idempotent synthetic procurement-task package:

- ``POST /procurement-tasks`` — create exactly one procurement task from an
  ``APPROVED`` approval request (PROCUREMENT_SPECIALIST, the approving
  specialist only). This is the single controlled mutation route; there is
  no external procurement execution endpoint and no update/delete route.
- ``GET /procurement-tasks`` — paginated list.
- ``GET /procurement-tasks/{task_id}`` — single task detail.

Authorization (canonical roles, DEC-052 M1; decomposition §3.6):

- Execute: ``PROCUREMENT_SPECIALIST`` only, and only the specialist who
  approved the request (``decided_by`` equals the caller). Any other role
  receives 403 before any entity lookup (no existence disclosure).
- Read (list + detail): ``PRODUCTION_MANAGER`` (own tasks),
  ``PROCUREMENT_SPECIALIST`` (tasks it approved), and ``AI_ADMINISTRATOR``
  (administrative read of all tasks). Row scope is enforced at the
  service/query boundary; scoped-out and nonexistent IDs are
  indistinguishable (404).
- ``ENGINEER`` and ``AUDITOR`` have no procurement authority.
- The unsupported ``platform_admin`` role does not exist.

The executable ``component_code`` and ``quantity`` are never accepted from
the client; they are re-read from the immutable WP-REC-04A approval
snapshot and validated against the canonical binding hash.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database import get_async_session
from app.dependencies import require_role
from app.models.procurement import ProcurementTask
from app.schemas.procurement import (
    ProcurementTaskCreate,
    ProcurementTaskListResponse,
    ProcurementTaskResponse,
)
from app.services.auth_service import AuthenticatedUser
from app.services.procurement_service import (
    ApprovalNotApprovedError,
    ApprovalRejectedError,
    ApprovalRequestNotFoundError,
    ApproverMismatchError,
    BindingMismatchError,
    ProcurementService,
    ProcurementServiceError,
    ProcurementTaskNotFoundError,
)

router = APIRouter(tags=["Procurement"])
logger = get_logger("app.api.procurement")

# Canonical roles (decomposition §3.6): the procurement specialist executes
# the controlled action; manager/specialist/administrator have scoped read.
_EXECUTOR_ROLE: set[str] = {"PROCUREMENT_SPECIALIST"}
_READ_ROLES: set[str] = {"PRODUCTION_MANAGER", "PROCUREMENT_SPECIALIST", "AI_ADMINISTRATOR"}

#: Unique-constraint name that is the exactly-once backstop (task §5).
_UQ_TASK_PER_APPROVAL = "uq_procurement_tasks_approval_request_id"


def _map_service_error(exc: ProcurementServiceError) -> HTTPException:
    """Map a procurement-service domain error to the repository-standard HTTP error."""
    if isinstance(exc, ApprovalRequestNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "approval_request_not_found"},
        )
    if isinstance(exc, ApprovalNotApprovedError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "approval_request_not_approved"},
        )
    if isinstance(exc, ApprovalRejectedError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "approval_request_rejected"},
        )
    if isinstance(exc, ApproverMismatchError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "approver_mismatch"},
        )
    if isinstance(exc, BindingMismatchError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "binding_mismatch"},
        )
    if isinstance(exc, ProcurementTaskNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "procurement_task_not_found"},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": "procurement_service_error"},
    )


def _violated_constraint(exc: IntegrityError) -> str | None:
    """Return the violated constraint name, or ``None`` if unknown.

    Handles the asyncpg (``.constraint_name``) and psycopg2
    (``.diag.constraint_name``) driver attribute shapes without importing
    driver-specific types.
    """
    orig = exc.orig
    name = getattr(orig, "constraint_name", None)
    if name is None:
        diag = getattr(orig, "diag", None)
        name = getattr(diag, "constraint_name", None)
    if name is None:
        text_value = str(orig)
        if _UQ_TASK_PER_APPROVAL in text_value:
            return _UQ_TASK_PER_APPROVAL
    return name


@router.post(
    "/procurement-tasks",
    response_model=ProcurementTaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_procurement_task(
    body: ProcurementTaskCreate,
    current_user: AuthenticatedUser = Depends(require_role(_EXECUTOR_ROLE)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> ProcurementTaskResponse:
    """Create exactly one procurement task from an APPROVED request.

    Requires PROCUREMENT_SPECIALIST (the approving specialist). A repeated
    identical execution returns the already-created task (200) rather than
    creating a second one; a changed-parameter or different-binding attempt
    fails closed. The task and its audit events commit atomically.

    Raises:
        HTTPException(401): unauthenticated.
        HTTPException(403): not PROCUREMENT_SPECIALIST, or not the approver.
        HTTPException(404): approval request not found.
        HTTPException(409): approval request not APPROVED (pending/rejected).
        HTTPException(422): binding hash/parameter mismatch.
        HTTPException(500): internal error.
    """
    service = ProcurementService(session)
    try:
        task = await service.execute_for_approval(
            approval_request_id=body.approval_request_id,
            actor=current_user,
        )
        await session.commit()
    except ProcurementServiceError as exc:
        # Fail-closed domain outcome: the service appended the attempt and
        # failure audit events before raising. Commit them so the rejection
        # is audited (decomposition §3.9), then return the mapped HTTP error.
        await session.commit()
        raise _map_service_error(exc) from None
    except IntegrityError as exc:
        await session.rollback()
        if _violated_constraint(exc) == _UQ_TASK_PER_APPROVAL:
            # Exactly-once backstop: a uniqueness race on the approval.
            # Re-read the authoritative already-created task and return it.
            existing = (
                await session.execute(
                    select(ProcurementTask).where(
                        ProcurementTask.approval_request_id == body.approval_request_id
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return ProcurementTaskResponse.model_validate(existing)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "procurement_service_error"},
        ) from None

    return ProcurementTaskResponse.model_validate(task)


@router.get(
    "/procurement-tasks",
    response_model=ProcurementTaskListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_procurement_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(require_role(_READ_ROLES)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> ProcurementTaskListResponse:
    """Return a caller-scoped paginated list of procurement tasks.

    Scope (decomposition §3.6): PRODUCTION_MANAGER sees its own tasks;
    PROCUREMENT_SPECIALIST sees the tasks it approved; AI_ADMINISTRATOR
    sees all. Ordering: created_at DESC, id DESC.
    """
    service = ProcurementService(session)
    items, total = await service.list_tasks(
        user=current_user, limit=limit, offset=offset
    )
    return ProcurementTaskListResponse(
        items=[ProcurementTaskResponse.model_validate(task) for task in items],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.get(
    "/procurement-tasks/{task_id}",
    response_model=ProcurementTaskResponse,
    status_code=status.HTTP_200_OK,
)
async def get_procurement_task(
    task_id: UUID,
    current_user: AuthenticatedUser = Depends(require_role(_READ_ROLES)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> ProcurementTaskResponse:
    """Return a single procurement task within the caller's scope.

    A task outside the caller's scope returns 404 exactly as a nonexistent
    ID does, so scoped-out and missing IDs are indistinguishable.
    """
    service = ProcurementService(session)
    try:
        task = await service.get_task(user=current_user, task_id=task_id)
    except ProcurementServiceError as exc:
        raise _map_service_error(exc) from None
    return ProcurementTaskResponse.model_validate(task)
