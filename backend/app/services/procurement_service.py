"""Procurement-task service (WP-REC-04C).

Implements the idempotent, exactly-once synthetic procurement-task
creation keyed by an ``APPROVED`` approval request, plus backend-scoped
read access.

Contract (WP-REC-04-DEC §4 WP-REC-04C; DEC-052 G2/G3; task §4/§5/§6):

- Execute: ``PROCUREMENT_SPECIALIST`` only (API role gate), and only the
  specialist who approved the request (``decided_by`` equals the caller)
  may execute the controlled action — a different specialist fails closed.
- Creation requires an ``APPROVED`` request. ``PENDING`` and ``REJECTED``
  requests fail closed without creating a task.
- Action-type allow-list: ``CREATE_PROCUREMENT_TASK`` only; any other
  action type fails closed.
- The executable parameters (``component_code`` and ``quantity``) are
  never client-controlled and never recomputed from mutable risk state.
  They are re-read from the WP-REC-04A persisted ``action_snapshot``, and
  the canonical binding hash is recomputed with the authoritative 04A
  serializer and compared against the persisted ``binding_hash``. Any
  hash, component, quantity, action, approval-identity, recommendation,
  workflow, or provenance mismatch fails closed.
- Exactly one task per approval is enforced by a database UNIQUE
  constraint (final backstop) and serialized by a ``SELECT ... FOR
  UPDATE`` row lock on the approval request plus a post-lock idempotency
  re-read (primary mechanism). A repeated identical execution returns the
  already-created task; a concurrent duplicate cannot create a second task
  or a second success audit result.
- Audit: every execution emits ``PROCUREMENT_TASK_CREATION_ATTEMPTED``
  (attempt) and exactly one terminal result — ``PROCUREMENT_TASK_CREATED``
  on success, ``PROCUREMENT_TASK_CREATION_FAILED`` on a fail-closed
  outcome. A duplicate (already-created) execution emits only the attempt
  (the original ``CREATED`` is the canonical result) and returns the
  existing task. All events reuse the approval request's correlation ID
  and carry the binding hash; none contains a secret, vendor, payment, or
  financial value.
- Transaction ownership: the service operates within a caller-provided
  ``AsyncSession``, flushes, and never commits. The API endpoint owns
  commit/rollback so the business write and its audit events commit (or
  roll back) atomically.

Deterministic and LLM-free: no provider, vendor, payment, or external
HTTP call is made anywhere in this module.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.approval import (
    BINDING_VERSION,
    ApprovalRequest,
    ApprovalStatus,
    _canonical_decimal,
    _canonical_uuid,
    compute_binding_hash,
)
from app.models.enums import AuditEntityType, AuditEventType
from app.models.procurement import ProcurementTask, ProcurementTaskState
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedUser

logger = get_logger(__name__)

#: The only controlled action the MVP supports (DEC-052 G2/G3; identical
#: to the WP-REC-04A allow-list). Any other action type fails closed.
SUPPORTED_ACTION_TYPE = "CREATE_PROCUREMENT_TASK"

#: Canonical role codes used for backend read scoping (decomposition §3.6).
_ROLE_ADMIN = "AI_ADMINISTRATOR"
_ROLE_MANAGER = "PRODUCTION_MANAGER"
_ROLE_SPECIALIST = "PROCUREMENT_SPECIALIST"


class ProcurementServiceError(Exception):
    """Base class for procurement-service domain errors."""


class ApprovalRequestNotFoundError(ProcurementServiceError):
    """The approval request does not exist."""


class ApprovalNotApprovedError(ProcurementServiceError):
    """The approval request is still PENDING (not yet approved)."""


class ApprovalRejectedError(ProcurementServiceError):
    """The approval request was REJECTED and can never execute."""


class ApproverMismatchError(ProcurementServiceError):
    """The caller is not the specialist who approved the request."""


class BindingMismatchError(ProcurementServiceError):
    """The action binding (hash or parameters) does not match the approval."""


class ProcurementTaskNotFoundError(ProcurementServiceError):
    """The procurement task does not exist or is outside the caller's scope."""


def _read_scope(user: AuthenticatedUser) -> str:
    """Return the backend read scope for an authenticated user.

    Precedence (decomposition §3.6): ``AI_ADMINISTRATOR`` → administrative
    read (all); ``PRODUCTION_MANAGER`` → own tasks (requester) only;
    ``PROCUREMENT_SPECIALIST`` → tasks they approved only. Any other
    caller has no read scope (the API role gate rejects them with 403
    before this).
    """
    if _ROLE_ADMIN in user.roles:
        return "all"
    if _ROLE_MANAGER in user.roles:
        return "own"
    if _ROLE_SPECIALIST in user.roles:
        return "approved"
    return "none"


def _scope_conditions(user: AuthenticatedUser) -> list[ColumnElement[bool]]:
    """Return the SQLAlchemy WHERE conditions for the caller's read scope."""
    scope = _read_scope(user)
    if scope == "own":
        return [ProcurementTask.requested_by == user.user_id]
    if scope == "approved":
        return [ProcurementTask.approved_by == user.user_id]
    return []


