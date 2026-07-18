"""Component, BOM item, and component alternative ORM models.

Components are discrete parts used in production. BOM items link
product versions to components with quantity-per-unit. Component
alternatives track approved or proposed substitute components.
"""

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.product import ProductVersion
    from app.models.production import ProductionOrderRequirement
    from app.models.supplier import PurchaseOrderLine
    from app.models.warehouse import InventoryBalance, InventoryReservation


class Component(Base):
    """ORM representation of the `components` table.

    Discrete components (e.g., CTRL-X4, MOTOR-M2, SENSOR-L9).
    """

    __tablename__ = "components"
    __table_args__ = (
        Index("idx_components_code", "code", unique=True),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    unit: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    bom_items: Mapped[list["BomItem"]] = relationship(
        back_populates="component",
    )

    inventory_balances: Mapped[list["InventoryBalance"]] = relationship(
        back_populates="component",
        cascade="all, delete-orphan",
    )

    inventory_reservations: Mapped[list["InventoryReservation"]] = relationship(
        back_populates="component",
    )

    purchase_order_lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="component",
    )

    production_order_requirements: Mapped[list["ProductionOrderRequirement"]] = relationship(
        back_populates="component",
    )

    alternatives_as_primary: Mapped[list["ComponentAlternative"]] = relationship(
        foreign_keys="ComponentAlternative.component_id",
        back_populates="component",
        cascade="all, delete-orphan",
    )

    alternatives_as_alternate: Mapped[list["ComponentAlternative"]] = relationship(
        foreign_keys="ComponentAlternative.alternative_component_id",
        back_populates="alternative_component",
    )


class BomItem(Base):
    """ORM representation of the `bom_items` table.

    Links a product version to a component with quantity-per-unit.
    Represents one row in a bill of materials.
    """

    __tablename__ = "bom_items"
    __table_args__ = (
        Index(
            "idx_bom_items_product_version_id_component_id",
            "product_version_id",
            "component_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    product_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_versions.id", ondelete="CASCADE"),
        nullable=False,
    )

    component_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )

    quantity_per_unit: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    # Relationships
    product_version: Mapped["ProductVersion"] = relationship(
        back_populates="bom_items",
    )

    component: Mapped["Component"] = relationship(
        back_populates="bom_items",
    )


class ComponentAlternative(Base):
    """ORM representation of the `component_alternatives` table.

    Tracks approved or proposed alternative components for substitution.
    Supports the structural property needed for risk severity calculation.
    """

    __tablename__ = "component_alternatives"
    __table_args__ = (
        Index(
            "idx_component_alternatives_comp_alt",
            "component_id",
            "alternative_component_id",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    component_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )

    alternative_component_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PROPOSED",
        server_default=func.literal("PROPOSED"),
    )

    rationale: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    component: Mapped["Component"] = relationship(
        foreign_keys=[component_id],
        back_populates="alternatives_as_primary",
    )

    alternative_component: Mapped["Component"] = relationship(
        foreign_keys=[alternative_component_id],
        back_populates="alternatives_as_alternate",
    )
