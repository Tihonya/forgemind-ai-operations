"""Tests for structured logging configuration."""

from __future__ import annotations

import importlib
import io
import json
import logging
import sys
from typing import Any

import pytest

import app.core.logging as logging_module
from app.core.logging import configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset_logging_module() -> None:
    """Reset the logging module's configured state between tests."""
    import structlog

    # Reload the module to reset _MANAGED_HANDLER to None.
    importlib.reload(logging_module)
    structlog.reset_defaults()

    # Remove handlers we may have added in prior tests.
    root = logging.getLogger()
    for handler in root.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and not _is_pytest_handler(handler):
            root.removeHandler(handler)

    yield

    # Post-test cleanup — remove managed handlers.
    for handler in root.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and not _is_pytest_handler(handler):
            root.removeHandler(handler)


def _is_pytest_handler(handler: logging.Handler) -> bool:
    """Check if a handler belongs to pytest's logging plugin."""
    return type(handler).__module__.startswith("_pytest")


def _capture_log_output(
    configure_kwargs: dict[str, Any] | None = None,
) -> io.StringIO:
    """Configure logging with stderr captured and return the buffer.

    Only redirects the managed handler's stream to the buffer;
    pytest's own handlers are left alone so they don't pollute our output.
    """
    buffer = io.StringIO()
    # Patch stderr before configuring so the StreamHandler writes to our buffer.
    original_stderr = sys.stderr
    sys.stderr = buffer
    try:
        configure_logging(**(configure_kwargs or {}))
    finally:
        sys.stderr = original_stderr

    # Only redirect the managed handler (not pytest's handlers).
    # Access via module reference to get the live value.
    managed = logging_module._MANAGED_HANDLER
    if managed is not None:
        managed.stream = buffer
    return buffer


def _parse_log_line(line: str) -> dict[str, Any]:
    """Parse a JSON log line from captured output."""
    stripped = line.strip()
    if not stripped:
        return {}
    return json.loads(stripped)


class TestImportSafety:
    """Import must not configure or emit logs."""

    def test_import_does_not_emit_logs(self, capsys: pytest.CaptureFixture[str]) -> None:
        importlib.reload(logging_module)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""

    def test_import_does_not_set_managed_handler(self) -> None:
        """Importing the module does not trigger side-effect configuration."""
        importlib.reload(logging_module)
        assert logging_module._MANAGED_HANDLER is None


