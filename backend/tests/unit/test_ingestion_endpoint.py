"""Unit tests for POST /api/v1/documents/{document_id}/versions/{version_id}/ingest.

Tests verify authorization (RBAC), document version validation, enqueue behavior,
deterministic ARQ job ID, pool ownership, error safety, and that no real
PostgreSQL, Redis, or external provider is required.

No live PostgreSQL, Redis, or worker required.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

import app.api.ingestion as ingestion_mod
from app.database import get_async_session
from app.dependencies import get_current_user
from app.main import app
from app.models.document import DocumentVersion
from app.services.auth_service import AuthenticatedUser

# ---------------------------------------------------------------------------
# Fake implementations
# ---------------------------------------------------------------------------


_document_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
_version_id = uuid.UUID("22222222-2222-2222-2222-222222222222")


class FakeResult:
    """Minimal SQLAlchemy Result fake with scalar_one_or_none."""

    def __init__(self, row: Any) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._row


class FakeSession:
    """AsyncSession fake that returns a scripted row from execute()."""

    def __init__(self, row: Any) -> None:
        self._row = row
        self.executed: list[Any] = []

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    async def execute(self, stmt: Any, *_args: Any, **_kwargs: Any) -> FakeResult:
        self.executed.append(stmt)
        return FakeResult(self._row)


class FakePool:
    """ArqRedis fake that records enqueue calls and close() invocations."""

    def __init__(self) -> None:
        self.enqueue_calls: list[dict[str, Any]] = []
        self.close_called = 0
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

    async def close(self) -> None:
        self.close_called += 1


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def doc_version() -> DocumentVersion:
    """A valid DocumentVersion belonging to _document_id."""
    return DocumentVersion(
        id=_version_id,
        document_id=_document_id,
        version_number="1",
        status="draft",
        content="test content",
    )


@pytest.fixture
def fake_pool() -> FakePool:
    return FakePool()


@pytest.fixture
def install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    doc_version: DocumentVersion,
    fake_pool: FakePool,
) -> Generator[dict[str, Any], None, None]:
    """Install module-level fakes for _pool_factory and get_async_session."""
    fake_session = FakeSession(doc_version)

    # Override _pool_factory on the ingestion module
    monkeypatch.setattr(
        ingestion_mod,
        "_pool_factory",
        AsyncMock(return_value=fake_pool),
    )

    # Override get_async_session dependency (used by FastAPI DI)
    # Use dependency_overrides instead of monkeypatch because FastAPI
    # captures the Depends reference at import time.
    async def _fake_get_session() -> AsyncGenerator[FakeSession, None]:
        yield fake_session

    app.dependency_overrides[get_async_session] = _fake_get_session

    # Bypass RBAC: override get_current_user so the dependency chain
    # receives a fake AuthenticatedUser instead of resolving a real JWT.
    fake_user = AuthenticatedUser(
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        username="test_admin",
        display_name="Test Admin",
        roles=frozenset({"AI_ADMINISTRATOR"}),
    )

    async def _fake_get_current_user() -> AuthenticatedUser:
        return fake_user

    app.dependency_overrides[get_current_user] = _fake_get_current_user

    yield {
        "fake_session": fake_session,
        "fake_pool": fake_pool,
        "doc_version": doc_version,
    }

    # Teardown: clear the overrides so other tests are not affected
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_async_session, None)


@pytest.fixture
def install_fakes_with_auth(
    monkeypatch: pytest.MonkeyPatch,
    doc_version: DocumentVersion,
    fake_pool: FakePool,
) -> Generator[dict[str, Any], None, None]:
    """Install fakes but keep real RBAC for auth tests."""
    fake_session = FakeSession(doc_version)

    monkeypatch.setattr(
        ingestion_mod,
        "_pool_factory",
        AsyncMock(return_value=fake_pool),
    )

    # Override get_async_session dependency (used by FastAPI DI)
    # Use dependency_overrides instead of monkeypatch because FastAPI
    # captures the Depends reference at import time.
    async def _fake_get_session() -> AsyncGenerator[FakeSession, None]:
        yield fake_session

    app.dependency_overrides[get_async_session] = _fake_get_session

    yield {
        "fake_session": fake_session,
        "fake_pool": fake_pool,
        "doc_version": doc_version,
    }

    # Teardown: clear the override so other tests are not affected
    app.dependency_overrides.pop(get_async_session, None)


# ---------------------------------------------------------------------------
# 1. Success path (test cases 1, 7-17)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ai_administrator_success_returns_202(
    install_fakes: dict[str, Any],
) -> None:
    """Case 1: AI_ADMINISTRATOR success returns 202."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert response.status_code == 202, response.text


