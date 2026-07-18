"""Enumeration types for business domain models.

These enums define the valid status values and categorical fields
used across the Phase 2 business schema entities.
"""

import enum


class ProductVersionStatus(enum.StrEnum):
    """Status lifecycle for product versions."""

    DRAFT = "DRAFT"
    RELEASED = "RELEASED"
    OBSOLETE = "OBSOLETE"


class ComponentUnit(enum.StrEnum):
    """Unit of measure for components."""

    PCS = "PCS"  # Pieces
    KG = "KG"  # Kilograms
    M = "M"  # Meters
    L = "L"  # Liters


class PurchaseOrderStatus(enum.StrEnum):
    """Status lifecycle for purchase order headers."""

    PLACED = "PLACED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    RECEIVED = "RECEIVED"


class PurchaseOrderLineStatus(enum.StrEnum):
    """Status lifecycle for purchase order lines.

    Note: DELIVERED is a line status only, not a header status.
    RECEIVED is a header status only, not a line status.
    """

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class ProductionPlanStatus(enum.StrEnum):
    """Status lifecycle for production plans."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"


class ProductionOrderStatus(enum.StrEnum):
    """Status lifecycle for production orders (work orders)."""

    PLANNED = "PLANNED"
    RELEASED = "RELEASED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ComponentAlternativeStatus(enum.StrEnum):
    """Approval status for component alternatives."""

    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
