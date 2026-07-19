"""Purchase order and line schemas for WP-2.7B.

Defines request/response schemas for:
- GET /api/v1/purchase-orders
- GET /api/v1/purchase-orders/{po_number}

Decimal convention: all quantities serialized as plain decimal strings.
Date/datetime convention: Pydantic serializes as ISO 8601 strings.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Decimal values serialized as plain string in JSON responses (never floats).
DecimalStr = Annotated[Decimal, PlainSerializer(str, return_type=str)]


class PurchaseOrderLineSummary(BaseModel):
    """Summary of a PO line.

    Attributes:
        component_code: Component natural business identifier.
        component_name: Component human-readable name.
        ordered_quantity: Quantity ordered.
        received_quantity: Quantity received so far.
        expected_delivery_date: Expected delivery (ISO 8601 date).
        status: Line status (enum string).
    """

    component_code: str
    component_name: str
    ordered_quantity: DecimalStr
    received_quantity: DecimalStr
    expected_delivery_date: date
    status: str

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderSummary(BaseModel):
    """Summary of a purchase order for list endpoints.

    Attributes:
        po_number: PO natural business identifier.
        supplier_code: Supplier natural business identifier.
        status: Header status (enum string).
        placed_at: When the PO was placed (ISO 8601 datetime).
        total_lines: Number of line items in the PO.
        total_ordered_quantity: Sum of ordered quantities.
    """

    po_number: str
    supplier_code: str
    status: str
    placed_at: datetime
    total_lines: int
    total_ordered_quantity: DecimalStr

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderDetail(BaseModel):
    """Purchase order detail with lines.

    Constructed explicitly in the router.
    """

    po_number: str
    supplier_code: str
    status: str
    placed_at: datetime
    lines: list[PurchaseOrderLineSummary]


class PurchaseOrderListResponse(BaseModel):
    """Paginated list of purchase orders.

    Attributes:
        items: PO summaries ordered by placed_at desc, then po_number asc.
        limit: Requested limit.
        offset: Requested offset.
        total: Total number of purchase orders.
    """

    items: list[PurchaseOrderSummary]
    limit: int
    offset: int
    total: int


__all__ = [
    "DecimalStr",
    "PurchaseOrderDetail",
    "PurchaseOrderLineSummary",
    "PurchaseOrderListResponse",
    "PurchaseOrderSummary",
]
