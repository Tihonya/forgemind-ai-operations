"""Unit tests for the approval-request service (WP-REC-04A).

Covers create/approve/reject with a mock ``AsyncSession`` (no live
database): eligibility validation, self-decision rejection, single-shot
terminal semantics, duplicate-active detection, deterministic binding
hash, correlation-ID propagation, and atomic audit-event emission. No
secret values are stored or printed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.models.approval import ApprovalRequest, ApprovalStatus, compute_binding_hash
from app.models.audit import AuditEvent
from app.models.enums import AuditEntityType, AuditEventType
from app.models.workflow import Recommendation
from app.schemas.recommendation import RecommendationData, RecommendedAction, RiskItem
from app.services.approval_service import (
    ApprovalRequestNotFoundError,
    ApprovalRequestNotPendingError,
    ApprovalService,
    DuplicateActiveApprovalError,
    RecommendationContentInvalidError,
    RecommendationIneligibleError,
    RecommendationNotFoundError,
    SelfDecisionError,
    build_action_snapshot,
)
from app.services.auth_service import AuthenticatedUser

CORRELATION_ID = "550e8400-e29b-41d4-a716-446655440000"
ACTION_TYPE = "CREATE_PROCUREMENT_TASK"
RISK_ID = "RISK-001"


def _user(user_id: UUID | None = None, username: str = "manager.demo") -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=user_id or uuid4(),
        username=username,
        display_name="Test User",
        roles=frozenset({"PRODUCTION_MANAGER"}),
    )


def _content(
    *,
    run_id: UUID,
    risk_id: str = RISK_ID,
    action_type: str = ACTION_TYPE,
    requires_approval: bool = True,
) -> dict[str, object]:
    return RecommendationData(
        schema_version="1.0",
        run_id=run_id,
        plan_id="PLAN-2026-W31",
        risks=[
            RiskItem(
                risk_id=risk_id,
                summary="Risk summary",
                business_impact="Business impact",
                recommended_actions=[
                    RecommendedAction(
                        action_type=action_type,
                        title="Procure replacement component",
                        rationale="Shortage detected",
                        requires_approval=requires_approval,
                    )
                ],
                sources=[],
            )
        ],
    ).model_dump(mode="json")


def _recommendation(
    *,
    recommendation_id: UUID,
    run_id: UUID,
    content: dict[str, object],
    status: str = "VALIDATED",
) -> Recommendation:
    return Recommendation(
        id=recommendation_id,
        run_id=run_id,
        plan_id=uuid4(),
        status=status,
        content=content,
        schema_version="1.0",
    )


def _make_session(*results: object) -> MagicMock:
    """Build a mock session with a sync ``add`` and an async ``flush``.

    ``results`` are returned in order by ``session.execute``.
    """
    session = MagicMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock(side_effect=list(results))
    return session


def _result_with_scalar(value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _result_with_first(value: object | None) -> MagicMock:
    result = MagicMock()
    result.first.return_value = value
    return result


class TestCreateRequest:
    async def test_creates_pending_request_with_binding_and_audit_event(self) -> None:
        run_id = uuid4()
        rec_id = uuid4()
        rec = _recommendation(
            recommendation_id=rec_id, run_id=run_id, content=_content(run_id=run_id)
        )
        session = _make_session(
            _result_with_scalar(rec), _result_with_first(None)
        )
        service = ApprovalService(session)
        requester = _user()

        approval = await service.create_request(
            recommendation_id=rec_id,
            risk_id=RISK_ID,
            action_type=ACTION_TYPE,
            requester=requester,
            correlation_id=CORRELATION_ID,
        )

        assert isinstance(approval, ApprovalRequest)
        assert approval.status == ApprovalStatus.PENDING.value
        assert approval.recommendation_id == rec_id
        assert approval.workflow_run_id == run_id
        assert approval.risk_id == RISK_ID
        assert approval.action_type == ACTION_TYPE
        assert approval.requested_by == requester.user_id
        assert approval.requested_by_username == requester.username
        assert approval.decided_by is None
        assert approval.decision_comment is None

        expected_snapshot = {
            "action_type": ACTION_TYPE,
            "risk_id": RISK_ID,
            "title": "Procure replacement component",
            "rationale": "Shortage detected",
            "workflow_run_id": str(run_id),
            "recommendation_id": str(rec_id),
        }
        assert approval.action_snapshot == expected_snapshot
        assert approval.binding_hash == compute_binding_hash(expected_snapshot)
        assert approval.correlation_id == UUID(CORRELATION_ID)

        # Two objects were added: the approval request and its audit event.
        assert session.add.call_count == 2
        added = [call[0][0] for call in session.add.call_args_list]
        assert isinstance(added[0], ApprovalRequest)
        assert isinstance(added[1], AuditEvent)
        assert added[1].event_type == AuditEventType.APPROVAL_REQUEST_CREATED.value
        assert added[1].entity_type == AuditEntityType.APPROVAL_REQUEST.value
        assert added[1].correlation_id == UUID(CORRELATION_ID)
        assert added[1].workflow_run_id == run_id
        assert added[1].risk_id == RISK_ID

        # The service flushes but never commits (caller owns the transaction).
        session.commit.assert_not_called()

    async def test_deterministic_hash_for_equivalent_input(self) -> None:
        run_id = uuid4()
        rec_id = uuid4()
        rec = _recommendation(
            recommendation_id=rec_id, run_id=run_id, content=_content(run_id=run_id)
        )
        session = _make_session(
            _result_with_scalar(rec), _result_with_first(None)
        )
        approval = await ApprovalService(session).create_request(
            recommendation_id=rec_id,
            risk_id=RISK_ID,
            action_type=ACTION_TYPE,
            requester=_user(),
            correlation_id=CORRELATION_ID,
        )
        snapshot = build_action_snapshot(
            recommendation=rec,
            risk_id=RISK_ID,
            action=RecommendationData.model_validate(rec.content).risks[0]
            .recommended_actions[0],
        )
        assert approval.binding_hash == compute_binding_hash(snapshot)

    async def test_recommendation_not_found(self) -> None:
        session = _make_session(_result_with_scalar(None))
        service = ApprovalService(session)
        with pytest.raises(RecommendationNotFoundError):
            await service.create_request(
                recommendation_id=uuid4(),
                risk_id=RISK_ID,
                action_type=ACTION_TYPE,
                requester=_user(),
            )

    async def test_invalid_recommendation_content(self) -> None:
        rec_id = uuid4()
        rec = _recommendation(
            recommendation_id=rec_id,
            run_id=uuid4(),
            content={"not": "valid"},
        )
        session = _make_session(_result_with_scalar(rec))
        service = ApprovalService(session)
        with pytest.raises(RecommendationContentInvalidError):
            await service.create_request(
                recommendation_id=rec_id,
                risk_id=RISK_ID,
                action_type=ACTION_TYPE,
                requester=_user(),
            )

    async def test_risk_not_found_in_recommendation(self) -> None:
        rec_id = uuid4()
        rec = _recommendation(
            recommendation_id=rec_id, run_id=uuid4(), content=_content(run_id=uuid4())
        )
        session = _make_session(_result_with_scalar(rec))
        service = ApprovalService(session)
        with pytest.raises(RecommendationIneligibleError) as exc_info:
            await service.create_request(
                recommendation_id=rec_id,
                risk_id="RISK-DOES-NOT-EXIST",
                action_type=ACTION_TYPE,
                requester=_user(),
            )
        assert exc_info.value.code == "risk_not_found_in_recommendation"

    async def test_action_not_found_in_recommendation(self) -> None:
        rec_id = uuid4()
        rec = _recommendation(
            recommendation_id=rec_id, run_id=uuid4(), content=_content(run_id=uuid4())
        )
        session = _make_session(_result_with_scalar(rec))
        service = ApprovalService(session)
        with pytest.raises(RecommendationIneligibleError) as exc_info:
            await service.create_request(
                recommendation_id=rec_id,
                risk_id=RISK_ID,
                action_type="SOME_OTHER_ACTION",
                requester=_user(),
            )
        assert exc_info.value.code == "action_not_found_in_recommendation"

    async def test_action_not_requiring_approval(self) -> None:
        rec_id = uuid4()
        rec = _recommendation(
            recommendation_id=rec_id,
            run_id=uuid4(),
            content=_content(run_id=uuid4(), requires_approval=False),
        )
        session = _make_session(_result_with_scalar(rec))
        service = ApprovalService(session)
        with pytest.raises(RecommendationIneligibleError) as exc_info:
            await service.create_request(
                recommendation_id=rec_id,
                risk_id=RISK_ID,
                action_type=ACTION_TYPE,
                requester=_user(),
            )
        assert exc_info.value.code == "action_not_requiring_approval"

    async def test_unsupported_action_type(self) -> None:
        rec_id = uuid4()
        run_id = uuid4()
        rec = _recommendation(
            recommendation_id=rec_id,
            run_id=run_id,
            content=_content(run_id=run_id, action_type="UNSUPPORTED_ACTION"),
        )
        session = _make_session(_result_with_scalar(rec))
        service = ApprovalService(session)
        with pytest.raises(RecommendationIneligibleError) as exc_info:
            await service.create_request(
                recommendation_id=rec_id,
                risk_id=RISK_ID,
                action_type="UNSUPPORTED_ACTION",
                requester=_user(),
            )
        assert exc_info.value.code == "unsupported_action_type"

    async def test_duplicate_active_approval_rejected(self) -> None:
        rec_id = uuid4()
        rec = _recommendation(
            recommendation_id=rec_id, run_id=uuid4(), content=_content(run_id=uuid4())
        )
        session = _make_session(
            _result_with_scalar(rec), _result_with_first((uuid4(),))
        )
        service = ApprovalService(session)
        with pytest.raises(DuplicateActiveApprovalError):
            await service.create_request(
                recommendation_id=rec_id,
                risk_id=RISK_ID,
                action_type=ACTION_TYPE,
                requester=_user(),
            )


def _pending_request(
    *,
    request_id: UUID,
    requested_by: UUID,
    run_id: UUID,
    risk_id: str = RISK_ID,
    action_type: str = ACTION_TYPE,
) -> ApprovalRequest:
    return ApprovalRequest(
        id=request_id,
        correlation_id=uuid4(),
        recommendation_id=uuid4(),
        workflow_run_id=run_id,
        risk_id=risk_id,
        action_type=action_type,
        action_snapshot={
            "action_type": action_type,
            "risk_id": risk_id,
            "title": "t",
            "rationale": "r",
            "workflow_run_id": str(run_id),
            "recommendation_id": str(uuid4()),
        },
        binding_hash=compute_binding_hash(
            {
                "action_type": action_type,
                "risk_id": risk_id,
                "title": "t",
                "rationale": "r",
                "workflow_run_id": str(run_id),
                "recommendation_id": str(uuid4()),
            }
        ),
        requested_by=requested_by,
        requested_by_username="manager.demo",
        status=ApprovalStatus.PENDING.value,
    )


class TestApproveRequest:
    async def test_approve_sets_terminal_fields_and_emits_audit(self) -> None:
        run_id = uuid4()
        requester = _user(username="manager.demo")
        approver = _user(username="procurement.demo")
        request = _pending_request(
            request_id=uuid4(), requested_by=requester.user_id, run_id=run_id
        )
        session = _make_session(_result_with_scalar(request))
        service = ApprovalService(session)

        result = await service.approve_request(
            request_id=request.id,
            approver=approver,
            comment="Approved after review",
            correlation_id=CORRELATION_ID,
        )

        assert result.status == ApprovalStatus.APPROVED.value
        assert result.decided_by == approver.user_id
        assert result.decided_by_username == "procurement.demo"
        assert result.decision_comment == "Approved after review"
        assert result.decided_at is not None

        assert session.add.call_count == 1
        audit = session.add.call_args_list[0][0][0]
        assert isinstance(audit, AuditEvent)
        assert audit.event_type == AuditEventType.APPROVAL_APPROVED.value
        assert audit.entity_id == request.id
        assert audit.actor_id == approver.user_id
        assert audit.correlation_id == UUID(CORRELATION_ID)

    async def test_approve_self_decision_forbidden(self) -> None:
        requester = _user(username="manager.demo")
        request = _pending_request(
            request_id=uuid4(), requested_by=requester.user_id, run_id=uuid4()
        )
        session = _make_session(_result_with_scalar(request))
        service = ApprovalService(session)
        # Same user (even if the caller happens to hold the approver role).
        approver = AuthenticatedUser(
            user_id=requester.user_id,
            username=requester.username,
            display_name=requester.display_name,
            roles=frozenset({"PROCUREMENT_SPECIALIST"}),
        )
        with pytest.raises(SelfDecisionError):
            await service.approve_request(
                request_id=request.id, approver=approver, comment="x"
            )

    async def test_approve_non_pending_fails(self) -> None:
        requester = _user()
        approver = _user(username="procurement.demo")
        request = _pending_request(
            request_id=uuid4(), requested_by=requester.user_id, run_id=uuid4()
        )
        request.status = ApprovalStatus.APPROVED.value
        session = _make_session(_result_with_scalar(request))
        service = ApprovalService(session)
        with pytest.raises(ApprovalRequestNotPendingError):
            await service.approve_request(
                request_id=request.id, approver=approver, comment="x"
            )

    async def test_approve_not_found(self) -> None:
        session = _make_session(_result_with_scalar(None))
        service = ApprovalService(session)
        with pytest.raises(ApprovalRequestNotFoundError):
            await service.approve_request(
                request_id=uuid4(), approver=_user(username="procurement.demo"), comment="x"
            )


class TestRejectRequest:
    async def test_reject_sets_terminal_fields_and_emits_audit(self) -> None:
        run_id = uuid4()
        requester = _user(username="manager.demo")
        approver = _user(username="procurement.demo")
        request = _pending_request(
            request_id=uuid4(), requested_by=requester.user_id, run_id=run_id
        )
        session = _make_session(_result_with_scalar(request))
        service = ApprovalService(session)

        result = await service.reject_request(
            request_id=request.id,
            approver=approver,
            reason="Insufficient justification",
            correlation_id=CORRELATION_ID,
        )

        assert result.status == ApprovalStatus.REJECTED.value
        assert result.decided_by == approver.user_id
        assert result.decision_comment == "Insufficient justification"
        assert result.decided_at is not None

        audit = session.add.call_args_list[0][0][0]
        assert audit.event_type == AuditEventType.APPROVAL_REJECTED.value
        assert audit.entity_id == request.id

    async def test_reject_self_decision_forbidden(self) -> None:
        requester = _user(username="manager.demo")
        request = _pending_request(
            request_id=uuid4(), requested_by=requester.user_id, run_id=uuid4()
        )
        session = _make_session(_result_with_scalar(request))
        service = ApprovalService(session)
        approver = AuthenticatedUser(
            user_id=requester.user_id,
            username=requester.username,
            display_name=requester.display_name,
            roles=frozenset({"PROCUREMENT_SPECIALIST"}),
        )
        with pytest.raises(SelfDecisionError):
            await service.reject_request(
                request_id=request.id, approver=approver, reason="no"
            )

    async def test_reject_non_pending_fails(self) -> None:
        requester = _user()
        approver = _user(username="procurement.demo")
        request = _pending_request(
            request_id=uuid4(), requested_by=requester.user_id, run_id=uuid4()
        )
        request.status = ApprovalStatus.REJECTED.value
        session = _make_session(_result_with_scalar(request))
        service = ApprovalService(session)
        with pytest.raises(ApprovalRequestNotPendingError):
            await service.reject_request(
                request_id=request.id, approver=approver, reason="x"
            )
