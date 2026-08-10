"""add dispatch_generation and pending_since columns (WP-REC-03F D5/D6)

Revision ID: a3b4c5d6e7f8
Revises: f1a2b3c4d5e6
Create Date: 2026-08-10 12:00:00.000000

This migration adds two columns and one partial index to the
``workflow_runs`` table per the WP-REC-03F D5 and D6 contracts:

- ``dispatch_generation`` (non-null, non-negative integer, default 0):
  durable dispatch identity for ARQ ``_job_id`` construction per D5.
  Existing rows receive 0 via ``server_default``.

- ``pending_since`` (nullable timezone-aware timestamp):
  represents the beginning of the run's current continuous stay in
  PENDING per D6 §1. Set on creation; reset on FAILED_* → PENDING
  retry. Existing rows receive NULL — they are not stale candidates
  because their state is already terminal or RUNNING.

- Partial index ``idx_workflow_runs_pending_since`` on
  ``(pending_since ASC, id ASC) WHERE state = 'PENDING'`` per D6 §11.
  Used by the D6 reconciler for stale-candidate detection.

Downgrade removes the index and both columns.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add dispatch_generation, pending_since, and partial PENDING index."""

    # D5 §2: dispatch_generation column — non-null, non-negative, default 0.
    op.add_column(
        "workflow_runs",
        sa.Column(
            "dispatch_generation",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment=(
                "Durable dispatch identity for ARQ job ID construction (D5). "
                "Initial value 0; incremented atomically on each authorized retry."
            ),
        ),
    )

    # D5 §2: CHECK constraint ensuring dispatch_generation is non-negative.
    op.create_check_constraint(
        "ck_workflow_runs_dispatch_generation_nonneg",
        "workflow_runs",
        "dispatch_generation >= 0",
    )

    # D6 §1: pending_since column — nullable timestamp.
    op.add_column(
        "workflow_runs",
        sa.Column(
            "pending_since",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=(
                "Beginning of the run's current continuous stay in PENDING (D6). "
                "Set on creation; reset on FAILED_* → PENDING retry."
            ),
        ),
    )

    # D6 §1: Backfill pending_since for existing PENDING rows.
    # Only PENDING rows need a pending_since value for reconciler candidate
    # detection. Existing terminal/RUNNING rows receive NULL — they are not
    # stale candidates. Use created_at as the best-available approximation
    # for existing PENDING rows (their actual PENDING start is unknown but
    # created_at is a conservative upper bound).
    op.execute(
        "UPDATE workflow_runs "
        "SET pending_since = created_at "
        "WHERE state = 'PENDING' AND pending_since IS NULL"
    )

    # D6 §11: Partial index for reconciler candidate selection.
    # Filters on state = 'PENDING' and orders by (pending_since ASC, id ASC).
    op.create_index(
        "idx_workflow_runs_pending_since",
        "workflow_runs",
        ["pending_since", "id"],
        unique=False,
        postgresql_where=sa.text("state = 'PENDING'"),
    )

    # D1 §10: Unique constraint on (run_id, seq) to enforce append-only
    # strictly-increasing step sequences at the database level. This is a
    # defense-in-depth guarantee that duplicate seq values cannot be
    # persisted even if the application-level _next_step_seq logic has a bug.
    op.create_unique_constraint(
        "uq_workflow_steps_run_id_seq",
        "workflow_steps",
        ["run_id", "seq"],
    )


def downgrade() -> None:
    """Remove the partial index, pending_since, and dispatch_generation."""

    # D1 §10: Drop the unique constraint on (run_id, seq).
    op.drop_constraint(
        "uq_workflow_steps_run_id_seq",
        "workflow_steps",
        type_="unique",
    )

    op.drop_index(
        "idx_workflow_runs_pending_since",
        table_name="workflow_runs",
    )

    op.drop_column("workflow_runs", "pending_since")

    op.drop_constraint(
        "ck_workflow_runs_dispatch_generation_nonneg",
        "workflow_runs",
        type_="check",
    )
    op.drop_column("workflow_runs", "dispatch_generation")
