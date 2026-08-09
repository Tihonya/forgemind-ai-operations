"""Workflow and recommendation ORM models (WP-REC-03B).

Defines the persistence layer for the AI workflow lifecycle:

- WorkflowRun: a single workflow execution attempt with explicit state
  machine state, correlation ID, and safe error metadata.
- WorkflowStep: individual step records within a run (provider call,
  risk calculation, validation, etc.) providing the persistent audit
  trail required by FR-07 / AT-012.
- Recommendation: the SQLAlchemy ORM model for a validated
  recommendation. WP-REC-03B owns the model and table; the validated
  persistence path (writing a Recommendation row from validated provider
  output) is deferred to WP-REC-03F. The Pydantic wire schema is owned
  by WP-REC-03C.

States and transitions are defined in
``backend/app/ai/workflow/state_machine.py``. The models store state as
a string column with a CHECK constraint matching the canonical state
names. No Recommendation row is persisted from unvalidated provider
output in this package.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    pass


class WorkflowRun(Base):
    """ORM representation of the ``workflow_runs`` table.

    A WorkflowRun is the durable anchor for one workflow execution
    attempt. Its ``state`` column is the source of truth for domain
    workflow state (DEC-013). Every state transition goes through the
    explicit state machine and is persisted here.

    Attributes:
        id: UUID primary key (also serves as ``run_id``).
        correlation_id: UUID v4 correlation ID propagated through all
            steps and into the ChatProvider context (DEC-024, FR-07).
        state: Current workflow state. One of PENDING, RUNNING,
            AWAITING_VALIDATION, COMPLETED, FAILED_VALIDATION,
            FAILED_PROVIDER, FAILED_INTERNAL.
        plan_id: Foreign key to ``production_plans.id`` — the plan
            being analysed by this workflow run.
        triggered_by: Username or system identifier that initiated the
            run. Nullable for system-initiated runs.
        error_code: Safe, bounded error classification code (e.g.
            "PROVIDER_TRANSIENT", "PROVIDER_PERMANENT",
            "INTERNAL_ERROR"). Never contains exception messages or
            stack traces. Null when the run has not failed.
        error_detail: Safe, bounded human-readable error summary. Must
            not contain API keys, prompts, or raw provider payloads.
            Null when the run has not failed.
        started_at: Timestamp when the run transitioned to RUNNING.
        completed_at: Timestamp when the run reached a terminal state.
        created_at: Row creation timestamp.
        updated_at: Last-update timestamp.
    """

    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('PENDING', 'RUNNING', 'AWAITING_VALIDATION', "
            "'COMPLETED', 'FAILED_VALIDATION', 'FAILED_PROVIDER', "
            "'FAILED_INTERNAL')",
            name="ck_workflow_runs_state",
        ),
        Index("idx_workflow_runs_correlation_id", "correlation_id"),
        Index("idx_workflow_runs_plan_id", "plan_id"),
        Index(
            "idx_workflow_runs_created_at",
            "created_at",
            postgresql_using="btree",
            postgresql_ops={"created_at": "DESC"},
        ),
        Index("idx_workflow_runs_state", "state"),
        {"comment": "Workflow run lifecycle records (WP-REC-03B)"},
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

    state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
        comment="Workflow state: PENDING, RUNNING, AWAITING_VALIDATION, "
        "COMPLETED, FAILED_VALIDATION, FAILED_PROVIDER, FAILED_INTERNAL",
    )

    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("production_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )

    triggered_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Safe error classification code (never contains secrets)",
    )

    error_detail: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Safe bounded error summary (never contains secrets)",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    steps: Mapped[list["WorkflowStep"]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        order_by="WorkflowStep.seq",
    )

    recommendation: Mapped["Recommendation | None"] = relationship(
        back_populates="workflow_run",
        uselist=False,
        cascade="all, delete-orphan",
    )


class WorkflowStep(Base):
    """ORM representation of the ``workflow_steps`` table.

    Each WorkflowStep records one step in the workflow lifecycle,
    providing the persistent audit trail required by FR-07 and AT-012.
    Steps include provider calls, risk calculation invocations, and
    validation attempts.

    Attributes:
        id: UUID primary key.
        run_id: Foreign key to ``workflow_runs.id``.
        seq: Zero-based sequence number within the run. Steps are
            ordered by this field.
        step_name: Canonical step name (e.g. "provider_call",
            "risk_calculation").
        status: Step status: "started", "completed", "failed".
        model_name: Model name when this step involved a provider call.
            Null for non-provider steps.
        latency_ms: Step duration in milliseconds. Null if not
            completed.
        token_usage: Token usage JSONB when available from the
            provider. Null for non-provider steps or when the provider
            does not report usage.
        metadata: Safe metadata JSONB (e.g. finish_reason, provider
            name). Must never contain API keys, prompts, or raw
            provider payloads.
        error_code: Safe error classification code when the step
            failed. Never contains exception messages.
        error_detail: Safe bounded error summary when the step failed.
        started_at: Timestamp when the step started.
        completed_at: Timestamp when the step completed or failed.
        created_at: Row creation timestamp.
    """

    __tablename__ = "workflow_steps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'completed', 'failed')",
            name="ck_workflow_steps_status",
        ),
        Index("idx_workflow_steps_run_id", "run_id"),
        Index("idx_workflow_steps_run_id_seq", "run_id", "seq"),
        Index("idx_workflow_steps_correlation_id", "correlation_id"),
        {"comment": "Workflow step audit trail (WP-REC-03B)"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    correlation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        default=uuid4,
    )

    seq: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Zero-based step sequence within the run",
    )

    step_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="started",
        server_default=text("'started'"),
        comment="Step status: started, completed, failed",
    )

    model_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Model name for provider-call steps",
    )

    latency_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    token_usage: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Token usage stats from provider (prompt/completion/total)",
    )

    step_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Safe step metadata (finish_reason, provider, etc.)",
    )

    error_code: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Safe error classification code",
    )

    error_detail: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Safe bounded error summary",
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    # Relationships
    workflow_run: Mapped["WorkflowRun"] = relationship(
        back_populates="steps",
    )


class Recommendation(Base):
    """ORM representation of the ``recommendations`` table.

    WP-REC-03B owns the SQLAlchemy model and table. The validated
    persistence path — writing a Recommendation row from validated
    provider output — is deferred to WP-REC-03F. The Pydantic wire
    schema (``backend/app/schemas/recommendation.py``) is owned by
    WP-REC-03C.

    No Recommendation row is persisted from unvalidated provider output.

    Attributes:
        id: UUID primary key.
        run_id: Foreign key to ``workflow_runs.id`` — the run that
            produced this recommendation.
        plan_id: Foreign key to ``production_plans.id`` — the plan
            this recommendation addresses.
        status: Recommendation status: "VALIDATED" (the only valid
            status in 03B; other statuses may be added by future
            packages).
        content: JSONB containing the validated recommendation payload
            matching the structured recommendation schema (SoT §6).
            Written only by the validated persistence path (03F).
        schema_version: Version string of the recommendation schema
            (e.g. "1.0").
        created_at: Row creation timestamp.
        updated_at: Last-update timestamp.
    """

    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('VALIDATED')",
            name="ck_recommendations_status",
        ),
        Index("idx_recommendations_run_id", "run_id", unique=True),
        Index("idx_recommendations_plan_id", "plan_id"),
        {"comment": "Validated AI recommendations (WP-REC-03B model, 03F write path)"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )

    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    plan_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("production_plans.id", ondelete="RESTRICT"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="VALIDATED",
        server_default=text("'VALIDATED'"),
        comment="Recommendation status (VALIDATED in 03B)",
    )

    content: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Validated recommendation payload (SoT §6 schema). "
        "Written only by 03F persistence path.",
    )

    schema_version: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="Recommendation schema version (e.g. 1.0)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )

    # Relationships
    workflow_run: Mapped["WorkflowRun"] = relationship(
        back_populates="recommendation",
    )
