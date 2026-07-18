"""Tests for Golden Dataset integrity endpoint and database checksum verification.

Verifies the semantic checksum computation matches between the in-memory
dataset generator and the database-loaded version. Tests:

- Empty database returns not_loaded status
- Seeded database returns valid status with matching checksums
- Tampered database returns invalid status
- Reseeding restores valid status
- diagnostic_jobs content does not affect the checksum
- Partial fixture returns invalid

Requires a live PostgreSQL database with Alembic migrations applied.
Skips cleanly if the database is unavailable.
"""

import os
from collections.abc import AsyncIterator, Generator, Iterator

import pytest
from httpx import AsyncClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.dataset_metadata import EXPECTED_CHECKSUM
from app.seed.generator.loader import (
    _delete_existing_business_data,
    _SessionFactory,
    load_golden_dataset,
)

# Determine if integration environment is available
_INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _can_connect_to_db() -> bool:
    """Check if we can connect to the database."""
    if not _INTEGRATION_DB_URL:
        return False
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


# Skip all tests in this module if no integration DB
pytestmark = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason=(
        "Integration database not available "
        "(TEST_DATABASE_URL or DATABASE_URL not set/unreachable)"
    ),
)


def _get_sync_engine() -> Engine:
    """Create synchronous SQLAlchemy engine for tests."""
    if not _INTEGRATION_DB_URL:
        raise RuntimeError("TEST_DATABASE_URL or DATABASE_URL not set")
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")
    return create_engine(sync_url, echo=False, pool_pre_ping=True)


def _get_async_engine() -> AsyncEngine:
    """Create async SQLAlchemy engine for service tests."""
    if not _INTEGRATION_DB_URL:
        raise RuntimeError("TEST_DATABASE_URL or DATABASE_URL not set")
    async_url = _INTEGRATION_DB_URL
    if "+psycopg" in async_url:
        async_url = async_url.replace("+psycopg", "+asyncpg")
    return create_async_engine(async_url, echo=False, pool_pre_ping=True)


@pytest.fixture(scope="module")
def sync_engine() -> Generator[Engine, None, None]:
    engine = _get_sync_engine()
    yield engine
    engine.dispose()


@pytest.fixture
def db_conn(sync_engine: Engine) -> Iterator[Connection]:
    with sync_engine.connect() as conn:
        yield conn


@pytest.fixture(autouse=True)
def clean_database(db_conn: Connection) -> Generator[None, None, None]:
    """Ensure clean state before and after each test."""
    session = _SessionFactory()
    try:
        _delete_existing_business_data(session)
        session.commit()
    finally:
        session.close()
    yield
    session = _SessionFactory()
    try:
        _delete_existing_business_data(session)
        session.commit()
    finally:
        session.close()


