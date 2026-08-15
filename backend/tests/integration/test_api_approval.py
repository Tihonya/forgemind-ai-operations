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

import os
from collections.abc import AsyncIterator, Generator
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
from app.models.approval import ApprovalRequest
from app.models.audit import AuditEvent
from app.models.workflow import Recommendation, WorkflowRun
from app.schemas.recommendation import RecommendationData, RecommendedAction, RiskItem
from app.services.approval_service import ApprovalService
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
        requester=requester,
    )
    await db_session.commit()
    return approval


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
            json={
                "recommendation_id": str(rec.id),
                "risk_id": RISK_ID,
                "action_type": ACTION_TYPE,
            },
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
        from app.models.approval import compute_binding_hash

        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.post(
            "/api/v1/approval-requests",
            json={
                "recommendation_id": str(rec.id),
                "risk_id": RISK_ID,
                "action_type": ACTION_TYPE,
            },
            headers=_auth(token),
        )
        assert response.status_code == 201
        data = response.json()
        expected = {
            "action_type": ACTION_TYPE,
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
            json={
                "recommendation_id": str(rec.id),
                "risk_id": RISK_ID,
                "action_type": ACTION_TYPE,
            },
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
            json={
                "recommendation_id": str(rec.id),
                "risk_id": RISK_ID,
                "action_type": ACTION_TYPE,
            },
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
            json={
                "recommendation_id": str(rec.id),
                "risk_id": RISK_ID,
                "action_type": ACTION_TYPE,
            },
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
        payload = {
            "recommendation_id": str(rec.id),
            "risk_id": RISK_ID,
            "action_type": ACTION_TYPE,
        }
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
            json={
                "recommendation_id": str(rec.id),
                "risk_id": RISK_ID,
                "action_type": ACTION_TYPE,
            },
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
        # WP-REC-04A owns no procurement-task persistence (04C scope).
        result = await db_session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'procurement_tasks'"
            )
        )
        assert result.fetchone() is None


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
    async def test_correlation_id_propagates_to_audit_event(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        correlation_id = uuid4()
        response = await client.post(
            "/api/v1/approval-requests",
            json={
                "recommendation_id": str(rec.id),
                "risk_id": RISK_ID,
                "action_type": ACTION_TYPE,
            },
            headers={**_auth(token), "X-Correlation-ID": str(correlation_id)},
        )
        assert response.status_code == 201
        request_id = response.json()["id"]
        assert response.json()["correlation_id"] == str(correlation_id)

        result = await db_session.execute(
            select(AuditEvent).where(AuditEvent.entity_id == UUID(request_id))
        )
        event = result.scalars().one()
        assert event.correlation_id == correlation_id

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
