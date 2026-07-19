"""Production Plans API router for WP-2.7A.

Endpoints:
- GET /api/v1/production-plans
- GET /api/v1/production-plans/{code}

Notes:
- List ordering: by ``period_start`` ascending then ``code`` ascending.
- Inside plan detail, ``production_orders`` are ordered by ``need_date``
  ascending then ``code`` ascending.

WP-2.7A scope: read-only, no auth/rbac restriction, pagination via
``limit``/``offset``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.models import ProductionOrder, ProductVersion
from app.models.production import ProductionPlan
from app.schemas.production import (
    ProductionOrderSummary,
    ProductionPlanDetail,
    ProductionPlanListResponse,
    ProductionPlanSummary,
)

router = APIRouter(tags=["Production Plans"])


def _build_order_summary(order: ProductionOrder) -> ProductionOrderSummary:
    """Build a ``ProductionOrderSummary`` from an ORM order.

    Product code and version are derived from the
    ``product_version → product`` relationship.
    """
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
    "/production-plans",
    response_model=ProductionPlanListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_production_plans(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_async_session),
) -> ProductionPlanListResponse:
    """Return production plans ordered by period start then code."""
    total_stmt = select(func.count()).select_from(ProductionPlan)
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(ProductionPlan)
        .order_by(ProductionPlan.period_start.asc(), ProductionPlan.code.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = [
        ProductionPlanSummary(
            code=p.code,
            status=p.status,
            period_start=p.period_start,
            period_end=p.period_end,
        )
        for p in rows
    ]
    return ProductionPlanListResponse(items=items, limit=limit, offset=offset, total=total)


@router.get(
    "/production-plans/{code}",
    response_model=ProductionPlanDetail,
    status_code=status.HTTP_200_OK,
)
async def get_production_plan(
    code: str,
    session: AsyncSession = Depends(get_async_session),
) -> ProductionPlanDetail:
    """Return a production plan with its associated orders."""
    stmt = (
        select(ProductionPlan)
        .options(
            selectinload(ProductionPlan.production_orders).options(
                selectinload(ProductionOrder.product_version).selectinload(
                    ProductVersion.product
                )
            )
        )
        .where(ProductionPlan.code == code)
    )
    plan = (await session.execute(stmt)).scalars().one_or_none()
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "production_plan_not_found", "code": code},
        )

    orders_sorted = sorted(
        plan.production_orders,
        key=lambda o: (o.need_date, o.code),
    )
    return ProductionPlanDetail(
        code=plan.code,
        status=plan.status,
        period_start=plan.period_start,
        period_end=plan.period_end,
        production_orders=[_build_order_summary(o) for o in orders_sorted],
    )
