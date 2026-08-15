"""Append-only audit-event write service (WP-REC-04B).

Provides the single internal creation path for audit events. There is
deliberately no update or delete method: audit events are created once
and never mutated through the service. The public API is read-only
(``app/api/audit.py``); future Phase 6 services (04A approval, 04C
procurement) call this service transactionally to append events.

Release 1 immutability boundary (documented, not over-claimed):
- The application service exposes no update/delete operation.
- The public REST API exposes no POST/PUT/PATCH/DELETE for audit events.
- No database-level trigger prevents direct UPDATE/DELETE by a privileged
  database operator. This is the agreed Release 1 boundary; stronger
  database-level immutability is not required by the decomposition
  (WP-REC-04-DEC §3.9).

Secret-safety (AT-012 negative, SoT §6):
- ``before_summary``, ``after_summary``, and ``metadata`` are redacted
  before persistence. Secret-bearing keys (``api_key``,
  ``authorization``, ``token``, ``access_token``, ``refresh_token``,
  ``password``, ``secret``, and provider credential variants) are
  replaced with the ``[REDACTED]`` sentinel, recursively and
  case-insensitively. Caller-supplied mappings are never mutated.

Timestamps are backend/database controlled: the service accepts no
timestamp argument. Actor identity is supplied only by trusted internal
callers (Phase 6 services deriving it from the authenticated user); no
public request body can set it because the public API is read-only.
"""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_correlation_id
from app.core.correlation import generate_correlation_id, validate_correlation_id
from app.core.logging import get_logger
from app.models.audit import AuditEvent
from app.models.enums import AuditEntityType, AuditEventType

logger = get_logger(__name__)

#: Sentinel used to replace secret-bearing values during redaction.
REDACTED = "[REDACTED]"

#: Secret-bearing key fragments (normalised, lowercase). A structured
#: field key is secret-bearing when its normalised name contains any of
#: these substrings, or ends with ``token`` (covering bare ``token``,
#: ``access_token``, ``refresh_token``, ``bearer_token`` without flagging
#: legitimate ``token_usage``-style keys).
_SECRET_KEY_SUBSTRINGS = frozenset(
    {
        "apikey",
        "authorization",
        "password",
        "secret",
        "credential",
        "accesstoken",
        "refreshtoken",
    }
)

#: Suffix marker for bare ``token``/``access_token``/``refresh_token`` keys.
#: Not a credential — a redaction key-fragment classifier.
_SECRET_TOKEN_SUFFIX = "token"  # noqa: S105

_NORMALISE_KEY_RE = re.compile(r"[^a-z0-9]")


def _normalise_key(key: str) -> str:
    """Lowercase a key and strip non-alphanumeric separators."""
    return _NORMALISE_KEY_RE.sub("", key.lower())


def _is_secret_key(key: str) -> bool:
    """Return True when a key is secret-bearing.

    Case-insensitive; normalises away ``_``/``-``/``.``/space so that
    ``api_key``, ``API-Key``, and ``apiKey`` all match. Provider
    credential variants (``groq_api_key``, ``openrouter_api_key``,
    ``client_secret``) match via substring.
    """
    normalised = _normalise_key(key)
    if any(token in normalised for token in _SECRET_KEY_SUBSTRINGS):
        return True
    return normalised.endswith(_SECRET_TOKEN_SUFFIX)


def redact_secrets(value: Any) -> Any:
    """Recursively redact secret-bearing keys without mutating the input.

    Returns a new structure in which any mapping key classified as
    secret-bearing has its value replaced with ``REDACTED``. Nested
    mappings and lists are walked recursively; scalar values are returned
    unchanged. The input is never mutated.

    Args:
        value: The structured value to redact (mapping, list, or scalar).

    Returns:
        A redacted deep structure independent of ``value``.

    Raises:
        TypeError: If a mapping contains a non-string key.
    """
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("structured audit fields must use string keys")
            if _is_secret_key(key):
                result[key] = REDACTED
            else:
                result[key] = redact_secrets(item)
        return result

    if isinstance(value, list):
        return [redact_secrets(item) for item in value]

    return value


