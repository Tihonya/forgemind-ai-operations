"""Inventory reservations API router for WP-2.7B.

Endpoints:
- GET /api/v1/inventory-reservations

Notes:
- List ordering: by component code asc, warehouse code asc, order code asc.
- Filters: optional warehouse_code, component_code, order_code.

WP-2.7B scope: read-only, no auth/rbac restriction, pagination via
``limit``/``offset``. Decimal quantities serialized as strings.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.models import Component, InventoryReservation, ProductionOrder
from app.models.warehouse import Warehouse
from app.schemas.inventory import (
    InventoryReservationListResponse,
    InventoryReservationSummary,
)

router = APIRouter(tags=["Inventory Reservations"])


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "/inventory-reservations",
    response_model=InventoryReservationListResponse,
    status_code=http_status.HTTP_200_OK,
)
async def list_inventory_reservations(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    warehouse_code: str | None = None,
    component_code: str | None = None,
    order_code: str | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> InventoryReservationListResponse:
    """Return inventory reservations with pagination and filters."""
    base_query = (
        select(InventoryReservation)
        .join(InventoryReservation.component)
        .join(InventoryReservation.warehouse)
        .join(InventoryReservation.production_order)
    )

    if warehouse_code is not None:
        base_query = base_query.where(Warehouse.code == warehouse_code)
    if component_code is not None:
        base_query = base_query.where(Component.code == component_code)
    if order_code is not None:
        base_query = base_query.where(ProductionOrder.code == order_code)

    # Count total with filters applied
    total_stmt = (
        select(func.count(InventoryReservation.id))
        .join_from(InventoryReservation, InventoryReservation.component)
        .join_from(InventoryReservation, InventoryReservation.warehouse)
        .join_from(InventoryReservation, InventoryReservation.production_order)
    )
    if warehouse_code is not None:
        total_stmt = total_stmt.where(Warehouse.code == warehouse_code)
    if component_code is not None:
        total_stmt = total_stmt.where(Component.code == component_code)
    if order_code is not None:
        total_stmt = total_stmt.where(ProductionOrder.code == order_code)
    total = (await session.execute(total_stmt)).scalar_one()

    # Fetch page with eager-loaded relationships
    stmt = base_query.options(
        selectinload(InventoryReservation.component),
        selectinload(InventoryReservation.warehouse),
        selectinload(InventoryReservation.production_order),
    )
    stmt = (
        stmt.order_by(
            Component.code.asc(),
            Warehouse.code.asc(),
            ProductionOrder.code.asc(),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = [
        InventoryReservationSummary(
            component_code=r.component.code,
            warehouse_code=r.warehouse.code,
            order_code=r.production_order.code,
            quantity=r.quantity,
        )
        for r in rows
    ]
    return InventoryReservationListResponse(
        items=items, limit=limit, offset=offset, total=total
    )
