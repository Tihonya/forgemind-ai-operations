"""add approval requests table (WP-REC-04A)

Revision ID: 3e619e551708
Revises: bf6f888442e9
Create Date: 2026-08-15 17:30:00.000000

Creates the ``approval_requests`` table — the Phase 6 approval-request
record and single-shot ``PENDING → APPROVED | REJECTED`` state machine
(WP-REC-04-DEC §3.7, §4 WP-REC-04A; DEC-052 G1/G3).

Contract:
- Stable UUID identity (server-generated).
- Correlation ID: UUID v4, not a foreign key.
- Authoritative recommendation linkage (FK to ``recommendations.id``,
  RESTRICT) plus a denormalized workflow-run linkage (FK to
  ``workflow_runs.id``, RESTRICT) validated to match the recommendation
  at creation time.
- ``risk_id``: business risk identifier (string, not a FK).
- ``action_type``: the bound action type (bounded to
  ``CREATE_PROCUREMENT_TASK`` by the service — the MVP's only controlled
  action; 04C's allow-list is identical).
- ``action_snapshot``: immutable canonical action snapshot (JSONB,
  ordered fields only — no secrets).
- ``binding_hash``: SHA-256 hex over the canonical action serialization
  (deterministic, insertion-order independent).
- ``requested_by``/``requested_by_username``: requester identity and an
  immutable username snapshot.
- ``status``: CHECK-constrained ``PENDING | APPROVED | REJECTED``.
- ``decided_by``/``decided_by_username``/``decided_at``/
  ``decision_comment``: decision actor, snapshot, timestamp, and the
  approval comment (approve) or rejection reason (reject). A terminal
  status requires all four decision fields; PENDING requires them all
  NULL (``ck_approval_requests_terminal_fields``).
- ``requested_at``: backend/database-controlled creation timestamp.

A partial unique index on ``(recommendation_id, risk_id, action_type)``
where ``status = 'PENDING'`` prevents duplicate active approval requests
for the same action. Terminal transitions are serialized at the
service/API boundary (row locking + status guard), not by a database
trigger.

Downgrade drops the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3e619e551708"
down_revision: str | Sequence[str] | None = "bf6f888442e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the ``approval_requests`` table."""
    op.create_table(
        "approval_requests",
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
            comment="UUID v4 correlation ID (not a foreign key)",
        ),
        sa.Column(
            "recommendation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("recommendations.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Authoritative recommendation this approval binds",
        ),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Workflow run linkage (validated to match recommendation)",
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
            "action_snapshot",
            JSONB(),
            nullable=False,
            comment="Immutable canonical action snapshot (no secrets)",
        ),
        sa.Column(
            "binding_hash",
            sa.String(64),
            nullable=False,
            comment="SHA-256 hex over the canonical action serialization",
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
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'PENDING'"),
            comment="Approval status: PENDING, APPROVED, REJECTED",
        ),
        sa.Column(
            "decided_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
            comment="Decision actor user UUID (null while PENDING)",
        ),
        sa.Column(
            "decided_by_username",
            sa.String(100),
            nullable=True,
            comment="Decision actor username snapshot",
        ),
        sa.Column(
            "decision_comment",
            sa.Text(),
            nullable=True,
            comment="Approval comment (approve) or rejection reason (reject)",
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Backend-controlled creation timestamp",
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Backend-controlled decision timestamp",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_approval_requests_status",
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND decided_by IS NULL AND "
            "decided_by_username IS NULL AND decided_at IS NULL AND "
            "decision_comment IS NULL) OR "
            "(status IN ('APPROVED', 'REJECTED') AND decided_by IS NOT NULL "
            "AND decided_by_username IS NOT NULL AND decided_at IS NOT NULL "
            "AND decision_comment IS NOT NULL)",
            name="ck_approval_requests_terminal_fields",
        ),
        sa.Index("idx_approval_requests_correlation_id", "correlation_id"),
        sa.Index("idx_approval_requests_recommendation_id", "recommendation_id"),
        sa.Index("idx_approval_requests_workflow_run_id", "workflow_run_id"),
        sa.Index("idx_approval_requests_requested_by", "requested_by"),
        sa.Index("idx_approval_requests_status", "status"),
        sa.Index(
            "idx_approval_requests_requested_at",
            "requested_at",
            postgresql_using="btree",
            postgresql_ops={"requested_at": "DESC"},
        ),
        sa.Index(
            "uq_approval_requests_active_action",
            "recommendation_id",
            "risk_id",
            "action_type",
            unique=True,
            postgresql_where=sa.text("status = 'PENDING'"),
        ),
        comment="Approval-request records (WP-REC-04A)",
    )


def downgrade() -> None:
    """Drop the ``approval_requests`` table."""
    op.drop_table("approval_requests")
