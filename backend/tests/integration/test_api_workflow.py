"""Integration tests for workflow run detail API (WP-REC-03E).

Tests the real API endpoints against a live PostgreSQL database.
Creates workflow runs directly in the test database using ORM models.
Does NOT simulate ARQ or worker execution. Does NOT claim AT-013 or
production worker functionality.

Coverage:

1. GET /workflow-runs/{run_id} returns 200 with run, steps, and recommendation
2. GET /workflow-runs/{run_id} returns 404 for non-existent run
3. GET /workflow-runs/{run_id} returns 200 with recommendation=null
   when no Recommendation row exists
4. GET /workflow-runs/{run_id} returns 200 with content=null when
   Recommendation exists but content is null
5. GET /workflow-runs returns 200 with paginated list — deterministic
   created_at DESC, id DESC ordering
6. GET /workflow-runs returns 200 with empty list when no runs exist
7. GET /workflow-runs/{run_id} returns 200 with FAILED_VALIDATION state —
   error visible in step data (AT-008 backend trace visibility)
8. GET /workflow-runs/{run_id} returns 401 without authentication
9. GET /workflow-runs respects limit/offset parameters
10. GET /workflow-runs/{run_id} returns 500 with stable error code
    when Recommendation has schema-invalid non-null content

Requires a live PostgreSQL database. Uses the already configured project
test environment. Do NOT hardcode or print database passwords.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

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
from app.models.production import ProductionPlan
from app.models.workflow import Recommendation, WorkflowRun, WorkflowStep

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

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
        await session.execute(text("DELETE FROM recommendations"))
        await session.execute(text("DELETE FROM workflow_steps"))
        await session.execute(text("DELETE FROM workflow_runs"))
        # Clean up synthetic plans created by F-3 tests (code starts with PLAN-TEST-SYNTHETIC).
        await session.execute(
            text("DELETE FROM production_plans WHERE code LIKE 'PLAN-TEST-SYNTHETIC-%'")
        )
        await session.commit()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def plan_id_sync() -> Any:
    """Get a production plan ID using a synchronous engine."""
    assert _INTEGRATION_DB_URL is not None
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id FROM production_plans LIMIT 1"))
        row = result.fetchone()
    if row is None:
        pytest.skip("No production plans in database")
    return row[0]


async def _login(client: AsyncClient, username: str, password: str) -> str:
    """Log in and return a bearer access token."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, (
        f"seed login failed: {response.status_code} {response.text}"
    )
    data = response.json()
    token: str = data["access_token"]
    return token


async def _create_run(
    session: AsyncSession,
    plan_id: Any,
    *,
    state: str = "PENDING",
    error_code: str | None = None,
    error_detail: str | None = None,
) -> WorkflowRun:
    """Create a workflow run directly in the database."""
    run = WorkflowRun(
        id=uuid4(),
        correlation_id=uuid4(),
        state=state,
        plan_id=plan_id,
        started_at=datetime.now(UTC) if state != "PENDING" else None,
        completed_at=(
            datetime.now(UTC)
            if state.startswith("FAILED") or state == "COMPLETED"
            else None
        ),
        error_code=error_code,
        error_detail=error_detail,
    )
    session.add(run)
    await session.flush()
    return run


async def _create_step(
    session: AsyncSession,
    run: WorkflowRun,
    *,
    seq: int = 0,
    step_name: str = "provider_call",
    status: str = "started",
    model_name: str | None = None,
    error_code: str | None = None,
    error_detail: str | None = None,
    step_metadata: dict[str, Any] | None = None,
) -> WorkflowStep:
    """Create a workflow step directly in the database."""
    step = WorkflowStep(
        id=uuid4(),
        run_id=run.id,
        correlation_id=run.correlation_id,
        seq=seq,
        step_name=step_name,
        status=status,
        model_name=model_name,
        error_code=error_code,
        error_detail=error_detail,
        step_metadata=step_metadata,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC) if status != "started" else None,
    )
    session.add(step)
    await session.flush()
    return step


