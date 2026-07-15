"""Unit tests for the Phase 1 health endpoint flat-string public contract.

Per docs/planning/phase_1_running_skeleton_plan.md §11.1, GET /health returns:

{
  "status": "healthy" | "degraded" | "unhealthy",
  "timestamp": "<ISO-8601>",
  "correlation_id": "<UUID-v4>",
  "checks": {
    "backend": "ok",
    "postgresql": "ok" | "error: ...",
    "redis": "ok" | "error: ...",
    "worker": "ok" | "unavailable",
    "alembic_revision": "<hash>"
  }
}

No check value is a dict or list. Secrets / exceptions / URLs are never
exposed publicly. Internal DependencyCheck and DependencyHealthSnapshot
remain unchanged; mapping is performed inside the endpoint.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.health import DependencyCheck, DependencyHealthSnapshot

_FIXED_TS = datetime(2026, 7, 15, 10, 30, 45, tzinfo=UTC)

EXPECTED_PUBLIC_KEYS = frozenset(
    {"backend", "postgresql", "redis", "alembic_revision", "worker"}
)
FORBIDDEN_SUBSTRINGS = (
    "postgres://",
    "postgresql://",
    "redis://",
    "password",
    "secret",
    "Traceback",
    "File \"",
)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client bound to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Snapshot factories
# ---------------------------------------------------------------------------


def _check(
    name: str, status: str, detail: str | None = None
) -> DependencyCheck:
    return DependencyCheck(name=name, status=status, latency_ms=1.5, detail=detail)


def healthy_snapshot() -> DependencyHealthSnapshot:
    """All dependencies healthy."""
    return DependencyHealthSnapshot(
        checks=[
            DependencyCheck(
                name="postgresql", status="ok", latency_ms=2.5,
                detail="SELECT 1 succeeded",
            ),
            DependencyCheck(
                name="redis", status="ok", latency_ms=1.2,
                detail="PING succeeded",
            ),
            DependencyCheck(
                name="alembic", status="ok", latency_ms=3.0,
                detail="revision abc12345",
            ),
            DependencyCheck(
                name="worker", status="ok", latency_ms=0.8,
                detail="worker heartbeat ok",
            ),
        ],
        summary="healthy",
        timestamp=_FIXED_TS,
    )


def single_failure_snapshot(
    name: str, status: str, detail: str | None = None
) -> DependencyHealthSnapshot:
    """Single named dependency fails, others ok."""
    checks = [c for c in healthy_snapshot().checks if c.name != name]
    checks.append(_check(name, status=status, detail=detail))
    # Summary recomputed to keep the snapshot valid
    snapshot = DependencyHealthSnapshot.from_checks(checks)
    return DependencyHealthSnapshot(
        checks=snapshot.checks, summary=snapshot.summary, timestamp=_FIXED_TS
    )


def all_deps_unknown_snapshot() -> DependencyHealthSnapshot:
    """Non-critical failure path where every dependency is 'unknown'."""
    return DependencyHealthSnapshot(
        checks=[
            _check("postgresql", status="unknown"),
            _check("redis", status="unknown"),
            _check("alembic", status="unknown"),
            _check("worker", status="unknown"),
        ],
        summary="degraded",
        timestamp=_FIXED_TS,
    )


def alembic_empty_detail_snapshot() -> DependencyHealthSnapshot:
    """Alembic successful but detail is None (safety edge case)."""
    return DependencyHealthSnapshot(
        checks=[
            DependencyCheck(
                name="postgresql", status="ok", latency_ms=2.0,
                detail="SELECT 1 succeeded",
            ),
            DependencyCheck(
                name="redis", status="ok", latency_ms=1.0,
                detail="PING succeeded",
            ),
            DependencyCheck(
                name="alembic", status="ok", latency_ms=3.0, detail=None,
            ),
            DependencyCheck(
                name="worker", status="ok", latency_ms=0.5,
                detail="ok",
            ),
        ],
        summary="degraded",  # worker unknown is ok but None-triggered mapping
        timestamp=_FIXED_TS,
    )


# ---------------------------------------------------------------------------
# Assertions helpers
# ---------------------------------------------------------------------------


def _assert_shape(data: dict) -> None:
    """Top-level shape: exactly the four public keys, correct types."""
    assert {"status", "timestamp", "correlation_id", "checks"} == set(data.keys())
    assert data["status"] in {"healthy", "degraded", "unhealthy"}
    assert isinstance(data["timestamp"], str)
    assert isinstance(data["correlation_id"], str)
    assert isinstance(data["checks"], dict)


def _assert_checks_shape(checks: dict) -> None:
    """All five public keys are present, exactly once, and all flat strings."""
    assert set(checks.keys()) == EXPECTED_PUBLIC_KEYS
    for key, value in checks.items():
        assert isinstance(value, str), f"checks[{key!r}] must be str, got {type(value).__name__}"
        assert not isinstance(value, (dict, list)), f"checks[{key!r}] is a structured object"


def _assert_no_secrets(checks: dict) -> None:
    """No check value contains secret-like substrings."""
    for key, value in checks.items():
        low = value.lower()
        for pattern in FORBIDDEN_SUBSTRINGS:
            assert pattern.lower() not in low, (
                f"checks[{key!r}] contains forbidden pattern {pattern!r}: {value!r}"
            )


# ===========================================================================
# Contract test: all healthy
# ===========================================================================


@pytest.mark.asyncio
async def test_all_healthy_flat_contract(client: AsyncClient) -> None:
    """Healthy snapshot emits the exact flat-string contract."""
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=healthy_snapshot()),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    _assert_shape(data)
    _assert_checks_shape(data["checks"])
    _assert_no_secrets(data["checks"])

    checks = data["checks"]
    assert checks["backend"] == "ok"
    assert checks["postgresql"] == "ok"
    assert checks["redis"] == "ok"
    assert checks["worker"] == "ok"
    # Successful Alembic -> revision hash extracted from "revision abc12345"
    assert checks["alembic_revision"] == "abc12345"
    assert data["status"] == "healthy"
    assert data["timestamp"] == _FIXED_TS.isoformat()


# ===========================================================================
# Contract test: PostgreSQL failure
# ===========================================================================


@pytest.mark.asyncio
async def test_postgresql_failure_is_sanitized_flat_string(
    client: AsyncClient,
) -> None:
    """PostgreSQL error maps to 'error: <sanitized detail>' flat string."""
    snapshot = single_failure_snapshot(
        name="postgresql",
        status="error",
        detail="SQLAlchemy error: OperationalError",
    )
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=snapshot),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    checks = response.json()["checks"]

    # Value is a flat string starting with "error:"
    value = checks["postgresql"]
    assert isinstance(value, str)
    assert value.startswith("error: ")
    # Contains only the sanitized exception class name, not the raw message
    assert "OperationalError" in value
    # Other checks unaffected
    assert checks["backend"] == "ok"
    assert checks["redis"] == "ok"


# ===========================================================================
# Contract test: Redis failure
# ===========================================================================


@pytest.mark.asyncio
async def test_redis_failure_is_sanitized_flat_string(client: AsyncClient) -> None:
    """Redis error maps to 'error: <sanitized detail>' flat string."""
    snapshot = single_failure_snapshot(
        name="redis",
        status="error",
        detail="Redis error: ConnectionError",
    )
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=snapshot),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    checks = response.json()["checks"]

    value = checks["redis"]
    assert isinstance(value, str)
    assert value.startswith("error: ")
    assert "ConnectionError" in value
    assert checks["backend"] == "ok"
    assert checks["postgresql"] == "ok"


# ===========================================================================
# Contract test: worker unknown -> "unavailable"
# ===========================================================================


@pytest.mark.parametrize("status", ["unknown", "error"])
@pytest.mark.asyncio
async def test_worker_non_ok_maps_to_unavailable(
    client: AsyncClient, status: str
) -> None:
    """worker status != 'ok' maps to the literal string 'unavailable'."""
    snapshot = single_failure_snapshot(
        name="worker", status=status, detail="worker heartbeat missing"
    )
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=snapshot),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["checks"]["worker"] == "unavailable"


@pytest.mark.asyncio
async def test_worker_ok_stays_ok(client: AsyncClient) -> None:
    """worker ok stays 'ok' (regression guard)."""
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=healthy_snapshot()),
    ):
        response = await client.get("/health")
    assert response.json()["checks"]["worker"] == "ok"


# ===========================================================================
# Top-level status is restricted to §11.1 approved values
# ===========================================================================


@pytest.mark.asyncio
async def test_unknown_summary_maps_to_degraded(client: AsyncClient) -> None:
    """Internal snapshot.summary='unknown' maps to approved public value 'degraded'.

    The internal DependencyHealthSnapshot.summary Literal also includes
    "unknown" (reachable only when the checks list is empty — which this
    endpoint cannot produce, but may occur in tests or via external mocks).
    The approved public contract §11.1 permits exactly
    ``healthy | degraded | unhealthy``. "unknown" must never leak.
    """
    empty_snapshot = DependencyHealthSnapshot(
        checks=[],
        summary="unknown",
        timestamp=_FIXED_TS,
    )
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=empty_snapshot),
    ):
        response = await client.get("/health")

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "degraded"
    assert body["status"] != "unknown"


# ===========================================================================
# Contract test: Alembic revision extraction
# ===========================================================================


@pytest.mark.asyncio
async def test_alembic_successful_revision_is_hash(client: AsyncClient) -> None:
    """Alembic success returns the revision hash stored in the check detail."""
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=healthy_snapshot()),
    ):
        response = await client.get("/health")

    # healthy_snapshot carries detail="revision abc12345" -> "abc12345"
    assert response.json()["checks"]["alembic_revision"] == "abc12345"


@pytest.mark.asyncio
async def test_alembic_unknown_maps_to_unknown(client: AsyncClient) -> None:
    """Alembic non-ok -> literal 'unknown' (no structure, no secrets)."""
    snapshot = single_failure_snapshot(
        name="alembic", status="unknown",
        detail="alembic_version table does not exist",
    )
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=snapshot),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["checks"]["alembic_revision"] == "unknown"


@pytest.mark.asyncio
async def test_alembic_error_maps_to_unknown(client: AsyncClient) -> None:
    """Alembic 'error' also maps to 'unknown' (no detail hash to expose)."""
    snapshot = single_failure_snapshot(
        name="alembic", status="error",
        detail="SQLAlchemy error: OperationalError",
    )
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=snapshot),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["checks"]["alembic_revision"] == "unknown"


@pytest.mark.asyncio
async def test_postgresql_missing_detail_falls_back_to_unavailable(
    client: AsyncClient,
) -> None:
    """When detail is None, the public error string uses a stable fallback."""
    snapshot = single_failure_snapshot(
        name="postgresql", status="error", detail=None,
    )
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=snapshot),
    ):
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["checks"]["postgresql"] == "error: unavailable"


# ===========================================================================
# Shape invariants
# ===========================================================================


@pytest.mark.asyncio
async def test_no_check_value_is_dict_or_list(client: AsyncClient) -> None:
    """Every value in checks must be a plain string — never dict or list."""
    for snapshot_factory in (
        healthy_snapshot,
        lambda: single_failure_snapshot(
            "postgresql", "error", "SQLAlchemy error: OperationalError"
        ),
        lambda: single_failure_snapshot(
            "redis", "error", "Redis error: ConnectionError"
        ),
        all_deps_unknown_snapshot,
    ):
        with patch(
            "app.main.check_all_dependencies",
            AsyncMock(return_value=snapshot_factory()),
        ):
            response = await client.get("/health")
        assert response.status_code == 200
        checks = response.json()["checks"]
        for key, value in checks.items():
            assert isinstance(value, str), (
                f"{key!r} value is {type(value).__name__}, expected str"
            )
            assert not isinstance(value, (dict, list)), f"{key!r} is a structured object"


@pytest.mark.asyncio
async def test_all_five_public_keys_appear_exactly_once(
    client: AsyncClient,
) -> None:
    """Top-level checks contains exactly the five approved public keys."""
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=healthy_snapshot()),
    ):
        response = await client.get("/health")

    keys = list(response.json()["checks"].keys())
    assert len(keys) == len(set(keys))           # no duplicates
    assert set(keys) == EXPECTED_PUBLIC_KEYS     # exactly the approved set


@pytest.mark.asyncio
async def test_no_secret_like_content_in_checks(client: AsyncClient) -> None:
    """No credential-like content in any check value (regression guard)."""
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=healthy_snapshot()),
    ):
        response = await client.get("/health")
    _assert_no_secrets(response.json()["checks"])


# ===========================================================================
# HTTP 200 invariant + correlation ID
# ===========================================================================


@pytest.mark.asyncio
async def test_http_status_always_200(client: AsyncClient) -> None:
    """HTTP status remains 200 regardless of snapshot summary."""
    for summary, factory in [
        ("healthy", healthy_snapshot),
        ("degraded", lambda: single_failure_snapshot(
            "worker", "unknown", "no heartbeat"
        )),
        ("unhealthy", lambda: DependencyHealthSnapshot(
            checks=[
                DependencyCheck(
                    name="postgresql", status="error", latency_ms=1.0,
                    detail="db error",
                ),
                DependencyCheck(
                    name="redis", status="error", latency_ms=1.0,
                    detail="redis error",
                ),
                DependencyCheck(
                    name="alembic", status="unknown", latency_ms=1.0,
                    detail="no table",
                ),
                DependencyCheck(
                    name="worker", status="unknown", latency_ms=1.0,
                    detail="no worker",
                ),
            ],
            summary="unhealthy",
            timestamp=_FIXED_TS,
        )),
    ]:
        with patch(
            "app.main.check_all_dependencies",
            AsyncMock(return_value=factory()),
        ):
            response = await client.get("/health")
        assert response.status_code == 200, f"expected 200 for summary={summary!r}"


@pytest.mark.asyncio
async def test_correlation_id_body_equals_header(client: AsyncClient) -> None:
    """Body correlation_id equals the X-Correlation-ID response header."""
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=healthy_snapshot()),
    ):
        response = await client.get("/health")

    body_cid = response.json()["correlation_id"]
    header_cid = response.headers["X-Correlation-ID"]
    assert body_cid == header_cid
    # UUID v4 sanity check — middleware enforces it
    assert uuid.UUID(body_cid).version == 4


@pytest.mark.asyncio
async def test_correlation_id_passes_through_when_supplied(
    client: AsyncClient,
) -> None:
    """Client-supplied X-Correlation-ID propagates to the body."""
    supplied = str(uuid.uuid4())
    with patch(
        "app.main.check_all_dependencies",
        AsyncMock(return_value=healthy_snapshot()),
    ):
        response = await client.get(
            "/health", headers={"X-Correlation-ID": supplied}
        )
    assert response.json()["correlation_id"] == supplied
    assert response.headers["X-Correlation-ID"] == supplied


# ===========================================================================
# DependencyCheck / DependencyHealthSnapshot unchanged
# ===========================================================================


def test_internal_dependency_check_schema_is_unchanged() -> None:
    """DependencyCheck still carries status / latency_ms / detail (internal)."""
    c = DependencyCheck(name="pg", status="error", latency_ms=1.5, detail="d")
    assert c.status == "error"
    assert c.latency_ms == 1.5
    assert c.detail == "d"


def test_internal_snapshot_summary_is_unchanged() -> None:
    """DependencyHealthSnapshot.from_checks still computes summary correctly."""
    checks = [
        DependencyCheck(name="postgresql", status="ok", latency_ms=0.0, detail=None),
        DependencyCheck(name="redis", status="error", latency_ms=0.0, detail=None),
    ]
    snap = DependencyHealthSnapshot.from_checks(checks)
    assert snap.summary == "degraded"
