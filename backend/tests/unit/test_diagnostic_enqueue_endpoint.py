"""Unit tests for POST /api/v1/system/diagnostics endpoint.

Tests verify contract compliance (202 + 3-field response), correlation ID
propagation, DB-then-enqueue transaction ordering, deterministic ARQ job ID,
pool ownership (owned pool closed, injected pool not closed), and enqueue
failure compensation (pending -> failed, safe error text, no orphan rows).

No live PostgreSQL, Redis, or worker required.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.services.diagnostic_jobs as service
from app.main import app
from app.models.diagnostic import DiagnosticJob
from app.schemas.diagnostic import DiagnosticCreateResponse

# ---------------------------------------------------------------------------
# Fake implementations
# ---------------------------------------------------------------------------


class FakeResult:
    """Minimal SQLAlchemy Result fake with scalar_one_or_none."""

    def __init__(self, row: Any) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._row


class FakeSession:
    """AsyncSession fake that records operations.

    ``add()`` registers the DiagnosticJob in a shared row_store, so the
    compensation path (which opens a separate session) can retrieve it via
    ``execute()``. This lets us verify real status transitions without a
    real database.
    """

    def __init__(self, row_store: dict[str, DiagnosticJob]) -> None:
        self._row_store = row_store
        self.added: list[Any] = []
        self.committed = 0
        self.executed: list[Any] = []
        self.closed = False
        self.refreshed: list[Any] = []

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.closed = True

    def add(self, obj: Any) -> None:
        self.added.append(obj)
        # Register in shared store so subsequent sessions can find it.
        if isinstance(obj, DiagnosticJob) and obj.id is not None:
            self._row_store[str(obj.id)] = obj

    async def commit(self) -> None:
        self.committed += 1

    async def refresh(self, obj: Any) -> None:
        self.refreshed.append(obj)
        if hasattr(obj, "created_at") and obj.created_at is None:
            obj.created_at = datetime.now(UTC)
        if hasattr(obj, "updated_at") and obj.updated_at is None:
            obj.updated_at = obj.created_at

    async def execute(self, stmt: Any, *_args: Any, **_kwargs: Any) -> FakeResult:
        self.executed.append(stmt)
        # Look up the most-recently-added row from the shared store.
        if self._row_store:
            return FakeResult(next(iter(self._row_store.values())))
        return FakeResult(None)


class FakeSessionFactory:
    """Factory that returns FakeSession instances sharing a row_store."""

    def __init__(self) -> None:
        self.sessions: list[FakeSession] = []
        self.row_store: dict[str, DiagnosticJob] = {}

    def __call__(self) -> FakeSession:
        session = FakeSession(self.row_store)
        self.sessions.append(session)
        return session


class FakePool:
    """ArqRedis fake that records enqueue calls and close() invocations."""

    def __init__(self, injected: bool = False) -> None:
        self.enqueue_calls: list[dict[str, Any]] = []
        self.aclose_called = 0
        self.close_called = 0
        self.injected = injected
        # Configurable by tests
        self.enqueue_result: Any = MagicMock(name="EnqueuedJob")
        self.enqueue_exception: Exception | None = None

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> Any:
        self.enqueue_calls.append({
            "function": function,
            "args": args,
            "kwargs": kwargs,
        })
        if self.enqueue_exception is not None:
            raise self.enqueue_exception
        return self.enqueue_result

    async def aclose(self) -> None:
        self.aclose_called += 1

    async def close(self) -> None:
        self.close_called += 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory() -> FakeSessionFactory:
    return FakeSessionFactory()


@pytest.fixture
def pool() -> FakePool:
    return FakePool()


@pytest.fixture
def fixed_job_id() -> uuid.UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    session_factory: FakeSessionFactory,
    pool: FakePool,
    fixed_job_id: uuid.UUID,
) -> Generator[dict[str, Any], None, None]:
    """Install module-level fakes for _session_factory, _pool_factory, uuid4."""
    monkeypatch.setattr(service, "_session_factory", session_factory)
    monkeypatch.setattr(
        service,
        "_pool_factory",
        AsyncMock(return_value=pool),
    )
    monkeypatch.setattr(uuid, "uuid4", lambda: fixed_job_id)

    yield {
        "session_factory": session_factory,
        "pool": pool,
        "fixed_job_id": fixed_job_id,
        "row_store": session_factory.row_store,
    }


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_diagnostics_returns_202_with_exact_fields(
    install_fakes: dict[str, Any], fixed_job_id: uuid.UUID
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/system/diagnostics")

    assert response.status_code == 202, response.text
    body = response.json()
    assert set(body.keys()) == {"job_id", "correlation_id", "status"}
    assert body["job_id"] == str(fixed_job_id)
    assert body["status"] == "pending"
    # correlation_id is a valid UUID string (generated or propagated)
    uuid.UUID(body["correlation_id"])


@pytest.mark.asyncio
async def test_correlation_id_generated_by_middleware(install_fakes: dict[str, Any]) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/system/diagnostics")

    header_cid = response.headers.get("x-correlation-id")
    body_cid = response.json()["correlation_id"]
    assert header_cid == body_cid
    uuid.UUID(header_cid)  # Validates UUID format


@pytest.mark.asyncio
async def test_correlation_id_propagated_from_client(install_fakes: dict[str, Any]) -> None:
    client_cid = str(uuid.uuid4())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/system/diagnostics",
            headers={"x-correlation-id": client_cid},
        )

    assert response.json()["correlation_id"] == client_cid
    assert response.headers.get("x-correlation-id") == client_cid


# ---------------------------------------------------------------------------
# Transaction ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_closed_before_enqueue(
    install_fakes: dict[str, Any], session_factory: FakeSessionFactory, pool: FakePool
) -> None:
    """Verify session.__aexit__ runs before pool.enqueue_job is called."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/system/diagnostics")

    # At least one session created and committed
    assert any(s.committed > 0 for s in session_factory.sessions)
    # First session (creation) is closed before enqueue
    assert session_factory.sessions[0].closed
    # Enqueue happened after commit
    assert len(pool.enqueue_calls) > 0