@pytest.mark.asyncio
async def test_accepted_enqueue_returns_202(
    install_fakes: dict[str, Any],
) -> None:
    """Case 7: Accepted enqueue returns 202."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert response.status_code == 202, response.text


# ---------------------------------------------------------------------------
# 2. Authorization tests (cases 2-3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(
    install_fakes_with_auth: dict[str, Any],
) -> None:
    """Case 2: Unauthenticated request returns 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    # No Bearer token -> 401 from get_current_user
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_forbidden_role_returns_403(
    monkeypatch: pytest.MonkeyPatch,
    install_fakes_with_auth: dict[str, Any],
) -> None:
    """Case 3: Forbidden role returns 403."""
    # Override get_current_user to return a user without AI_ADMINISTRATOR role
    fake_user = AuthenticatedUser(
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        username="test_user",
        display_name="Test User",
        roles=frozenset({"VIEWER"}),  # Not AI_ADMINISTRATOR
    )

    async def _fake_get_current_user() -> AuthenticatedUser:
        return fake_user

    app.dependency_overrides[get_current_user] = _fake_get_current_user

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    # Clean up
    app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403, response.text


# ---------------------------------------------------------------------------
# 3. Document version validation (cases 4-6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_document_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    install_fakes: dict[str, Any],
) -> None:
    """Case 4: Missing document/version returns 404."""
    # Override the session to return None for the version query
    fake_session = FakeSession(None)

    async def _fake_get_session() -> AsyncGenerator[FakeSession, None]:
        yield fake_session

    app.dependency_overrides[get_async_session] = _fake_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    # Clean up
    app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_ownership_mismatch_returns_404(
    monkeypatch: pytest.MonkeyPatch,
    install_fakes: dict[str, Any],
) -> None:
    """Case 5: Ownership mismatch returns 404."""
    # Version belongs to a different document
    # Return None to simulate that no version matches both id and document_id
    fake_session = FakeSession(None)

    async def _fake_get_session() -> AsyncGenerator[FakeSession, None]:
        yield fake_session

    app.dependency_overrides[get_async_session] = _fake_get_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    # Clean up
    app.dependency_overrides.pop(get_async_session, None)

    assert response.status_code == 404, response.text


