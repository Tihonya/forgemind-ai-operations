"""Tests for request context correlation ID binding."""

from __future__ import annotations

import asyncio
import io
import json
import sys
from typing import Any

import pytest

from app.core.context import (
    bind_correlation_id,
    clear_correlation_id,
    correlation_context,
    get_correlation_id,
)
from app.core.correlation import InvalidCorrelationIdError, generate_correlation_id


@pytest.fixture(autouse=True)
def _clear_context() -> None:
    """Ensure clean structlog contextvars before and after each test."""
    from structlog.contextvars import clear_contextvars

    clear_contextvars()
    yield
    clear_contextvars()


def _capture_log_output(fn: Any) -> dict[str, Any]:
    """Configure logging, call fn, capture and return one JSON record."""
    import importlib
    import logging

    import app.core.logging as logging_module  # noqa: I001
    from app.core.logging import configure_logging, get_logger

    # Reset logging state
    importlib.reload(logging_module)
    from structlog import reset_defaults

    reset_defaults()

    # Configure with buffer capture
    root = logging.getLogger()
    for h in root.handlers[:]:
        if isinstance(h, logging.StreamHandler) and not type(h).__module__.startswith(
            "_pytest"
        ):
            root.removeHandler(h)

    buffer = io.StringIO()
    original_stderr = sys.stderr
    sys.stderr = buffer
    try:
        configure_logging()
    finally:
        sys.stderr = original_stderr

    managed = logging_module._MANAGED_HANDLER
    if managed is not None:
        managed.stream = buffer

    # Call function that logs
    logger = get_logger("test.context")
    fn(logger)

    lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
    assert len(lines) >= 1
    return json.loads(lines[0])


class TestBindCorrelationId:
    """Tests for bind_correlation_id()."""

    def test_valid_uuid_v4_binding(self) -> None:
        cid = generate_correlation_id()
        result = bind_correlation_id(cid)
        assert result == cid
        assert get_correlation_id() == cid

    def test_returns_canonical_form(self) -> None:
        cid_upper = "550E8400-E29B-41D4-A716-446655440000"
        result = bind_correlation_id(cid_upper)
        assert result == "550e8400-e29b-41d4-a716-446655440000"
        assert get_correlation_id() == result

    def test_rejects_malformed_string(self) -> None:
        with pytest.raises(InvalidCorrelationIdError):
            bind_correlation_id("not-a-uuid")

    def test_rejects_non_v4_uuid(self) -> None:
        # UUID v1
        v1 = "550e8400-e29b-11d4-a716-446655440000"
        with pytest.raises(InvalidCorrelationIdError):
            bind_correlation_id(v1)

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(InvalidCorrelationIdError):
            bind_correlation_id("")

    def test_bind_overwrites_previous(self) -> None:
        cid1 = generate_correlation_id()
        cid2 = generate_correlation_id()
        bind_correlation_id(cid1)
        assert get_correlation_id() == cid1
        bind_correlation_id(cid2)
        assert get_correlation_id() == cid2


class TestGetCorrelationId:
    """Tests for get_correlation_id()."""

    def test_returns_none_before_binding(self) -> None:
        assert get_correlation_id() is None

    def test_returns_bound_value(self) -> None:
        cid = generate_correlation_id()
        bind_correlation_id(cid)
        assert get_correlation_id() == cid

    def test_returns_none_after_clear(self) -> None:
        cid = generate_correlation_id()
        bind_correlation_id(cid)
        clear_correlation_id()
        assert get_correlation_id() is None


class TestClearCorrelationId:
    """Tests for clear_correlation_id()."""

    def test_clear_removes_value(self) -> None:
        cid = generate_correlation_id()
        bind_correlation_id(cid)
        assert get_correlation_id() == cid
        clear_correlation_id()
        assert get_correlation_id() is None

    def test_clear_when_not_bound_is_safe(self) -> None:
        # Should not raise
        clear_correlation_id()
        assert get_correlation_id() is None


