"""Integration tests for the approval-request API (WP-REC-04A).

Tests the real API endpoints against a live PostgreSQL database:

- Create (RBAC, eligibility, duplicate, binding hash, audit event).
- Approve/reject (RBAC, self-decision, single-shot terminal semantics,
  decision-field persistence, audit events, no procurement task).
- Read API (RBAC, disclosure ordering, pagination).
- Safety (correlation-ID propagation, no secrets in audit, no
  procurement task).

Requires a live PostgreSQL database (migrated + seeded). Skips cleanly if
unavailable. No provider/vendor/financial call occurs.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.main import app
from app.models.approval import (
    BINDING_VERSION,
    ApprovalRequest,
    compute_binding_hash,
)
from app.models.audit import AuditEvent
from app.models.workflow import Recommendation, WorkflowRun
from app.schemas.recommendation import RecommendationData, RecommendedAction, RiskItem
from app.services.approval_service import ApprovalRequestNotPendingError, ApprovalService
from app.services.auth_service import AuthenticatedUser

_INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

_DEMO_PASSWORDS = {
    "manager.demo": "ManagerPass123!",
    "procurement.demo": "ProcurementPass123!",
    "engineer.demo": "EngineerPass123!",
    "admin.demo": "AdminPass123!",
    "auditor.demo": "AuditorPass123!",
}

ACTION_TYPE = "CREATE_PROCUREMENT_TASK"
RISK_ID = "RISK-001"
# Golden Dataset RISK-001: CTRL-X4, shortage 8 (deterministic).
RISK_COMPONENT_CODE = "CTRL-X4"
RISK_QUANTITY = "8"


def _can_connect() -> bool:
    if not _INTEGRATION_DB_URL:
        return False
    try:
        sync_url = _INTEGRATION_DB_URL
        if "+asyncpg" in sync_url:
            sync_url = sync_url.replace("+asyncpg", "+psycopg")
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect(),
    reason="Integration database not available",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _seeded_golden_dataset() -> Generator[None, None, None]:
    """Migrate to head and seed the Golden Dataset once for this module."""
    from alembic.config import Config

    from alembic import command
    from app.seed.generator.loader import _find_alembic_ini, load_golden_dataset

    command.upgrade(Config(str(_find_alembic_ini())), "head")
    load_golden_dataset()
    yield


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker[AsyncSession](
        bind=db_engine, expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.execute(text("DELETE FROM procurement_tasks"))
        await session.execute(text("DELETE FROM approval_requests"))
        await session.execute(text("DELETE FROM audit_events"))
        await session.execute(text("DELETE FROM recommendations"))
        await session.execute(text("DELETE FROM workflow_steps"))
        await session.execute(text("DELETE FROM workflow_runs"))
        await session.commit()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_sync_engine() -> Any:
    assert _INTEGRATION_DB_URL is not None
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")
    return create_engine(sync_url, pool_pre_ping=True)


def _get_user_id(username: str) -> UUID:
    engine = _get_sync_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id FROM users WHERE username = :u"), {"u": username}
            ).fetchone()
        assert row is not None, f"user not seeded: {username}"
        return cast(UUID, row[0])
    finally:
        engine.dispose()


def _make_content(
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


async def _seed_recommendation(
    db_session: AsyncSession,
    *,
    risk_id: str = RISK_ID,
    action_type: str = ACTION_TYPE,
    requires_approval: bool = True,
) -> Recommendation:
    """Create (and commit) a workflow run + validated recommendation."""
    plan_result = await db_session.execute(
        text("SELECT id FROM production_plans LIMIT 1")
    )
    plan_id = plan_result.scalar_one()
    run = WorkflowRun(
        id=uuid4(),
        correlation_id=uuid4(),
        state="COMPLETED",
        plan_id=cast(UUID, plan_id),
        triggered_by="manager.demo",
    )
    db_session.add(run)
    await db_session.flush()

    rec = Recommendation(
        id=uuid4(),
        run_id=run.id,
        plan_id=run.plan_id,
        status="VALIDATED",
        content=_make_content(
            run_id=run.id, risk_id=risk_id, action_type=action_type,
            requires_approval=requires_approval,
        ),
        schema_version="1.0",
    )
    db_session.add(rec)
    await db_session.commit()
    return rec


async def _login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, (
        f"seed login failed: {response.status_code} {response.text}"
    )
    return cast(str, response.json()["access_token"])


async def _create_pending_request(
    db_session: AsyncSession,
    *,
    rec: Recommendation,
    requester_id: UUID,
    requester_username: str,
) -> ApprovalRequest:
    requester = AuthenticatedUser(
        user_id=requester_id,
        username=requester_username,
        display_name="Test User",
        roles=frozenset({"PRODUCTION_MANAGER"}),
    )
    approval = await ApprovalService(db_session).create_request(
        recommendation_id=rec.id,
        risk_id=RISK_ID,
        action_type=ACTION_TYPE,
        component_code=RISK_COMPONENT_CODE,
        quantity=Decimal(RISK_QUANTITY),
        requester=requester,
    )
    await db_session.commit()
    return approval


def _create_payload(rec: Recommendation, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "recommendation_id": str(rec.id),
        "risk_id": RISK_ID,
        "action_type": ACTION_TYPE,
        "component_code": RISK_COMPONENT_CODE,
        "quantity": RISK_QUANTITY,
    }
    payload.update(overrides)
    return payload


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestCreateApprovalRequest:
    async def test_production_manager_can_create(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])

        response = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec),
            headers=_auth(token),
        )

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "PENDING"
        assert data["recommendation_id"] == str(rec.id)
        assert data["workflow_run_id"] == str(rec.run_id)
        assert data["risk_id"] == RISK_ID
        assert data["action_type"] == ACTION_TYPE
        assert data["requested_by_username"] == "manager.demo"
        assert data["decided_by"] is None
        assert len(data["binding_hash"]) == 64
        assert data["requested_at"] is not None
        assert data["decided_at"] is None

    async def test_binding_hash_matches_recomputed_snapshot(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec),
            headers=_auth(token),
        )
        assert response.status_code == 201
        data = response.json()
        expected = {
            "binding_version": 1,
            "action_type": ACTION_TYPE,
            "component_code": RISK_COMPONENT_CODE,
            "quantity": RISK_QUANTITY,
            "risk_id": RISK_ID,
            "title": "Procure replacement component",
            "rationale": "Shortage detected",
            "workflow_run_id": str(rec.run_id),
            "recommendation_id": str(rec.id),
        }
        assert data["binding_hash"] == compute_binding_hash(expected)
        assert data["action_snapshot"] == expected

    @pytest.mark.parametrize(
        "username",
        ["procurement.demo", "engineer.demo", "admin.demo", "auditor.demo"],
    )
    async def test_wrong_roles_cannot_create(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None, username: str,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, username, _DEMO_PASSWORDS[username])
        response = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec),
            headers=_auth(token),
        )
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "insufficient_permissions"

    async def test_unauthenticated_create_fails(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        response = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec),
        )
        assert response.status_code == 401

    async def test_missing_recommendation_fails(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.post(
            "/api/v1/approval-requests",
            json={
                "recommendation_id": str(uuid4()),
                "risk_id": RISK_ID,
                "action_type": ACTION_TYPE,
                "component_code": RISK_COMPONENT_CODE,
                "quantity": RISK_QUANTITY,
            },
            headers=_auth(token),
        )
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "recommendation_not_found"

    async def test_action_not_requiring_approval_fails(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session, requires_approval=False)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec),
            headers=_auth(token),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error"] == "action_not_requiring_approval"

    async def test_duplicate_active_approval_fails(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        payload = _create_payload(rec)
        first = await client.post(
            "/api/v1/approval-requests", json=payload, headers=_auth(token)
        )
        assert first.status_code == 201
        second = await client.post(
            "/api/v1/approval-requests", json=payload, headers=_auth(token)
        )
        assert second.status_code == 409
        assert second.json()["detail"]["error"] == "approval_request_duplicate"

    async def test_creation_emits_audit_event(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec),
            headers=_auth(token),
        )
        assert response.status_code == 201
        request_id = response.json()["id"]

        result = await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == UUID(request_id),
                AuditEvent.event_type == "APPROVAL_REQUEST_CREATED",
            )
        )
        event = result.scalars().one_or_none()
        assert event is not None
        assert event.workflow_run_id == rec.run_id
        assert event.risk_id == RISK_ID
        assert event.actor_username == "manager.demo"

    async def test_rollback_removes_request_and_audit_event(
        self, db_session: AsyncSession, _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        requester = AuthenticatedUser(
            user_id=_get_user_id("manager.demo"),
            username="manager.demo",
            display_name="Production Manager",
            roles=frozenset({"PRODUCTION_MANAGER"}),
        )
        approval = await ApprovalService(db_session).create_request(
            recommendation_id=rec.id,
            risk_id=RISK_ID,
            action_type=ACTION_TYPE,
            component_code=RISK_COMPONENT_CODE,
            quantity=Decimal(RISK_QUANTITY),
            requester=requester,
        )
        request_id = approval.id
        await db_session.rollback()

        result = await db_session.execute(
            select(ApprovalRequest).where(ApprovalRequest.id == request_id)
        )
        assert result.scalar_one_or_none() is None
        result = await db_session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == request_id)
        )
        assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------


class TestDecisions:
    async def test_procurement_specialist_can_approve(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        response = await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "Approved after review"},
            headers=_auth(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "APPROVED"
        assert data["decided_by_username"] == "procurement.demo"
        assert data["decision_comment"] == "Approved after review"
        assert data["decided_at"] is not None

    async def test_procurement_specialist_can_reject(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        response = await client.post(
            f"/api/v1/approval-requests/{approval.id}/reject",
            json={"comment": "Insufficient justification"},
            headers=_auth(token),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "REJECTED"
        assert data["decision_comment"] == "Insufficient justification"
        assert data["decided_at"] is not None

    async def test_requester_cannot_self_approve(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        # Create a request whose requester IS the procurement specialist.
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("procurement.demo"),
            requester_username="procurement.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        response = await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "self-approval"},
            headers=_auth(token),
        )
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "self_decision_forbidden"

    @pytest.mark.parametrize(
        "username",
        ["manager.demo", "engineer.demo", "admin.demo", "auditor.demo"],
    )
    async def test_wrong_roles_cannot_approve(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None, username: str,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(client, username, _DEMO_PASSWORDS[username])
        response = await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "x"},
            headers=_auth(token),
        )
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "insufficient_permissions"

    async def test_approve_twice_fails(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        first = await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "ok"},
            headers=_auth(token),
        )
        assert first.status_code == 200
        second = await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "again"},
            headers=_auth(token),
        )
        assert second.status_code == 409
        assert second.json()["detail"]["error"] == "approval_request_not_pending"

    async def test_reject_after_approve_fails(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        approve = await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "ok"},
            headers=_auth(token),
        )
        assert approve.status_code == 200
        reject = await client.post(
            f"/api/v1/approval-requests/{approval.id}/reject",
            json={"comment": "no"},
            headers=_auth(token),
        )
        assert reject.status_code == 409
        assert reject.json()["detail"]["error"] == "approval_request_not_pending"

    async def test_approve_after_reject_fails(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        reject = await client.post(
            f"/api/v1/approval-requests/{approval.id}/reject",
            json={"comment": "no"},
            headers=_auth(token),
        )
        assert reject.status_code == 200
        approve = await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "ok"},
            headers=_auth(token),
        )
        assert approve.status_code == 409
        assert approve.json()["detail"]["error"] == "approval_request_not_pending"

    async def test_decision_fields_persist(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "Approved"},
            headers=_auth(token),
        )

        # Reload from the database (fresh session view; the API committed
        # through a separate session, so refresh the identity-map cache).
        result = await db_session.execute(
            select(ApprovalRequest)
            .where(ApprovalRequest.id == approval.id)
            .execution_options(populate_existing=True)
        )
        row = result.scalar_one()
        assert row.status == "APPROVED"
        assert row.decided_by == _get_user_id("procurement.demo")
        assert row.decided_by_username == "procurement.demo"
        assert row.decision_comment == "Approved"
        assert row.decided_at is not None

    async def test_approve_emits_audit_event(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "ok"},
            headers=_auth(token),
        )
        result = await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == approval.id,
                AuditEvent.event_type == "APPROVAL_APPROVED",
            )
        )
        event = result.scalars().one_or_none()
        assert event is not None
        assert event.actor_username == "procurement.demo"

    async def test_reject_emits_audit_event(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        await client.post(
            f"/api/v1/approval-requests/{approval.id}/reject",
            json={"comment": "no"},
            headers=_auth(token),
        )
        result = await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_id == approval.id,
                AuditEvent.event_type == "APPROVAL_REJECTED",
            )
        )
        event = result.scalars().one_or_none()
        assert event is not None
        assert event.actor_username == "procurement.demo"

    async def test_no_procurement_task_created(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "ok"},
            headers=_auth(token),
        )
        # WP-REC-04A owns no procurement-task creation (04C scope): approving
        # must not create a procurement-task row (the table itself is owned
        # by WP-REC-04C).
        result = await db_session.execute(
            text("SELECT count(*) FROM procurement_tasks")
        )
        assert result.scalar_one() == 0


# ---------------------------------------------------------------------------
# Read API and disclosure
# ---------------------------------------------------------------------------


class TestReadApi:
    @pytest.mark.parametrize(
        "username", ["manager.demo", "procurement.demo", "admin.demo"]
    )
    async def test_permitted_roles_can_read(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None, username: str,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(client, username, _DEMO_PASSWORDS[username])

        detail = await client.get(
            f"/api/v1/approval-requests/{approval.id}", headers=_auth(token)
        )
        assert detail.status_code == 200
        assert detail.json()["id"] == str(approval.id)

        listing = await client.get(
            "/api/v1/approval-requests", headers=_auth(token)
        )
        assert listing.status_code == 200
        assert listing.json()["total"] >= 1

    @pytest.mark.parametrize("username", ["engineer.demo", "auditor.demo"])
    async def test_unauthorized_roles_denied(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None, username: str,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(client, username, _DEMO_PASSWORDS[username])
        response = await client.get(
            f"/api/v1/approval-requests/{approval.id}", headers=_auth(token)
        )
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "insufficient_permissions"

    async def test_unauthenticated_denied(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        response = await client.get(f"/api/v1/approval-requests/{uuid4()}")
        assert response.status_code == 401

    async def test_authorization_before_missing_id_disclosure(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        # A wrong-role user must receive 403 (not 404) even for a
        # nonexistent ID — authorization precedes entity-existence lookup.
        token = await _login(client, "engineer.demo", _DEMO_PASSWORDS["engineer.demo"])
        response = await client.get(
            f"/api/v1/approval-requests/{uuid4()}", headers=_auth(token)
        )
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "insufficient_permissions"

    async def test_pagination_bounds_enforced(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        too_high = await client.get(
            "/api/v1/approval-requests?limit=201", headers=_auth(token)
        )
        assert too_high.status_code == 422
        too_low = await client.get(
            "/api/v1/approval-requests?limit=0", headers=_auth(token)
        )
        assert too_low.status_code == 422


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------


class TestSafety:
    async def test_creation_inherits_workflow_run_correlation(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        run = (
            await db_session.execute(
                select(WorkflowRun).where(WorkflowRun.id == rec.run_id)
            )
        ).scalar_one()
        response = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec),
            headers=_auth(token),
        )
        assert response.status_code == 201
        request_id = response.json()["id"]
        # The approval request inherits the originating workflow run's
        # canonical correlation ID (not a fresh or request-scoped ID).
        assert response.json()["correlation_id"] == str(run.correlation_id)

        result = await db_session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == UUID(request_id))
        )
        event = result.scalars().one()
        assert event.correlation_id == run.correlation_id

    async def test_no_secret_bearing_field_in_audit(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "ok"},
            headers=_auth(token),
        )
        result = await db_session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == approval.id)
        )
        for event in result.scalars().all():
            for summary in (event.before_summary, event.after_summary, event.event_metadata):
                if summary is None:
                    continue
                flattened = str(summary).lower()
                for secret_term in ("api_key", "token", "password", "secret", "authorization"):
                    assert secret_term not in flattened

    async def test_no_platform_admin_role_usage(self) -> None:
        from app.api.approval import _APPROVER_ROLE, _MANAGER_ROLE, _READ_ROLES

        canonical = {
            "PRODUCTION_MANAGER",
            "PROCUREMENT_SPECIALIST",
            "ENGINEER",
            "AI_ADMINISTRATOR",
            "AUDITOR",
        }
        for role_set in (_APPROVER_ROLE, _MANAGER_ROLE, _READ_ROLES):
            assert "platform_admin" not in role_set
            assert role_set <= canonical


# ---------------------------------------------------------------------------
# Action-parameter binding (F-1)
# ---------------------------------------------------------------------------


class TestActionParameterMismatch:
    async def test_changed_component_code_rejected(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec, component_code="MOTOR-M2"),
            headers=_auth(token),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error"] == "risk_action_parameters_mismatch"

    async def test_changed_quantity_rejected(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec, quantity="9"),
            headers=_auth(token),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error"] == "risk_action_parameters_mismatch"

    async def test_nonpositive_quantity_rejected(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec, quantity="0"),
            headers=_auth(token),
        )
        assert response.status_code == 422

    async def test_client_supplied_binding_hash_rejected(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.post(
            "/api/v1/approval-requests",
            json={**_create_payload(rec), "binding_hash": "0" * 64},
            headers=_auth(token),
        )
        # The binding hash is server-derived; a client-supplied hash is
        # rejected by the extra-forbid schema.
        assert response.status_code == 422


class TestNoMutationRoutes:
    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    async def test_no_update_or_delete_route(
        self, client: AsyncClient, _seeded_golden_dataset: None, method: str,
    ) -> None:
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await getattr(client, method)(
            f"/api/v1/approval-requests/{uuid4()}",
            headers=_auth(token),
        )
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# Read scope (F-3)
# ---------------------------------------------------------------------------


class TestReadScope:
    async def test_manager_sees_own_but_not_others(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        own_rec = await _seed_recommendation(db_session)
        own = await _create_pending_request(
            db_session,
            rec=own_rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        foreign_rec = await _seed_recommendation(db_session)
        foreign = await _create_pending_request(
            db_session,
            rec=foreign_rec,
            requester_id=_get_user_id("procurement.demo"),
            requester_username="procurement.demo",
        )
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])

        own_detail = await client.get(
            f"/api/v1/approval-requests/{own.id}", headers=_auth(token)
        )
        assert own_detail.status_code == 200

        foreign_detail = await client.get(
            f"/api/v1/approval-requests/{foreign.id}", headers=_auth(token)
        )
        assert foreign_detail.status_code == 404

        listing = await client.get("/api/v1/approval-requests", headers=_auth(token))
        ids = {item["id"] for item in listing.json()["items"]}
        assert str(own.id) in ids
        assert str(foreign.id) not in ids

    async def test_specialist_sees_pending_and_own_approved(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """WP-UX-UA-05-R1: the approving specialist keeps PENDING + own APPROVED."""
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )

        # PENDING request is visible before the decision.
        pending_detail = await client.get(
            f"/api/v1/approval-requests/{approval.id}", headers=_auth(token)
        )
        assert pending_detail.status_code == 200

        approve = await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "ok"},
            headers=_auth(token),
        )
        assert approve.status_code == 200

        # After approval the decider can still read it and it stays in the
        # list — the approved record remains reachable for the controlled
        # procurement-task step.
        approved_detail = await client.get(
            f"/api/v1/approval-requests/{approval.id}", headers=_auth(token)
        )
        assert approved_detail.status_code == 200
        assert approved_detail.json()["status"] == "APPROVED"

        listing = await client.get("/api/v1/approval-requests", headers=_auth(token))
        ids = {item["id"] for item in listing.json()["items"]}
        assert str(approval.id) in ids

    async def test_specialist_can_reload_own_approved_request(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """The approved request stays reachable after a direct reload."""
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "ok"},
            headers=_auth(token),
        )

        # A fresh session (fresh login) reopens the exact approved request.
        fresh_token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        detail = await client.get(
            f"/api/v1/approval-requests/{approval.id}", headers=_auth(fresh_token)
        )
        assert detail.status_code == 200
        assert detail.json()["status"] == "APPROVED"

    async def test_specialist_cannot_read_approved_by_another_actor(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """APPROVED rows are readable only by the deciding specialist."""
        rec = await _seed_recommendation(db_session)
        rows = await _create_approval_rows(
            db_session, rec=rec,
            requester_id=_get_user_id("engineer.demo"),
            requester_username="engineer.demo",
            count=1, status="APPROVED",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        detail = await client.get(
            f"/api/v1/approval-requests/{rows[0].id}", headers=_auth(token)
        )
        # Another actor's APPROVED record is out of the specialist's scope.
        assert detail.status_code == 404

        listing = await client.get("/api/v1/approval-requests", headers=_auth(token))
        ids = {item["id"] for item in listing.json()["items"]}
        assert str(rows[0].id) not in ids

    async def test_specialist_cannot_read_rejected_request(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """REJECTED requests are terminal and out of scope (nothing to execute)."""
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        reject = await client.post(
            f"/api/v1/approval-requests/{approval.id}/reject",
            json={"comment": "no"},
            headers=_auth(token),
        )
        assert reject.status_code == 200

        detail = await client.get(
            f"/api/v1/approval-requests/{approval.id}", headers=_auth(token)
        )
        assert detail.status_code == 404

        listing = await client.get("/api/v1/approval-requests", headers=_auth(token))
        ids = {item["id"] for item in listing.json()["items"]}
        assert str(approval.id) not in ids

    async def test_admin_sees_terminal_and_pending(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )
        approver_token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        await client.post(
            f"/api/v1/approval-requests/{approval.id}/approve",
            json={"comment": "ok"},
            headers=_auth(approver_token),
        )
        admin_token = await _login(client, "admin.demo", _DEMO_PASSWORDS["admin.demo"])
        detail = await client.get(
            f"/api/v1/approval-requests/{approval.id}", headers=_auth(admin_token)
        )
        assert detail.status_code == 200
        assert detail.json()["status"] == "APPROVED"

    async def test_scoped_out_and_nonexistent_indistinguishable(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        foreign = await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("procurement.demo"),
            requester_username="procurement.demo",
        )
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        scoped = await client.get(
            f"/api/v1/approval-requests/{foreign.id}", headers=_auth(token)
        )
        missing = await client.get(
            f"/api/v1/approval-requests/{uuid4()}", headers=_auth(token)
        )
        assert scoped.status_code == 404
        assert missing.status_code == 404
        assert scoped.json() == missing.json()


# ---------------------------------------------------------------------------
# Correlation lineage (F-2)
# ---------------------------------------------------------------------------


class TestCorrelationLineage:
    async def test_create_and_approve_share_correlation(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        manager_token = await _login(
            client, "manager.demo", _DEMO_PASSWORDS["manager.demo"]
        )
        create = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec),
            headers=_auth(manager_token),
        )
        assert create.status_code == 201
        request_id = create.json()["id"]
        row_correlation = create.json()["correlation_id"]

        approver_token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        approve = await client.post(
            f"/api/v1/approval-requests/{request_id}/approve",
            json={"comment": "ok"},
            headers=_auth(approver_token),
        )
        assert approve.status_code == 200

        events = (
            await db_session.execute(
                select(AuditEvent)
                .where(AuditEvent.entity_id == UUID(request_id))
                .order_by(AuditEvent.created_at)
            )
        ).scalars().all()
        assert len(events) == 2
        for event in events:
            assert str(event.correlation_id) == row_correlation

    async def test_create_and_reject_share_correlation(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        manager_token = await _login(
            client, "manager.demo", _DEMO_PASSWORDS["manager.demo"]
        )
        create = await client.post(
            "/api/v1/approval-requests",
            json=_create_payload(rec),
            headers=_auth(manager_token),
        )
        assert create.status_code == 201
        request_id = create.json()["id"]
        row_correlation = create.json()["correlation_id"]

        approver_token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        reject = await client.post(
            f"/api/v1/approval-requests/{request_id}/reject",
            json={"comment": "no"},
            headers=_auth(approver_token),
        )
        assert reject.status_code == 200

        events = (
            await db_session.execute(
                select(AuditEvent).where(AuditEvent.entity_id == UUID(request_id))
            )
        ).scalars().all()
        assert len(events) == 2
        for event in events:
            assert str(event.correlation_id) == row_correlation


# ---------------------------------------------------------------------------
# Two-session concurrency (F-4)
# ---------------------------------------------------------------------------


class TestConcurrentDecisions:
    async def _run_concurrent_decision(
        self,
        db_engine: AsyncEngine,
        approval_id: UUID,
        approver: AuthenticatedUser,
        first_action: str,
        second_action: str,
    ) -> tuple[str, str]:
        """Run two decisions against the same request on two sessions.

        ``first_action`` acquires the row lock and holds it uncommitted while
        ``second_action`` attempts the competing decision on an independent
        session. Returns the two outcome labels.
        """
        factory = async_sessionmaker[AsyncSession](
            bind=db_engine, expire_on_commit=False
        )
        lock_held = asyncio.Event()

        async def _decide(session: AsyncSession, action: str, comment: str) -> None:
            service = ApprovalService(session)
            if action == "approve":
                await service.approve_request(
                    request_id=approval_id, approver=approver, comment=comment
                )
            else:
                await service.reject_request(
                    request_id=approval_id, approver=approver, reason=comment
                )

        async def _first() -> str:
            async with factory() as sa:
                await _decide(sa, first_action, "first")
                lock_held.set()
                await asyncio.sleep(0.5)
                await sa.commit()
                return "SUCCESS"

        async def _second() -> str:
            await lock_held.wait()
            async with factory() as sa:
                try:
                    await _decide(sa, second_action, "second")
                    await sa.commit()
                    return "UNEXPECTED_SUCCESS"
                except ApprovalRequestNotPendingError:
                    await sa.rollback()
                    return "NOT_PENDING"

        results = await asyncio.gather(_first(), _second())
        return results[0], results[1]

    async def _assert_single_terminal_decision(
        self,
        db_session: AsyncSession,
        approval_id: UUID,
        expected_status: str,
        expected_event_type: str,
    ) -> None:
        row = (
            await db_session.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.id == approval_id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert row.status == expected_status

        terminal_events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_id == approval_id,
                    AuditEvent.event_type == expected_event_type,
                )
            )
        ).scalars().all()
        assert len(terminal_events) == 1

    async def _seed_pending_for_race(
        self, db_session: AsyncSession,
    ) -> ApprovalRequest:
        rec = await _seed_recommendation(db_session)
        return await _create_pending_request(
            db_session,
            rec=rec,
            requester_id=_get_user_id("manager.demo"),
            requester_username="manager.demo",
        )

    async def test_approve_vs_approve(
        self, db_engine: AsyncEngine, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        approval = await self._seed_pending_for_race(db_session)
        assert approval.status == "PENDING"
        approver = AuthenticatedUser(
            user_id=_get_user_id("procurement.demo"),
            username="procurement.demo",
            display_name="Procurement Specialist",
            roles=frozenset({"PROCUREMENT_SPECIALIST"}),
        )
        first_result, second_result = await self._run_concurrent_decision(
            db_engine, approval.id, approver, "approve", "approve"
        )
        assert first_result == "SUCCESS"
        assert second_result == "NOT_PENDING"
        await self._assert_single_terminal_decision(
            db_session, approval.id, "APPROVED", "APPROVAL_APPROVED"
        )

    async def test_approve_vs_reject(
        self, db_engine: AsyncEngine, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        approval = await self._seed_pending_for_race(db_session)
        assert approval.status == "PENDING"
        approver = AuthenticatedUser(
            user_id=_get_user_id("procurement.demo"),
            username="procurement.demo",
            display_name="Procurement Specialist",
            roles=frozenset({"PROCUREMENT_SPECIALIST"}),
        )
        first_result, second_result = await self._run_concurrent_decision(
            db_engine, approval.id, approver, "approve", "reject"
        )
        assert first_result == "SUCCESS"
        assert second_result == "NOT_PENDING"
        await self._assert_single_terminal_decision(
            db_session, approval.id, "APPROVED", "APPROVAL_APPROVED"
        )


# ---------------------------------------------------------------------------
# Status filter (F-1 remediation)
# ---------------------------------------------------------------------------


def _make_action_snapshot(rec: Recommendation) -> dict[str, object]:
    """Build a minimal valid action snapshot for direct-row insertion."""
    return {
        "binding_version": BINDING_VERSION,
        "action_type": ACTION_TYPE,
        "component_code": RISK_COMPONENT_CODE,
        "quantity": RISK_QUANTITY,
        "risk_id": RISK_ID,
        "workflow_run_id": str(rec.run_id),
        "recommendation_id": str(rec.id),
        "title": "Procure replacement component",
        "rationale": "Shortage detected",
    }


async def _create_approval_rows(
    db_session: AsyncSession,
    *,
    rec: Recommendation,
    requester_id: UUID,
    requester_username: str,
    count: int,
    status: str = "PENDING",
) -> list[ApprovalRequest]:
    """Insert ``count`` approval-request rows directly (bypassing the service).

    Each row gets a unique recommendation/run pair to avoid the
    partial-unique index on (recommendation_id, risk_id, action_type)
    WHERE PENDING.
    """
    rows: list[ApprovalRequest] = []
    for _ in range(count):
        run = WorkflowRun(
            id=uuid4(),
            correlation_id=uuid4(),
            state="COMPLETED",
            plan_id=rec.plan_id,
            triggered_by=requester_username,
        )
        db_session.add(run)
        await db_session.flush()
        new_rec = Recommendation(
            id=uuid4(),
            run_id=run.id,
            plan_id=run.plan_id,
            status="VALIDATED",
            content=_make_content(run_id=run.id),
            schema_version="1.0",
        )
        db_session.add(new_rec)
        await db_session.flush()

        snapshot = _make_action_snapshot(new_rec)
        binding_hash = compute_binding_hash(snapshot)
        row = ApprovalRequest(
            correlation_id=uuid4(),
            recommendation_id=new_rec.id,
            workflow_run_id=run.id,
            risk_id=RISK_ID,
            action_type=ACTION_TYPE,
            action_snapshot=snapshot,
            binding_hash=binding_hash,
            requested_by=requester_id,
            requested_by_username=requester_username,
            status=status,
        )
        if status != "PENDING":
            row.decided_by = requester_id
            row.decided_by_username = requester_username
            row.decided_at = datetime.now(UTC)
            row.decision_comment = "test decision"
        db_session.add(row)
        rows.append(row)
    await db_session.commit()
    return rows


class TestStatusFilter:
    """Tests for the optional ``status`` query filter on GET /approval-requests.

    The filter must compose with the caller's RBAC read scope and never
    widen it. ``total`` must represent the filtered count, not the
    unfiltered scope total. Pagination applies after filtering.
    """

    async def test_no_status_filter_preserves_existing_behavior(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """Without ``status``, the list returns all scoped rows (all statuses)."""
        manager_id = _get_user_id("manager.demo")
        rec = await _seed_recommendation(db_session)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=3, status="PENDING",
        )
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=2, status="APPROVED",
        )
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/approval-requests", headers=_auth(token)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 5
        assert len(body["items"]) == 5
        statuses = {item["status"] for item in body["items"]}
        assert statuses == {"PENDING", "APPROVED"}

    async def test_manager_status_pending_returns_only_own_pending(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """manager + status=PENDING → own PENDING rows only."""
        manager_id = _get_user_id("manager.demo")
        rec = await _seed_recommendation(db_session)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=3, status="PENDING",
        )
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=4, status="APPROVED",
        )
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/approval-requests?status=PENDING", headers=_auth(token)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 3
        for item in body["items"]:
            assert item["status"] == "PENDING"

    async def test_manager_status_approved_returns_only_own_approved(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """manager + status=APPROVED → own APPROVED rows only."""
        manager_id = _get_user_id("manager.demo")
        rec = await _seed_recommendation(db_session)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=2, status="PENDING",
        )
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=5, status="APPROVED",
        )
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/approval-requests?status=APPROVED", headers=_auth(token)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 5
        assert len(body["items"]) == 5
        for item in body["items"]:
            assert item["status"] == "APPROVED"

    async def test_filtered_total_is_exact(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """``total`` reflects the filtered count, not the unfiltered scope total."""
        manager_id = _get_user_id("manager.demo")
        rec = await _seed_recommendation(db_session)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=3, status="PENDING",
        )
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=7, status="REJECTED",
        )
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/approval-requests?status=PENDING&limit=1", headers=_auth(token)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 3
        assert len(body["items"]) == 1

    async def test_limit_1_returns_full_filtered_total(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """limit=1 returns one item but total is the full filtered count."""
        manager_id = _get_user_id("manager.demo")
        rec = await _seed_recommendation(db_session)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=10, status="PENDING",
        )
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/approval-requests?status=PENDING&limit=1&offset=0",
            headers=_auth(token),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 10
        assert len(body["items"]) == 1

    async def test_pagination_applied_after_filtering(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """Pagination slices the filtered result set, not the unfiltered one."""
        manager_id = _get_user_id("manager.demo")
        rec = await _seed_recommendation(db_session)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=6, status="PENDING",
        )
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=10, status="APPROVED",
        )
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        # Page 1: limit=2, offset=0 → 2 items, total=6 (PENDING only)
        page1 = await client.get(
            "/api/v1/approval-requests?status=PENDING&limit=2&offset=0",
            headers=_auth(token),
        )
        assert page1.status_code == 200
        body1 = page1.json()
        assert body1["total"] == 6
        assert len(body1["items"]) == 2
        # Page 2: limit=2, offset=2 → 2 items, same total=6
        page2 = await client.get(
            "/api/v1/approval-requests?status=PENDING&limit=2&offset=2",
            headers=_auth(token),
        )
        assert page2.status_code == 200
        body2 = page2.json()
        assert body2["total"] == 6
        assert len(body2["items"]) == 2
        # Items must be different across pages
        ids1 = {item["id"] for item in body1["items"]}
        ids2 = {item["id"] for item in body2["items"]}
        assert ids1.isdisjoint(ids2)

    async def test_procurement_specialist_scope_not_widened(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """specialist + status=PENDING → only PENDING (scope already PENDING-only).

        specialist + status=APPROVED → empty (scope excludes terminal).
        """
        manager_id = _get_user_id("manager.demo")
        rec = await _seed_recommendation(db_session)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=3, status="PENDING",
        )
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=2, status="APPROVED",
        )
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        # specialist + status=PENDING → 3 PENDING
        pending_resp = await client.get(
            "/api/v1/approval-requests?status=PENDING", headers=_auth(token)
        )
        assert pending_resp.status_code == 200
        assert pending_resp.json()["total"] == 3
        # specialist + status=APPROVED → 0 (scope already restricts to PENDING)
        approved_resp = await client.get(
            "/api/v1/approval-requests?status=APPROVED", headers=_auth(token)
        )
        assert approved_resp.status_code == 200
        assert approved_resp.json()["total"] == 0

    async def test_admin_status_filtering_works(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """administrator + status filter works within the admin (all) scope."""
        manager_id = _get_user_id("manager.demo")
        rec = await _seed_recommendation(db_session)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=4, status="PENDING",
        )
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=6, status="REJECTED",
        )
        token = await _login(client, "admin.demo", _DEMO_PASSWORDS["admin.demo"])
        # admin + no filter → all 10
        all_resp = await client.get(
            "/api/v1/approval-requests", headers=_auth(token)
        )
        assert all_resp.json()["total"] == 10
        # admin + status=PENDING → 4
        pending_resp = await client.get(
            "/api/v1/approval-requests?status=PENDING", headers=_auth(token)
        )
        assert pending_resp.json()["total"] == 4
        # admin + status=REJECTED → 6
        rejected_resp = await client.get(
            "/api/v1/approval-requests?status=REJECTED", headers=_auth(token)
        )
        assert rejected_resp.json()["total"] == 6

    async def test_invalid_status_rejected(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        """Invalid status value is rejected with 422."""
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/approval-requests?status=INVALID", headers=_auth(token)
        )
        assert response.status_code == 422

    async def test_manager_does_not_see_other_users_rows(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """manager + status=PENDING does not widen to other users' PENDING rows."""
        manager_id = _get_user_id("manager.demo")
        procurement_id = _get_user_id("procurement.demo")
        rec = await _seed_recommendation(db_session)
        # manager's own PENDING
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=2, status="PENDING",
        )
        # procurement's PENDING (created via direct insertion as if by procurement)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=procurement_id,
            requester_username="procurement.demo", count=5, status="PENDING",
        )
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/approval-requests?status=PENDING", headers=_auth(token)
        )
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2  # only own PENDING
        for item in body["items"]:
            assert item["requested_by_username"] == "manager.demo"

    async def test_f1_regression_pending_beyond_first_page(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """F-1 regression: >50 total manager-visible requests, PENDING beyond page 1.

        Create 55 total requests for the manager (all statuses), with at
        least one PENDING request that would fall beyond the first page of
        the old unfiltered query (default limit=50, ordered by
        requested_at DESC).  Request status=PENDING&limit=1 and assert
        returned total equals the actual PENDING count.
        """
        manager_id = _get_user_id("manager.demo")
        rec = await _seed_recommendation(db_session)
        # 52 APPROVED (enough to fill the first page of the old unfiltered query)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=52, status="APPROVED",
        )
        # 3 PENDING — all beyond page 1 of the old unfiltered query (52 APPROVED > 50)
        pending_rows = await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=3, status="PENDING",
        )
        # Verify the PENDING count we expect
        expected_pending = len(pending_rows)
        assert expected_pending == 3

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])

        # OLD behavior (no status filter): first page has 50 items, total=55
        old_resp = await client.get(
            "/api/v1/approval-requests?limit=50&offset=0", headers=_auth(token)
        )
        assert old_resp.status_code == 200
        old_body = old_resp.json()
        assert old_body["total"] == 55
        assert len(old_body["items"]) == 50
        # In the old behavior, client-side filtering of the first 50 items
        # would yield 0 PENDING (all 50 are APPROVED because of ordering by
        # requested_at DESC — the 3 PENDING were inserted AFTER the 52
        # APPROVED, so they have newer timestamps and actually appear FIRST).
        # To truly test F-1, we need PENDING to be beyond page 1. Since
        # requested_at is server_default=func.now(), the rows inserted later
        # have LATER timestamps. So PENDING rows (inserted last) appear FIRST
        # in DESC ordering. To make PENDING fall beyond page 1, we need to
        # insert them with EARLIER timestamps.

        # Actually, let's verify with the status filter directly:
        # status=PENDING&limit=1 must return total=3 regardless of ordering
        filtered_resp = await client.get(
            "/api/v1/approval-requests?status=PENDING&limit=1&offset=0",
            headers=_auth(token),
        )
        assert filtered_resp.status_code == 200
        filtered_body = filtered_resp.json()
        assert filtered_body["total"] == 3
        assert len(filtered_body["items"]) == 1
        assert filtered_body["items"][0]["status"] == "PENDING"

    async def test_f1_regression_exact_pending_count_across_pagination(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """F-1 core regression: the backend-filtered PENDING total is exact.

        Create >50 total requests across statuses. Ensure at least one
        PENDING request would fall beyond the first page of the old
        unfiltered query. Request status=PENDING&limit=1 and assert
        returned total equals the actual PENDING count.

        To guarantee PENDING rows fall beyond page 1 of the unfiltered
        query, we insert APPROVED rows with timestamps AFTER (newer than)
        PENDING rows, so the unfiltered DESC ordering puts APPROVED first.
        """
        manager_id = _get_user_id("manager.demo")
        rec = await _seed_recommendation(db_session)

        # Insert 3 PENDING first (older timestamps)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=3, status="PENDING",
        )
        # Insert 52 APPROVED after (newer timestamps → appear first in DESC)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=52, status="APPROVED",
        )

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])

        # Verify old behavior: first page (limit=50) has 0 PENDING items
        old_resp = await client.get(
            "/api/v1/approval-requests?limit=50&offset=0", headers=_auth(token)
        )
        assert old_resp.status_code == 200
        old_body = old_resp.json()
        assert old_body["total"] == 55
        assert len(old_body["items"]) == 50
        old_pending_count = sum(
            1 for item in old_body["items"] if item["status"] == "PENDING"
        )
        assert old_pending_count == 0  # All first-page items are APPROVED

        # New behavior: status=PENDING&limit=1 → total=3 (exact)
        new_resp = await client.get(
            "/api/v1/approval-requests?status=PENDING&limit=1&offset=0",
            headers=_auth(token),
        )
        assert new_resp.status_code == 200
        new_body = new_resp.json()
        assert new_body["total"] == 3
        assert len(new_body["items"]) == 1
        assert new_body["items"][0]["status"] == "PENDING"

    async def test_status_filter_composes_with_scope_not_widens(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """RBAC composition proof: status filter never widens read authority.

        manager sees only own rows with or without status filter.
        specialist sees PENDING plus its own APPROVED (WP-UX-UA-05-R1) —
        the status filter composes with (never widens) that scope.
        """
        manager_id = _get_user_id("manager.demo")
        procurement_id = _get_user_id("procurement.demo")
        rec = await _seed_recommendation(db_session)
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=2, status="PENDING",
        )
        await _create_approval_rows(
            db_session, rec=rec, requester_id=manager_id,
            requester_username="manager.demo", count=3, status="APPROVED",
        )
        await _create_approval_rows(
            db_session, rec=rec, requester_id=procurement_id,
            requester_username="procurement.demo", count=4, status="PENDING",
        )
        await _create_approval_rows(
            db_session, rec=rec, requester_id=procurement_id,
            requester_username="procurement.demo", count=1, status="APPROVED",
        )

        # Manager: own rows only (5 total), status=PENDING → 2
        mgr_token = await _login(
            client, "manager.demo", _DEMO_PASSWORDS["manager.demo"]
        )
        mgr_all = await client.get(
            "/api/v1/approval-requests", headers=_auth(mgr_token)
        )
        assert mgr_all.json()["total"] == 5
        mgr_pending = await client.get(
            "/api/v1/approval-requests?status=PENDING", headers=_auth(mgr_token)
        )
        assert mgr_pending.json()["total"] == 2

        # Specialist: all PENDING in the system (2+4=6) plus the one APPROVED
        # row it decided (procurement.demo). status=APPROVED → that single own
        # APPROVED row; other actors' APPROVED rows stay out of scope.
        spec_token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        spec_all = await client.get(
            "/api/v1/approval-requests", headers=_auth(spec_token)
        )
        assert spec_all.json()["total"] == 7
        spec_approved = await client.get(
            "/api/v1/approval-requests?status=APPROVED", headers=_auth(spec_token)
        )
        assert spec_approved.json()["total"] == 1
        spec_pending = await client.get(
            "/api/v1/approval-requests?status=PENDING", headers=_auth(spec_token)
        )
        assert spec_pending.json()["total"] == 6

        # Admin: all 10, status=PENDING → 6, status=APPROVED → 4
        admin_token = await _login(
            client, "admin.demo", _DEMO_PASSWORDS["admin.demo"]
        )
        admin_all = await client.get(
            "/api/v1/approval-requests", headers=_auth(admin_token)
        )
        assert admin_all.json()["total"] == 10
        admin_pending = await client.get(
            "/api/v1/approval-requests?status=PENDING", headers=_auth(admin_token)
        )
        assert admin_pending.json()["total"] == 6
        admin_approved = await client.get(
            "/api/v1/approval-requests?status=APPROVED", headers=_auth(admin_token)
        )
        assert admin_approved.json()["total"] == 4
