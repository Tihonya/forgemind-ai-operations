"""Integration tests for WP-2.7B warehouses API.

Tests cover:
- List warehouses with pagination
- Get warehouse detail with inventory balances
- 404 for unknown warehouse
- Decimal serialization as string
- Deterministic ordering by natural key
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
    """Async httpx client wired to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Test: List Warehouses
# ---------------------------------------------------------------------------


class TestWarehouseList:
    """Test GET /api/v1/warehouses."""

    async def test_list_warehouses_returns_seeded_data(self, client: AsyncClient) -> None:
        """Returns seeded warehouses ordered by code."""
        response = await client.get("/api/v1/warehouses")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert data["total"] == 1  # Golden dataset has exactly 1 warehouse
        assert data["items"][0]["code"] == "WH-MAIN"
        assert data["items"][0]["name"] == "Main Warehouse"

    async def test_list_warehouses_pagination(self, client: AsyncClient) -> None:
        """Pagination works correctly."""
        response = await client.get("/api/v1/warehouses?limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # Offset beyond total
        response = await client.get("/api/v1/warehouses?limit=1&offset=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    async def test_invalid_pagination_params(self, client: AsyncClient) -> None:
        """Negative limit or offset returns 422."""
        response = await client.get("/api/v1/warehouses?limit=-1")
        assert response.status_code == 422

        response = await client.get("/api/v1/warehouses?offset=-1")
        assert response.status_code == 422

        response = await client.get("/api/v1/warehouses?limit=0")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: Get Warehouse Detail
# ---------------------------------------------------------------------------


class TestWarehouseDetail:
    """Test GET /api/v1/warehouses/{code}."""

    async def test_get_warehouse_with_inventory_balances(self, client: AsyncClient) -> None:
        """Returns warehouse with inventory balances ordered by component code."""
        response = await client.get("/api/v1/warehouses/WH-MAIN")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "WH-MAIN"
        assert data["name"] == "Main Warehouse"
        assert len(data["inventory_balances"]) == 5

        # Ordered by component_code asc
        codes = [b["component_code"] for b in data["inventory_balances"]]
        assert codes == ["CTRL-X4", "MOTOR-M2", "PIPE-P1", "SENSOR-L9", "VALVE-V3"]

        # Decimal as string
        for balance in data["inventory_balances"]:
            assert isinstance(balance["quantity_on_hand"], str)

        # Exact quantities from Golden Dataset
        qty_map = {b["component_code"]: b["quantity_on_hand"] for b in data["inventory_balances"]}
        assert qty_map["CTRL-X4"] == "12.0000"
        assert qty_map["MOTOR-M2"] == "10.0000"
        assert qty_map["SENSOR-L9"] == "7.0000"
        assert qty_map["VALVE-V3"] == "50.0000"
        assert qty_map["PIPE-P1"] == "70.0000"

    async def test_warehouse_not_found(self, client: AsyncClient) -> None:
        """Unknown warehouse returns 404."""
        response = await client.get("/api/v1/warehouses/WH-NONEXISTENT")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "warehouse_not_found"
