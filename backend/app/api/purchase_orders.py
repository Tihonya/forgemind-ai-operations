"""Purchase orders API router for WP-2.7B.

Endpoints:
- GET /api/v1/purchase-orders
- GET /api/v1/purchase-orders/{po_number}

Notes:
- List ordering: by placed_at DESC, then po_number ASC.
- Filters: optional supplier_code, optional status.
- Detail endpoint returns PO fields + ordered lines.
- Lines ordered by component code ASC.

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
from app.models import PurchaseOrder, PurchaseOrderLine, Supplier
from app.schemas.purchase_order import (
    PurchaseOrderDetail,
    PurchaseOrderLineSummary,
    PurchaseOrderListResponse,
    PurchaseOrderSummary,
)

router = APIRouter(tags=["Purchase Orders"])


# ---------------------------------------------------------------------------
# List / Detail
# ---------------------------------------------------------------------------


@router.get(
    "/purchase-orders",
    response_model=PurchaseOrderListResponse,
    status_code=http_status.HTTP_200_OK,
)
async def list_purchase_orders(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    supplier_code: str | None = None,
    po_status: Annotated[str | None, Query(alias="status")] = None,
    session: AsyncSession = Depends(get_async_session),
) -> PurchaseOrderListResponse:
    """Return purchase orders with pagination and filters."""
    base_query = select(PurchaseOrder).join(PurchaseOrder.supplier)

    if supplier_code is not None:
        base_query = base_query.where(Supplier.code == supplier_code)
    if po_status is not None:
        base_query = base_query.where(PurchaseOrder.status == po_status)

    # Count total with filters applied
    total_stmt = (
        select(func.count(PurchaseOrder.id))
        .join_from(PurchaseOrder, PurchaseOrder.supplier)
    )
    if supplier_code is not None:
        total_stmt = total_stmt.where(Supplier.code == supplier_code)
    if po_status is not None:
        total_stmt = total_stmt.where(PurchaseOrder.status == po_status)
    total = (await session.execute(total_stmt)).scalar_one()

    # Fetch page with eager-loaded relationships
    stmt = base_query.options(
        selectinload(PurchaseOrder.supplier),
        selectinload(PurchaseOrder.lines),
    )
    stmt = (
        stmt.order_by(PurchaseOrder.placed_at.desc(), PurchaseOrder.po_number.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = []
    for po in rows:
        total_lines = len(po.lines)
        total_ordered_quantity = sum(
            (line.ordered_quantity for line in po.lines),
            Decimal("0"),
        )
        items.append(
            PurchaseOrderSummary(
                po_number=po.po_number,
                supplier_code=po.supplier.code,
                status=po.status,
                placed_at=po.placed_at,
                total_lines=total_lines,
                total_ordered_quantity=total_ordered_quantity,
            )
        )
    return PurchaseOrderListResponse(items=items, limit=limit, offset=offset, total=total)


@router.get(
    "/purchase-orders/{po_number}",
    response_model=PurchaseOrderDetail,
    status_code=http_status.HTTP_200_OK,
)
async def get_purchase_order(
    po_number: str,
    session: AsyncSession = Depends(get_async_session),
) -> PurchaseOrderDetail:
    """Return a purchase order with lines."""
    stmt = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.supplier))
        .options(
            selectinload(PurchaseOrder.lines).selectinload(PurchaseOrderLine.component)
        )
        .where(PurchaseOrder.po_number == po_number)
    )
    po = (await session.execute(stmt)).scalars().one_or_none()
    if po is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail={"error": "purchase_order_not_found", "po_number": po_number},
        )

    # Sort lines by component code ascending
    lines_sorted = sorted(po.lines, key=lambda line: line.component.code)
    lines = [
        PurchaseOrderLineSummary(
            component_code=line.component.code,
            component_name=line.component.name,
            ordered_quantity=line.ordered_quantity,
            received_quantity=line.received_quantity,
            expected_delivery_date=line.expected_delivery_date,
            status=line.status,
        )
        for line in lines_sorted
    ]

    return PurchaseOrderDetail(
        po_number=po.po_number,
        supplier_code=po.supplier.code,
        status=po.status,
        placed_at=po.placed_at,
        lines=lines,
    )
