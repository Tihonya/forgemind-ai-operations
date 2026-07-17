"""Service for creating and enqueuing diagnostic jobs.

Public contract (plan §11.1):
    POST /api/v1/system/diagnostics → HTTP 202
    {
        "job_id":         "<uuid>",
        "correlation_id": "<uuid-v4>",
        "status":         "pending"
    }

Design invariants:
1. The DiagnosticJob row is inserted and committed in a short-lived session
   that is always closed before any Redis/ARQ interaction.
2. An optional ``redis_pool`` may be injected (for tests / future lifespan
   caching). If ``None``, the service creates an owned ``ArqRedis`` pool
   via ``_pool_factory`` and closes it in a ``finally`` block exactly
   once, regardless of success, enqueue failure, or exception.
3. ARQ enqueue uses ``_job_id="diagnostic-job-<db-job-uuid>"`` so that
   duplicate HTTP retries for the same database row cannot produce
   duplicate worker executions. The ARQ job id is derived only from the
   diagnostic-job UUID, never from the correlation id.
4. Enqueue returns ``None`` (duplicate _job_id already in queue) or
   raises: the pending row is then re-opened via a fresh session and
   transitioned to ``status="failed"`` with a bounded, single-line,
   secret-free ``error_message``. The pending row is never left orphaned.
5. The ARQ function name ``"run_diagnostic_job"`` matches the worker's
   registered ``__qualname__`` (verified in app/worker.py).

Testability:
- ``_pool_factory``: module-level async callable; production uses
  ``arq.connections.create_pool``. Tests monkeypatch this attribute on
  the service module directly, no implementation-internals patching
  needed.
- ``_session_factory``: module-level alias of
  ``app.database.async_session_factory``. Tests monkeypatch this
  attribute on the service module.
"""

from __future__ import annotations

import uuid as _uuid_module
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.logging import get_logger
from app.models.diagnostic import DiagnosticJob
from app.schemas.diagnostic import DiagnosticCreateResponse, DiagnosticJobResponse

if TYPE_CHECKING:  # pragma: no cover - typing only
    from arq.connections import ArqRedis

logger = get_logger(__name__)

# Safe, bounded, static error text. Never interpolated with raw
# exception strings, connection URLs, or passwords.
_SAFE_ENQUEUE_ERROR_MESSAGE: str = (
    "The diagnostic job could not be enqueued. Please retry."
)
_MAX_ERROR_MESSAGE_LENGTH: int = 200

# Module-level pool factory.
# Production: set to arq.connections.create_pool at import completion.
# Tests: monkeypatch ``service._pool_factory`` directly.
PoolFactory = Callable[
    [],  # No positional args
    Awaitable["ArqRedis"],
]


