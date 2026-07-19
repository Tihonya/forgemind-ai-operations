"""Supplier and purchase order schemas for WP-2.7B.

Defines request/response schemas for:
- GET /api/v1/suppliers
- GET /api/v1/suppliers/{code}

Decimal convention: all quantities serialized as plain decimal strings.
Date/datetime convention: Pydantic serializes as ISO 8601 strings.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Decimal values serialized as plain string in JSON responses (never floats).
DecimalStr = Annotated[Decimal, PlainSerializer(str, return_type=str)]


class SupplierSummary(BaseModel):
    """Supplier summary for list endpoints.

    Attributes:
        code: Natural business identifier (e.g., SUP-ACME).
        name: Supplier name.
    """

    code: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderInSupplier(BaseModel):
    """Purchase order nested within supplier detail.

    Attributes:
        po_number: Purchase order natural business identifier.
        status: Header status (enum string).
        placed_at: When the PO was placed (ISO 8601 datetime).
        total_lines: Number of lines in the PO.
        total_ordered_quantity: Sum of ordered quantities across lines.
    """

    po_number: str
    status: str
    placed_at: datetime
    total_lines: int
    total_ordered_quantity: DecimalStr

    model_config = ConfigDict(from_attributes=True)


class SupplierDetail(BaseModel):
    """Supplier detail with nested purchase orders.

    Constructed explicitly in the router.
    """

    code: str
    name: str
    purchase_orders: list[PurchaseOrderInSupplier]


class SupplierListResponse(BaseModel):
    """Paginated list of suppliers.

    Attributes:
        items: Supplier summaries ordered by ``code``.
        limit: Requested limit.
        offset: Requested offset.
        total: Total number of suppliers.
    """

    items: list[SupplierSummary]
    limit: int
    offset: int
    total: int


__all__ = [
    "DecimalStr",
    "PurchaseOrderInSupplier",
    "SupplierDetail",
    "SupplierListResponse",
    "SupplierSummary",
]