class TestCorrelationContext:
    """Tests for correlation_context() context manager."""

    def test_context_manager_clears_after_exit(self) -> None:
        cid = generate_correlation_id()
        with correlation_context(cid) as bound:
            assert bound == cid
            assert get_correlation_id() == cid
        # After exit, should be cleared
        assert get_correlation_id() is None

    def test_nested_context_restores_previous_value(self) -> None:
        cid_outer = generate_correlation_id()
        cid_inner = generate_correlation_id()

        with correlation_context(cid_outer):
            assert get_correlation_id() == cid_outer
            with correlation_context(cid_inner):
                assert get_correlation_id() == cid_inner
            # After inner exits, outer value restored
            assert get_correlation_id() == cid_outer
        # After outer exits, cleared
        assert get_correlation_id() is None

    def test_none_generates_new_uuid_v4(self) -> None:
        """When value=None, a new UUID v4 is generated."""
        with correlation_context() as cid:
            assert cid is not None
            # Must be valid UUID v4 format
            import uuid

            parsed = uuid.UUID(cid)
            assert parsed.version == 4
            assert get_correlation_id() == cid
        # After exit, cleared
        assert get_correlation_id() is None

    def test_none_generates_distinct_uuids(self) -> None:
        """Each call with None generates a distinct UUID."""
        with correlation_context() as cid1:
            pass
        with correlation_context() as cid2:
            assert cid2 != cid1

    def test_restores_outer_even_when_inner_is_none(self) -> None:
        """correlation_context(None) still generates new UUID and restores outer."""
        cid_outer = generate_correlation_id()
        with correlation_context(cid_outer):
            with correlation_context() as cid_inner:
                assert get_correlation_id() == cid_inner
                assert cid_inner != cid_outer
            # Outer restored
            assert get_correlation_id() == cid_outer
        assert get_correlation_id() is None

    def test_restores_on_exception(self) -> None:
        """Context restores previous value when the wrapped block raises."""
        cid_outer = generate_correlation_id()
        cid_inner = generate_correlation_id()

        with correlation_context(cid_outer):
            assert get_correlation_id() == cid_outer

            with pytest.raises(RuntimeError), correlation_context(cid_inner):
                assert get_correlation_id() == cid_inner
                raise RuntimeError("simulated failure")

            # Outer restored after exception
            assert get_correlation_id() == cid_outer
        # Outer cleared after exit
        assert get_correlation_id() is None

    def test_restores_to_none_on_exception(self) -> None:
        """When nothing was bound before entering, exception restores None."""
        cid = generate_correlation_id()
        with pytest.raises(ValueError), correlation_context(cid):
            assert get_correlation_id() == cid
            raise ValueError("test")
        assert get_correlation_id() is None

    def test_rejects_invalid_uuid(self) -> None:
        with (
            pytest.raises(InvalidCorrelationIdError), correlation_context("invalid"),
        ):
            pass  # pragma: no cover

    def test_yields_str_not_none(self) -> None:
        """The yielded value is always a str (never None)."""
        # With explicit value
        cid = generate_correlation_id()
        with correlation_context(cid) as bound:
            assert isinstance(bound, str)
            assert bound == cid

        # With None (auto-generated)
        with correlation_context() as bound:
            assert isinstance(bound, str)
            assert len(bound) == 36  # canonical UUID v4


