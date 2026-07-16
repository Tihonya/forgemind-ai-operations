"""Unit tests for diagnostic job worker function.

Tests cover registration, lifecycle, atomic claim, persistence,
idempotency, error handling, structured logging, and transaction boundaries.
No live PostgreSQL, Redis, or ARQ worker required.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.core.correlation import InvalidCorrelationIdError
from app.jobs.diagnostics import run_diagnostic_job
from app.models.diagnostic import DiagnosticJob
from app.schemas.health import DependencyCheck, DependencyHealthSnapshot
from app.worker import WorkerSettings

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _make_orm_job(
    *,
    job_id: uuid.UUID,
    status: str = "pending",
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
    error_message: str | None = None,
    checks: list[dict[str, Any]] | None = None,
) -> DiagnosticJob:
    """Build a DiagnosticJob ORM instance matching the schema contract."""
    return DiagnosticJob(
        id=job_id,
        correlation_id=uuid.uuid4(),
        status=status,
        triggered_by="operator",
        checks=checks,
        error_message=error_message,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
    )


def _healthy_snapshot() -> DependencyHealthSnapshot:
    """Return a DependencyHealthSnapshot with all 'ok' checks."""
    checks = [
        DependencyCheck(name="postgresql", status="ok", latency_ms=1.2, detail="ok"),
        DependencyCheck(name="redis", status="ok", latency_ms=0.5, detail="ok"),
        DependencyCheck(name="alembic", status="ok", latency_ms=0.8, detail="ok"),
        DependencyCheck(name="worker", status="ok", latency_ms=0.3, detail="ok"),
    ]
    return DependencyHealthSnapshot(
        checks=checks, summary="healthy", timestamp=datetime.now(UTC),
    )


# --------------------------------------------------------------------------- #
# Scripted session + fake UPDATE mutation contract
# --------------------------------------------------------------------------- #


class _RowProxy:
    """Minimal Row-like object for select(...col, col...) results."""

    def __init__(self, **fields: Any) -> None:
        self._fields = fields

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        if name in self._fields:
            return self._fields[name]
        raise AttributeError(
            f"RowProxy has no field {name!r}; known: {list(self._fields)}"
        )


class _SeqResult:
    """Fake Result consumed from a scripted sequence.

    Each script entry is a dict with keys:
      - "kind": 'row_or_none' | 'first' | 'scalar_one' | 'scalar_one_or_none'
      - "value": the value to return from that method
      - "mutate" (optional): callable(DiagnosticJob) -> None that simulates
        what the real DB UPDATE would have written to the row (e.g. the claim
        UPDATE writes status='running', started_at=now, etc.)
    """

    def __init__(
        self,
        kind: str,
        value: Any,
        mutate: Callable[[DiagnosticJob], None] | None = None,
        job: DiagnosticJob | None = None,
    ) -> None:
        self._kind = kind
        self._value = value
        self._mutate = mutate
        self._job = job

    def _maybe_mutate(self) -> None:
        if self._mutate is not None and self._job is not None:
            self._mutate(self._job)

    def one_or_none(self) -> Any:
        assert self._kind == "row_or_none", f"expected row_or_none, got {self._kind}"
        return self._value

    def first(self) -> Any:
        assert self._kind == "first", f"expected first, got {self._kind}"
        self._maybe_mutate()
        return self._value

    def scalar_one(self) -> Any:
        assert self._kind == "scalar_one", f"expected scalar_one, got {self._kind}"
        return self._value

    def scalar_one_or_none(self) -> Any:
        assert self._kind == "scalar_one_or_none", (
            f"expected scalar_one_or_none, got {self._kind}"
        )
        return self._value


class ScriptedSession:
    """Fake async session that returns scripted results in call order.

    Tracks commits and exposes the ORM job object for assertions.
    """

    def __init__(
        self,
        script: list[dict[str, Any]],
        job: DiagnosticJob | None = None,
    ) -> None:
        self._script = list(script)
        self.job = job
        self.commits: list[int] = []
        self.closes: list[int] = []
        self._call_index = 0
        self._exit_count = 0

    async def execute(self, statement: Any) -> _SeqResult:
        assert self._call_index < len(self._script), (
            f"Unexpected execute() call #{self._call_index}; "
            f"script has {len(self._script)} entries"
        )
        entry = self._script[self._call_index]
        kind = entry["kind"]
        value = entry["value"]
        mutate = entry.get("mutate")
        result = _SeqResult(kind, value, mutate=mutate, job=self.job)
        self._call_index += 1
        return result

    async def commit(self) -> None:
        self.commits.append(self._call_index)

    # Async context manager interface (mirrors async_session_factory() usage)
    async def __aenter__(self) -> ScriptedSession:
        return self

    async def __aexit__(self, *_: Any) -> bool:
        self._exit_count += 1
        self.closes.append(self._call_index)
        return False


def _session_factory(session: ScriptedSession) -> ScriptedSession:
    """Return the session as the factory result.

    `async with async_session_factory() as session` requires the factory's
    return value to be an async context manager. ScriptedSession IS one.
    """
    return session


# --------------------------------------------------------------------------- #
# Claim mutation (mirrors what _try_claim's UPDATE writes in production)
# --------------------------------------------------------------------------- #


def _claim_mutate(now: datetime) -> Callable[[DiagnosticJob], None]:
    """Return a mutator that applies _try_claim's UPDATE to an ORM job.

    Mirrors the production UPDATE:
        status='running', started_at=now, updated_at=now,
        completed_at=None, duration_ms=None, error_message=None, checks=None
    """
    def apply(job: DiagnosticJob) -> None:
        job.status = "running"
        job.started_at = now
        job.updated_at = now
        job.completed_at = None
        job.duration_ms = None
        job.error_message = None
        job.checks = None

    return apply


# --------------------------------------------------------------------------- #
# Helper: happy-path script (pending → completed)
# --------------------------------------------------------------------------- #
# Call sequence for happy-path pending→completed:
#   0: _load_state           -> row_or_none(status, duration_ms)
#   1: _try_claim            -> first(row) + mutate(job)  [claim succeeds]
#   2: _persist_completion   -> scalar_one(job ORM)
# --------------------------------------------------------------------------- #


def _happy_path_script(
    job: DiagnosticJob, now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Script for pending→completed happy path."""
    ts = now or datetime.now(UTC)
    return [
        {"kind": "row_or_none", "value": _RowProxy(status=job.status, duration_ms=job.duration_ms)},
        {"kind": "first", "value": _RowProxy(id=job.id), "mutate": _claim_mutate(ts)},
        {"kind": "scalar_one", "value": job},
    ]


