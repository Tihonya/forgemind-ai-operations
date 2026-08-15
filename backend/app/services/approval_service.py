"""Approval-request service (WP-REC-04A).

Implements the bounded single-shot approval state machine, the immutable
action-binding hash, fail-closed authorization invariants, and atomic
audit-event emission through the WP-REC-04B ``AuditService``.

Contract (WP-REC-04-DEC §4 WP-REC-04A; DEC-052 G1/G3):

- Create: ``PRODUCTION_MANAGER`` only (enforced by the API role gate).
- Approve/reject: ``PROCUREMENT_SPECIALIST`` only (API role gate), and
  only when the decision actor differs from the requester (self-decision
  fails closed).
- Single-shot lifecycle ``PENDING → APPROVED | REJECTED``; a terminal
  request cannot be decided again.
- The request binds an immutable action snapshot and a deterministic
  SHA-256 binding hash over its canonical serialization.
- Creation and each decision emit the corresponding audit event in the
  same transaction as the business mutation.

Transaction ownership: this service operates within a caller-provided
``AsyncSession``, flushes, and never commits. The API endpoint owns
commit/rollback, so the business mutation and its audit event commit (or
roll back) atomically.

Deterministic and LLM-free: no provider, vendor, payment, or external
HTTP call is made anywhere in this module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_correlation_id
from app.core.correlation import generate_correlation_id, validate_correlation_id
from app.core.logging import get_logger
from app.models.approval import (
    ApprovalRequest,
    ApprovalStatus,
    compute_binding_hash,
)
from app.models.enums import AuditEntityType, AuditEventType
from app.models.workflow import Recommendation
from app.schemas.recommendation import RecommendationData, RecommendedAction
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedUser

logger = get_logger(__name__)

#: The only controlled action the MVP supports (DEC-052 G2/G3). Matches the
#: WP-REC-04C action allow-list; any other action type fails closed.
SUPPORTED_ACTION_TYPE = "CREATE_PROCUREMENT_TASK"


class ApprovalServiceError(Exception):
    """Base class for approval-service domain errors."""


class RecommendationNotFoundError(ApprovalServiceError):
    """The referenced recommendation does not exist."""


class RecommendationContentInvalidError(ApprovalServiceError):
    """The recommendation content fails the typed wire schema."""


class RecommendationIneligibleError(ApprovalServiceError):
    """The recommendation/action is ineligible for an approval request.

    ``code`` is a bounded, stable error code (``risk_not_found_in_recommendation``,
    ``action_not_found_in_recommendation``, ``action_not_requiring_approval``,
    ``unsupported_action_type``).
    """

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ApprovalRequestNotFoundError(ApprovalServiceError):
    """The approval request does not exist."""


class ApprovalRequestNotPendingError(ApprovalServiceError):
    """The approval request is not in PENDING state (already decided)."""


class SelfDecisionError(ApprovalServiceError):
    """The decision actor is the requester (separation of duties)."""


class DuplicateActiveApprovalError(ApprovalServiceError):
    """A PENDING approval request already exists for this action."""


def build_action_snapshot(
    *,
    recommendation: Recommendation,
    risk_id: str,
    action: RecommendedAction,
) -> dict[str, str]:
    """Build the immutable canonical action snapshot from a recommendation.

    The snapshot is a fixed, ordered set of string fields derived from the
    persisted recommendation at creation time. It contains no secrets and no
    mutable pointer — it is never recomputed from later recommendation state.
    """
    return {
        "action_type": action.action_type,
        "risk_id": risk_id,
        "title": action.title,
        "rationale": action.rationale,
        "workflow_run_id": str(recommendation.run_id),
        "recommendation_id": str(recommendation.id),
    }


class ApprovalService:
    """Bounded approval-request service (caller owns the transaction)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _resolve_correlation_id(correlation_id: str | UUID | None) -> UUID:
        """Resolve and validate a correlation ID for the business + audit event.

        Resolution order: explicit argument → bound request context → newly
        generated UUID v4. The result is validated as UUID v4 and shared by
        the approval-request row and its audit event (same correlation).
        """
        resolved = correlation_id
        if resolved is None:
            resolved = get_correlation_id()
        if resolved is None:
            resolved = generate_correlation_id()
        return UUID(validate_correlation_id(str(resolved)))

    async def create_request(
        self,
        *,
        recommendation_id: UUID,
        risk_id: str,
        action_type: str,
        requester: AuthenticatedUser,
        correlation_id: str | UUID | None = None,
    ) -> ApprovalRequest:
        """Create a PENDING approval request bound to an eligible action.

        Raises:
            RecommendationNotFoundError: no such recommendation.
            RecommendationContentInvalidError: content fails the wire schema.
            RecommendationIneligibleError: risk/action absent, action does not
                require approval, or unsupported action type.
            DuplicateActiveApprovalError: a PENDING request already exists
                for this action.
        """
        rec = (
            await self._session.execute(
                select(Recommendation).where(Recommendation.id == recommendation_id)
            )
        ).scalar_one_or_none()
        if rec is None:
            raise RecommendationNotFoundError()

        if rec.status != "VALIDATED" or rec.content is None:
            raise RecommendationIneligibleError("recommendation_not_validated")

        try:
            data = RecommendationData.model_validate(rec.content)
        except ValidationError as exc:
            raise RecommendationContentInvalidError() from exc

        risk_item = next((r for r in data.risks if r.risk_id == risk_id), None)
        if risk_item is None:
            raise RecommendationIneligibleError("risk_not_found_in_recommendation")

        action = next(
            (a for a in risk_item.recommended_actions if a.action_type == action_type),
            None,
        )
        if action is None:
            raise RecommendationIneligibleError("action_not_found_in_recommendation")

        if not action.requires_approval:
            raise RecommendationIneligibleError("action_not_requiring_approval")

        if action.action_type != SUPPORTED_ACTION_TYPE:
            raise RecommendationIneligibleError("unsupported_action_type")

        # Duplicate-active pre-check (defense-in-depth: the partial unique
        # index on (recommendation_id, risk_id, action_type) WHERE PENDING
        # is the race-safe backstop).
        existing = (
            await self._session.execute(
                select(ApprovalRequest.id).where(
                    ApprovalRequest.recommendation_id == recommendation_id,
                    ApprovalRequest.risk_id == risk_id,
                    ApprovalRequest.action_type == action_type,
                    ApprovalRequest.status == ApprovalStatus.PENDING.value,
                )
            )
        ).first()
        if existing is not None:
            raise DuplicateActiveApprovalError()

        snapshot = build_action_snapshot(
            recommendation=rec, risk_id=risk_id, action=action
        )
        binding_hash = compute_binding_hash(snapshot)
        corr = self._resolve_correlation_id(correlation_id)

        request = ApprovalRequest(
            correlation_id=corr,
            recommendation_id=recommendation_id,
            workflow_run_id=rec.run_id,
            risk_id=risk_id,
            action_type=action_type,
            action_snapshot=snapshot,
            binding_hash=binding_hash,
            requested_by=requester.user_id,
            requested_by_username=requester.username,
            status=ApprovalStatus.PENDING.value,
        )
        self._session.add(request)
        await self._session.flush()

        audit = AuditService(self._session)
        await audit.create_event(
            event_type=AuditEventType.APPROVAL_REQUEST_CREATED,
            entity_type=AuditEntityType.APPROVAL_REQUEST,
            entity_id=request.id,
            actor_id=requester.user_id,
            actor_username=requester.username,
            correlation_id=corr,
            workflow_run_id=rec.run_id,
            risk_id=risk_id,
            before_summary={"status": ApprovalStatus.PENDING.value},
            after_summary={
                "status": ApprovalStatus.PENDING.value,
                "action_type": action_type,
                "binding_hash": binding_hash,
            },
            metadata={"action_type": action_type, "binding_hash": binding_hash},
        )

        logger.info(
            "approval.request.created",
            approval_request_id=str(request.id),
            recommendation_id=str(recommendation_id),
            risk_id=risk_id,
            action_type=action_type,
            requester=requester.username,
        )
        return request

    async def approve_request(
        self,
        *,
        request_id: UUID,
        approver: AuthenticatedUser,
        comment: str,
        correlation_id: str | UUID | None = None,
    ) -> ApprovalRequest:
        """Transition a PENDING request to APPROVED.

        Raises:
            ApprovalRequestNotFoundError: no such request.
            ApprovalRequestNotPendingError: already decided.
            SelfDecisionError: the approver is the requester.
        """
        return await self._decide(
            request_id=request_id,
            actor=approver,
            comment=comment,
            status=ApprovalStatus.APPROVED,
            event_type=AuditEventType.APPROVAL_APPROVED,
            correlation_id=correlation_id,
        )

    async def reject_request(
        self,
        *,
        request_id: UUID,
        approver: AuthenticatedUser,
        reason: str,
        correlation_id: str | UUID | None = None,
    ) -> ApprovalRequest:
        """Transition a PENDING request to REJECTED.

        Raises:
            ApprovalRequestNotFoundError: no such request.
            ApprovalRequestNotPendingError: already decided.
            SelfDecisionError: the approver is the requester.
        """
        return await self._decide(
            request_id=request_id,
            actor=approver,
            comment=reason,
            status=ApprovalStatus.REJECTED,
            event_type=AuditEventType.APPROVAL_REJECTED,
            correlation_id=correlation_id,
        )

    async def _decide(
        self,
        *,
        request_id: UUID,
        actor: AuthenticatedUser,
        comment: str,
        status: ApprovalStatus,
        event_type: AuditEventType,
        correlation_id: str | UUID | None,
    ) -> ApprovalRequest:
        """Apply a terminal decision under a row lock.

        The request row is locked with ``SELECT ... FOR UPDATE`` so that
        concurrent decisions serialize: the second transaction blocks until
        the first commits, then observes the terminal status and fails
        closed with ``ApprovalRequestNotPendingError``.
        """
        result = await self._session.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == request_id)
            .with_for_update()
        )
        request = result.scalar_one_or_none()
        if request is None:
            raise ApprovalRequestNotFoundError()

        if request.status != ApprovalStatus.PENDING.value:
            raise ApprovalRequestNotPendingError()

        if request.requested_by == actor.user_id:
            raise SelfDecisionError()

        now = datetime.now(UTC)
        request.status = status.value
        request.decided_by = actor.user_id
        request.decided_by_username = actor.username
        request.decided_at = now
        request.decision_comment = comment

        corr = self._resolve_correlation_id(correlation_id)
        audit = AuditService(self._session)
        await audit.create_event(
            event_type=event_type,
            entity_type=AuditEntityType.APPROVAL_REQUEST,
            entity_id=request.id,
            actor_id=actor.user_id,
            actor_username=actor.username,
            correlation_id=corr,
            workflow_run_id=request.workflow_run_id,
            risk_id=request.risk_id,
            before_summary={"status": ApprovalStatus.PENDING.value},
            after_summary={
                "status": status.value,
                "decided_by_username": actor.username,
            },
            metadata={
                "action_type": request.action_type,
                "binding_hash": request.binding_hash,
            },
        )

        logger.info(
            "approval.request.decided",
            approval_request_id=str(request.id),
            status=status.value,
            actor=actor.username,
        )
        return request
