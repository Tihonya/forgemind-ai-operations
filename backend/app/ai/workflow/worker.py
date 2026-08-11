"""ARQ worker functions for workflow execution (WP-REC-03F D5).

This module defines the two ARQ worker functions:

- ``workflow_start``: executes a workflow run started via the start API.
- ``workflow_retry``: executes a workflow run re-enqueued via the retry API.

Both functions:

- accept ``run_id`` as the only workflow-specific function argument (D3 §5);
- obtain the dispatch generation from the ARQ job identity (``ctx["job_id"]``)
  per D5 §4;
- compare the queued generation with the committed
  ``WorkflowRun.dispatch_generation``;
- skip stale-generation jobs without provider execution or state
  regression (D5 §4);
- retain the guarded database ``PENDING → RUNNING`` transition with
  generation check (D6 §5);
- prevent duplicate delivery from executing the workflow more than once.

Registration (D5 §5):

Both functions are registered in ``WorkerSettings.functions`` via
``arq.func(...)`` with:
- ``keep_result=0`` — no ARQ result key stored;
- ``max_tries=1`` — no ARQ automatic retry;
- timeout from ``settings.arq_job_timeout``.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

from app.ai.provider.factory import create_chat_provider
from app.ai.workflow.vertical import execute_workflow
from app.core.context import correlation_context
from app.core.logging import get_logger
from app.database import async_session_factory

_logger = get_logger(__name__)

# Prefix for workflow ARQ job IDs (D5 §3).
_JOB_ID_PREFIX = "workflow:"


def _parse_generation_from_job_id(ctx: dict[str, Any]) -> int | None:
    """Extract the dispatch generation from the ARQ job identity.

    The ARQ job ID is constructed as ``workflow:{run_id}:{dispatch_generation}``
    per D5 §3. The job_id is available in ``ctx["job_id"]``.

    Args:
        ctx: ARQ worker context dictionary.

    Returns:
        The parsed dispatch generation integer, or ``None`` if the job
        ID is malformed or missing.
    """
    job_id: str | None = ctx.get("job_id")
    if job_id is None or not job_id.startswith(_JOB_ID_PREFIX):
        return None

    # Strip the prefix and split on ":" — the remaining part is
    # "{run_id}:{dispatch_generation}".
    remainder = job_id[len(_JOB_ID_PREFIX):]
    parts = remainder.rsplit(":", 1)
    if len(parts) != 2:
        return None

    try:
        return int(parts[1])
    except (ValueError, TypeError):
        return None


async def _execute_workflow_job(
    ctx: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    """Common execution path for workflow_start and workflow_retry.

    Args:
        ctx: ARQ worker context dictionary.
        run_id: Workflow run UUID string.

    Returns:
        A dict with run_id, final_state, and execution metadata.
    """
    # Parse the dispatch generation from the ARQ job identity (D5 §4).
    queued_generation = _parse_generation_from_job_id(ctx)
    if queued_generation is None:
        _logger.warning(
            "workflow.worker.malformed_job_id",
            run_id=run_id,
            job_id=ctx.get("job_id"),
        )
        return {
            "run_id": run_id,
            "final_state": "SKIPPED",
            "reason": "malformed_job_id",
        }

    run_uuid = UUID(run_id)

    # Bind correlation context for structured logging.
    correlation_id = ctx.get("correlation_id")
    if correlation_id is not None:
        with correlation_context(str(correlation_id)):
            return await _do_execute(ctx, run_uuid, run_id, queued_generation)
    return await _do_execute(ctx, run_uuid, run_id, queued_generation)


async def _do_execute(
    ctx: dict[str, Any],
    run_uuid: UUID,
    run_id_str: str,
    queued_generation: int,
) -> dict[str, Any]:
    """Execute the workflow with a fresh session and provider.

    Args:
        ctx: ARQ worker context (used for job_try logging).
        run_uuid: Parsed workflow run UUID.
        run_id_str: Workflow run UUID string (for logging).
        queued_generation: Parsed dispatch generation.

    Returns:
        Result dict with run_id, final_state, and duration.
    """
    job_try: int = ctx.get("job_try", 1)
    start = time.monotonic()

    _logger.info(
        "workflow.worker.started",
        run_id=run_id_str,
        queued_generation=queued_generation,
        job_try=job_try,
    )

    # Fresh session per job (existing pattern from jobs/ingestion.py).
    async with async_session_factory() as session:
        try:
            # Create the chat provider through the factory (03A + 03D).
            provider = create_chat_provider()

            # Execute the vertical wiring.
            result = await execute_workflow(
                session=session,
                provider=provider,
                run_id=run_uuid,
                queued_generation=queued_generation,
            )

            # Commit only after successful execution.
            await session.commit()

            duration_ms = int((time.monotonic() - start) * 1000)
            _logger.info(
                "workflow.worker.completed",
                run_id=run_id_str,
                final_state=result.final_state,
                success=result.success,
                duration_ms=duration_ms,
            )
            return {
                "run_id": run_id_str,
                "final_state": result.final_state,
                "success": result.success,
                "duration_ms": duration_ms,
            }
        except Exception:
            await session.rollback()
            duration_ms = int((time.monotonic() - start) * 1000)
            _logger.error(
                "workflow.worker.failed",
                run_id=run_id_str,
                duration_ms=duration_ms,
            )
            return {
                "run_id": run_id_str,
                "final_state": "FAILED_INTERNAL",
                "success": False,
                "duration_ms": duration_ms,
            }


async def workflow_start(
    ctx: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    """ARQ worker function for workflow start execution.

    Accepts ``run_id`` as the only workflow-specific argument (D3 §5).
    The dispatch generation is obtained from the ARQ job identity
    (``ctx["job_id"]``) per D5 §4.

    Args:
        ctx: ARQ worker context dictionary.
        run_id: Workflow run UUID string.

    Returns:
        Dict with run_id, final_state, success, and duration_ms.
    """
    return await _execute_workflow_job(ctx, run_id)


async def workflow_retry(
    ctx: dict[str, Any],
    run_id: str,
) -> dict[str, Any]:
    """ARQ worker function for workflow retry execution.

    Accepts ``run_id`` as the only workflow-specific argument (D3 §5).
    The dispatch generation is obtained from the ARQ job identity
    (``ctx["job_id"]``) per D5 §4.

    The retry worker uses the same execution path as the start worker.
    The distinction is semantic: ``workflow_retry`` represents a
    re-enqueued job from an authorized retry (D1), while
    ``workflow_start`` represents the initial dispatch. Both share the
    deterministic dispatch-generation identity model (D5 §3).

    Args:
        ctx: ARQ worker context dictionary.
        run_id: Workflow run UUID string.

    Returns:
        Dict with run_id, final_state, success, and duration_ms.
    """
    return await _execute_workflow_job(ctx, run_id)
