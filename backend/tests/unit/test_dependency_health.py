"""Unit tests for dependency health check primitives.

Tests cover PostgreSQL, Redis, Alembic, and ARQ worker health checks.
All tests use mocks to avoid requiring real external services.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from app.schemas.health import DependencyCheck, DependencyHealthSnapshot
from app.services.dependency_health import (
    check_alembic,
    check_all_dependencies,
    check_arq_worker,
    check_postgresql,
    check_redis,
)


@pytest.mark.asyncio
async def test_check_postgresql_success():
    """Test PostgreSQL check returns 'ok' with valid latency on success."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    with patch("app.services.dependency_health.engine", mock_engine):
        result = await check_postgresql()

    assert isinstance(result, DependencyCheck)
    assert result.name == "postgresql"
    assert result.status == "ok"
    assert result.latency_ms >= 0
    assert result.detail is not None
    assert result.detail is not None
    assert "SELECT 1" in result.detail


@pytest.mark.asyncio
async def test_check_postgresql_operational_error():
    """Test PostgreSQL check returns 'error' with safe detail on failure."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=OperationalError("mock", {}, Exception("mock")))
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    with patch("app.services.dependency_health.engine", mock_engine):
        result = await check_postgresql()

    assert isinstance(result, DependencyCheck)
    assert result.name == "postgresql"
    assert result.status == "error"
    assert result.latency_ms >= 0
    assert result.detail is not None
    # Verify safe detail: only exception class name, no message
    assert result.detail is not None
    assert "SQLAlchemy error" in result.detail
    assert result.detail is not None
    assert "OperationalError" in result.detail
    # Ensure no connection string or sensitive info leaked
    assert result.detail is not None
    assert "postgres://" not in result.detail
    assert result.detail is not None
    assert result.detail is not None
    assert "password" not in result.detail.lower()


@pytest.mark.asyncio
async def test_check_postgresql_unexpected_error():
    """Test PostgreSQL check handles unexpected exceptions safely."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=ValueError("sensitive connection string postgres://user:pass"))
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    with patch("app.services.dependency_health.engine", mock_engine):
        result = await check_postgresql()

    assert result.status == "error"
    assert result.detail is not None
    assert "Unexpected error" in result.detail
    assert result.detail is not None
    assert "ValueError" in result.detail
    # Ensure sensitive info not leaked
    assert result.detail is not None
    assert "postgres://" not in result.detail
    assert result.detail is not None
    assert "password" not in result.detail


@pytest.mark.asyncio
async def test_check_redis_success():
    """Test Redis check returns 'ok' with valid latency on success."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
        result = await check_redis()

    assert isinstance(result, DependencyCheck)
    assert result.name == "redis"
    assert result.status == "ok"
    assert result.latency_ms >= 0
    assert result.detail is not None
    assert result.detail is not None
    assert "PING" in result.detail


@pytest.mark.asyncio
async def test_check_redis_ping_false():
    """Test Redis check returns 'error' when PING returns False."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=False)
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
        result = await check_redis()

    assert result.status == "error"
    assert result.detail is not None
    assert "PING returned False" in result.detail


@pytest.mark.asyncio
async def test_check_redis_connection_error():
    """Test Redis check returns 'error' with safe detail on connection failure."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(
        side_effect=ConnectionError("redis://localhost:6379 password=secret")
    )
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
        result = await check_redis()

    assert result.status == "error"
    assert result.latency_ms >= 0
    assert result.detail is not None
    assert "Redis error" in result.detail
    assert result.detail is not None
    assert "ConnectionError" in result.detail
    # Ensure no connection string or password leaked
    assert result.detail is not None
    assert "redis://" not in result.detail
    assert result.detail is not None
    assert "secret" not in result.detail


@pytest.mark.asyncio
async def test_check_alembic_success():
    """Test Alembic check returns 'ok' with revision when table exists."""
    mock_result = MagicMock()
    mock_result.fetchone = MagicMock(return_value=("abc123def456",))

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=mock_result)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    with patch("app.services.dependency_health.engine", mock_engine):
        result = await check_alembic()

    assert result.name == "alembic"
    assert result.status == "ok"
    assert result.latency_ms >= 0
    assert result.detail is not None
    assert result.detail is not None
    assert "revision" in result.detail
    assert result.detail is not None
    assert "abc123de" in result.detail  # Truncated to 8 chars


@pytest.mark.asyncio
async def test_check_alembic_empty_table():
    """Test Alembic check returns 'unknown' when table is empty."""
    mock_result = MagicMock()
    mock_result.fetchone = MagicMock(return_value=None)

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=mock_result)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    with patch("app.services.dependency_health.engine", mock_engine):
        result = await check_alembic()

    assert result.status == "unknown"
    assert result.detail is not None
    assert "empty" in result.detail


@pytest.mark.asyncio
async def test_check_alembic_table_not_exists():
    """Test Alembic check returns 'unknown' when table doesn't exist."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(
        side_effect=OperationalError("table does not exist", {}, Exception("mock"))
    )
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    with patch("app.services.dependency_health.engine", mock_engine):
        result = await check_alembic()

    assert result.status == "unknown"
    assert result.detail is not None
    assert "does not exist" in result.detail