class ProcurementService:
    """Bounded procurement-task service (caller owns the transaction)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute_for_approval(
        self,
        *,
        approval_request_id: UUID,
        actor: AuthenticatedUser,
    ) -> ProcurementTask:
        """Create exactly one procurement task from an APPROVED request.

        Serializes concurrent executions on the same approval with a row
        lock, verifies the immutable action binding, and creates the task
        (or returns the already-created task on a duplicate). Every
        execution emits an attempt event and exactly one terminal result
        event (``CREATED`` or ``FAILED``).

        Raises:
            ApprovalRequestNotFoundError: no such approval request.
            ApprovalNotApprovedError: the request is PENDING.
            ApprovalRejectedError: the request is REJECTED.
            ApproverMismatchError: the caller is not the approver.
            BindingMismatchError: hash/parameter/provenance mismatch.
        """
        result = await self._session.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval_request_id)
            .with_for_update()
        )
        request = result.scalar_one_or_none()
        if request is None:
            raise ApprovalRequestNotFoundError()

        audit = AuditService(self._session)

        # Attempt event: records the controlled-action execution attempt.
        await audit.create_event(
            event_type=AuditEventType.PROCUREMENT_TASK_CREATION_ATTEMPTED,
            entity_type=AuditEntityType.APPROVAL_REQUEST,
            entity_id=request.id,
            actor_id=actor.user_id,
            actor_username=actor.username,
            correlation_id=request.correlation_id,
            workflow_run_id=request.workflow_run_id,
            risk_id=request.risk_id,
            before_summary={"approval_status": request.status},
            after_summary={"action_type": request.action_type},
            metadata={
                "approval_request_id": str(request.id),
                "action_type": request.action_type,
                "binding_hash": request.binding_hash,
            },
        )

        if request.status == ApprovalStatus.PENDING.value:
            await self._emit_failure(audit, request, actor, "approval_request_pending")
            raise ApprovalNotApprovedError()

        if request.status == ApprovalStatus.REJECTED.value:
            await self._emit_failure(audit, request, actor, "approval_request_rejected")
            raise ApprovalRejectedError()

        # APPROVED: only the approving specialist may execute.
        if request.decided_by is None or request.decided_by != actor.user_id:
            await self._emit_failure(audit, request, actor, "approver_mismatch")
            raise ApproverMismatchError()

        # Verify the immutable action binding (fail closed on any mismatch).
        try:
            component_code, quantity = self._verify_binding(request)
        except BindingMismatchError:
            await self._emit_failure(audit, request, actor, "binding_mismatch")
            raise

        # Idempotency re-read under the row lock: return the already-created
        # task for a repeated identical execution (no second CREATED event).
        existing = (
            await self._session.execute(
                select(ProcurementTask).where(
                    ProcurementTask.approval_request_id == request.id
                )
            )
        ).scalar_one_or_none()

        if existing is not None:
            if (
                existing.component_code != component_code
                or existing.quantity != quantity
                or existing.binding_hash != request.binding_hash
                or existing.action_type != request.action_type
            ):
                await self._emit_failure(audit, request, actor, "existing_task_mismatch")
                raise BindingMismatchError()
            return existing

        # APPROVED rows carry a non-null decision actor (DB CHECK), but fail
        # closed defensively if the snapshot is somehow absent.
        approver_id = request.decided_by
        approver_username = request.decided_by_username
        if approver_id is None or approver_username is None:
            await self._emit_failure(audit, request, actor, "missing_approver_identity")
            raise BindingMismatchError()

        task = ProcurementTask(
            correlation_id=request.correlation_id,
            approval_request_id=request.id,
            recommendation_id=request.recommendation_id,
            workflow_run_id=request.workflow_run_id,
            risk_id=request.risk_id,
            action_type=request.action_type,
            component_code=component_code,
            quantity=quantity,
            binding_hash=request.binding_hash,
            task_state=ProcurementTaskState.CREATED.value,
            requested_by=request.requested_by,
            requested_by_username=request.requested_by_username,
            approved_by=approver_id,
            approved_by_username=approver_username,
        )
        self._session.add(task)
        await self._session.flush()

        await audit.create_event(
            event_type=AuditEventType.PROCUREMENT_TASK_CREATED,
            entity_type=AuditEntityType.PROCUREMENT_TASK,
            entity_id=task.id,
            actor_id=actor.user_id,
            actor_username=actor.username,
            correlation_id=request.correlation_id,
            workflow_run_id=request.workflow_run_id,
            risk_id=request.risk_id,
            before_summary={"approval_status": ApprovalStatus.APPROVED.value},
            after_summary={
                "task_state": task.task_state,
                "component_code": task.component_code,
                "quantity": _canonical_decimal(task.quantity),
                "binding_hash": task.binding_hash,
            },
            metadata={
                "approval_request_id": str(request.id),
                "binding_hash": request.binding_hash,
            },
        )

        logger.info(
            "procurement.task.created",
            procurement_task_id=str(task.id),
            approval_request_id=str(request.id),
            risk_id=request.risk_id,
            component_code=component_code,
            actor=actor.username,
        )
        return task

    async def _emit_failure(
        self,
        audit: AuditService,
        request: ApprovalRequest,
        actor: AuthenticatedUser,
        reason: str,
    ) -> None:
        """Append the terminal ``PROCUREMENT_TASK_CREATION_FAILED`` event."""
        await audit.create_event(
            event_type=AuditEventType.PROCUREMENT_TASK_CREATION_FAILED,
            entity_type=AuditEntityType.APPROVAL_REQUEST,
            entity_id=request.id,
            actor_id=actor.user_id,
            actor_username=actor.username,
            correlation_id=request.correlation_id,
            workflow_run_id=request.workflow_run_id,
            risk_id=request.risk_id,
            before_summary={"approval_status": request.status},
            after_summary={"outcome": "failed", "reason": reason},
            metadata={
                "approval_request_id": str(request.id),
                "reason": reason,
                "binding_hash": request.binding_hash,
            },
        )

    def _verify_binding(self, request: ApprovalRequest) -> tuple[str, Decimal]:
        """Recompute and validate the immutable action binding.

        Re-derives the canonical SHA-256 binding hash from the persisted
        ``action_snapshot`` using the authoritative WP-REC-04A serializer
        and compares it against ``request.binding_hash``, then verifies the
        snapshot's identity fields against the approval request's own
        columns. Returns ``(component_code, quantity)``.

        Raises:
            BindingMismatchError: on any hash, parameter, or provenance
                mismatch (fail closed).
        """
        snapshot = request.action_snapshot
        if not isinstance(snapshot, dict):
            raise BindingMismatchError()

        try:
            recomputed = compute_binding_hash(snapshot)
        except (KeyError, ValueError, TypeError):
            raise BindingMismatchError() from None

        if recomputed != request.binding_hash:
            raise BindingMismatchError()

        # Cross-check the snapshot's identity fields against the approval's
        # own columns (provenance/identity mismatch fails closed).
        if snapshot.get("binding_version") != BINDING_VERSION:
            raise BindingMismatchError()
        if snapshot.get("action_type") != request.action_type:
            raise BindingMismatchError()
        if request.action_type != SUPPORTED_ACTION_TYPE:
            raise BindingMismatchError()
        if snapshot.get("risk_id") != request.risk_id:
            raise BindingMismatchError()
        try:
            if _canonical_uuid(snapshot.get("workflow_run_id")) != str(
                request.workflow_run_id
            ):
                raise BindingMismatchError()
            if _canonical_uuid(snapshot.get("recommendation_id")) != str(
                request.recommendation_id
            ):
                raise BindingMismatchError()
        except (ValueError, AttributeError, TypeError):
            raise BindingMismatchError() from None

        component_code = snapshot.get("component_code")
        if not isinstance(component_code, str) or not component_code.strip():
            raise BindingMismatchError()

        try:
            quantity = Decimal(str(snapshot.get("quantity")))
        except (InvalidOperation, ValueError, TypeError):
            raise BindingMismatchError() from None
        if not quantity.is_finite() or quantity <= 0:
            raise BindingMismatchError()

        return component_code, quantity

    async def list_tasks(
        self,
        *,
        user: AuthenticatedUser,
        limit: int,
        offset: int,
    ) -> tuple[list[ProcurementTask], int]:
        """Return the caller-scoped page of procurement tasks.

        Scope: administrator sees all; manager sees its own (requester);
        specialist sees the tasks it approved. Returns ``(items, total)``
        ordered by ``created_at DESC, id DESC``.
        """
        if _read_scope(user) == "none":
            return [], 0

        conditions = _scope_conditions(user)
        total_stmt = select(func.count(ProcurementTask.id)).where(*conditions)
        total = (await self._session.execute(total_stmt)).scalar_one()

        stmt = (
            select(ProcurementTask)
            .where(*conditions)
            .order_by(ProcurementTask.created_at.desc(), ProcurementTask.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all()), total

    async def get_task(
        self,
        *,
        user: AuthenticatedUser,
        task_id: UUID,
    ) -> ProcurementTask:
        """Return a single procurement task within the caller's scope.

        A task outside the caller's scope raises
        ``ProcurementTaskNotFoundError`` exactly as a nonexistent ID does,
        so the caller cannot distinguish scoped-out from missing.
        """
        if _read_scope(user) == "none":
            raise ProcurementTaskNotFoundError()

        stmt = select(ProcurementTask).where(ProcurementTask.id == task_id)
        stmt = stmt.where(*_scope_conditions(user))
        result = await self._session.execute(stmt)
        task = result.scalar_one_or_none()
        if task is None:
            raise ProcurementTaskNotFoundError()
        return task
