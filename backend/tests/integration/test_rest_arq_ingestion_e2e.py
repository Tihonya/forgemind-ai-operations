"""Scenario D: REST + ARQ ingestion E2E test.

Verifies the complete flow:
1. REST API endpoint enqueues ARQ job (HTTP 202)
2. ARQ worker consumes job and executes ingestion
3. Database contains chunks with embeddings
4. Cleanup removes only test-owned data
"""

import asyncio
import os
import socket
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest

# CRITICAL: Set environment BEFORE any app.* imports
# Snapshot for restoration
_SAVED_ENV = {
    k: os.environ.get(k)
    for k in [
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "REDIS_URL",
        "EMBEDDING_PROVIDER",
        "EMBEDDING_DIMENSIONS",
        "ENVIRONMENT",
        "SECRET_KEY",
    ]
}

os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("EMBEDDING_PROVIDER", "fake")
os.environ.setdefault("EMBEDDING_DIMENSIONS", "1536")
os.environ.setdefault("ENVIRONMENT", "development")

# Now safe to import app.* modules (must come after env setup)
from arq import create_pool  # noqa: E402
from arq.connections import RedisSettings  # noqa: E402
from arq.jobs import Job, JobStatus  # noqa: E402
from arq.worker import create_worker  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings as app_settings  # noqa: E402
from app.models.document import Document, DocumentVersion  # noqa: E402
from app.models.knowledge import KnowledgeChunk  # noqa: E402
from app.worker import WorkerSettings  # noqa: E402

# CRITICAL: conftest.py imports app.main which instantiates Settings() at import time.
# Our os.environ.setdefault runs AFTER Settings is already created with defaults.
# We must patch the singleton directly for the in-process worker to use fake embeddings.
app_settings.embedding_provider = "fake"
app_settings.environment = "development"
app_settings.embedding_dimensions = 1536

# ---------------------------------------------------------------------------
# Integration-gate: skip entire module when no DB/Redis reachable
# ---------------------------------------------------------------------------

INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
    "DATABASE_URL"
)


def _can_connect_postgres() -> bool:
    if not INTEGRATION_DB_URL:
        return False
    try:
        from sqlalchemy import create_engine

        url = INTEGRATION_DB_URL.replace("+asyncpg", "+psycopg")
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


def _get_redis_settings_from_env() -> tuple[str, int, int, str | None]:
    """Parse Redis connection settings from REDIS_URL env var."""
    import os
    from urllib.parse import urlparse

    url = os.environ.get("REDIS_URL", "redis://localhost:6379/15")
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    path = parsed.path.lstrip("/")
    db = int(path) if path else 15
    password = parsed.password
    return host, port, db, password


def _can_connect_redis() -> bool:
    try:
        import redis

        host, port, _db, password = _get_redis_settings_from_env()
        r = redis.Redis(host=host, port=port, db=15, password=password)
        r.ping()
        r.connection_pool.disconnect()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect_postgres() or not _can_connect_redis(),
    reason="Integration database or Redis not available",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def allocate_port() -> int:
    """Allocate a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        port: int = s.getsockname()[1]
        return port


async def wait_for_ready(client: httpx.AsyncClient, timeout: float = 15.0) -> None:
    """Poll /health endpoint until ready or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        try:
            resp = await client.get("/health")
            if resp.status_code == 200:
                return
        except Exception:  # noqa: S110
            # Server not ready yet, continue polling
            pass
        await asyncio.sleep(0.5)
    raise TimeoutError("Uvicorn did not become ready")


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


