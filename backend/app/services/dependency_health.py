"""Dependency health check primitives.

Provides async functions to check the health of PostgreSQL, Redis, Alembic,
and ARQ worker. Each check returns a typed DependencyCheck result with status,
latency, and safe detail. Checks are isolated and never raise exceptions.

ARQ Worker Health Mechanism:
    ARQ workers write a heartbeat to Redis key: {queue_name}:health-check
    Key contains timestamped job stats (ISO format) and has TTL slightly longer
    than health_check_interval (default 3600s). The key is written immediately
    on worker startup and periodically during the worker's lifetime.

    This check reads the key existence. If present -> worker is alive. If absent ->
    worker has not yet started or has stopped. Status is "ok" or "unknown", never
    "error", because absence is not necessarily a failure (e.g., worker starting up).

    Mechanism is documented in ARQ source: arq/worker.py record_health(),
    arq/constants.py health_check_key_suffix. No custom implementation required.
"""

from __future__ import annotations

import contextlib
import time

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database import engine
from app.schemas.health import DependencyCheck, DependencyHealthSnapshot


async def check_postgresql() -> DependencyCheck:
    """Check PostgreSQL connectivity via SELECT 1.

    Uses the existing async SQLAlchemy engine. Returns "ok" with latency on
    success, "error" with safe detail on failure. Never raises exceptions.

    Returns:
        DependencyCheck with status, latency_ms, and optional detail.
    """
    start = time.perf_counter()
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - start) * 1000
        return DependencyCheck(
            name="postgresql",
            status="ok",
            latency_ms=latency_ms,
            detail="SELECT 1 succeeded",
        )
    except SQLAlchemyError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        # Safe detail: exception class name only, no message (may contain sensitive info)
        detail = f"SQLAlchemy error: {type(exc).__name__}"
        return DependencyCheck(
            name="postgresql",
            status="error",
            latency_ms=latency_ms,
            detail=detail,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        detail = f"Unexpected error: {type(exc).__name__}"
        return DependencyCheck(
            name="postgresql",
            status="error",
            latency_ms=latency_ms,
            detail=detail,
        )


async def check_redis() -> DependencyCheck:
    """Check Redis connectivity via PING.

    Uses redis.asyncio with settings.redis_url. Returns "ok" with latency on
    success, "error" with safe detail on failure. Never raises exceptions.

    Returns:
        DependencyCheck with status, latency_ms, and optional detail.
    """
    from redis.asyncio import Redis

    from app.config import settings

    start = time.perf_counter()
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        result = await redis_client.ping()
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        detail = f"Redis error: {type(exc).__name__}"
        return DependencyCheck(
            name="redis",
            status="error",
            latency_ms=latency_ms,
            detail=detail,
        )
    finally:
        with contextlib.suppress(Exception):
            await redis_client.close()
    latency_ms = (time.perf_counter() - start) * 1000
    if result:
        return DependencyCheck(
            name="redis",
            status="ok",
            latency_ms=latency_ms,
            detail="PING succeeded",
        )
    return DependencyCheck(
        name="redis",
        status="error",
        latency_ms=latency_ms,
        detail="PING returned False",
    )


async def check_alembic() -> DependencyCheck:
    """Check Alembic current revision from alembic_version table.

    Queries the alembic_version table for the current revision hash. Returns
    "ok" with revision in detail if found, "unknown" if table does not exist
    or database is unavailable. Never raises exceptions.

    Returns:
        DependencyCheck with status, latency_ms, and optional detail.
    """
    start = time.perf_counter()
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            row = result.fetchone()
        latency_ms = (time.perf_counter() - start) * 1000
        if row:
            revision = row[0]
            return DependencyCheck(
                name="alembic",
                status="ok",
                latency_ms=latency_ms,
                detail=f"revision {revision[:8]}",
            )
        return DependencyCheck(
            name="alembic",
            status="unknown",
            latency_ms=latency_ms,
            detail="alembic_version table is empty",
        )
    except SQLAlchemyError as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        # Check if it's a "table does not exist" error
        if "does not exist" in str(exc).lower() or "no such table" in str(exc).lower():
            return DependencyCheck(
                name="alembic",
                status="unknown",
                latency_ms=latency_ms,
                detail="alembic_version table does not exist",
            )
        detail = f"SQLAlchemy error: {type(exc).__name__}"
        return DependencyCheck(
            name="alembic",
            status="error",
            latency_ms=latency_ms,
            detail=detail,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        detail = f"Unexpected error: {type(exc).__name__}"
        return DependencyCheck(
            name="alembic",
            status="error",
            latency_ms=latency_ms,
            detail=detail,
        )


async def check_arq_worker() -> DependencyCheck:
    """Check ARQ worker availability via health check key in Redis.

    ARQ workers write a heartbeat to Redis key: {queue_name}:health-check
    (see arq/constants.py health_check_key_suffix). The key is written immediately
    on worker startup and periodically (default every 3600s) during the worker's
    lifetime. The key has a TTL slightly longer than the check interval.

    This check reads the key existence via Redis GET. If present → worker is alive.
    If absent → worker has not yet started or has stopped. Status is "ok" or
    "unknown", never "error", because absence is not necessarily a failure
    (e.g., worker starting up).

    Mechanism is documented in ARQ source:
    - arq/worker.py record_health() (line 773)
    - arq/constants.py health_check_key_suffix (line 9)
    - arq/cli.py async_check_health() (line 903)

    Returns:
        DependencyCheck with status "ok" or "unknown", latency_ms, and optional detail.
    """
    from arq.constants import health_check_key_suffix
    from redis.asyncio import Redis

    from app.config import settings

    # Compute the health check key using ARQ's documented constant.
    # Risk: health_check_key_suffix is an internal ARQ constant (arq/constants.py
    # line 9) not part of the public API. May break on major ARQ upgrades.
    # Current stable version: 0.28.0. The ARQ worker itself derives the key the
    # same way (arq/worker.py line 257-259), so this is safe in practice.
    queue_name = settings.arq_queue_name
    health_check_key = f"{queue_name}{health_check_key_suffix}"

    start = time.perf_counter()
    redis_client = Redis.from_url(settings.redis_url, decode_responses=False)
    try:
        data = await redis_client.get(health_check_key)
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        detail = f"Redis error: {type(exc).__name__}"
        return DependencyCheck(
            name="worker",
            status="unknown",
            latency_ms=latency_ms,
            detail=detail,
        )
    finally:
        with contextlib.suppress(Exception):
            await redis_client.close()
    latency_ms = (time.perf_counter() - start) * 1000

    if data is None:
        # Key absent: worker not yet started or has stopped
        return DependencyCheck(
            name="worker",
            status="unknown",
            latency_ms=latency_ms,
            detail="worker health check key not found",
        )

    # Validate the health check value is a well-formed ARQ heartbeat.
    # ARQ worker writes: "{datetime:%b-%d %H:%M:%S} j_complete=... j_failed=..."
    # If the key contains an unparseable value (set by another process), do not
    # treat it as healthy.
    try:
        info = data.decode("utf-8") if isinstance(data, bytes) else str(data)
    except (UnicodeDecodeError, ValueError):
        return DependencyCheck(
            name="worker",
            status="unknown",
            latency_ms=latency_ms,
            detail="worker health check key contains malformed data",
        )

    # Require the ARQ heartbeat signature fields
    if "j_complete=" not in info or "j_failed=" not in info:
        return DependencyCheck(
            name="worker",
            status="unknown",
            latency_ms=latency_ms,
            detail="worker health check key missing ARQ signature fields",
        )

    detail = info[:50] if len(info) > 50 else info
    return DependencyCheck(
        name="worker",
        status="ok",
        latency_ms=latency_ms,
        detail=detail,
    )


async def check_all_dependencies() -> DependencyHealthSnapshot:
    """Execute all dependency checks and aggregate into a snapshot.

    Runs checks sequentially for simplicity and error isolation. Each check
    catches its own exceptions, so one failure does not prevent others from
    running. The snapshot summary is computed from individual check statuses.

    This function does not:
    - Query latest diagnostic jobs
    - Include build metadata
    - Read correlation context
    - Decide HTTP status codes

    Returns:
        DependencyHealthSnapshot with ordered list of checks and computed summary.
    """
    checks = [
        await check_postgresql(),
        await check_redis(),
        await check_alembic(),
        await check_arq_worker(),
    ]
    return DependencyHealthSnapshot.from_checks(checks)