async def _create_recommendation(
    session: AsyncSession,
    run: WorkflowRun,
    plan_id: Any,
    *,
    content: dict[str, Any] | None = None,
    schema_version: str = "1.0",
) -> Recommendation:
    """Create a recommendation directly in the database."""
    rec = Recommendation(
        id=uuid4(),
        run_id=run.id,
        plan_id=plan_id,
        status="VALIDATED",
        content=content,
        schema_version=schema_version,
    )
    session.add(rec)
    await session.flush()
    return rec


def _valid_recommendation_content(run_id: str) -> dict[str, Any]:
    """Return a valid RecommendationData-shaped dict."""
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "plan_id": "PLAN-2026-W31",
        "risks": [
            {
                "risk_id": "RISK-001",
                "summary": "Test risk summary",
                "business_impact": "Test business impact",
                "recommended_actions": [
                    {
                        "action_type": "CREATE_PROCUREMENT_TASK",
                        "title": "Test action",
                        "rationale": "Test rationale",
                        "requires_approval": True,
                    }
                ],
                "sources": [
                    {
                        "document_id": "DOC-001",
                        "version": "1.0",
                        "chunk_id": str(uuid4()),
                    }
                ],
            }
        ],
    }


def _get_plan_code(plan_id: Any) -> str:
    """Get the external code for a production plan ID via a sync engine."""
    assert _INTEGRATION_DB_URL is not None
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")
    engine = create_engine(sync_url)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT code FROM production_plans WHERE id = :pid"),
            {"pid": str(plan_id)},
        )
        row = result.fetchone()
    engine.dispose()
    assert row is not None, "Plan must exist"
    return str(row[0])


