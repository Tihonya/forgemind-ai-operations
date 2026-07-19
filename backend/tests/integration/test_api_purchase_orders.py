"""Integration tests for WP-2.7B purchase orders API.

Tests cover:
- List purchase orders with pagination and filters
- Get purchase order detail with lines
- 404 for unknown purchase order
- Deterministic ordering by natural keys
- Decimal serialization as string
- ISO date serialization
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
# Test: List Purchase Orders
# ---------------------------------------------------------------------------


class TestPurchaseOrderList:
    """Test GET /api/v1/purchase-orders."""

    async def test_list_purchase_orders_returns_seeded_data(
        self, client: AsyncClient
    ) -> None:
        """Returns seeded purchase orders ordered by placed_at desc."""
        response = await client.get("/api/v1/purchase-orders")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert data["total"] == 3  # Golden dataset has exactly 3 POs
        assert len(data["items"]) == 3

        # Ordered by placed_at DESC (most recent first)
        # PO-2026-0422 (2026-07-26) -> PO-2026-0421 (2026-07-25) -> PO-2026-0423 (2026-07-20)
        po_numbers = [item["po_number"] for item in data["items"]]
        assert po_numbers[0] == "PO-2026-0422"
        assert po_numbers[1] == "PO-2026-0421"
        assert po_numbers[2] == "PO-2026-0423"

    async def test_list_purchase_orders_filter_by_supplier(
        self, client: AsyncClient
    ) -> None:
        """Filter by supplier_code returns matching purchase orders."""
        response = await client.get("/api/v1/purchase-orders?supplier_code=SUP-ACME")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["supplier_code"] == "SUP-ACME"
        assert data["items"][0]["po_number"] == "PO-2026-0421"

    async def test_list_purchase_orders_filter_by_status(
        self, client: AsyncClient
    ) -> None:
        """Filter by status returns matching purchase orders."""
        response = await client.get("/api/v1/purchase-orders?status=CONFIRMED")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2  # PO-2026-0421 and PO-2026-0422
        assert len(data["items"]) == 2

        for item in data["items"]:
            assert item["status"] == "CONFIRMED"

    async def test_list_purchase_orders_filter_by_status_cancelled(
        self, client: AsyncClient
    ) -> None:
        """Filter by CANCELLED status returns matching purchase orders."""
        response = await client.get("/api/v1/purchase-orders?status=CANCELLED")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["po_number"] == "PO-2026-0423"
        assert data["items"][0]["status"] == "CANCELLED"

    async def test_list_purchase_orders_combined_filters(
        self, client: AsyncClient
    ) -> None:
        """Combined filters work correctly."""
        response = await client.get(
            "/api/v1/purchase-orders?supplier_code=SUP-ACME&status=CONFIRMED"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["po_number"] == "PO-2026-0421"

    async def test_list_purchase_orders_empty_filter_result(
        self, client: AsyncClient
    ) -> None:
        """Filter with no matches returns empty list."""
        response = await client.get(
            "/api/v1/purchase-orders?supplier_code=SUP-NONEXISTENT"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0

    async def test_list_purchase_orders_pagination(
        self, client: AsyncClient
    ) -> None:
        """Pagination works correctly."""
        response = await client.get("/api/v1/purchase-orders?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

        response = await client.get("/api/v1/purchase-orders?limit=1&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # Offset beyond total
        response = await client.get("/api/v1/purchase-orders?limit=1&offset=100")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    async def test_invalid_pagination_params(self, client: AsyncClient) -> None:
        """Negative limit or offset returns 422."""
        response = await client.get("/api/v1/purchase-orders?limit=-1")
        assert response.status_code == 422

        response = await client.get("/api/v1/purchase-orders?offset=-1")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: Get Purchase Order Detail
# ---------------------------------------------------------------------------


class TestPurchaseOrderDetail:
    """Test GET /api/v1/purchase-orders/{po_number}."""

    async def test_get_purchase_order_0421(self, client: AsyncClient) -> None:
        """Returns purchase order PO-2026-0421 with lines."""
        response = await client.get("/api/v1/purchase-orders/PO-2026-0421")
        assert response.status_code == 200
        data = response.json()
        assert data["po_number"] == "PO-2026-0421"
        assert data["supplier_code"] == "SUP-ACME"
        assert data["status"] == "CONFIRMED"
        assert len(data["lines"]) == 1

        line = data["lines"][0]
        assert line["component_code"] == "MOTOR-M2"
        assert line["component_name"] == "Motor M2"
        assert line["ordered_quantity"] == "10.0000"
        assert line["received_quantity"] == "0.0000"
        assert line["expected_delivery_date"] == "2026-08-09"
        assert line["status"] == "IN_TRANSIT"

    async def test_get_purchase_order_0422(self, client: AsyncClient) -> None:
        """Returns purchase order PO-2026-0422 with lines."""
        response = await client.get("/api/v1/purchase-orders/PO-2026-0422")
        assert response.status_code == 200
        data = response.json()
        assert data["po_number"] == "PO-2026-0422"
        assert data["supplier_code"] == "SUP-GLOBAL"
        assert data["status"] == "CONFIRMED"
        assert len(data["lines"]) == 1

        line = data["lines"][0]
        assert line["component_code"] == "PIPE-P1"
        assert line["component_name"] == "Pipe P1"
        assert line["ordered_quantity"] == "20.0000"
        assert line["received_quantity"] == "0.0000"
        assert line["expected_delivery_date"] == "2026-08-01"
        assert line["status"] == "CONFIRMED"

    async def test_get_purchase_order_0423_cancelled(
        self, client: AsyncClient
    ) -> None:
        """Returns CANCELLED purchase order PO-2026-0423 with lines."""
        response = await client.get("/api/v1/purchase-orders/PO-2026-0423")
        assert response.status_code == 200
        data = response.json()
        assert data["po_number"] == "PO-2026-0423"
        assert data["status"] == "CANCELLED"
        assert len(data["lines"]) == 1

        line = data["lines"][0]
        assert line["component_code"] == "CTRL-X4"
        assert line["status"] == "CANCELLED"

    async def test_purchase_order_lines_ordering(
        self, client: AsyncClient
    ) -> None:
        """Lines ordered by component code ascending."""
        response = await client.get("/api/v1/purchase-orders/PO-2026-0421")
        assert response.status_code == 200
        data = response.json()

        component_codes = [line["component_code"] for line in data["lines"]]
        assert component_codes == sorted(component_codes)

    async def test_purchase_order_decimal_serialization(
        self, client: AsyncClient
    ) -> None:
        """Decimal quantities serialized as strings."""
        response = await client.get("/api/v1/purchase-orders/PO-2026-0421")
        assert response.status_code == 200
        data = response.json()

        for line in data["lines"]:
            assert isinstance(line["ordered_quantity"], str)
            assert isinstance(line["received_quantity"], str)

    async def test_purchase_order_date_serialization(
        self, client: AsyncClient
    ) -> None:
        """Dates serialized as ISO 8601 strings."""
        response = await client.get("/api/v1/purchase-orders/PO-2026-0421")
        assert response.status_code == 200
        data = response.json()

        for line in data["lines"]:
            # expected_delivery_date must be ISO 8601 date string
            assert isinstance(line["expected_delivery_date"], str)
            assert "T" not in line["expected_delivery_date"]  # Date, not datetime
            # Format: YYYY-MM-DD
            assert len(line["expected_delivery_date"]) == 10

    async def test_purchase_order_placed_at_serialization(
        self, client: AsyncClient
    ) -> None:
        """placed_at datetime serialized as ISO 8601 string."""
        response = await client.get("/api/v1/purchase-orders/PO-2026-0421")
        assert response.status_code == 200
        data = response.json()

        # placed_at must be ISO 8601 datetime string
        assert isinstance(data["placed_at"], str)
        assert "T" in data["placed_at"]

    async def test_purchase_order_not_found(self, client: AsyncClient) -> None:
        """Unknown purchase order returns 404."""
        response = await client.get("/api/v1/purchase-orders/PO-NONEXISTENT")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "purchase_order_not_found"
