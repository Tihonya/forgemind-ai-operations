"""Products and Product Versions API router for WP-2.7A.

Endpoints:
- GET /api/v1/products
- GET /api/v1/products/{code}
- GET /api/v1/product-versions/{code}

Notes:
- ``GET /product-versions/{code}`` uses the *product* natural code and
  returns the *latest* version of that product (by version string
  descending). Product versions do not have a standalone natural code, so
  the product code is the only stable URL key. Phase 2 has no ``?version``
  override; adding one would be an undocumented filter.
- List ordering: by ``code`` ascending (stable natural key).
- Version ordering (inside product detail): by ``version`` descending.
- BOM ordering (inside product-version detail): by ``component.code`` ascending.

WP-2.7A scope: read-only, no auth/rbac restriction, pagination via
``limit``/``offset``. Decimal quantities serialized as strings.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_async_session
from app.models import BomItem, Product, ProductVersion
from app.schemas.product import (
    BomItemSummary,
    ProductDetail,
    ProductListResponse,
    ProductSummary,
    ProductVersionDetail,
    ProductVersionSummary,
)

router = APIRouter(tags=["Products and Product Versions"])


# ---------------------------------------------------------------------------
# List / Detail
# ---------------------------------------------------------------------------


@router.get("/products", response_model=ProductListResponse, status_code=status.HTTP_200_OK)
async def list_products(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_async_session),
) -> ProductListResponse:
    """Return products ordered by ``code`` with pagination."""
    total_stmt = select(func.count()).select_from(Product)
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(Product)
        .order_by(Product.code.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = [
        ProductSummary(
            code=p.code,
            name=p.name,
            description=p.description,
        )
        for p in rows
    ]
    return ProductListResponse(items=items, limit=limit, offset=offset, total=total)


@router.get(
    "/products/{code}",
    response_model=ProductDetail,
    status_code=status.HTTP_200_OK,
)
async def get_product(
    code: str,
    session: AsyncSession = Depends(get_async_session),
) -> ProductDetail:
    """Return a product with its versions ordered by ``version`` desc."""
    stmt = (
        select(Product)
        .options(selectinload(Product.versions))
        .where(Product.code == code)
    )
    product = (await session.execute(stmt)).scalars().one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "product_not_found", "code": code},
        )

    versions_sorted = sorted(product.versions, key=lambda v: v.version, reverse=True)
    return ProductDetail(
        code=product.code,
        name=product.name,
        description=product.description,
        versions=[
            ProductVersionSummary(version=v.version, status=v.status)
            for v in versions_sorted
        ],
    )


@router.get(
    "/product-versions/{code}",
    response_model=ProductVersionDetail,
    status_code=status.HTTP_200_OK,
)
async def get_product_version(
    code: str,
    session: AsyncSession = Depends(get_async_session),
) -> ProductVersionDetail:
    """Return the *latest* version of a product and its BOM items.

    The URL path uses the *product* natural code. The endpoint returns the
    version with the highest ``version`` string for that product. BomItems
    are ordered by component code (stable natural-key ordering).
    """
    stmt = (
        select(ProductVersion)
        .join(ProductVersion.product)
        .where(Product.code == code)
        .options(selectinload(ProductVersion.product))
        .options(
            selectinload(ProductVersion.bom_items).selectinload(
                BomItem.component
            )
        )
        .order_by(ProductVersion.version.desc())
        .limit(1)
    )
    version = (await session.execute(stmt)).scalars().one_or_none()
    if version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "product_version_not_found", "code": code},
        )

    bom_sorted = sorted(version.bom_items, key=lambda b: b.component.code)
    bom_items = [
        BomItemSummary(
            component_code=b.component.code,
            quantity_per_unit=b.quantity_per_unit,
        )
        for b in bom_sorted
    ]
    return ProductVersionDetail(
        product_code=version.product.code,
        version=version.version,
        status=version.status,
        bom_items=bom_items,
    )
