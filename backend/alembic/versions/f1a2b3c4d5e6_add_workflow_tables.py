"""add workflow and recommendation tables (WP-REC-03B)

Revision ID: f1a2b3c4d5e6
Revises: 625c9f549f2b
Create Date: 2026-08-09 12:00:00.000000

This migration creates three tables for the AI workflow lifecycle:

- workflow_runs: durable anchor for each workflow execution attempt.
  The ``state`` column is the source of truth for domain workflow
  state (DEC-013).
- workflow_steps: per-step audit trail within a run (FR-07, AT-012).
- recommendations: validated AI recommendations (ORM model owned by
  03B; validated write path deferred to WP-REC-03F).

Foreign keys:
- workflow_runs.plan_id -> production_plans.id (RESTRICT)
- workflow_steps.run_id -> workflow_runs.id (CASCADE)
- recommendations.run_id -> workflow_runs.id (CASCADE, unique)
- recommendations.plan_id -> production_plans.id (RESTRICT)

Downgrade removes all three tables in safe dependency order:
recommendations, workflow_steps, workflow_runs.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | Sequence[str] | None = "625c9f549f2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create workflow_runs, workflow_steps, and recommendations tables."""

    # --- workflow_runs ---
    op.create_table(
        "workflow_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "correlation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'PENDING'"),
            comment=(
                "Workflow state: PENDING, RUNNING, AWAITING_VALIDATION, "
                "COMPLETED, FAILED_VALIDATION, FAILED_PROVIDER, "
                "FAILED_INTERNAL"
            ),
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("triggered_by", sa.String(length=100), nullable=True),
        sa.Column(
            "error_code",
            sa.String(length=50),
            nullable=True,
            comment="Safe error classification code (never contains secrets)",
        ),
        sa.Column(
            "error_detail",
            sa.Text(),
            nullable=True,
            comment="Safe bounded error summary (never contains secrets)",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["production_plans.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "state IN ('PENDING', 'RUNNING', 'AWAITING_VALIDATION', "
            "'COMPLETED', 'FAILED_VALIDATION', 'FAILED_PROVIDER', "
            "'FAILED_INTERNAL')",
            name="ck_workflow_runs_state",
        ),
        comment="Workflow run lifecycle records (WP-REC-03B)",
    )

    op.create_index(
        "idx_workflow_runs_correlation_id",
        "workflow_runs",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        "idx_workflow_runs_plan_id",
        "workflow_runs",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        "idx_workflow_runs_created_at",
        "workflow_runs",
        ["created_at"],
        unique=False,
        postgresql_using="btree",
        postgresql_ops={"created_at": "DESC"},
    )
    op.create_index(
        "idx_workflow_runs_state",
        "workflow_runs",
        ["state"],
        unique=False,
    )

    # --- workflow_steps ---
    op.create_table(
        "workflow_steps",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "correlation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "seq",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="Zero-based step sequence within the run",
        ),
        sa.Column("step_name", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'started'"),
            comment="Step status: started, completed, failed",
        ),
        sa.Column(
            "model_name",
            sa.String(length=100),
            nullable=True,
            comment="Model name for provider-call steps",
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "token_usage",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Token usage stats from provider (prompt/completion/total)",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Safe step metadata (finish_reason, provider, etc.)",
        ),
        sa.Column(
            "error_code",
            sa.String(length=50),
            nullable=True,
            comment="Safe error classification code",
        ),
        sa.Column(
            "error_detail",
            sa.Text(),
            nullable=True,
            comment="Safe bounded error summary",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('started', 'completed', 'failed')",
            name="ck_workflow_steps_status",
        ),
        comment="Workflow step audit trail (WP-REC-03B)",
    )

    op.create_index(
        "idx_workflow_steps_run_id",
        "workflow_steps",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "idx_workflow_steps_run_id_seq",
        "workflow_steps",
        ["run_id", "seq"],
        unique=False,
    )
    op.create_index(
        "idx_workflow_steps_correlation_id",
        "workflow_steps",
        ["correlation_id"],
        unique=False,
    )

    # --- recommendations ---
    op.create_table(
        "recommendations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'VALIDATED'"),
            comment="Recommendation status (VALIDATED in 03B)",
        ),
        sa.Column(
            "content",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Validated recommendation payload (SoT §6 schema). "
                "Written only by 03F persistence path."
            ),
        ),
        sa.Column(
            "schema_version",
            sa.String(length=10),
            nullable=True,
            comment="Recommendation schema version (e.g. 1.0)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["workflow_runs.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["production_plans.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            name="uq_recommendations_run_id",
        ),
        sa.CheckConstraint(
            "status IN ('VALIDATED')",
            name="ck_recommendations_status",
        ),
        comment="Validated AI recommendations (WP-REC-03B model, 03F write path)",
    )

    op.create_index(
        "idx_recommendations_run_id",
        "recommendations",
        ["run_id"],
        unique=True,
    )
    op.create_index(
        "idx_recommendations_plan_id",
        "recommendations",
        ["plan_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove recommendations, workflow_steps, and workflow_runs tables.

    Dependency order: recommendations (depends on workflow_runs) first,
    then workflow_steps (depends on workflow_runs), then workflow_runs.
    """
    # Drop indexes first (safe even if table-level cascade would handle it)
    op.drop_index("idx_recommendations_plan_id", table_name="recommendations")
    op.drop_index("idx_recommendations_run_id", table_name="recommendations")
    op.drop_table("recommendations")

    op.drop_index("idx_workflow_steps_correlation_id", table_name="workflow_steps")
    op.drop_index("idx_workflow_steps_run_id_seq", table_name="workflow_steps")
    op.drop_index("idx_workflow_steps_run_id", table_name="workflow_steps")
    op.drop_table("workflow_steps")

    op.drop_index("idx_workflow_runs_state", table_name="workflow_runs")
    op.drop_index("idx_workflow_runs_created_at", table_name="workflow_runs")
    op.drop_index("idx_workflow_runs_plan_id", table_name="workflow_runs")
    op.drop_index("idx_workflow_runs_correlation_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
