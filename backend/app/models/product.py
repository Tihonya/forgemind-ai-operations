"""Product and product version ORM models.

Products represent top-level finished goods. Product versions represent
distinct releases of a product BOM (bill of materials).
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.component import BomItem
    from app.models.production import ProductionOrder


class Product(Base):
    """ORM representation of the `products` table.

    Top-level finished goods (e.g., "Industrial Pump MK-III").
    """

    __tablename__ = "products"
    __table_args__ = (
        Index("idx_products_code", "code", unique=True),
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

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships (string-based targets to avoid circular imports)
    versions: Mapped[list["ProductVersion"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
    )


class ProductVersion(Base):
    """ORM representation of the `product_versions` table.

    A distinct release of a product BOM. One product may have many versions.
    """

    __tablename__ = "product_versions"
    __table_args__ = (
        Index(
            "idx_product_versions_product_id_version",
            "product_id",
            "version",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )

    version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="DRAFT",
        server_default=func.literal("DRAFT"),
    )

    # Relationships
    product: Mapped["Product"] = relationship(
        back_populates="versions",
    )

    bom_items: Mapped[list["BomItem"]] = relationship(
        back_populates="product_version",
        cascade="all, delete-orphan",
    )

    production_orders: Mapped[list["ProductionOrder"]] = relationship(
        back_populates="product_version",
    )
