"""Request context binding for correlation IDs.

Provides a typed API for binding, querying, and clearing correlation IDs
from the current async context. Uses ``structlog.contextvars`` primitives
exclusively for context storage so that :func:`structlog.contextvars.merge_contextvars`
includes the bound correlation_id in every structured log record.

Usage:
    from app.core.context import bind_correlation_id, get_correlation_id

    # Bind a correlation ID
    bind_correlation_id("550e8400-e29b-41d4-a716-446655440000")

    # Get current correlation ID (canonical form, or None)
    get_correlation_id()

    # Clear
    clear_correlation_id()

    # Context manager (nested contexts restore previous value;
    # None generates a new UUID v4)
    with correlation_context("550e8400-e29b-41d4-a716-446655440000") as cid:
        # correlation_id is bound here
        pass
    # correlation_id restored or cleared

    # Generate new correlation ID
    with correlation_context() as cid:
        # cid is a new UUID v4
        pass

This module does not depend on FastAPI or any web framework.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from structlog.contextvars import (
    bind_contextvars,
    bound_contextvars,
    get_contextvars,
    unbind_contextvars,
)

from app.core.correlation import generate_correlation_id, validate_correlation_id


def bind_correlation_id(value: str) -> str:
    """Bind a correlation ID to the current async context.

    The supplied value is validated and canonicalised through
    :func:`app.core.correlation.validate_correlation_id` (UUID v4 only).

    After this call, every structured log record emitted in the same task
    (including through stdlib ``logging``) includes ``correlation_id`` via
    the ``merge_contextvars`` logging processor.

    Args:
        value: Correlation ID string. Must be a valid UUID v4.

    Returns:
        The validated canonical lowercase UUID v4 string.

    Raises:
        InvalidCorrelationIdError: If value is not a valid UUID v4.
    """
    canonical = validate_correlation_id(value)
    bind_contextvars(correlation_id=canonical)
    return canonical


def get_correlation_id() -> str | None:
    """Return the current correlation ID, or None if not bound.

    Returns:
        Canonical lowercase UUID v4 string, or None.
    """
    return get_contextvars().get("correlation_id")


def clear_correlation_id() -> None:
    """Clear the correlation ID from the current async context.

    After this call :func:`get_correlation_id` returns None within the same
    task, and log records no longer include ``correlation_id``.

    Concurrent tasks are unaffected — each task has its own context.
    """
    unbind_contextvars("correlation_id")


@contextmanager
def correlation_context(value: str | None = None) -> Generator[str, None, None]:
    """Context manager that binds a correlation ID and restores previous state.

    On ``__exit__`` the context is restored to its state at entry time:

    - If the key was bound before entry with another value, that value is
      restored (nested contexts).
    - If the key was not bound before entry, the key is removed.

    Args:
        value: Correlation ID to bind. If ``None``, a new UUID v4 is generated
            via :func:`app.core.correlation.generate_correlation_id`.

    Yields:
        The bound correlation ID in canonical form.

    Raises:
        InvalidCorrelationIdError: If a non-None value is not valid UUID v4.
    """
    canonical = validate_correlation_id(value) if value is not None else generate_correlation_id()
    with bound_contextvars(correlation_id=canonical):
        yield canonical
