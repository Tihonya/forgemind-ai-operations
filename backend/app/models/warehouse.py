"""Warehouse and inventory ORM models.

Warehouses represent physical storage locations. Inventory balances track
current stock levels. Inventory reservations track commitments for production.
"""

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.component import Component
    from app.models.production import ProductionOrder


class Warehouse(Base):
    """Warehouse storage location.

    Represents a physical location where components are stored.

    Fields:
        id: UUID primary key
        code: Natural business identifier (e.g., WH-MAIN, WH-SOUTH)
        name: Human-readable warehouse name

    Relationships:
        inventory_balances: Component quantities stored in this warehouse
        inventory_reservations: Component reservations from this warehouse
    """

    __tablename__ = "warehouses"
    __table_args__ = (
        Index("idx_warehouses_code", "code", unique=True),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    # Relationships
    inventory_balances: Mapped[list["InventoryBalance"]] = relationship(
        back_populates="warehouse",
        cascade="all, delete-orphan",
    )
    inventory_reservations: Mapped[list["InventoryReservation"]] = relationship(
        back_populates="warehouse",
    )


class InventoryBalance(Base):
    """Current stock level for a component in a warehouse.

    Fields:
        id: UUID primary key
        component_id: FK to components
        warehouse_id: FK to warehouses
        quantity_on_hand: Current available quantity

    Constraints:
        Unique: (component_id, warehouse_id) - one balance per component per warehouse

    Relationships:
        component: The component being tracked
        warehouse: The warehouse location
    """

    __tablename__ = "inventory_balances"
    __table_args__ = (
        Index(
            "idx_inventory_balances_comp_wh",
            "component_id",
            "warehouse_id",
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
    warehouse_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity_on_hand: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        server_default="0",
    )

    # Relationships
    component: Mapped["Component"] = relationship(
        back_populates="inventory_balances",
    )
    warehouse: Mapped["Warehouse"] = relationship(
        back_populates="inventory_balances",
    )


class InventoryReservation(Base):
    """Reservation of a component for a production order.

    Reservations represent committed inventory that cannot be used by other
    production orders until released or fulfilled.

    Fields:
        id: UUID primary key
        component_id: FK to components
        warehouse_id: FK to warehouses
        production_order_id: FK to production_orders
        quantity: Quantity reserved

    Relationships:
        component: The component being reserved
        warehouse: The warehouse location
        production_order: The production order this reservation is for
    """

    __tablename__ = "inventory_reservations"
    __table_args__ = (
        Index(
            "idx_inventory_reservations_comp_wo",
            "component_id",
            "warehouse_id",
            "production_order_id",
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
    warehouse_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False,
    )
    production_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("production_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    # Relationships
    component: Mapped["Component"] = relationship(
        back_populates="inventory_reservations",
    )
    warehouse: Mapped["Warehouse"] = relationship(
        back_populates="inventory_reservations",
    )
    production_order: Mapped["ProductionOrder"] = relationship(
        back_populates="inventory_reservations",
    )
