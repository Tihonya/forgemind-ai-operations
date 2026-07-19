"""WP-2.7A integration tests for component APIs against live PostgreSQL.

Required scenarios:
 1. GET /api/v1/components returns seeded components ordered by code
 2. GET /api/v1/components/{code} returns component with alternatives
 3. Unknown natural code returns 404
 4. Alternatives state correctly returned (SENSOR-L9 → VALVE-V3 PROPOSED)
 5. Pagination limit/offset work correctly
 6. Components with no alternatives return empty list
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.config import settings
from app.main import app
from app.seed.generator.loader import (
    _delete_existing_business_data,
    _SessionFactory,
    load_golden_dataset,
)

# ---------------------------------------------------------------------------

_INTEGRATION_DB_URL = settings.database_url


def _can_connect() -> bool:
    try:
        sync_url = _INTEGRATION_DB_URL
        if "+asyncpg" in sync_url:
            sync_url = sync_url.replace("+asyncpg", "+psycopg")
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect(),
    reason="Integration database not available",
)


def _get_sync_engine() -> Engine:
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")
    return create_engine(sync_url, echo=False, pool_pre_ping=True)


@pytest.fixture(scope="module")
def sync_engine() -> Generator[Engine, None, None]:
    eng = _get_sync_engine()
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _ensure_seed(sync_engine: Engine) -> Generator[None, None, None]:
    """Re-seed business data before each test for deterministic state."""
    session = _SessionFactory()
    try:
        _delete_existing_business_data(session)
        session.commit()
    finally:
        session.close()
    load_golden_dataset()
    yield


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Test: List Components
# ---------------------------------------------------------------------------


class TestComponentList:
    """Test GET /api/v1/components."""

    async def test_list_components_returns_seeded_data(self, client: AsyncClient) -> None:
        """Scenario 1: returns 5 components ordered by code."""
        response = await client.get("/api/v1/components")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert data["limit"] == 50
        assert data["offset"] == 0

        # Ordered by code asc: CTRL-X4, MOTOR-M2, PIPE-P1, SENSOR-L9, VALVE-V3
        codes = [item["code"] for item in data["items"]]
        assert codes == ["CTRL-X4", "MOTOR-M2", "PIPE-P1", "SENSOR-L9", "VALVE-V3"]

        # Each item has expected fields
        for item in data["items"]:
            assert "code" in item
            assert "name" in item
            assert "unit" in item
            assert item["unit"] == "PCS"

    async def test_pagination(self, client: AsyncClient) -> None:
        """Scenario 5: limit and offset work correctly."""
        response = await client.get("/api/v1/components?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 0
        assert data["total"] == 5

        response = await client.get("/api/v1/components?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["offset"] == 2


# ---------------------------------------------------------------------------
# Test: Component Detail with Alternatives
# ---------------------------------------------------------------------------


class TestComponentDetail:
    """Test GET /api/v1/components/{code}."""

    async def test_component_with_alternatives(self, client: AsyncClient) -> None:
        """Scenario 2 & 4: SENSOR-L9 returns VALVE-V3 as PROPOSED alternative."""
        response = await client.get("/api/v1/components/SENSOR-L9")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SENSOR-L9"
        assert data["name"] == "Sensor L9"
        assert data["unit"] == "PCS"
        assert len(data["alternatives"]) == 1

        alt = data["alternatives"][0]
        assert alt["alternative_code"] == "VALVE-V3"
        assert alt["status"] == "PROPOSED"
        assert alt["rationale"] is not None
        assert "VALVE-V3" in alt["rationale"]

    async def test_component_without_alternatives(self, client: AsyncClient) -> None:
        """Scenario 6: CTRL-X4 has no alternatives (empty list)."""
        response = await client.get("/api/v1/components/CTRL-X4")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "CTRL-X4"
        assert data["alternatives"] == []

    async def test_component_not_found(self, client: AsyncClient) -> None:
        """Scenario 3: unknown code returns 404."""
        response = await client.get("/api/v1/components/NONEXISTENT-999")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "component_not_found"
