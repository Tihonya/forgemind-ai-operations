"""BOM explosion service.

Expands a production plan's work orders into per-component requirements
by traversing product_version → bom_items → component.

Output is a flat list of (WO, component, required_quantity) tuples suitable
for downstream inventory and supply calculations.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.component import BomItem, Component
from app.models.product import ProductVersion
from app.models.production import ProductionOrder, ProductionPlan


@dataclass(frozen=True)
class BomExplosionRow:
    """One row of a BOM explosion (WO × component).

    Attributes:
        production_order_id: UUID of the work order
        wo_code: Natural work order identifier (e.g. WO-2026-0142)
        need_date: Date when components are needed
        component_id: UUID of the component
        component_code: Natural component identifier (e.g. CTRL-X4)
        component_name: Human-readable component name
        required: Total quantity needed (wo.quantity × bom.quantity_per_unit)
        plan_code: Parent production plan code
    """

    production_order_id: UUID
    wo_code: str
    need_date: date
    component_id: UUID
    component_code: str
    component_name: str
    required: Decimal
    plan_code: str


async def explode_plan(
    session: AsyncSession,
    plan_code: str,
) -> Sequence[BomExplosionRow]:
    """Load a production plan and expand all WOs into component requirements.

    Uses selectinload to traverse the full tree (plan → orders → product_version
    → bom_items → component) in a minimal number of queries, avoiding N+1.

    Args:
        session: Async database session.
        plan_code: Natural identifier of the production plan.

    Returns:
        Sequence of BomExplosionRow, one per (WO, component) combination.

    Raises:
        ValueError: If no plan with the given code exists.
    """
    stmt = (
        select(ProductionPlan)
        .where(ProductionPlan.code == plan_code)
        .options(
            selectinload(ProductionPlan.production_orders)
            .selectinload(ProductionOrder.product_version)
            .selectinload(ProductVersion.bom_items)
            .selectinload(BomItem.component)
        )
    )
    result = await session.execute(stmt)
    plan = result.scalar_one_or_none()
    if plan is None:
        raise ValueError(f"Production plan not found: {plan_code}")

    rows: list[BomExplosionRow] = []
    for wo in plan.production_orders:
        product_version = wo.product_version
        for bom_item in product_version.bom_items:
            component: Component = bom_item.component
            required: Decimal = wo.quantity * bom_item.quantity_per_unit
            rows.append(
                BomExplosionRow(
                    production_order_id=wo.id,
                    wo_code=wo.code,
                    need_date=wo.need_date,
                    component_id=component.id,
                    component_code=component.code,
                    component_name=component.name,
                    required=required,
                    plan_code=plan.code,
                )
            )
    return rows
