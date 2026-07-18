"""Supplier, purchase order, and purchase order line ORM models.

Suppliers are named vendors. Purchase orders represent a supplier order
header with status. Purchase order lines represent one line per (PO, component)
with ordered quantity, expected delivery date, and line status.

Convention: RECEIVED is a header status only. DELIVERED is a line status only.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.component import Component


class Supplier(Base):
    """ORM representation of the `suppliers` table.

    Named suppliers/vendors.
    """

    __tablename__ = "suppliers"
    __table_args__ = (
        Index("idx_suppliers_code", "code", unique=True),
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
    purchase_orders: Mapped[list["PurchaseOrder"]] = relationship(
        back_populates="supplier",
        cascade="all, delete-orphan",
    )


class PurchaseOrder(Base):
    """ORM representation of the `purchase_orders` table.

    A purchase order header (supplier, order number, status, placed_at).
    Header status includes RECEIVED but not DELIVERED.
    """

    __tablename__ = "purchase_orders"
    __table_args__ = (
        Index("idx_purchase_orders_po_number", "po_number", unique=True),
        Index("idx_purchase_orders_supplier_id", "supplier_id"),
        Index("idx_purchase_orders_placed_at", "placed_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    supplier_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
    )

    po_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PLACED",
        server_default=func.literal("PLACED"),
    )

    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    supplier: Mapped["Supplier"] = relationship(
        back_populates="purchase_orders",
    )

    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
    )


class PurchaseOrderLine(Base):
    """ORM representation of the `purchase_order_lines` table.

    One line per (PO, component) with ordered quantity, expected delivery
    date, and line status. Line status includes DELIVERED but not RECEIVED.
    """

    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        Index("idx_purchase_order_lines_po_id", "purchase_order_id"),
        Index("idx_purchase_order_lines_component_id", "component_id"),
        Index("idx_purchase_order_lines_expected_delivery_date", "expected_delivery_date"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    purchase_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    component_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("components.id", ondelete="CASCADE"),
        nullable=False,
    )

    ordered_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    received_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        server_default=func.literal("0"),
    )

    expected_delivery_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="PENDING",
        server_default=func.literal("PENDING"),
    )

    # Relationships
    purchase_order: Mapped["PurchaseOrder"] = relationship(
        back_populates="lines",
    )

    component: Mapped["Component"] = relationship(
        back_populates="purchase_order_lines",
    )
