"""Golden Dataset PostgreSQL loader.

Transactional loader for Phase 2 Golden Dataset. Implements:
- Alembic head verification
- Transaction boundaries with rollback
- Idempotent loading (safe to run multiple times)
- Preservation of Phase 1 diagnostic_jobs

Dataset version: GOLDEN_DATASET_V1.0
"""

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models.component import BomItem, Component, ComponentAlternative
from app.models.product import Product, ProductVersion
from app.models.production import (
    ProductionOrder,
    ProductionOrderRequirement,
    ProductionPlan,
)
from app.models.supplier import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.warehouse import InventoryBalance, InventoryReservation, Warehouse
from app.seed.generator.golden_dataset import (
    ANCHOR_DATE,
    DATASET_VERSION,
    SEED,
    generate_golden_dataset,
)

logger = logging.getLogger(__name__)

# Expected Alembic revision after WP-2.2 migration
EXPECTED_ALEMBIC_HEAD = "3f5e7a9b21cd"


def _get_sync_engine() -> Engine:
    """Create synchronous SQLAlchemy engine for loader operations.

    Returns:
        Synchronous SQLAlchemy engine
    """
    # Convert async URL to sync URL (like Alembic does)
    sync_url = settings.database_url
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")

    return create_engine(sync_url, echo=False, pool_pre_ping=True)


# Create sync engine for loader operations
_sync_engine = _get_sync_engine()
_SessionFactory = sessionmaker(bind=_sync_engine)


