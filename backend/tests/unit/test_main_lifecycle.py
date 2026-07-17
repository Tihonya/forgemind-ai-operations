"""Tests for FastAPI application lifecycle logging integration.

These tests verify that:
- importing app.main does not emit startup logs
- startup configures structured logging via lifespan
- log level comes from Settings
- startup event uses safe fields (no secrets)
- endpoints still work after lifecycle changes
- repeated lifecycles do not duplicate handlers
- shutdown has no log event (not required by Phase 1 plan)
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.schemas.health import DependencyCheck, DependencyHealthSnapshot

_BACKEND_CWD = str(pathlib.Path(__file__).resolve().parents[2])
_MAIN_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "main.py"

_FIXED_TS = datetime(2026, 7, 15, 14, 0, 0, tzinfo=UTC)


def _run_lifespan_script(code: str) -> subprocess.CompletedProcess[str]:
    """Run a subprocess that executes lifespan code and returns the result."""
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=_BACKEND_CWD,
        timeout=10,
    )


def _parse_json_lines(stderr: str) -> list[dict[str, Any]]:
    """Parse structured JSON log lines from stderr, skipping non-JSON lines.

    The subprocess may emit import warnings or other non-JSON noise on stderr.
    Only lines that are valid JSON objects are returned.
    """
    lines = []
    for ln in stderr.strip().split("\n"):
        stripped = ln.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        try:
            lines.append(json.loads(stripped))
        except json.JSONDecodeError:
            continue
    return lines


# -- Helper: subprocess code templates -----------------------------------------
# @asynccontextmanager generators must be __aenter__'d and __aexit__'d on the
# SAME instance.  We store the context manager in a named variable so each
# enter/exit pair references the identical generator object.

_STARTUP_ONLY = (
    "import asyncio, sys, json; "
    "from app.main import app, lifespan; "
    "loop = asyncio.new_event_loop(); "
    "asyncio.set_event_loop(loop); "
    "ctx = lifespan(app); "
    "loop.run_until_complete(ctx.__aenter__()); "
    "exit(0)"
)

_EXIT_AFTER_ENTER = (
    "import asyncio, sys, json; "
    "from app.main import app, lifespan; "
    "loop = asyncio.new_event_loop(); "
    "asyncio.set_event_loop(loop); "
    "ctx = lifespan(app); "
    "loop.run_until_complete(ctx.__aenter__()); "
    "loop.run_until_complete(ctx.__aexit__(None, None, None)); "
    "exit(0)"
)

_TWO_LIFECYCLES = (
    "import asyncio, sys, json; "
    "from app.main import app, lifespan; "
    "loop = asyncio.new_event_loop(); "
    "asyncio.set_event_loop(loop); "
    "ctx1 = lifespan(app); "
    "loop.run_until_complete(ctx1.__aenter__()); "
    "loop.run_until_complete(ctx1.__aexit__(None, None, None)); "
    "ctx2 = lifespan(app); "
    "loop.run_until_complete(ctx2.__aenter__()); "
    "loop.run_until_complete(ctx2.__aexit__(None, None, None)); "
    "exit(0)"
)


class TestImportSafety:
    """Importing app.main must not configure logging or emit logs."""

    def test_import_main_does_not_emit_startup_logs(self) -> None:
        """Importing app.main in a fresh Python process emits no stderr."""
        code = (
            "import sys; "
            "import logging; "
            "root = logging.getLogger(); "
            "handlers_before = [h for h in root.handlers "
            "if type(h).__module__ != 'logging']; "
            "from app.main import app as _app; "
            "root_after = logging.getLogger(); "
            "handlers_after = [h for h in root_after.handlers "
            "if type(h).__module__ != 'logging']; "
            "assert len(handlers_after) == len(handlers_before), "
            "'import added handlers'; "
            "print('OK')"
        )
        result = _run_lifespan_script(code)
        assert result.returncode == 0, (
            f"Import failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert result.stdout.strip() == "OK"
        assert result.stderr == "", f"Import emitted stderr: {result.stderr}"


class TestStartupLogging:
    """Application startup must configure logging via lifespan."""

    def test_startup_emits_structured_json(self) -> None:
        """Lifespan startup emits a structured JSON log line to stderr."""
        result = _run_lifespan_script(_STARTUP_ONLY)
        assert result.returncode == 0, f"Startup failed: {result.stderr}"
        assert result.stderr.strip(), "No stderr output from lifespan startup"

        records = _parse_json_lines(result.stderr)
        assert records, f"No JSON records parsed from stderr: {result.stderr!r}"
        # The last JSON line should be the startup event
        record = records[-1]
        assert record["event"] == "application_startup"
        assert record["level"] == "info"
        assert "timestamp" in record

    def test_startup_event_uses_only_safe_fields(self) -> None:
        """Startup event must contain only safe fields (verified by code inspection).

        The lifespan in app.main calls logger.info('application_startup') with
        exactly four keyword arguments: application_name, version, git_sha,
        environment. No secret, URL, or credential fields are passed.
        """
        main_text = _MAIN_PATH.read_text()

        # Find the startup log call
        assert '"application_startup"' in main_text

        # Extract the logger.info(...) call block for startup
        start_idx = main_text.index('"application_startup"')
        call_start = main_text.rfind("logger.info(", 0, start_idx)
        assert call_start != -1, "Could not find logger.info( call"
        depth = 0
        end_idx = call_start
        for i in range(call_start, len(main_text)):
            if main_text[i] == "(":
                depth += 1
            elif main_text[i] == ")":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        startup_call = main_text[call_start : end_idx + 1]

        # Verify required fields are present
        assert "application_name=build_info.application_name" in startup_call
        assert "version=build_info.version" in startup_call
        assert "git_sha=build_info.git_sha" in startup_call
        assert "environment=build_info.environment" in startup_call

        # Verify no secret fields appear in the startup call
        forbidden = [
            "secret_key",
            "database_url",
            "redis_url",
            "openai_api_key",
            "cors_origins",
            "backend_host",
            "backend_port",
        ]
        for secret in forbidden:
            assert secret not in startup_call, (
                f"Startup event exposes forbidden field: {secret}"
            )

    def test_startup_event_contains_build_info_values(self) -> None:
        """Startup event contains real build-info values (not empty)."""
        result = _run_lifespan_script(_STARTUP_ONLY)
        assert result.returncode == 0
        records = _parse_json_lines(result.stderr)
        assert records, f"No JSON records parsed from stderr: {result.stderr!r}"
        record = records[-1]

        assert record["application_name"] == "forgemind-backend"
        assert isinstance(record["version"], str) and record["version"]
        assert isinstance(record["git_sha"], str) and record["git_sha"]
        assert record["environment"] == "development"


class TestLogLevelFromSettings:
    """Log level must come from Settings, not os.environ."""

    def test_log_level_resolved_from_settings(self) -> None:
        """Configured log level comes from settings.log_level.

        Verified by code inspection: lifespan calls
        configure_logging(level=settings.log_level), not os.environ.
        """
        main_text = _MAIN_PATH.read_text()

        # Confirm lifespan passes settings.log_level (not os.environ)
        assert "configure_logging(level=settings.log_level)" in main_text
        assert "os.environ" not in main_text


class TestEndpointAvailability:
    """Application must still serve endpoints after lifecycle changes."""

    @pytest.mark.asyncio
    async def test_health_endpoint_works(self) -> None:
        """Health endpoint is accessible and returns structured response."""
        from unittest.mock import AsyncMock, patch

        snapshot = DependencyHealthSnapshot(
            timestamp=_FIXED_TS,
            checks=[
                DependencyCheck(name="postgresql", status="ok", latency_ms=1.0, detail="ok"),
                DependencyCheck(name="redis", status="ok", latency_ms=1.0, detail="ok"),
                DependencyCheck(
                    name="alembic", status="ok", latency_ms=1.0, detail="revision abc1234"
                ),
                DependencyCheck(name="worker", status="ok", latency_ms=1.0, detail="ok"),
            ],
            summary="healthy",
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with patch(
                "app.main.check_all_dependencies",
                new=AsyncMock(return_value=snapshot),
            ):
                response = await client.get("/health")

        assert response.status_code == 200
        # Phase 1: structured response with status, checks, correlation_id
        body = response.json()
        assert body["status"] == "healthy"
        assert "checks" in body
        assert "correlation_id" in body

    @pytest.mark.asyncio
    async def test_root_endpoint_works(self) -> None:
        """Root endpoint is accessible after startup."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "ForgeMind AI Operations"
        assert "version" in data
        assert data["docs"] == "/docs"


