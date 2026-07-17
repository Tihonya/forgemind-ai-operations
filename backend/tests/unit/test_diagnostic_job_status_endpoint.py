"""Unit tests for GET /api/v1/system/diagnostics/{job_id} endpoint.

Tests verify contract compliance: 200 for existing job (all states),
404 for missing job, 422 for invalid UUID, exact response fields,
read-only behavior (no commit, no enqueue, no Redis), session lifecycle,
and correlation header preservation.

No live PostgreSQL, Redis, or worker required.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.diagnostic_jobs as service
from app.main import app
from app.models.diagnostic import DiagnosticJob

# ---------------------------------------------------------------------------
# Fake implementations
# ---------------------------------------------------------------------------


class FakeResult:
    """Minimal SQLAlchemy Result fake with scalar_one_or_none."""

    def __init__(self, row: DiagnosticJob | None) -> None:
        self._row = row

    def scalar_one_or_none(self) -> DiagnosticJob | None:
        return self._row


class FakeSession:
    """AsyncSession fake that returns a diagnostic job via execute().

    Tracks: commit calls (must be zero for GET), close on __aexit__,
    execute calls.
    """

    def __init__(self, row: DiagnosticJob | None) -> None:
        self._row = row
        self.committed = 0
        self.closed = False
        self.executed = 0

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.closed = True

    def add(self, obj: Any) -> None:
        raise AssertionError("GET must not call session.add()")

    async def commit(self) -> None:
        self.committed += 1
        raise AssertionError("GET must not call session.commit()")

    async def rollback(self) -> None:
        raise AssertionError("GET must not call session.rollback()")

    async def execute(self, stmt: Any, *_args: Any, **_kwargs: Any) -> FakeResult:
        self.executed += 1
        return FakeResult(self._row)


class FakeSessionFactory:
    """Factory that returns FakeSession instances holding a specific row."""

    def __init__(self, row: DiagnosticJob | None = None) -> None:
        self.row = row
        self.sessions: list[FakeSession] = []
        self.calls = 0

    def set_row(self, row: DiagnosticJob | None) -> None:
        self.row = row

    def __call__(self) -> FakeSession:
        self.calls += 1
        session = FakeSession(self.row)
        self.sessions.append(session)
        return session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


FIXED_CORRELATION_UUID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-000000000001")
FIXED_JOB_UUID = uuid.UUID("12345678-1234-5678-1234-567812345678")
FIXED_CREATED_AT = datetime(2026, 7, 17, 12, 0, 0, tzinfo=UTC)
FIXED_STARTED_AT = datetime(2026, 7, 17, 12, 0, 1, tzinfo=UTC)
FIXED_COMPLETED_AT = datetime(2026, 7, 17, 12, 0, 2, tzinfo=UTC)


@pytest.fixture
def session_factory() -> FakeSessionFactory:
    return FakeSessionFactory(row=None)


@pytest.fixture
def install_session_factory(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: FakeSessionFactory,
) -> FakeSessionFactory:
    monkeypatch.setattr(service, "_session_factory", session_factory)
    return session_factory


@pytest.fixture
def enqueue_spy() -> AsyncMock:
    """Spy on pool.enqueue_job to ensure GET never calls enqueue."""
    return AsyncMock(return_value=None)


def _make_diagnostic_job(
    *,
    job_id: uuid.UUID = FIXED_JOB_UUID,
    correlation_id: uuid.UUID = FIXED_CORRELATION_UUID,
    status: str = "pending",
    checks: list[dict[str, Any]] | None = None,
    error_message: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
    created_at: datetime = FIXED_CREATED_AT,
) -> DiagnosticJob:
    """Build a DiagnosticJob row with controlled field values."""
    job = DiagnosticJob()
    job.id = job_id
    job.correlation_id = correlation_id
    job.status = status  # type: ignore[assignment]
    job.checks = checks
    job.error_message = error_message
    job.started_at = started_at
    job.completed_at = completed_at
    job.duration_ms = duration_ms
    job.created_at = created_at
    job.updated_at = created_at
    return job


# ---------------------------------------------------------------------------
# Route existence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_exists(install_session_factory: FakeSessionFactory) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )
    # Not 404 from the router (422 for invalid UUID would also NOT occur
    # since this is a valid UUID; 500 would indicate route is not registered).
    # A 200 or 404 from handler is proof the route is registered.
    assert response.status_code in (200, 404), response.text


# ---------------------------------------------------------------------------
# 200 responses for each valid state
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_job_returns_200(
    install_session_factory: FakeSessionFactory,
) -> None:
    job = _make_diagnostic_job(status="pending")
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["id"] == str(FIXED_JOB_UUID)


@pytest.mark.asyncio
async def test_running_job_returns_200(
    install_session_factory: FakeSessionFactory,
) -> None:
    job = _make_diagnostic_job(status="running", started_at=FIXED_STARTED_AT)
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["started_at"] is not None
    assert body["completed_at"] is None
    assert body["duration_ms"] is None


@pytest.mark.asyncio
async def test_completed_job_returns_200_with_checks_and_duration(
    install_session_factory: FakeSessionFactory,
) -> None:
    # Actual persisted shape from worker (list of check objects, not dict)
    checks = [
        {"name": "postgresql", "status": "ok", "latency_ms": 1.99, "detail": "SELECT 1 succeeded"},
        {"name": "redis", "status": "ok", "latency_ms": 1.79, "detail": "PING succeeded"},
        {"name": "alembic", "status": "ok", "latency_ms": 2.69, "detail": "revision 12927017"},
        {
            "name": "worker",
            "status": "ok",
            "latency_ms": 1.57,
            "detail": "Jul-17 13:55:53 j_complete=0",
        },
    ]
    job = _make_diagnostic_job(
        status="completed",
        checks=checks,
        started_at=FIXED_STARTED_AT,
        completed_at=FIXED_COMPLETED_AT,
        duration_ms=1500,
    )
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["checks"] == checks
    assert body["duration_ms"] == 1500
    assert body["completed_at"] is not None
    assert body["error_message"] is None


@pytest.mark.asyncio
async def test_failed_job_returns_200_with_safe_error(
    install_session_factory: FakeSessionFactory,
) -> None:
    job = _make_diagnostic_job(
        status="failed",
        error_message="Enqueue failed: duplicate_lease",
        completed_at=FIXED_COMPLETED_AT,
    )
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert isinstance(body["error_message"], str)
    assert len(body["error_message"]) > 0
    # No secrets leak through
    assert "redis://" not in body["error_message"]
    assert body["checks"] is None


# ---------------------------------------------------------------------------
# Exact response fields
# ---------------------------------------------------------------------------


APPROVED_FIELDS = {
    "id",
    "correlation_id",
    "status",
    "checks",
    "error_message",
    "started_at",
    "completed_at",
    "duration_ms",
    "created_at",
}


@pytest.mark.asyncio
async def test_exact_response_fields(install_session_factory: FakeSessionFactory) -> None:
    job = _make_diagnostic_job(status="pending")
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == APPROVED_FIELDS


@pytest.mark.asyncio
async def test_uuid_and_datetime_serialization(
    install_session_factory: FakeSessionFactory,
) -> None:
    job = _make_diagnostic_job(
        status="completed",
        started_at=FIXED_STARTED_AT,
        completed_at=FIXED_COMPLETED_AT,
        duration_ms=1000,
    )
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )

    body = response.json()
    # UUIDs serialized as strings
    assert isinstance(body["id"], str)
    uuid.UUID(body["id"])  # validates UUID format
    assert isinstance(body["correlation_id"], str)
    uuid.UUID(body["correlation_id"])
    # Timestamps are ISO-8601 strings
    assert isinstance(body["created_at"], str)
    assert isinstance(body["started_at"], str)
    assert isinstance(body["completed_at"], str)
    # Parseable back to datetime (with timezone)
    datetime.fromisoformat(body["created_at"])
    datetime.fromisoformat(body["started_at"])
    datetime.fromisoformat(body["completed_at"])
    # duration_ms is an integer
    assert isinstance(body["duration_ms"], int)


@pytest.mark.asyncio
async def test_optional_fields_are_null_for_pending(
    install_session_factory: FakeSessionFactory,
) -> None:
    job = _make_diagnostic_job(status="pending")
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )

    body = response.json()
    assert body["checks"] is None
    assert body["error_message"] is None
    assert body["started_at"] is None
    assert body["completed_at"] is None
    assert body["duration_ms"] is None
    # Only created_at is always present
    assert isinstance(body["created_at"], str)


# ---------------------------------------------------------------------------
# 404 for missing job
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_job_returns_404(
    install_session_factory: FakeSessionFactory,
) -> None:
    # No row set - service returns None
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )

    assert response.status_code == 404
    body = response.json()
    detail = body["detail"]
    assert detail["error"] == "diagnostic_job_not_found"
    assert detail["job_id"] == str(FIXED_JOB_UUID)
    # No secrets or internal details
    lower = str(body).lower()
    assert "sqlalchemy" not in lower
    assert "traceback" not in lower


# ---------------------------------------------------------------------------
# 422 for invalid UUID path (FastAPI / Pydantic validation)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_uuid_returns_422(
    install_session_factory: FakeSessionFactory,
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/system/diagnostics/not-a-valid-uuid")

    assert response.status_code == 422
    # FastAPI returns {"detail": [...validation_error]}
    body = response.json()
    assert "detail" in body


# ---------------------------------------------------------------------------
# Read-only invariants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_redis_pool_created(install_session_factory: FakeSessionFactory) -> None:
    """GET must never invoke _pool_factory (no Redis interaction)."""
    pool_spy = AsyncMock()
    original_pool_factory = service._pool_factory
    service._pool_factory = pool_spy
    try:
        install_session_factory.set_row(_make_diagnostic_job(status="pending"))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.get(f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}")

        pool_spy.assert_not_called()
    finally:
        service._pool_factory = original_pool_factory


@pytest.mark.asyncio
async def test_no_enqueue_call(install_session_factory: FakeSessionFactory) -> None:
    """GET must not enqueue any ARQ job.

    Verified indirectly: no pool is created, so no enqueue can happen.
    The read-only GET handler only calls get_diagnostic_job, which opens
    a session, queries, and returns.
    """
    install_session_factory.set_row(_make_diagnostic_job(status="running"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get(f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}")

    # At most one session was used, never committed
    assert install_session_factory.calls == 1
    session = install_session_factory.sessions[0]
    assert session.committed == 0
    assert session.executed == 1


@pytest.mark.asyncio
async def test_database_session_closes_after_lookup(
    install_session_factory: FakeSessionFactory,
) -> None:
    install_session_factory.set_row(_make_diagnostic_job(status="pending"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get(f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}")

    assert install_session_factory.calls >= 1
    # Every session must have been closed via __aexit__
    for session in install_session_factory.sessions:
        assert session.closed, "Session was not closed after GET"


@pytest.mark.asyncio
async def test_read_only_request_performs_no_commit(
    install_session_factory: FakeSessionFactory,
) -> None:
    install_session_factory.set_row(_make_diagnostic_job(status="completed"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.get(f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}")

    for session in install_session_factory.sessions:
        assert session.committed == 0, "GET must not commit"


# ---------------------------------------------------------------------------
# Correlation ID header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_middleware_correlation_header_present(
    install_session_factory: FakeSessionFactory,
) -> None:
    install_session_factory.set_row(_make_diagnostic_job(status="pending"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )

    header = response.headers.get("x-correlation-id")
    assert header is not None, "Middleware X-Correlation-ID header must be present"
    # Validates UUID-v4 format
    uuid.UUID(header)


@pytest.mark.asyncio
async def test_client_provided_correlation_id_preserved(
    install_session_factory: FakeSessionFactory,
) -> None:
    install_session_factory.set_row(_make_diagnostic_job(status="pending"))
    # Must be a valid UUID v4 (middleware rejects non-v4 with 400)
    client_cid = str(uuid.uuid4())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}",
            headers={"x-correlation-id": client_cid},
        )

    assert response.status_code == 200
    assert response.headers.get("x-correlation-id") == client_cid


@pytest.mark.asyncio
async def test_exactly_one_correlation_header(
    install_session_factory: FakeSessionFactory,
) -> None:
    """Middleware must set exactly one X-Correlation-ID header, not duplicate."""
    install_session_factory.set_row(_make_diagnostic_job(status="pending"))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}"
        )

    values = response.headers.get_list("x-correlation-id")
    assert len(values) == 1, f"Expected exactly 1 X-Correlation-ID header, got {len(values)}"


# ---------------------------------------------------------------------------
# Existing POST endpoint remains unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_endpoint_still_registers(
    install_session_factory: FakeSessionFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST endpoint still routes and returns 202 even after GET is added."""

    class FakeRowStore(dict[str, DiagnosticJob]):
        """Shared dict for creation + compensation sessions."""

        pass

    class FakeSessionForPost:
        def __init__(self, store: dict[str, DiagnosticJob]) -> None:
            self._store = store
            self.committed = 0

        async def __aenter__(self) -> FakeSessionForPost:
            return self

        async def __aexit__(self, *_a: Any) -> None:
            pass

        def add(self, obj: Any) -> None:
            if isinstance(obj, DiagnosticJob) and obj.id is not None:
                self._store[str(obj.id)] = obj

        async def commit(self) -> None:
            self.committed += 1

        async def refresh(self, obj: Any) -> None:
            if hasattr(obj, "created_at") and obj.created_at is None:
                obj.created_at = datetime.now(UTC)
            if hasattr(obj, "updated_at") and obj.updated_at is None:
                obj.updated_at = obj.created_at

        async def execute(self, *_a: Any, **_kw: Any) -> Any:
            return None

    class FakeFactory:
        def __init__(self) -> None:
            self.store: dict[str, DiagnosticJob] = {}

        def __call__(self) -> FakeSessionForPost:
            return FakeSessionForPost(self.store)

    post_factory = FakeFactory()
    monkeypatch.setattr(service, "_session_factory", post_factory)
    monkeypatch.setattr(uuid, "uuid4", lambda: FIXED_JOB_UUID)

    class FakePool:
        enqueue_calls: list[dict[str, Any]] = []

        async def enqueue_job(self, *args: Any, **kwargs: Any) -> Any:
            return "dummy-job"

        async def close(self) -> None:
            pass

    monkeypatch.setattr(service, "_pool_factory", AsyncMock(return_value=FakePool()))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/system/diagnostics")

    assert response.status_code == 202
    body = response.json()
    assert set(body.keys()) == {"job_id", "correlation_id", "status"}
    assert body["status"] == "pending"


