"""Production planning Pydantic schemas for WP-2.7A.

Defines request/response schemas for:
- GET /api/v1/production-plans
- GET /api/v1/production-plans/{code}
- GET /api/v1/production-orders
- GET /api/v1/production-orders/{code}
- GET /api/v1/production-order-requirements

Decimal convention: all quantities serialized as plain decimal strings.
Date convention: Pydantic serializes ``date`` values as ISO 8601 strings by
default when ``model_dump(mode="json")`` is used, which FastAPI uses.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

# Decimal values serialized as plain string in JSON responses (never floats).
DecimalStr = Annotated[Decimal, PlainSerializer(str, return_type=str)]


# ---------------------------------------------------------------------------
# Production plan
# ---------------------------------------------------------------------------


class ProductionOrderSummary(BaseModel):
    """Production order summary for nested responses.

    Constructed explicitly in the router (``product_code`` / ``product_version``
    are derived from ORM relationships).
    """

    code: str
    product_code: str
    product_version: str
    quantity: DecimalStr
    need_date: date
    status: str


class ProductionPlanSummary(BaseModel):
    """Production plan summary for list endpoints."""

    code: str
    status: str
    period_start: date
    period_end: date

    model_config = {"from_attributes": True}


class ProductionPlanDetail(BaseModel):
    """Production plan detail with associated orders.

    Constructed explicitly in the router (``production_orders`` is derived).
    """

    code: str
    status: str
    period_start: date
    period_end: date
    production_orders: list[ProductionOrderSummary]


class ProductionPlanListResponse(BaseModel):
    """Paginated list of production plans.

    Items ordered by ``period_start`` then ``code``.
    """

    items: list[ProductionPlanSummary]
    limit: int
    offset: int
    total: int


# ---------------------------------------------------------------------------
# Production order
# ---------------------------------------------------------------------------


class ProductionOrderRequirementDetail(BaseModel):
    """Requirement used inside production-order detail response.

    The parent order code is implicit and therefore omitted.
    """

    component_code: str
    component_name: str
    required_quantity: DecimalStr
    reserved_quantity: DecimalStr


class ProductionOrderDetail(BaseModel):
    """Production order detail with requirements.

    Constructed explicitly in the router.
    """

    code: str
    plan_code: str
    product_code: str
    product_version: str
    quantity: DecimalStr
    need_date: date
    status: str
    requirements: list[ProductionOrderRequirementDetail]


class ProductionOrderListResponse(BaseModel):
    """Paginated list of production orders.

    Items ordered by ``need_date`` then ``code``.
    """

    items: list[ProductionOrderSummary]
    limit: int
    offset: int
    total: int


# ---------------------------------------------------------------------------
# Production-order requirements (list endpoint)
# ---------------------------------------------------------------------------


class ProductionOrderRequirementSummary(BaseModel):
    """Production-order requirement row for the list endpoint.

    Includes the parent order code so rows from multiple orders are
    distinguishable.

    Note: ``warehouse_code`` is optional. The
    ``production_order_requirements`` table does not reference a warehouse;
    warehouse attribution comes from ``inventory_reservations``. This WP does
    not perform that derivation — ``warehouse_code`` is always ``None`` and
    is reserved for WP-2.7B risk calculation.
    """

    order_code: str
    component_code: str
    required_quantity: DecimalStr
    reserved_quantity: DecimalStr
    warehouse_code: str | None = None


class ProductionOrderRequirementListResponse(BaseModel):
    """List of production-order requirements with pagination.

    Items ordered by ``order_code`` then ``component_code``.
    """

    items: list[ProductionOrderRequirementSummary]
    limit: int
    offset: int
    total: int


__all__ = [
    "DecimalStr",
    "ProductionOrderDetail",
    "ProductionOrderListResponse",
    "ProductionOrderRequirementDetail",
    "ProductionOrderRequirementListResponse",
    "ProductionOrderRequirementSummary",
    "ProductionOrderSummary",
    "ProductionPlanDetail",
    "ProductionPlanListResponse",
    "ProductionPlanSummary",
]
