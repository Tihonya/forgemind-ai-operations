"""ORM models package.

Re-exports the domain models so they are registered with Base.metadata
for Alembic autogenerate discovery.
"""

from app.models.component import BomItem, Component, ComponentAlternative
from app.models.diagnostic import DiagnosticJob
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.enums import (
    ComponentAlternativeStatus,
    ComponentUnit,
    DocumentVersionStatus,
    ProductionOrderStatus,
    ProductionPlanStatus,
    ProductVersionStatus,
    PurchaseOrderLineStatus,
    PurchaseOrderStatus,
)
from app.models.knowledge import KnowledgeChunk
from app.models.product import Product, ProductVersion
from app.models.production import (
    ProductionOrder,
    ProductionOrderRequirement,
    ProductionPlan,
)
from app.models.supplier import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.user import Role, User, UserRole
from app.models.warehouse import InventoryBalance, InventoryReservation, Warehouse

__all__ = [
    # Diagnostic (Phase 1)
    "DiagnosticJob",
    # Products
    "Product",
    "ProductVersion",
    "ProductVersionStatus",
    # Components
    "Component",
    "ComponentUnit",
    "BomItem",
    "ComponentAlternative",
    "ComponentAlternativeStatus",
    # Warehouses and inventory
    "Warehouse",
    "InventoryBalance",
    "InventoryReservation",
    # Suppliers and purchase orders
    "Supplier",
    "PurchaseOrder",
    "PurchaseOrderStatus",
    "PurchaseOrderLine",
    "PurchaseOrderLineStatus",
    # Production
    "ProductionPlan",
    "ProductionPlanStatus",
    "ProductionOrder",
    "ProductionOrderStatus",
    "ProductionOrderRequirement",
    # Authentication (WP-2.5)
    "Role",
    "User",
    "UserRole",
    # Document management (WP-4.1)
    "Document",
    "DocumentVersion",
    "DocumentVersionStatus",
    "DocumentPermission",
    # Knowledge chunks (WP-4.2)
    "KnowledgeChunk",
]