def _redact_structured_field(value: Any, field_name: str) -> dict[str, Any] | None:
    """Validate and redact a structured audit field.

    A structured field must be a JSON object (``dict`` with string keys)
    when present. The redacted structure is a fresh object — the caller's
    mapping is never mutated.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError(
            f"{field_name} must be a JSON object (dict), got {type(value).__name__}"
        )
    redacted = redact_secrets(value)
    if not isinstance(redacted, dict):
        # Unreachable: a dict input always redacts to a dict.
        raise TypeError(f"{field_name} redaction produced a non-object value")
    return redacted


class AuditService:
    """Internal append-only audit-event creation service.

    Instances are bound to an ``AsyncSession``. ``create_event`` adds a
    single ``AuditEvent`` row and flushes (so ``id``/``created_at`` are
    populated) but does not commit — the caller owns the transaction so
    future Phase 6 services can append audit events atomically with their
    own domain writes.

    The service exposes no update or delete operation by construction.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_event(
        self,
        *,
        event_type: AuditEventType,
        entity_type: AuditEntityType,
        entity_id: UUID,
        actor_id: UUID | None = None,
        actor_username: str | None = None,
        correlation_id: str | UUID | None = None,
        workflow_run_id: UUID | None = None,
        risk_id: str | None = None,
        before_summary: dict[str, Any] | None = None,
        after_summary: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Create and append one audit event.

        All validation and redaction happens before any row is added, so
        a failing event never leaves a partially populated record.

        Args:
            event_type: Canonical event type (``AuditEventType``).
            entity_type: Canonical entity type (``AuditEntityType``).
            entity_id: Logical UUID identity of the event's entity.
            actor_id: Authenticated actor user UUID (null for system
                events). Supplied only by trusted internal callers.
            actor_username: Actor username snapshot (null for system
                events).
            correlation_id: Correlation UUID v4. When None, resolved from
                the request context (``get_correlation_id``) or generated.
            workflow_run_id: Optional workflow run linkage.
            risk_id: Optional business risk identifier.
            before_summary: Optional structured pre-state summary.
            after_summary: Optional structured post-state summary.
            metadata: Optional structured event metadata.

        Returns:
            The appended ``AuditEvent`` (flushed; caller commits).

        Raises:
            ValueError: Invalid ``event_type``/``entity_type`` enum value
                or invalid correlation ID.
            TypeError: A structured field is not a JSON object (dict).
        """
        if not isinstance(event_type, AuditEventType):
            raise ValueError(f"invalid event_type: {event_type!r}")
        if not isinstance(entity_type, AuditEntityType):
            raise ValueError(f"invalid entity_type: {entity_type!r}")

        correlation_uuid = self._resolve_correlation_id(correlation_id)

        redacted_before = _redact_structured_field(before_summary, "before_summary")
        redacted_after = _redact_structured_field(after_summary, "after_summary")
        redacted_metadata = _redact_structured_field(metadata, "metadata")

        event = AuditEvent(
            correlation_id=correlation_uuid,
            event_type=event_type.value,
            actor_id=actor_id,
            actor_username=actor_username,
            entity_type=entity_type.value,
            entity_id=entity_id,
            workflow_run_id=workflow_run_id,
            risk_id=risk_id,
            before_summary=redacted_before,
            after_summary=redacted_after,
            event_metadata=redacted_metadata,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    @staticmethod
    def _resolve_correlation_id(correlation_id: str | UUID | None) -> UUID:
        """Resolve and validate the correlation ID for a new event.

        Resolution order: explicit argument → bound request context →
        newly generated UUID v4. The result is validated as a UUID v4.
        """
        resolved = correlation_id
        if resolved is None:
            resolved = get_correlation_id()
        if resolved is None:
            resolved = generate_correlation_id()

        try:
            canonical = validate_correlation_id(str(resolved))
        except ValueError as exc:
            raise ValueError(f"invalid correlation_id: {resolved!r}") from exc

        return UUID(canonical)
