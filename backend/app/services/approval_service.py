"""Approval-request service (WP-REC-04A).

Implements the bounded single-shot approval state machine, the immutable
action-binding hash, fail-closed authorization invariants, backend read
scoping, and atomic audit-event emission through the WP-REC-04B
``AuditService``.

Contract (WP-REC-04-DEC §4 WP-REC-04A; DEC-052 G1/G2/G3):

- Create: ``PRODUCTION_MANAGER`` only (enforced by the API role gate). The
  executable action parameters (``component_code`` and ``quantity``) are
  independently resolved through the deterministic risk engine at creation,
  matched against the authoritative current risk, and bound into the
  immutable snapshot + binding hash (fail-closed on mismatch).
- Approve/reject: ``PROCUREMENT_SPECIALIST`` only (API role gate), and
  only when the decision actor differs from the requester (self-decision
  fails closed).
- Single-shot lifecycle ``PENDING → APPROVED | REJECTED``; a terminal
  request cannot be decided again.
- The request binds an immutable action snapshot and a deterministic
  SHA-256 binding hash over its canonical serialization.
- One correlation ID spans the whole approval lifecycle: creation inherits
  the originating workflow run's correlation ID (or generates one once),
  and every decision audit event reuses ``approval_request.correlation_id``.
- Creation and each decision emit the corresponding audit event in the
  same transaction as the business mutation.
- Read scope: ``PRODUCTION_MANAGER`` sees only its own requests;
  ``PROCUREMENT_SPECIALIST`` sees PENDING requests (the shared decision
  queue) plus the APPROVED requests it decided (so the approved record
  stays reachable for the controlled procurement task);
  ``AI_ADMINISTRATOR`` retains administrative read access (decomposition
  §3.6). Scoped-out and nonexistent IDs are indistinguishable (404).

Transaction ownership: this service operates within a caller-provided
``AsyncSession``, flushes, and never commits. The API endpoint owns
commit/rollback, so the business mutation and its audit event commit (or
roll back) atomically.

Deterministic and LLM-free: no provider, vendor, payment, or external
HTTP call is made anywhere in this module.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import generate_correlation_id, validate_correlation_id
from app.core.logging import get_logger
from app.models.approval import (
    BINDING_VERSION,
    ApprovalRequest,
    ApprovalStatus,
    _canonical_decimal,
    compute_binding_hash,
)
from app.models.enums import AuditEntityType, AuditEventType
from app.models.workflow import Recommendation, WorkflowRun
from app.schemas.recommendation import RecommendationData, RecommendedAction
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedUser
from app.services.risk_engine import analyze_plan

logger = get_logger(__name__)

#: The only controlled action the MVP supports (DEC-052 G2/G3). Matches the
#: WP-REC-04C action allow-list; any other action type fails closed.
SUPPORTED_ACTION_TYPE = "CREATE_PROCUREMENT_TASK"

#: Canonical role codes used for backend read scoping (decomposition §3.6).
_ROLE_ADMIN = "AI_ADMINISTRATOR"
_ROLE_MANAGER = "PRODUCTION_MANAGER"
_ROLE_SPECIALIST = "PROCUREMENT_SPECIALIST"


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
    """The approval request does not exist or is outside the caller's scope."""


class ApprovalRequestNotPendingError(ApprovalServiceError):
    """The approval request is not in PENDING state (already decided)."""


class SelfDecisionError(ApprovalServiceError):
    """The decision actor is the requester (separation of duties)."""


class DuplicateActiveApprovalError(ApprovalServiceError):
    """A PENDING approval request already exists for this action."""


class RiskActionParametersMismatchError(ApprovalServiceError):
    """The requested action parameters do not match the authoritative risk.

    Raised when the requested ``component_code``/``quantity`` tuple cannot be
    matched against the current deterministic risk result, or when the
    originating risk cannot be reconstructed unambiguously from the risk
    engine. Fail-closed: no request is persisted.
    """


def _risk_position(risk_id: str) -> int | None:
    """Return the 0-based position of a deterministic ``RISK-NNN`` identifier.

    The risks API assigns ``RISK-001`` to the first (index 0) risk in the
    deterministically sorted engine output. Returns ``None`` when the
    identifier is not a valid positional risk ID.
    """
    if not risk_id.startswith("RISK-"):
        return None
    suffix = risk_id[len("RISK-"):]
    if not suffix.isdigit():
        return None
    position = int(suffix) - 1
    return position if position >= 0 else None