# --------------------------------------------------------------------------- #
# Registration tests
# --------------------------------------------------------------------------- #


def test_registration_function_in_worker_settings() -> None:
    """run_diagnostic_job must be in WorkerSettings.functions."""
    assert run_diagnostic_job in WorkerSettings.functions


def test_registration_no_noop_functions() -> None:
    """functions must contain at least one real callable; no placeholders."""
    assert len(WorkerSettings.functions) >= 1
    for fn in WorkerSettings.functions:
        assert callable(fn)
        # Accept only the real diagnostic function
        assert fn.__name__ == "run_diagnostic_job"


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pending_to_completed() -> None:
    """Happy path: pending → running → completed populates duration and checks."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="pending")
    now = datetime.now(UTC)
    session = ScriptedSession(_happy_path_script(job, now=now), job=job)

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=AsyncMock(return_value=_healthy_snapshot()),
    ):
        result = await run_diagnostic_job({}, str(job_id), correlation_id)

    assert result["job_id"] == str(job_id)
    assert result["status"] == "completed"
    assert isinstance(result["duration_ms"], int)
    assert result["duration_ms"] >= 0
    assert result["dependency_summary"] == "healthy"

    # Model state checks
    assert job.status == "completed"
    assert job.started_at is not None
    assert job.started_at.tzinfo is not None  # timezone-aware UTC
    assert job.started_at == now
    assert job.completed_at is not None
    assert job.completed_at >= job.started_at
    assert job.duration_ms == result["duration_ms"]
    assert isinstance(job.checks, list)
    assert len(job.checks) == 4  # pg, redis, alembic, worker


# --------------------------------------------------------------------------- #
# Atomic claim / concurrency
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_atomic_claim_winner_runs_checks() -> None:
    """When claim UPDATE returns a row, the job proceeds to dependency checks."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="pending")
    session = ScriptedSession(_happy_path_script(job), job=job)

    check_mock = AsyncMock(return_value=_healthy_snapshot())

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=check_mock,
    ):
        result = await run_diagnostic_job({}, str(job_id), correlation_id)

    assert result["status"] == "completed"
    check_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_atomic_claim_loser_skips_checks_if_completed() -> None:
    """When claim returns no rows, and job is completed by then, return cached."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="completed", duration_ms=456)
    script = [
        {"kind": "row_or_none", "value": _RowProxy(status="pending", duration_ms=None)},
        {"kind": "first", "value": None},  # claim failed
        {"kind": "row_or_none", "value": _RowProxy(status="completed", duration_ms=456)},
    ]
    session = ScriptedSession(script, job=job)

    check_mock = AsyncMock(return_value=_healthy_snapshot())

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=check_mock,
    ):
        result = await run_diagnostic_job({}, str(job_id), correlation_id)

    assert result["status"] == "completed"
    assert result["duration_ms"] == 456
    assert result["dependency_summary"] == "cached"
    check_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_atomic_claim_loser_raises_when_running() -> None:
    """When claim fails and re-load sees status=running, raise ValueError."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="running")
    script = [
        {"kind": "row_or_none", "value": _RowProxy(status="pending", duration_ms=None)},
        {"kind": "first", "value": None},  # claim lost
        {"kind": "row_or_none", "value": _RowProxy(status="running", duration_ms=None)},
    ]
    session = ScriptedSession(script, job=job)

    check_mock = AsyncMock(return_value=_healthy_snapshot())

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=check_mock,
    ), pytest.raises(ValueError, match="is already running"):
        await run_diagnostic_job({}, str(job_id), correlation_id)

    check_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_atomic_claim_no_two_invocations_run_checks() -> None:
    """Regression: two near-simultaneous calls cannot both execute checks.

    Worker A's claim succeeds; worker B's claim fails. Only A runs checks.
    This proves the atomic UPDATE...WHERE...RETURNING prevents the
    SELECT-then-UPDATE race.
    """
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job_a = _make_orm_job(job_id=job_id, status="pending")
    job_b = _make_orm_job(job_id=job_id, status="pending")

    check_mock = AsyncMock(return_value=_healthy_snapshot())

    session_a = ScriptedSession(_happy_path_script(job_a), job=job_a)
    # Session B: load sees pending (so claim is tried), claim loses,
    # re-load sees running (someone else has it).
    script_b = [
        {"kind": "row_or_none", "value": _RowProxy(status="pending", duration_ms=None)},
        {"kind": "first", "value": None},
        {"kind": "row_or_none", "value": _RowProxy(status="running", duration_ms=None)},
    ]
    session_b = ScriptedSession(script_b, job=job_b)

    async def run_a() -> dict[str, Any]:
        with patch(
            "app.jobs.diagnostics.async_session_factory",
            return_value=_session_factory(session_a),
        ):
            return await run_diagnostic_job({}, str(job_id), correlation_id)

    async def run_b() -> None:
        with patch(
            "app.jobs.diagnostics.async_session_factory",
            return_value=_session_factory(session_b),
        ), pytest.raises(ValueError, match="is already running"):
            await run_diagnostic_job({}, str(job_id), correlation_id)

    with patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=check_mock,
    ):
        await asyncio.gather(run_a(), run_b(), return_exceptions=False)

    # Exactly one check_all_dependencies invocation across both workers.
    assert check_mock.await_count == 1


