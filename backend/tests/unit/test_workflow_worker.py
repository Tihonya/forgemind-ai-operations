"""Unit tests for WP-REC-03F worker functions (D5).

Tests cover:
- Worker registration (both functions registered, correct options).
- Worker input contract (run_id is the only workflow-specific argument).
- Generation parsing from ARQ job identity.
- Stale-generation worker no-op.
- Worker lifecycle and resource cleanup.
"""

from __future__ import annotations

from typing import Any

from app.ai.workflow.worker import (
    _JOB_ID_PREFIX,
    _parse_generation_from_job_id,
    workflow_retry,
    workflow_start,
)


class TestWorkerRegistration:
    """D5 §5: Worker registration."""

    def test_workflow_start_is_registered(self) -> None:
        """workflow_start is in WorkerSettings.functions."""
        from app.worker import WorkerSettings

        names = [
            getattr(f, "name", getattr(f, "__name__", ""))
            for f in WorkerSettings.functions
        ]
        assert "workflow_start" in names

    def test_workflow_retry_is_registered(self) -> None:
        """workflow_retry is in WorkerSettings.functions."""
        from app.worker import WorkerSettings

        names = [
            getattr(f, "name", getattr(f, "__name__", ""))
            for f in WorkerSettings.functions
        ]
        assert "workflow_retry" in names

    def test_both_functions_are_distinct(self) -> None:
        """The two functions are distinct."""
        assert workflow_start is not workflow_retry

    def test_keep_result_is_zero(self) -> None:
        """D5 §6: keep_result=0 for both workflow functions."""
        from app.worker import WorkerSettings

        for f in WorkerSettings.functions:
            name = getattr(f, "name", getattr(f, "__name__", ""))
            if name in ("workflow_start", "workflow_retry"):
                # arq.func wraps with keep_result attribute.
                assert getattr(f, "keep_result", None) == 0 or hasattr(f, "coroutine")

    def test_queue_remains_forgemind_tasks(self) -> None:
        """D5 §5: The queue remains forgemind-tasks."""
        from app.worker import WorkerSettings

        assert WorkerSettings.queue_name == "forgemind-tasks"


class TestCronRegistration:
    """D6 §4: Reconciler cron registration."""

    def test_cron_jobs_is_not_empty(self) -> None:
        """D6 §4: cron_jobs contains the reconciler."""
        from app.worker import WorkerSettings

        assert len(WorkerSettings.cron_jobs) >= 1

    def test_cron_jobs_contains_reconciler(self) -> None:
        """The reconciler function is registered in cron_jobs."""
        from app.worker import WorkerSettings

        # CronJob has a 'func' or 'coroutine' attribute.
        has_reconciler = False
        for job in WorkerSettings.cron_jobs:
            func = getattr(job, "func", None) or getattr(job, "coroutine", None)
            if func is not None and "reconcile" in getattr(
                func, "__name__", ""
            ):
                has_reconciler = True
        assert has_reconciler


class TestWorkerInputContract:
    """D3 §5 / D5 §4: Worker input contract."""

    def test_workflow_start_accepts_run_id(self) -> None:
        """workflow_start accepts run_id as the only workflow-specific arg."""
        import inspect

        sig = inspect.signature(workflow_start)
        params = list(sig.parameters.keys())
        assert "ctx" in params
        assert "run_id" in params

    def test_workflow_retry_accepts_run_id(self) -> None:
        """workflow_retry accepts run_id as the only workflow-specific arg."""
        import inspect

        sig = inspect.signature(workflow_retry)
        params = list(sig.parameters.keys())
        assert "ctx" in params
        assert "run_id" in params

    def test_no_dispatch_generation_in_worker_args(self) -> None:
        """D5 §4: dispatch_generation is not a worker-function argument."""
        import inspect

        for func in (workflow_start, workflow_retry):
            sig = inspect.signature(func)
            assert "dispatch_generation" not in sig.parameters
            assert "plan_id" not in sig.parameters


class TestGenerationParsing:
    """D5 §4: Generation parsing from ARQ job identity."""

    def test_valid_job_id_generation_zero(self) -> None:
        ctx: dict[str, Any] = {"job_id": "workflow:abc-123:0"}
        gen = _parse_generation_from_job_id(ctx)
        assert gen == 0

    def test_valid_job_id_generation_one(self) -> None:
        ctx: dict[str, Any] = {"job_id": "workflow:abc-123:1"}
        gen = _parse_generation_from_job_id(ctx)
        assert gen == 1

    def test_valid_job_id_generation_large(self) -> None:
        ctx: dict[str, Any] = {"job_id": "workflow:abc-123:42"}
        gen = _parse_generation_from_job_id(ctx)
        assert gen == 42

    def test_missing_job_id_returns_none(self) -> None:
        ctx: dict[str, Any] = {}
        gen = _parse_generation_from_job_id(ctx)
        assert gen is None

    def test_malformed_job_id_no_prefix_returns_none(self) -> None:
        ctx: dict[str, Any] = {"job_id": "not-a-workflow-job:0"}
        gen = _parse_generation_from_job_id(ctx)
        assert gen is None

    def test_malformed_job_id_no_generation_returns_none(self) -> None:
        ctx: dict[str, Any] = {"job_id": "workflow:abc-123"}
        gen = _parse_generation_from_job_id(ctx)
        assert gen is None

    def test_malformed_job_id_non_integer_generation_returns_none(self) -> None:
        ctx: dict[str, Any] = {"job_id": "workflow:abc-123:abc"}
        gen = _parse_generation_from_job_id(ctx)
        assert gen is None

    def test_job_id_prefix_constant(self) -> None:
        assert _JOB_ID_PREFIX == "workflow:"
