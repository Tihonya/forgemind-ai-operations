"""Tests for Golden Dataset loader.

Tests loader behavior:
- Idempotency (safe to run multiple times)
- Transaction rollback on failure
- Preservation of diagnostic_jobs
- Foreign key reference integrity
- Live PostgreSQL validation

All tests REQUIRE a live PostgreSQL database connection via TEST_DATABASE_URL
or the default backend database URL. Tests skip cleanly if unavailable.
"""

import os

import pytest
from sqlalchemy import Engine, create_engine, text

# Determine if integration environment is available
_INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _can_connect_to_db() -> bool:
    """Check if we can connect to the database."""
    if not _INTEGRATION_DB_URL:
        return False
    try:
        # Convert async URL to sync if needed
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
    )
)


def _get_test_engine() -> Engine:
    """Create synchronous SQLAlchemy engine for tests."""
    if not _INTEGRATION_DB_URL:
        raise RuntimeError("TEST_DATABASE_URL or DATABASE_URL not set")
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")
    return create_engine(sync_url, echo=False, pool_pre_ping=True)


from app.seed.generator.loader import (  # noqa: E402
    EXPECTED_ALEMBIC_HEAD,
    _delete_existing_business_data,
    _SessionFactory,
    load_golden_dataset,
)


# Module-level fixture for sync engine
@pytest.fixture(scope="module")
def sync_engine():
    engine = _get_test_engine()
    yield engine
    engine.dispose()


@pytest.fixture
def db_conn(sync_engine):
    with sync_engine.connect() as conn:
        yield conn


@pytest.fixture(autouse=True)
def clean_and_reload_dataset():
    """Ensure dataset is loaded before each test and cleaned after."""
    # Load dataset before test
    load_golden_dataset()

    yield

    # Clean up after test
    session = _SessionFactory()
    try:
        _delete_existing_business_data(session)
        session.commit()
    finally:
        session.close()


class TestLoaderIdempotency:
    """Test that loader can be run multiple times safely."""

    def test_loader_runs_multiple_times_successfully(self):
        """Verify loader can be called multiple times without errors."""
        counts1 = load_golden_dataset()
        counts2 = load_golden_dataset()
        counts3 = load_golden_dataset()

        assert counts1 == counts2 == counts3

    def test_loader_produces_same_counts_on_rerun(self):
        """Verify entity counts are identical after multiple loads."""
        counts1 = load_golden_dataset()
        counts2 = load_golden_dataset()

        for entity_type in counts1:
            if entity_type == "deleted":
                continue
            assert counts1[entity_type] == counts2[entity_type], \
                f"{entity_type} count differs: {counts1[entity_type]} vs {counts2[entity_type]}"


class TestTransactionRollback:
    """Test that loader transaction rolls back on failure."""

    def test_rollback_on_constraint_violation(self, db_conn):
        """Verify transaction rolls back completely when constraint violated."""
        # Insert a component with duplicate code that will conflict with the dataset
        # Use TEST-COMPONENT-CONFLICT so it doesn't collide with any existing dataset code
        db_conn.execute(text("""
            INSERT INTO components (id, code, name, unit, description)
            VALUES (gen_random_uuid(), 'TEST-CONFLICT', 'Conflict', 'PCS', 'Test')
        """))
        db_conn.commit()

        # Now manually trigger the loader's insert path with code that duplicates
        # the TEST-CONFLICT component we just inserted (same code)
        from app.seed.generator.loader import _insert_components, _SessionFactory

        conflicting_component = [{
            "id": __import__("uuid").uuid4(),
            "code": "TEST-CONFLICT",  # duplicates the row above
            "name": "Conflicting",
            "unit": "PCS",
            "description": "This will cause unique violation",
        }]

        session = _SessionFactory()
        try:
            _insert_components(session, conflicting_component)
            session.commit()
            pytest.fail("Expected unique constraint violation")
        except Exception as e:
            session.rollback()
            # Expected - unique constraint on component code
            assert "unique" in str(e).lower() or "duplicate" in str(e).lower()
        finally:
            session.close()

        # Verify no partial data was inserted (rollback worked)
        # The TEST-CONFLICT row we inserted manually should still exist
        # (we committed it before the conflict)
        sql = (
            "SELECT COUNT(*) FROM components "
            "WHERE code = 'TEST-CONFLICT'"
        )
        result = db_conn.execute(text(sql)).fetchone()
        count = result[0]
        assert count == 1  # Only the original row, no duplicate

        # Clean up
        db_conn.execute(text("DELETE FROM components WHERE code = 'TEST-CONFLICT'"))
        db_conn.commit()


