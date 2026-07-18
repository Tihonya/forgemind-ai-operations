"""Add Phase 2 business schema

Revision ID: 3f5e7a9b21cd
Revises: 129270172ebc
Create Date: 2026-07-18 10:00:00.000000

Adds 14 business tables for the Phase 2 Synthetic ERP Core:
- products, product_versions, components, bom_items
- warehouses, inventory_balances, inventory_reservations
- suppliers, purchase_orders, purchase_order_lines
- production_plans, production_orders, production_order_requirements
- component_alternatives

All quantities use numeric(18,4) for ERP-grade precision.
Timestamps use timestamp with time zone (UTC).
No seed data. No auth entities (deferred to WP-2.5).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3f5e7a9b21cd'
down_revision: str | Sequence[str] | None = '129270172ebc'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create 14 Phase 2 business tables with constraints and indexes."""

    # ──────────────────────────────────────────────────────────
    # products — top-level finished goods
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'products',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('code', sa.String(100), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_products_code'),
    )
    op.create_index('idx_products_code', 'products', ['code'], unique=True)

    # ──────────────────────────────────────────────────────────
    # product_versions — distinct releases of a product BOM
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'product_versions',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('product_id', sa.UUID(), nullable=False),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.literal_column("'DRAFT'")),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE', name='fk_product_versions_product_id'),
    )
    op.create_index(
        'idx_product_versions_product_id_version',
        'product_versions',
        ['product_id', 'version'],
        unique=True,
    )

    # ──────────────────────────────────────────────────────────
    # components — discrete parts used in production
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'components',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('code', sa.String(100), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('unit', sa.String(10), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_components_code'),
    )
    op.create_index('idx_components_code', 'components', ['code'], unique=True)

    # ──────────────────────────────────────────────────────────
    # bom_items — bill of materials rows
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'bom_items',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('product_version_id', sa.UUID(), nullable=False),
        sa.Column('component_id', sa.UUID(), nullable=False),
        sa.Column('quantity_per_unit', sa.Numeric(18, 4), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['product_version_id'], ['product_versions.id'],
            ondelete='CASCADE', name='fk_bom_items_product_version_id',
        ),
        sa.ForeignKeyConstraint(
            ['component_id'], ['components.id'],
            ondelete='CASCADE', name='fk_bom_items_component_id',
        ),
    )
    op.create_index(
        'idx_bom_items_product_version_id_component_id',
        'bom_items',
        ['product_version_id', 'component_id'],
        unique=True,
    )

    # ──────────────────────────────────────────────────────────
    # warehouses — named stock locations
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'warehouses',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_warehouses_code'),
    )
    op.create_index('idx_warehouses_code', 'warehouses', ['code'], unique=True)

    # ──────────────────────────────────────────────────────────
    # production_plans — plan headers
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'production_plans',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.literal_column("'DRAFT'")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_production_plans_code'),
    )
    op.create_index('idx_production_plans_code', 'production_plans', ['code'], unique=True)
    op.create_index('idx_production_plans_period', 'production_plans', ['period_start', 'period_end'])

    # ──────────────────────────────────────────────────────────
    # production_orders — work orders under a plan
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'production_orders',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('production_plan_id', sa.UUID(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('product_version_id', sa.UUID(), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 4), nullable=False),
        sa.Column('need_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.literal_column("'PLANNED'")),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_production_orders_code'),
        sa.ForeignKeyConstraint(
            ['production_plan_id'], ['production_plans.id'],
            ondelete='CASCADE', name='fk_production_orders_plan_id',
        ),
        sa.ForeignKeyConstraint(
            ['product_version_id'], ['product_versions.id'],
            ondelete='CASCADE', name='fk_production_orders_product_version_id',
        ),
    )
    op.create_index('idx_production_orders_code', 'production_orders', ['code'], unique=True)
    op.create_index('idx_production_orders_plan_id', 'production_orders', ['production_plan_id'])
    op.create_index('idx_production_orders_product_version_id', 'production_orders', ['product_version_id'])
    op.create_index('idx_production_orders_need_date', 'production_orders', ['need_date'])

    # ──────────────────────────────────────────────────────────
    # inventory_balances — per (component, warehouse) on-hand
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'inventory_balances',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('component_id', sa.UUID(), nullable=False),
        sa.Column('warehouse_id', sa.UUID(), nullable=False),
        sa.Column('quantity_on_hand', sa.Numeric(18, 4), nullable=False, server_default=sa.literal_column('0')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['component_id'], ['components.id'],
            ondelete='CASCADE', name='fk_inventory_balances_component_id',
        ),
        sa.ForeignKeyConstraint(
            ['warehouse_id'], ['warehouses.id'],
            ondelete='CASCADE', name='fk_inventory_balances_warehouse_id',
        ),
    )
    op.create_index(
        'idx_inventory_balances_comp_wh',
        'inventory_balances',
        ['component_id', 'warehouse_id'],
        unique=True,
    )

    # ──────────────────────────────────────────────────────────
    # inventory_reservations — per (component, warehouse, WO) reserved
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'inventory_reservations',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('component_id', sa.UUID(), nullable=False),
        sa.Column('warehouse_id', sa.UUID(), nullable=False),
        sa.Column('production_order_id', sa.UUID(), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 4), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['component_id'], ['components.id'],
            ondelete='CASCADE', name='fk_inventory_reservations_component_id',
        ),
        sa.ForeignKeyConstraint(
            ['warehouse_id'], ['warehouses.id'],
            ondelete='CASCADE', name='fk_inventory_reservations_warehouse_id',
        ),
        sa.ForeignKeyConstraint(
            ['production_order_id'], ['production_orders.id'],
            ondelete='CASCADE', name='fk_inventory_reservations_production_order_id',
        ),
    )
    op.create_index(
        'idx_inventory_reservations_comp_wo',
        'inventory_reservations',
        ['component_id', 'warehouse_id', 'production_order_id'],
    )

    # ──────────────────────────────────────────────────────────
    # suppliers — named vendors
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'suppliers',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uq_suppliers_code'),
    )
    op.create_index('idx_suppliers_code', 'suppliers', ['code'], unique=True)

    # ──────────────────────────────────────────────────────────
    # purchase_orders — header with status (RECEIVED allowed, not DELIVERED)
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'purchase_orders',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('supplier_id', sa.UUID(), nullable=False),
        sa.Column('po_number', sa.String(50), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.literal_column("'PLACED'")),
        sa.Column('placed_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('po_number', name='uq_purchase_orders_po_number'),
        sa.ForeignKeyConstraint(
            ['supplier_id'], ['suppliers.id'],
            ondelete='CASCADE', name='fk_purchase_orders_supplier_id',
        ),
    )
    op.create_index('idx_purchase_orders_po_number', 'purchase_orders', ['po_number'], unique=True)
    op.create_index('idx_purchase_orders_supplier_id', 'purchase_orders', ['supplier_id'])
    op.create_index('idx_purchase_orders_placed_at', 'purchase_orders', ['placed_at'])

    # ──────────────────────────────────────────────────────────
    # purchase_order_lines — line level (DELIVERED allowed, not RECEIVED)
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'purchase_order_lines',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('purchase_order_id', sa.UUID(), nullable=False),
        sa.Column('component_id', sa.UUID(), nullable=False),
        sa.Column('ordered_quantity', sa.Numeric(18, 4), nullable=False),
        sa.Column('received_quantity', sa.Numeric(18, 4), nullable=False, server_default=sa.literal_column('0')),
        sa.Column('expected_delivery_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.literal_column("'PENDING'")),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['purchase_order_id'], ['purchase_orders.id'],
            ondelete='CASCADE', name='fk_purchase_order_lines_po_id',
        ),
        sa.ForeignKeyConstraint(
            ['component_id'], ['components.id'],
            ondelete='CASCADE', name='fk_purchase_order_lines_component_id',
        ),
    )
    op.create_index('idx_purchase_order_lines_po_id', 'purchase_order_lines', ['purchase_order_id'])
    op.create_index('idx_purchase_order_lines_component_id', 'purchase_order_lines', ['component_id'])
    op.create_index(
        'idx_purchase_order_lines_expected_delivery_date',
        'purchase_order_lines',
        ['expected_delivery_date'],
    )

    # ──────────────────────────────────────────────────────────
    # production_order_requirements — demand lines (denormalized BOM × WO.qty)
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'production_order_requirements',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('production_order_id', sa.UUID(), nullable=False),
        sa.Column('component_id', sa.UUID(), nullable=False),
        sa.Column('required_quantity', sa.Numeric(18, 4), nullable=False),
        sa.Column('reserved_quantity', sa.Numeric(18, 4), nullable=False, server_default=sa.literal_column('0')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['production_order_id'], ['production_orders.id'],
            ondelete='CASCADE', name='fk_production_order_requirements_order_id',
        ),
        sa.ForeignKeyConstraint(
            ['component_id'], ['components.id'],
            ondelete='CASCADE', name='fk_production_order_requirements_component_id',
        ),
    )
    op.create_index(
        'idx_production_order_requirements_order_id',
        'production_order_requirements',
        ['production_order_id'],
    )
    op.create_index(
        'idx_production_order_requirements_component_id',
        'production_order_requirements',
        ['component_id'],
    )

    # ──────────────────────────────────────────────────────────
    # component_alternatives — structural proposed/approved/rejected substitutes
    # ──────────────────────────────────────────────────────────
    op.create_table(
        'component_alternatives',
        sa.Column('id', sa.UUID(), server_default=sa.func.gen_random_uuid(), nullable=False),
        sa.Column('component_id', sa.UUID(), nullable=False),
        sa.Column('alternative_component_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.literal_column("'PROPOSED'")),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['component_id'], ['components.id'],
            ondelete='CASCADE', name='fk_component_alternatives_component_id',
        ),
        sa.ForeignKeyConstraint(
            ['alternative_component_id'], ['components.id'],
            ondelete='CASCADE', name='fk_component_alternatives_alt_component_id',
        ),
    )
    op.create_index(
        'idx_component_alternatives_comp_alt',
        'component_alternatives',
        ['component_id', 'alternative_component_id'],
        unique=True,
    )


