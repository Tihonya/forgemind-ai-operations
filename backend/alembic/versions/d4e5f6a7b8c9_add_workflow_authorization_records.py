"""add workflow authorization records and FAILED_RETRIEVAL state (WP-REC-05 M1/M2)

Revision ID: d4e5f6a7b8c9
Revises: a3b4c5d6e7f8
Create Date: 2026-08-14 12:00:00.000000

This migration implements the WP-REC-05 M1 and M2 database contracts:

M1 — Authorization context (DEC-045):
- Creates the append-only ``workflow_authorization_records`` table keyed by
  ``(run_id, dispatch_generation)`` (unique), carrying the authenticated
  ``user_id``, an immutable ``role_snapshot`` (JSONB list of role-UUID
  strings), the ``capture_action`` boundary (``"start"`` or ``"retry"``),
  and capture timestamps. No mutable role snapshot is added to
  ``workflow_runs``.
- CHECK constraints: ``dispatch_generation >= 0`` and
  ``capture_action IN ('start', 'retry')``.
- Indexes on ``run_id`` and ``user_id``.

M2 — Retrieval failure (DEC-046):
- Extends the ``workflow_runs`` state contract (``ck_workflow_runs_state``)
  with ``FAILED_RETRIEVAL``.

Downgrade removes the table and restores the previous state contract.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | Sequence[str] | None = "a3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# M2: state contract with FAILED_RETRIEVAL (new) vs without (old).
_NEW_STATE_CONSTRAINT = (
    "state IN ('PENDING', 'RUNNING', 'AWAITING_VALIDATION', "
    "'COMPLETED', 'FAILED_VALIDATION', 'FAILED_PROVIDER', "
    "'FAILED_INTERNAL', 'FAILED_RETRIEVAL')"
)
_OLD_STATE_CONSTRAINT = (
    "state IN ('PENDING', 'RUNNING', 'AWAITING_VALIDATION', "
    "'COMPLETED', 'FAILED_VALIDATION', 'FAILED_PROVIDER', "
    "'FAILED_INTERNAL')"
)


def upgrade() -> None:
    """Add FAILED_RETRIEVAL to the state contract and the auth-records table."""

    # M2: extend the workflow_runs state check constraint.
    op.drop_constraint(
        "ck_workflow_runs_state",
        "workflow_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_workflow_runs_state",
        "workflow_runs",
        _NEW_STATE_CONSTRAINT,
    )

    # M1: append-only generation-specific authorization context table.
    op.create_table(
        "workflow_authorization_records",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dispatch_generation",
            sa.Integer(),
            nullable=False,
            comment="Exact dispatch generation this record authorizes",
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
            comment="Authenticated user UUID (User primary-key type)",
        ),
        sa.Column(
            "role_snapshot",
            JSONB(),
            nullable=False,
            comment="Immutable role-UUID snapshot (JSONB list of UUID strings)",
        ),
        sa.Column(
            "capture_action",
            sa.String(20),
            nullable=False,
            comment="Capture boundary: start or retry",
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
            comment="Timestamp of the authenticated capture",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "dispatch_generation >= 0",
            name="ck_workflow_auth_records_generation_nonneg",
        ),
        sa.CheckConstraint(
            "capture_action IN ('start', 'retry')",
            name="ck_workflow_auth_records_capture_action",
        ),
        sa.UniqueConstraint(
            "run_id",
            "dispatch_generation",
            name="uq_workflow_auth_records_run_id_generation",
        ),
        sa.Index("idx_workflow_auth_records_run_id", "run_id"),
        sa.Index("idx_workflow_auth_records_user_id", "user_id"),
        comment=(
            "Append-only generation-specific authorization context "
            "(WP-REC-05 M1)"
        ),
    )


def downgrade() -> None:
    """Remove the auth-records table and restore the previous state contract."""

    op.drop_table("workflow_authorization_records")

    op.drop_constraint(
        "ck_workflow_runs_state",
        "workflow_runs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_workflow_runs_state",
        "workflow_runs",
        _OLD_STATE_CONSTRAINT,
    )
