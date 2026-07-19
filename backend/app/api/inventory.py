"""Inventory API router for WP-2.7B.

Endpoints:
- GET /api/v1/inventory
- GET /api/v1/inventory/{component_code}

Notes:
- List ordering: by component code asc, then warehouse code asc.
- Detail endpoint returns component fields + balances by warehouse + reservations.
- Balances ordered by warehouse code ascending.
- Reservations ordered by order code ascending.

WP-2.7B scope: read-only, no auth/rbac restriction, pagination via
``limit``/``offset``. Decimal quantities serialized as strings.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.models import Component, InventoryBalance, InventoryReservation
from app.models.warehouse import Warehouse
from app.schemas.inventory import (
    InventoryBalanceInDetail,
    InventoryBalanceSummary,
    InventoryDetail,
    InventoryListResponse,
    ReservationInInventoryDetail,
)

router = APIRouter(tags=["Inventory"])


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@router.get(
    "/inventory",
    response_model=InventoryListResponse,
    status_code=http_status.HTTP_200_OK,
)
async def list_inventory(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    warehouse_code: str | None = None,
    component_code: str | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> InventoryListResponse:
    """Return inventory balances ordered by component code then warehouse code."""
    base_query = (
        select(InventoryBalance)
        .join(InventoryBalance.component)
        .join(InventoryBalance.warehouse)
    )

    if warehouse_code is not None:
        base_query = base_query.where(Warehouse.code == warehouse_code)
    if component_code is not None:
        base_query = base_query.where(Component.code == component_code)

    # Count total with filters applied
    total_stmt = (
        select(func.count(InventoryBalance.id))
        .join_from(InventoryBalance, InventoryBalance.component)
        .join_from(InventoryBalance, InventoryBalance.warehouse)
    )
    if warehouse_code is not None:
        total_stmt = total_stmt.where(Warehouse.code == warehouse_code)
    if component_code is not None:
        total_stmt = total_stmt.where(Component.code == component_code)
    total = (await session.execute(total_stmt)).scalar_one()

    # Fetch page with eager-loaded component and warehouse
    stmt = base_query.options(
        selectinload(InventoryBalance.component),
        selectinload(InventoryBalance.warehouse),
    )
    stmt = (
        stmt.order_by(Component.code.asc(), Warehouse.code.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = [
        InventoryBalanceSummary(
            component_code=b.component.code,
            warehouse_code=b.warehouse.code,
            quantity_on_hand=b.quantity_on_hand,
        )
        for b in rows
    ]
    return InventoryListResponse(items=items, limit=limit, offset=offset, total=total)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------


@router.get(
    "/inventory/{component_code}",
    response_model=InventoryDetail,
    status_code=http_status.HTTP_200_OK,
)
async def get_inventory(
    component_code: str,
    session: AsyncSession = Depends(get_async_session),
) -> InventoryDetail:
    """Return component inventory detail with balances and reservations."""
    stmt = (
        select(Component)
        .options(
            selectinload(Component.inventory_balances).selectinload(
                InventoryBalance.warehouse
            )
        )
        .options(
            selectinload(Component.inventory_reservations).selectinload(
                InventoryReservation.warehouse
            )
        )
        .options(
            selectinload(Component.inventory_reservations).selectinload(
                InventoryReservation.production_order
            )
        )
        .where(Component.code == component_code)
    )
    component = (await session.execute(stmt)).scalars().one_or_none()
    if component is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={"error": "component_inventory_not_found", "component_code": component_code},
        )

    # Sort balances by warehouse code ascending
    balances_sorted = sorted(component.inventory_balances, key=lambda b: b.warehouse.code)
    balances = [
        InventoryBalanceInDetail(
            warehouse_code=b.warehouse.code,
            quantity_on_hand=b.quantity_on_hand,
        )
        for b in balances_sorted
    ]

    # Sort reservations by order code ascending, then warehouse code as
    # tiebreaker, then reservation id.
    reservations_sorted = sorted(
        component.inventory_reservations,
        key=lambda r: (r.production_order.code, r.warehouse.code, r.id),
    )
    reservations = [
        ReservationInInventoryDetail(
            order_code=r.production_order.code,
            warehouse_code=r.warehouse.code,
            quantity=r.quantity,
        )
        for r in reservations_sorted
    ]

    return InventoryDetail(
        component_code=component.code,
        component_name=component.name,
        unit=component.unit,
        description=component.description,
        balances=balances,
        reservations=reservations,
    )