def _read_scope(user: AuthenticatedUser) -> str:
    """Return the backend read scope for an authenticated user.

    Precedence (decomposition §3.6): ``AI_ADMINISTRATOR`` → administrative
    read (all); ``PRODUCTION_MANAGER`` → own requests only;
    ``PROCUREMENT_SPECIALIST`` → PENDING requests (the shared decision
    queue) plus the APPROVED requests the specialist themselves decided,
    so an approved request stays reachable for the controlled
    procurement-task execution and after a reload. Any other caller has no
    read scope (the API role gate rejects them with 403 before this).
    """
    if _ROLE_ADMIN in user.roles:
        return "all"
    if _ROLE_MANAGER in user.roles:
        return "own"
    if _ROLE_SPECIALIST in user.roles:
        return "actionable"
    return "none"


def _scope_conditions(user: AuthenticatedUser) -> list[ColumnElement[bool]]:
    """Return the SQLAlchemy WHERE conditions for the caller's read scope."""
    scope = _read_scope(user)
    if scope == "own":
        return [ApprovalRequest.requested_by == user.user_id]
    if scope == "actionable":
        # WP-UX-UA-05-R1: the specialist still sees every PENDING request
        # (the shared decision queue), and additionally the APPROVED requests
        # they themselves decided — the actor who may invoke the controlled
        # procurement task. This keeps the approved record reachable after
        # the decision and after a reload without granting access to other
        # specialists' approved records or to any REJECTED record.
        return [
            or_(
                ApprovalRequest.status == ApprovalStatus.PENDING.value,
                and_(
                    ApprovalRequest.status == ApprovalStatus.APPROVED.value,
                    ApprovalRequest.decided_by == user.user_id,
                ),
            )
        ]
    return []


def build_action_snapshot(
    *,
    recommendation: Recommendation,
    risk_id: str,
    action: RecommendedAction,
    component_code: str,
    quantity: Decimal,
) -> dict[str, object]:
    """Build the immutable canonical action snapshot.

    The snapshot is a fixed, versioned set of fields derived from the
    persisted recommendation and the resolved deterministic risk at creation
    time. It binds the executable parameters (``component_code`` and
    ``quantity``) plus action/risk identity and recommendation/workflow-run
    linkage. It contains no secrets and no mutable pointer — it is never
    recomputed from later recommendation or risk state.
    """
    return {
        "binding_version": BINDING_VERSION,
        "action_type": action.action_type,
        "component_code": component_code,
        "quantity": _canonical_decimal(quantity),
        "risk_id": risk_id,
        "workflow_run_id": str(recommendation.run_id),
        "recommendation_id": str(recommendation.id),
        "title": action.title,
        "rationale": action.rationale,
    }


