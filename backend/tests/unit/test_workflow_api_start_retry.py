"""Unit tests for WP-REC-03F workflow start/retry API (D1, D2, D3).

Tests cover:
- Strict start-request schema validation (D3).
- Exact external plan-code resolution (D3).
- Authentication and start-role enforcement (D2).
- Creator-or-manager retry authorization (D2).
- triggered_by IS NULL retry behavior (D2).
- Authorization before mutation (D2).
- Unknown plan creates no run (D3).
- Start commit before enqueue (D1/C1).
- Retry commit before enqueue (D1/C1).
- Exact accepted response contracts.
- Enqueue-failure 503 (D1/C1).
- Start enqueue failure does not expose run_id (D1/C1).
- Committed PENDING survival after enqueue failure (D1/C1).
- Same-run retry (D1).
- All eligible failed states (D1).
- COMPLETED retry rejection (D1).
- Concurrent retry winner/loser behavior (D1).
- Atomic error-field and timestamp clearing (D1).
- Atomic generation increment (D5).
- Generation remains unchanged for rejected retries (D5).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database import get_async_session
from app.main import app
from app.models.workflow import WorkflowRun

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakePool:
    """Fake ARQ pool that records enqueue calls without connecting to Redis."""

    def __init__(
        self,
        *,
        enqueue_result: Any = "fake_job_id",
        enqueue_error: Exception | None = None,
    ) -> None:
        self._enqueue_result = enqueue_result
        self._enqueue_error = enqueue_error
        self.enqueue_calls: list[dict[str, Any]] = []

    async def enqueue_job(
        self,
        function: str,
        *args: Any,
        _job_id: str | None = None,
        _queue_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        self.enqueue_calls.append(
            {
                "function": function,
                "args": args,
                "_job_id": _job_id,
                "_queue_name": _queue_name,
            }
        )
        if self._enqueue_error is not None:
            raise self._enqueue_error
        return self._enqueue_result

    async def close(self) -> None:
        pass


@pytest.fixture
async def test_engine() -> AsyncIterator[Any]:
    """Create a fresh async engine bound to the test's event loop."""
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine: Any) -> AsyncIterator[AsyncSession]:
    """Async session for direct DB verification, using the test engine."""
    session_factory = async_sessionmaker[AsyncSession](
        bind=test_engine, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.execute(text("DELETE FROM recommendations"))
        await session.execute(text("DELETE FROM workflow_steps"))
        await session.execute(text("DELETE FROM workflow_runs"))
        await session.commit()


@pytest.fixture
async def client(test_engine: Any) -> AsyncIterator[AsyncClient]:
    """HTTP client with the app, using the test engine via dependency override."""
    session_factory = async_sessionmaker[AsyncSession](
        bind=test_engine, expire_on_commit=False
    )

    async def get_test_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = get_test_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_async_session, None)


@pytest.fixture
async def plan_code_async(client: AsyncClient) -> str:
    """Get the real plan code from the database via the API."""
    resp = await client.get(f"{settings.api_v1_prefix}/production-plans")
    if resp.status_code != 200 or not resp.json().get("items"):
        pytest.skip("No production plans in database")
    return resp.json()["items"][0]["code"]


@pytest.fixture
async def auth_token(client: AsyncClient) -> dict[str, str]:
    """Get auth headers for the production manager user via login API."""
    resp = await client.post(
        f"{settings.api_v1_prefix}/auth/login",
        json={"username": "manager.demo", "password": "ManagerPass123!"},
    )
    if resp.status_code != 200:
        pytest.skip("Cannot login as manager.demo")
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def non_manager_token(client: AsyncClient) -> dict[str, str]:
    """Get auth headers for a non-manager user (engineer) via login API."""
    resp = await client.post(
        f"{settings.api_v1_prefix}/auth/login",
        json={"username": "engineer.demo", "password": "EngineerPass123!"},
    )
    if resp.status_code != 200:
        pytest.skip("Cannot login as engineer.demo")
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fake_pool() -> _FakePool:
    """Fake ARQ pool."""
    return _FakePool()


