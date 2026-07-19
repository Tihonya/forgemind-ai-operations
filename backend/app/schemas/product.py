"""Product and product version Pydantic schemas for WP-2.7A.

Defines request/response schemas for:
- GET /api/v1/products
- GET /api/v1/products/{code}
- GET /api/v1/product-versions/{code}

Decimal convention: all quantities serialized as plain decimal strings.
Date convention: Pydantic serializes ``date`` values as ISO 8601 strings by
default when ``model_dump(mode="json")`` is used, which FastAPI uses.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Decimal values serialized as plain string in JSON responses (never floats).
DecimalStr = Annotated[Decimal, PlainSerializer(str, return_type=str)]


class ProductSummary(BaseModel):
    """Product summary for list endpoints.

    Attributes:
        code: Natural business identifier.
        name: Product name.
        description: Optional product description.
    """

    code: str
    name: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductVersionSummary(BaseModel):
    """Product version summary for nested responses.

    Attributes:
        version: Version string (e.g., "2.1").
        status: Version lifecycle status (enum string).
    """

    version: str
    status: str

    model_config = ConfigDict(from_attributes=True)


class ProductDetail(BaseModel):
    """Product detail with ordered versions.

    Constructed explicitly in the router (``versions`` is derived).
    """

    code: str
    name: str
    description: str | None = None
    versions: list[ProductVersionSummary]


class BomItemSummary(BaseModel):
    """BOM item summary for product version detail.

    Attributes:
        component_code: Natural business identifier of the component.
        quantity_per_unit: Quantity required per unit of product.
    """

    component_code: str
    quantity_per_unit: DecimalStr

    model_config = ConfigDict(from_attributes=True)


class ProductVersionDetail(BaseModel):
    """Product version detail with BOM items.

    Constructed explicitly in the router (``product_code`` and ``bom_items``
    are derived from ORM relationships).
    """

    product_code: str
    version: str
    status: str
    bom_items: list[BomItemSummary]


class ProductListResponse(BaseModel):
    """Paginated list of products.

    Attributes:
        items: Product summaries ordered by ``code``.
        limit: Requested limit.
        offset: Requested offset.
        total: Total number of products.
    """

    items: list[ProductSummary]
    limit: int
    offset: int
    total: int


__all__ = [
    "BomItemSummary",
    "DecimalStr",
    "ProductDetail",
    "ProductListResponse",
    "ProductSummary",
    "ProductVersionDetail",
    "ProductVersionSummary",
]
