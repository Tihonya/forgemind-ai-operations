"""Integration tests for WP-2.7B suppliers API.

Tests cover:
- List suppliers with pagination
- Get supplier detail with purchase orders
- 404 for unknown supplier
- Deterministic ordering by natural key
- Decimal serialization as string
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
# Test: List Suppliers
# ---------------------------------------------------------------------------


class TestSupplierList:
    """Test GET /api/v1/suppliers."""

    async def test_list_suppliers_returns_seeded_data(
        self, client: AsyncClient
    ) -> None:
        """Returns seeded suppliers ordered by code."""
        response = await client.get("/api/v1/suppliers")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert data["total"] == 3  # Golden dataset has exactly 3 suppliers
        assert len(data["items"]) == 3

        # Ordered by code ASC
        codes = [item["code"] for item in data["items"]]
        assert codes == ["SUP-ACME", "SUP-GLOBAL", "SUP-TECH"]

    async def test_list_suppliers_pagination(self, client: AsyncClient) -> None:
        """Pagination works correctly."""
        response = await client.get("/api/v1/suppliers?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

        response = await client.get("/api/v1/suppliers?limit=1&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        # Offset beyond total
        response = await client.get("/api/v1/suppliers?limit=1&offset=100")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    async def test_invalid_pagination_params(self, client: AsyncClient) -> None:
        """Negative limit or offset returns 422."""
        response = await client.get("/api/v1/suppliers?limit=-1")
        assert response.status_code == 422

        response = await client.get("/api/v1/suppliers?offset=-1")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: Get Supplier Detail
# ---------------------------------------------------------------------------


class TestSupplierDetail:
    """Test GET /api/v1/suppliers/{code}."""

    async def test_get_supplier_with_purchase_orders(
        self, client: AsyncClient
    ) -> None:
        """Returns supplier with purchase orders ordered by placed_at desc."""
        response = await client.get("/api/v1/suppliers/SUP-ACME")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUP-ACME"
        assert data["name"] == "Acme Industrial Supply"
        assert "purchase_orders" in data
        assert len(data["purchase_orders"]) == 1

        # Purchase order PO-2026-0421
        po = data["purchase_orders"][0]
        assert po["po_number"] == "PO-2026-0421"
        assert po["status"] == "CONFIRMED"
        assert po["total_lines"] == 1
        assert po["total_ordered_quantity"] == "10.0000"

    async def test_get_supplier_global(self, client: AsyncClient) -> None:
        """Returns supplier SUP-GLOBAL with its purchase orders."""
        response = await client.get("/api/v1/suppliers/SUP-GLOBAL")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUP-GLOBAL"
        assert data["name"] == "Global Components Ltd"
        assert len(data["purchase_orders"]) == 1

        po = data["purchase_orders"][0]
        assert po["po_number"] == "PO-2026-0422"
        assert po["status"] == "CONFIRMED"
        assert po["total_lines"] == 1
        assert po["total_ordered_quantity"] == "20.0000"

    async def test_get_supplier_tech(self, client: AsyncClient) -> None:
        """Returns supplier SUP-TECH with CANCELLED purchase order."""
        response = await client.get("/api/v1/suppliers/SUP-TECH")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "SUP-TECH"
        assert data["name"] == "TechParts International"
        assert len(data["purchase_orders"]) == 1

        po = data["purchase_orders"][0]
        assert po["po_number"] == "PO-2026-0423"
        assert po["status"] == "CANCELLED"

    async def test_supplier_purchase_order_date_serialization(
        self, client: AsyncClient
    ) -> None:
        """Purchase order dates serialized as ISO 8601 strings."""
        response = await client.get("/api/v1/suppliers/SUP-ACME")
        assert response.status_code == 200
        data = response.json()

        for po in data["purchase_orders"]:
            # placed_at must be ISO 8601 datetime string
            assert isinstance(po["placed_at"], str)
            assert "T" in po["placed_at"]
            assert "+" in po["placed_at"] or "Z" in po["placed_at"]

    async def test_supplier_detail_decimal_serialization(
        self, client: AsyncClient
    ) -> None:
        """Decimal quantities serialized as strings."""
        response = await client.get("/api/v1/suppliers/SUP-ACME")
        assert response.status_code == 200
        data = response.json()

        for po in data["purchase_orders"]:
            assert isinstance(po["total_ordered_quantity"], str)

    async def test_supplier_not_found(self, client: AsyncClient) -> None:
        """Unknown supplier returns 404."""
        response = await client.get("/api/v1/suppliers/SUP-NONEXISTENT")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "supplier_not_found"
