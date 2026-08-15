"""add procurement tasks table (WP-REC-04C)

Revision ID: d00f71c78f67
Revises: 3e619e551708
Create Date: 2026-08-15 21:09:02.160277

Creates the ``procurement_tasks`` table — the synthetic, deterministic
local controlled-action record created exactly once from an ``APPROVED``
approval request (WP-REC-04-DEC §4 WP-REC-04C; DEC-052 G2/G3).

Contract:

- Stable UUID identity (server-generated).
- Correlation ID: UUID v4 reused from the source approval request (not a
  foreign key).
- ``approval_request_id``: FK to ``approval_requests.id`` (RESTRICT) and
  UNIQUE — at most one task per approval (decomposition §3.10).
- Provenance: FK to ``recommendations.id`` (RESTRICT) and
  ``workflow_runs.id`` (RESTRICT); ``risk_id`` business string.
- ``action_type`` CHECK-constrained to ``CREATE_PROCUREMENT_TASK`` (the
  MVP's only controlled action; identical to the 04A allow-list).
- ``component_code`` and ``quantity`` are the immutable approved action
  parameters re-read from the 04A ``action_snapshot`` (never recomputed,
  never client-controlled). ``quantity`` is CHECK-constrained ``> 0``.
- ``binding_hash``: the approved SHA-256 binding hash (provenance for
  AT-012 traceability).
- ``task_state`` CHECK-constrained to ``CREATED`` (single deterministic
  synthetic state; no further lifecycle).
- ``requested_by``/``requested_by_username`` and
  ``approved_by``/``approved_by_username``: requester and approver
  identities with immutable username snapshots.
- ``created_at``: backend/database-controlled creation timestamp.

Contains no vendor, supplier, price, amount, currency, payment,
bank/account, external ERP identifier, provider prompt, or secret.

Downgrade drops the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d00f71c78f67"
down_revision: str | Sequence[str] | None = "3e619e551708"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``procurement_tasks`` table."""
    op.create_table(
        "procurement_tasks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "correlation_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="UUID v4 correlation ID reused from the approval request",
        ),
        sa.Column(
            "approval_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("approval_requests.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Source approval request (exactly one task per approval)",
        ),
        sa.Column(
            "recommendation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("recommendations.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Authoritative recommendation provenance",
        ),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Originating workflow run",
        ),
        sa.Column(
            "risk_id",
            sa.String(100),
            nullable=False,
            comment="Originating risk identifier (e.g. RISK-001)",
        ),
        sa.Column(
            "action_type",
            sa.String(50),
            nullable=False,
            comment="Bound action type (CREATE_PROCUREMENT_TASK)",
        ),
        sa.Column(
            "component_code",
            sa.String(100),
            nullable=False,
            comment="Approved component/item identity (immutable)",
        ),
        sa.Column(
            "quantity",
            sa.Numeric(18, 4),
            nullable=False,
            comment="Approved positive quantity (immutable)",
        ),
        sa.Column(
            "binding_hash",
            sa.String(64),
            nullable=False,
            comment="Approved SHA-256 binding hash (provenance)",
        ),
        sa.Column(
            "task_state",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'CREATED'"),
            comment="Synthetic task state (CREATED)",
        ),
        sa.Column(
            "requested_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Requester user UUID",
        ),
        sa.Column(
            "requested_by_username",
            sa.String(100),
            nullable=False,
            comment="Immutable requester username snapshot",
        ),
        sa.Column(
            "approved_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Approver/decision actor user UUID",
        ),
        sa.Column(
            "approved_by_username",
            sa.String(100),
            nullable=False,
            comment="Immutable approver username snapshot",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Backend-controlled creation timestamp",
        ),
        sa.CheckConstraint(
            "action_type IN ('CREATE_PROCUREMENT_TASK')",
            name="ck_procurement_tasks_action_type",
        ),
        sa.CheckConstraint(
            "task_state IN ('CREATED')",
            name="ck_procurement_tasks_task_state",
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_procurement_tasks_quantity_positive",
        ),
        sa.UniqueConstraint(
            "approval_request_id",
            name="uq_procurement_tasks_approval_request_id",
        ),
        sa.Index("idx_procurement_tasks_correlation_id", "correlation_id"),
        sa.Index("idx_procurement_tasks_recommendation_id", "recommendation_id"),
        sa.Index("idx_procurement_tasks_workflow_run_id", "workflow_run_id"),
        sa.Index("idx_procurement_tasks_risk_id", "risk_id"),
        sa.Index("idx_procurement_tasks_requested_by", "requested_by"),
        sa.Index("idx_procurement_tasks_approved_by", "approved_by"),
        sa.Index(
            "idx_procurement_tasks_created_at",
            "created_at",
            postgresql_using="btree",
            postgresql_ops={"created_at": "DESC"},
        ),
        comment="Synthetic procurement-task records (WP-REC-04C)",
    )


def downgrade() -> None:
    """Drop the ``procurement_tasks`` table."""
    op.drop_table("procurement_tasks")