class TestConfigureLogging:
    """Tests for configure_logging()."""

    def test_produces_valid_json(self) -> None:
        buffer = _capture_log_output()
        logger = get_logger()
        logger.info("test event")
        record = _parse_log_line(buffer.getvalue())
        assert record

    def test_json_contains_event_level_timestamp(self) -> None:
        buffer = _capture_log_output()
        logger = get_logger()
        logger.info("hello world")
        record = _parse_log_line(buffer.getvalue())
        assert record["event"] == "hello world"
        assert record["level"] == "info"
        assert "timestamp" in record
        # ISO-8601 check: contains T separator.
        assert "T" in record["timestamp"]

    def test_logger_name_included(self) -> None:
        buffer = _capture_log_output()
        logger = get_logger("my.module.name")
        logger.info("named logger test")
        record = _parse_log_line(buffer.getvalue())
        assert record.get("logger") == "my.module.name"

    def test_arbitrary_fields_preserved(self) -> None:
        buffer = _capture_log_output()
        logger = get_logger()
        logger.info("with fields", user_id=42, action="deploy", region="eu-west")
        record = _parse_log_line(buffer.getvalue())
        assert record["user_id"] == 42
        assert record["action"] == "deploy"
        assert record["region"] == "eu-west"

    def test_correlation_id_preserved(self) -> None:
        buffer = _capture_log_output()
        logger = get_logger()
        cid = "550e8400-e29b-41d4-a716-446655440000"
        logger.info("with correlation", correlation_id=cid)
        record = _parse_log_line(buffer.getvalue())
        assert record["correlation_id"] == cid

    def test_level_filtering_works(self) -> None:
        buffer = _capture_log_output({"level": "WARNING"})
        logger = get_logger()
        logger.debug("should not appear")
        logger.info("should not appear either")
        logger.warning("this should appear")
        lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 1
        record = _parse_log_line(lines[0])
        assert record["event"] == "this should appear"
        assert record["level"] == "warning"

    def test_exception_info_serialized(self) -> None:
        buffer = _capture_log_output()
        logger = get_logger()
        try:
            raise ValueError("test error details here")
        except ValueError:
            logger.exception("operation failed")

        record = _parse_log_line(buffer.getvalue())
        assert record["event"] == "operation failed"
        assert record["level"] == "error"
        # structlog's format_exc_info renders into the "exception" field.
        exception_text = record.get("exception") or record.get("exc_info")
        assert exception_text is not None, f"No exception field in: {record}"
        assert "ValueError" in str(exception_text)
        assert "test error details here" in str(exception_text)

    def test_no_duplicate_output_after_reconfigure(self) -> None:
        """Two configure_logging calls produce exactly one log line."""
        configure_logging(level="INFO")
        configure_logging(level="WARNING")

        # Access via module reference to get the live value.
        managed = logging_module._MANAGED_HANDLER
        assert managed is not None, "configure_logging should set _MANAGED_HANDLER"
        buffer = io.StringIO()
        managed.stream = buffer

        logger = get_logger()
        logger.warning("single event")

        lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 1, f"Expected 1 log line, got {len(lines)}: {lines}"
        record = _parse_log_line(lines[0])
        assert record["event"] == "single event"

    def test_reconfigure_updates_log_level_down(self) -> None:
        """INFO -> WARNING reconfiguration filters lower-level events."""
        configure_logging(level="INFO")
        configure_logging(level="WARNING")

        managed = logging_module._MANAGED_HANDLER
        assert managed is not None
        buffer = io.StringIO()
        managed.stream = buffer

        logger = get_logger()
        logger.info("should be filtered")
        logger.warning("should appear")

        lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 1
        record = _parse_log_line(lines[0])
        assert record["event"] == "should appear"
        assert record["level"] == "warning"

    def test_reconfigure_updates_log_level_up(self) -> None:
        """WARNING -> DEBUG reconfiguration makes lower-level events visible."""
        configure_logging(level="WARNING")
        configure_logging(level="DEBUG")

        managed = logging_module._MANAGED_HANDLER
        assert managed is not None
        buffer = io.StringIO()
        managed.stream = buffer

        logger = get_logger()
        logger.debug("now visible")
        logger.info("also visible")
        logger.warning("still visible")

        lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 3
        events = [_parse_log_line(ln)["event"] for ln in lines]
        assert events == ["now visible", "also visible", "still visible"]

    def test_no_duplicate_managed_handlers_after_reconfigure(self) -> None:
        """Multiple configure_logging calls do not add duplicate handlers."""
        # Initial config + several reconfigurations.
        configure_logging(level="INFO")
        configure_logging(level="DEBUG")
        configure_logging(level="WARNING")
        configure_logging(level="INFO")

        # Count StreamHandlers we manage (exclude pytest).
        root = logging.getLogger()
        our_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not _is_pytest_handler(h)
        ]
        assert len(our_handlers) == 1, (
            f"Expected 1 managed handler, got {len(our_handlers)}"
        )

    def test_reconfigure_produces_exactly_one_line(self) -> None:
        """After several reconfigurations, a single log call yields one line."""
        configure_logging(level="INFO")
        configure_logging(level="WARNING")
        configure_logging(level="DEBUG")
        configure_logging(level="INFO")

        managed = logging_module._MANAGED_HANDLER
        assert managed is not None
        buffer = io.StringIO()
        managed.stream = buffer

        logger = get_logger()
        logger.info("exactly one")

        lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 1
        record = _parse_log_line(lines[0])
        assert record["event"] == "exactly one"

    def test_reconfigure_preserves_json_pipeline(self) -> None:
        """After reconfiguration, output is still structured JSON with all fields."""
        configure_logging(level="WARNING")
        configure_logging(level="INFO")  # reconfigure.

        managed = logging_module._MANAGED_HANDLER
        assert managed is not None
        buffer = io.StringIO()
        managed.stream = buffer

        logger = get_logger("reconfig.check")
        logger.info("after reconfig", request_id="r-1")

        lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 1
        record = _parse_log_line(lines[0])
        assert record["event"] == "after reconfig"
        assert record["level"] == "info"
        assert "timestamp" in record
        assert record["logger"] == "reconfig.check"
        assert record["request_id"] == "r-1"

    def test_level_is_lowercase(self) -> None:
        buffer = _capture_log_output()
        logger = get_logger()
        logger.error("an error")
        record = _parse_log_line(buffer.getvalue())
        assert record["level"] == "error"
        assert record["level"] == record["level"].lower()


class TestStdlibLoggingCompatibility:
    """Verify that stdlib logging.getLogger() also produces structured JSON."""

    def test_stdlib_logger_produces_json(self) -> None:
        configure_logging()
        managed = logging_module._MANAGED_HANDLER
        assert managed is not None
        buffer = io.StringIO()
        managed.stream = buffer

        stdlib_logger = logging.getLogger("test.stdlib.module")
        stdlib_logger.info("stdlib structured event")

        lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 1
        record = _parse_log_line(lines[0])
        assert record["event"] == "stdlib structured event"
        assert record["level"] == "info"
        assert "timestamp" in record
        assert record["logger"] == "test.stdlib.module"

    def test_stdlib_logger_level_filtering(self) -> None:
        configure_logging(level="ERROR")
        managed = logging_module._MANAGED_HANDLER
        assert managed is not None
        buffer = io.StringIO()
        managed.stream = buffer

        stdlib_logger = logging.getLogger("test.stdlib.filtered")
        stdlib_logger.info("should be filtered")
        stdlib_logger.error("should appear")

        lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 1
        record = _parse_log_line(lines[0])
        assert record["event"] == "should appear"
        assert record["level"] == "error"

    def test_stdlib_exception_serialization(self) -> None:
        configure_logging()
        managed = logging_module._MANAGED_HANDLER
        assert managed is not None
        buffer = io.StringIO()
        managed.stream = buffer

        stdlib_logger = logging.getLogger("test.stdlib.exception")
        try:
            raise RuntimeError("stdlib test failure")
        except RuntimeError:
            stdlib_logger.exception("stdlib op failed")

        record = _parse_log_line(buffer.getvalue())
        assert record["event"] == "stdlib op failed"
        assert record["level"] == "error"
        exception_text = record.get("exception") or record.get("exc_info")
        assert exception_text is not None, f"No exception field in: {record}"
        assert "RuntimeError" in str(exception_text)
        assert "stdlib test failure" in str(exception_text)
