"""Component Pydantic schemas for WP-2.7A.

Defines request/response schemas for:
- GET /api/v1/components
- GET /api/v1/components/{code}
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ComponentSummary(BaseModel):
    """Component summary for list endpoints.

    Attributes:
        code: Natural business identifier.
        name: Component name.
        unit: Unit of measure (enum string).
        description: Optional component description.
    """

    code: str
    name: str
    unit: str
    description: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ComponentAlternativeSummary(BaseModel):
    """Component alternative summary.

    Constructed explicitly in the router (``alternative_code`` is derived
    from the alternative-component relationship).
    """

    alternative_code: str
    status: str
    rationale: str | None = None


class ComponentDetail(BaseModel):
    """Component detail with approved alternatives.

    Constructed explicitly in the router (``alternatives`` is derived).
    """

    code: str
    name: str
    unit: str
    description: str | None = None
    alternatives: list[ComponentAlternativeSummary]


class ComponentListResponse(BaseModel):
    """Paginated list of components.

    Attributes:
        items: Component summaries ordered by ``code``.
        limit: Requested limit.
        offset: Requested offset.
        total: Total number of components.
    """

    items: list[ComponentSummary]
    limit: int
    offset: int
    total: int


__all__ = [
    "ComponentAlternativeSummary",
    "ComponentDetail",
    "ComponentListResponse",
    "ComponentSummary",
]