class ApprovalService:
    """Bounded approval-request service (caller owns the transaction)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _resolve_creation_correlation_id(
        self,
        run_id: UUID,
        correlation_id: str | UUID | None,
    ) -> UUID:
        """Resolve the correlation ID for a new approval request.

        Resolution order: explicit argument → the originating workflow run's
        canonical correlation ID → newly generated UUID v4. The result is
        validated as UUID v4 and reused for the approval-request row and
        every subsequent approval audit event (one lineage).
        """
        resolved = correlation_id
        if resolved is None:
            run = await self._session.get(WorkflowRun, run_id)
            if run is not None and run.correlation_id is not None:
                resolved = run.correlation_id
        if resolved is None:
            resolved = generate_correlation_id()
        return UUID(validate_correlation_id(str(resolved)))

    async def create_request(
        self,
        *,
        recommendation_id: UUID,
        risk_id: str,
        action_type: str,
        component_code: str,
        quantity: Decimal,
        requester: AuthenticatedUser,
        correlation_id: str | UUID | None = None,
    ) -> ApprovalRequest:
        """Create a PENDING approval request bound to an eligible action.

        The executable parameters (``component_code`` and ``quantity``) are
        resolved against the current deterministic risk engine output and
        must match the authoritative risk; otherwise the request fails closed.

        Raises:
            RecommendationNotFoundError: no such recommendation.
            RecommendationContentInvalidError: content fails the wire schema.
            RecommendationIneligibleError: risk/action absent, action does not
                require approval, or unsupported action type.
            RiskActionParametersMismatchError: component/quantity do not match
                the current risk, or the risk cannot be reconstructed.
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

        # Resolve the current deterministic risk result and bind the
        # executable parameters (component/item identity and quantity).
        try:
            risks = await analyze_plan(self._session, data.plan_id)
        except ValueError as exc:
            # The originating plan/risk cannot be reconstructed → fail closed.
            raise RiskActionParametersMismatchError() from exc

        position = _risk_position(risk_id)
        if position is None or position >= len(risks):
            raise RiskActionParametersMismatchError()

        current = risks[position]
        if current.component_code != component_code or current.shortage != quantity:
            raise RiskActionParametersMismatchError()

        snapshot = build_action_snapshot(
            recommendation=rec,
            risk_id=risk_id,
            action=action,
            component_code=current.component_code,
            quantity=current.shortage,
        )
        binding_hash = compute_binding_hash(snapshot)
        corr = await self._resolve_creation_correlation_id(rec.run_id, correlation_id)

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
            component_code=current.component_code,
            requester=requester.username,
        )
        return request

    async def approve_request(
        self,
        *,
        request_id: UUID,
        approver: AuthenticatedUser,
        comment: str,
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
        )

    async def reject_request(
        self,
        *,
        request_id: UUID,
        approver: AuthenticatedUser,
        reason: str,
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
        )

    async def _decide(
        self,
        *,
        request_id: UUID,
        actor: AuthenticatedUser,
        comment: str,
        status: ApprovalStatus,
        event_type: AuditEventType,
    ) -> ApprovalRequest:
        """Apply a terminal decision under a row lock.

        The request row is locked with ``SELECT ... FOR UPDATE`` so that
        concurrent decisions serialize: the second transaction blocks until
        the first commits, then observes the terminal status and fails
        closed with ``ApprovalRequestNotPendingError``.

        The decision audit event reuses ``request.correlation_id`` (never a
        fresh per-decision ID), preserving the single approval correlation
        lineage across create/approve/reject.
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

        audit = AuditService(self._session)
        await audit.create_event(
            event_type=event_type,
            entity_type=AuditEntityType.APPROVAL_REQUEST,
            entity_id=request.id,
            actor_id=actor.user_id,
            actor_username=actor.username,
            correlation_id=request.correlation_id,
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

    async def list_requests(
        self,
        *,
        user: AuthenticatedUser,
        limit: int,
        offset: int,
        status: ApprovalStatus | None = None,
    ) -> tuple[list[ApprovalRequest], int]:
        """Return the caller-scoped page of approval requests.

        Scope (decomposition §3.6): manager sees own requests; specialist
        sees PENDING requests plus the APPROVED requests it decided;
        administrator sees all. Returns ``(items, total)`` ordered by
        ``requested_at DESC, id DESC``.

        When ``status`` is provided, results and ``total`` are further
        filtered to that status. The status filter composes with — and
        never widens — the caller's RBAC read scope.
        """
        scope = _read_scope(user)
        if scope == "none":
            return [], 0

        conditions = _scope_conditions(user)
        if status is not None:
            conditions = [*conditions, ApprovalRequest.status == status.value]

        total_stmt = select(func.count(ApprovalRequest.id)).where(*conditions)
        total = (await self._session.execute(total_stmt)).scalar_one()

        stmt = (
            select(ApprovalRequest)
            .where(*conditions)
            .order_by(ApprovalRequest.requested_at.desc(), ApprovalRequest.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        items = list(result.scalars().all())
        return items, total

    async def get_request(
        self,
        *,
        user: AuthenticatedUser,
        request_id: UUID,
    ) -> ApprovalRequest:
        """Return a single approval request within the caller's scope.

        A request outside the caller's scope raises
        ``ApprovalRequestNotFoundError`` exactly as a nonexistent ID does, so
        the caller cannot distinguish scoped-out from missing.
        """
        scope = _read_scope(user)
        if scope == "none":
            raise ApprovalRequestNotFoundError()

        stmt = select(ApprovalRequest).where(ApprovalRequest.id == request_id)
        stmt = stmt.where(*_scope_conditions(user))
        result = await self._session.execute(stmt)
        request = result.scalar_one_or_none()
        if request is None:
            raise ApprovalRequestNotFoundError()
        return request