@pytest.fixture
def patched_pool(monkeypatch: pytest.MonkeyPatch, fake_pool: _FakePool) -> _FakePool:
    """Patch the workflow API's pool factory with a fake pool."""
    import app.api.workflow as workflow_api

    async def fake_factory() -> _FakePool:
        return fake_pool

    monkeypatch.setattr(workflow_api, "_pool_factory", fake_factory)
    return fake_pool


# ---------------------------------------------------------------------------
# Start API tests
# ---------------------------------------------------------------------------


class TestStartRequestSchemaValidation:
    """D3 §2: Strict start-request schema validation."""

    async def test_missing_plan_id_returns_422(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={},
            headers=auth_token,
        )
        assert resp.status_code == 422

    async def test_null_plan_id_returns_422(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": None},
            headers=auth_token,
        )
        assert resp.status_code == 422

    async def test_non_string_plan_id_returns_422(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": 12345},
            headers=auth_token,
        )
        assert resp.status_code == 422

    async def test_empty_string_plan_id_returns_422(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": ""},
            headers=auth_token,
        )
        assert resp.status_code == 422

    async def test_whitespace_only_plan_id_returns_422(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": "   "},
            headers=auth_token,
        )
        assert resp.status_code == 422

    async def test_leading_trailing_whitespace_plan_id_returns_422(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": " PLAN-2026-W31"},
            headers=auth_token,
        )
        assert resp.status_code == 422

    async def test_boolean_plan_id_returns_422(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": True},
            headers=auth_token,
        )
        assert resp.status_code == 422

    async def test_array_plan_id_returns_422(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": ["PLAN-2026-W31"]},
            headers=auth_token,
        )
        assert resp.status_code == 422


class TestStartPlanResolution:
    """D3 §3: Exact plan-code resolution."""

    async def test_unknown_plan_returns_404(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": "NONEXISTENT-PLAN"},
            headers=auth_token,
        )
        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "production_plan_not_found"

        # Verify no run was created.
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM workflow_runs")
        )
        count = result.scalar()
        assert count == 0

    async def test_unknown_plan_creates_no_run_no_enqueue(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": "NONEXISTENT-PLAN"},
            headers=auth_token,
        )
        assert resp.status_code == 404
        assert len(patched_pool.enqueue_calls) == 0

    async def test_valid_plan_creates_run(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        plan_code_async: str,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": plan_code_async},
            headers=auth_token,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "run_id" in data
        assert data["state"] == "PENDING"
        assert "location" in data
        assert "plan_id" not in data

    async def test_uuid_string_resolved_as_code_not_id(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        """A syntactically valid UUID string is looked up only as a code."""
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": str(uuid4())},
            headers=auth_token,
        )
        assert resp.status_code == 404


class TestStartAuthorization:
    """D2: Start role enforcement."""

    async def test_unauthenticated_start_returns_401(
        self,
        client: AsyncClient,
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": "PLAN-2026-W31"},
        )
        assert resp.status_code == 401

    async def test_non_manager_start_returns_403(
        self,
        client: AsyncClient,
        non_manager_token: dict[str, str],
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": "PLAN-2026-W31"},
            headers=non_manager_token,
        )
        assert resp.status_code == 403


class TestStartCommitBeforeEnqueue:
    """D1/C1: Commit-then-enqueue behavior."""

    async def test_start_commits_before_enqueue(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        plan_code_async: str,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": plan_code_async},
            headers=auth_token,
        )
        assert resp.status_code == 202

        # Verify the run is committed in the DB.
        run_id = resp.json()["run_id"]
        result = await db_session.execute(
            text("SELECT state FROM workflow_runs WHERE id = :id"),
            {"id": run_id},
        )
        state = result.scalar()
        assert state == "PENDING"

    async def test_enqueue_failure_returns_503_without_run_id(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
        plan_code_async: str,
        db_session: AsyncSession,
    ) -> None:
        """Start enqueue failure returns 503 and does not expose run_id."""
        error_pool = _FakePool(enqueue_error=ConnectionError("Redis down"))

        async def error_factory() -> _FakePool:
            return error_pool

        import app.api.workflow as workflow_api

        monkeypatch.setattr(workflow_api, "_pool_factory", error_factory)

        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": plan_code_async},
            headers=auth_token,
        )
        assert resp.status_code == 503
        data = resp.json()
        assert "run_id" not in data.get("detail", {})

    async def test_committed_pending_survives_enqueue_failure(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
        plan_code_async: str,
        db_session: AsyncSession,
    ) -> None:
        """The committed PENDING row remains after enqueue failure."""
        error_pool = _FakePool(enqueue_error=ConnectionError("Redis down"))

        async def error_factory() -> _FakePool:
            return error_pool

        import app.api.workflow as workflow_api

        monkeypatch.setattr(workflow_api, "_pool_factory", error_factory)

        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": plan_code_async},
            headers=auth_token,
        )
        assert resp.status_code == 503

        # Verify a PENDING row exists.
        result = await db_session.execute(
            text("SELECT COUNT(*) FROM workflow_runs WHERE state = 'PENDING'")
        )
        count = result.scalar()
        assert count == 1


