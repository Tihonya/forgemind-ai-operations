"""Approval-request API (WP-REC-04A).

Backend REST API for the bounded approval-request package:

- ``POST /approval-requests`` — create a PENDING approval request
  (PRODUCTION_MANAGER).
- ``GET /approval-requests`` — paginated list.
- ``GET /approval-requests/{request_id}`` — single request detail.
- ``POST /approval-requests/{request_id}/approve`` — approve (PROCUREMENT_SPECIALIST).
- ``POST /approval-requests/{request_id}/reject`` — reject (PROCUREMENT_SPECIALIST).

Authorization (canonical roles, DEC-052 M1; decomposition §3.6):

- Create: ``PRODUCTION_MANAGER`` only.
- Approve/reject: ``PROCUREMENT_SPECIALIST`` only; self-decision fails
  closed (requester/approver separation).
- Read (list + detail): ``PRODUCTION_MANAGER`` (own requests),
  ``PROCUREMENT_SPECIALIST`` (PENDING requests), and ``AI_ADMINISTRATOR``
  (administrative read of all requests) — decomposition §3.6. Row scope is
  enforced at the service/query boundary; scoped-out and nonexistent IDs are
  indistinguishable (404).
- ``ENGINEER`` and ``AUDITOR`` have no Phase 6 approval authority.

There is no procurement-execution route (owned by WP-REC-04C) and no
public mutation path. Authorization runs as a FastAPI dependency before
the endpoint body, so a wrong-role request receives 403 before any
entity-existence lookup (no ID-existence disclosure).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database import get_async_session
from app.dependencies import require_role
from app.schemas.approval import (
    ApprovalRequestCreate,
    ApprovalRequestListResponse,
    ApprovalRequestResponse,
    DecisionRequest,
)
from app.services.approval_service import (
    ApprovalRequestNotFoundError,
    ApprovalRequestNotPendingError,
    ApprovalService,
    ApprovalServiceError,
    DuplicateActiveApprovalError,
    RecommendationContentInvalidError,
    RecommendationIneligibleError,
    RecommendationNotFoundError,
    RiskActionParametersMismatchError,
    SelfDecisionError,
)
from app.services.auth_service import AuthenticatedUser

router = APIRouter(tags=["Approval"])
logger = get_logger("app.api.approval")

# Canonical read roles (decomposition §3.6): manager and procurement
# specialist inspect requests; AI administrator has administrative read.
_READ_ROLES: set[str] = {"PRODUCTION_MANAGER", "PROCUREMENT_SPECIALIST", "AI_ADMINISTRATOR"}
_MANAGER_ROLE: set[str] = {"PRODUCTION_MANAGER"}
_APPROVER_ROLE: set[str] = {"PROCUREMENT_SPECIALIST"}


def _map_service_error(exc: ApprovalServiceError) -> HTTPException:
    """Map an approval-service domain error to the repository-standard HTTP error."""
    if isinstance(exc, RecommendationNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "recommendation_not_found"},
        )
    if isinstance(exc, RecommendationContentInvalidError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "invalid_recommendation_content"},
        )
    if isinstance(exc, RecommendationIneligibleError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": exc.code},
        )
    if isinstance(exc, RiskActionParametersMismatchError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "risk_action_parameters_mismatch"},
        )
    if isinstance(exc, ApprovalRequestNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "approval_request_not_found"},
        )
    if isinstance(exc, ApprovalRequestNotPendingError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "approval_request_not_pending"},
        )
    if isinstance(exc, SelfDecisionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": "self_decision_forbidden"},
        )
    if isinstance(exc, DuplicateActiveApprovalError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "approval_request_duplicate"},
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail={"error": "approval_service_error"},
    )


@router.post(
    "/approval-requests",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_approval_request(
    body: ApprovalRequestCreate,
    current_user: AuthenticatedUser = Depends(require_role(_MANAGER_ROLE)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> ApprovalRequestResponse:
    """Create a PENDING approval request bound to an eligible action.

    Requires PRODUCTION_MANAGER. The executable parameters
    (``component_code`` and ``quantity``) are verified against the
    deterministic risk engine and the action binding (snapshot + SHA-256
    hash) is derived from the persisted recommendation; the request and its
    audit event commit atomically.

    Raises:
        HTTPException(401): unauthenticated.
        HTTPException(403): not PRODUCTION_MANAGER.
        HTTPException(404): recommendation not found.
        HTTPException(409): duplicate active approval request.
        HTTPException(422): ineligible action input or risk-parameter
            mismatch.
        HTTPException(500): invalid recommendation content or internal error.
    """
    service = ApprovalService(session)
    try:
        approval = await service.create_request(
            recommendation_id=body.recommendation_id,
            risk_id=body.risk_id,
            action_type=body.action_type,
            component_code=body.component_code,
            quantity=body.quantity,
            requester=current_user,
        )
        await session.commit()
    except ApprovalServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "approval_request_duplicate"},
        ) from None

    return ApprovalRequestResponse.model_validate(approval)


@router.get(
    "/approval-requests",
    response_model=ApprovalRequestListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_approval_requests(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(require_role(_READ_ROLES)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> ApprovalRequestListResponse:
    """Return a caller-scoped paginated list of approval requests.

    Scope (decomposition §3.6): PRODUCTION_MANAGER sees its own requests;
    PROCUREMENT_SPECIALIST sees PENDING requests; AI_ADMINISTRATOR sees all.

    Ordering: requested_at DESC, id DESC (deterministic tie-breaker).
    """
    service = ApprovalService(session)
    items, total = await service.list_requests(
        user=current_user, limit=limit, offset=offset
    )
    return ApprovalRequestListResponse(
        items=[
            ApprovalRequestResponse.model_validate(request) for request in items
        ],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.get(
    "/approval-requests/{request_id}",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_200_OK,
)
async def get_approval_request(
    request_id: UUID,
    current_user: AuthenticatedUser = Depends(require_role(_READ_ROLES)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> ApprovalRequestResponse:
    """Return a single approval request within the caller's scope.

    A request outside the caller's scope returns 404 exactly as a
    nonexistent ID does, so scoped-out and missing IDs are indistinguishable.
    """
    service = ApprovalService(session)
    try:
        approval = await service.get_request(user=current_user, request_id=request_id)
    except ApprovalServiceError as exc:
        raise _map_service_error(exc) from None
    return ApprovalRequestResponse.model_validate(approval)


@router.post(
    "/approval-requests/{request_id}/approve",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_200_OK,
)
async def approve_approval_request(
    request_id: UUID,
    body: DecisionRequest,
    current_user: AuthenticatedUser = Depends(require_role(_APPROVER_ROLE)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> ApprovalRequestResponse:
    """Approve a PENDING approval request (PROCUREMENT_SPECIALIST).

    Self-approval fails closed. The decision and its audit event commit
    atomically. No procurement task is created (owned by WP-REC-04C).
    """
    service = ApprovalService(session)
    try:
        approval = await service.approve_request(
            request_id=request_id,
            approver=current_user,
            comment=body.comment,
        )
        await session.commit()
    except ApprovalServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None

    return ApprovalRequestResponse.model_validate(approval)


@router.post(
    "/approval-requests/{request_id}/reject",
    response_model=ApprovalRequestResponse,
    status_code=status.HTTP_200_OK,
)
async def reject_approval_request(
    request_id: UUID,
    body: DecisionRequest,
    current_user: AuthenticatedUser = Depends(require_role(_APPROVER_ROLE)),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> ApprovalRequestResponse:
    """Reject a PENDING approval request (PROCUREMENT_SPECIALIST).

    The rejection reason is persisted as ``decision_comment``. Self-decision
    fails closed. The decision and its audit event commit atomically. No
    procurement task is created.
    """
    service = ApprovalService(session)
    try:
        approval = await service.reject_request(
            request_id=request_id,
            approver=current_user,
            reason=body.comment,
        )
        await session.commit()
    except ApprovalServiceError as exc:
        await session.rollback()
        raise _map_service_error(exc) from None

    return ApprovalRequestResponse.model_validate(approval)
