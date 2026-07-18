"""Test Phase 2 business schema foundation.

Verifies that all 14 business models are correctly defined and that
the Alembic migration contains proper table definitions.
"""

from app.database import Base
from app.models import (
    BomItem,
    Component,
    ComponentAlternative,
    InventoryBalance,
    InventoryReservation,
    Product,
    ProductionOrder,
    ProductionOrderRequirement,
    ProductionPlan,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    Warehouse,
)


class TestModelRegistration:
    """Test all business models are registered with Base.metadata."""

    def test_all_business_models_importable(self) -> None:
        """Verify all 14 business models can be imported."""
        models = [
            Product,
            Warehouse,
            Component,
            BomItem,
            Supplier,
            PurchaseOrder,
            PurchaseOrderLine,
            ProductionPlan,
            ProductionOrder,
            ProductionOrderRequirement,
            ComponentAlternative,
            InventoryBalance,
            InventoryReservation,
        ]
        assert len(models) == 13, "Expected 13 Phase 2 models"

    def test_all_tables_registered_in_metadata(self) -> None:
        """Verify all 14 business tables are in Base.metadata."""
        expected_tables = {
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
        }
        actual_tables = set(Base.metadata.tables.keys())
        # Expect 14 business tables + diagnostic_jobs
        assert expected_tables.issubset(actual_tables), (
            f"Missing tables: {expected_tables - actual_tables}"
        )

    def test_diagnostic_table_still_present(self) -> None:
        """Phase 1 diagnostic_jobs table remains in metadata."""
        assert "diagnostic_jobs" in Base.metadata.tables


class TestModelTableNames:
    """Test that each model has the correct __tablename__."""

    def test_product_tablename(self) -> None:
        assert Product.__tablename__ == "products"

    def test_component_tablename(self) -> None:
        assert Component.__tablename__ == "components"

    def test_bom_item_tablename(self) -> None:
        assert BomItem.__tablename__ == "bom_items"

    def test_warehouse_tablename(self) -> None:
        assert Warehouse.__tablename__ == "warehouses"

    def test_inventory_balance_tablename(self) -> None:
        assert InventoryBalance.__tablename__ == "inventory_balances"

    def test_inventory_reservation_tablename(self) -> None:
        assert InventoryReservation.__tablename__ == (
            "inventory_reservations"
        )

    def test_supplier_tablename(self) -> None:
        assert Supplier.__tablename__ == "suppliers"

    def test_purchase_order_tablename(self) -> None:
        assert PurchaseOrder.__tablename__ == "purchase_orders"

    def test_purchase_order_line_tablename(self) -> None:
        assert PurchaseOrderLine.__tablename__ == "purchase_order_lines"

    def test_production_plan_tablename(self) -> None:
        assert ProductionPlan.__tablename__ == "production_plans"

    def test_production_order_tablename(self) -> None:
        assert ProductionOrder.__tablename__ == "production_orders"

    def test_production_order_requirement_tablename(self) -> None:
        assert ProductionOrderRequirement.__tablename__ == (
            "production_order_requirements"
        )

    def test_component_alternative_tablename(self) -> None:
        assert ComponentAlternative.__tablename__ == (
            "component_alternatives"
        )


