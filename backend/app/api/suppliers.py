"""Suppliers API router for WP-2.7B.

Endpoints:
- GET /api/v1/suppliers
- GET /api/v1/suppliers/{code}

Notes:
- List ordering: by ``code`` ascending (stable natural key).
- Detail endpoint returns supplier fields + nested purchase orders.
- Purchase orders ordered by placed_at DESC, then po_number ASC.

WP-2.7B scope: read-only, no auth/rbac restriction, pagination via
``limit``/``offset``. Decimal quantities serialized as strings.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.models import PurchaseOrder, Supplier
from app.schemas.supplier import (
    PurchaseOrderInSupplier,
    SupplierDetail,
    SupplierListResponse,
    SupplierSummary,
)

router = APIRouter(tags=["Suppliers"])


# ---------------------------------------------------------------------------
# List / Detail
# ---------------------------------------------------------------------------


@router.get(
    "/suppliers",
    response_model=SupplierListResponse,
    status_code=http_status.HTTP_200_OK,
)
async def list_suppliers(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_async_session),
) -> SupplierListResponse:
    """Return suppliers ordered by ``code`` with pagination."""
    total_stmt = select(func.count()).select_from(Supplier)
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(Supplier)
        .order_by(Supplier.code.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = [SupplierSummary(code=s.code, name=s.name) for s in rows]
    return SupplierListResponse(items=items, limit=limit, offset=offset, total=total)


@router.get(
    "/suppliers/{code}",
    response_model=SupplierDetail,
    status_code=http_status.HTTP_200_OK,
)
async def get_supplier(
    code: str,
    session: AsyncSession = Depends(get_async_session),
) -> SupplierDetail:
    """Return a supplier with nested purchase orders."""
    stmt = (
        select(Supplier)
        .options(selectinload(Supplier.purchase_orders))
        .options(
            selectinload(Supplier.purchase_orders).selectinload(PurchaseOrder.lines)
        )
        .where(Supplier.code == code)
    )
    supplier = (await session.execute(stmt)).scalars().one_or_none()
    if supplier is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={"error": "supplier_not_found", "code": code},
        )

    # Sort purchase orders by placed_at DESC, then po_number ASC
    pos_sorted = sorted(
        supplier.purchase_orders,
        key=lambda po: (-po.placed_at.timestamp(), po.po_number),
    )

    purchase_orders = []
    for po in pos_sorted:
        # Calculate total lines and total ordered quantity
        total_lines = len(po.lines)
        total_ordered_quantity = sum(
            (line.ordered_quantity for line in po.lines),
            Decimal("0"),
        )
        purchase_orders.append(
            PurchaseOrderInSupplier(
                po_number=po.po_number,
                status=po.status,
                placed_at=po.placed_at,
                total_lines=total_lines,
                total_ordered_quantity=total_ordered_quantity,
            )
        )

    return SupplierDetail(
        code=supplier.code, name=supplier.name, purchase_orders=purchase_orders
    )