# ---------------------------------------------------------------------------
# Deterministic ARQ job ID
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deterministic_arq_job_id(
    install_fakes: dict[str, Any], pool: FakePool, fixed_job_id: uuid.UUID
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/system/diagnostics")

    assert len(pool.enqueue_calls) == 1
    call = pool.enqueue_calls[0]
    assert call["function"] == "run_diagnostic_job"
    assert call["args"][0] == str(fixed_job_id)
    assert call["kwargs"]["_job_id"] == f"diagnostic-job-{fixed_job_id}"


# ---------------------------------------------------------------------------
# Pool ownership
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_owned_pool_closed_on_success(
    install_fakes: dict[str, Any], pool: FakePool
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/system/diagnostics")

    # Owned pool: close() called exactly once (via finally)
    assert pool.close_called >= 1


@pytest.mark.asyncio
async def test_owned_pool_closed_on_failure(
    install_fakes: dict[str, Any], pool: FakePool
) -> None:
    pool.enqueue_exception = RuntimeError("Connection refused")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/system/diagnostics")

    # Even on enqueue failure, owned pool must be closed (finally block)
    assert pool.close_called >= 1


@pytest.mark.asyncio
async def test_injected_pool_not_closed(
    monkeypatch: pytest.MonkeyPatch, session_factory: FakeSessionFactory
) -> None:
    """Passing redis_pool= skips _pool_factory and leaves ownership to caller."""
    injected_pool = FakePool(injected=True)
    fixed_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    monkeypatch.setattr(service, "_session_factory", session_factory)
    monkeypatch.setattr(uuid, "uuid4", lambda: fixed_id)
    # Do NOT patch _pool_factory — redis_pool is supplied directly

    response_data = await service.enqueue_diagnostic_job(
        correlation_id=str(uuid.uuid4()),
        redis_pool=injected_pool,  # type: ignore[arg-type]
    )

    # Injected pool: neither close() nor aclose() called
    assert injected_pool.aclose_called == 0
    assert injected_pool.close_called == 0
    assert isinstance(response_data, DiagnosticCreateResponse)


# ---------------------------------------------------------------------------
# Enqueue failure compensation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_exception_marks_row_failed(
    install_fakes: dict[str, Any], pool: FakePool, session_factory: FakeSessionFactory
) -> None:
    pool.enqueue_exception = RuntimeError("Connection refused")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/system/diagnostics")

    # HTTPException(503, detail={...}) → {"detail": {...}}
    assert response.status_code == 503
    body = response.json()
    detail = body["detail"]
    assert detail["error"] == "diagnostic_job_enqueue_failed"
    # No secrets in response
    lower = str(body).lower()
    assert "redis://" not in lower
    assert "password" not in lower
    assert "traceback" not in lower

    # Exactly two sessions used: creation + compensation
    assert len(session_factory.sessions) == 2
    creation_session = session_factory.sessions[0]
    compensation_session = session_factory.sessions[1]

    # Creation session: added DiagnosticJob and committed
    assert len(creation_session.added) == 1
    assert isinstance(creation_session.added[0], DiagnosticJob)
    assert creation_session.committed > 0

    # Compensation session: executed SELECT + committed the failed update
    assert len(compensation_session.executed) > 0
    assert compensation_session.committed > 0

    # The DiagnosticJob was transitioned to failed status
    job = creation_session.added[0]
    assert job.status == "failed"
    assert job.completed_at is not None
    assert job.error_message is not None
    # No raw exception text in stored error
    assert "Connection refused" not in job.error_message


@pytest.mark.asyncio
async def test_enqueue_none_marks_row_failed(
    install_fakes: dict[str, Any], pool: FakePool, session_factory: FakeSessionFactory
) -> None:
    pool.enqueue_result = None  # Duplicate lease
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/system/diagnostics")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["error"] == "diagnostic_job_enqueue_failed"

    # Two sessions: creation + compensation
    assert len(session_factory.sessions) == 2
    job = session_factory.sessions[0].added[0]
    assert job.status == "failed"


@pytest.mark.asyncio
async def test_error_text_is_bounded_and_safe(install_fakes: dict[str, Any]) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/system/diagnostics")

    assert response.status_code == 202
    # Confirm the static error message meets our safety/size constraints.
    msg = service._SAFE_ENQUEUE_ERROR_MESSAGE
    assert "\n" not in msg
    assert "\r" not in msg
    assert len(msg) < service._MAX_ERROR_MESSAGE_LENGTH
    assert "redis://" not in msg.lower()
    assert "password" not in msg.lower()
    assert "traceback" not in msg.lower()


@pytest.mark.asyncio
async def test_no_pending_orphan_after_failure(
    install_fakes: dict[str, Any], pool: FakePool, session_factory: FakeSessionFactory
) -> None:
    pool.enqueue_exception = RuntimeError("Connection refused")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/system/diagnostics")

    # Verify: creation session added a row; compensation updated to failed.
    assert any(s.added for s in session_factory.sessions)
    assert any(s.executed for s in session_factory.sessions)
    # No row is left in pending state.
    for job in session_factory.row_store.values():
        assert job.status != "pending"


# ---------------------------------------------------------------------------
# Enqueue call count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_called_exactly_once(
    install_fakes: dict[str, Any], pool: FakePool
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/v1/system/diagnostics")

    assert len(pool.enqueue_calls) == 1


# ---------------------------------------------------------------------------
# Enqueue arguments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enqueue_job_arguments(
    install_fakes: dict[str, Any], pool: FakePool, fixed_job_id: uuid.UUID
) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/system/diagnostics")

    body = response.json()
    correlation_id = body["correlation_id"]

    call = pool.enqueue_calls[0]
    assert call["function"] == "run_diagnostic_job"
    # Positional args: (job_id, correlation_id)
    assert call["args"][0] == str(fixed_job_id)
    assert call["args"][1] == correlation_id
    # Keyword args
    assert call["kwargs"]["_job_id"] == f"diagnostic-job-{fixed_job_id}"
    assert call["kwargs"]["_queue_name"] == "forgemind-tasks"
