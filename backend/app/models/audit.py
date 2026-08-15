"""Audit-event ORM model (WP-REC-04B).

Provides the append-only ``audit_events`` persistence foundation for the
Phase 6 approval (04A), procurement (04C), and Audit Log UI (04E)
packages.

Append-only boundary: the audit service exposes only creation and the
public API is read-only. There is no update/delete service method and no
database trigger. This Release 1 boundary is documented and tested (see
``app/services/audit_service.py``) and is not over-claimed as
database-enforced immutability.

Secret-safety: ``before_summary``, ``after_summary``, and
``event_metadata`` are structured JSONB that the audit service
deterministically redacts before persistence. They must never contain API
keys, tokens, prompts, or raw provider payloads (AT-012 negative, SoT §6).
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

if TYPE_CHECKING:
    pass


class AuditEvent(Base):
    """ORM representation of the ``audit_events`` table.

    Attributes:
        id: UUID primary key — immutable event identity.
        correlation_id: UUID v4 correlation ID propagated through the
            workflow and Phase 6 services (DEC-024). Not a foreign key —
            a correlation ID may span multiple entities.
        event_type: Bounded event taxonomy (``AuditEventType``).
        actor_id: Foreign key to ``users.id`` — the authenticated actor
            when a human actor exists. Null for system-initiated events.
        actor_username: Human-readable actor snapshot (username) so the
            trace remains legible even if the user is later renamed or
            deactivated. Null when no human actor exists.
        entity_type: Bounded entity-type allow-list (``AuditEntityType``).
        entity_id: Logical identity of the entity this event concerns
            (e.g. an approval-request UUID). NOT a foreign key: the
            approval/procurement tables are owned by 04A/04C and do not
            yet exist at this package's boundary.
        workflow_run_id: Optional foreign key to ``workflow_runs.id`` for
            run-scoped traceability.
        risk_id: Optional business risk identifier (e.g. "RISK-001").
            Stored as a string, not a foreign key — risks are
            deterministic calculation outputs, not a persisted entity.
        before_summary: Optional structured pre-state summary (JSONB).
        after_summary: Optional structured post-state summary (JSONB).
        event_metadata: Optional structured event metadata (JSONB, column
            ``metadata``). Redacted before persistence.
        created_at: Backend/database-controlled row creation timestamp.
            Clients cannot set this field.
    """

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('APPROVAL_REQUEST_CREATED', 'APPROVAL_APPROVED', "
            "'APPROVAL_REJECTED', 'PROCUREMENT_TASK_CREATION_ATTEMPTED', "
            "'PROCUREMENT_TASK_CREATED', 'PROCUREMENT_TASK_CREATION_FAILED')",
            name="ck_audit_events_event_type",
        ),
        CheckConstraint(
            "entity_type IN ('APPROVAL_REQUEST', 'PROCUREMENT_TASK')",
            name="ck_audit_events_entity_type",
        ),
        Index(
            "idx_audit_events_created_at",
            "created_at",
            postgresql_using="btree",
            postgresql_ops={"created_at": "DESC"},
        ),
        Index("idx_audit_events_correlation_id", "correlation_id"),
        Index("idx_audit_events_entity", "entity_type", "entity_id"),
        Index("idx_audit_events_workflow_run_id", "workflow_run_id"),
        Index("idx_audit_events_event_type", "event_type"),
        {"comment": "Append-only audit-event trail (WP-REC-04B)"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    correlation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        default=uuid4,
    )

    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    actor_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    actor_username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    entity_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    entity_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
    )

    workflow_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=True,
    )

    risk_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    before_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    after_summary: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Safe structured event metadata (redacted; never secrets)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