@pytest.mark.asyncio
async def test_check_alembic_sqlalchemy_error():
    """Test Alembic check returns 'error' for non-table-missing SQLAlchemy errors."""
    mock_conn = AsyncMock()
    error_msg = "connection failed: postgres://user:***@host/db"
    mock_conn.execute = AsyncMock(
        side_effect=OperationalError(error_msg, {}, Exception("mock"))
    )
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    with patch("app.services.dependency_health.engine", mock_engine):
        result = await check_alembic()

    assert result.status == "error"
    assert result.detail is not None
    assert "SQLAlchemy error" in result.detail
    # Ensure no connection string leaked
    assert result.detail is not None
    assert "postgres://" not in result.detail


@pytest.mark.asyncio
async def test_check_arq_worker_key_present():
    """Test ARQ worker check returns 'ok' when health check key exists."""
    mock_redis = AsyncMock()
    health_data = b"2026-07-15 14:30:00 j_complete=5 j_failed=0 j_retried=0"
    mock_redis.get = AsyncMock(return_value=health_data)
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
        result = await check_arq_worker()

    assert result.name == "worker"
    assert result.status == "ok"
    assert result.latency_ms >= 0
    assert result.detail is not None
    # Verify detail contains some info from the key
    assert len(result.detail) <= 50


@pytest.mark.asyncio
async def test_check_arq_worker_key_absent():
    """Test ARQ worker check returns 'unknown' when health check key is missing."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
        result = await check_arq_worker()

    assert result.status == "unknown"
    assert result.detail is not None
    assert "not found" in result.detail


@pytest.mark.asyncio
async def test_check_arq_worker_redis_error():
    """Test ARQ worker check returns 'unknown' on Redis connection error."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=ConnectionError("redis://localhost:6379"))
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
        result = await check_arq_worker()

    assert result.status == "unknown"
    assert result.detail is not None
    assert "Redis error" in result.detail
    # Ensure no connection string leaked
    assert result.detail is not None
    assert "redis://" not in result.detail


@pytest.mark.asyncio
async def test_latency_non_negative_all_checks():
    """Test that all checks return non-negative latency."""
    # Mock all dependencies to fail fast
    with (
        patch("app.services.dependency_health.engine") as mock_engine,
        patch("redis.asyncio.Redis.from_url") as mock_redis_from_url,
    ):
        # PostgreSQL failure
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=Exception("fail"))
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.connect = MagicMock(return_value=mock_conn)

        # Redis failure
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("fail"))
        mock_redis.close = AsyncMock()
        mock_redis_from_url.return_value = mock_redis

        pg_result = await check_postgresql()
        redis_result = await check_redis()
        alembic_result = await check_alembic()
        worker_result = await check_arq_worker()

    assert pg_result.latency_ms >= 0
    assert redis_result.latency_ms >= 0
    assert alembic_result.latency_ms >= 0
    assert worker_result.latency_ms >= 0


@pytest.mark.asyncio
async def test_check_all_dependencies_error_isolation():
    """Test that one failed check does not prevent others from running."""
    # Mock PostgreSQL to fail
    pg_conn = AsyncMock()
    pg_conn.execute = AsyncMock(side_effect=Exception("PG fail"))
    pg_conn.__aenter__ = AsyncMock(return_value=pg_conn)
    pg_conn.__aexit__ = AsyncMock(return_value=None)

    pg_engine = AsyncMock()
    pg_engine.connect = MagicMock(return_value=pg_conn)

    # Mock Redis to succeed
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.close = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    with (
        patch("app.services.dependency_health.engine", pg_engine),
        patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
    ):
        snapshot = await check_all_dependencies()

    assert isinstance(snapshot, DependencyHealthSnapshot)
    assert len(snapshot.checks) == 4

    # All dependencies should be present exactly once
    dependency_names = [c.name for c in snapshot.checks]
    assert dependency_names.count("postgresql") == 1
    assert dependency_names.count("redis") == 1
    assert dependency_names.count("alembic") == 1
    assert dependency_names.count("worker") == 1

    # PostgreSQL should be error, others should have completed
    pg_check = next(c for c in snapshot.checks if c.name == "postgresql")
    assert pg_check.status == "error"

    # All should have non-negative latency
    for check in snapshot.checks:
        assert check.latency_ms >= 0


@pytest.mark.asyncio
async def test_check_all_dependencies_all_success():
    """Test aggregate snapshot with all checks successful."""
    # Mock all dependencies to succeed
    conn = AsyncMock()
    conn.execute = AsyncMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=None)

    eng = AsyncMock()
    eng.connect = MagicMock(return_value=conn)

    mock_result = MagicMock()
    mock_result.fetchone = MagicMock(return_value=("abc123",))

    conn.execute = AsyncMock(return_value=mock_result)

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)
    mock_redis.close = AsyncMock()
    worker_heartbeat = (
        b"Jul-15 12:00:00 j_complete=5 j_failed=0 j_retried=0 j_ongoing=0 queued=0"
    )
    mock_redis.get = AsyncMock(return_value=worker_heartbeat)

    with (
        patch("app.services.dependency_health.engine", eng),
        patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
    ):
        snapshot = await check_all_dependencies()

    assert snapshot.summary == "healthy"
    assert all(c.status == "ok" for c in snapshot.checks)


@pytest.mark.asyncio
async def test_dependency_health_snapshot_summary_healthy():
    """Test snapshot summary is 'healthy' when all checks are ok."""
    checks = [
        DependencyCheck(name="postgresql", status="ok", latency_ms=10, detail="ok"),
        DependencyCheck(name="redis", status="ok", latency_ms=5, detail="ok"),
        DependencyCheck(name="alembic", status="ok", latency_ms=8, detail="ok"),
        DependencyCheck(name="worker", status="ok", latency_ms=12, detail="ok"),
    ]
    snapshot = DependencyHealthSnapshot.from_checks(checks)
    assert snapshot.summary == "healthy"


@pytest.mark.asyncio
async def test_dependency_health_snapshot_summary_degraded():
    """Test snapshot summary is 'degraded' when one non-critical check fails."""
    checks = [
        DependencyCheck(name="postgresql", status="ok", latency_ms=10, detail="ok"),
        DependencyCheck(name="redis", status="ok", latency_ms=5, detail="ok"),
        DependencyCheck(name="alembic", status="error", latency_ms=8, detail="error"),
        DependencyCheck(name="worker", status="unknown", latency_ms=12, detail="unknown"),
    ]
    snapshot = DependencyHealthSnapshot.from_checks(checks)
    assert snapshot.summary == "degraded"


@pytest.mark.asyncio
async def test_dependency_health_snapshot_summary_unhealthy():
    """Test snapshot summary is 'unhealthy' when all critical deps fail."""
    checks = [
        DependencyCheck(name="postgresql", status="error", latency_ms=10, detail="error"),
        DependencyCheck(name="redis", status="error", latency_ms=5, detail="error"),
        DependencyCheck(name="alembic", status="error", latency_ms=8, detail="error"),
        DependencyCheck(name="worker", status="unknown", latency_ms=12, detail="unknown"),
    ]
    snapshot = DependencyHealthSnapshot.from_checks(checks)
    assert snapshot.summary == "unhealthy"


@pytest.mark.asyncio
async def test_dependency_health_snapshot_summary_unknown():
    """Test snapshot summary is 'unknown' when no checks provided."""
    snapshot = DependencyHealthSnapshot.from_checks([])
    assert snapshot.summary == "unknown"


@pytest.mark.asyncio
async def test_check_arq_worker_malformed_heartbeat_value():
    """Test worker check returns 'unknown' when heartbeat value lacks ARQ signature fields."""
    mock_redis = AsyncMock()
    # Valid bytes but not an ARQ heartbeat
    mock_redis.get = AsyncMock(return_value=b"random data without signature")
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
        result = await check_arq_worker()

    assert result.name == "worker"
    assert result.status == "unknown"
    assert result.latency_ms >= 0
    assert result.detail is not None
    assert result.detail is not None
    assert "malformed" in result.detail.lower() or "missing" in result.detail.lower()


@pytest.mark.asyncio
async def test_check_arq_worker_valid_heartbeat_value():
    """Test worker check returns 'ok' when heartbeat contains ARQ signature fields."""
    mock_redis = AsyncMock()
    # Valid ARQ worker heartbeat format
    heartbeat = b"Sep-02 10:15:30 j_complete=42 j_failed=0 j_retried=2 j_ongoing=0 queued=1"
    mock_redis.get = AsyncMock(return_value=heartbeat)
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
        result = await check_arq_worker()

    assert result.name == "worker"
    assert result.status == "ok"
    assert result.latency_ms >= 0
    assert result.detail is not None
    assert "j_complete" in result.detail


