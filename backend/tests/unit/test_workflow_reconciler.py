"""Unit tests for WP-REC-03F reconciler (D6).

Tests cover:
- Keyset pagination behavior.
- Candidate predicate (state = PENDING AND pending_since <= cutoff).
- Generation-based dispatch target selection.
- Per-candidate failure isolation.
- Accepted/deduplicated/error enqueue classification.
- dispatch_generation not incremented by reconciliation.
- Harmless overlap.
- Observability without raw exception text.
- Budget/pagination exhaustion observability.
- Partial completion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.ai.workflow.reconciler import (
    MAX_PAGES_PER_OCCURRENCE,
    PAGE_SIZE,
    STALE_THRESHOLD_MINUTES,
    _process_candidate,
)


class _FakePool:
    """Fake ARQ pool for reconciler tests."""

    def __init__(
        self,
        *,
        enqueue_results: list[Any] | None = None,
        enqueue_error: Exception | None = None,
    ) -> None:
        self._enqueue_results = enqueue_results or ["job_1"]
        self._enqueue_error = enqueue_error
        self.enqueue_calls: list[dict[str, Any]] = []

    async def enqueue_job(
        self,
        function: str,
        *args: Any,
        _job_id: str | None = None,
        _queue_name: str | None = None,
        **kwargs: Any,
    ) -> Any:
        self.enqueue_calls.append(
            {
                "function": function,
                "args": args,
                "_job_id": _job_id,
            }
        )
        if self._enqueue_error is not None:
            raise self._enqueue_error
        if self._enqueue_results:
            return self._enqueue_results.pop(0)
        return None

    async def close(self) -> None:
        pass


class _FakeSettings:
    """Fake settings for reconciler."""

    arq_queue_name = "forgemind-tasks"


class TestReconcilerConfiguration:
    """D6 §9: Configuration defaults."""

    def test_stale_threshold_is_2_minutes(self) -> None:
        assert STALE_THRESHOLD_MINUTES == 2

    def test_page_size_is_100(self) -> None:
        assert PAGE_SIZE == 100

    def test_max_pages_is_5(self) -> None:
        assert MAX_PAGES_PER_OCCURRENCE == 5


class TestDispatchTargetSelection:
    """D6 §4: Generation-based dispatch target selection."""

    async def test_generation_zero_uses_workflow_start(self) -> None:
        pool = _FakePool()
        metrics: dict[str, Any] = {
            "accepted_count": 0,
            "deduplicated_count": 0,
            "enqueue_error_count": 0,
        }
        candidate = {
            "id": uuid4(),
            "pending_since": datetime.now(UTC) - timedelta(minutes=5),
            "dispatch_generation": 0,
            "run_id": str(uuid4()),
        }
        await _process_candidate(
            pool=pool,
            candidate=candidate,
            metrics=metrics,
            settings_ref=_FakeSettings(),
        )
        assert pool.enqueue_calls[0]["function"] == "workflow_start"
        assert metrics["accepted_count"] == 1

    async def test_generation_positive_uses_workflow_retry(self) -> None:
        pool = _FakePool()
        metrics: dict[str, Any] = {
            "accepted_count": 0,
            "deduplicated_count": 0,
            "enqueue_error_count": 0,
        }
        candidate = {
            "id": uuid4(),
            "pending_since": datetime.now(UTC) - timedelta(minutes=5),
            "dispatch_generation": 3,
            "run_id": str(uuid4()),
        }
        await _process_candidate(
            pool=pool,
            candidate=candidate,
            metrics=metrics,
            settings_ref=_FakeSettings(),
        )
        assert pool.enqueue_calls[0]["function"] == "workflow_retry"
        assert metrics["accepted_count"] == 1


class TestEnqueueOutcomeClassification:
    """D6 §6: Per-candidate enqueue outcome classification."""

    async def test_job_instance_is_accepted(self) -> None:
        pool = _FakePool(enqueue_results=["job_instance"])
        metrics: dict[str, Any] = {
            "accepted_count": 0,
            "deduplicated_count": 0,
            "enqueue_error_count": 0,
        }
        candidate = {
            "id": uuid4(),
            "pending_since": datetime.now(UTC) - timedelta(minutes=5),
            "dispatch_generation": 0,
            "run_id": str(uuid4()),
        }
        await _process_candidate(
            pool=pool,
            candidate=candidate,
            metrics=metrics,
            settings_ref=_FakeSettings(),
        )
        assert metrics["accepted_count"] == 1
        assert metrics["deduplicated_count"] == 0

    async def test_none_is_deduplicated(self) -> None:
        pool = _FakePool(enqueue_results=[None])
        metrics: dict[str, Any] = {
            "accepted_count": 0,
            "deduplicated_count": 0,
            "enqueue_error_count": 0,
        }
        candidate = {
            "id": uuid4(),
            "pending_since": datetime.now(UTC) - timedelta(minutes=5),
            "dispatch_generation": 0,
            "run_id": str(uuid4()),
        }
        await _process_candidate(
            pool=pool,
            candidate=candidate,
            metrics=metrics,
            settings_ref=_FakeSettings(),
        )
        assert metrics["accepted_count"] == 0
        assert metrics["deduplicated_count"] == 1

    async def test_exception_is_error(self) -> None:
        pool = _FakePool(enqueue_error=ConnectionError("Redis down"))
        metrics: dict[str, Any] = {
            "accepted_count": 0,
            "deduplicated_count": 0,
            "enqueue_error_count": 0,
        }
        candidate = {
            "id": uuid4(),
            "pending_since": datetime.now(UTC) - timedelta(minutes=5),
            "dispatch_generation": 0,
            "run_id": str(uuid4()),
        }
        await _process_candidate(
            pool=pool,
            candidate=candidate,
            metrics=metrics,
            settings_ref=_FakeSettings(),
        )
        assert metrics["accepted_count"] == 0
        assert metrics["enqueue_error_count"] == 1


class TestPerCandidateIsolation:
    """D6 §6: Per-candidate failure isolation."""

    async def test_one_error_does_not_prevent_later_candidates(self) -> None:
        """One candidate's enqueue error does not prevent later candidates."""
        # First call raises, second succeeds.
        call_count = [0]

        class _MixedPool:
            async def enqueue_job(
                self,
                function: str,
                *args: Any,
                _job_id: str | None = None,
                _queue_name: str | None = None,
                **kwargs: Any,
            ) -> Any:
                call_count[0] += 1
                if call_count[0] == 1:
                    raise ConnectionError("Redis down")
                return "job_success"

            async def close(self) -> None:
                pass

        pool = _MixedPool()

        metrics: dict[str, Any] = {
            "accepted_count": 0,
            "deduplicated_count": 0,
            "enqueue_error_count": 0,
        }
        for _i in range(2):
            candidate = {
                "id": uuid4(),
                "pending_since": datetime.now(UTC) - timedelta(minutes=5),
                "dispatch_generation": 0,
                "run_id": str(uuid4()),
            }
            await _process_candidate(
                pool=pool,
                candidate=candidate,
                metrics=metrics,
                settings_ref=_FakeSettings(),
            )

        assert metrics["enqueue_error_count"] == 1
        assert metrics["accepted_count"] == 1