class TestAsyncPropagation:
    """Tests for async task isolation and propagation."""

    @pytest.mark.asyncio
    async def test_propagation_through_awaited_calls(self) -> None:
        """Correlation ID propagates through await calls in same task."""
        cid = generate_correlation_id()

        async def inner() -> str | None:
            return get_correlation_id()

        bind_correlation_id(cid)
        result = await inner()
        assert result == cid

    @pytest.mark.asyncio
    async def test_isolation_between_concurrent_tasks(self) -> None:
        """Each concurrent task has isolated correlation ID context."""
        cid_task1 = generate_correlation_id()
        cid_task2 = generate_correlation_id()
        results: dict[str, str | None] = {}

        async def task1() -> None:
            bind_correlation_id(cid_task1)
            await asyncio.sleep(0.01)  # Yield control
            results["task1"] = get_correlation_id()

        async def task2() -> None:
            bind_correlation_id(cid_task2)
            await asyncio.sleep(0.01)  # Yield control
            results["task2"] = get_correlation_id()

        # Run tasks concurrently
        await asyncio.gather(task1(), task2())

        # Each task sees its own correlation ID
        assert results["task1"] == cid_task1
        assert results["task2"] == cid_task2
        # Main task is unaffected
        assert get_correlation_id() is None

    @pytest.mark.asyncio
    async def test_context_manager_in_async(self) -> None:
        """correlation_context works correctly in async context."""
        cid = generate_correlation_id()

        with correlation_context(cid):
            assert get_correlation_id() == cid
            await asyncio.sleep(0)  # Yield control
            assert get_correlation_id() == cid
        assert get_correlation_id() is None

    @pytest.mark.asyncio
    async def test_cleared_context_isolated_per_task(self) -> None:
        """Clearing in one task does not affect other tasks."""
        cid = generate_correlation_id()
        results: dict[str, str | None] = {}

        async def task_clears() -> None:
            bind_correlation_id(cid)
            clear_correlation_id()
            results["task_that_cleared"] = get_correlation_id()

        async def task_doesnt_clear() -> None:
            bind_correlation_id(cid)
            await asyncio.sleep(0.01)  # Yield control
            results["task_that_kept"] = get_correlation_id()

        await asyncio.gather(task_clears(), task_doesnt_clear())
        assert results["task_that_cleared"] is None
        assert results["task_that_kept"] == cid


class TestExplicitFieldPrecedence:
    """Explicit kwarg correlation_id=... must not be overwritten by bound context.

    This is guaranteed by merge_contextvars using event_dict.setdefault(),
    so explicit kwargs (already in the event dict) win over bound context.
    """

    def test_explicit_field_wins_over_bound_context(self) -> None:
        bound_cid = generate_correlation_id()
        explicit_cid = generate_correlation_id()
        bind_correlation_id(bound_cid)

        record = _capture_log_output(
            lambda logger: logger.info("explicit", correlation_id=explicit_cid)
        )
        # Explicit kwarg wins
        assert record["correlation_id"] == explicit_cid

    def test_bound_context_used_when_no_explicit(self) -> None:
        bound_cid = generate_correlation_id()
        bind_correlation_id(bound_cid)

        record = _capture_log_output(lambda logger: logger.info("no explicit"))
        assert record["correlation_id"] == bound_cid


class TestStructlogIntegration:
    """Tests that correlation_id appears in structured logs automatically."""

    def test_correlation_id_in_structlog_json(self) -> None:
        """When bound, correlation_id appears in JSON log output."""
        cid = generate_correlation_id()
        bind_correlation_id(cid)

        record = _capture_log_output(lambda logger: logger.info("test event"))
        assert "correlation_id" in record
        assert record["correlation_id"] == cid

    def test_no_correlation_id_when_not_bound(self) -> None:
        """When not bound, correlation_id does not appear in logs."""
        record = _capture_log_output(lambda logger: logger.info("no context"))
        assert "correlation_id" not in record

    def test_correlation_id_updates_after_rebind(self) -> None:
        """Rebinding updates the correlation_id in logs."""
        cid1 = generate_correlation_id()
        bind_correlation_id(cid1)
        record1 = _capture_log_output(lambda logger: logger.info("first"))
        assert record1["correlation_id"] == cid1

        cid2 = generate_correlation_id()
        bind_correlation_id(cid2)
        record2 = _capture_log_output(lambda logger: logger.info("second"))
        assert record2["correlation_id"] == cid2
        assert record2["correlation_id"] != cid1

    def test_correlation_id_absent_after_clear(self) -> None:
        """After clear, correlation_id no longer appears."""
        cid = generate_correlation_id()
        bind_correlation_id(cid)
        record1 = _capture_log_output(lambda logger: logger.info("before clear"))
        assert "correlation_id" in record1

        clear_correlation_id()
        record2 = _capture_log_output(lambda logger: logger.info("after clear"))
        assert "correlation_id" not in record2


