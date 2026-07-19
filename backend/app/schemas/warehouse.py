"""Warehouse and inventory balance schemas for WP-2.7B.

Defines request/response schemas for:
- GET /api/v1/warehouses
- GET /api/v1/warehouses/{code}

Decimal convention: all quantities serialized as plain decimal strings.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Decimal values serialized as plain string in JSON responses (never floats).
DecimalStr = Annotated[Decimal, PlainSerializer(str, return_type=str)]


class WarehouseSummary(BaseModel):
    """Warehouse summary for list endpoints.

    Attributes:
        code: Natural business identifier (e.g., WH-MAIN).
        name: Human-readable warehouse name.
    """

    code: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class InventoryBalanceInWarehouse(BaseModel):
    """Inventory balance for a component within a warehouse detail response.

    Attributes:
        component_code: Natural business identifier of the component.
        quantity_on_hand: Current stock level.
    """

    component_code: str
    quantity_on_hand: DecimalStr

    model_config = ConfigDict(from_attributes=True)


class WarehouseDetail(BaseModel):
    """Warehouse detail with inventory balances.

    Constructed explicitly in the router (``inventory_balances`` is derived).
    """

    code: str
    name: str
    inventory_balances: list[InventoryBalanceInWarehouse]


class WarehouseListResponse(BaseModel):
    """Paginated list of warehouses.

    Attributes:
        items: Warehouse summaries ordered by ``code``.
        limit: Requested limit.
        offset: Requested offset.
        total: Total number of warehouses.
    """

    items: list[WarehouseSummary]
    limit: int
    offset: int
    total: int


__all__ = [
    "DecimalStr",
    "InventoryBalanceInWarehouse",
    "WarehouseDetail",
    "WarehouseListResponse",
    "WarehouseSummary",
]
