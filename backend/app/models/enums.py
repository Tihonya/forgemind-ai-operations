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


class DocumentVersionStatus(enum.StrEnum):
    """Status lifecycle for document versions."""

    DRAFT = "DRAFT"
    APPROVED = "APPROVED"
    OBSOLETE = "OBSOLETE"


class AuditEventType(enum.StrEnum):
    """Canonical Phase 6 audit-event taxonomy (WP-REC-04B).

    The bounded set of events the audit foundation must be able to
    persist for later approval (04A) and procurement (04C) integration:
    approval request creation, approval decision, rejection, and
    procurement-task creation attempt and result. Emitting these events
    is the integration responsibility of WP-REC-04A and WP-REC-04C; this
    package only defines and persists them.
    """

    APPROVAL_REQUEST_CREATED = "APPROVAL_REQUEST_CREATED"
    APPROVAL_APPROVED = "APPROVAL_APPROVED"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    PROCUREMENT_TASK_CREATION_ATTEMPTED = "PROCUREMENT_TASK_CREATION_ATTEMPTED"
    PROCUREMENT_TASK_CREATED = "PROCUREMENT_TASK_CREATED"
    PROCUREMENT_TASK_CREATION_FAILED = "PROCUREMENT_TASK_CREATION_FAILED"


class AuditEntityType(enum.StrEnum):
    """Bounded entity-type allow-list for audit events (WP-REC-04B).

    Only the Phase 6 business entities the audit foundation must trace.
    ``entity_id`` is a logical UUID reference (not a foreign key) because
    the approval-request and procurement-task tables are owned by
    WP-REC-04A and WP-REC-04C respectively.
    """

    APPROVAL_REQUEST = "APPROVAL_REQUEST"
    PROCUREMENT_TASK = "PROCUREMENT_TASK"