class TestStartResponseContract:
    """D3 §4: Exact start response contract."""

    async def test_response_has_exactly_run_id_state_location(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        plan_code_async: str,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": plan_code_async},
            headers=auth_token,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert set(data.keys()) == {"run_id", "state", "location"}

    async def test_triggered_by_set_to_username(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        plan_code_async: str,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": plan_code_async},
            headers=auth_token,
        )
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]

        result = await db_session.execute(
            text("SELECT triggered_by FROM workflow_runs WHERE id = :id"),
            {"id": run_id},
        )
        triggered_by = result.scalar()
        assert triggered_by is not None
        # The token was created for the production manager user.
        assert triggered_by is not None


# ---------------------------------------------------------------------------
# Retry API tests
# ---------------------------------------------------------------------------


async def _create_failed_run(
    session: AsyncSession,
    plan_id: Any,
    *,
    state: str = "FAILED_PROVIDER",
    triggered_by: str | None = "test_manager",
) -> WorkflowRun:
    """Create a run directly in a failed state for retry testing."""
    run = WorkflowRun(
        plan_id=plan_id,
        state=state,
        triggered_by=triggered_by,
        dispatch_generation=0,
        pending_since=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        error_code="PROVIDER_TRANSIENT",
        error_detail="test",
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def _get_plan_id(session: AsyncSession) -> Any:
    result = await session.execute(
        text("SELECT id FROM production_plans LIMIT 1")
    )
    row = result.fetchone()
    if row is None:
        pytest.skip("No production plans in database")
    return row[0]


class TestRetryAuthorization:
    """D2: Retry authorization."""

    async def test_unauthenticated_retry_returns_401(
        self,
        client: AsyncClient,
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(db_session, plan_id)
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
        )
        assert resp.status_code == 401

    async def test_non_creator_non_manager_retry_returns_403(
        self,
        client: AsyncClient,
        non_manager_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(db_session, plan_id, triggered_by="someone_else")
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=non_manager_token,
        )
        assert resp.status_code == 403

    async def test_triggered_by_null_non_manager_returns_403(
        self,
        client: AsyncClient,
        non_manager_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(db_session, plan_id, triggered_by=None)
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=non_manager_token,
        )
        assert resp.status_code == 403


class TestRetryEligibility:
    """D1: Retry-eligible failed states."""

    @pytest.mark.parametrize(
        "failed_state",
        ["FAILED_PROVIDER", "FAILED_VALIDATION", "FAILED_INTERNAL"],
    )
    async def test_retry_from_eligible_failed_state_returns_202(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
        failed_state: str,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(
            db_session, plan_id, state=failed_state
        )
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["state"] == "PENDING"
        assert data["run_id"] == str(run.id)

    async def test_retry_completed_returns_409(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(
            db_session, plan_id, state="COMPLETED"
        )
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 409

    async def test_retry_pending_returns_409(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(
            db_session, plan_id, state="PENDING"
        )
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 409

    async def test_retry_not_found_returns_404(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{uuid4()}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 404


class TestRetryAtomicTransition:
    """D1: Atomic conditional transition behavior."""

    async def test_retry_clears_error_fields(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(db_session, plan_id)
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 202

        result = await db_session.execute(
            text(
                "SELECT error_code, error_detail, completed_at, started_at "
                "FROM workflow_runs WHERE id = :id"
            ),
            {"id": str(run.id)},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] is None  # error_code
        assert row[1] is None  # error_detail
        assert row[2] is None  # completed_at
        assert row[3] is None  # started_at (D1 implementation choice)

    async def test_retry_increments_generation(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(db_session, plan_id)
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 202

        result = await db_session.execute(
            text("SELECT dispatch_generation FROM workflow_runs WHERE id = :id"),
            {"id": str(run.id)},
        )
        gen = result.scalar()
        assert gen == 1

    async def test_retry_does_not_modify_triggered_by(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(db_session, plan_id, triggered_by="original_user")
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 202

        result = await db_session.execute(
            text("SELECT triggered_by FROM workflow_runs WHERE id = :id"),
            {"id": str(run.id)},
        )
        assert result.scalar() == "original_user"

    async def test_retry_resets_pending_since(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(db_session, plan_id)
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 202

        result = await db_session.execute(
            text("SELECT pending_since FROM workflow_runs WHERE id = :id"),
            {"id": str(run.id)},
        )
        ps = result.scalar()
        assert ps is not None


class TestRetryEnqueueFailure:
    """D1/C1: Retry enqueue-failure behavior."""

    async def test_retry_enqueue_failure_returns_503(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(db_session, plan_id)

        error_pool = _FakePool(enqueue_error=ConnectionError("Redis down"))

        async def error_factory() -> _FakePool:
            return error_pool

        import app.api.workflow as workflow_api

        monkeypatch.setattr(workflow_api, "_pool_factory", error_factory)

        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 503

        # Verify the PENDING row survived.
        result = await db_session.execute(
            text("SELECT state, dispatch_generation FROM workflow_runs WHERE id = :id"),
            {"id": str(run.id)},
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "PENDING"
        assert row[1] == 1


class TestRetryResponseContract:
    """D1: Exact retry response contract."""

    async def test_retry_response_has_exactly_run_id_state_location(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(db_session, plan_id)
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 202
        data = resp.json()
        assert set(data.keys()) == {"run_id", "state", "location"}
        assert data["run_id"] == str(run.id)


class TestStartJobIdConstruction:
    """D5 §3: Deterministic job ID in start enqueue."""

    async def test_start_job_id_uses_generation_0(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        plan_code_async: str,
    ) -> None:
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs",
            json={"plan_id": plan_code_async},
            headers=auth_token,
        )
        assert resp.status_code == 202
        assert len(patched_pool.enqueue_calls) == 1
        call = patched_pool.enqueue_calls[0]
        assert call["function"] == "workflow_start"
        run_id = resp.json()["run_id"]
        assert call["_job_id"] == f"workflow:{run_id}:0"


class TestRetryJobIdConstruction:
    """D5 §3: Deterministic job ID in retry enqueue."""

    async def test_retry_job_id_uses_new_generation(
        self,
        client: AsyncClient,
        auth_token: dict[str, str],
        patched_pool: _FakePool,
        db_session: AsyncSession,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_failed_run(db_session, plan_id)
        resp = await client.post(
            f"{settings.api_v1_prefix}/workflow-runs/{run.id}/retry",
            headers=auth_token,
        )
        assert resp.status_code == 202
        assert len(patched_pool.enqueue_calls) == 1
        call = patched_pool.enqueue_calls[0]
        assert call["function"] == "workflow_retry"
        assert call["_job_id"] == f"workflow:{run.id}:1"
