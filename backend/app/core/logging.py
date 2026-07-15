"""Structured logging configuration for ForgeMind backend.

Provides a small, typed API for configuring structlog-based JSON logging
with ISO-8601 UTC timestamps and normalized lowercase log levels.
Stdlib `logging` and structlog share the same processor pipeline so all
output is consistently structured.

Usage:
    from app.core.logging import configure_logging, get_logger

    configure_logging(level="INFO")
    logger = get_logger("my.module")
    logger.info("operation started", correlation_id="abc-123")

This module is framework-independent. It does not configure automatically
on import and does not bind to FastAPI/Uvicorn.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def _lower_log_level(
    logger: Any,  # noqa: ARG001
    method_name: str,  # noqa: ARG001
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Normalize the log level to lowercase."""
    level = event_dict.get("level")
    if isinstance(level, str):
        event_dict["level"] = level.lower()
    return event_dict


def _ensure_event_field(
    logger: Any,  # noqa: ARG001
    method_name: str,  # noqa: ARG001
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Ensure the event field is always present even if empty."""
    if "event" not in event_dict:
        event_dict["event"] = ""
    return event_dict


# Shared processor chain used by both stdlib and structlog.
# Use list[Any] to avoid mypy conflicts with structlog's complex Processor alias.
# merge_contextvars is the first processor — it merges structlog contextvars
# (including correlation_id bound via app.core.context) into the event dict.
_SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    _lower_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
    structlog.processors.UnicodeDecoder(),
    _ensure_event_field,
]


# Track the managed handler for safe reconfiguration.
# Use Any to avoid mypy generic type argument issues with StreamHandler.
_MANAGED_HANDLER: Any = None


def configure_logging(*, level: str | int = "INFO") -> None:
    """Configure the root logger and structlog for JSON structured output.

    Safe to call multiple times. Repeated calls will reuse the existing
    managed handler (no duplicates) and update the effective log level.

    Args:
        level: The minimum log level. Accepts the same values as
            ``logging.getLogger().setLevel`` (e.g., ``"INFO"``,
            ``"DEBUG"``, ``logging.WARNING``).
    """
    global _MANAGED_HANDLER  # noqa: PLW0603

    # Resolve numeric level for the root logger.
    numeric_level = level if isinstance(level, int) else getattr(logging, str(level).upper())

    # Shared processors, terminated by JSONRenderer for structlog;
    # the formatter terminates with JSONRenderer for stdlib.
    json_renderer = structlog.processors.JSONRenderer()

    # Configure the stdlib root logger with ProcessorFormatter so
    # both stdlib and structlog output flow through the same processors.
    shared_processors: list[Any] = list(_SHARED_PROCESSORS)

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            json_renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    # Reuse existing managed handler if present, otherwise create new.
    handler = _MANAGED_HANDLER
    if handler is None:
        handler = logging.StreamHandler(sys.stderr)
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        _MANAGED_HANDLER = handler

    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Bind structlog to stdlog so get_logger() returns a stdlib-backed logger.
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )


def get_logger(name: str | None = None) -> Any:
    """Return a structured logger bound to the given name.

    Args:
        name: Optional logger name. If ``None``, the root logger is used.

    Returns:
        A bound logger (structlog.stdlib.BoundLogger) that emits structured JSON records.
    """
    if name is None:
        return structlog.get_logger()
    return structlog.get_logger(name)
