"""Warehouse API router for WP-2.7B.

Endpoints:
- GET /api/v1/warehouses
- GET /api/v1/warehouses/{code}

Notes:
- List ordering: by ``code`` ascending (stable natural key).
- Detail endpoint returns warehouse fields + ordered inventory balances.
- Inventory balances ordered by component code ascending.

WP-2.7B scope: read-only, no auth/rbac restriction, pagination via
``limit``/``offset``. Decimal quantities serialized as strings.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.models import InventoryBalance, Warehouse
from app.schemas.warehouse import (
    InventoryBalanceInWarehouse,
    WarehouseDetail,
    WarehouseListResponse,
    WarehouseSummary,
)

router = APIRouter(tags=["Warehouses"])


# ---------------------------------------------------------------------------
# List / Detail
# ---------------------------------------------------------------------------


@router.get(
    "/warehouses",
    response_model=WarehouseListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_warehouses(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_async_session),
) -> WarehouseListResponse:
    """Return warehouses ordered by ``code`` with pagination."""
    total_stmt = select(func.count()).select_from(Warehouse)
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(Warehouse)
        .order_by(Warehouse.code.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = [
        WarehouseSummary(code=w.code, name=w.name) for w in rows
    ]
    return WarehouseListResponse(items=items, limit=limit, offset=offset, total=total)


@router.get(
    "/warehouses/{code}",
    response_model=WarehouseDetail,
    status_code=status.HTTP_200_OK,
)
async def get_warehouse(
    code: str,
    session: AsyncSession = Depends(get_async_session),
) -> WarehouseDetail:
    """Return a warehouse with inventory balances ordered by component code."""
    stmt = (
        select(Warehouse)
        .options(selectinload(Warehouse.inventory_balances))
        .options(
            selectinload(Warehouse.inventory_balances).selectinload(
                InventoryBalance.component
            )
        )
        .where(Warehouse.code == code)
    )
    warehouse = (await session.execute(stmt)).scalars().one_or_none()
    if warehouse is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "warehouse_not_found", "code": code},
        )

    # Sort inventory balances by component code ascending
    balances_sorted = sorted(
        warehouse.inventory_balances,
        key=lambda b: b.component.code,
    )
    balances = [
        InventoryBalanceInWarehouse(
            component_code=b.component.code,
            quantity_on_hand=b.quantity_on_hand,
        )
        for b in balances_sorted
    ]
    return WarehouseDetail(code=warehouse.code, name=warehouse.name, inventory_balances=balances)
