"""Components API router for WP-2.7A.

Endpoints:
- GET /api/v1/components
- GET /api/v1/components/{code}

Notes:
- List ordering: by ``code`` ascending (stable natural key).
- Alternatives ordering (inside detail): by ``alternative_code`` ascending.

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
from app.models import Component, ComponentAlternative
from app.schemas.component import (
    ComponentAlternativeSummary,
    ComponentDetail,
    ComponentListResponse,
    ComponentSummary,
)

router = APIRouter(tags=["Components"])


@router.get(
    "/components",
    response_model=ComponentListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_components(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_async_session),
) -> ComponentListResponse:
    """Return components ordered by ``code`` with pagination."""
    total_stmt = select(func.count()).select_from(Component)
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(Component)
        .order_by(Component.code.asc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()

    items = [
        ComponentSummary(
            code=c.code,
            name=c.name,
            unit=c.unit,
            description=c.description,
        )
        for c in rows
    ]
    return ComponentListResponse(items=items, limit=limit, offset=offset, total=total)


@router.get(
    "/components/{code}",
    response_model=ComponentDetail,
    status_code=status.HTTP_200_OK,
)
async def get_component(
    code: str,
    session: AsyncSession = Depends(get_async_session),
) -> ComponentDetail:
    """Return a component and its approved alternatives.

    Alternatives are ordered by ``alternative_code`` ascending (stable
    natural-key ordering).
    """
    stmt = (
        select(Component)
        .options(
            selectinload(Component.alternatives_as_primary).selectinload(
                ComponentAlternative.alternative_component
            )
        )
        .where(Component.code == code)
    )
    component = (await session.execute(stmt)).scalars().unique().one_or_none()
    if component is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "component_not_found", "code": code},
        )

    alternatives_sorted = sorted(
        component.alternatives_as_primary,
        key=lambda a: a.alternative_component.code,
    )
    alternatives = [
        ComponentAlternativeSummary(
            alternative_code=a.alternative_component.code,
            status=a.status,
            rationale=a.rationale,
        )
        for a in alternatives_sorted
    ]
    return ComponentDetail(
        code=component.code,
        name=component.name,
        unit=component.unit,
        description=component.description,
        alternatives=alternatives,
    )