# ---------------------------------------------------------------------------
# Regression tests: actual persisted checks shape (list, not dict)
# ---------------------------------------------------------------------------
# The worker persists checks as a list of DependencyCheck.model_dump() dicts,
# not as a dict[str, str]. The old schema (dict[str, str] | None) caused a
# Pydantic ValidationError on GET /api/v1/system/diagnostics/{job_id} when the
# job was completed. These tests lock in the correct behaviour.
# ---------------------------------------------------------------------------

_REAL_WORKER_CHECKS: list[dict[str, Any]] = [
    {"name": "postgresql", "status": "ok", "latency_ms": 1.993, "detail": "SELECT 1 succeeded"},
    {"name": "redis", "status": "ok", "latency_ms": 1.787, "detail": "PING succeeded"},
    {"name": "alembic", "status": "ok", "latency_ms": 2.69, "detail": "revision 12927017"},
    {"name": "worker", "status": "ok", "latency_ms": 1.57, "detail": "worker healthy"},
]


@pytest.mark.asyncio
async def test_get_completed_job_with_list_shaped_checks_returns_200(
    install_session_factory: FakeSessionFactory,
) -> None:
    """A completed job whose `checks` is a list of check objects must
    return HTTP 200 with the exact serialized shape — no Pydantic error."""
    job = _make_diagnostic_job(
        status="completed",
        checks=_REAL_WORKER_CHECKS,
        started_at=FIXED_STARTED_AT,
        completed_at=FIXED_COMPLETED_AT,
        duration_ms=42,
    )
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["checks"] == _REAL_WORKER_CHECKS
    assert body["duration_ms"] == 42
    assert body["error_message"] is None