async def _create_synthetic_plan(
    session: AsyncSession,
    code: str = "PLAN-TEST-SYNTHETIC-001",
) -> ProductionPlan:
    """Create a minimal valid synthetic ProductionPlan in the test transaction.

    This does NOT modify production seed data — the plan is created within
    the test session and cleaned up by the db_session fixture teardown.
    """
    from datetime import date as date_type

    plan = ProductionPlan(
        code=code,
        status="DRAFT",
        period_start=date_type(2026, 6, 1),
        period_end=date_type(2026, 6, 7),
    )
    session.add(plan)
    await session.flush()
    return plan


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetWorkflowRunDetail:
    """GET /api/v1/workflow-runs/{run_id}"""

    async def test_returns_run_with_steps_and_recommendation(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        run = await _create_run(db_session, plan_id_sync, state="COMPLETED")
        await _create_step(
            db_session, run,
            seq=0, status="completed",
            model_name="gpt-4o-mini",
        )
        await _create_recommendation(
            db_session, run, plan_id_sync,
            content=_valid_recommendation_content(str(run.id)),
        )
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs/{run.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(run.id)
        assert data["state"] == "COMPLETED"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["step_name"] == "provider_call"
        assert data["steps"][0]["model_name"] == "gpt-4o-mini"
        assert data["recommendation"] is not None
        assert data["recommendation"]["status"] == "VALIDATED"
        assert data["recommendation"]["content"] is not None
        assert data["recommendation"]["content"]["schema_version"] == "1.0"
        assert len(data["recommendation"]["content"]["risks"]) == 1

    async def test_returns_404_for_nonexistent_run(
        self, client: AsyncClient,
    ) -> None:
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        detail = response.json()["detail"]
        assert detail["error"] == "workflow_run_not_found"
        assert "run_id" in detail

    async def test_returns_recommendation_null_when_no_row(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        run = await _create_run(db_session, plan_id_sync, state="COMPLETED")
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs/{run.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["recommendation"] is None

    async def test_returns_content_null_when_recommendation_content_is_null(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        run = await _create_run(db_session, plan_id_sync, state="AWAITING_VALIDATION")
        await _create_recommendation(
            db_session, run, plan_id_sync, content=None,
        )
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs/{run.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["recommendation"] is not None
        assert data["recommendation"]["content"] is None

    async def test_returns_failed_validation_with_error_in_steps(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        run = await _create_run(
            db_session, plan_id_sync,
            state="FAILED_VALIDATION",
            error_code="VALIDATION_ERROR",
            error_detail="StructuredOutputValidationError",
        )
        await _create_step(
            db_session, run,
            seq=0, status="failed",
            error_code="VALIDATION_ERROR",
            error_detail="INVALID_SCHEMA",
        )
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs/{run.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "FAILED_VALIDATION"
        assert data["error_code"] == "VALIDATION_ERROR"
        assert len(data["steps"]) == 1
        assert data["steps"][0]["error_code"] == "VALIDATION_ERROR"
        assert data["steps"][0]["error_detail"] == "INVALID_SCHEMA"

    async def test_returns_401_without_auth(
        self, client: AsyncClient,
    ) -> None:
        response = await client.get(
            f"/api/v1/workflow-runs/{uuid4()}",
        )
        assert response.status_code == 401

    async def test_invalid_recommendation_content_returns_500(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        run = await _create_run(db_session, plan_id_sync, state="COMPLETED")
        await _create_recommendation(
            db_session, run, plan_id_sync,
            content={"invalid": "not a valid RecommendationData"},
        )
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs/{run.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 500
        detail = response.json()["detail"]
        assert detail["error"] == "invalid_recommendation_content"
        # Must not leak the raw payload or validation details
        response_text = response.text
        assert "not a valid RecommendationData" not in response_text
        assert "validation" not in response_text.lower()


class TestListWorkflowRuns:
    """GET /api/v1/workflow-runs"""

    async def test_returns_empty_list_when_no_runs(
        self, client: AsyncClient,
    ) -> None:
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/workflow-runs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["limit"] == 50
        assert data["offset"] == 0

    async def test_returns_paginated_list(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        # Create 3 runs with different timestamps for deterministic ordering
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(3):
            run = WorkflowRun(
                id=uuid4(),
                correlation_id=uuid4(),
                state="PENDING",
                plan_id=plan_id_sync,
                created_at=base + timedelta(seconds=i),
            )
            db_session.add(run)
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/workflow-runs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3
        # Ordering: created_at DESC — newest first
        timestamps = [item["created_at"] for item in data["items"]]
        assert timestamps[0] > timestamps[1] > timestamps[2]
        # No steps or recommendation in summary items
        assert "steps" not in data["items"][0]
        assert "recommendation" not in data["items"][0]

    async def test_respects_limit_and_offset(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(3):
            run = WorkflowRun(
                id=uuid4(),
                correlation_id=uuid4(),
                state="PENDING",
                plan_id=plan_id_sync,
                created_at=base + timedelta(seconds=i),
            )
            db_session.add(run)
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])

        # Page 1: limit=2, offset=0
        response = await client.get(
            "/api/v1/workflow-runs?limit=2&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["limit"] == 2
        assert data["offset"] == 0

        # Page 2: limit=2, offset=2
        response = await client.get(
            "/api/v1/workflow-runs?limit=2&offset=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 3
        assert data["limit"] == 2
        assert data["offset"] == 2


class TestListWorkflowRunsPlanCodeFilter:
    """GET /api/v1/workflow-runs?plan_code=... — WP-UX-02 plan filter.

    Tests the backward-compatible ``plan_code`` query parameter that
    lets the frontend ask for the latest run belonging to a specific
    production plan identified by its external code (e.g.
    ``PLAN-2026-W31``).
    """

    async def test_no_filter_preserves_unfiltered_list_behavior(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        """Without plan_code, the endpoint returns all runs (backward compat)."""
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(2):
            run = WorkflowRun(
                id=uuid4(),
                correlation_id=uuid4(),
                state="PENDING",
                plan_id=plan_id_sync,
                created_at=base + timedelta(seconds=i),
            )
            db_session.add(run)
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/workflow-runs",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_valid_plan_filter_returns_only_that_plans_runs(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        """plan_code filter returns only runs for the specified plan.

        F-3 FIX: Also creates a run for a synthetic second plan to prove
        that the filter excludes cross-plan runs, not just same-plan.
        """
        plan_code = _get_plan_code(plan_id_sync)

        # Create a synthetic second plan with a run.
        plan_b = await _create_synthetic_plan(db_session, code="PLAN-TEST-SYNTHETIC-VPF")
        run_other = WorkflowRun(
            id=uuid4(),
            correlation_id=uuid4(),
            state="PENDING",
            plan_id=plan_b.id,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        db_session.add(run_other)

        # Create 3 runs for this plan.
        base = datetime(2026, 1, 1, tzinfo=UTC)
        for i in range(3):
            run = WorkflowRun(
                id=uuid4(),
                correlation_id=uuid4(),
                state="PENDING",
                plan_id=plan_id_sync,
                created_at=base + timedelta(seconds=i),
            )
            db_session.add(run)
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs?plan_code={plan_code}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        # All items belong to the requested plan (plan_id matches).
        for item in data["items"]:
            assert item["plan_id"] == str(plan_id_sync)

    async def test_total_is_filtered(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        """total reflects only the filtered plan's runs, not all runs.

        F-3 FIX: Uses a synthetic second plan to prove that runs from a
        different plan are excluded from the filtered total.
        """
        plan_a_code = _get_plan_code(plan_id_sync)

        # Create a synthetic second plan.
        plan_b = await _create_synthetic_plan(db_session, code="PLAN-TEST-SYNTHETIC-TTF")
        await db_session.commit()

        base = datetime(2026, 1, 1, tzinfo=UTC)
        # 2 runs for plan A.
        for i in range(2):
            run = WorkflowRun(
                id=uuid4(),
                correlation_id=uuid4(),
                state="PENDING",
                plan_id=plan_id_sync,
                created_at=base + timedelta(seconds=i),
            )
            db_session.add(run)
        # 3 runs for plan B.
        for i in range(3):
            run = WorkflowRun(
                id=uuid4(),
                correlation_id=uuid4(),
                state="PENDING",
                plan_id=plan_b.id,
                created_at=base + timedelta(seconds=i),
            )
            db_session.add(run)
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs?plan_code={plan_a_code}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        # total must be 2 (plan A only), not 5 (A+B).
        assert data["total"] == 2

    async def test_limit_one_returns_latest_run_while_total_remains_full(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        """limit=1 returns the latest run while total stays the full count."""
        sync_url = _INTEGRATION_DB_URL
        assert sync_url is not None
        if "+asyncpg" in sync_url:
            sync_url = sync_url.replace("+asyncpg", "+psycopg")
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT code FROM production_plans WHERE id = :pid"),
                {"pid": str(plan_id_sync)},
            )
            plan_row = result.fetchone()
            assert plan_row is not None, "Plan must exist"
            plan_code = plan_row[0]
        engine.dispose()

        base = datetime(2026, 1, 1, tzinfo=UTC)
        run_ids = []
        for i in range(3):
            rid = uuid4()
            run_ids.append(rid)
            run = WorkflowRun(
                id=rid,
                correlation_id=uuid4(),
                state="PENDING",
                plan_id=plan_id_sync,
                created_at=base + timedelta(seconds=i),
            )
            db_session.add(run)
        await db_session.commit()

        # The newest run is the last one created (created_at = base + 2s).
        expected_newest_id = run_ids[-1]

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs?plan_code={plan_code}&limit=1&offset=0",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 3
        # The single returned run must be the newest one (created_at DESC).
        assert data["items"][0]["id"] == str(expected_newest_id)

    async def test_deterministic_tie_order_contract_remains_correct(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        """Tie-breaker ordering (created_at DESC, id DESC) is stable."""
        sync_url = _INTEGRATION_DB_URL
        assert sync_url is not None
        if "+asyncpg" in sync_url:
            sync_url = sync_url.replace("+asyncpg", "+psycopg")
        engine = create_engine(sync_url)
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT code FROM production_plans WHERE id = :pid"),
                {"pid": str(plan_id_sync)},
            )
            plan_row = result.fetchone()
            assert plan_row is not None, "Plan must exist"
            plan_code = plan_row[0]
        engine.dispose()

        # Create runs with identical timestamps to test tie-breaker.
        same_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        run_ids = []
        for _ in range(3):
            rid = uuid4()
            run_ids.append(rid)
            run = WorkflowRun(
                id=rid,
                correlation_id=uuid4(),
                state="PENDING",
                plan_id=plan_id_sync,
                created_at=same_time,
            )
            db_session.add(run)
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs?plan_code={plan_code}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        # All 3 returned.
        assert len(data["items"]) == 3
        # Tie-breaker: id DESC (UUID string comparison, descending).
        returned_ids = [item["id"] for item in data["items"]]
        assert returned_ids == sorted(returned_ids, reverse=True)

    async def test_another_plan_newer_run_cannot_displace_requested_plan_latest(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        """A newer run from a different plan does not appear in filtered results.

        F-3 FIX: Creates a synthetic second ProductionPlan within the test
        transaction so this test always runs in CI (previously skipped when
        only one plan was seeded).
        """
        plan_a_code = _get_plan_code(plan_id_sync)

        # Create a synthetic second plan.
        plan_b = await _create_synthetic_plan(db_session, code="PLAN-TEST-SYNTHETIC-XPL")
        await db_session.commit()

        # Create an old run for plan A.
        base_old = datetime(2026, 1, 1, tzinfo=UTC)
        run_old = WorkflowRun(
            id=uuid4(),
            correlation_id=uuid4(),
            state="COMPLETED",
            plan_id=plan_id_sync,
            created_at=base_old,
        )
        db_session.add(run_old)

        # Create a newer run for plan B.
        run_new_other = WorkflowRun(
            id=uuid4(),
            correlation_id=uuid4(),
            state="COMPLETED",
            plan_id=plan_b.id,
            created_at=base_old + timedelta(hours=1),
        )
        db_session.add(run_new_other)
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            f"/api/v1/workflow-runs?plan_code={plan_a_code}&limit=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        # The returned run must be from plan A, not plan B.
        assert data["items"][0]["plan_id"] == str(plan_id_sync)

    async def test_cross_plan_filtered_total_and_items(
        self, client: AsyncClient, db_session: AsyncSession, plan_id_sync: Any,
    ) -> None:
        """F-3: Cross-plan filtered total and item isolation with mixed plans.

        Plan A has 2 runs, plan B has 1 run. Querying plan A returns total=2
        and only plan-A items. Querying plan B returns total=1 and only
        plan-B items.
        """
        plan_a_code = _get_plan_code(plan_id_sync)
        plan_b = await _create_synthetic_plan(db_session, code="PLAN-TEST-SYNTHETIC-CPT")
        await db_session.commit()

        base = datetime(2026, 1, 1, tzinfo=UTC)
        # 2 runs for plan A.
        for i in range(2):
            run = WorkflowRun(
                id=uuid4(),
                correlation_id=uuid4(),
                state="PENDING",
                plan_id=plan_id_sync,
                created_at=base + timedelta(seconds=i),
            )
            db_session.add(run)
        # 1 run for plan B.
        run_b = WorkflowRun(
            id=uuid4(),
            correlation_id=uuid4(),
            state="PENDING",
            plan_id=plan_b.id,
            created_at=base + timedelta(hours=1),
        )
        db_session.add(run_b)
        await db_session.commit()

        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])

        # Query plan A.
        resp_a = await client.get(
            f"/api/v1/workflow-runs?plan_code={plan_a_code}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_a.status_code == 200
        data_a = resp_a.json()
        assert data_a["total"] == 2
        assert len(data_a["items"]) == 2
        for item in data_a["items"]:
            assert item["plan_id"] == str(plan_id_sync)

        # Query plan B.
        resp_b = await client.get(
            "/api/v1/workflow-runs?plan_code=PLAN-TEST-SYNTHETIC-CPT",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp_b.status_code == 200
        data_b = resp_b.json()
        assert data_b["total"] == 1
        assert len(data_b["items"]) == 1
        assert data_b["items"][0]["plan_id"] == str(plan_b.id)

    async def test_no_authorization_regression(
        self, client: AsyncClient,
    ) -> None:
        """Unauthenticated requests are still rejected with 401."""
        response = await client.get(
            "/api/v1/workflow-runs?plan_code=PLAN-2026-W31",
        )
        assert response.status_code == 401

    async def test_unknown_plan_code_returns_empty_with_zero_total(
        self, client: AsyncClient,
    ) -> None:
        """Unknown plan code returns 200 with empty list and total=0."""
        token = await _login(client, "manager.demo", _DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            "/api/v1/workflow-runs?plan_code=NONEXISTENT-PLAN-999",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["limit"] == 50
        assert data["offset"] == 0
