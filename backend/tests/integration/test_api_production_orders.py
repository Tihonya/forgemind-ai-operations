"""WP-2.7A integration tests for production order APIs against live PostgreSQL.

Required scenarios:
 1. GET /api/v1/production-orders returns seeded orders ordered by need_date
 2. GET /api/v1/production-orders/{code} returns order with requirements
 3. GET /api/v1/production-orders?plan_code=X filters by plan
 4. GET /api/v1/production-order-requirements?order_code=X returns requirements
 5. Unknown natural code returns 404
 6. Decimal quantities serialized as strings
 7. Requirements ordered by component code asc
 8. Requirements filter by order_code required (422 if missing)
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
# Test: List Production Orders
# ---------------------------------------------------------------------------


class TestProductionOrderList:
    """Test GET /api/v1/production-orders."""

    async def test_list_orders_returns_all_seeded(self, client: AsyncClient) -> None:
        """Scenario 1: returns all 3 work orders for the seeded plan."""
        response = await client.get("/api/v1/production-orders")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

        # Ordered by need_date asc then code asc
        # WO-2026-0142 need_date=2026-08-03
        # WO-2026-0150 need_date=2026-08-03
        # WO-2026-0156 need_date=2026-08-05
        assert data["items"][0]["code"] == "WO-2026-0142"
        assert data["items"][1]["code"] == "WO-2026-0150"
        assert data["items"][2]["code"] == "WO-2026-0156"
        # Decimal serialized as string
        for item in data["items"]:
            assert isinstance(item["quantity"], str)

    async def test_filter_by_plan_code(self, client: AsyncClient) -> None:
        """Scenario 3: filter by plan_code returns matching orders."""
        response = await client.get("/api/v1/production-orders?plan_code=PLAN-2026-W31")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

        # Non-matching filter returns empty
        response = await client.get("/api/v1/production-orders?plan_code=NONEXISTENT-PLAN")
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []


# ---------------------------------------------------------------------------
# Test: Production Order Detail
# ---------------------------------------------------------------------------


class TestProductionOrderDetail:
    """Test GET /api/v1/production-orders/{code}."""

    async def test_order_detail_with_requirements(self, client: AsyncClient) -> None:
        """Scenario 2: WO-2026-0142 has correct references and requirements.

        WO-2026-0142 uses product PROD-PUMP-001 version 2.1.
        BOM for 2.1: CTRL-X4 (1.0), VALVE-V3 (2.0), PIPE-P1 (3.0).
        Required for qty=20: CTRL-X4=20, VALVE-V3=40, PIPE-P1=60.
        """
        response = await client.get("/api/v1/production-orders/WO-2026-0142")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "WO-2026-0142"
        assert data["plan_code"] == "PLAN-2026-W31"
        assert data["product_code"] == "PROD-PUMP-001"
        assert data["product_version"] == "2.1"
        assert data["quantity"] == "20.0000"
        assert data["need_date"] == "2026-08-03"
        assert data["status"] == "RELEASED"
        assert len(data["requirements"]) == 3

        # Scenario 7: requirements sorted by component code asc
        codes = [r["component_code"] for r in data["requirements"]]
        assert codes == ["CTRL-X4", "PIPE-P1", "VALVE-V3"]

        # Scenario 6: Decimal as string
        for r in data["requirements"]:
            assert isinstance(r["required_quantity"], str)
            assert isinstance(r["reserved_quantity"], str)

    async def test_order_detail_requirements_quantities(self, client: AsyncClient) -> None:
        """Scenario 6: BOM explosion produces correct required quantities.

        WO-2026-0142 qty=20, BOM 2.1:
        - CTRL-X4: 1*20 = 20.0000
        - VALVE-V3: 2*20 = 40.0000
        - PIPE-P1: 3*20 = 60.0000
        """
        response = await client.get("/api/v1/production-orders/WO-2026-0142")
        data = response.json()
        qty_map = {r["component_code"]: r["required_quantity"] for r in data["requirements"]}
        assert qty_map["CTRL-X4"] == "20.0000"
        assert qty_map["VALVE-V3"] == "40.0000"
        assert qty_map["PIPE-P1"] == "60.0000"

    async def test_order_not_found(self, client: AsyncClient) -> None:
        """Scenario 5: unknown code returns 404."""
        response = await client.get("/api/v1/production-orders/NONEXISTENT-WO")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "production_order_not_found"


# ---------------------------------------------------------------------------
# Test: Production Order Requirements List
# ---------------------------------------------------------------------------


class TestProductionOrderRequirements:
    """Test GET /api/v1/production-order-requirements."""

    async def test_requirements_list_for_order(self, client: AsyncClient) -> None:
        """Scenario 4: returns requirements for given order_code.

        WO-2026-0142 has 3 requirements (from BOM 2.1 * qty=20).
        """
        response = await client.get("/api/v1/production-order-requirements?order_code=WO-2026-0142")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3

        # Requirements ordered by component code asc (natural business key,
        # independent of UUID ordering in the database)
        codes = [item["component_code"] for item in data["items"]]
        assert codes == sorted(codes), f"requirements must be ordered by component code: {codes}"
        assert codes == ["CTRL-X4", "PIPE-P1", "VALVE-V3"]

        for item in data["items"]:
            assert item["order_code"] == "WO-2026-0142"
            assert "component_code" in item
            assert isinstance(item["required_quantity"], str)
            assert isinstance(item["reserved_quantity"], str)

    async def test_requirements_for_nonexistent_order(self, client: AsyncClient) -> None:
        """Return empty list for unknown order_code (not 404)."""
        response = await client.get(
            "/api/v1/production-order-requirements?order_code=NONEXISTENT-WO"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_missing_order_code_returns_422(self, client: AsyncClient) -> None:
        """Scenario 8: order_code query param is required."""
        response = await client.get("/api/v1/production-order-requirements")
        assert response.status_code == 422
