"""Pure structured-output validator for AI model responses (WP-REC-03C).

This module provides a single pure function, :func:`validate_structured_output`,
that accepts the ``ChatResult.content`` string produced by the AI provider
(WP-REC-03A), parses it as JSON, and validates it against the versioned
recommendation Pydantic wire schema (``backend/app/schemas/recommendation.py``).

Design contract (WP-REC-03C):

- **Pure**: no persistence, no workflow-state mutation, no write actions.
- **Unified failure**: a single validator-level exception
  (:class:`StructuredOutputValidationError`) covers both malformed JSON and
  schema-validation failures. The future 03F caller catches this one
  exception and maps it to the ``FAILED_VALIDATION`` workflow state via
  the existing 03B state machine.
- **Safe**: the exception's public message and any log output never
  contain raw model output, raw input values, prompts, or complete
  Pydantic error messages that may echo rejected input. Only bounded,
  sanitized metadata (failure classification, error count, field
  locations, Pydantic error types) is exposed.
- **No side effects**: the function does not import or call any database,
  ORM, ARQ, or workflow-engine code. Its only dependencies are the
  Pydantic wire schema and the standard library.

AT-008 boundary (WP-REC-03C):

This validator verifies that invalid model output produces a
validator-level failure. Unit tests may independently verify that the
existing pure state-machine contract permits
``AWAITING_VALIDATION → FAILED_VALIDATION``. The actual runtime
transition, error persistence, and trace exposure are deferred to
WP-REC-03F and WP-REC-03E. This package must not claim full AT-008 PASS.
"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from app.core.logging import get_logger
from app.schemas.recommendation import RecommendationData

_logger = get_logger(__name__)

# Maximum number of error detail entries exposed in the exception's
# ``field_locations`` and ``error_types`` lists and in structured logs.
# The total ``error_count`` always reports the full number of validation
# errors; only the exposed detail lists are capped to prevent unbounded
# exception and log metadata.
_MAX_EXPOSED_ERRORS: int = 20

# Maximum length of a single sanitized location-component string.
# Components longer than this are truncated and marked.
_MAX_LOC_COMPONENT_LENGTH: int = 50

# Known schema field names for the v1 recommendation wire schema.
# When a Pydantic error location component matches one of these names,
# it is exposed as-is. Integer list indices (e.g. ``0``, ``1``) are
# also exposed as-is. Any other string component — including
# input-controlled extra-field names — is replaced with ``<extra>`` to
# prevent input-controlled text from entering exception metadata or logs.
_KNOWN_FIELD_NAMES: frozenset[str] = frozenset({
    "schema_version",
    "run_id",
    "plan_id",
    "risks",
    "risk_id",
    "summary",
    "business_impact",
    "recommended_actions",
    "action_type",
    "title",
    "rationale",
    "requires_approval",
    "sources",
    "document_id",
    "version",
    "chunk_id",
})

# Neutral marker replacing unknown or input-controlled location components.
_UNKNOWN_MARKER: str = "<extra>"


class ValidationFailureReason(StrEnum):
    """Safe, bounded classification of why validation failed.

    These values may appear in logs and in the exception's ``reason``
    attribute. They never contain raw input or sensitive data.
    """

    INVALID_JSON = "INVALID_JSON"
    INVALID_SCHEMA = "INVALID_SCHEMA"


class StructuredOutputValidationError(Exception):
    """Unified validator-level exception for all structured-output failures.

    This is the single exception type that the future 03F caller catches
    to map a validation failure to the ``FAILED_VALIDATION`` workflow
    state via the 03B state machine.

    Attributes:
        reason: Safe failure classification
            (:class:`ValidationFailureReason`). Never contains raw input.
        error_count: Total number of schema-validation errors when
            ``reason`` is ``INVALID_SCHEMA``. ``0`` for ``INVALID_JSON``.
            This always reports the full count, even when the detail
            lists are capped.
        field_locations: Sanitized and capped list of safe
            field-location strings (e.g. ``"risks.0.sources"``) when
            ``reason`` is ``INVALID_SCHEMA``. Empty for ``INVALID_JSON``.
            Each component is either a known schema field name, an
            integer list index, or the neutral marker ``<extra>``.
            Unknown or input-controlled components are never exposed.
            The list is capped at ``_MAX_EXPOSED_ERRORS`` entries.
        error_types: Sanitized and capped list of safe Pydantic
            error-type strings (e.g. ``"missing"`` or
            ``"extra_forbidden"``) when ``reason`` is ``INVALID_SCHEMA``.
            Empty for ``INVALID_JSON``.
            The list is capped at ``_MAX_EXPOSED_ERRORS`` entries.

    The ``__cause__`` attribute preserves the original exception
    (``json.JSONDecodeError`` or ``pydantic.ValidationError``) as an
    internal cause. Callers must not expose ``__cause__`` in user-facing
    messages or logs — it may contain raw input values.
    """

    def __init__(
        self,
        reason: ValidationFailureReason,
        *,
        error_count: int = 0,
        field_locations: list[str] | None = None,
        error_types: list[str] | None = None,
    ) -> None:
        self.reason = reason
        self.error_count = error_count
        self.field_locations = field_locations or []
        self.error_types = error_types or []
        super().__init__(
            f"Structured output validation failed: {reason.value}"
        )

    def __str__(self) -> str:
        """Safe string representation — no raw input values."""
        parts = [f"Structured output validation failed: {self.reason.value}"]
        if self.error_count > 0:
            parts.append(f"error_count={self.error_count}")
        if self.field_locations:
            parts.append(f"field_locations={self.field_locations}")
        if self.error_types:
            parts.append(f"error_types={self.error_types}")
        return ", ".join(parts)


def _sanitize_location_component(component: Any) -> str:
    """Sanitize a single Pydantic error location component.

    Known schema field names are returned as-is. Integer list indices
    are returned as their string representation. Any other string
    component — including input-controlled extra-field names — is
    replaced with ``_UNKNOWN_MARKER`` to prevent input-controlled text
    from entering exception metadata or logs.

    Components longer than ``_MAX_LOC_COMPONENT_LENGTH`` are truncated
    and marked, even if they are known field names (defensive).

    Args:
        component: A single element from a Pydantic error ``loc`` tuple.

    Returns:
        A safe, bounded string representation of the component.
    """
    if isinstance(component, int):
        return str(component)

    text = str(component)

    if len(text) > _MAX_LOC_COMPONENT_LENGTH:
        return _UNKNOWN_MARKER

    if text in _KNOWN_FIELD_NAMES:
        return text

    return _UNKNOWN_MARKER


def _sanitize_field_location(loc: tuple[Any, ...]) -> str:
    """Sanitize a full Pydantic error location path.

    Each component is individually sanitized via
    :func:`_sanitize_location_component`. Components are joined with
    ``"."`` to produce a dotted path string.

    Args:
        loc: The ``loc`` tuple from a Pydantic validation error.

    Returns:
        A safe, bounded field-location string such as
        ``"risks.0.sources"`` or ``"<extra>"``.
    """
    if not loc:
        return ""
    parts = [_sanitize_location_component(c) for c in loc]
    return ".".join(parts)


def _extract_safe_error_info(exc: ValidationError) -> tuple[int, list[str], list[str]]:
    """Extract safe, bounded metadata from a Pydantic ValidationError.

    Returns:
        A tuple of (error_count, field_locations, error_types).

        - ``error_count`` is the total number of validation errors
          (uncapped).
        - ``field_locations`` is a list of sanitized, bounded
          field-location strings, capped at ``_MAX_EXPOSED_ERRORS``
          entries. Each location contains only known schema field
          names, integer indices, or the neutral marker ``<extra>``.
        - ``error_types`` is a list of safe Pydantic error-type
          strings, capped at ``_MAX_EXPOSED_ERRORS`` entries.

    Field locations and error types are safe to log because they
    contain only field paths and type names — never raw input values
    or input-controlled field names.
    """
    errors = exc.errors()
    error_count = len(errors)

    # Cap the number of exposed detail entries.
    exposed_errors = errors[:_MAX_EXPOSED_ERRORS]

    field_locations: list[str] = []
    error_types: list[str] = []

    for err in exposed_errors:
        loc = err.get("loc", ())
        field_locations.append(_sanitize_field_location(tuple(loc)))

        err_type = err.get("type", "unknown")
        error_types.append(str(err_type))

    return error_count, field_locations, error_types


def validate_structured_output(content: str) -> RecommendationData:
    """Validate AI model output against the structured recommendation schema.

    This is a pure function. It performs no persistence, no workflow-state
    mutation, and no write actions. It only parses and validates.

    Args:
        content: The ``ChatResult.content`` string from the AI provider.
            Must be a JSON string matching the recommendation wire schema
            (SoT 02 §6, schema version ``"1.0"``).

    Returns:
        The validated :class:`RecommendationData` on success.

    Raises:
        StructuredOutputValidationError: If the content is not valid JSON
            (``reason=INVALID_JSON``) or if it is valid JSON but does not
            match the recommendation schema (``reason=INVALID_SCHEMA``).
            This is the single exception type the future 03F caller
            catches to map to ``FAILED_VALIDATION``.

    Notes:
        - Raw model output is never included in the exception's public
          message, ``reason``, ``field_locations``, or ``error_types``.
        - The original exception (``json.JSONDecodeError`` or
          ``pydantic.ValidationError``) is preserved as ``__cause__``
          for debugging but must not be exposed in user-facing messages
          or logs.
        - Success logs contain only safe metadata: schema version and
          risk count. Failure logs contain only bounded, sanitized
          metadata: failure classification, error count, field
          locations, and Pydantic error types.
        - If the caller needs correlation-ID or run-ID logging, those
          must be supplied by the future 03F caller's context. This pure
          validator does not receive or invent correlation context to
          avoid inappropriate dependencies.
    """
    # Step 1: Parse JSON.
    try:
        parsed: Any = json.loads(content)
    except (json.JSONDecodeError, TypeError) as exc:
        failure = StructuredOutputValidationError(
            ValidationFailureReason.INVALID_JSON,
        )
        failure.__cause__ = exc
        _logger.warning(
            "structured_output.validation.failed",
            reason=ValidationFailureReason.INVALID_JSON.value,
        )
        raise failure from exc

    # Step 2: Validate against the recommendation Pydantic schema.
    try:
        recommendation = RecommendationData.model_validate(parsed)
    except ValidationError as exc:
        error_count, field_locations, error_types = _extract_safe_error_info(exc)
        failure = StructuredOutputValidationError(
            ValidationFailureReason.INVALID_SCHEMA,
            error_count=error_count,
            field_locations=field_locations,
            error_types=error_types,
        )
        failure.__cause__ = exc
        _logger.warning(
            "structured_output.validation.failed",
            reason=ValidationFailureReason.INVALID_SCHEMA.value,
            error_count=error_count,
            field_locations=field_locations,
            error_types=error_types,
        )
        raise failure from exc

    # Step 3: Log success with safe metadata only.
    _logger.info(
        "structured_output.validation.succeeded",
        schema_version=recommendation.schema_version,
        risk_count=len(recommendation.risks),
    )

    return recommendation
