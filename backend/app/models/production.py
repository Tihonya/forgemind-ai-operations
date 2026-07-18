"""Production planning models.

ProductionPlan: Planning container for work orders with time period
ProductionOrder: Work order producing product versions by due date
ProductionOrderRequirement: Material requirement for work orders
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
    from app.models.product import ProductVersion
    from app.models.warehouse import InventoryReservation


class ProductionPlan(Base):
    """Production plan container for work orders.

    A plan represents a time period (typically weekly) during which
    production orders are scheduled. Plans coordinate production
    activities across multiple work orders.

    Attributes:
        code: Unique plan identifier (e.g., PLAN-2026-W31)
        status: Plan lifecycle state (draft/approved/executing/completed/cancelled)
        period_start: Plan start date (inclusive)
        period_end: Plan end date (inclusive)
    """

    __tablename__ = "production_plans"
    __table_args__ = (
        Index("idx_production_plans_code", "code", unique=True),
        Index("idx_production_plans_period", "period_start", "period_end"),
        {"comment": "Production planning containers for work orders"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    code: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True,
        comment="Unique plan identifier (e.g., PLAN-2026-W31)"
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="DRAFT",
        comment="Plan status: DRAFT, APPROVED, EXECUTING, COMPLETED, CLOSED"
    )

    period_start: Mapped[date] = mapped_column(
        Date, nullable=False,
        comment="Plan period start date (inclusive)"
    )

    period_end: Mapped[date] = mapped_column(
        Date, nullable=False,
        comment="Plan period end date (inclusive)"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        comment="Plan creation timestamp (UTC)"
    )

    # Relationships
    production_orders: Mapped[list["ProductionOrder"]] = relationship(
        back_populates="production_plan", cascade="all, delete-orphan"
    )


class ProductionOrder(Base):
    """Production work order for manufacturing products.

    A work order specifies the production of a specific quantity of a
    product version by a required date. Work orders drive material
    requirements and inventory reservations.

    Attributes:
        code: Unique work order identifier (e.g., WO-001)
        production_plan_id: Parent production plan
        product_version_id: Product version to manufacture
        quantity: Quantity to produce
        need_date: Required completion date
        status: Work order lifecycle state
    """

    __tablename__ = "production_orders"
    __table_args__ = (
        Index("idx_production_orders_code", "code", unique=True),
        Index("idx_production_orders_plan_id", "production_plan_id"),
        Index("idx_production_orders_product_version_id", "product_version_id"),
        Index("idx_production_orders_need_date", "need_date"),
        {"comment": "Production work orders for manufacturing"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    code: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True,
        comment="Unique work order identifier (e.g., WO-001)"
    )

    production_plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("production_plans.id", ondelete="CASCADE"),
        nullable=False,
    )

    product_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("product_versions.id", ondelete="CASCADE"),
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False,
        comment="Quantity to produce"
    )

    need_date: Mapped[date] = mapped_column(
        Date, nullable=False,
        comment="Required completion date"
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PLANNED",
        comment="Work order status: PLANNED, RELEASED, IN_PROGRESS, COMPLETED, CANCELLED"
    )

    # Relationships
    production_plan: Mapped[ProductionPlan] = relationship(
        back_populates="production_orders"
    )

    product_version: Mapped["ProductVersion"] = relationship(
        back_populates="production_orders"
    )

    requirements: Mapped[list["ProductionOrderRequirement"]] = relationship(
        back_populates="production_order", cascade="all, delete-orphan"
    )

    inventory_reservations: Mapped[list["InventoryReservation"]] = relationship(
        back_populates="production_order"
    )


class ProductionOrderRequirement(Base):
    """Material requirement for a production work order.

    A requirement specifies the quantity of a component needed for a
    specific work order. Requirements drive inventory reservations and
    procurement activities.

    Attributes:
        production_order_id: Parent work order
        component_id: Required component
        required_quantity: Quantity needed for this order
        reserved_quantity: Quantity already reserved in inventory
    """

    __tablename__ = "production_order_requirements"
    __table_args__ = (
        Index("idx_production_order_requirements_order_id", "production_order_id"),
        Index("idx_production_order_requirements_component_id", "component_id"),
        {"comment": "Material requirements for production orders"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    production_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("production_orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    component_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("components.id"),
        nullable=False,
    )

    required_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False,
        comment="Quantity required for this work order"
    )

    reserved_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), nullable=False,
        default=Decimal("0"), server_default=func.literal("0"),
        comment="Quantity already reserved in inventory"
    )

    # Relationships
    production_order: Mapped[ProductionOrder] = relationship(
        back_populates="requirements"
    )

    component: Mapped["Component"] = relationship(
        back_populates="production_order_requirements"
    )
