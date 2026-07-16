"""Diagnostic job worker function.

Implements the ARQ-compatible async function that executes system diagnostic
checks and persists the lifecycle to PostgreSQL. Uses existing SQLAlchemy
session factory, DiagnosticJob model, and dependency health service.

Claim mechanism (atomic):
- Single UPDATE ... WHERE id=:id AND status IN ('pending','failed') RETURNING id
- Exactly one worker may claim a pending/failed job; losers see zero rows.
- The claim commits before external dependency checks.
- No SELECT-then-UPDATE race: atomic conditional write.

Transaction boundaries:
- Claim session commits running state BEFORE external checks.
- Completion/failure persistence uses separate sessions.
- All sessions close via async context managers.
- No transaction is held while external dependency checks execute.

Idempotency / duplicate delivery:
- completed: return existing summary without rerunning.
- running: rejected deterministically (another worker holds it).
- failed: retry allowed — stale fields cleared, re-execute.
- missing: raise RuntimeError (nothing to persist).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from app.core.context import correlation_context
from app.core.correlation import validate_correlation_id
from app.core.logging import get_logger
from app.database import async_session_factory
from app.models.diagnostic import DiagnosticJob
from app.services.dependency_health import check_all_dependencies

logger = get_logger(__name__)

# Maximum error message length to prevent unbounded storage.
_MAX_ERROR_MESSAGE_LENGTH: int = 500


async def run_diagnostic_job(
    ctx: dict[str, Any],
    diagnostic_job_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """Execute diagnostic job and persist lifecycle.

    Args:
        ctx: ARQ worker context. Not used for session or DB resources;
            the module-level async_session_factory is used instead.
        diagnostic_job_id: UUID string of the DiagnosticJob row.
        correlation_id: UUID v4 string for correlation context.

    Returns:
        JSON-serializable dict with job_id, status, duration_ms, summary.

    Raises:
        ValueError: If inputs are invalid, or job is already running.
        RuntimeError: If job row does not exist.
        Exception: Re-raised after persisting failure state, so ARQ records
            the job as failed.
    """
    # Validate inputs BEFORE any database access
    _validate_inputs(diagnostic_job_id, correlation_id)

    with correlation_context(correlation_id):
        job_uuid = uuid.UUID(diagnostic_job_id)
        job_id_str = str(job_uuid)
        start_time = time.perf_counter()

        # --- Phase A: Check current state ---
        state = await _load_state(job_uuid)

        if state is None:
            logger.info(
                "diagnostic_job_skipped",
                diagnostic_job_id=job_id_str,
                reason="not_found",
            )
            raise RuntimeError(f"Diagnostic job {job_id_str} not found")

        current_status = state["status"]

        if current_status == "completed":
            logger.info(
                "diagnostic_job_skipped",
                diagnostic_job_id=job_id_str,
                reason="already_completed",
            )
            return {
                "job_id": job_id_str,
                "status": "completed",
                "duration_ms": state["duration_ms"],
                "dependency_summary": "cached",
            }

        if current_status == "running":
            logger.info(
                "diagnostic_job_skipped",
                diagnostic_job_id=job_id_str,
                reason="already_running",
            )
            raise ValueError(f"Diagnostic job {job_id_str} is already running")

        # --- Phase B: Atomic claim (pending/failed → running) ---
        claimed = await _try_claim(job_uuid)
        if not claimed:
            # Another worker claimed it between our read and claim, or
            # status changed to completed/running concurrently.
            logger.info(
                "diagnostic_job_skipped",
                diagnostic_job_id=job_id_str,
                reason="claim_failed",
            )
            # Re-read state to determine what happened
            state = await _load_state(job_uuid)
            if state is None:
                raise RuntimeError(f"Diagnostic job {job_id_str} not found")
            if state["status"] == "completed":
                return {
                    "job_id": job_id_str,
                    "status": "completed",
                    "duration_ms": state["duration_ms"],
                    "dependency_summary": "cached",
                }
            # Otherwise it's running (another worker) or back to failed
            # (transient). Running case is a real conflict:
            if state["status"] == "running":
                raise ValueError(f"Diagnostic job {job_id_str} is already running")
            # If still pending/failed after lost claim — extremely unlikely
            # race. Log and raise to avoid silent loops.
            raise RuntimeError(
                f"Diagnostic job {job_id_str} claim collision; status={state['status']}"
            )

        logger.info(
            "diagnostic_job_started",
            diagnostic_job_id=job_id_str,
            status="running",
        )

        # --- Phase C: Run dependency checks (NO session held) ---
        try:
            snapshot = await check_all_dependencies()
        except Exception:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            await _persist_failure(job_uuid, duration_ms, "Dependency check error")
            raise

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        # Serialize Pydantic models to plain dicts (JSON-safe, JSONB-compatible)
        checks_data: list[dict[str, Any]] = [c.model_dump() for c in snapshot.checks]

        # --- Phase D: Persist completion ---
        await _persist_completion(job_uuid, checks_data, duration_ms)

        logger.info(
            "diagnostic_job_completed",
            diagnostic_job_id=job_id_str,
            status="completed",
            duration_ms=duration_ms,
            dependency_summary=snapshot.summary,
        )

        return {
            "job_id": job_id_str,
            "status": "completed",
            "duration_ms": duration_ms,
            "dependency_summary": snapshot.summary,
        }


def _validate_inputs(diagnostic_job_id: str, correlation_id: str) -> None:
    """Validate both inputs; raises ValueError on failure. No DB access."""
    try:
        uuid.UUID(diagnostic_job_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"Invalid diagnostic_job_id: {diagnostic_job_id!r} is not a valid UUID"
        ) from exc

    # validate_correlation_id raises InvalidCorrelationIdError (ValueError subclass)
    validate_correlation_id(correlation_id)


async def _load_state(job_id: uuid.UUID) -> dict[str, Any] | None:
    """Read job row status and scalar fields in a short session.

    Returns a dict with keys 'status' and 'duration_ms', or None if missing.
    The session is always closed before return.
    """
    async with async_session_factory() as session:
        result = await session.execute(
            select(DiagnosticJob.status, DiagnosticJob.duration_ms)
            .where(DiagnosticJob.id == job_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        return {"status": row.status, "duration_ms": row.duration_ms}


async def _try_claim(job_id: uuid.UUID) -> bool:
    """Atomically claim a pending/failed job by setting it to running.

    Uses a single UPDATE ... WHERE ... RETURNING to make the claim atomic.
    If the row is not in a claimable state, returns False immediately.

    On successful claim, also resets stale retry fields:
    - started_at → now
    - completed_at → None
    - duration_ms → None
    - error_message → None
    - checks → None

    Returns True if claimed, False otherwise.
    """
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        result = await session.execute(
            update(DiagnosticJob)
            .where(DiagnosticJob.id == job_id)
            .where(DiagnosticJob.status.in_(("pending", "failed")))
            .values(
                status="running",
                started_at=now,
                updated_at=now,
                # Clear stale fields on retry/re-execution
                completed_at=None,
                duration_ms=None,
                error_message=None,
                checks=None,
            )
            .returning(DiagnosticJob.id)
        )
        claimed = result.first() is not None
        await session.commit()
        return claimed


async def _persist_completion(
    job_id: uuid.UUID,
    checks_data: list[dict[str, Any]],
    duration_ms: int,
) -> None:
    """Persist completed state in a separate session."""
    now = datetime.now(UTC)
    async with async_session_factory() as session:
        result = await session.execute(
            select(DiagnosticJob).where(DiagnosticJob.id == job_id)
        )
        job = result.scalar_one()
        job.status = "completed"
        job.completed_at = now
        job.checks = checks_data  # type: ignore[assignment]
        job.duration_ms = duration_ms
        job.error_message = None
        job.updated_at = now
        await session.commit()


async def _persist_failure(
    job_id: uuid.UUID,
    duration_ms: int,
    safe_description: str,
) -> None:
    """Persist failed state with safe bounded error message.

    The error message is:
    - Bounded to _MAX_ERROR_MESSAGE_LENGTH (500 chars).
    - Single-line (newlines stripped).
    - Contains no raw exception text, URLs, credentials, or tracebacks.
    - Uses only the pre-authored safe_description string.
    """
    # Build safe message: static prefix + safe_description only.
    # Never interpolate the original exception or its message.
    error_msg = f"Diagnostic check failed: {safe_description}"
    # Strip any accidental newlines (defensive — safe_description is static)
    error_msg = error_msg.replace("\n", " ").replace("\r", " ")
    if len(error_msg) > _MAX_ERROR_MESSAGE_LENGTH:
        error_msg = error_msg[:_MAX_ERROR_MESSAGE_LENGTH]

    now = datetime.now(UTC)
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(DiagnosticJob).where(DiagnosticJob.id == job_id)
            )
            job = result.scalar_one_or_none()
            if job is None:
                return

            job.status = "failed"
            job.completed_at = now
            job.duration_ms = duration_ms
            job.error_message = error_msg
            job.updated_at = now
            await session.commit()

            logger.error(
                "diagnostic_job_failed",
                diagnostic_job_id=str(job_id),
                status="failed",
                duration_ms=duration_ms,
            )
    except Exception:
        logger.exception(
            "diagnostic_job_persistence_failed",
            diagnostic_job_id=str(job_id),
        )
