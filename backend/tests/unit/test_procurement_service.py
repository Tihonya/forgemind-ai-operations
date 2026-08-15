"""Unit tests for the procurement-task service (WP-REC-04C).

Covers the idempotent exactly-once creation with a mock ``AsyncSession``
(no live database): approved-path task construction, pending/rejected
fail-closed behavior, approver separation, immutable binding verification
(component/quantity/hash/provenance mismatch and non-reconstructable
snapshots), duplicate suppression, and the audit attempt/result event
semantics (ATTEMPTED + CREATED on success, ATTEMPTED + FAILED on
fail-closed, ATTEMPTED only on duplicate). No secret values are stored or
printed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.models.approval import (
    BINDING_VERSION,
    ApprovalRequest,
    ApprovalStatus,
    compute_binding_hash,
)
from app.models.audit import AuditEvent
from app.models.enums import AuditEntityType, AuditEventType
from app.models.procurement import ProcurementTask, ProcurementTaskState
from app.services.auth_service import AuthenticatedUser
from app.services.procurement_service import (
    ApprovalNotApprovedError,
    ApprovalRejectedError,
    ApprovalRequestNotFoundError,
    ApproverMismatchError,
    BindingMismatchError,
    ProcurementService,
    ProcurementTaskNotFoundError,
)

RISK_ID = "RISK-001"
ACTION_TYPE = "CREATE_PROCUREMENT_TASK"
COMPONENT_CODE = "CTRL-X4"
QUANTITY = "8"


def _user(
    user_id: UUID | None = None,
    username: str = "procurement.demo",
    roles: frozenset[str] = frozenset({"PROCUREMENT_SPECIALIST"}),
) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id or uuid4(),
        username=username,
        display_name="Test User",
        roles=roles,
    )


def _snapshot(
    run_id: UUID,
    rec_id: UUID,
    *,
    component_code: str = COMPONENT_CODE,
    quantity: str = QUANTITY,
    risk_id: str = RISK_ID,
    action_type: str = ACTION_TYPE,
) -> dict[str, object]:
    return {
        "binding_version": BINDING_VERSION,
        "action_type": action_type,
        "component_code": component_code,
        "quantity": quantity,
        "risk_id": risk_id,
        "workflow_run_id": str(run_id),
        "recommendation_id": str(rec_id),
        "title": "Procure replacement component",
        "rationale": "Shortage detected",
    }


def _approved_request(
    *,
    request_id: UUID,
    requested_by: UUID,
    approver: UUID,
    run_id: UUID,
    rec_id: UUID,
    status: str = ApprovalStatus.APPROVED.value,
    snapshot: dict[str, object] | None = None,
    binding_hash: str | None = None,
    risk_id: str = RISK_ID,
    action_type: str = ACTION_TYPE,
) -> ApprovalRequest:
    snap = (
        snapshot
        if snapshot is not None
        else _snapshot(run_id, rec_id, risk_id=risk_id, action_type=action_type)
    )
    return ApprovalRequest(
        id=request_id,
        correlation_id=uuid4(),
        recommendation_id=rec_id,
        workflow_run_id=run_id,
        risk_id=risk_id,
        action_type=action_type,
        action_snapshot=snap,
        binding_hash=binding_hash if binding_hash is not None else compute_binding_hash(snap),
        requested_by=requested_by,
        requested_by_username="manager.demo",
        status=status,
        decided_by=approver if status == ApprovalStatus.APPROVED.value else None,
        decided_by_username="procurement.demo" if status == ApprovalStatus.APPROVED.value else None,
        decision_comment="Approved" if status == ApprovalStatus.APPROVED.value else None,
    )


def _make_session(*results: object) -> MagicMock:
    """Build a mock session with a sync ``add`` and an async ``flush``/``execute``."""
    session = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=list(results))
    return session


def _result_with_scalar(value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _added_objects(session: MagicMock) -> list[Any]:
    return [call[0][0] for call in session.add.call_args_list]


def _assert_binding_mismatch_audit(
    session: MagicMock, request: ApprovalRequest
) -> None:
    """Assert the exact ATTEMPTED → FAILED audit sequence for a binding mismatch.

    A fail-closed binding outcome must persist exactly two audit events
    (attempt then terminal failure), carry the approval's persisted
    correlation ID, and contain no CREATED result and no task row. The
    failure metadata must be a safe, secret-free mapping.
    """
    events = [
        obj for obj in _added_objects(session) if isinstance(obj, AuditEvent)
    ]
    assert [e.event_type for e in events] == [
        AuditEventType.PROCUREMENT_TASK_CREATION_ATTEMPTED.value,
        AuditEventType.PROCUREMENT_TASK_CREATION_FAILED.value,
    ]
    attempt, failed = events
    # Both events reuse the approval request's persisted correlation ID.
    assert attempt.correlation_id == request.correlation_id
    assert failed.correlation_id == request.correlation_id
    assert attempt.entity_type == AuditEntityType.APPROVAL_REQUEST.value
    assert failed.entity_type == AuditEntityType.APPROVAL_REQUEST.value
    assert failed.entity_id == request.id
    assert failed.after_summary is not None
    assert failed.after_summary["reason"] == "binding_mismatch"
    # No CREATED event and no task row for a fail-closed outcome.
    assert all(
        e.event_type != AuditEventType.PROCUREMENT_TASK_CREATED.value for e in events
    )
    assert all(not isinstance(obj, ProcurementTask) for obj in _added_objects(session))
    # Binding/provenance metadata is a safe, secret-free mapping.
    metadata = failed.event_metadata
    assert metadata is not None
    assert set(metadata) == {
        "approval_request_id",
        "reason",
        "binding_hash",
    }
    assert metadata["reason"] == "binding_mismatch"
    assert metadata["binding_hash"] == request.binding_hash
    assert metadata["approval_request_id"] == str(request.id)


class TestExecuteForApproval:
    async def test_approved_request_creates_task_with_provenance(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
        )
        session = _make_session(
            _result_with_scalar(request), _result_with_scalar(None)
        )
        service = ProcurementService(session)

        task = await service.execute_for_approval(
            approval_request_id=request_id, actor=approver
        )

        assert isinstance(task, ProcurementTask)
        assert task.approval_request_id == request_id
        assert task.recommendation_id == rec_id
        assert task.workflow_run_id == run_id
        assert task.risk_id == RISK_ID
        assert task.action_type == ACTION_TYPE
        assert task.component_code == COMPONENT_CODE
        assert task.quantity == Decimal(QUANTITY)
        assert task.binding_hash == request.binding_hash
        assert task.task_state == ProcurementTaskState.CREATED.value
        assert task.requested_by == requester.user_id
        assert task.requested_by_username == "manager.demo"
        assert task.approved_by == approver.user_id
        assert task.approved_by_username == "procurement.demo"
        assert task.correlation_id == request.correlation_id

        # Three objects added: ATTEMPTED event, the task, CREATED event.
        added = _added_objects(session)
        assert [type(obj).__name__ for obj in added] == [
            "AuditEvent",
            "ProcurementTask",
            "AuditEvent",
        ]
        attempt, _, created = added
        assert attempt.event_type == AuditEventType.PROCUREMENT_TASK_CREATION_ATTEMPTED.value
        assert attempt.entity_type == AuditEntityType.APPROVAL_REQUEST.value
        assert attempt.entity_id == request_id
        assert attempt.correlation_id == request.correlation_id
        assert created.event_type == AuditEventType.PROCUREMENT_TASK_CREATED.value
        assert created.entity_type == AuditEntityType.PROCUREMENT_TASK.value
        assert created.correlation_id == request.correlation_id
        assert created.entity_id == task.id

        # Service flushes but never commits (caller owns the transaction).
        session.commit.assert_not_called()

    async def test_pending_fails_closed_without_task(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
            status=ApprovalStatus.PENDING.value,
        )
        session = _make_session(_result_with_scalar(request))
        service = ProcurementService(session)

        with pytest.raises(ApprovalNotApprovedError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=approver
            )

        added = _added_objects(session)
        assert [type(obj).__name__ for obj in added] == ["AuditEvent", "AuditEvent"]
        attempt, failed = added
        assert attempt.event_type == AuditEventType.PROCUREMENT_TASK_CREATION_ATTEMPTED.value
        assert failed.event_type == AuditEventType.PROCUREMENT_TASK_CREATION_FAILED.value
        assert failed.after_summary["reason"] == "approval_request_pending"
        assert all(not isinstance(obj, ProcurementTask) for obj in added)

    async def test_rejected_fails_closed_without_task(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
            status=ApprovalStatus.REJECTED.value,
        )
        session = _make_session(_result_with_scalar(request))
        service = ProcurementService(session)

        with pytest.raises(ApprovalRejectedError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=approver
            )

        added = _added_objects(session)
        failed = added[-1]
        assert failed.event_type == AuditEventType.PROCUREMENT_TASK_CREATION_FAILED.value
        assert failed.after_summary["reason"] == "approval_request_rejected"
        assert all(not isinstance(obj, ProcurementTask) for obj in added)

    async def test_non_approver_fails_closed(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        other = _user(username="procurement.other")
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
        )
        session = _make_session(_result_with_scalar(request))
        service = ProcurementService(session)

        with pytest.raises(ApproverMismatchError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=other
            )

        added = _added_objects(session)
        assert added[-1].after_summary["reason"] == "approver_mismatch"
        assert all(not isinstance(obj, ProcurementTask) for obj in added)

    async def test_not_found(self) -> None:
        session = _make_session(_result_with_scalar(None))
        service = ProcurementService(session)
        with pytest.raises(ApprovalRequestNotFoundError):
            await service.execute_for_approval(
                approval_request_id=uuid4(), actor=_user()
            )

    async def test_component_substitution_fails_closed(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        # Tampered snapshot: component changed but the persisted binding hash
        # still reflects the original snapshot.
        tampered = _snapshot(run_id, rec_id, component_code="MOTOR-M2")
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
            snapshot=tampered,
            binding_hash=compute_binding_hash(_snapshot(run_id, rec_id)),
        )
        session = _make_session(_result_with_scalar(request))
        service = ProcurementService(session)

        with pytest.raises(BindingMismatchError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=approver
            )
        _assert_binding_mismatch_audit(session, request)

    async def test_quantity_substitution_fails_closed(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        tampered = _snapshot(run_id, rec_id, quantity="99")
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
            snapshot=tampered,
            binding_hash=compute_binding_hash(_snapshot(run_id, rec_id)),
        )
        session = _make_session(_result_with_scalar(request))
        service = ProcurementService(session)

        with pytest.raises(BindingMismatchError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=approver
            )
        _assert_binding_mismatch_audit(session, request)

    async def test_changed_binding_hash_fails_closed(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        snapshot = _snapshot(run_id, rec_id)
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
            snapshot=snapshot,
            binding_hash="0" * 64,
        )
        session = _make_session(_result_with_scalar(request))
        service = ProcurementService(session)

        with pytest.raises(BindingMismatchError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=approver
            )
        _assert_binding_mismatch_audit(session, request)

    async def test_risk_provenance_mismatch_fails_closed(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        snapshot = _snapshot(run_id, rec_id)
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
            snapshot=snapshot,
            binding_hash=compute_binding_hash(snapshot),
            risk_id="RISK-002",  # denormalized column tampered; snapshot intact
        )
        session = _make_session(_result_with_scalar(request))
        service = ProcurementService(session)

        with pytest.raises(BindingMismatchError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=approver
            )
        _assert_binding_mismatch_audit(session, request)

    async def test_workflow_provenance_mismatch_fails_closed(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        snapshot = _snapshot(run_id, rec_id)
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=uuid4(),  # denormalized column tampered; snapshot intact
            rec_id=rec_id,
            snapshot=snapshot,
            binding_hash=compute_binding_hash(snapshot),
        )
        session = _make_session(_result_with_scalar(request))
        service = ProcurementService(session)

        with pytest.raises(BindingMismatchError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=approver
            )
        _assert_binding_mismatch_audit(session, request)

    async def test_recommendation_provenance_mismatch_fails_closed(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        snapshot = _snapshot(run_id, rec_id)
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=uuid4(),  # denormalized column tampered; snapshot intact
            snapshot=snapshot,
            binding_hash=compute_binding_hash(snapshot),
        )
        session = _make_session(_result_with_scalar(request))
        service = ProcurementService(session)

        with pytest.raises(BindingMismatchError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=approver
            )
        _assert_binding_mismatch_audit(session, request)

    async def test_non_reconstructable_snapshot_fails_closed(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        snapshot = _snapshot(run_id, rec_id)
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
            snapshot=snapshot,
            binding_hash=compute_binding_hash(snapshot),
        )
        # Malformed snapshot (missing a canonical field).
        request.action_snapshot = {k: v for k, v in snapshot.items() if k != "quantity"}
        session = _make_session(_result_with_scalar(request))
        service = ProcurementService(session)

        with pytest.raises(BindingMismatchError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=approver
            )
        _assert_binding_mismatch_audit(session, request)


class TestDuplicateAndIdempotency:
    async def test_duplicate_identical_returns_existing_without_second_created(
        self,
    ) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
        )
        existing = ProcurementTask(
            id=uuid4(),
            correlation_id=request.correlation_id,
            approval_request_id=request_id,
            recommendation_id=rec_id,
            workflow_run_id=run_id,
            risk_id=RISK_ID,
            action_type=ACTION_TYPE,
            component_code=COMPONENT_CODE,
            quantity=Decimal(QUANTITY),
            binding_hash=request.binding_hash,
            task_state=ProcurementTaskState.CREATED.value,
            requested_by=requester.user_id,
            requested_by_username="manager.demo",
            approved_by=approver.user_id,
            approved_by_username="procurement.demo",
        )
        session = _make_session(
            _result_with_scalar(request), _result_with_scalar(existing)
        )
        service = ProcurementService(session)

        result = await service.execute_for_approval(
            approval_request_id=request_id, actor=approver
        )

        assert result is existing
        added = _added_objects(session)
        # Only the ATTEMPTED event is appended; no second CREATED event and no
        # second task row.
        assert len(added) == 1
        assert added[0].event_type == AuditEventType.PROCUREMENT_TASK_CREATION_ATTEMPTED.value
        created_events = [
            obj
            for obj in added
            if isinstance(obj, AuditEvent)
            and obj.event_type == AuditEventType.PROCUREMENT_TASK_CREATED.value
        ]
        assert created_events == []

    async def test_existing_task_with_changed_parameters_fails_closed(self) -> None:
        request_id = uuid4()
        run_id = uuid4()
        rec_id = uuid4()
        requester = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        approver = _user(username="procurement.demo")
        request = _approved_request(
            request_id=request_id,
            requested_by=requester.user_id,
            approver=approver.user_id,
            run_id=run_id,
            rec_id=rec_id,
        )
        existing = ProcurementTask(
            id=uuid4(),
            correlation_id=request.correlation_id,
            approval_request_id=request_id,
            recommendation_id=rec_id,
            workflow_run_id=run_id,
            risk_id=RISK_ID,
            action_type=ACTION_TYPE,
            component_code="MOTOR-M2",  # differs from the approved snapshot
            quantity=Decimal(QUANTITY),
            binding_hash=request.binding_hash,
            task_state=ProcurementTaskState.CREATED.value,
            requested_by=requester.user_id,
            requested_by_username="manager.demo",
            approved_by=approver.user_id,
            approved_by_username="procurement.demo",
        )
        session = _make_session(
            _result_with_scalar(request), _result_with_scalar(existing)
        )
        service = ProcurementService(session)

        with pytest.raises(BindingMismatchError):
            await service.execute_for_approval(
                approval_request_id=request_id, actor=approver
            )


class TestReadScope:
    def _task(
        self,
        *,
        requested_by: UUID,
        approved_by: UUID,
    ) -> ProcurementTask:
        return ProcurementTask(
            id=uuid4(),
            correlation_id=uuid4(),
            approval_request_id=uuid4(),
            recommendation_id=uuid4(),
            workflow_run_id=uuid4(),
            risk_id=RISK_ID,
            action_type=ACTION_TYPE,
            component_code=COMPONENT_CODE,
            quantity=Decimal(QUANTITY),
            binding_hash="0" * 64,
            task_state=ProcurementTaskState.CREATED.value,
            requested_by=requested_by,
            requested_by_username="manager.demo",
            approved_by=approved_by,
            approved_by_username="procurement.demo",
        )

    async def test_manager_sees_own_tasks(self) -> None:
        manager = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        task = self._task(requested_by=manager.user_id, approved_by=uuid4())
        session = _make_session(_result_with_scalar(task))
        result = await ProcurementService(session).get_task(
            user=manager, task_id=task.id
        )
        assert result is task

    async def test_specialist_sees_approved_tasks(self) -> None:
        specialist = _user(username="procurement.demo")
        task = self._task(requested_by=uuid4(), approved_by=specialist.user_id)
        session = _make_session(_result_with_scalar(task))
        result = await ProcurementService(session).get_task(
            user=specialist, task_id=task.id
        )
        assert result is task

    async def test_scoped_out_or_missing_is_indistinguishable(self) -> None:
        # A manager looking up a task it did not request raises the same
        # error as a missing task.
        manager = _user(username="manager.demo", roles=frozenset({"PRODUCTION_MANAGER"}))
        session = _make_session(_result_with_scalar(None))
        with pytest.raises(ProcurementTaskNotFoundError):
            await ProcurementService(session).get_task(
                user=manager, task_id=uuid4()
            )

    async def test_unscoped_role_has_no_read(self) -> None:
        auditor = _user(username="auditor.demo", roles=frozenset({"AUDITOR"}))
        session = _make_session()
        items, total = await ProcurementService(session).list_tasks(
            user=auditor, limit=10, offset=0
        )
        assert items == []
        assert total == 0
