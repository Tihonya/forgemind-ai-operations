"""Add knowledge_chunks schema for RAG chunk storage

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-07-28 00:00:00.000000

This migration adds the knowledge_chunks table for WP-4.2 (Knowledge
Chunks Schema). It stores text chunks extracted from document versions,
together with vector embeddings for similarity-based RAG retrieval.

Steps:
1. Enable the pgvector extension (required for the Vector column type).
2. Create the knowledge_chunks table with FK to document_versions.
3. Create the btree index on document_version_id.

Schema:
- knowledge_chunks: id (UUID PK), document_version_id (UUID FK ->
  document_versions.id, ON DELETE CASCADE, NOT NULL), chunk_index
  (Integer, zero-based, NOT NULL), chunk_text (Text, NOT NULL),
  token_count (Integer, NULL), metadata (JSONB, NULL),
  content_hash (String(64), NULL), embedding (Vector(1536), NULL),
  created_at (DateTime, server_default=now())
- Unique constraint: (document_version_id, chunk_index)
- Index: ix_knowledge_chunks_document_version_id
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Step 1: Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Step 2: Create knowledge_chunks table
    op.create_table(
        "knowledge_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "chunk_index",
            sa.Integer(),
            nullable=False,
            comment="zero-based",
        ),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_version_id",
            "chunk_index",
            name="uq_knowledge_chunks_document_version_id_chunk_index",
        ),
    )

    # Step 3: Create btree index on document_version_id
    op.create_index(
        "ix_knowledge_chunks_document_version_id",
        "knowledge_chunks",
        ["document_version_id"],
        unique=False,
    )


def downgrade() -> None:
    # Step 1: Drop index
    op.drop_index(
        "ix_knowledge_chunks_document_version_id",
        table_name="knowledge_chunks",
    )

    # Step 2: Drop table
    op.drop_table("knowledge_chunks")

    # Step 3: DO NOT drop vector extension (other tables may need it)