# --------------------------------------------------------------------------- #
# Idempotency
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_completed_job_not_rerun() -> None:
    """Completed jobs must return cached result without calling checks."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="completed", duration_ms=123)
    script = [
        {"kind": "row_or_none", "value": _RowProxy(status="completed", duration_ms=123)},
    ]
    session = ScriptedSession(script, job=job)
    check_mock = AsyncMock()

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=check_mock,
    ):
        result = await run_diagnostic_job({}, str(job_id), correlation_id)

    assert result["status"] == "completed"
    assert result["duration_ms"] == 123
    assert result["dependency_summary"] == "cached"
    check_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_running_job_raises_value_error() -> None:
    """Running jobs raise ValueError deterministically."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="running")
    script = [
        {"kind": "row_or_none", "value": _RowProxy(status="running", duration_ms=None)},
    ]
    session = ScriptedSession(script, job=job)

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), pytest.raises(ValueError, match="is already running"):
        await run_diagnostic_job({}, str(job_id), correlation_id)


@pytest.mark.asyncio
async def test_failed_job_allows_retry() -> None:
    """Jobs in 'failed' status are eligible to claim and retry."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(
        job_id=job_id,
        status="failed",
        error_message="Old error",
        duration_ms=999,
    )
    script = _happy_path_script(job)
    script[0] = {"kind": "row_or_none", "value": _RowProxy(status="failed", duration_ms=999)}
    session = ScriptedSession(script, job=job)

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=AsyncMock(return_value=_healthy_snapshot()),
    ):
        result = await run_diagnostic_job({}, str(job_id), correlation_id)

    assert result["status"] == "completed"
    assert job.status == "completed"


# --------------------------------------------------------------------------- #
# Failed-job retry reset behavior
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_failed_retry_clears_stale_fields() -> None:
    """Claim of a failed job clears completed_at, duration_ms, error_message, checks.

    _try_claim's UPDATE sets:
      started_at='now', completed_at=NULL, duration_ms=NULL,
      error_message=NULL, checks=NULL
    Then _persist_completion sets the new values. This test verifies the
    stale fields from the previous failure are replaced.
    """
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    old_started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    old_completed = datetime(2026, 1, 1, 12, 1, tzinfo=UTC)
    job = _make_orm_job(
        job_id=job_id,
        status="failed",
        started_at=old_started,
        completed_at=old_completed,
        duration_ms=42,
        error_message="Old failure error",
        checks=[{"name": "old", "status": "error", "latency_ms": 0}],
    )
    script = _happy_path_script(job)
    script[0] = {"kind": "row_or_none", "value": _RowProxy(status="failed", duration_ms=42)}
    session = ScriptedSession(script, job=job)

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=AsyncMock(return_value=_healthy_snapshot()),
    ):
        result = await run_diagnostic_job({}, str(job_id), correlation_id)

    assert result["status"] == "completed"
    assert job.status == "completed"
    # duration_ms is from the new run, not the old 42
    assert job.duration_ms is not None
    assert job.duration_ms != 42
    assert job.duration_ms == result["duration_ms"]
    # started_at must be a new value (not the old timestamp)
    assert job.started_at is not None
    assert job.started_at != old_started
    assert job.started_at.tzinfo is not None  # timezone-aware UTC
    assert job.duration_ms >= 0
    # completed_at must be newer than (or equal to) started_at
    assert job.completed_at is not None
    assert job.completed_at >= job.started_at
    # error_message cleared on success
    assert job.error_message is None
    # checks replaced with new data, not the stale list
    assert isinstance(job.checks, list)
    assert len(job.checks) == 4
    assert all(c.get("name") != "old" for c in job.checks)


# --------------------------------------------------------------------------- #
# Missing job
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_missing_job_raises_runtime_error() -> None:
    """Missing job raises RuntimeError without attempting any work."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    script = [{"kind": "row_or_none", "value": None}]
    session = ScriptedSession(script, job=None)
    check_mock = AsyncMock()

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=check_mock,
    ), pytest.raises(RuntimeError, match="not found"):
        await run_diagnostic_job({}, str(job_id), correlation_id)

    check_mock.assert_not_awaited()
    # No commits happened (no DB mutation)
    assert session.commits == []


