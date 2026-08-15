"""Approval-request ORM model and action-binding contract (WP-REC-04A).

Defines the ``approval_requests`` persistence entity, the single-shot
``PENDING → APPROVED | REJECTED`` status enum, and the deterministic
action-binding hash contract consumed later by WP-REC-04C.

Action binding (WP-REC-04-DEC §3.8, §5; task §5):

An approval request binds an immutable action snapshot — never a mutable
pointer. The snapshot is a fixed, versioned set of fields derived from the
persisted recommendation and the deterministic risk engine at creation
time, and never recomputed from later recommendation or risk state. It
carries the executable procurement parameters (``component_code`` and
``quantity``) in addition to action/risk identity and
recommendation/workflow-run linkage, so WP-REC-04C can consume the stored
snapshot directly and compare its binding without re-deriving quantity
from mutable risk state.

``compute_binding_hash`` hashes a versioned canonical JSON serialization
(SHA-256) so WP-REC-04C can re-derive and compare its intended action
against the stored approved binding; a mismatch fails closed.

The snapshot contains no secrets and no vendor/price/payment fields.
"""

from __future__ import annotations

import enum
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ApprovalStatus(enum.StrEnum):
    """Single-shot approval lifecycle status (DEC-052 G3).

    The only transitions are ``PENDING → APPROVED`` and
    ``PENDING → REJECTED``. ``APPROVED`` and ``REJECTED`` are terminal.
    """

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


#: Canonical binding schema version. Bumped only when the action-snapshot
#: field set or normalization changes; included in the snapshot and the
#: binding hash so a schema change invalidates prior bindings.
BINDING_VERSION = 1

#: Canonical field set for the action snapshot. The set is fixed and
#: explicit — the binding hash is computed over these fields only, every
#: field is required (a missing field cannot be silently treated as a
#: different action), and the canonical serialization is deterministic
#: (independent of dictionary insertion order).
ACTION_SNAPSHOT_FIELDS: tuple[str, ...] = (
    "binding_version",
    "action_type",
    "component_code",
    "quantity",
    "risk_id",
    "workflow_run_id",
    "recommendation_id",
    "title",
    "rationale",
)

#: Snapshot fields whose value is a UUID and must be canonicalized to the
#: lowercase hyphenated form so case/format variation cannot split bindings.
_UUID_FIELDS: frozenset[str] = frozenset(
    {"workflow_run_id", "recommendation_id"}
)


def _canonical_decimal(value: object) -> str:
    """Return the canonical string form of a Decimal quantity.

    Contractually equivalent decimal representations (``Decimal("5")``,
    ``"5"``, ``"5.0"``, ``"5.00"``) normalize to the same string, so a
    quantity cannot be re-serialized into a different binding. NaN,
    Infinity, and non-numeric values fail closed.
    """
    if isinstance(value, bool):
        raise ValueError(f"quantity must not be a boolean: {value!r}")
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid decimal quantity: {value!r}") from exc
    if not dec.is_finite():
        raise ValueError(f"quantity must be finite: {value!r}")
    if dec == 0:
        return "0"
    return format(dec.normalize(), "f")


def _canonical_uuid(value: object) -> str:
    """Return the canonical lowercase-hyphenated UUID string form."""
    try:
        return str(UUID(str(value)))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f"invalid UUID: {value!r}") from exc


def canonical_action_serialization(snapshot: Mapping[str, Any]) -> str:
    """Return the deterministic canonical serialization of an action snapshot.

    The snapshot is serialized as a versioned JSON object with a fixed
    schema, deterministic key ordering (``sort_keys``), compact separators,
    and stable UUID/numeric normalization. Missing fields raise ``KeyError``
    (fail-closed); invalid values raise ``ValueError``/``TypeError``.

    JSON string escaping makes it impossible for delimiter/newline
    characters inside descriptive text (``title``, ``rationale``) to forge
    an additional field or collide with a distinct structured snapshot.
    """
    canonical: dict[str, Any] = {}
    for field in ACTION_SNAPSHOT_FIELDS:
        value = snapshot[field]  # KeyError on a missing field → fail closed
        if field == "binding_version":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"binding_version must be an integer: {value!r}")
            canonical[field] = value
        elif field == "quantity":
            canonical[field] = _canonical_decimal(value)
        elif field in _UUID_FIELDS:
            canonical[field] = _canonical_uuid(value)
        else:
            if not isinstance(value, str):
                raise TypeError(f"{field} must be a string: {value!r}")
            canonical[field] = value
    return json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def compute_binding_hash(snapshot: Mapping[str, Any]) -> str:
    """Compute the SHA-256 binding hash over the canonical serialization.

    Returns the lowercase hex digest. Deterministic and independent of
    dictionary insertion order; includes no secret values by construction.
    """
    return hashlib.sha256(canonical_action_serialization(snapshot).encode("utf-8")).hexdigest()


class ApprovalRequest(Base):
    """ORM representation of the ``approval_requests`` table.

    Attributes:
        id: UUID primary key — stable approval-request identity.
        correlation_id: UUID v4 correlation ID (not a foreign key).
        recommendation_id: Authoritative recommendation this approval binds.
        workflow_run_id: Workflow run linkage (validated to match the
            recommendation's run at creation time).
        risk_id: Originating risk identifier (e.g. ``RISK-001``).
        action_type: Bound action type (``CREATE_PROCUREMENT_TASK``).
        action_snapshot: Immutable canonical action snapshot (JSONB, no
            secrets).
        binding_hash: SHA-256 hex over the canonical serialization.
        requested_by: Requester user UUID (``users.id``, RESTRICT).
        requested_by_username: Immutable requester username snapshot.
        status: ``PENDING`` / ``APPROVED`` / ``REJECTED``.
        decided_by: Decision actor user UUID (null while PENDING).
        decided_by_username: Decision actor username snapshot.
        decision_comment: Approval comment (approve) or rejection reason
            (reject).
        requested_at: Backend-controlled creation timestamp.
        decided_at: Backend-controlled decision timestamp.
    """

    __tablename__ = "approval_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name="ck_approval_requests_status",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND decided_by IS NULL AND "
            "decided_by_username IS NULL AND decided_at IS NULL AND "
            "decision_comment IS NULL) OR "
            "(status IN ('APPROVED', 'REJECTED') AND decided_by IS NOT NULL "
            "AND decided_by_username IS NOT NULL AND decided_at IS NOT NULL "
            "AND decision_comment IS NOT NULL)",
            name="ck_approval_requests_terminal_fields",
        ),
        Index("idx_approval_requests_correlation_id", "correlation_id"),
        Index("idx_approval_requests_recommendation_id", "recommendation_id"),
        Index("idx_approval_requests_workflow_run_id", "workflow_run_id"),
        Index("idx_approval_requests_requested_by", "requested_by"),
        Index("idx_approval_requests_status", "status"),
        Index(
            "idx_approval_requests_requested_at",
            "requested_at",
            postgresql_using="btree",
            postgresql_ops={"requested_at": "DESC"},
        ),
        Index(
            "uq_approval_requests_active_action",
            "recommendation_id",
            "risk_id",
            "action_type",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
        {"comment": "Approval-request records (WP-REC-04A)"},
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

    action_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    binding_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
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

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ApprovalStatus.PENDING.value,
        server_default=text("'PENDING'"),
    )

    decided_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )

    decided_by_username: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    decision_comment: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