def _build_redis_settings() -> Any:
    """Build ARQ RedisSettings from app config without connecting.

    Returns an arq.connections.RedisSettings instance (typed as Any to
    avoid requiring arq at module import time).
    """
    from arq.connections import RedisSettings

    parsed = urlparse(settings.redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    path = parsed.path.lstrip("/")
    db = int(path) if path else 0
    password = parsed.password
    return RedisSettings(
        host=host,
        port=port,
        database=db,
        password=password,
    )


async def _default_pool_factory() -> ArqRedis:
    """Production pool factory wrapping arq.connections.create_pool."""
    from arq.connections import create_pool

    return await create_pool(_build_redis_settings())


# Module-level reference; monkeypatchable by tests.
_pool_factory: PoolFactory = _default_pool_factory


def _arq_job_id(diagnostic_job_id: _uuid_module.UUID) -> str:
    """Deterministic ARQ ``_job_id`` derived ONLY from the DB row UUID.

    Format: ``"diagnostic-job-<uuid>"``. Deliberately NOT the correlation id,
    per contract: the correlation id travels as an argument, not as the
    queue-level dedup key.
    """
    return f"diagnostic-job-{diagnostic_job_id}"


async def enqueue_diagnostic_job(
    *,
    correlation_id: str,
    triggered_by: str = "api",
    redis_pool: ArqRedis | None = None,
) -> DiagnosticCreateResponse:
    """Create a pending DiagnosticJob row, then enqueue the worker task.

    Transaction sequence:
        1. Open session via ``_session_factory``.
        2. INSERT DiagnosticJob row (status=pending, correlation_id, triggered_by).
        3. commit(); session __aexit__ closes it.
        4. Obtain an ARQ Redis pool (owned if none injected).
        5. enqueue_job("run_diagnostic_job", <job_id_str>, <correlation_str>,
                        _job_id="diagnostic-job-<uuid>",
                        _queue_name=settings.arq_queue_name).
        6. On exception or None return, mark row failed via a fresh session.
        7. Close owned pool in finally.

    Args:
        correlation_id: Request correlation UUID-v4 string.
        triggered_by: Operator/trigger identifier; defaults to ``"api"``.
        redis_pool: Optional ARQ Redis pool. If ``None``, the service creates
            an owned pool that is closed exactly once on every exit path.
            If supplied, the caller retains ownership and the service
            does NOT close the pool.

    Returns:
        ``DiagnosticCreateResponse`` (HTTP 202 body) on success.

    Raises:
        fastapi.HTTPException(503): Enqueue failure; row is marked failed
            with a safe bounded ``error_message``.
        ValueError: ``correlation_id`` is not a valid UUID.
    """
    from fastapi import HTTPException

    # Validate correlation id up front — raises ValueError cleanly.
    correlation_uuid = _uuid_module.UUID(correlation_id)

    # New DB row UUID (UUID-v4 by default from uuid.uuid4()).
    job_uuid = _uuid_module.uuid4()

    # 1-3. Create pending row and commit in a short-lived session.
    async with _session_factory() as session:
        job_row = DiagnosticJob(
            id=job_uuid,  # explicit id so ARQ job id stays deterministic
            correlation_id=correlation_uuid,
            status="pending",
            triggered_by=triggered_by,
        )
        session.add(job_row)
        await session.commit()
        # Populate server-default timestamps on Python object for response.
        await session.refresh(job_row)

    # At this point the session's __aexit__ has run; it is closed.

    # 4. Obtain ARQ Redis pool.
    owned_pool = redis_pool is None
    pool: ArqRedis | None = redis_pool
    arq_job_id_value = _arq_job_id(job_uuid)

    try:
        if pool is None:
            pool = await _pool_factory()

        # 5. Enqueue the ARQ task.
        try:
            enqueued_job = await pool.enqueue_job(
                "run_diagnostic_job",
                str(job_uuid),
                correlation_id,
                _job_id=arq_job_id_value,
                _queue_name=settings.arq_queue_name,
            )
        except Exception as exc:
            await _mark_enqueue_failure(
                job_uuid, reason=type(exc).__name__
            )
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "diagnostic_job_enqueue_failed",
                    "job_id": str(job_uuid),
                    "correlation_id": correlation_id,
                    "detail": _SAFE_ENQUEUE_ERROR_MESSAGE,
                },
            ) from None

        # ARQ returns None when a job with the same _job_id already exists.
        # For a freshly-minted unique UUID this should not normally occur;
        # treat it as an enqueue failure so the row is never left pending.
        if enqueued_job is None:
            await _mark_enqueue_failure(job_uuid, reason="duplicate_lease")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "diagnostic_job_enqueue_failed",
                    "job_id": str(job_uuid),
                    "correlation_id": correlation_id,
                    "detail": _SAFE_ENQUEUE_ERROR_MESSAGE,
                },
            )

        logger.info(
            "diagnostic_job_enqueued",
            diagnostic_job_id=str(job_uuid),
            arq_job_id=arq_job_id_value,
            status="pending",
        )

        return DiagnosticCreateResponse(
            job_id=job_uuid,
            correlation_id=correlation_uuid,
            status="pending",
        )
    finally:
        # 7. Close pool we created; never close an injected pool.
        # ArqRedis extends redis.asyncio.Redis; close() is guaranteed
        # to exist in both runtime and type stubs.
        if owned_pool and pool is not None:
            await pool.close()


