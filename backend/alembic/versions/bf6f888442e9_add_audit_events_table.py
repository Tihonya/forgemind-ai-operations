"""add audit events table (WP-REC-04B)

Revision ID: bf6f888442e9
Revises: d4e5f6a7b8c9
Create Date: 2026-08-15 14:55:14.589265

Creates the append-only ``audit_events`` table — the Phase 6 audit-event
persistence foundation on which approval (04A), procurement (04C), and
the Audit Log UI (04E) build.

Contract (WP-REC-04-DEC §3.9, §4 WP-REC-04B):
- Immutable event identity: UUID primary key (server-generated).
- Correlation ID: UUID v4, not a foreign key (a correlation ID may span
  multiple entities).
- Event taxonomy: CHECK-constrained ``event_type``.
- Actor: nullable ``actor_id`` (FK to ``users.id``, RESTRICT) plus a
  nullable ``actor_username`` snapshot.
- Entity: CHECK-constrained ``entity_type`` plus ``entity_id`` (logical
  UUID reference, no FK — approval/procurement tables are owned by 04A/04C).
- Traceability linkage: nullable ``workflow_run_id`` (FK to
  ``workflow_runs.id``, RESTRICT) and nullable ``risk_id`` (business
  string identifier).
- Structured before/after summaries and event metadata (JSONB, redacted
  by the service before write).
- Backend/database-controlled ``created_at`` (server default now()).

Append-only is enforced at the application boundary (no update/delete
service method, read-only public API); no database-level trigger is
introduced (documented Release 1 boundary).

Downgrade drops the table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bf6f888442e9"
down_revision: str | Sequence[str] | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the append-only ``audit_events`` table."""
    op.create_table(
        "audit_events",
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
            "event_type",
            sa.String(50),
            nullable=False,
            comment="Bounded event taxonomy (AuditEventType)",
        ),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
            comment="Authenticated actor user UUID (null for system events)",
        ),
        sa.Column(
            "actor_username",
            sa.String(100),
            nullable=True,
            comment="Human-readable actor username snapshot",
        ),
        sa.Column(
            "entity_type",
            sa.String(50),
            nullable=False,
            comment="Bounded entity-type allow-list (AuditEntityType)",
        ),
        sa.Column(
            "entity_id",
            UUID(as_uuid=True),
            nullable=False,
            comment="Logical entity UUID (no FK; 04A/04C tables do not exist yet)",
        ),
        sa.Column(
            "workflow_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
            nullable=True,
            comment="Optional workflow run linkage for traceability",
        ),
        sa.Column(
            "risk_id",
            sa.String(100),
            nullable=True,
            comment="Business risk identifier (e.g. RISK-001)",
        ),
        sa.Column(
            "before_summary",
            JSONB(),
            nullable=True,
            comment="Structured pre-state summary (redacted)",
        ),
        sa.Column(
            "after_summary",
            JSONB(),
            nullable=True,
            comment="Structured post-state summary (redacted)",
        ),
        sa.Column(
            "metadata",
            JSONB(),
            nullable=True,
            comment="Safe structured event metadata (redacted)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "event_type IN ('APPROVAL_REQUEST_CREATED', 'APPROVAL_APPROVED', "
            "'APPROVAL_REJECTED', 'PROCUREMENT_TASK_CREATION_ATTEMPTED', "
            "'PROCUREMENT_TASK_CREATED', 'PROCUREMENT_TASK_CREATION_FAILED')",
            name="ck_audit_events_event_type",
        ),
        sa.CheckConstraint(
            "entity_type IN ('APPROVAL_REQUEST', 'PROCUREMENT_TASK')",
            name="ck_audit_events_entity_type",
        ),
        sa.Index(
            "idx_audit_events_created_at",
            "created_at",
            postgresql_using="btree",
            postgresql_ops={"created_at": "DESC"},
        ),
        sa.Index("idx_audit_events_correlation_id", "correlation_id"),
        sa.Index("idx_audit_events_entity", "entity_type", "entity_id"),
        sa.Index("idx_audit_events_workflow_run_id", "workflow_run_id"),
        sa.Index("idx_audit_events_event_type", "event_type"),
        comment="Append-only audit-event trail (WP-REC-04B)",
    )


def downgrade() -> None:
    """Drop the ``audit_events`` table."""
    op.drop_table("audit_events")
