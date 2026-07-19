"""Integration tests for WP-2.7B inventory API.

Tests cover:
- List inventory with pagination and filters
- Get component inventory detail with balances and reservations
- 404 for unknown component
- Decimal serialization as string
- Deterministic ordering by natural keys
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
# Test: List Inventory
# ---------------------------------------------------------------------------


class TestInventoryList:
    """Test GET /api/v1/inventory."""

    async def test_list_inventory_returns_seeded_data(self, client: AsyncClient) -> None:
        """Returns seeded inventory ordered by component then warehouse code."""
        response = await client.get("/api/v1/inventory")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert data["total"] == 5  # Golden dataset has exactly 5 inventory balances
        assert len(data["items"]) == 5

        # Ordered by component_code asc, then warehouse_code asc
        items = data["items"]
        assert items[0]["component_code"] == "CTRL-X4"
        assert items[0]["warehouse_code"] == "WH-MAIN"
        assert items[1]["component_code"] == "MOTOR-M2"
        assert items[1]["warehouse_code"] == "WH-MAIN"

    async def test_list_inventory_filter_by_component(self, client: AsyncClient) -> None:
        """Filter by component_code returns matching inventory."""
        response = await client.get("/api/v1/inventory?component_code=CTRL-X4")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["component_code"] == "CTRL-X4"

    async def test_list_inventory_filter_by_warehouse(self, client: AsyncClient) -> None:
        """Filter by warehouse_code returns matching inventory."""
        response = await client.get("/api/v1/inventory?warehouse_code=WH-MAIN")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5  # All 5 balances are in WH-MAIN

    async def test_list_inventory_combined_filters(self, client: AsyncClient) -> None:
        """Combined filters work correctly."""
        response = await client.get(
            "/api/v1/inventory?component_code=CTRL-X4&warehouse_code=WH-MAIN"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["component_code"] == "CTRL-X4"
        assert data["items"][0]["warehouse_code"] == "WH-MAIN"

    async def test_list_inventory_empty_filter_result(self, client: AsyncClient) -> None:
        """Filter with no matches returns empty list."""
        response = await client.get("/api/v1/inventory?warehouse_code=WH-NONEXISTENT")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0

    async def test_list_inventory_pagination(self, client: AsyncClient) -> None:
        """Pagination works correctly."""
        response = await client.get("/api/v1/inventory?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

        response = await client.get("/api/v1/inventory?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

    async def test_invalid_pagination_params(self, client: AsyncClient) -> None:
        """Negative limit or offset returns 422."""
        response = await client.get("/api/v1/inventory?limit=-1")
        assert response.status_code == 422

        response = await client.get("/api/v1/inventory?offset=-1")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: Get Inventory Detail
# ---------------------------------------------------------------------------


class TestInventoryDetail:
    """Test GET /api/v1/inventory/{component_code}."""

    async def test_get_inventory_detail_ctrl_x4(self, client: AsyncClient) -> None:
        """Returns component inventory detail for CTRL-X4."""
        response = await client.get("/api/v1/inventory/CTRL-X4")
        assert response.status_code == 200
        data = response.json()
        assert data["component_code"] == "CTRL-X4"
        assert data["component_name"] == "Control Unit X4"
        assert data["unit"] == "PCS"

        # Balances ordered by warehouse_code asc
        assert len(data["balances"]) == 1
        assert data["balances"][0]["warehouse_code"] == "WH-MAIN"
        assert data["balances"][0]["quantity_on_hand"] == "12.0000"

        # Reservations (Golden Dataset has none for CTRL-X4)
        assert len(data["reservations"]) == 0

    async def test_get_inventory_detail_motor_m2(self, client: AsyncClient) -> None:
        """Returns component inventory detail for MOTOR-M2."""
        response = await client.get("/api/v1/inventory/MOTOR-M2")
        assert response.status_code == 200
        data = response.json()
        assert data["component_code"] == "MOTOR-M2"
        assert data["balances"][0]["warehouse_code"] == "WH-MAIN"
        assert data["balances"][0]["quantity_on_hand"] == "10.0000"

    async def test_get_inventory_detail_valve_v3(self, client: AsyncClient) -> None:
        """Returns component inventory detail for VALVE-V3."""
        response = await client.get("/api/v1/inventory/VALVE-V3")
        assert response.status_code == 200
        data = response.json()
        assert data["component_code"] == "VALVE-V3"
        assert data["balances"][0]["warehouse_code"] == "WH-MAIN"
        assert data["balances"][0]["quantity_on_hand"] == "50.0000"

    async def test_inventory_detail_decimal_serialization(self, client: AsyncClient) -> None:
        """Decimal quantities serialized as strings."""
        response = await client.get("/api/v1/inventory/CTRL-X4")
        assert response.status_code == 200
        data = response.json()

        for balance in data["balances"]:
            assert isinstance(balance["quantity_on_hand"], str)

    async def test_inventory_component_not_found(self, client: AsyncClient) -> None:
        """Unknown component returns 404."""
        response = await client.get("/api/v1/inventory/NONEXISTENT-999")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "component_inventory_not_found"
