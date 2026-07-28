"""Add document schema for Phase 4

Revision ID: a1b2c3d4e5f6
Revises: b4c5a6b7c8d9
Create Date: 2026-01-21 00:00:00.000000

This migration adds the document metadata schema for Phase 4
(Knowledge & RAG). Creates three tables: documents,
document_versions, and document_permissions.

Schema:
- documents: id (UUID PK), title (String(500), NOT NULL),
  description (Text, NULL), created_at (DateTime,
  server_default=now()), updated_at (DateTime,
  server_default=now())
- document_versions: id (UUID PK), document_id (UUID FK ->
  documents.id, ON DELETE CASCADE, NOT NULL), version_number
  (String(50), NOT NULL), status (String(20) storing DocumentVersionStatus values,
  NOT NULL), content_hash (String(64), NULL), created_at
  (DateTime, server_default=now())
- document_permissions: id (UUID PK), document_id (UUID FK ->
  documents.id, ON DELETE CASCADE, NOT NULL), role_id
  (UUID FK -> roles.id, ON DELETE CASCADE, NOT NULL)
- Unique constraint: (document_id, role_id) on document_permissions
- Indexes: idx_document_versions_document_id,
  idx_document_permissions_document_id,
  idx_document_permissions_role_id
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "b4c5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create documents table
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create document_versions table
    op.create_table(
        "document_versions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("version_number", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_document_versions_document_id",
        "document_versions",
        ["document_id"],
        unique=False,
    )

    # Create document_permissions table
    op.create_table(
        "document_permissions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["role_id"], ["roles.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "role_id",
            name="uq_document_permissions_document_role",
        ),
    )
    op.create_index(
        "idx_document_permissions_document_id",
        "document_permissions",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "idx_document_permissions_role_id",
        "document_permissions",
        ["role_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_document_permissions_role_id", table_name="document_permissions")
    op.drop_index("idx_document_permissions_document_id", table_name="document_permissions")
    op.drop_table("document_permissions")
    op.drop_index("idx_document_versions_document_id", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_table("documents")