# --------------------------------------------------------------------------- #
# Failure persistence
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_dependency_failure_persists_failed_state() -> None:
    """Dependency check errors persist 'failed' state and re-raise."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="pending")
    now_ts = datetime.now(UTC)
    script = [
        {"kind": "row_or_none", "value": _RowProxy(status="pending", duration_ms=None)},
        {
            "kind": "first",
            "value": _RowProxy(id=job.id),
            "mutate": _claim_mutate(now_ts),
        },
        {"kind": "scalar_one_or_none", "value": job},
    ]
    session = ScriptedSession(script, job=job)

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ), pytest.raises(RuntimeError, match="boom"):
        await run_diagnostic_job({}, str(job_id), correlation_id)

    assert job.status == "failed"
    assert job.completed_at is not None
    assert job.completed_at >= job.started_at  # type: ignore[operator]
    assert job.error_message is not None
    assert "\n" not in job.error_message  # single-line
    assert len(job.error_message) <= 500


@pytest.mark.asyncio
async def test_persisted_error_never_contains_raw_exception_or_secrets() -> None:
    """Error must not leak raw exception text, URLs, passwords, or tracebacks."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="pending")
    now_ts = datetime.now(UTC)
    script = [
        {"kind": "row_or_none", "value": _RowProxy(status="pending", duration_ms=None)},
        {
            "kind": "first",
            "value": _RowProxy(id=job.id),
            "mutate": _claim_mutate(now_ts),
        },
        {"kind": "scalar_one_or_none", "value": job},
    ]
    session = ScriptedSession(script, job=job)

    evil_message = (
        "psycopg2.OperationalError: FATAL: password authentication failed\n"
        "  connection string: postgresql://user:s3cr3tP@ss@db.internal:5432/prod\n"
        "Traceback (most recent call last):\n"
        "  File \"/app/jobs.py\", line 42, in run_diagnostic_job\n"
        "    raise psycopg2.OperationalError(message)\n"
        "psycopg2.OperationalError: connection refused"
    )
    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=AsyncMock(side_effect=RuntimeError(evil_message)),
    ), pytest.raises(RuntimeError):
        await run_diagnostic_job({}, str(job_id), correlation_id)

    assert job.status == "failed"
    err = job.error_message or ""
    # Must never leak any of these from the exception message
    assert "s3cr3tP@ss" not in err
    assert "db.internal" not in err
    assert "postgresql://user" not in err
    assert "Traceback" not in err
    assert "psycopg2" not in err
    assert "/app/jobs.py" not in err
    # Still single-line, bounded
    assert "\n" not in err
    assert len(err) <= 500