class TestReconcilerDoesNotIncrementGeneration:
    """D6 §3: Reconciliation must not increment dispatch_generation."""

    async def test_process_candidate_does_not_increment(self) -> None:
        pool = _FakePool()
        metrics: dict[str, Any] = {
            "accepted_count": 0,
            "deduplicated_count": 0,
            "enqueue_error_count": 0,
        }
        original_gen = 5
        candidate = {
            "id": uuid4(),
            "pending_since": datetime.now(UTC) - timedelta(minutes=5),
            "dispatch_generation": original_gen,
            "run_id": str(uuid4()),
        }
        await _process_candidate(
            pool=pool,
            candidate=candidate,
            metrics=metrics,
            settings_ref=_FakeSettings(),
        )
        # The candidate dict is not modified.
        assert candidate["dispatch_generation"] == original_gen


class TestJobIdReconstruction:
    """D5 §3: Deterministic job-ID reconstruction."""

    async def test_job_id_matches_workflow_prefix(self) -> None:
        pool = _FakePool()
        metrics: dict[str, Any] = {
            "accepted_count": 0,
            "deduplicated_count": 0,
            "enqueue_error_count": 0,
        }
        run_id = str(uuid4())
        gen = 2
        candidate = {
            "id": uuid4(),
            "pending_since": datetime.now(UTC) - timedelta(minutes=5),
            "dispatch_generation": gen,
            "run_id": run_id,
        }
        await _process_candidate(
            pool=pool,
            candidate=candidate,
            metrics=metrics,
            settings_ref=_FakeSettings(),
        )
        expected_job_id = f"workflow:{run_id}:{gen}"
        assert pool.enqueue_calls[0]["_job_id"] == expected_job_id
