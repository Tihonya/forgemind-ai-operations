"""Test Phase 2 Alembic migration structure.

Verifies that the migration file contains correct table definitions,
proper upgrade/downgrade logic, and maintains compatibility with
Phase 1 diagnostic_jobs table.
"""

import re

import pytest

# Path constant to avoid repeated long path expressions
_MIGRATION_REL = (
    "alembic/versions/"
    "3f5e7a9b21cd_add_phase_2_business_schema.py"
)
_MIGRATION_PATH = (
    __import__("pathlib", fromlist=["Path"]).Path(__file__)
    .parents[2]
    / _MIGRATION_REL
)


class TestMigrationFileStructure:
    """Test that the migration file has correct structure and metadata."""

    @pytest.fixture
    def migration_file(self):
        """Path to the Phase 2 business schema migration file."""
        return _MIGRATION_PATH

    def test_migration_file_exists(self, migration_file) -> None:
        """Migration file should exist at expected location."""
        assert migration_file.exists(), (
            f"Migration file not found: {migration_file}"
        )

    def test_migration_has_correct_revision_id(
        self, migration_file
    ) -> None:
        """Migration should have the expected revision ID."""
        content = migration_file.read_text()
        assert "revision: str = '3f5e7a9b21cd'" in content

    def test_migration_has_correct_down_revision(
        self, migration_file
    ) -> None:
        """Migration should chain from Phase 1 diagnostic migration."""
        content = migration_file.read_text()
        expected = "down_revision: str | Sequence[str] | None"
        assert expected in content
        assert "'129270172ebc'" in content

    def test_migration_has_upgrade_function(
        self, migration_file
    ) -> None:
        """Migration should define an upgrade() function."""
        content = migration_file.read_text()
        assert "def upgrade() -> None:" in content

    def test_migration_has_downgrade_function(
        self, migration_file
    ) -> None:
        """Migration should define a downgrade() function."""
        content = migration_file.read_text()
        assert "def downgrade() -> None:" in content


def _read_migration() -> str:
    return _MIGRATION_PATH.read_text()