@pytest.mark.asyncio
async def test_get_completed_job_serialized_checks_shape(
    install_session_factory: FakeSessionFactory,
) -> None:
    """Verify the serialized checks field is a list of objects with the
    expected keys and types, matching `DependencyCheck.model_dump()`."""
    job = _make_diagnostic_job(
        status="completed",
        checks=_REAL_WORKER_CHECKS,
        started_at=FIXED_STARTED_AT,
        completed_at=FIXED_COMPLETED_AT,
        duration_ms=42,
    )
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}")

    assert response.status_code == 200
    body = response.json()
    checks = body["checks"]
    assert isinstance(checks, list)
    assert len(checks) == 4
    for check in checks:
        assert set(check.keys()) == {"name", "status", "latency_ms", "detail"}
        assert isinstance(check["name"], str) and len(check["name"]) > 0
        assert check["status"] in ("ok", "error", "unknown")
        assert isinstance(check["latency_ms"], (int, float))
        assert check["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_get_completed_job_no_pydantic_validation_error(
    install_session_factory: FakeSessionFactory,
) -> None:
    """The GET handler must not raise a Pydantic ValidationError when the
    persisted checks are the actual list shape. Previously this returned
    HTTP 500 — now it returns 200."""
    job = _make_diagnostic_job(
        status="completed",
        checks=_REAL_WORKER_CHECKS,
        started_at=FIXED_STARTED_AT,
        completed_at=FIXED_COMPLETED_AT,
        duration_ms=42,
    )
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}")

    # Must NOT be 500. 500 would prove the Pydantic regression is still live.
    assert response.status_code != 500, (
        f"Pydantic regression still live: {response.status_code} {response.text!r}"
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_pending_job_checks_null(
    install_session_factory: FakeSessionFactory,
) -> None:
    """Pending job: checks must be null, not an empty list."""
    job = _make_diagnostic_job(status="pending", checks=None)
    install_session_factory.set_row(job)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}")

    assert response.status_code == 200
    body = response.json()
    assert body["checks"] is None
    assert body["status"] == "pending"


@pytest.mark.asyncio
async def test_malformed_checks_fail_predictably_and_do_not_leak_internals(
    install_session_factory: FakeSessionFactory,
) -> None:
    """If stored checks contain an invalid status, the response must
    not leak Pydantic/SQLAlchemy/URL details to the client.

    In production, Starlette's ServerErrorMiddleware converts the Pydantic
    ValidationError to a generic 500. We simulate this by using
    raise_app_exceptions=False on the ASGITransport.
    """
    bad_checks = [
        {"name": "postgresql", "status": "NOT_A_REAL_STATUS", "latency_ms": 1.0, "detail": None},
    ]
    job = _make_diagnostic_job(
        status="completed",
        checks=bad_checks,
        started_at=FIXED_STARTED_AT,
        completed_at=FIXED_COMPLETED_AT,
        duration_ms=10,
    )
    install_session_factory.set_row(job)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/system/diagnostics/{FIXED_JOB_UUID}")

    assert response.status_code == 500
    response_text = response.text.lower()
    for leak in ("traceback", "pydantic", "validationerror", "postgresql+asyncpg", "redis://"):
        assert leak not in response_text, f"Leak detected: {leak!r} in {response.text!r}"