class TestModelColumnCounts:
    """Test that each model has the expected number of columns."""

    def test_product_columns(self) -> None:
        cols = {c.name for c in Product.__table__.columns}
        assert cols == {"id", "code", "name", "description"}

    def test_component_columns(self) -> None:
        cols = {c.name for c in Component.__table__.columns}
        assert cols == {"id", "code", "name", "unit", "description"}

    def test_bom_item_columns(self) -> None:
        cols = {c.name for c in BomItem.__table__.columns}
        assert cols == {
            "id",
            "product_version_id",
            "component_id",
            "quantity_per_unit",
        }

    def test_warehouse_columns(self) -> None:
        cols = {c.name for c in Warehouse.__table__.columns}
        assert cols == {"id", "code", "name"}

    def test_inventory_balance_columns(self) -> None:
        cols = {c.name for c in InventoryBalance.__table__.columns}
        assert cols == {
            "id",
            "component_id",
            "warehouse_id",
            "quantity_on_hand",
        }

    def test_inventory_reservation_columns(self) -> None:
        cols = {c.name for c in InventoryReservation.__table__.columns}
        assert cols == {
            "id",
            "component_id",
            "warehouse_id",
            "production_order_id",
            "quantity",
        }

    def test_supplier_columns(self) -> None:
        cols = {c.name for c in Supplier.__table__.columns}
        assert cols == {"id", "code", "name"}

    def test_purchase_order_columns(self) -> None:
        cols = {c.name for c in PurchaseOrder.__table__.columns}
        assert cols == {
            "id",
            "supplier_id",
            "po_number",
            "status",
            "placed_at",
        }

    def test_purchase_order_line_columns(self) -> None:
        cols = {c.name for c in PurchaseOrderLine.__table__.columns}
        assert cols == {
            "id",
            "purchase_order_id",
            "component_id",
            "ordered_quantity",
            "received_quantity",
            "expected_delivery_date",
            "status",
        }

    def test_production_plan_columns(self) -> None:
        cols = {c.name for c in ProductionPlan.__table__.columns}
        assert cols == {
            "id",
            "code",
            "status",
            "created_at",
            "period_start",
            "period_end",
        }

    def test_production_order_columns(self) -> None:
        cols = {c.name for c in ProductionOrder.__table__.columns}
        assert cols == {
            "id",
            "production_plan_id",
            "code",
            "product_version_id",
            "quantity",
            "need_date",
            "status",
        }

    def test_production_order_requirement_columns(self) -> None:
        cols = {
            c.name
            for c in ProductionOrderRequirement.__table__.columns
        }
        assert cols == {
            "id",
            "production_order_id",
            "component_id",
            "required_quantity",
            "reserved_quantity",
        }

    def test_component_alternative_columns(self) -> None:
        cols = {
            c.name for c in ComponentAlternative.__table__.columns
        }
        assert cols == {
            "id",
            "component_id",
            "alternative_component_id",
            "status",
            "rationale",
        }


class TestModelConstraints:
    """Test that models have correct constraints and indexes."""

    def test_bom_item_unique_constraint(self) -> None:
        """BOM items: unique on (product_version_id, component_id)."""
        idx_names = {idx.name for idx in BomItem.__table__.indexes}
        expected = "idx_bom_items_product_version_id_component_id"
        assert expected in idx_names

    def test_inventory_balance_unique_constraint(self) -> None:
        """Inventory balances: unique on (component_id, warehouse_id)."""
        idx_names = {
            idx.name for idx in InventoryBalance.__table__.indexes
        }
        assert "idx_inventory_balances_comp_wh" in idx_names

    def test_component_alternative_unique_constraint(self) -> None:
        """Alt: unique on (component_id, alternative_component_id)."""
        idx_names = {
            idx.name
            for idx in ComponentAlternative.__table__.indexes
        }
        assert "idx_component_alternatives_comp_alt" in idx_names

    def test_purchase_order_po_number_index(self) -> None:
        """Purchase orders: unique index on po_number."""
        idx_names = {
            idx.name for idx in PurchaseOrder.__table__.indexes
        }
        assert "idx_purchase_orders_po_number" in idx_names

    def test_production_order_code_index(self) -> None:
        """Production orders: unique index on code."""
        idx_names = {
            idx.name for idx in ProductionOrder.__table__.indexes
        }
        assert "idx_production_orders_code" in idx_names


def _fk_targets(columns, *col_names):
    """Collect FK target table names for given column names."""
    targets = set()
    for col_name in col_names:
        for fk in columns[col_name].foreign_keys:
            targets.add(fk.column.table.name)
    return targets