# --------------------------------------------------------------------------- #
# Input validation: no DB access for invalid inputs
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_invalid_diagnostic_job_id_raises_value_error_no_db_access() -> None:
    """Invalid diagnostic_job_id raises ValueError without DB access."""
    factory_called = False

    def never_call() -> Any:
        nonlocal factory_called
        factory_called = True
        raise AssertionError("Session factory should not be called")

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        side_effect=never_call,
    ), pytest.raises(ValueError, match="is not a valid UUID"):
        await run_diagnostic_job({}, "not-a-uuid", str(uuid.uuid4()))

    assert factory_called is False


@pytest.mark.asyncio
async def test_invalid_correlation_id_raises_validation_error_no_db_access() -> None:
    """Invalid correlation_id raises InvalidCorrelationIdError without DB."""
    factory_called = False

    def never_call() -> Any:
        nonlocal factory_called
        factory_called = True
        raise AssertionError("Session factory should not be called")

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        side_effect=never_call,
    ), pytest.raises(InvalidCorrelationIdError):
        await run_diagnostic_job({}, str(uuid.uuid4()), "not-a-uuid")

    assert factory_called is False


# --------------------------------------------------------------------------- #
# Transaction boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_claim_commit_happens_before_external_checks() -> None:
    """The claim session must commit BEFORE check_all_dependencies executes."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="pending")
    session = ScriptedSession(_happy_path_script(job), job=job)

    events: list[str] = []

    original_commit = session.commit

    async def tracking_commit() -> None:
        events.append("commit")
        await original_commit()
    session.commit = tracking_commit  # type: ignore[method-assign]

    async def check_with_marker() -> DependencyHealthSnapshot:
        events.append("checks_running")
        return _healthy_snapshot()

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=AsyncMock(side_effect=check_with_marker),
    ):
        await run_diagnostic_job({}, str(job_id), correlation_id)

    # First commit must be the claim commit, before checks run.
    assert "commit" in events
    assert "checks_running" in events
    assert events.index("commit") < events.index("checks_running"), (
        f"Claim commit must precede checks; events={events}"
    )


# --------------------------------------------------------------------------- #
# Return value & serialization
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_return_value_is_json_serializable() -> None:
    """Return value must contain only JSON-primitive values."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="pending")
    session = ScriptedSession(_happy_path_script(job), job=job)

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=AsyncMock(return_value=_healthy_snapshot()),
    ):
        result = await run_diagnostic_job({}, str(job_id), correlation_id)

    json_str = json.dumps(result)
    parsed = json.loads(json_str)
    assert parsed == result
    assert isinstance(result["job_id"], str)
    assert isinstance(result["status"], str)
    assert isinstance(result["duration_ms"], int)
    assert isinstance(result["dependency_summary"], str)


