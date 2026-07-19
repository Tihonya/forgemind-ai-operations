"""Production Orders and Requirements API router for WP-2.7A.

Endpoints:
- GET /api/v1/production-orders
- GET /api/v1/production-orders/{code}
- GET /api/v1/production-order-requirements

Notes:
- Orders list ordering: by ``need_date`` ascending then ``code`` ascending.
- Orders detail ``requirements`` ordering: by ``component.code`` ascending.
- Requirements list ordering: by ``component_code`` ascending
  (natural business key, independent of UUID ordering).
- Filter ``plan_code`` on orders list is optional.
- Filter ``order_code`` on requirements list is required.

WP-2.7A scope: read-only, no auth/rbac restriction, pagination via
``limit``/``offset``. Quantity fields serialized as decimal strings.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.models import Component, ProductVersion
from app.models.production import (
    ProductionOrder,
    ProductionOrderRequirement,
    ProductionPlan,
)
from app.schemas.production import (
    ProductionOrderDetail,
    ProductionOrderListResponse,
    ProductionOrderRequirementDetail,
    ProductionOrderRequirementListResponse,
    ProductionOrderRequirementSummary,
    ProductionOrderSummary,
)

router = APIRouter(tags=["Production Orders"])


def _build_order_summary(order: ProductionOrder) -> ProductionOrderSummary:
    pv = order.product_version
    return ProductionOrderSummary(
        code=order.code,
        product_code=pv.product.code,
        product_version=pv.version,
        quantity=order.quantity,
        need_date=order.need_date,
        status=order.status,
    )


@router.get(
    "/production-orders",
    response_model=ProductionOrderListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_production_orders(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    plan_code: str | None = Query(None, description="Optional filter by plan code"),
    session: AsyncSession = Depends(get_async_session),
) -> ProductionOrderListResponse:
    """Return production orders with optional ``plan_code`` filter."""
    base_stmt = select(ProductionOrder).options(
        selectinload(ProductionOrder.product_version)
        .selectinload(ProductVersion.product),
    )
    count_stmt = select(func.count()).select_from(ProductionOrder)

    if plan_code is not None:
        base_stmt = base_stmt.join(ProductionPlan).where(
            ProductionPlan.code == plan_code
        )
        count_stmt = count_stmt.join(ProductionPlan).where(
            ProductionPlan.code == plan_code
        )

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = (
        base_stmt.order_by(ProductionOrder.need_date.asc(), ProductionOrder.code.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().unique().all()

    items = [_build_order_summary(o) for o in rows]
    return ProductionOrderListResponse(items=items, limit=limit, offset=offset, total=total)


@router.get(
    "/production-orders/{code}",
    response_model=ProductionOrderDetail,
    status_code=status.HTTP_200_OK,
)
async def get_production_order(
    code: str,
    session: AsyncSession = Depends(get_async_session),
) -> ProductionOrderDetail:
    """Return a production order with its component requirements."""
    stmt = (
        select(ProductionOrder)
        .options(
            selectinload(ProductionOrder.product_version).selectinload(
                ProductVersion.product
            ),
            selectinload(ProductionOrder.production_plan),
            selectinload(ProductionOrder.requirements).selectinload(
                ProductionOrderRequirement.component
            ),
        )
        .where(ProductionOrder.code == code)
    )
    order = (await session.execute(stmt)).scalars().one_or_none()
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "production_order_not_found", "code": code},
        )

    reqs_sorted = sorted(order.requirements, key=lambda r: r.component.code)
    requirements = [
        ProductionOrderRequirementDetail(
            component_code=r.component.code,
            component_name=r.component.name,
            required_quantity=r.required_quantity,
            reserved_quantity=r.reserved_quantity,
        )
        for r in reqs_sorted
    ]
    return ProductionOrderDetail(
        code=order.code,
        plan_code=order.production_plan.code,
        product_code=order.product_version.product.code,
        product_version=order.product_version.version,
        quantity=order.quantity,
        need_date=order.need_date,
        status=order.status,
        requirements=requirements,
    )


@router.get(
    "/production-order-requirements",
    response_model=ProductionOrderRequirementListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_production_order_requirements(
    order_code: str = Query(..., description="Required parent order code"),
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_async_session),
) -> ProductionOrderRequirementListResponse:
    """Return requirements for a production order.

    ``order_code`` is required. If the order does not exist the result is
    an empty list (the 404 rule applies only to path parameters per the
    WP-2.7A contract).
    """
    base_stmt = select(ProductionOrderRequirement).join(ProductionOrder).where(
        ProductionOrder.code == order_code
    ).options(selectinload(ProductionOrderRequirement.component))

    count_stmt = (
        select(func.count())
        .select_from(ProductionOrderRequirement)
        .join(ProductionOrder)
        .where(ProductionOrder.code == order_code)
    )

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = (
        base_stmt.join(Component)
        .order_by(Component.code.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().unique().all()

    items = [
        ProductionOrderRequirementSummary(
            order_code=order_code,
            component_code=r.component.code,
            required_quantity=r.required_quantity,
            reserved_quantity=r.reserved_quantity,
            warehouse_code=None,
        )
        for r in rows
    ]
    return ProductionOrderRequirementListResponse(
        items=items, limit=limit, offset=offset, total=total
    )