def _verify_alembic_head() -> None:
    """Verify the database is at the expected Alembic revision.

    Checks three things:
      1. Alembic migration scripts declare the expected head revision.
      2. The `alembic_version` table exists in the database.
      3. The stored version matches the expected head.

    This uses direct DB queries (no alembic.ini file path lookup) for reliability
    across host/container filesystem layouts.

    Raises:
        RuntimeError: If any check fails
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    # Resolve alembic.ini location.
    # Module is at backend/app/seed/generator/, so backend/ is 4 levels up.
    backend_root = Path(__file__).resolve().parent.parent.parent.parent
    candidates = [
        backend_root / "alembic.ini",
    ]

    alembic_ini_path = next((p for p in candidates if p.exists()), None)
    if not alembic_ini_path:
        raise RuntimeError(
            f"alembic.ini not found. Tried: {', '.join(str(p) for p in candidates)}"
        )

    alembic_cfg = Config(str(alembic_ini_path))
    script_dir = ScriptDirectory.from_config(alembic_cfg)
    expected_head = script_dir.get_current_head()

    if expected_head != EXPECTED_ALEMBIC_HEAD:
        raise RuntimeError(
            f"Migration scripts declare head '{expected_head}', "
            f"expected '{EXPECTED_ALEMBIC_HEAD}'. Migrations may be out of date."
        )

    # Verify actual DB state
    try:
        with _sync_engine.connect() as conn:
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            row = result.fetchone()
    except Exception as e:
        raise RuntimeError(f"Failed to query alembic_version: {e}") from e

    if not row:
        raise RuntimeError("alembic_version table is empty; run 'alembic upgrade head'")

    db_version = str(row[0])
    if db_version != EXPECTED_ALEMBIC_HEAD:
        raise RuntimeError(
            f"Database at revision '{db_version}', expected '{EXPECTED_ALEMBIC_HEAD}'. "
            f"Run 'alembic upgrade head' before loading seed data."
        )

    logger.info(f"Alembic revision verified: {EXPECTED_ALEMBIC_HEAD}")


def _delete_existing_business_data(session: Session) -> int:
    """Delete existing business data while preserving diagnostic_jobs.

    Returns:
        Number of records deleted

    Raises:
        Exception: If deletion fails
    """
    total_deleted = 0

    # Delete in reverse dependency order (children before parents)
    # Note: No FK from diagnostic_jobs, so it's preserved automatically

    total_deleted += session.query(ProductionOrderRequirement).delete()
    total_deleted += session.query(PurchaseOrderLine).delete()
    total_deleted += session.query(PurchaseOrder).delete()
    total_deleted += session.query(Supplier).delete()
    total_deleted += session.query(InventoryReservation).delete()
    total_deleted += session.query(InventoryBalance).delete()
    total_deleted += session.query(ProductionOrder).delete()
    total_deleted += session.query(ProductionPlan).delete()
    total_deleted += session.query(ComponentAlternative).delete()
    total_deleted += session.query(BomItem).delete()
    total_deleted += session.query(ProductVersion).delete()
    total_deleted += session.query(Product).delete()
    total_deleted += session.query(Warehouse).delete()
    total_deleted += session.query(Component).delete()

    logger.info(f"Deleted {total_deleted} existing business records")
    return total_deleted


def _insert_products(session: Session, products: list[dict[str, Any]]) -> None:
    """Insert products into database."""
    for product_data in products:
        product = Product(**product_data)
        session.add(product)


def _insert_product_versions(
    session: Session, product_versions: list[dict[str, Any]]
) -> None:
    """Insert product versions into database."""
    for pv_data in product_versions:
        product_version = ProductVersion(**pv_data)
        session.add(product_version)


def _insert_components(session: Session, components: list[dict[str, Any]]) -> None:
    """Insert components into database."""
    for component_data in components:
        component = Component(**component_data)
        session.add(component)


def _insert_bom_items(session: Session, bom_items: list[dict[str, Any]]) -> None:
    """Insert BOM items into database."""
    for bom_item_data in bom_items:
        bom_item = BomItem(**bom_item_data)
        session.add(bom_item)


def _insert_component_alternatives(
    session: Session, component_alternatives: list[dict[str, Any]]
) -> None:
    """Insert component alternatives into database."""
    for alt_data in component_alternatives:
        alternative = ComponentAlternative(**alt_data)
        session.add(alternative)


def _insert_warehouses(session: Session, warehouses: list[dict[str, Any]]) -> None:
    """Insert warehouses into database."""
    for warehouse_data in warehouses:
        warehouse = Warehouse(**warehouse_data)
        session.add(warehouse)


def _insert_suppliers(session: Session, suppliers: list[dict[str, Any]]) -> None:
    """Insert suppliers into database."""
    for supplier_data in suppliers:
        supplier = Supplier(**supplier_data)
        session.add(supplier)


def _insert_production_plans(
    session: Session, production_plans: list[dict[str, Any]]
) -> None:
    """Insert production plans into database."""
    for plan_data in production_plans:
        plan = ProductionPlan(**plan_data)
        session.add(plan)


def _insert_production_orders(
    session: Session, production_orders: list[dict[str, Any]]
) -> None:
    """Insert production orders into database."""
    for order_data in production_orders:
        order = ProductionOrder(**order_data)
        session.add(order)


def _insert_inventory_balances(
    session: Session, inventory_balances: list[dict[str, Any]]
) -> None:
    """Insert inventory balances into database."""
    for balance_data in inventory_balances:
        balance = InventoryBalance(**balance_data)
        session.add(balance)


def _insert_inventory_reservations(
    session: Session, inventory_reservations: list[dict[str, Any]]
) -> None:
    """Insert inventory reservations into database."""
    for reservation_data in inventory_reservations:
        reservation = InventoryReservation(**reservation_data)
        session.add(reservation)


def _insert_purchase_orders(
    session: Session, purchase_orders: list[dict[str, Any]]
) -> None:
    """Insert purchase orders into database."""
    for po_data in purchase_orders:
        po = PurchaseOrder(**po_data)
        session.add(po)


def _insert_purchase_order_lines(
    session: Session, purchase_order_lines: list[dict[str, Any]]
) -> None:
    """Insert purchase order lines into database."""
    for line_data in purchase_order_lines:
        line = PurchaseOrderLine(**line_data)
        session.add(line)


def _insert_production_order_requirements(
    session: Session, production_order_requirements: list[dict[str, Any]]
) -> None:
    """Insert production order requirements into database."""
    for req_data in production_order_requirements:
        requirement = ProductionOrderRequirement(**req_data)
        session.add(requirement)


def load_golden_dataset() -> dict[str, int]:
    """Load the Golden Dataset into PostgreSQL with transaction safety.

    Implements:
    - Alembic head verification
    - Delete existing business data (preserves diagnostic_jobs)
    - Insert all entities in dependency order
    - Commit transaction or rollback on failure

    Returns:
        Dictionary with counts of inserted records per entity type

    Raises:
        RuntimeError: If Alembic head is not at expected revision
        Exception: If insertion fails (transaction rolls back)
    """
    logger.info("=" * 70)
    logger.info(f"Loading Golden Dataset v{DATASET_VERSION}")
    logger.info(f"Seed: {SEED}")
    logger.info(f"Anchor Date: {ANCHOR_DATE}")
    logger.info("=" * 70)

    # Verify Alembic head
    _verify_alembic_head()

    # Generate dataset
    dataset = generate_golden_dataset()

    # Create session and begin transaction
    session = _SessionFactory()

    try:
        # Delete existing business data
        deleted_count = _delete_existing_business_data(session)

        # Insert in dependency order
        _insert_products(session, dataset["products"])
        _insert_product_versions(session, dataset["product_versions"])
        _insert_components(session, dataset["components"])
        _insert_bom_items(session, dataset["bom_items"])
        _insert_component_alternatives(session, dataset["component_alternatives"])
        _insert_warehouses(session, dataset["warehouses"])
        _insert_suppliers(session, dataset["suppliers"])
        _insert_production_plans(session, dataset["production_plans"])
        _insert_production_orders(session, dataset["production_orders"])
        _insert_inventory_balances(session, dataset["inventory_balances"])
        _insert_inventory_reservations(session, dataset["inventory_reservations"])
        _insert_purchase_orders(session, dataset["purchase_orders"])
        _insert_purchase_order_lines(session, dataset["purchase_order_lines"])
        _insert_production_order_requirements(
            session, dataset["production_order_requirements"]
        )

        # Commit transaction
        session.commit()

        logger.info("Golden Dataset loaded successfully")
        logger.info("=" * 70)

        # Return counts
        return {
            "products": len(dataset["products"]),
            "product_versions": len(dataset["product_versions"]),
            "components": len(dataset["components"]),
            "bom_items": len(dataset["bom_items"]),
            "component_alternatives": len(dataset["component_alternatives"]),
            "warehouses": len(dataset["warehouses"]),
            "suppliers": len(dataset["suppliers"]),
            "production_plans": len(dataset["production_plans"]),
            "production_orders": len(dataset["production_orders"]),
            "inventory_balances": len(dataset["inventory_balances"]),
            "inventory_reservations": len(dataset["inventory_reservations"]),
            "purchase_orders": len(dataset["purchase_orders"]),
            "purchase_order_lines": len(dataset["purchase_order_lines"]),
            "production_order_requirements": len(
                dataset["production_order_requirements"]
            ),
            "deleted": deleted_count,
        }

    except Exception as e:
        # Rollback transaction on failure
        session.rollback()
        logger.error(f"Failed to load Golden Dataset: {e}")
        logger.error("Transaction rolled back")
        logger.error("=" * 70)
        raise
    finally:
        session.close()


def main() -> None:
    """CLI entry point for seed generator."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        counts = load_golden_dataset()

        logger.info("Golden Dataset loaded successfully")
        logger.info("Inserted records:")
        for k, v in counts.items():
            logger.info("  %s: %s", k, v)

    except RuntimeError as e:
        logger.error(f"Error: {e}")
        raise SystemExit(1) from None
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
