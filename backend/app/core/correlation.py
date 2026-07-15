"""Correlation ID utilities for request tracing.

Provides generation, validation, and normalization of UUID v4 correlation IDs.
Framework-independent — no FastAPI or global state dependencies.
"""

from __future__ import annotations

import uuid

# Canonical HTTP header name for correlation ID
CORRELATION_HEADER: str = "X-Correlation-ID"


class InvalidCorrelationIdError(ValueError):
    """Raised when a correlation ID is malformed or not a valid UUID v4."""


def generate_correlation_id() -> str:
    """Generate a new UUID v4 correlation ID.

    Returns:
        Canonical lowercase UUID v4 string.
    """
    return str(uuid.uuid4())


def validate_correlation_id(value: str) -> str:
    """Validate and normalize a supplied correlation ID.

    Accepts a string that is a valid UUID v4 (case-insensitive, with or
    without hyphens) and returns the canonical lowercase hyphenated form.

    Args:
        value: The correlation ID string to validate.

    Returns:
        Canonical lowercase UUID v4 string.

    Raises:
        InvalidCorrelationIdError: If the value is not a valid UUID v4.
    """
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise InvalidCorrelationIdError(
            f"Invalid correlation ID: {value!r} is not a valid UUID v4"
        ) from exc

    if parsed.version != 4:
        raise InvalidCorrelationIdError(
            f"Invalid correlation ID: {value!r} is not a UUID v4 (got version {parsed.version})"
        )

    return str(parsed)
