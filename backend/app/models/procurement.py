"""Procurement-task ORM model (WP-REC-04C).

Defines the ``procurement_tasks`` persistence entity — the synthetic,
deterministic local controlled-action record created exactly once from an
``APPROVED`` approval request (WP-REC-04-DEC §4 WP-REC-04C; DEC-052 G2/G3).

Contract:

- Synthetic local entity only: it carries component/item identity, the
  approved quantity, originating risk and workflow run, the source
  approval request, requester and approver identities, the approved
  binding hash, a correlation ID, and a backend-controlled creation
  timestamp. It contains no vendor, supplier, price, amount, currency,
  payment, bank/account, external ERP identifier, provider prompt, or
  secret (DEC-052 G2; decomposition §3.5).
- Exactly one task per approval request is enforced at the database layer
  by a UNIQUE constraint on ``approval_request_id`` (decomposition §3.10;
  task §3/§5). The service/API boundary additionally serializes
  concurrent executions with a row lock and re-reads the authoritative row
  on a uniqueness race.
- ``task_state`` is a single deterministic synthetic value (``CREATED``):
  the controlled action is creation of exactly one local row, with no
  further lifecycle, external transmission, or payment state (DEC-052 G3).
- ``quantity`` and ``component_code`` are the immutable approved action
  parameters re-read from the WP-REC-04A persisted ``action_snapshot``;
  they are never recomputed from mutable risk state and never accepted
  from the client (task §4).
- ``binding_hash`` is the approved SHA-256 binding hash copied from the
  approval request so the task row itself carries verifiable provenance
  for AT-012 traceability without re-deriving it from later state.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProcurementTaskState(enum.StrEnum):
    """Deterministic synthetic procurement-task state.

    The controlled action is the creation of exactly one local
    ``procurement_tasks`` row. There is no further Release 1 lifecycle:
    the only state a task can hold is ``CREATED`` (DEC-052 G3).
    """

    CREATED = "CREATED"


class ProcurementTask(Base):
    """ORM representation of the ``procurement_tasks`` table.

    Attributes:
        id: UUID primary key — stable procurement-task identity.
        correlation_id: UUID v4 correlation ID reused from the source
            approval request (not a foreign key — one lineage spans the
            approval and the task).
        approval_request_id: Source approval request (FK, RESTRICT,
            UNIQUE — at most one task per approval).
        recommendation_id: Authoritative recommendation provenance (FK,
            RESTRICT).
        workflow_run_id: Originating workflow run (FK, RESTRICT).
        risk_id: Originating risk identifier (e.g. ``RISK-001``).
        action_type: Bound action type (``CREATE_PROCUREMENT_TASK``).
        component_code: Approved component/item identity (immutable,
            re-read from the approval snapshot).
        quantity: Approved positive quantity (immutable, re-read from the
            approval snapshot; DB CHECK ``quantity > 0``).
        binding_hash: Approved SHA-256 binding hash (immutable
            provenance).
        task_state: ``CREATED`` (single deterministic state).
        requested_by: Requester user UUID (``users.id``, RESTRICT).
        requested_by_username: Immutable requester username snapshot.
        approved_by: Approver/decision actor user UUID (``users.id``,
            RESTRICT).
        approved_by_username: Immutable approver username snapshot.
        created_at: Backend/database-controlled creation timestamp.
    """

    __tablename__ = "procurement_tasks"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('CREATE_PROCUREMENT_TASK')",
            name="ck_procurement_tasks_action_type",
        ),
        CheckConstraint(
            "task_state IN ('CREATED')",
            name="ck_procurement_tasks_task_state",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_procurement_tasks_quantity_positive",
        ),
        UniqueConstraint(
            "approval_request_id",
            name="uq_procurement_tasks_approval_request_id",
        ),
        Index("idx_procurement_tasks_correlation_id", "correlation_id"),
        Index("idx_procurement_tasks_recommendation_id", "recommendation_id"),
        Index("idx_procurement_tasks_workflow_run_id", "workflow_run_id"),
        Index("idx_procurement_tasks_risk_id", "risk_id"),
        Index("idx_procurement_tasks_requested_by", "requested_by"),
        Index("idx_procurement_tasks_approved_by", "approved_by"),
        Index(
            "idx_procurement_tasks_created_at",
            "created_at",
            postgresql_using="btree",
            postgresql_ops={"created_at": "DESC"},
        ),
        {"comment": "Synthetic procurement-task records (WP-REC-04C)"},
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

    approval_request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("approval_requests.id", ondelete="RESTRICT"),
        nullable=False,
    )

    recommendation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="RESTRICT"),
        nullable=False,
    )

    workflow_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workflow_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )

    risk_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    action_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    component_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
    )

    binding_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    task_state: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=ProcurementTaskState.CREATED.value,
        server_default=text("'CREATED'"),
    )

    requested_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    requested_by_username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    approved_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    approved_by_username: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )
