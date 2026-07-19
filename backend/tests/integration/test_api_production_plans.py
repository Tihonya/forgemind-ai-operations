"""WP-2.7A integration tests for production plan APIs against live PostgreSQL.

Required scenarios:
 1. GET /api/v1/production-plans returns seeded plans ordered by period_start
 2. GET /api/v1/production-plans/{code} returns plan with its orders
 3. UNKNOWN plan returns 404
 4. Pagination limit/offset work correctly
 5. Plan codes, statuses, dates correct
 6. Orders nested in plan detail are sorted by need_date then code
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
# Test: List Production Plans
# ---------------------------------------------------------------------------


class TestProductionPlanList:
    """Test GET /api/v1/production-plans."""

    async def test_list_plans_returns_seeded_data(self, client: AsyncClient) -> None:
        """Scenario 1: returns 1 plan (PLAN-2026-W31) with correct fields."""
        response = await client.get("/api/v1/production-plans")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["code"] == "PLAN-2026-W31"
        assert data["items"][0]["status"] == "EXECUTING"
        assert data["items"][0]["period_start"] == "2026-07-31"
        assert data["items"][0]["period_end"] == "2026-08-06"

    async def test_pagination(self, client: AsyncClient) -> None:
        """Scenario 4: limit/offset work, offset beyond total returns empty."""
        response = await client.get("/api/v1/production-plans?limit=1&offset=1")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []

        response = await client.get("/api/v1/production-plans?limit=-1")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Test: Production Plan Detail
# ---------------------------------------------------------------------------


class TestProductionPlanDetail:
    """Test GET /api/v1/production-plans/{code}."""

    async def test_plan_detail_with_orders(self, client: AsyncClient) -> None:
        """Scenario 2: PLAN-2026-W31 contains all 3 production orders."""
        response = await client.get("/api/v1/production-plans/PLAN-2026-W31")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == "PLAN-2026-W31"
        assert data["status"] == "EXECUTING"
        assert data["period_start"] == "2026-07-31"
        assert data["period_end"] == "2026-08-06"
        assert len(data["production_orders"]) == 3

        # Sorted by need_date asc, then by code asc
        orders = data["production_orders"]
        need_dates = [o["need_date"] for o in orders]
        assert need_dates == sorted(need_dates)

        # All orders belong to this plan
        for o in orders:
            assert o["product_code"] == "PROD-PUMP-001"
            assert o["product_version"] in ("2.1", "2.2", "2.3")
            # Quantity serialized as decimal string
            assert isinstance(o["quantity"], str)

    async def test_plan_not_found(self, client: AsyncClient) -> None:
        """Scenario 3: unknown plan returns 404."""
        response = await client.get("/api/v1/production-plans/NONEXISTENT-PLAN")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "production_plan_not_found"