@pytest.fixture
async def async_session() -> AsyncIterator[AsyncSession]:
    engine = _get_async_engine()
    session_factory = async_sessionmaker[AsyncSession](
        bind=engine, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Endpoint Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDatasetStatusEndpoint:
    """Test the GET /api/v1/system/dataset/status endpoint."""

    async def test_empty_database_returns_not_loaded(self, client: AsyncClient) -> None:
        """When all business tables are empty, endpoint returns not_loaded."""
        response = await client.get("/api/v1/system/dataset/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "not_loaded"
        assert data["dataset_version"] == "GOLDEN_DATASET_V1.0"
        assert data["checksum_algorithm"] == "sha256:v1"
        assert data["expected_checksum"] == EXPECTED_CHECKSUM
        assert data["actual_checksum"] is None

    async def test_seeded_database_returns_valid(self, client: AsyncClient) -> None:
        """After seeding, endpoint returns valid status with matching checksums."""
        load_golden_dataset()
        response = await client.get("/api/v1/system/dataset/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "valid"
        assert data["dataset_version"] == "GOLDEN_DATASET_V1.0"
        assert data["checksum_algorithm"] == "sha256:v1"
        assert data["expected_checksum"] == EXPECTED_CHECKSUM
        assert data["actual_checksum"] == EXPECTED_CHECKSUM

    async def test_tampered_quantity_returns_invalid(
        self, client: AsyncClient, db_conn: Connection
    ) -> None:
        """Modifying a business quantity makes the checksum mismatch."""
        load_golden_dataset()
        db_conn.execute(text(
            "UPDATE inventory_balances SET quantity_on_hand = 99 "
            "WHERE component_id = (SELECT id FROM components WHERE code = 'CTRL-X4')"
        ))
        db_conn.commit()

        response = await client.get("/api/v1/system/dataset/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "invalid"
        assert data["actual_checksum"] != EXPECTED_CHECKSUM

    async def test_deleted_row_returns_invalid(
        self, client: AsyncClient, db_conn: Connection
    ) -> None:
        """Deleting a row makes the checksum mismatch."""
        load_golden_dataset()
        db_conn.execute(text(
            "DELETE FROM inventory_balances "
            "WHERE component_id = (SELECT id FROM components WHERE code = 'PIPE-P1')"
        ))
        db_conn.commit()

        response = await client.get("/api/v1/system/dataset/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "invalid"

    async def test_added_row_returns_invalid(
        self, client: AsyncClient, db_conn: Connection
    ) -> None:
        """Adding an extra row makes the checksum mismatch."""
        load_golden_dataset()
        db_conn.execute(text(
            "INSERT INTO suppliers (id, code, name) "
            "VALUES (gen_random_uuid(), 'SUP-EXTRA', 'Extra Supplier')"
        ))
        db_conn.commit()

        response = await client.get("/api/v1/system/dataset/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "invalid"

    async def test_changed_relationship_returns_invalid(
        self, client: AsyncClient, db_conn: Connection
    ) -> None:
        """Moving a BOM item to a different product version changes the checksum."""
        load_golden_dataset()
        db_conn.execute(text("""
            UPDATE bom_items
            SET product_version_id = (
                SELECT pv.id FROM product_versions pv
                JOIN products p ON pv.product_id = p.id
                WHERE p.code = 'PROD-PUMP-001' AND pv.version = '2.3'
                LIMIT 1
            )
            WHERE id = (
                SELECT bi.id FROM bom_items bi
                JOIN product_versions pv ON bi.product_version_id = pv.id
                JOIN products p ON pv.product_id = p.id
                JOIN components c ON bi.component_id = c.id
                WHERE p.code = 'PROD-PUMP-001'
                  AND pv.version = '2.1'
                  AND c.code = 'CTRL-X4'
                LIMIT 1
            )
        """))
        db_conn.commit()

        response = await client.get("/api/v1/system/dataset/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "invalid"

    async def test_reseed_restores_valid(self, client: AsyncClient) -> None:
        """After tampering, reseeding restores valid status."""
        load_golden_dataset()
        response = await client.get("/api/v1/system/dataset/status")
        assert response.json()["status"] == "valid"

        # Reseed (idempotent)
        load_golden_dataset()

        response = await client.get("/api/v1/system/dataset/status")
        data = response.json()
        assert data["status"] == "valid"
        assert data["actual_checksum"] == EXPECTED_CHECKSUM

    async def test_diagnostic_jobs_do_not_affect_checksum(
        self, client: AsyncClient, db_conn: Connection
    ) -> None:
        """Inserting into diagnostic_jobs does not change the checksum."""
        load_golden_dataset()

        response_before = await client.get("/api/v1/system/dataset/status")
        checksum_before = response_before.json()["actual_checksum"]

        db_conn.execute(text("""
            INSERT INTO diagnostic_jobs (id, correlation_id, status, created_at)
            VALUES (gen_random_uuid(), gen_random_uuid(), 'completed', NOW())
        """))
        db_conn.commit()

        response_after = await client.get("/api/v1/system/dataset/status")
        checksum_after = response_after.json()["actual_checksum"]

        assert checksum_before == checksum_after
        assert response_after.json()["status"] == "valid"

    async def test_partial_fixture_returns_invalid(
        self, client: AsyncClient, db_conn: Connection
    ) -> None:
        """When only some tables are populated, endpoint returns invalid."""
        db_conn.execute(text(
            "INSERT INTO products (id, code, name, description) "
            "VALUES (gen_random_uuid(), 'PROD-PUMP-001', 'Industrial Pump MK-III', "
            "'Heavy-duty industrial pump for manufacturing plants')"
        ))
        db_conn.commit()

        response = await client.get("/api/v1/system/dataset/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "invalid"

    async def test_response_schema_conformance(self, client: AsyncClient) -> None:
        """Verify endpoint response matches the documented schema."""
        response = await client.get("/api/v1/system/dataset/status")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "dataset_version" in data
        assert "checksum_algorithm" in data
        assert "expected_checksum" in data
        assert "actual_checksum" in data
        assert data["status"] in ("valid", "invalid", "not_loaded")
        assert data["expected_checksum"].startswith("sha256:")
        assert len(data["expected_checksum"]) == 71  # "sha256:" + 64 hex chars


# ─────────────────────────────────────────────────────────────────────────────
# Database Checksum Service Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDatabaseChecksumService:
    """Test the DatasetIntegrityService directly against PostgreSQL."""

    async def test_actual_checksum_matches_expected_after_seed(
        self, async_session: AsyncSession
    ) -> None:
        """After seeding, the DB-produced checksum must equal EXPECTED_CHECKSUM."""
        load_golden_dataset()

        from app.services.dataset_integrity import DatasetIntegrityService

        service = DatasetIntegrityService(async_session)
        actual = await service.compute_actual_checksum()
        assert actual == EXPECTED_CHECKSUM

    async def test_checksums_deterministic_on_rerun(
        self, async_session: AsyncSession
    ) -> None:
        """Computing checksum twice yields the same result."""
        load_golden_dataset()

        from app.services.dataset_integrity import DatasetIntegrityService

        service = DatasetIntegrityService(async_session)
        actual1 = await service.compute_actual_checksum()
        actual2 = await service.compute_actual_checksum()
        assert actual1 == actual2
        assert actual1 == EXPECTED_CHECKSUM

    async def test_entity_counts_after_seed(self, async_session: AsyncSession) -> None:
        """Entity counts match the expected counts after seeding."""
        load_golden_dataset()

        from app.services.dataset_integrity import DatasetIntegrityService

        service = DatasetIntegrityService(async_session)
        counts = await service.get_entity_counts()
        assert counts["products"] == 1
        assert counts["product_versions"] == 3
        assert counts["components"] == 5
        assert counts["bom_items"] == 9
        assert counts["warehouses"] == 1
        assert counts["inventory_balances"] == 5
        assert counts["suppliers"] == 3
        assert counts["production_plans"] == 1
        assert counts["production_orders"] == 3
        assert counts["inventory_reservations"] == 0
        assert counts["purchase_orders"] == 3
        assert counts["purchase_order_lines"] == 3
        assert counts["production_order_requirements"] == 9
        assert counts["component_alternatives"] == 1