class TestMigrationUpgrade:
    """Test that migration upgrade creates all required tables."""

    @pytest.fixture
    def migration_content(self) -> str:
        """Content of the migration file."""
        return _read_migration()

    def test_creates_products_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create products table."""
        assert "op.create_table(" in migration_content
        assert "'products'," in migration_content

    def test_creates_product_versions_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create product_versions table."""
        assert "'product_versions'," in migration_content

    def test_creates_components_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create components table."""
        assert "'components'," in migration_content

    def test_creates_bom_items_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create bom_items table."""
        assert "'bom_items'," in migration_content

    def test_creates_warehouses_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create warehouses table."""
        assert "'warehouses'," in migration_content

    def test_creates_inventory_balances_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create inventory_balances table."""
        assert "'inventory_balances'," in migration_content

    def test_creates_inventory_reservations_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create inventory_reservations table."""
        assert "'inventory_reservations'," in migration_content

    def test_creates_suppliers_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create suppliers table."""
        assert "'suppliers'," in migration_content

    def test_creates_purchase_orders_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create purchase_orders table."""
        assert "'purchase_orders'," in migration_content

    def test_creates_purchase_order_lines_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create purchase_order_lines table."""
        assert "'purchase_order_lines'," in migration_content

    def test_creates_production_plans_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create production_plans table."""
        assert "'production_plans'," in migration_content

    def test_creates_production_orders_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create production_orders table."""
        assert "'production_orders'," in migration_content

    def test_creates_production_order_requirements_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create production_order_requirements."""
        assert "'production_order_requirements'," in migration_content

    def test_creates_component_alternatives_table(
        self, migration_content: str
    ) -> None:
        """Upgrade should create component_alternatives table."""
        assert "'component_alternatives'," in migration_content


class TestMigrationColumnTypes:
    """Test that migration uses correct column types per specification."""

    @pytest.fixture
    def migration_content(self) -> str:
        """Content of the migration file."""
        return _read_migration()

    def test_quantity_columns_use_numeric_18_4(
        self, migration_content: str
    ) -> None:
        """All quantity columns should use Numeric(18, 4)."""
        # Expected 8 occurrences:
        # bom_items.quantity_per_unit, inventory_balances.quantity_on_hand,
        # inventory_reservations.quantity,
        # purchase_order_lines.ordered_quantity,
        # purchase_order_lines.received_quantity,
        # production_orders.quantity,
        # production_order_requirements.required_quantity,
        # production_order_requirements.reserved_quantity
        numeric_count = migration_content.count(
            "sa.Numeric(18, 4)"
        )
        assert numeric_count == 8, (
            f"Expected 8 Numeric(18, 4) columns, "
            f"found {numeric_count}"
        )

    def test_uuid_primary_keys(
        self, migration_content: str
    ) -> None:
        """All tables should use UUID primary keys."""
        uuid_pk_count = migration_content.count(
            "sa.Column('id', sa.UUID()"
        )
        # 14 tables in WP-2.2 migration
        assert uuid_pk_count >= 14, (
            f"Expected >=14 UUID primary keys, found {uuid_pk_count}"
        )

    def test_timestamps_use_timezone_aware(
        self, migration_content: str
    ) -> None:
        """All timestamp columns should use DateTime(timezone=True)."""
        pattern = r"sa\.Column\('[^']+',\s*sa\.DateTime\(timezone=True\)"
        datetime_columns = re.findall(pattern, migration_content)
        # Should include: production_plans.created_at,
        # purchase_orders.placed_at
        msg = (
            f"Expected >=2 timezone-aware DateTime columns, "
            f"found {len(datetime_columns)}"
        )
        assert len(datetime_columns) >= 2, msg


class TestMigrationConstraints:
    """Test that migration defines correct constraints and indexes."""

    @pytest.fixture
    def migration_content(self) -> str:
        """Content of the migration file."""
        return _read_migration()

    def test_creates_unique_constraints(
        self, migration_content: str
    ) -> None:
        """Migration should create unique constraints."""
        unique_constraints = [
            "uq_products_code",
            "uq_components_code",
            "uq_warehouses_code",
            "uq_suppliers_code",
            "uq_purchase_orders_po_number",
            "uq_production_plans_code",
            "uq_production_orders_code",
        ]
        for constraint in unique_constraints:
            assert constraint in migration_content, (
                f"Missing unique constraint: {constraint}"
            )

    def test_creates_composite_unique_indexes(
        self, migration_content: str
    ) -> None:
        """Migration should create composite unique indexes."""
        composite_indexes = [
            "idx_bom_items_product_version_id_component_id",
            "idx_inventory_balances_comp_wh",
            "idx_component_alternatives_comp_alt",
        ]
        for idx_name in composite_indexes:
            assert idx_name in migration_content, (
                f"Missing composite index: {idx_name}"
            )
        assert "unique=True" in migration_content, (
            "Expected 'unique=True' in migration"
        )

    def test_creates_foreign_keys(
        self, migration_content: str
    ) -> None:
        """Migration should create foreign key constraints."""
        fk_patterns = [
            "['product_versions.id']",
            "['components.id']",
            "['warehouses.id']",
            "['suppliers.id']",
            "['production_orders.id']",
            "['production_plans.id']",
            "['products.id']",
        ]
        for pattern in fk_patterns:
            assert pattern in migration_content, (
                f"Missing foreign key target: {pattern}"
            )

    def test_foreign_keys_use_cascade_delete(
        self, migration_content: str
    ) -> None:
        """All foreign keys should use ON DELETE CASCADE."""
        cascade_count = migration_content.count(
            "ondelete='CASCADE'"
        )
        assert cascade_count >= 15, (
            f"Expected >=15 CASCADE delete FKs, found {cascade_count}"
        )


class TestMigrationDowngrade:
    """Test that migration downgrade properly removes all tables."""

    @pytest.fixture
    def migration_content(self) -> str:
        """Content of the migration file."""
        return _read_migration()

    def test_downgrade_drops_all_tables(
        self, migration_content: str
    ) -> None:
        """Downgrade should drop all 14 Phase 2 tables."""
        tables_to_drop = [
            "products",
            "product_versions",
            "components",
            "bom_items",
            "warehouses",
            "inventory_balances",
            "inventory_reservations",
            "suppliers",
            "purchase_orders",
            "purchase_order_lines",
            "production_plans",
            "production_orders",
            "production_order_requirements",
            "component_alternatives",
        ]
        for table in tables_to_drop:
            expected = f"op.drop_table('{table}')"
            assert expected in migration_content, (
                f"Missing drop for table: {table}"
            )

    def test_downgrade_drops_indexes_before_tables(
        self, migration_content: str
    ) -> None:
        """Downgrade should drop indexes before dropping tables."""
        downgrade_start = migration_content.find(
            "def downgrade() -> None:"
        )
        assert downgrade_start != -1, (
            "Could not find downgrade function"
        )

        downgrade_section = migration_content[downgrade_start:]
        first_drop_index = downgrade_section.find("op.drop_index(")
        first_drop_table = downgrade_section.find("op.drop_table(")

        assert first_drop_index != -1, "No drop_index calls found"
        assert first_drop_table != -1, "No drop_table calls found"
        msg = "Indexes should be dropped before tables"
        assert first_drop_index < first_drop_table, msg


class TestMigrationDoesNotAffect:
    """Test that migration does not affect Phase 1 schema."""

    @pytest.fixture
    def migration_content(self) -> str:
        """Content of the migration file."""
        return _read_migration()

    def test_does_not_drop_diagnostic_jobs_table(
        self, migration_content: str
    ) -> None:
        """Migration should not drop Phase 1 diagnostic_jobs."""
        assert "op.drop_table('diagnostic_jobs')" not in migration_content

    def test_does_not_alter_diagnostic_jobs_table(
        self, migration_content: str
    ) -> None:
        """Migration should not alter Phase 1 diagnostic_jobs."""
        assert "ALTER TABLE diagnostic_jobs" not in migration_content
        assert "drop_index" in migration_content
        downgrade_section = migration_content.split("def downgrade")[1]
        assert "idx_diagnostic_jobs_correlation_id" not in downgrade_section

    def test_does_not_add_auth_entities(
        self, migration_content: str
    ) -> None:
        """Migration should not create auth tables."""
        auth_tables = ["users", "roles", "user_roles"]
        for table in auth_tables:
            assert f"op.create_table('{table}'" not in migration_content

    def test_does_not_add_seed_data(
        self, migration_content: str
    ) -> None:
        """Migration should not INSERT any seed data."""
        assert 'op.execute("INSERT' not in migration_content
        assert "op.execute('INSERT" not in migration_content


class TestMigrationDocumentation:
    """Test that migration has proper documentation."""

    @pytest.fixture
    def migration_content(self) -> str:
        """Content of the migration file."""
        return _read_migration()

    def test_has_migration_docstring(
        self, migration_content: str
    ) -> None:
        """Migration file should have a docstring."""
        assert "Phase 2 business schema" in migration_content
        assert "14 business tables" in migration_content or \
               "Adds 14" in migration_content

    def test_has_create_date_comment(
        self, migration_content: str
    ) -> None:
        """Migration should document its creation date."""
        assert "Create Date:" in migration_content
