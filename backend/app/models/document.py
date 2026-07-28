"""Document metadata ORM models.

Document management data foundation (WP-4.1). Defines the core schema
for documents, versioning, and access permissions. Document content
is stored directly in the DocumentVersion.content column for RAG
processing. AI logic belongs to later work packages.
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import Role


class Document(Base):
    """ORM representation of the ``documents`` table.

    Top-level document entity. Each document can have multiple versions
    and multiple permission records.
    """

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    title: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    permissions: Mapped[list["DocumentPermission"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )


class DocumentVersion(Base):
    """ORM representation of the ``document_versions`` table.

    Tracks individual versions of a document with lifecycle status.
    """

    __tablename__ = "document_versions"
    __table_args__ = (
        Index("idx_document_versions_document_id", "document_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    version_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    content: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        back_populates="versions",
    )


class DocumentPermission(Base):
    """ORM representation of the ``document_permissions`` table.

    Controls which roles can access which documents. Implements
    document-level access control for RAG filtering.
    """

    __tablename__ = "document_permissions"
    __table_args__ = (
        Index(
            "idx_document_permissions_document_id_role_id",
            "document_id",
            "role_id",
            unique=True,
        ),
        Index("idx_document_permissions_document_id", "document_id"),
        Index("idx_document_permissions_role_id", "role_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )

    role_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Relationships
    document: Mapped["Document"] = relationship(
        back_populates="permissions",
    )

    role: Mapped["Role"] = relationship(
        lazy="select",
    )
