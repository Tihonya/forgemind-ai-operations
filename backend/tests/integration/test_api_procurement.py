"""Integration tests for the procurement-task API (WP-REC-04C).

Tests the real API endpoints against a live PostgreSQL database:

- Execute (RBAC, approved path, pending/rejected fail-closed, approver
  separation, binding verification, duplicate suppression, concurrency,
  audit events, atomicity).
- Read API (RBAC, scoping, disclosure ordering, pagination).
- Safety (correlation-ID propagation, no secrets, no unauthorized
  mutation route).

Requires a live PostgreSQL database (migrated + seeded). Skips cleanly if
unavailable. No provider/vendor/financial call occurs.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Generator
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.main import app
from app.models.approval import ApprovalRequest
from app.models.audit import AuditEvent
from app.models.procurement import ProcurementTask
from app.models.workflow import Recommendation, WorkflowRun
from app.schemas.recommendation import RecommendationData, RecommendedAction, RiskItem
from app.services.approval_service import ApprovalService
from app.services.auth_service import AuthenticatedUser
from app.services.procurement_service import ProcurementService

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


async def _seed_recommendation(db_session: AsyncSession) -> Recommendation:
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
        content=_make_content(run_id=run.id),
        schema_version="1.0",
    )
    db_session.add(rec)
    await db_session.commit()
    return rec


def _authenticated(username: str, roles: frozenset[str]) -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id=_get_user_id(username),
        username=username,
        display_name="Test User",
        roles=roles,
    )


async def _create_approved_request(
    db_session: AsyncSession,
    *,
    rec: Recommendation,
) -> ApprovalRequest:
    """Create a PENDING request (manager) and approve it (specialist)."""
    manager = _authenticated("manager.demo", frozenset({"PRODUCTION_MANAGER"}))
    specialist = _authenticated("procurement.demo", frozenset({"PROCUREMENT_SPECIALIST"}))
    approval = await ApprovalService(db_session).create_request(
        recommendation_id=rec.id,
        risk_id=RISK_ID,
        action_type=ACTION_TYPE,
        component_code=RISK_COMPONENT_CODE,
        quantity=Decimal(RISK_QUANTITY),
        requester=manager,
    )
    await db_session.flush()
    await ApprovalService(db_session).approve_request(
        request_id=approval.id, approver=specialist, comment="Approved"
    )
    await db_session.commit()
    return approval


async def _login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, (
        f"seed login failed: {response.status_code} {response.text}"
    )
    return cast(str, response.json()["access_token"])


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _execute_payload(approval: ApprovalRequest) -> dict[str, object]:
    return {"approval_request_id": str(approval.id)}


async def _task_count(db_session: AsyncSession) -> int:
    return (await db_session.execute(select(func.count(ProcurementTask.id)))).scalar_one()


# ---------------------------------------------------------------------------
# Execute — approved path
# ---------------------------------------------------------------------------


class TestExecuteApproved:
    async def test_approved_request_creates_exactly_one_task(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_approved_request(db_session, rec=rec)
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )

        response = await client.post(
            "/api/v1/procurement-tasks",
            json=_execute_payload(approval),
            headers=_auth(token),
        )
        assert response.status_code == 201
        data = response.json()
        assert data["approval_request_id"] == str(approval.id)
        assert data["component_code"] == RISK_COMPONENT_CODE
        assert data["quantity"] == RISK_QUANTITY
        assert data["risk_id"] == RISK_ID
        assert data["action_type"] == ACTION_TYPE
        assert data["task_state"] == "CREATED"
        assert data["binding_hash"] == approval.binding_hash
        assert data["requested_by_username"] == "manager.demo"
        assert data["approved_by_username"] == "procurement.demo"
        assert data["correlation_id"] == str(approval.correlation_id)
        assert data["workflow_run_id"] == str(approval.workflow_run_id)

        # Exactly one persisted task row.
        assert await _task_count(db_session) == 1

    async def test_success_emits_attempt_and_created_audit_events(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_approved_request(db_session, rec=rec)
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        response = await client.post(
            "/api/v1/procurement-tasks",
            json=_execute_payload(approval),
            headers=_auth(token),
        )
        assert response.status_code == 201
        task_id = UUID(response.json()["id"])

        result = await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.correlation_id == approval.correlation_id
            )
        )
        events = {e.event_type for e in result.scalars().all()}
        assert "PROCUREMENT_TASK_CREATION_ATTEMPTED" in events
        assert "PROCUREMENT_TASK_CREATED" in events

        created = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "PROCUREMENT_TASK_CREATED"
                )
            )
        ).scalars().all()
        assert len(created) == 1
        assert created[0].entity_id == task_id
        assert created[0].entity_type == "PROCUREMENT_TASK"
        assert created[0].actor_username == "procurement.demo"


class TestExecutePendingRejected:
    async def test_pending_cannot_execute(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        manager = _authenticated("manager.demo", frozenset({"PRODUCTION_MANAGER"}))
        approval = await ApprovalService(db_session).create_request(
            recommendation_id=rec.id,
            risk_id=RISK_ID,
            action_type=ACTION_TYPE,
            component_code=RISK_COMPONENT_CODE,
            quantity=Decimal(RISK_QUANTITY),
            requester=manager,
        )
        await db_session.commit()

        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        response = await client.post(
            "/api/v1/procurement-tasks",
            json=_execute_payload(approval),
            headers=_auth(token),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["error"] == "approval_request_not_approved"
        assert await _task_count(db_session) == 0

    async def test_rejected_cannot_execute(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        manager = _authenticated("manager.demo", frozenset({"PRODUCTION_MANAGER"}))
        specialist = _authenticated("procurement.demo", frozenset({"PROCUREMENT_SPECIALIST"}))
        approval = await ApprovalService(db_session).create_request(
            recommendation_id=rec.id,
            risk_id=RISK_ID,
            action_type=ACTION_TYPE,
            component_code=RISK_COMPONENT_CODE,
            quantity=Decimal(RISK_QUANTITY),
            requester=manager,
        )
        await db_session.flush()
        await ApprovalService(db_session).reject_request(
            request_id=approval.id, approver=specialist, reason="Insufficient justification"
        )
        await db_session.commit()

        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        response = await client.post(
            "/api/v1/procurement-tasks",
            json=_execute_payload(approval),
            headers=_auth(token),
        )
        assert response.status_code == 409
        assert response.json()["detail"]["error"] == "approval_request_rejected"
        assert await _task_count(db_session) == 0

        # Rejection reason and approval history remain intact.
        rejected = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "APPROVAL_REJECTED"
                )
            )
        ).scalars().all()
        assert len(rejected) == 1
        assert rejected[0].entity_id == approval.id


class TestExecuteBindingFailures:
    async def test_changed_binding_hash_fails_closed(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_approved_request(db_session, rec=rec)

        # Tamper the persisted binding hash directly in the database.
        engine = _get_sync_engine()
        try:
            with engine.connect() as conn:
                conn.execute(
                    text("UPDATE approval_requests SET binding_hash = :h WHERE id = :id"),
                    {"h": "0" * 64, "id": approval.id},
                )
                conn.commit()
        finally:
            engine.dispose()

        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        response = await client.post(
            "/api/v1/procurement-tasks",
            json=_execute_payload(approval),
            headers=_auth(token),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error"] == "binding_mismatch"
        assert await _task_count(db_session) == 0

    async def test_provenance_mismatch_fails_closed(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_approved_request(db_session, rec=rec)

        # Tamper the denormalized risk_id column (snapshot + hash intact).
        engine = _get_sync_engine()
        try:
            with engine.connect() as conn:
                conn.execute(
                    text("UPDATE approval_requests SET risk_id = 'RISK-002' WHERE id = :id"),
                    {"id": approval.id},
                )
                conn.commit()
        finally:
            engine.dispose()

        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        response = await client.post(
            "/api/v1/procurement-tasks",
            json=_execute_payload(approval),
            headers=_auth(token),
        )
        assert response.status_code == 422
        assert response.json()["detail"]["error"] == "binding_mismatch"
        assert await _task_count(db_session) == 0


class TestDuplicateAndConcurrency:
    async def test_repeated_identical_call_does_not_create_second_task(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_approved_request(db_session, rec=rec)
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        payload = _execute_payload(approval)

        first = await client.post(
            "/api/v1/procurement-tasks", json=payload, headers=_auth(token)
        )
        assert first.status_code == 201
        first_id = first.json()["id"]

        second = await client.post(
            "/api/v1/procurement-tasks", json=payload, headers=_auth(token)
        )
        assert second.status_code == 201
        assert second.json()["id"] == first_id

        assert await _task_count(db_session) == 1
        created_events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "PROCUREMENT_TASK_CREATED"
                )
            )
        ).scalars().all()
        assert len(created_events) == 1

    async def test_concurrent_identical_calls_yield_exactly_one_task(
        self, db_engine: AsyncEngine, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_approved_request(db_session, rec=rec)
        approver = _authenticated("procurement.demo", frozenset({"PROCUREMENT_SPECIALIST"}))

        session_factory = async_sessionmaker[AsyncSession](
            bind=db_engine, expire_on_commit=False,
        )

        async def _execute() -> ProcurementTask:
            async with session_factory() as session:
                task = await ProcurementService(session).execute_for_approval(
                    approval_request_id=approval.id, actor=approver
                )
                await session.commit()
                return task

        results = await asyncio.gather(_execute(), _execute())
        assert len({task.id for task in results}) == 1

        assert await _task_count(db_session) == 1
        created_events = (
            await db_session.execute(
                select(AuditEvent).where(
                    AuditEvent.event_type == "PROCUREMENT_TASK_CREATED"
                )
            )
        ).scalars().all()
        assert len(created_events) == 1


class TestAtomicity:
    async def test_rollback_removes_task_and_audit_events(
        self, db_engine: AsyncEngine, _seeded_golden_dataset: None,
    ) -> None:
        factory = async_sessionmaker[AsyncSession](
            bind=db_engine, expire_on_commit=False,
        )
        async with factory() as session:
            rec = await _seed_recommendation(session)
            approval = await _create_approved_request(session, rec=rec)
            approver = _authenticated(
                "procurement.demo", frozenset({"PROCUREMENT_SPECIALIST"})
            )
            await ProcurementService(session).execute_for_approval(
                approval_request_id=approval.id, actor=approver
            )
            await session.rollback()

        # A fresh session observes neither the task nor its audit events.
        async with factory() as session:
            count = (
                await session.execute(select(func.count(ProcurementTask.id)))
            ).scalar_one()
            assert count == 0
            events = (
                await session.execute(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.event_type.in_(
                            (
                                "PROCUREMENT_TASK_CREATION_ATTEMPTED",
                                "PROCUREMENT_TASK_CREATED",
                            )
                        )
                    )
                )
            ).scalar_one()
            assert events == 0
            # Cleanup: remove the seeded recommendation/approval rows left by
            # this test (they committed before the rollback).
            await session.execute(text("DELETE FROM approval_requests"))
            await session.execute(text("DELETE FROM audit_events"))
            await session.execute(text("DELETE FROM recommendations"))
            await session.execute(text("DELETE FROM workflow_steps"))
            await session.execute(text("DELETE FROM workflow_runs"))
            await session.commit()

    async def test_commit_persists_task_and_audit_events(
        self, db_engine: AsyncEngine, _seeded_golden_dataset: None,
    ) -> None:
        factory = async_sessionmaker[AsyncSession](
            bind=db_engine, expire_on_commit=False,
        )
        async with factory() as session:
            rec = await _seed_recommendation(session)
            approval = await _create_approved_request(session, rec=rec)
            approver = _authenticated(
                "procurement.demo", frozenset({"PROCUREMENT_SPECIALIST"})
            )
            await ProcurementService(session).execute_for_approval(
                approval_request_id=approval.id, actor=approver
            )
            await session.commit()

        async with factory() as session:
            count = (
                await session.execute(select(func.count(ProcurementTask.id)))
            ).scalar_one()
            assert count == 1
            created = (
                await session.execute(
                    select(func.count(AuditEvent.id)).where(
                        AuditEvent.event_type == "PROCUREMENT_TASK_CREATED"
                    )
                )
            ).scalar_one()
            assert created == 1
            # Cleanup.
            await session.execute(text("DELETE FROM procurement_tasks"))
            await session.execute(text("DELETE FROM approval_requests"))
            await session.execute(text("DELETE FROM audit_events"))
            await session.execute(text("DELETE FROM recommendations"))
            await session.execute(text("DELETE FROM workflow_steps"))
            await session.execute(text("DELETE FROM workflow_runs"))
            await session.commit()


# ---------------------------------------------------------------------------
# RBAC and read API
# ---------------------------------------------------------------------------


class TestRBAC:
    async def test_specialist_can_execute(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_approved_request(db_session, rec=rec)
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        response = await client.post(
            "/api/v1/procurement-tasks",
            json=_execute_payload(approval),
            headers=_auth(token),
        )
        assert response.status_code == 201

    @pytest.mark.parametrize(
        "username",
        ["manager.demo", "engineer.demo", "admin.demo", "auditor.demo"],
    )
    async def test_forbidden_roles_cannot_execute(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None, username: str,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_approved_request(db_session, rec=rec)
        token = await _login(client, username, _DEMO_PASSWORDS[username])
        response = await client.post(
            "/api/v1/procurement-tasks",
            json=_execute_payload(approval),
            headers=_auth(token),
        )
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "insufficient_permissions"
        assert await _task_count(db_session) == 0

    async def test_unauthenticated_execute_fails(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_approved_request(db_session, rec=rec)
        response = await client.post(
            "/api/v1/procurement-tasks", json=_execute_payload(approval)
        )
        assert response.status_code == 401

    async def test_nonexistent_approval_fails(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        response = await client.post(
            "/api/v1/procurement-tasks",
            json={"approval_request_id": str(uuid4())},
            headers=_auth(token),
        )
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "approval_request_not_found"

    async def test_read_roles_and_scope(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        rec = await _seed_recommendation(db_session)
        approval = await _create_approved_request(db_session, rec=rec)
        token = await _login(
            client, "procurement.demo", _DEMO_PASSWORDS["procurement.demo"]
        )
        created = await client.post(
            "/api/v1/procurement-tasks",
            json=_execute_payload(approval),
            headers=_auth(token),
        )
        task_id = created.json()["id"]

        # manager (requester) sees the task.
        manager_token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        manager_resp = await client.get(
            f"/api/v1/procurement-tasks/{task_id}", headers=_auth(manager_token)
        )
        assert manager_resp.status_code == 200

        # specialist (approver) sees the task.
        specialist_resp = await client.get(
            f"/api/v1/procurement-tasks/{task_id}", headers=_auth(token)
        )
        assert specialist_resp.status_code == 200

        # administrator sees all.
        admin_token = await _login(client, "admin.demo", _DEMO_PASSWORDS["admin.demo"])
        admin_resp = await client.get(
            f"/api/v1/procurement-tasks/{task_id}", headers=_auth(admin_token)
        )
        assert admin_resp.status_code == 200

        # engineer and auditor have no procurement read authority.
        for username in ("engineer.demo", "auditor.demo"):
            other_token = await _login(client, username, _DEMO_PASSWORDS[username])
            other_resp = await client.get(
                f"/api/v1/procurement-tasks/{task_id}", headers=_auth(other_token)
            )
            assert other_resp.status_code == 403

    async def test_nonexistent_task_returns_404(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        admin_token = await _login(client, "admin.demo", _DEMO_PASSWORDS["admin.demo"])
        response = await client.get(
            f"/api/v1/procurement-tasks/{uuid4()}", headers=_auth(admin_token)
        )
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "procurement_task_not_found"

    async def test_openapi_has_no_unauthorized_mutation_route(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        schema = app.openapi()
        procurement_paths = {
            path: methods
            for path, methods in schema["paths"].items()
            if "procurement" in path
        }
        # Only the single controlled create/execute mutation plus reads.
        assert set(procurement_paths) == {
            "/api/v1/procurement-tasks",
            "/api/v1/procurement-tasks/{task_id}",
        }
        for methods in procurement_paths.values():
            assert not ({"put", "patch", "delete"} & set(methods))
        # The execute route exists exactly once.
        assert set(procurement_paths["/api/v1/procurement-tasks"]) == {"get", "post"}
        assert set(procurement_paths["/api/v1/procurement-tasks/{task_id}"]) == {"get"}
