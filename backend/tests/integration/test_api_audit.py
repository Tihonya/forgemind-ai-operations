"""Integration tests for the read-only audit-event API (WP-REC-04B).

Tests the real API endpoints against a live PostgreSQL database:

- GET /audit-events/{event_id} — detail, RBAC, 404, unauthenticated.
- GET /audit-events — deterministic ordering, pagination bounds.
- No audit mutation route exists (405 for POST/PUT/PATCH/DELETE).
- Audit events written via the internal service round-trip through the API
  with secrets redacted and a backend-controlled timestamp.

Requires a live PostgreSQL database (migrated + seeded). Skips cleanly if
unavailable. No provider call occurs; synthetic sentinel values only.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.main import app
from app.models.audit import AuditEvent
from app.models.enums import AuditEntityType, AuditEventType
from app.models.workflow import WorkflowRun
from app.services.audit_service import REDACTED, AuditService

_INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

_DEMO_PASSWORDS = {
    "manager.demo": "ManagerPass123!",
    "procurement.demo": "ProcurementPass123!",
    "engineer.demo": "EngineerPass123!",
    "admin.demo": "AdminPass123!",
    "auditor.demo": "AuditorPass123!",
}


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


def _get_plan_id() -> UUID:
    engine = _get_sync_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id FROM production_plans LIMIT 1")
            ).fetchone()
        assert row is not None, "no production plans seeded"
        return cast(UUID, row[0])
    finally:
        engine.dispose()


async def _login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, (
        f"seed login failed: {response.status_code} {response.text}"
    )
    return cast(str, response.json()["access_token"])


async def _create_run(db_session: AsyncSession, plan_id: UUID) -> WorkflowRun:
    run = WorkflowRun(
        id=uuid4(),
        correlation_id=uuid4(),
        state="COMPLETED",
        plan_id=plan_id,
        triggered_by="manager.demo",
    )
    db_session.add(run)
    await db_session.flush()
    return run


async def _create_event(
    db_session: AsyncSession,
    *,
    event_type: AuditEventType = AuditEventType.APPROVAL_REQUEST_CREATED,
    entity_type: AuditEntityType = AuditEntityType.APPROVAL_REQUEST,
    actor_id: UUID,
    actor_username: str,
    workflow_run_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    service = AuditService(db_session)
    return await service.create_event(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=uuid4(),
        actor_id=actor_id,
        actor_username=actor_username,
        workflow_run_id=workflow_run_id,
        risk_id="RISK-001",
        before_summary={"status": "PENDING"},
        after_summary={"status": "APPROVED"},
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


class TestGetAuditEvent:
    async def test_auditor_can_read(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        actor_id = _get_user_id("manager.demo")
        event = await _create_event(
            db_session, actor_id=actor_id, actor_username="manager.demo"
        )
        await db_session.commit()

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            f"/api/v1/audit-events/{event.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(event.id)
        assert data["event_type"] == "APPROVAL_REQUEST_CREATED"
        assert data["entity_type"] == "APPROVAL_REQUEST"
        assert data["actor_id"] == str(actor_id)
        assert data["actor_username"] == "manager.demo"
        assert data["risk_id"] == "RISK-001"
        assert data["before_summary"] == {"status": "PENDING"}
        assert data["after_summary"] == {"status": "APPROVED"}
        assert data["created_at"] is not None

    async def test_ai_administrator_can_read(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        actor_id = _get_user_id("manager.demo")
        event = await _create_event(
            db_session, actor_id=actor_id, actor_username="manager.demo"
        )
        await db_session.commit()

        token = await _login(client, "admin.demo", _DEMO_PASSWORDS["admin.demo"])
        response = await client.get(
            f"/api/v1/audit-events/{event.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "username",
        ["manager.demo", "procurement.demo", "engineer.demo"],
    )
    async def test_non_audit_roles_denied(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None, username: str,
    ) -> None:
        actor_id = _get_user_id("manager.demo")
        event = await _create_event(
            db_session, actor_id=actor_id, actor_username="manager.demo"
        )
        await db_session.commit()

        token = await _login(client, username, _DEMO_PASSWORDS[username])
        response = await client.get(
            f"/api/v1/audit-events/{event.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "insufficient_permissions"

    async def test_unauthenticated_denied(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        response = await client.get(f"/api/v1/audit-events/{uuid4()}")
        assert response.status_code == 401

    async def test_missing_event_returns_404(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        missing = uuid4()
        response = await client.get(
            f"/api/v1/audit-events/{missing}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "audit_event_not_found"

    async def test_secret_values_are_redacted_in_api_response(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        actor_id = _get_user_id("manager.demo")
        event = await _create_event(
            db_session,
            actor_id=actor_id,
            actor_username="manager.demo",
            metadata={"api_key": "sk-should-never-leak", "reason": "test"},
        )
        await db_session.commit()

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            f"/api/v1/audit-events/{event.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["event_metadata"] == {"api_key": REDACTED, "reason": "test"}
        assert "sk-should-never-leak" not in response.text


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


class TestListAuditEvents:
    async def test_empty_list(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            "/api/v1/audit-events", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["limit"] == 50
        assert data["offset"] == 0

    async def test_deterministic_ordering(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        actor_id = _get_user_id("manager.demo")
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(3):
            db_session.add(
                AuditEvent(
                    id=uuid4(),
                    correlation_id=uuid4(),
                    event_type=AuditEventType.APPROVAL_REQUEST_CREATED.value,
                    entity_type=AuditEntityType.APPROVAL_REQUEST.value,
                    entity_id=uuid4(),
                    actor_id=actor_id,
                    actor_username="manager.demo",
                    created_at=base + timedelta(seconds=i),
                )
            )
        await db_session.commit()

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            "/api/v1/audit-events", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 3
        timestamps = [item["created_at"] for item in items]
        assert timestamps[0] > timestamps[1] > timestamps[2]

    async def test_pagination_bounds_enforced(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])

        too_high = await client.get(
            "/api/v1/audit-events?limit=201",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert too_high.status_code == 422

        too_low = await client.get(
            "/api/v1/audit-events?limit=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert too_low.status_code == 422


# ---------------------------------------------------------------------------
# No mutation route
# ---------------------------------------------------------------------------


class TestNoMutationRoute:
    async def test_post_is_not_allowed(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.post(
            "/api/v1/audit-events",
            headers={"Authorization": f"Bearer {token}"},
            json={"event_type": "APPROVAL_APPROVED"},
        )
        assert response.status_code == 405

    @pytest.mark.parametrize("method", ["put", "patch", "delete"])
    async def test_mutation_verbs_are_not_allowed(
        self, client: AsyncClient, _seeded_golden_dataset: None, method: str,
    ) -> None:
        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.request(
            method, f"/api/v1/audit-events/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert response.status_code == 405