async def _mark_enqueue_failure(
    job_uuid: _uuid_module.UUID, *, reason: str
) -> None:
    """Transition a pending row to status='failed' with a safe error_message.

    Uses a fresh session (the original enqueue session is already closed).
    The stored error_message is bounded, single-line, and never contains
    raw exception text, connection URLs, or credentials.

    If this compensation itself fails, the failure is logged but not
    re-raised, so the original HTTP 503 is always returned to the client.
    """
    safe_message = f"Enqueue failed: {reason}"
    safe_message = safe_message.replace("\n", " ").replace("\r", " ")
    if len(safe_message) > _MAX_ERROR_MESSAGE_LENGTH:
        safe_message = safe_message[:_MAX_ERROR_MESSAGE_LENGTH]

    now = datetime.now(UTC)
    try:
        async with _session_factory() as session:
            result = await session.execute(
                select(DiagnosticJob).where(DiagnosticJob.id == job_uuid)
            )
            job_row = result.scalar_one_or_none()
            if job_row is None:
                return
            job_row.status = "failed"
            job_row.completed_at = now
            job_row.error_message = safe_message
            job_row.updated_at = now
            await session.commit()
    except Exception:
        logger.exception(
            "diagnostic_job_enqueue_failure_persistence_failed",
            diagnostic_job_id=str(job_uuid),
        )


# ---------------------------------------------------------------------------
# Session-factory indirection.
#
# In production this is ``app.database.async_session_factory``.
# We assign it via a module-level alias so unit tests can monkeypatch
# this attribute without touching production wiring, and so the service
# function itself is independent of FastAPI ``Depends`` (the endpoint
# does not hold the session during enqueue).
# ---------------------------------------------------------------------------
from app.database import async_session_factory as _production_session_factory  # noqa: E402

_session_factory: async_sessionmaker[AsyncSession] = _production_session_factory


async def get_diagnostic_job(
    job_id: _uuid_module.UUID,
) -> DiagnosticJobResponse | None:
    """Look up a diagnostic job by primary key.

    Read-only: no commit, no rollback (not needed for read), no Redis
    interaction, no enqueue.

    Args:
        job_id: Primary key UUID of the diagnostic job.

    Returns:
        ``DiagnosticJobResponse`` if the row exists, ``None`` otherwise.
    """
    async with _session_factory() as session:
        result = await session.execute(
            select(DiagnosticJob).where(DiagnosticJob.id == job_id)
        )
        job_row = result.scalar_one_or_none()

        if job_row is None:
            return None

        # Convert persisted ORM checks (list[dict[str, Any]] | None) to
        # validated DependencyCheck models. Validate each dict through the
        # Pydantic model to ensure type safety without altering persisted
        # JSON shape or worker behavior.
        validated_checks = None
        if job_row.checks is not None:
            from app.schemas.health import DependencyCheck
            validated_checks = [DependencyCheck.model_validate(check) for check in job_row.checks]

        # Map detached ORM attributes to response schema.
        # Timestamps → ISO-8601 strings; UUIDs pass through directly.
        return DiagnosticJobResponse(
            id=job_row.id,
            correlation_id=job_row.correlation_id,
            status=job_row.status,
            checks=validated_checks,
            error_message=job_row.error_message,
            started_at=(
                job_row.started_at.isoformat()
                if job_row.started_at is not None
                else None
            ),
            completed_at=(
                job_row.completed_at.isoformat()
                if job_row.completed_at is not None
                else None
            ),
            duration_ms=job_row.duration_ms,
            created_at=job_row.created_at.isoformat(),
        )
