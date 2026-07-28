"""add_document_version_content

Revision ID: 625c9f549f2b
Revises: c7d8e9f0a1b2
Create Date: 2026-07-28 17:50:09.728354

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "625c9f549f2b"
down_revision: str | Sequence[str] | None = "c7d8e9f0a1b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add content column to document_versions table."""
    op.add_column(
        "document_versions",
        sa.Column("content", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Drop content column from document_versions table."""
    op.drop_column("document_versions", "content")