def downgrade() -> None:
    """Remove all 14 Phase 2 business tables in reverse dependency order."""

    # component_alternatives (depends on components)
    op.drop_index('idx_component_alternatives_comp_alt', table_name='component_alternatives')
    op.drop_table('component_alternatives')

    # production_order_requirements (depends on production_orders, components)
    op.drop_index('idx_production_order_requirements_component_id', table_name='production_order_requirements')
    op.drop_index('idx_production_order_requirements_order_id', table_name='production_order_requirements')
    op.drop_table('production_order_requirements')

    # purchase_order_lines (depends on purchase_orders, components)
    op.drop_index('idx_purchase_order_lines_expected_delivery_date', table_name='purchase_order_lines')
    op.drop_index('idx_purchase_order_lines_component_id', table_name='purchase_order_lines')
    op.drop_index('idx_purchase_order_lines_po_id', table_name='purchase_order_lines')
    op.drop_table('purchase_order_lines')

    # purchase_orders (depends on suppliers)
    op.drop_index('idx_purchase_orders_placed_at', table_name='purchase_orders')
    op.drop_index('idx_purchase_orders_supplier_id', table_name='purchase_orders')
    op.drop_index('idx_purchase_orders_po_number', table_name='purchase_orders')
    op.drop_table('purchase_orders')

    # suppliers
    op.drop_index('idx_suppliers_code', table_name='suppliers')
    op.drop_table('suppliers')

    # inventory_reservations (depends on components, warehouses, production_orders)
    op.drop_index('idx_inventory_reservations_comp_wo', table_name='inventory_reservations')
    op.drop_table('inventory_reservations')

    # inventory_balances (depends on components, warehouses)
    op.drop_index('idx_inventory_balances_comp_wh', table_name='inventory_balances')
    op.drop_table('inventory_balances')

    # production_orders (depends on production_plans, product_versions)
    op.drop_index('idx_production_orders_need_date', table_name='production_orders')
    op.drop_index('idx_production_orders_product_version_id', table_name='production_orders')
    op.drop_index('idx_production_orders_plan_id', table_name='production_orders')
    op.drop_index('idx_production_orders_code', table_name='production_orders')
    op.drop_table('production_orders')

    # production_plans
    op.drop_index('idx_production_plans_period', table_name='production_plans')
    op.drop_index('idx_production_plans_code', table_name='production_plans')
    op.drop_table('production_plans')

    # warehouses
    op.drop_index('idx_warehouses_code', table_name='warehouses')
    op.drop_table('warehouses')

    # bom_items (depends on product_versions, components)
    op.drop_index('idx_bom_items_product_version_id_component_id', table_name='bom_items')
    op.drop_table('bom_items')

    # components
    op.drop_index('idx_components_code', table_name='components')
    op.drop_table('components')

    # product_versions (depends on products)
    op.drop_index('idx_product_versions_product_id_version', table_name='product_versions')
    op.drop_table('product_versions')

    # products
    op.drop_index('idx_products_code', table_name='products')
    op.drop_table('products')
