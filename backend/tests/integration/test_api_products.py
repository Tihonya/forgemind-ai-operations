"""WP-2.7A integration tests for product APIs against live PostgreSQL.

Required scenarios:
 1. GET /api/v1/products returns seeded products with correct schema
 2. GET /api/v1/products/{code} returns product with versions ordered desc
 3. GET /api/v1/product-versions/{code} returns latest version with BOM items
 4. Unknown natural code returns 404
 5. Pagination limit/offset work correctly
 6. Decimal quantities serialized as strings (not floats)
 7. Invalid pagination params return 422
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
# Test: List Products
# ---------------------------------------------------------------------------


class TestProductList:
    """Test GET /api/v1/products."""

    async def test_list_products_returns_seeded_data(self, client: AsyncClient) -> None:
        """Scenario 1: returns seeded products ordered by code."""
        response = await client.get("/api/v1/products")
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert data["total"] == 1  # Golden dataset has exactly 1 product
        assert data["items"][0]["code"] == "PROD-PUMP-001"
        assert data["items"][0]["name"] == "Industrial Pump MK-III"

    async def test_list_products_pagination(
        self, client: AsyncClient
    ) -> None:
        """Scenario 5: limit=0 returns empty items, offset=1 for 1 item returns empty."""
        response = await client.get("/api/v1/products?limit=1&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1

        response = await client.get("/api/v1/products?limit=1&offset=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 0

    async def test_invalid_pagination_params(self, client: AsyncClient) -> None:
        """Scenario 7: negative limit or offset returns 422."""
        response = await client.get("/api/v1/products?limit=-1")
        assert response.status_code == 422

        response = await client.get("/api/v1/products?offset=-1")
        assert response.status_code == 422

        response = await client.get("/api/v1/products?limit=0")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: Get Product Detail
# ---------------------------------------------------------------------------


class TestProductDetail:
    """Test GET /api/v1/products/{code}."""

    async def test_get_product_with_versions(self, client: AsyncClient) -> None:
        """Scenario 2: returns product with versions ordered by version desc."""
        response = await client.get("/api/v1/products/PROD-PUMP-001")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "PROD-PUMP-001"
        assert data["name"] == "Industrial Pump MK-III"
        assert len(data["versions"]) == 3
        # Latest first (desc): "2.3", "2.2", "2.1"
        assert data["versions"][0]["version"] == "2.3"
        assert data["versions"][1]["version"] == "2.2"
        assert data["versions"][2]["version"] == "2.1"
        # All statuses are RELEASED
        for v in data["versions"]:
            assert v["status"] == "RELEASED"

    async def test_product_not_found(self, client: AsyncClient) -> None:
        """Scenario 4: unknown product returns 404."""
        response = await client.get("/api/v1/products/NONEXISTENT-999")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "product_not_found"


# ---------------------------------------------------------------------------
# Test: Get Product Version
# ---------------------------------------------------------------------------


class TestProductVersion:
    """Test GET /api/v1/product-versions/{code}."""

    async def test_get_latest_version_with_bom(self, client: AsyncClient) -> None:
        """Scenario 3: returns latest version (2.3) with BOM items.

        Version 2.3 BOM: SENSOR-L9 (1.0), VALVE-V3 (2.0), PIPE-P1 (3.0).
        Ordered by component code asc: PIPE-P1, SENSOR-L9, VALVE-V3.
        """
        response = await client.get("/api/v1/product-versions/PROD-PUMP-001")
        assert response.status_code == 200
        data = response.json()
        assert data["product_code"] == "PROD-PUMP-001"
        assert data["version"] == "2.3"  # Latest (highest version desc)
        assert data["status"] == "RELEASED"
        assert len(data["bom_items"]) == 3

        # Ordered by component_code asc
        codes = [b["component_code"] for b in data["bom_items"]]
        assert codes == ["PIPE-P1", "SENSOR-L9", "VALVE-V3"]

        # Scenario 6: Decimal as string
        for bom in data["bom_items"]:
            assert isinstance(bom["quantity_per_unit"], str)

        # Quantities for v2.3: SENSOR-L9=1, VALVE-V3=2, PIPE-P1=3
        qty_map = {b["component_code"]: b["quantity_per_unit"] for b in data["bom_items"]}
        assert qty_map["SENSOR-L9"] == "1.0000"
        assert qty_map["VALVE-V3"] == "2.0000"
        assert qty_map["PIPE-P1"] == "3.0000"

    async def test_version_for_unknown_product(self, client: AsyncClient) -> None:
        """Scenario 4: unknown product code returns 404."""
        response = await client.get("/api/v1/product-versions/NONEXISTENT-999")
        assert response.status_code == 404
