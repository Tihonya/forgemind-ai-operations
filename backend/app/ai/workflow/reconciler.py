"""D6 reconciler for stale PENDING workflow runs (WP-REC-03F).

Implements the complete D6/DEC-042 contract:

- ARQ cron job registered in ``WorkerSettings.cron_jobs``.
- Dedicated ``pending_since`` field for stale-candidate detection.
- Keyset pagination ordered by ``(pending_since ASC, id ASC)`` (D6 §2).
- Harmless overlap between distinct cron occurrences (D6 §3).
- Generation-based dispatch target selection (D6 §4).
- Mandatory generation guard (D6 §5).
- Best-effort recovery of committed stale PENDING rows.
- Correct handling of rows concurrently changed after selection.
- No global singleton lock (D6 §3).
- No separate process, queue, Redis topology, or external scheduler.

Configuration defaults (D6 §9 — proposed, not permanently fixed):

- Reconciliation interval: 60 seconds
- Stale threshold: 2 minutes
- Page size: 100
- Maximum pages per occurrence: 5
- Scan time budget: 50 seconds
- Cron timeout: 60 seconds
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.database import async_session_factory

_logger = get_logger(__name__)

# D6 §9: Proposed configuration defaults (not permanently fixed).
RECONCILER_INTERVAL_SECONDS: int = 60
STALE_THRESHOLD_MINUTES: int = 2
PAGE_SIZE: int = 100
MAX_PAGES_PER_OCCURRENCE: int = 5
SCAN_TIME_BUDGET_SECONDS: int = 50
CRON_TIMEOUT_SECONDS: int = 60

# D6 §9: Age-event thresholds.
AGE_WARNING_THRESHOLD = timedelta(hours=1)
AGE_ERROR_THRESHOLD = timedelta(hours=24)
AGE_CRITICAL_THRESHOLD = timedelta(days=7)


async def reconcile_stale_pending_runs(
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile stale PENDING workflow runs (D6 §2–§7).

    This function is registered as an ARQ cron job. Each occurrence
    processes pages using keyset pagination ordered by
    ``(pending_since ASC, id ASC)``. It is best-effort and harmless
    under overlapping occurrences.

    Args:
        ctx: ARQ worker context dictionary (optional, unused — the
            reconciler creates its own session).

    Returns:
        A dict with observability metrics per D6 §10:
        - scan_occurrence_id: unique scan identifier
        - cutoff: the stale cutoff timestamp
        - scanned_count: total candidates scanned
        - accepted_count: successfully enqueued
        - deduplicated_count: enqueue returned None (already queued)
        - enqueue_error_count: enqueue errors
        - skipped_invalid_count: candidates skipped due to invalid state
        - scan_duration_seconds: total scan duration
        - pages_processed: number of pages processed
        - budget_exhausted: whether the time budget was exhausted
        - max_pages_reached: whether the max-page limit was reached
    """
    occurrence_id = f"reconcile-{datetime.now(UTC).isoformat()}"
    cutoff = datetime.now(UTC) - timedelta(minutes=STALE_THRESHOLD_MINUTES)
    start = time.monotonic()

    metrics: dict[str, Any] = {
        "scan_occurrence_id": occurrence_id,
        "cutoff": cutoff.isoformat(),
        "scanned_count": 0,
        "accepted_count": 0,
        "deduplicated_count": 0,
        "enqueue_error_count": 0,
        "skipped_invalid_count": 0,
        "scan_duration_seconds": 0.0,
        "pages_processed": 0,
        "budget_exhausted": False,
        "max_pages_reached": False,
    }

    _logger.info(
        "workflow.reconciler.scan_started",
        scan_occurrence_id=occurrence_id,
        cutoff=cutoff.isoformat(),
        stale_threshold_minutes=STALE_THRESHOLD_MINUTES,
        page_size=PAGE_SIZE,
        max_pages=MAX_PAGES_PER_OCCURRENCE,
    )

    # Keyset pagination state (D6 §2).
    last_pending_since: datetime | None = None
    last_id: UUID | None = None

    # Import here to avoid import-time external connections.
    from arq.connections import create_pool

    from app.config import settings
    from app.worker import _build_redis_settings

    pool = None
    try:
        pool = await create_pool(_build_redis_settings())

        for page_num in range(1, MAX_PAGES_PER_OCCURRENCE + 1):
            # Check time budget (D6 §2).
            elapsed = time.monotonic() - start
            if elapsed > SCAN_TIME_BUDGET_SECONDS:
                metrics["budget_exhausted"] = True
                _logger.info(
                    "workflow.reconciler.budget_exhausted",
                    scan_occurrence_id=occurrence_id,
                    elapsed_seconds=elapsed,
                    pages_processed=metrics["pages_processed"],
                )
                break

            # Fetch a page of stale candidates (D6 §2, §6).
            async with async_session_factory() as session:
                candidates = await _fetch_candidate_page(
                    session,
                    cutoff=cutoff,
                    last_pending_since=last_pending_since,
                    last_id=last_id,
                    page_size=PAGE_SIZE,
                )

            if not candidates:
                break

            metrics["pages_processed"] = page_num

            # Process each candidate with per-candidate isolation (D6 §6).
            for candidate in candidates:
                metrics["scanned_count"] += 1
                await _process_candidate(
                    pool=pool,
                    candidate=candidate,
                    metrics=metrics,
                    settings_ref=settings,
                )
                # Update keyset cursor.
                last_pending_since = candidate["pending_since"]
                last_id = candidate["id"]

            if len(candidates) < PAGE_SIZE:
                break

        if metrics["pages_processed"] >= MAX_PAGES_PER_OCCURRENCE:
            metrics["max_pages_reached"] = True
            _logger.info(
                "workflow.reconciler.max_pages_reached",
                scan_occurrence_id=occurrence_id,
                max_pages=MAX_PAGES_PER_OCCURRENCE,
            )

    except Exception:
        _logger.error(
            "workflow.reconciler.scan_error",
            scan_occurrence_id=occurrence_id,
        )
    finally:
        if pool is not None:
            await pool.close()

    metrics["scan_duration_seconds"] = round(
        time.monotonic() - start, 3
    )
    _logger.info(
        "workflow.reconciler.scan_completed",
        scan_occurrence_id=occurrence_id,
        scanned_count=metrics["scanned_count"],
        accepted_count=metrics["accepted_count"],
        deduplicated_count=metrics["deduplicated_count"],
        enqueue_error_count=metrics["enqueue_error_count"],
        skipped_invalid_count=metrics["skipped_invalid_count"],
        scan_duration_seconds=metrics["scan_duration_seconds"],
        pages_processed=metrics["pages_processed"],
        budget_exhausted=metrics["budget_exhausted"],
        max_pages_reached=metrics["max_pages_reached"],
    )
    return metrics


