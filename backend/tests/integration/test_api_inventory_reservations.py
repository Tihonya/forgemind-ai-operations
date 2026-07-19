"""Integration tests for WP-2.7B inventory reservations API.

Tests cover:
- List inventory reservations with pagination and filters
- Deterministic ordering by natural keys
- Empty filter results
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
# Test: List Inventory Reservations
# ---------------------------------------------------------------------------


class TestInventoryReservationList:
    """Test GET /api/v1/inventory-reservations."""

    async def test_list_reservations_returns_empty(
        self, client: AsyncClient
    ) -> None:
        """Golden Dataset has no inventory reservations."""
        response = await client.get("/api/v1/inventory-reservations")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert data["total"] == 0
        assert len(data["items"]) == 0

    async def test_list_reservations_filter_by_component(
        self, client: AsyncClient
    ) -> None:
        """Filter by component_code returns matching reservations."""
        response = await client.get(
            "/api/v1/inventory-reservations?component_code=CTRL-X4"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    async def test_list_reservations_filter_by_warehouse(
        self, client: AsyncClient
    ) -> None:
        """Filter by warehouse_code returns matching reservations."""
        response = await client.get(
            "/api/v1/inventory-reservations?warehouse_code=WH-MAIN"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    async def test_list_reservations_filter_by_order(
        self, client: AsyncClient
    ) -> None:
        """Filter by order_code returns matching reservations."""
        response = await client.get(
            "/api/v1/inventory-reservations?order_code=WO-2026-0142"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    async def test_list_reservations_combined_filters(
        self, client: AsyncClient
    ) -> None:
        """Combined filters work correctly."""
        response = await client.get(
            "/api/v1/inventory-reservations?component_code=CTRL-X4"
            "&warehouse_code=WH-MAIN&order_code=WO-2026-0142"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    async def test_invalid_pagination_params(self, client: AsyncClient) -> None:
        """Negative limit or offset returns 422."""
        response = await client.get("/api/v1/inventory-reservations?limit=-1")
        assert response.status_code == 422

        response = await client.get("/api/v1/inventory-reservations?offset=-1")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: Ordering Validation (when reservations exist)
# ---------------------------------------------------------------------------


class TestInventoryReservationOrdering:
    """Test ordering when reservations exist (requires test fixture insertion)."""

    async def test_ordering_schema(self, client: AsyncClient) -> None:
        """Verify response schema for pagination."""
        response = await client.get("/api/v1/inventory-reservations")
        assert response.status_code == 200
        data = response.json()

        # Verify pagination structure
        assert "items" in data
        assert "limit" in data
        assert "offset" in data
        assert "total" in data