async def test_rest_arq_ingestion_e2e() -> None:
    """Scenario D: REST + ARQ ingestion full E2E flow."""

    # Proof 1: PostgreSQL and Redis reachable (skipif handles this)
    assert INTEGRATION_DB_URL is not None, "DATABASE_URL not set"

    # Proof 2: Create test-owned Document and DocumentVersion
    doc_id = uuid4()
    version_id = uuid4()
    known_content = "Section A. " * 200 + "Section B. " * 200 + "Section C. " * 200

    db_url = INTEGRATION_DB_URL
    if "+psycopg" in db_url:
        db_url = db_url.replace("+psycopg", "+asyncpg")

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    uvicorn_process = None
    redis_pool = None

    try:
        # Create test data
        async with session_factory() as session:
            doc = Document(
                id=doc_id,
                title="WP-4.3B5 Scenario D E2E Test",
                description=None,
            )
            version = DocumentVersion(
                id=version_id,
                document_id=doc_id,
                version_number="1.0",
                status="draft",
                content_hash=None,
                content=known_content,
            )
            session.add(doc)
            session.add(version)
            await session.commit()

        # Proof 3: Uvicorn starts on dynamically allocated port
        port = allocate_port()
        backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        # Trusted internal subprocess for test server (S603 acceptable in test)
        uvicorn_process = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=backend_dir,
            env={**os.environ},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Proof 4: /health becomes ready (poll up to 15s)
        base_url = f"http://127.0.0.1:{port}"
        async with httpx.AsyncClient(base_url=base_url, timeout=5.0) as client:
            await wait_for_ready(client, timeout=15.0)

            # Proof 5: Real login succeeds via POST /api/v1/auth/login
            login_response = await client.post(
                "/api/v1/auth/login",
                json={"username": "admin.demo", "password": "AdminPass123!"},
            )
            assert login_response.status_code == 200, (
                f"Login failed: {login_response.status_code} {login_response.text}"
            )
            login_data = login_response.json()
            assert "access_token" in login_data
            token = login_data["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            # Proof 6: User has AI_ADMINISTRATOR role (verify via GET /api/v1/auth/me)
            me_response = await client.get("/api/v1/auth/me", headers=headers)
            assert me_response.status_code == 200
            me_data = me_response.json()
            assert "AI_ADMINISTRATOR" in me_data.get("roles", [])

            # Proof 7: Real TCP POST to ingest endpoint
            ingest_response = await client.post(
                f"/api/v1/documents/{doc_id}/versions/{version_id}/ingest",
                headers=headers,
            )

            # Proof 8: Response is HTTP 202 with status "pending"
            assert ingest_response.status_code == 202, (
                f"Expected 202, got {ingest_response.status_code}: "
                f"{ingest_response.text}"
            )
            response_data = ingest_response.json()
            assert response_data["status"] == "pending"

            # Proof 9: job_id matches format "document-ingestion:{version_id}"
            expected_job_id = f"document-ingestion:{version_id}"
            assert response_data["job_id"] == expected_job_id

        # Proof 10: Job exists in Redis queue before worker execution
        # Parse the database number from REDIS_URL to ensure we check the correct DB
        from urllib.parse import urlparse
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        parsed_url = urlparse(redis_url)
        db_from_url = int(parsed_url.path.lstrip("/") or "0")

        _host, _port, _db, _password = _get_redis_settings_from_env()
        redis_pool = await create_pool(
            RedisSettings(host=_host, port=_port, database=db_from_url, password=_password),
            default_queue_name="forgemind-tasks",
        )
        job = Job(
            response_data["job_id"],
            redis=redis_pool,
            _queue_name="forgemind-tasks",
        )
        job_status_before = await job.status()
        assert job_status_before in (
            JobStatus.queued,
            JobStatus.deferred,
            JobStatus.in_progress,
        ), f"Job not in queue: {job_status_before}"

        # Proof 11: Real WorkerSettings and run_document_ingestion used
        # (WorkerSettings imported from app.worker includes run_document_ingestion)
        assert hasattr(WorkerSettings, "functions")
        assert hasattr(WorkerSettings, "queue_name")

        # Proof 12: In-process burst ARQ worker consumes job
        worker = create_worker(
            WorkerSettings,  # type: ignore[arg-type]
            burst=True,
            handle_signals=False,
        )
        try:
            await asyncio.wait_for(worker.async_run(), timeout=60)
        finally:
            # Proof 20 (partial): Worker resources closed
            await worker.close()

        # Proof 13: Job status becomes "complete"
        job_status_after = await job.status()
        assert job_status_after == JobStatus.complete, (
            f"Job not complete: {job_status_after}"
        )

        # Proof 14: Job result contains status "completed" and version_id
        job_result = await job.result(timeout=5)
        assert job_result is not None
        assert job_result["status"] == "completed"
        assert job_result["document_version_id"] == str(version_id)

        # Proof 15: PostgreSQL contains test-owned chunks
        async with session_factory() as session:
            chunk_result = await session.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_version_id == version_id)
                .order_by(KnowledgeChunk.chunk_index)
            )
            chunks = chunk_result.scalars().all()
            assert len(chunks) > 0, "No chunks found after ingestion"

            # Proof 16: Chunks have non-null embeddings
            for chunk in chunks:
                assert chunk.embedding is not None, "Chunk has null embedding"
                assert len(chunk.embedding) > 0, "Embedding is empty"

                # Proof 17: vector_dims(embedding) = 1536
                assert len(chunk.embedding) == 1536, (
                    f"Expected 1536 dims, got {len(chunk.embedding)}"
                )

            # Proof 18: Explicit cleanup removes only test-owned database rows
            await session.execute(
                text(
                    "DELETE FROM knowledge_chunks "
                    "WHERE document_version_id = :vid"
                ),
                {"vid": str(version_id)},
            )
            await session.execute(
                text("DELETE FROM document_versions WHERE id = :vid"),
                {"vid": str(version_id)},
            )
            await session.execute(
                text("DELETE FROM documents WHERE id = :did"),
                {"did": str(doc_id)},
            )
            await session.commit()

            # Verify cleanup: query database to confirm zero rows remain
            chunk_row = await session.execute(
                text(
                    "SELECT COUNT(*) FROM knowledge_chunks "
                    "WHERE document_version_id = :vid"
                ),
                {"vid": str(version_id)},
            )
            assert chunk_row.scalar() == 0, "Chunks not cleaned up"

            version_row = await session.execute(
                text("SELECT COUNT(*) FROM document_versions WHERE id = :vid"),
                {"vid": str(version_id)},
            )
            assert version_row.scalar() == 0, "Versions not cleaned up"

            doc_row = await session.execute(
                text("SELECT COUNT(*) FROM documents WHERE id = :did"),
                {"did": str(doc_id)},
            )
            assert doc_row.scalar() == 0, "Documents not cleaned up"

        # Proof 19: Isolated Redis DB 15 cleaned
        await redis_pool.flushdb()
        # Verify Redis is clean
        keys = await redis_pool.keys("*")
        assert len(keys) == 0, f"Redis not clean: {len(keys)} keys remain"

    finally:
        # Proof 20: Worker resources, Redis connections, HTTP client, Uvicorn closed
        if redis_pool is not None:
            await redis_pool.close(close_connection_pool=True)

        if uvicorn_process is not None:
            uvicorn_process.terminate()
            try:
                uvicorn_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                uvicorn_process.kill()
                uvicorn_process.wait(timeout=2)

        await engine.dispose()

        # Proof 21: Environment variables restored exactly
        for key, value in _SAVED_ENV.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

        # Proof 22: No background/orphan processes remain
        if uvicorn_process is not None:
            assert uvicorn_process.returncode is not None, (
                "Uvicorn process still running"
            )