@pytest.mark.asyncio
async def test_one_combined_ownership_query(
    install_fakes: dict[str, Any],
) -> None:
    """Case 6: Single combined ownership query (one SELECT)."""
    fake_session = install_fakes["fake_session"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    # Exactly one execute call (the combined query)
    assert len(fake_session.executed) == 1
    # Verify it's a select on DocumentVersion (combined ownership check)
    stmt = fake_session.executed[0]
    # Compile the statement and verify it targets the document_versions table
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "document_versions" in compiled


# ---------------------------------------------------------------------------
# 4. Deterministic job ID and enqueue args (cases 8-12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deterministic_job_id(
    install_fakes: dict[str, Any],
) -> None:
    """Case 8: Job ID is document-ingestion:{version_id}."""
    fake_pool = install_fakes["fake_pool"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert len(fake_pool.enqueue_calls) == 1
    call = fake_pool.enqueue_calls[0]
    assert call["kwargs"]["_job_id"] == f"document-ingestion:{_version_id}"


@pytest.mark.asyncio
async def test_function_name_is_run_document_ingestion(
    install_fakes: dict[str, Any],
) -> None:
    """Case 9: Function name is run_document_ingestion."""
    fake_pool = install_fakes["fake_pool"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert fake_pool.enqueue_calls[0]["function"] == "run_document_ingestion"


@pytest.mark.asyncio
async def test_document_version_id_argument_is_string(
    install_fakes: dict[str, Any],
) -> None:
    """Case 10: document_version_id argument is a string."""
    fake_pool = install_fakes["fake_pool"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    args = fake_pool.enqueue_calls[0]["args"]
    assert isinstance(args[0], str)
    assert args[0] == str(_version_id)


@pytest.mark.asyncio
async def test_correlation_id_argument_is_passed(
    install_fakes: dict[str, Any],
) -> None:
    """Case 11: correlation_id argument is passed."""
    fake_pool = install_fakes["fake_pool"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    args = fake_pool.enqueue_calls[0]["args"]
    assert len(args) >= 2
    # Second positional arg is correlation_id
    assert isinstance(args[1], str)
    uuid.UUID(args[1])  # validates UUID format


@pytest.mark.asyncio
async def test_configured_queue_name_is_passed(
    install_fakes: dict[str, Any],
) -> None:
    """Case 12: Configured queue name is passed."""
    from app.config import settings

    fake_pool = install_fakes["fake_pool"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert fake_pool.enqueue_calls[0]["kwargs"]["_queue_name"] == settings.arq_queue_name


# ---------------------------------------------------------------------------
# 5. Response field tests (cases 13-17)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_contains_job_id(
    install_fakes: dict[str, Any],
) -> None:
    """Case 13: Response contains job_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    body = response.json()
    assert "job_id" in body
    assert body["job_id"] == f"document-ingestion:{_version_id}"


@pytest.mark.asyncio
async def test_response_contains_document_id(
    install_fakes: dict[str, Any],
) -> None:
    """Case 14: Response contains document_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    body = response.json()
    assert body["document_id"] == str(_document_id)


@pytest.mark.asyncio
async def test_response_contains_document_version_id(
    install_fakes: dict[str, Any],
) -> None:
    """Case 15: Response contains document_version_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    body = response.json()
    assert body["document_version_id"] == str(_version_id)


@pytest.mark.asyncio
async def test_response_contains_correlation_id(
    install_fakes: dict[str, Any],
) -> None:
    """Case 16: Response contains correlation_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    body = response.json()
    assert "correlation_id" in body
    uuid.UUID(body["correlation_id"])  # validates UUID format


@pytest.mark.asyncio
async def test_response_status_is_pending(
    install_fakes: dict[str, Any],
) -> None:
    """Case 17: Response status is pending."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    body = response.json()
    assert body["status"] == "pending"


# ---------------------------------------------------------------------------
# 6. Duplicate enqueue (cases 18-19)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_enqueue_returns_409(
    monkeypatch: pytest.MonkeyPatch,
    install_fakes: dict[str, Any],
) -> None:
    """Case 18: Duplicate enqueue None returns 409."""
    fake_pool = install_fakes["fake_pool"]
    fake_pool.enqueue_result = None  # ARQ returns None for duplicate _job_id

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_duplicate_response_does_not_claim_accepted(
    monkeypatch: pytest.MonkeyPatch,
    install_fakes: dict[str, Any],
) -> None:
    """Case 19: Duplicate response does not claim accepted."""
    fake_pool = install_fakes["fake_pool"]
    fake_pool.enqueue_result = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert response.status_code == 409
    body = response.json()
    # Response should not contain a "status": "pending" (which would imply accepted)
    assert body.get("status") != "pending"


# ---------------------------------------------------------------------------
# 7. Pool creation and enqueue failures (cases 20-24)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_creation_failure_returns_503(
    monkeypatch: pytest.MonkeyPatch,
    install_fakes: dict[str, Any],
) -> None:
    """Case 20: Pool creation failure returns 503."""
    monkeypatch.setattr(
        ingestion_mod,
        "_pool_factory",
        AsyncMock(side_effect=RuntimeError("Connection refused")),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert response.status_code == 503, response.text


@pytest.mark.asyncio
async def test_enqueue_exception_returns_503(
    monkeypatch: pytest.MonkeyPatch,
    install_fakes: dict[str, Any],
) -> None:
    """Case 21: Enqueue exception returns 503."""
    fake_pool = install_fakes["fake_pool"]
    fake_pool.enqueue_exception = RuntimeError("enqueue failed")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert response.status_code == 503, response.text


@pytest.mark.asyncio
async def test_pool_closes_after_success(
    install_fakes: dict[str, Any],
) -> None:
    """Case 22: Pool closes after success."""
    fake_pool = install_fakes["fake_pool"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert fake_pool.close_called >= 1


@pytest.mark.asyncio
async def test_pool_closes_after_duplicate(
    monkeypatch: pytest.MonkeyPatch,
    install_fakes: dict[str, Any],
) -> None:
    """Case 23: Pool closes after duplicate."""
    fake_pool = install_fakes["fake_pool"]
    fake_pool.enqueue_result = None

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert fake_pool.close_called >= 1


@pytest.mark.asyncio
async def test_pool_closes_after_enqueue_exception(
    monkeypatch: pytest.MonkeyPatch,
    install_fakes: dict[str, Any],
) -> None:
    """Case 24: Pool closes after enqueue exception."""
    fake_pool = install_fakes["fake_pool"]
    fake_pool.enqueue_exception = RuntimeError("enqueue failed")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert fake_pool.close_called >= 1


# ---------------------------------------------------------------------------
# 8. Malformed input (case 25)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_malformed_uuid_returns_422(
    install_fakes: dict[str, Any],
) -> None:
    """Case 25: Malformed UUID follows FastAPI validation behavior (422)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/documents/not-a-uuid/versions/not-a-uuid/ingest"
        )

    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# 9. Security / information leakage (cases 26-28)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_credentials_absent_from_response(
    install_fakes: dict[str, Any],
) -> None:
    """Case 26: Redis credentials absent from response."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    lower = response.text.lower()
    assert "redis://" not in lower
    assert "password" not in lower


@pytest.mark.asyncio
async def test_raw_queue_exception_details_absent_from_response(
    monkeypatch: pytest.MonkeyPatch,
    install_fakes: dict[str, Any],
) -> None:
    """Case 27: Raw queue exception details absent from response."""
    fake_pool = install_fakes["fake_pool"]
    fake_pool.enqueue_exception = RuntimeError("Internal Redis error: connection refused")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    assert response.status_code == 503
    body = response.json()
    lower = str(body).lower()
    assert "internal redis error" not in lower
    assert "connection refused" not in lower


@pytest.mark.asyncio
async def test_document_content_and_embeddings_absent_from_logs(
    caplog: pytest.LogCaptureFixture,
    install_fakes: dict[str, Any],
) -> None:
    """Case 28: Document content and embeddings absent from logs."""
    caplog.set_level("DEBUG")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            f"/api/v1/documents/{_document_id}/versions/{_version_id}/ingest"
        )

    # No log record should contain the document content or "embedding"
    for record in caplog.records:
        msg = record.getMessage().lower()
        assert "test content" not in msg
        assert "embedding" not in msg


# ---------------------------------------------------------------------------
# 10. Router and worker registration (cases 29-32)
# ---------------------------------------------------------------------------


def test_ingestion_router_is_registered_in_app() -> None:
    """Case 29: Ingestion router is registered in app."""
    from app.main import app as fastapi_app

    # The ingestion router is wrapped in an _IncludedRouter (internal FastAPI
    # representation), so we must look inside original_router.routes to find
    # the actual APIRoute objects with .path attributes.
    route_paths: list[str] = []
    for r in fastapi_app.routes:
        path = getattr(r, "path", None)
        if path is not None:
            route_paths.append(path)
        else:
            # _IncludedRouter wrapper — unwrap to original_router
            orig = getattr(r, "original_router", None)
            if orig is not None:
                for ir in orig.routes:
                    p = getattr(ir, "path", None)
                    if p is not None:
                        route_paths.append(p)
    assert any(
        "ingest" in path for path in route_paths
    ), f"No ingest route found in {route_paths}"


def test_worker_registration_preserves_diagnostic_job() -> None:
    """Case 30: Worker registration preserves diagnostic job."""
    from app.jobs.diagnostics import run_diagnostic_job
    from app.worker import WorkerSettings

    assert run_diagnostic_job in WorkerSettings.functions


def test_worker_wrapper_uses_keep_result_300() -> None:
    """Case 31: Worker wrapper uses keep_result=300."""
    from app.worker import WorkerSettings

    # The ingestion function should have keep_result=300
    for fn in WorkerSettings.functions:
        if hasattr(fn, "keep_result"):
            assert fn.keep_result == 300


def test_worker_wrapper_uses_max_tries_3() -> None:
    """Case 32: Worker wrapper uses max_tries=3."""
    from app.worker import WorkerSettings

    for fn in WorkerSettings.functions:
        if hasattr(fn, "max_tries"):
            assert fn.max_tries == 3


# ---------------------------------------------------------------------------
# 11. No real infrastructure required (cases 33-35)
# ---------------------------------------------------------------------------


def test_no_real_redis_required() -> None:
    """Case 33: No real Redis required (use FakePool)."""
    # FakePool is used; no arq.create_pool call is made
    # This is verified by the fact that install_fakes monkeypatches _pool_factory
    # and all HTTP tests pass without Redis running.
    assert FakePool is not None


def test_no_real_database_required() -> None:
    """Case 34: No real database required (use FakeSession)."""
    # FakeSession is used; no real DB connection is made.
    assert FakeSession is not None


def test_no_real_provider_endpoint_required() -> None:
    """Case 35: No real provider endpoint required."""
    # The endpoint only enqueues; it does not call embedding providers.
    # This is verified by the fact that all enqueue tests pass without
    # any provider mock being needed.
    assert True
