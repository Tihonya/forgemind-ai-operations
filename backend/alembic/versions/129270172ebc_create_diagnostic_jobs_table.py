"""create diagnostic jobs table

Revision ID: 129270172ebc
Revises:
Create Date: 2026-07-15 16:45:23.123456

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '129270172ebc'
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create diagnostic_jobs table with all required columns and constraints."""
    # Enable pgcrypto extension for gen_random_uuid()
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')

    op.create_table(
        'diagnostic_jobs',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('correlation_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column('triggered_by', sa.String(100), nullable=True),
        sa.Column('checks', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column(
            'created_at', sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            'updated_at', sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name='ck_diagnostic_jobs_status'
        )
    )

    # Create indexes
    op.create_index('idx_diagnostic_jobs_correlation_id', 'diagnostic_jobs', ['correlation_id'])
    op.create_index(
        'idx_diagnostic_jobs_created_at',
        'diagnostic_jobs',
        ['created_at'],
        postgresql_using='btree',
        postgresql_ops={'created_at': 'DESC'}
    )


def downgrade() -> None:
    """Remove diagnostic_jobs table and indexes safely."""
    # Drop indexes first
    op.drop_index('idx_diagnostic_jobs_created_at', table_name='diagnostic_jobs')
    op.drop_index('idx_diagnostic_jobs_correlation_id', table_name='diagnostic_jobs')

    # Drop table
    op.drop_table('diagnostic_jobs')

    # Do NOT drop pgcrypto extension - it may be shared by other tables
