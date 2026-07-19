"""Inventory balance and reservation schemas for WP-2.7B.

Defines request/response schemas for:
- GET /api/v1/inventory
- GET /api/v1/inventory/{component_code}
- GET /api/v1/inventory-reservations

Decimal convention: all quantities serialized as plain decimal strings.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Decimal values serialized as plain string in JSON responses (never floats).
DecimalStr = Annotated[Decimal, PlainSerializer(str, return_type=str)]


class InventoryBalanceSummary(BaseModel):
    """Inventory balance summary for list endpoint.

    Attributes:
        component_code: Component natural business identifier.
        warehouse_code: Warehouse natural business identifier.
        quantity_on_hand: Current stock level.
    """

    component_code: str
    warehouse_code: str
    quantity_on_hand: DecimalStr

    model_config = ConfigDict(from_attributes=True)


class InventoryListResponse(BaseModel):
    """Paginated list of inventory balances.

    Attributes:
        items: Inventory balances ordered by component code, then warehouse code.
        limit: Requested limit.
        offset: Requested offset.
        total: Total number of inventory balances.
    """

    items: list[InventoryBalanceSummary]
    limit: int
    offset: int
    total: int


class InventoryBalanceInDetail(BaseModel):
    """Inventory balance within component detail response.

    Attributes:
        warehouse_code: Warehouse natural business identifier.
        quantity_on_hand: Current stock level in that warehouse.
    """

    warehouse_code: str
    quantity_on_hand: DecimalStr

    model_config = ConfigDict(from_attributes=True)


class ReservationInInventoryDetail(BaseModel):
    """Reservation within component detail response.

    Attributes:
        order_code: Production order code (WO-YYYY-NNNN).
        warehouse_code: Warehouse from which the reservation is allocated.
        quantity: Reserved quantity.
    """

    order_code: str
    warehouse_code: str
    quantity: DecimalStr

    model_config = ConfigDict(from_attributes=True)


class InventoryDetail(BaseModel):
    """Component inventory detail with balances and reservations.

    Constructed explicitly in the router.
    """

    component_code: str
    component_name: str
    unit: str
    description: str | None = None
    balances: list[InventoryBalanceInDetail]
    reservations: list[ReservationInInventoryDetail]


class InventoryReservationSummary(BaseModel):
    """Inventory reservation for list endpoint.

    Attributes:
        component_code: Component natural business identifier.
        warehouse_code: Warehouse natural business identifier.
        order_code: Production order code.
        quantity: Reserved quantity.
    """

    component_code: str
    warehouse_code: str
    order_code: str
    quantity: DecimalStr

    model_config = ConfigDict(from_attributes=True)


class InventoryReservationListResponse(BaseModel):
    """Paginated list of inventory reservations.

    Attributes:
        items: Reservations ordered by component, warehouse, order code.
        limit: Requested limit.
        offset: Requested offset.
        total: Total number of reservations.
    """

    items: list[InventoryReservationSummary]
    limit: int
    offset: int
    total: int


__all__ = [
    "DecimalStr",
    "InventoryBalanceInDetail",
    "InventoryBalanceSummary",
    "InventoryDetail",
    "InventoryListResponse",
    "InventoryReservationListResponse",
    "InventoryReservationSummary",
    "ReservationInInventoryDetail",
]