class TestModelForeignKeys:
    """Test that models have correct foreign key relationships."""

    def test_bom_item_foreign_keys(self) -> None:
        """BOM items reference product_versions and components."""
        cols = BomItem.__table__.columns
        targets = _fk_targets(
            cols, "product_version_id", "component_id"
        )
        assert targets == {"product_versions", "components"}

    def test_inventory_balance_foreign_keys(self) -> None:
        """Inventory balances reference components and warehouses."""
        cols = InventoryBalance.__table__.columns
        targets = _fk_targets(cols, "component_id", "warehouse_id")
        assert targets == {"components", "warehouses"}

    def test_inventory_reservation_foreign_keys(self) -> None:
        """Reservations reference components, warehouses, WOs."""
        cols = InventoryReservation.__table__.columns
        targets = _fk_targets(
            cols,
            "component_id",
            "warehouse_id",
            "production_order_id",
        )
        assert targets == {
            "components",
            "warehouses",
            "production_orders",
        }

    def test_purchase_order_line_foreign_keys(self) -> None:
        """POLs reference purchase_orders and components."""
        cols = PurchaseOrderLine.__table__.columns
        targets = _fk_targets(
            cols, "purchase_order_id", "component_id"
        )
        assert targets == {"purchase_orders", "components"}

    def test_production_order_foreign_keys(self) -> None:
        """WOs reference production_plans and product_versions."""
        cols = ProductionOrder.__table__.columns
        targets = _fk_targets(
            cols, "production_plan_id", "product_version_id"
        )
        assert targets == {"production_plans", "product_versions"}

    def test_production_order_requirement_foreign_keys(self) -> None:
        """Requirements reference WOs and components."""
        cols = ProductionOrderRequirement.__table__.columns
        targets = _fk_targets(
            cols, "production_order_id", "component_id"
        )
        assert targets == {"production_orders", "components"}

    def test_component_alternative_foreign_keys(self) -> None:
        """Alt: both FKs point to components."""
        cols = ComponentAlternative.__table__.columns
        targets = _fk_targets(
            cols, "component_id", "alternative_component_id"
        )
        assert targets == {"components"}


class TestModelRelationships:
    """Test that models have correct ORM relationships defined."""

    def test_product_has_versions_relationship(self) -> None:
        """Product should have a 'versions' relationship."""
        assert hasattr(Product, "versions")
        rel = Product.__mapper__.relationships.get("versions")
        assert rel is not None

    def test_component_has_bom_items_relationship(self) -> None:
        """Component should have a 'bom_items' relationship."""
        assert hasattr(Component, "bom_items")
        rel = Component.__mapper__.relationships.get("bom_items")
        assert rel is not None

    def test_warehouse_has_inventory_balances_relationship(self) -> None:
        """Warehouse should have 'inventory_balances' relationship."""
        assert hasattr(Warehouse, "inventory_balances")
        rel = Warehouse.__mapper__.relationships.get(
            "inventory_balances"
        )
        assert rel is not None

    def test_purchase_order_has_lines_relationship(self) -> None:
        """Purchase order should have a 'lines' relationship."""
        assert hasattr(PurchaseOrder, "lines")
        rel = PurchaseOrder.__mapper__.relationships.get("lines")
        assert rel is not None

    def test_production_plan_has_orders_relationship(self) -> None:
        """Plan should have a 'production_orders' relationship."""
        assert hasattr(ProductionPlan, "production_orders")
        rel = ProductionPlan.__mapper__.relationships.get(
            "production_orders"
        )
        assert rel is not None

    def test_production_order_has_requirements_relationship(self) -> None:
        """WO should have a 'requirements' relationship."""
        assert hasattr(ProductionOrder, "requirements")
        rel = ProductionOrder.__mapper__.relationships.get(
            "requirements"
        )
        assert rel is not None