@pytest.mark.asyncio
async def test_check_arq_worker_undecodable_bytes():
    """Test worker check returns 'unknown' when heartbeat bytes cannot be decoded."""
    mock_redis = AsyncMock()
    # Invalid UTF-8 bytes
    mock_redis.get = AsyncMock(return_value=b"\xff\xfe\xfd\xfc")
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
        result = await check_arq_worker()

    assert result.name == "worker"
    assert result.status == "unknown"
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_check_postgresql_cancellation_not_swallowed():
    """Test that asyncio.CancelledError propagates from postgresql check."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=asyncio.CancelledError())
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    with patch("app.services.dependency_health.engine", mock_engine), pytest.raises(
        asyncio.CancelledError
    ):
        await check_postgresql()


@pytest.mark.asyncio
async def test_check_redis_cancellation_not_swallowed():
    """Test that asyncio.CancelledError propagates from redis check."""
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=asyncio.CancelledError())
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis), pytest.raises(
        asyncio.CancelledError
    ):
        await check_redis()


@pytest.mark.asyncio
async def test_check_alembic_cancellation_not_swallowed():
    """Test that asyncio.CancelledError propagates from alembic check."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(side_effect=asyncio.CancelledError())
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_engine = AsyncMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    with patch("app.services.dependency_health.engine", mock_engine), pytest.raises(
        asyncio.CancelledError
    ):
        await check_alembic()


@pytest.mark.asyncio
async def test_check_arq_worker_cancellation_not_swallowed():
    """Test that asyncio.CancelledError propagates from worker check."""
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(side_effect=asyncio.CancelledError())
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis), pytest.raises(
        asyncio.CancelledError
    ):
        await check_arq_worker()


@pytest.mark.asyncio
async def test_error_detail_sanitization_no_connection_strings():
    """Test that error details never contain connection strings or credentials."""

    # Database errors (PostgreSQL and Alembic checks)
    db_errors = [
        OperationalError("postgres://user:***@host:5432/db", {}, Exception()),
        RuntimeError("connection failed: mysql://root:***@localhost/test"),
    ]
    for error in db_errors:
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=error)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_engine = AsyncMock()
        mock_engine.connect = MagicMock(return_value=mock_conn)

        with patch("app.services.dependency_health.engine", mock_engine):
            pg_result = await check_postgresql()
            alembic_result = await check_alembic()

            for result in [pg_result, alembic_result]:
                if result.detail:
                    assert result.detail is not None
                    assert "postgres://" not in result.detail
                    assert result.detail is not None
                    assert "mysql://" not in result.detail
                    assert result.detail is not None
                    assert result.detail is not None
                    assert "password" not in result.detail.lower()
                    assert result.detail is not None
                    assert result.detail is not None
                    assert "secret" not in result.detail.lower()

    # Redis errors (Redis and Worker checks)
    redis_error = ConnectionError("redis://localhost:6379/0?password=secret123")
    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(side_effect=redis_error)
    mock_redis.get = AsyncMock(side_effect=redis_error)
    mock_redis.close = AsyncMock()

    with patch("redis.asyncio.Redis.from_url", return_value=mock_redis):
        redis_result = await check_redis()
        worker_result = await check_arq_worker()

        for result in [redis_result, worker_result]:
            if result.detail:
                assert result.detail is not None
                assert "redis://" not in result.detail
                assert result.detail is not None
                assert result.detail is not None
                assert "password" not in result.detail.lower()
                assert result.detail is not None
                assert result.detail is not None
                assert "secret" not in result.detail.lower()


@pytest.mark.asyncio
async def test_all_checks_have_non_negative_latency():
    """Test that latency_ms is always non-negative even under error conditions."""
    with (
        patch("app.services.dependency_health.engine") as mock_engine,
        patch("redis.asyncio.Redis.from_url") as mock_redis_from_url,
    ):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(side_effect=Exception("fail"))
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_engine.connect = MagicMock(return_value=mock_conn)

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=Exception("fail"))
        mock_redis.get = AsyncMock(side_effect=Exception("fail"))
        mock_redis.close = AsyncMock()
        mock_redis_from_url.return_value = mock_redis

        snapshot = await check_all_dependencies()

    for check in snapshot.checks:
        assert check.latency_ms >= 0, f"{check.name} has negative latency: {check.latency_ms}"