@pytest.mark.asyncio
async def test_persisted_checks_round_trip_json_safe() -> None:
    """DiagnosticJob.checks must be plain JSON-safe data (no ORM/Pydantic)."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="pending")
    session = ScriptedSession(_happy_path_script(job), job=job)

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=AsyncMock(return_value=_healthy_snapshot()),
    ):
        await run_diagnostic_job({}, str(job_id), correlation_id)

    assert job.checks is not None
    round_trip = json.loads(json.dumps(job.checks))
    assert isinstance(round_trip, list)
    assert len(round_trip) == 4
    for check in round_trip:
        assert isinstance(check, dict)
        assert isinstance(check.get("name"), str)
        assert isinstance(check.get("status"), str)
        assert isinstance(check.get("latency_ms"), (int, float))
    # No Pydantic model instances leaked
    assert all(not hasattr(c, "model_dump") for c in round_trip)


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_correlation_context_in_logs(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Structured logs must include correlation_id (bound via context)."""
    job_id = uuid.uuid4()
    correlation_id = str(uuid.uuid4())
    job = _make_orm_job(job_id=job_id, status="pending")
    session = ScriptedSession(_happy_path_script(job), job=job)

    with patch(
        "app.jobs.diagnostics.async_session_factory",
        return_value=_session_factory(session),
    ), patch(
        "app.jobs.diagnostics.check_all_dependencies",
        new=AsyncMock(return_value=_healthy_snapshot()),
    ):
        await run_diagnostic_job({}, str(job_id), correlation_id)

    log_evidence: list[str] = []

    for record in caplog.records:
        if "diagnostic_job_completed" in record.getMessage():
            log_evidence.append(record.getMessage())

    captured = capsys.readouterr()
    for line in (captured.out + captured.err).splitlines():
        if "diagnostic_job_completed" in line:
            log_evidence.append(line)

    assert log_evidence, "No diagnostic_job_completed log captured"
    assert any(correlation_id in text for text in log_evidence), (
        f"correlation_id {correlation_id} not found in log evidence: {log_evidence}"
    )