class TestDiagnosticJobsPreservation:
    """Test that Phase 1 diagnostic_jobs are preserved."""

    def test_diagnostic_jobs_table_exists(self, db_conn):
        """Verify diagnostic_jobs table exists in database."""
        result = db_conn.execute(text("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'diagnostic_jobs'
        """)).fetchone()
        assert result[0] == 1

    def test_diagnostic_jobs_not_deleted_by_loader(self, db_conn):
        """Verify loader doesn't delete diagnostic_jobs data."""
        # Count existing diagnostic_jobs (if any)
        result = db_conn.execute(text("SELECT COUNT(*) FROM diagnostic_jobs")).fetchone()
        initial_count = result[0]

        # Load dataset
        load_golden_dataset()

        # Count again
        result = db_conn.execute(text("SELECT COUNT(*) FROM diagnostic_jobs")).fetchone()
        final_count = result[0]

        # Should be unchanged
        assert final_count == initial_count


class TestReferentialIntegrity:
    """Test that all foreign keys reference valid entities in the database."""

    def test_all_product_versions_reference_valid_products(self, db_conn):
        """Verify product_versions.product_id references existing products."""
        result = db_conn.execute(text("""
            SELECT COUNT(*) FROM product_versions pv
            LEFT JOIN products p ON pv.product_id = p.id
            WHERE p.id IS NULL
        """)).fetchone()
        assert result[0] == 0

    def test_all_bom_items_reference_valid_product_versions(self, db_conn):
        """Verify bom_items.product_version_id references existing product_versions."""
        result = db_conn.execute(text("""
            SELECT COUNT(*) FROM bom_items bi
            LEFT JOIN product_versions pv ON bi.product_version_id = pv.id
            WHERE pv.id IS NULL
        """)).fetchone()
        assert result[0] == 0

    def test_all_bom_items_reference_valid_components(self, db_conn):
        """Verify bom_items.component_id references existing components."""
        result = db_conn.execute(text("""
            SELECT COUNT(*) FROM bom_items bi
            LEFT JOIN components c ON bi.component_id = c.id
            WHERE c.id IS NULL
        """)).fetchone()
        assert result[0] == 0

    def test_all_component_alternatives_reference_valid_components(self, db_conn):
        """Verify component_alternatives both FKs reference existing components."""
        result = db_conn.execute(text("""
            SELECT COUNT(*) FROM component_alternatives ca
            LEFT JOIN components c1 ON ca.component_id = c1.id
            LEFT JOIN components c2 ON ca.alternative_component_id = c2.id
            WHERE c1.id IS NULL OR c2.id IS NULL
        """)).fetchone()
        assert result[0] == 0

    def test_all_inventory_balances_reference_valid_entities(self, db_conn):
        """Verify inventory_balances FKs reference existing entities."""
        result = db_conn.execute(text("""
            SELECT COUNT(*) FROM inventory_balances ib
            LEFT JOIN components c ON ib.component_id = c.id
            LEFT JOIN warehouses w ON ib.warehouse_id = w.id
            WHERE c.id IS NULL OR w.id IS NULL
        """)).fetchone()
        assert result[0] == 0

    def test_all_purchase_orders_reference_valid_suppliers(self, db_conn):
        """Verify purchase_orders.supplier_id references existing suppliers."""
        result = db_conn.execute(text("""
            SELECT COUNT(*) FROM purchase_orders po
            LEFT JOIN suppliers s ON po.supplier_id = s.id
            WHERE s.id IS NULL
        """)).fetchone()
        assert result[0] == 0

    def test_all_purchase_order_lines_reference_valid_entities(self, db_conn):
        """Verify purchase_order_lines FKs reference existing entities."""
        result = db_conn.execute(text("""
            SELECT COUNT(*) FROM purchase_order_lines pol
            LEFT JOIN purchase_orders po ON pol.purchase_order_id = po.id
            LEFT JOIN components c ON pol.component_id = c.id
            WHERE po.id IS NULL OR c.id IS NULL
        """)).fetchone()
        assert result[0] == 0

    def test_all_production_order_requirements_reference_valid_entities(self, db_conn):
        """Verify production_order_requirements FKs reference existing entities."""
        result = db_conn.execute(text("""
            SELECT COUNT(*) FROM production_order_requirements por
            LEFT JOIN production_orders po ON por.production_order_id = po.id
            LEFT JOIN components c ON por.component_id = c.id
            WHERE po.id IS NULL OR c.id IS NULL
        """)).fetchone()
        assert result[0] == 0


class TestLivePostgreSQLValidation:
    """Test live PostgreSQL database validation."""

    def test_alembic_head_is_correct(self, db_conn):
        """Verify database is at expected Alembic revision."""
        result = db_conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        assert result is not None
        assert result[0] == EXPECTED_ALEMBIC_HEAD

    def test_dataset_loads_completely(self):
        """Verify dataset loads without errors."""
        counts = load_golden_dataset()

        # Verify all entity types are present
        expected_types = [
            "products", "product_versions", "components", "bom_items",
            "component_alternatives", "warehouses", "suppliers", "purchase_orders",
            "purchase_order_lines", "production_plans", "production_orders",
            "inventory_balances", "inventory_reservations",
            "production_order_requirements"
        ]

        for entity_type in expected_types:
            assert entity_type in counts, f"Missing {entity_type} in counts"

    def test_entity_counts_match_expectations(self, db_conn):
        """Verify database contains expected entity counts."""
        expected_counts = {
            "products": 1,
            "product_versions": 3,
            "components": 5,
            "bom_items": 9,
            "component_alternatives": 1,
            "warehouses": 1,
            "suppliers": 3,
            "purchase_orders": 3,
            "purchase_order_lines": 3,
            "production_plans": 1,
            "production_orders": 3,
            "inventory_balances": 5,
            "inventory_reservations": 0,
            "production_order_requirements": 9,
        }

        for table, expected_count in expected_counts.items():
            result = db_conn.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
            actual_count = result[0]
            assert actual_count == expected_count, \
                f"{table}: expected {expected_count}, got {actual_count}"

    def test_business_identifiers_are_correct(self, db_conn):
        """Verify key business identifiers are present."""
        # Check product
        result = db_conn.execute(text("SELECT code FROM products")).fetchone()
        assert result[0] == "PROD-PUMP-001"

        # Check product versions
        result = db_conn.execute(text("""
            SELECT version FROM product_versions
            WHERE product_id = (SELECT id FROM products WHERE code = 'PROD-PUMP-001')
            ORDER BY version
        """)).fetchall()
        versions = [row[0] for row in result]
        assert "2.1" in versions
        assert "2.2" in versions
        assert "2.3" in versions

        # Check components
        result = db_conn.execute(text("SELECT code FROM components ORDER BY code")).fetchall()
        components = [row[0] for row in result]
        assert "CTRL-X4" in components
        assert "MOTOR-M2" in components
        assert "SENSOR-L9" in components
        assert "VALVE-V3" in components
        assert "PIPE-P1" in components

        # Check production orders
        result = db_conn.execute(text(
            "SELECT code FROM production_orders ORDER BY code"
        )).fetchall()
        orders = [row[0] for row in result]
        assert "WO-2026-0142" in orders
        assert "WO-2026-0150" in orders
        assert "WO-2026-0156" in orders

        # Check production plan
        result = db_conn.execute(text("SELECT code FROM production_plans")).fetchone()
        assert result[0] == "PLAN-2026-W31"

    def test_golden_scenario_data_is_accurate(self, db_conn):
        """Verify the exact data required for the golden scenario."""
        # RISK-001: CTRL-X4 shortage = 8
        result = db_conn.execute(text("""
            SELECT
                ib.quantity_on_hand,
                por.required_quantity
            FROM inventory_balances ib
            JOIN components c ON ib.component_id = c.id
            JOIN production_order_requirements por ON c.id = por.component_id
            WHERE c.code = 'CTRL-X4'
        """)).fetchone()
        assert result is not None
        on_hand, required = result
        assert on_hand == 12
        assert required == 20

        # RISK-002: MOTOR-M2 shortage = 6, with late supply
        result = db_conn.execute(text("""
            SELECT
                ib.quantity_on_hand,
                por.required_quantity
            FROM inventory_balances ib
            JOIN components c ON ib.component_id = c.id
            JOIN production_order_requirements por ON c.id = por.component_id
            WHERE c.code = 'MOTOR-M2'
        """)).fetchone()
        assert result is not None
        on_hand, required = result
        assert on_hand == 10
        assert required == 16

        # Verify late supply for MOTOR-M2 (PO line arriving after need_date)
        result = db_conn.execute(text("""
            SELECT pol.ordered_quantity, pol.expected_delivery_date
            FROM purchase_order_lines pol
            JOIN purchase_orders po ON pol.purchase_order_id = po.id
            JOIN components c ON pol.component_id = c.id
            WHERE c.code = 'MOTOR-M2'
              AND po.status = 'CONFIRMED'
              AND pol.status IN ('CONFIRMED', 'IN_TRANSIT')
              AND pol.expected_delivery_date > '2026-08-03'
        """)).fetchone()
        assert result is not None

        # RISK-003: SENSOR-L9 shortage = 5, with proposed alternative
        result = db_conn.execute(text("""
            SELECT
                ib.quantity_on_hand,
                por.required_quantity
            FROM inventory_balances ib
            JOIN components c ON ib.component_id = c.id
            JOIN production_order_requirements por ON c.id = por.component_id
            WHERE c.code = 'SENSOR-L9'
        """)).fetchone()
        assert result is not None
        on_hand, required = result
        assert on_hand == 7
        assert required == 12

        # Verify proposed alternative for SENSOR-L9
        result = db_conn.execute(text("""
            SELECT ca.status
            FROM component_alternatives ca
            JOIN components c ON ca.component_id = c.id
            WHERE c.code = 'SENSOR-L9'
        """)).fetchone()
        assert result is not None
        assert result[0] == "PROPOSED"

    def test_no_inventory_reservations_exist(self, db_conn):
        """Verify no inventory reservations (clean state for future risk calculation)."""
        result = db_conn.execute(text("SELECT COUNT(*) FROM inventory_reservations")).fetchone()
        assert result[0] == 0