class TestStdlibIntegration:
    """stdlib logging.getLogger also inherits context via ProcessorFormatter.

    The pipeline places merge_contextvars in the shared processor chain,
    and the ProcessorFormatter's foreign_pre_chain also uses these same
    processors — so stdlib records include correlation_id.
    """

    def test_stdlib_logger_includes_correlation_id(self) -> None:
        """stdlib logging.getLogger includes correlation_id when bound."""
        import importlib
        import logging

        from structlog import reset_defaults

        import app.core.logging as logging_module  # noqa: I001
        from app.core.logging import configure_logging

        importlib.reload(logging_module)
        reset_defaults()

        root = logging.getLogger()
        for h in root.handlers[:]:
            if isinstance(h, logging.StreamHandler) and not type(h).__module__.startswith(
                "_pytest"
            ):
                root.removeHandler(h)

        cid = generate_correlation_id()
        bind_correlation_id(cid)

        buffer = io.StringIO()
        original_stderr = sys.stderr
        sys.stderr = buffer
        try:
            configure_logging()
        finally:
            sys.stderr = original_stderr

        managed = logging_module._MANAGED_HANDLER
        if managed is not None:
            managed.stream = buffer

        stdlib_logger = logging.getLogger("test.stdlib.context")
        stdlib_logger.info("stdlib with context")

        lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
        assert len(lines) >= 1
        record = json.loads(lines[0])
        assert "correlation_id" in record
        assert record["correlation_id"] == cid


class TestLoggingReconfigurationRegression:
    """Verify context merging still works after repeated logging reconfiguration."""

    def test_context_merging_survives_reconfigure(self) -> None:
        """After multiple configure_logging calls, context still merges once."""
        cid = generate_correlation_id()
        bind_correlation_id(cid)

        # Reconfigure multiple times
        from app.core.logging import configure_logging

        configure_logging()
        configure_logging()
        configure_logging()

        record = _capture_log_output(lambda logger: logger.info("after reconfigure"))
        assert record["correlation_id"] == cid

        # Verify exactly one correlation_id (no duplicates in processors)
        assert record.get("correlation_id", "X") == cid
        # No list-valued correlation_id (would indicate duplicate merge)
        assert not isinstance(record["correlation_id"], list)

    def test_reconfigure_no_duplicate_handlers(self) -> None:
        """Context merging still works without handler duplication."""
        import importlib
        import logging

        from structlog import reset_defaults

        import app.core.logging as logging_module  # noqa: I001
        from app.core.logging import configure_logging, get_logger

        importlib.reload(logging_module)
        reset_defaults()

        root = logging.getLogger()
        for h in root.handlers[:]:
            if isinstance(h, logging.StreamHandler) and not type(h).__module__.startswith(
                "_pytest"
            ):
                root.removeHandler(h)

        configure_logging()
        configure_logging()
        configure_logging()

        # Count managed handlers
        managed_handlers = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler)
            and not type(h).__module__.startswith("_pytest")
        ]
        assert len(managed_handlers) == 1

        # Verify context merge works
        cid = generate_correlation_id()
        bind_correlation_id(cid)
        buffer = io.StringIO()
        logging_module._MANAGED_HANDLER.stream = buffer

        logger = get_logger()
        logger.info("single line")

        lines = [ln for ln in buffer.getvalue().splitlines() if ln.strip()]
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["correlation_id"] == cid
