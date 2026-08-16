"""Pydantic schemas for the normalized audit-trace API (AT-012 remediation).

The unified trace endpoint (``GET /api/v1/audit-trace/{correlation_id}``)
combines Phase 5 ``workflow_steps`` (items 1-6) with Phase 6 ``audit_events``
(items 7-9) into a single, correlation-scoped, read-only view of the required
nine-item AT-012 trace.

Secret-safety: the trace ``summary`` is assembled only from already-redacted
Phase 6 ``after_summary``/``before_summary`` and safe Phase 5 ``step_metadata``.
``sanitize_trace_summary`` additionally strips ``binding_hash`` (every spelling
variant) at every nesting depth and re-applies secret redaction, so the trace
surface never carries a binding hash or a secret-bearing value.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.services.audit_service import redact_secrets

# Canonical nine-item AT-012 trace category union.
TraceCategory = Literal[
    "user_action",
    "deterministic_calculation",
    "retrieval",
    "model_call",
    "structured_validation",
    "recommendation",
    "approval_request",
    "human_decision",
    "write_action",
]

# Canonical nine-item AT-012 trace categories in fixed display order.
TRACE_CATEGORY_ORDER: tuple[TraceCategory, ...] = (
    "user_action",
    "deterministic_calculation",
    "retrieval",
    "model_call",
    "structured_validation",
    "recommendation",
    "approval_request",
    "human_decision",
    "write_action",
)

TraceSource = Literal["workflow_step", "audit_event"]


class TraceItem(BaseModel):
    """A single normalized item in the nine-item trace."""

    model_config = ConfigDict(from_attributes=True)

    category: TraceCategory = Field(..., description="Canonical trace category")
    category_order: int = Field(..., description="Stable display order 1..9")
    occurred_at: datetime = Field(..., description="When the item occurred")
    source: TraceSource = Field(..., description="workflow_step or audit_event")
    source_id: UUID = Field(..., description="Underlying step/event row UUID")
    actor: str | None = Field(
        default=None, description="Human actor username, or null for system actions"
    )
    entity_type: str | None = Field(
        default=None, description="Entity type for audit-event items"
    )
    entity_id: str | None = Field(
        default=None, description="Entity identity for audit-event items"
    )
    risk_id: str | None = Field(
        default=None, description="Business risk identifier"
    )
    summary: dict[str, Any] | None = Field(
        default=None,
        description="Safe, redacted, binding-hash-free summary",
    )


class AuditTraceResponse(BaseModel):
    """Normalized, correlation-scoped nine-item trace response."""

    correlation_id: UUID = Field(..., description="Correlation UUID v4")
    workflow_run_id: UUID = Field(..., description="Workflow run UUID")
    triggered_by: str | None = Field(
        default=None, description="Run initiator (item 1 display source)"
    )
    final_state: str = Field(..., description="Final workflow run state")
    complete: bool = Field(..., description="True when all nine categories present")
    is_legacy: bool = Field(
        ...,
        description=(
            "True only when the trace contains neither of the two "
            "post-remediation capture markers (user_action, "
            "deterministic_calculation). Derived from durable capture markers, "
            "never from timestamps."
        ),
    )
    missing_categories: list[str] = Field(
        default_factory=list,
        description="Canonical category names absent from the trace, in order",
    )
    items: list[TraceItem] = Field(
        default_factory=list, description="Canonical trace items ordered 1..9"
    )


_BINDING_HASH_NORMALIZED = "bindinghash"
_NORMALISE_KEY_RE = re.compile(r"[^a-z0-9]")


def _normalise_key(key: str) -> str:
    """Lowercase a key and strip non-alphanumeric separators."""
    return _NORMALISE_KEY_RE.sub("", key.lower())


def _is_binding_hash_key(key: str) -> bool:
    """Return True when a key is ``binding_hash`` in any spelling variant.

    Matches ``binding_hash``, ``bindingHash``, and ``binding-hash`` exactly;
    unrelated keys such as ``binding_version`` do not match.
    """
    return _normalise_key(key) == _BINDING_HASH_NORMALIZED


def _strip_binding_hash(value: Any) -> Any:
    """Recursively remove binding-hash keys without mutating the input."""
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and _is_binding_hash_key(key):
                continue
            result[key] = _strip_binding_hash(item)
        return result
    if isinstance(value, list):
        return [_strip_binding_hash(item) for item in value]
    return value


def sanitize_trace_summary(value: Any) -> Any:
    """Build a safe trace summary: strip binding hashes, redact secrets.

    Applies in order:
    1. Recursively removes ``binding_hash``/``bindingHash``/``binding-hash``
       keys at every nesting depth (neither key nor value survives).
    2. Recursively redacts secret-bearing keys to the ``[REDACTED]``
       sentinel via the shared audit-service redaction.

    Safe adjacent values are preserved verbatim and the input is never
    mutated. The ``[REDACTED]`` sentinel is preserved exactly as the backend
    wrote it.
    """
    stripped = _strip_binding_hash(value)
    return redact_secrets(stripped)