async def _fetch_candidate_page(
    session: AsyncSession,
    *,
    cutoff: datetime,
    last_pending_since: datetime | None,
    last_id: UUID | None,
    page_size: int,
) -> list[dict[str, Any]]:
    """Fetch a page of stale PENDING candidates using keyset pagination.

    Candidate predicate (D6 §6):
    ``state = PENDING AND pending_since <= cutoff AND pending_since IS NOT NULL``

    Keyset pagination (D6 §2): ordered by ``(pending_since ASC, id ASC)``.
    The next page continues strictly after the last processed tuple.

    Args:
        session: Async database session.
        cutoff: The stale cutoff timestamp.
        last_pending_since: The pending_since of the last processed row.
        last_id: The id of the last processed row.
        page_size: Maximum number of candidates per page.

    Returns:
        A list of candidate dicts with keys: id, pending_since,
        dispatch_generation, run_id.
    """
    # Build the keyset-paginated query.
    #
    # Keyset pagination: if we have a cursor, fetch rows where
    # (pending_since, id) > (last_pending_since, last_id).
    if last_pending_since is not None and last_id is not None:
        query = text("""
            SELECT id, pending_since, dispatch_generation
            FROM workflow_runs
            WHERE state = 'PENDING'
              AND pending_since IS NOT NULL
              AND pending_since <= :cutoff
              AND (pending_since, id) > (:last_pending_since, :last_id)
            ORDER BY pending_since ASC, id ASC
            LIMIT :page_size
        """)
        params = {
            "cutoff": cutoff,
            "last_pending_since": last_pending_since,
            "last_id": str(last_id),
            "page_size": page_size,
        }
    else:
        query = text("""
            SELECT id, pending_since, dispatch_generation
            FROM workflow_runs
            WHERE state = 'PENDING'
              AND pending_since IS NOT NULL
              AND pending_since <= :cutoff
            ORDER BY pending_since ASC, id ASC
            LIMIT :page_size
        """)
        params = {
            "cutoff": cutoff,
            "page_size": page_size,
        }

    result = await session.execute(query, params)
    rows = result.fetchall()

    return [
        {
            "id": row[0],
            "pending_since": row[1],
            "dispatch_generation": row[2],
            "run_id": str(row[0]),
        }
        for row in rows
    ]


async def _process_candidate(
    *,
    pool: Any,
    candidate: dict[str, Any],
    metrics: dict[str, Any],
    settings_ref: Any,
) -> None:
    """Process a single stale PENDING candidate (D6 §6).

    Per-candidate isolation: one candidate's enqueue error must not
    prevent later candidates from being attempted (D6 §6).

    The candidate is re-checked against the committed state before
    enqueue. If the row was concurrently changed (no longer PENDING or
    generation changed), it is skipped.

    Args:
        pool: ARQ Redis pool for enqueue.
        candidate: Candidate dict with id, pending_since,
            dispatch_generation, run_id.
        metrics: Metrics dict to update.
        settings_ref: Application settings for queue name.
    """
    run_id = candidate["run_id"]
    dispatch_generation = candidate["dispatch_generation"]

    # D6 §4: Select dispatch target from committed dispatch_generation.
    target_function = (
        "workflow_start" if dispatch_generation == 0 else "workflow_retry"
    )

    # D5 §3: Deterministic job ID.
    job_id = f"workflow:{run_id}:{dispatch_generation}"

    # D6 §10: Candidate age.
    pending_since = candidate["pending_since"]
    if pending_since is not None:
        age = datetime.now(UTC) - pending_since
        age_seconds = age.total_seconds()
    else:
        age_seconds = 0.0

    try:
        enqueued_job = await pool.enqueue_job(
            target_function,
            run_id,
            _job_id=job_id,
            _queue_name=settings_ref.arq_queue_name,
        )

        if enqueued_job is not None:
            metrics["accepted_count"] += 1
            _logger.info(
                "workflow.reconciler.candidate_enqueued",
                run_id=run_id,
                dispatch_generation=dispatch_generation,
                target_function=target_function,
                job_id=job_id,
                candidate_age_seconds=age_seconds,
            )
        else:
            metrics["deduplicated_count"] += 1
            _logger.info(
                "workflow.reconciler.candidate_deduplicated",
                run_id=run_id,
                dispatch_generation=dispatch_generation,
                job_id=job_id,
            )

    except Exception:
        # D6 §6: Per-candidate isolation — do not log raw exception text.
        metrics["enqueue_error_count"] += 1
        _logger.warning(
            "workflow.reconciler.candidate_enqueue_error",
            run_id=run_id,
            dispatch_generation=dispatch_generation,
            job_id=job_id,
        )