class TestRepeatedLifecycle:
    """Repeated lifespan execution must not duplicate log output."""

    def test_repeated_startup_no_duplicate_log_lines(self) -> None:
        """Multiple lifespan startups emit exactly one startup log each time.

        configure_logging() is idempotent — it reuses _MANAGED_HANDLER, so
        each lifespan produces exactly one log line, not accumulating.
        """
        result = _run_lifespan_script(_TWO_LIFECYCLES)
        assert result.returncode == 0, f"Failed: {result.stderr}"

        records = _parse_json_lines(result.stderr)
        startup_events = [
            r for r in records if r.get("event") == "application_startup"
        ]
        assert len(startup_events) == 2, (
            f"Expected exactly 2 startup events, got {len(startup_events)}"
        )


class TestShutdownBehavior:
    """Shutdown behavior must match the lifecycle contract."""

    def test_lifespan_uses_empty_shutdown_block(self) -> None:
        """Lifespan shutdown does not contain any log emission.

        Phase 1 plan does not require shutdown observability.
        """
        main_text = _MAIN_PATH.read_text()

        # Find shutdown section: everything after "    yield" in lifespan
        yield_idx = main_text.index("    yield")
        lifespan_rest = main_text[yield_idx:]
        shutdown_section_lines = lifespan_rest.split("\n")
        # Collect indented (still-inside-lifespan) lines after yield
        shutdown_code: list[str] = []
        for line in shutdown_section_lines[1:]:
            if line.strip() == "":
                shutdown_code.append("")
                continue
            if line.startswith("    "):
                shutdown_code.append(line)
            else:
                break
        shutdown_text = "\n".join(shutdown_code)

        assert "logger." not in shutdown_text, (
            f"Shutdown block should not emit log events, found:\n{shutdown_text}"
        )
        assert "get_logger" not in shutdown_text

    def test_shutdown_does_not_emit_log_event(self) -> None:
        """Verify runtime: shutdown (lifespan exit) produces no shutdown log."""
        result = _run_lifespan_script(_EXIT_AFTER_ENTER)
        assert result.returncode == 0

        records = _parse_json_lines(result.stderr)
        for record in records:
            assert record.get("event") != "application_shutdown", (
                "Shutdown event emitted but not required by Phase 1 plan"
            )
