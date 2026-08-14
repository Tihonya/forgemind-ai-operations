"""Workflow run detail API (WP-REC-03E) and start/retry API (WP-REC-03F).

Read-only REST API for viewing workflow run details (03E):

- GET /api/v1/workflow-runs/{run_id} — run with steps and optional
  typed recommendation.
- GET /api/v1/workflow-runs — paginated list of run summaries.

Start/Retry REST API (03F):

- POST /api/v1/workflow-runs — start a new workflow run (PRODUCTION_MANAGER).
- POST /api/v1/workflow-runs/{run_id}/retry — retry a failed run.

Authentication:
- GET endpoints: any authenticated user (existing ``get_current_user``).
- POST /workflow-runs: PRODUCTION_MANAGER role (D2).
- POST /workflow-runs/{run_id}/retry: run creator OR PRODUCTION_MANAGER (D2).

Security:
- Model metadata (name, latency) is returned but API keys are never
  exposed.
- No raw exception messages, provider payloads, or validation error
  details are returned.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.state_machine import WorkflowState
from app.config import settings
from app.core.context import get_correlation_id
from app.core.logging import get_logger
from app.database import get_async_session
from app.dependencies import get_current_user, require_role
from app.models.production import ProductionPlan
from app.models.user import Role
from app.models.workflow import (
    Recommendation,
    WorkflowAuthorizationRecord,
    WorkflowRun,
)
from app.schemas.workflow import (
    RecommendationResponse,
    WorkflowRetryResponse,
    WorkflowRunDetailResponse,
    WorkflowRunListResponse,
    WorkflowRunSummarySchema,
    WorkflowStartRequest,
    WorkflowStartResponse,
)
from app.services.auth_service import AuthenticatedUser

if TYPE_CHECKING:  # pragma: no cover - typing only
    from arq.connections import ArqRedis

router = APIRouter(tags=["Workflow"])
logger = get_logger("app.api.workflow")


def _build_recommendation_response(
    rec: Recommendation | None,
) -> RecommendationResponse | None:
    """Construct and validate a ``RecommendationResponse`` from ORM row.

    Returns ``None`` if no Recommendation row exists.

    If the ORM row exists and ``content`` is ``None``, returns a
    response with ``content=None`` (safe absence).

    If the ORM row exists and ``content`` is a non-null dict that
    fails ``RecommendationData`` validation, raises ``ValidationError``.
    The caller catches it and returns HTTP 500 with a stable error code.
    """
    if rec is None:
        return None
    return RecommendationResponse.model_validate(rec)


@router.get(
    "/workflow-runs/{run_id}",
    response_model=WorkflowRunDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_workflow_run(
    run_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> WorkflowRunDetailResponse:
    """Return a workflow run with steps and optional recommendation.

    Args:
        run_id: UUID of the workflow run.
        current_user: Authenticated user (dependency-injected).
        session: Async database session (dependency-injected).

    Returns:
        WorkflowRunDetailResponse: Run with steps and optional typed
        recommendation.

    Raises:
        HTTPException(404): Run not found.
        HTTPException(500): Invalid recommendation content (integrity
            failure) or database error.
    """
    stmt = (
        select(WorkflowRun)
        .options(
            selectinload(WorkflowRun.steps),
            selectinload(WorkflowRun.recommendation),
        )
        .where(WorkflowRun.id == run_id)
    )
    result = await session.execute(stmt)
    run = result.scalars().one_or_none()

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "workflow_run_not_found", "run_id": str(run_id)},
        )

    recommendation: RecommendationResponse | None = None
    if run.recommendation is not None:
        try:
            recommendation = _build_recommendation_response(
                run.recommendation
            )
        except ValidationError:
            correlation_id = get_correlation_id()
            logger.error(
                "invalid_recommendation_content",
                correlation_id=str(correlation_id) if correlation_id else None,
                run_id=str(run_id),
                recommendation_id=str(run.recommendation.id),
                error="invalid_recommendation_content",
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "invalid_recommendation_content"},
            ) from None

    return WorkflowRunDetailResponse.model_validate(run).model_copy(
        update={"recommendation": recommendation}
    )


@router.get(
    "/workflow-runs",
    response_model=WorkflowRunListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_workflow_runs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> WorkflowRunListResponse:
    """Return a paginated list of workflow run summaries.

    Ordering: created_at DESC, id DESC (deterministic tie-breaker).

    Args:
        limit: Maximum number of items (1-200).
        offset: Number of items to skip.
        current_user: Authenticated user (dependency-injected).
        session: Async database session (dependency-injected).

    Returns:
        WorkflowRunListResponse: Paginated list with items, limit,
        offset, and total count.
    """
    total_stmt = select(func.count(WorkflowRun.id))
    total = (await session.execute(total_stmt)).scalar_one()

    stmt = (
        select(WorkflowRun)
        .order_by(
            WorkflowRun.created_at.desc(),
            WorkflowRun.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    result = await session.execute(stmt)
    runs = result.scalars().all()

    items = [WorkflowRunSummarySchema.model_validate(run) for run in runs]

    return WorkflowRunListResponse(
        items=items,
        limit=limit,
        offset=offset,
        total=total,
    )


# ---------------------------------------------------------------------------
# WP-REC-03F: Start / Retry endpoints
# ---------------------------------------------------------------------------

# Pool-factory seam (mirrors ingestion.py pattern).
PoolFactory = Callable[[], Awaitable["ArqRedis"]]


def _build_redis_settings() -> Any:
    """Build ARQ RedisSettings from app config without connecting."""
    from arq.connections import RedisSettings

    parsed = urlparse(settings.redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    path = parsed.path.lstrip("/")
    db = int(path) if path else 0
    password = parsed.password
    return RedisSettings(
        host=host,
        port=port,
        database=db,
        password=password,
    )


async def _default_pool_factory() -> ArqRedis:
    """Production pool factory wrapping arq.connections.create_pool."""
    from arq.connections import create_pool

    return await create_pool(_build_redis_settings())


# Module-level reference; monkeypatchable by tests.
_pool_factory: PoolFactory = _default_pool_factory

# Retry-eligible failed states (D1 + WP-REC-05 M2).
_RETRY_ELIGIBLE_STATES = frozenset({
    WorkflowState.FAILED_PROVIDER.value,
    WorkflowState.FAILED_VALIDATION.value,
    WorkflowState.FAILED_INTERNAL.value,
    WorkflowState.FAILED_RETRIEVAL.value,
})


async def _resolve_role_ids(
    session: AsyncSession,
    role_codes: frozenset[str],
) -> set[UUID]:
    """Resolve role codes to role UUIDs server-side (WP-REC-05 M1).

    Args:
        session: Async database session.
        role_codes: Set of role codes from the authenticated user.

    Returns:
        Set of role UUIDs (empty when the user has no roles).
    """
    if not role_codes:
        return set()
    stmt = select(Role.id).where(Role.code.in_(role_codes))
    result = await session.execute(stmt)
    return {row[0] for row in result.fetchall()}


def _build_location(run_id: UUID) -> str:
    """Build the location URL for the 202 response."""
    return f"{settings.api_v1_prefix}/workflow-runs/{run_id}"


@router.post(
    "/workflow-runs",
    response_model=WorkflowStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_workflow_run(
    request: WorkflowStartRequest,
    current_user: AuthenticatedUser = Depends(require_role({"PRODUCTION_MANAGER"})),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> WorkflowStartResponse:
    """Start a new workflow run (WP-REC-03F D2/D3).

    Requires PRODUCTION_MANAGER role. The request body ``plan_id``
    carries the external ``ProductionPlan.code`` (D3), not the database
    UUID. The endpoint resolves the code to the plan UUID, creates a
    durable PENDING run, commits, then enqueues an ARQ job.

    No provider call, risk calculation, validation, or workflow
    execution occurs inside the HTTP request.

    Args:
        request: Start request containing ``plan_id`` (plan code).
        current_user: Authenticated PRODUCTION_MANAGER user.
        session: Async database session.

    Returns:
        WorkflowStartResponse with run_id, state, and location.

    Raises:
        HTTPException(422): Invalid request body (D3 validation).
        HTTPException(404): Unknown plan code (production_plan_not_found).
        HTTPException(503): ARQ enqueue failure.
    """
    plan_code = request.plan_id

    # D3 §3: Resolve plan code to UUID before creating a WorkflowRun.
    plan_result = await session.execute(
        select(ProductionPlan).where(ProductionPlan.code == plan_code)
    )
    plan = plan_result.scalar_one_or_none()

    if plan is None:
        logger.info(
            "workflow.start.plan_not_found",
            plan_code=plan_code,
            username=current_user.username,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "production_plan_not_found",
                "plan_code": plan_code,
            },
        )

    # D2: Store current_user.username in triggered_by.
    # D5: Initial dispatch_generation = 0.
    # D6: Set pending_since on creation.
    engine = WorkflowEngine(provider=None, session=session)  # type: ignore[arg-type]
    run = await engine.create_run(
        plan_id=plan.id,
        triggered_by=current_user.username,
    )

    # WP-REC-05 M1: resolve role UUIDs server-side and capture the
    # generation-specific authorization record before enqueue. The
    # snapshot is immutable and committed atomically with the run.
    role_ids = await _resolve_role_ids(session, current_user.roles)
    auth_record = WorkflowAuthorizationRecord(
        run_id=run.id,
        dispatch_generation=run.dispatch_generation,
        user_id=current_user.user_id,
        role_snapshot=[str(role_id) for role_id in sorted(role_ids)],
        capture_action="start",
    )
    session.add(auth_record)
    await session.commit()

    logger.info(
        "workflow.start.run_created",
        run_id=str(run.id),
        plan_code=plan_code,
        plan_id=str(plan.id),
        triggered_by=current_user.username,
        dispatch_generation=run.dispatch_generation,
    )

    # D5 §3: Construct deterministic job ID.
    job_id = f"workflow:{run.id}:{run.dispatch_generation}"

    # Commit-then-enqueue (D1/C1): enqueue only after commit.
    pool = None
    try:
        pool = await _pool_factory()
        enqueued_job = await pool.enqueue_job(
            "workflow_start",
            str(run.id),
            _job_id=job_id,
            _queue_name=settings.arq_queue_name,
        )

        if enqueued_job is None:
            # Deduplicated — the job is already queued for this generation.
            logger.info(
                "workflow.start.deduplicated",
                run_id=str(run.id),
                job_id=job_id,
            )

    except HTTPException:
        raise
    except Exception:
        # D1/C1: Enqueue failure → 503 without run_id.
        logger.error(
            "workflow.start.enqueue_failed",
            run_id=str(run.id),
            plan_code=plan_code,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "workflow_enqueue_failed",
                "message": "The workflow job could not be enqueued. "
                "Please retry.",
            },
        ) from None
    finally:
        if pool is not None:
            await pool.close()

    return WorkflowStartResponse(
        run_id=run.id,
        state=WorkflowState(run.state),
        location=_build_location(run.id),
    )


@router.post(
    "/workflow-runs/{run_id}/retry",
    response_model=WorkflowRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_workflow_run(
    run_id: UUID,
    current_user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> WorkflowRetryResponse:
    """Retry a failed workflow run (WP-REC-03F D1/D2).

    Requires authentication. Permitted when:
    - ``current_user.username == workflow_run.triggered_by`` (run creator); or
    - the current user has the PRODUCTION_MANAGER role (D2).

    When ``triggered_by IS NULL``, only PRODUCTION_MANAGER may retry.

    Performs the D1 atomic conditional FAILED_* → PENDING transition,
    then enqueues an ARQ retry job.

    Args:
        run_id: UUID of the workflow run to retry.
        current_user: Authenticated user.
        session: Async database session.

    Returns:
        WorkflowRetryResponse with run_id, state, and location.

    Raises:
        HTTPException(404): Run not found.
        HTTPException(403): User is neither the run creator nor
            PRODUCTION_MANAGER.
        HTTPException(409): Run is not in an eligible failed state or
            another concurrent caller won the transition.
        HTTPException(503): ARQ enqueue failure.
    """
    # Load the run.
    result = await session.execute(
        select(WorkflowRun).where(WorkflowRun.id == run_id)
    )
    run = result.scalar_one_or_none()

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "workflow_run_not_found",
                "run_id": str(run_id),
            },
        )

    # D2: Authorization before the D1 conditional transition.
    is_manager = current_user.has_role("PRODUCTION_MANAGER")
    is_creator = (
        run.triggered_by is not None
        and run.triggered_by == current_user.username
    )

    if not is_manager and not is_creator:
        # D2 §5: When triggered_by IS NULL, only PRODUCTION_MANAGER.
        logger.info(
            "workflow.retry.unauthorized",
            run_id=str(run_id),
            username=current_user.username,
            triggered_by=run.triggered_by,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "insufficient_permissions",
                "message": "Only the run creator or a PRODUCTION_MANAGER "
                "may retry this workflow run.",
            },
        )

    # D1: Check if the run is in a retry-eligible failed state.
    if run.state not in _RETRY_ELIGIBLE_STATES:
        logger.info(
            "workflow.retry.not_eligible",
            run_id=str(run_id),
            state=run.state,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "workflow_run_not_retryable",
                "run_id": str(run_id),
                "state": run.state,
            },
        )

    # D1: Atomic conditional FAILED_* → PENDING transition.
    engine = WorkflowEngine(provider=None, session=session)  # type: ignore[arg-type]
    won = await engine.retry_transition(run)

    if not won:
        # Another concurrent caller won the transition.
        logger.info(
            "workflow.retry.conflict",
            run_id=str(run_id),
            state=run.state,
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "workflow_retry_conflict",
                "run_id": str(run_id),
                "state": run.state,
            },
        )

    # WP-REC-05 M1: capture a new generation-specific authorization record
    # from the retrying authenticated user. Prior generation records remain
    # unchanged; the record is committed atomically with the transition.
    role_ids = await _resolve_role_ids(session, current_user.roles)
    auth_record = WorkflowAuthorizationRecord(
        run_id=run.id,
        dispatch_generation=run.dispatch_generation,
        user_id=current_user.user_id,
        role_snapshot=[str(role_id) for role_id in sorted(role_ids)],
        capture_action="retry",
    )
    session.add(auth_record)
    await session.commit()

    logger.info(
        "workflow.retry.transitioned",
        run_id=str(run_id),
        dispatch_generation=run.dispatch_generation,
        triggered_by=run.triggered_by,
    )

    # D5 §3: Construct deterministic job ID with the new generation.
    job_id = f"workflow:{run.id}:{run.dispatch_generation}"

    # Commit-then-enqueue (D1/C1): enqueue only after commit.
    pool = None
    try:
        pool = await _pool_factory()
        enqueued_job = await pool.enqueue_job(
            "workflow_retry",
            str(run.id),
            _job_id=job_id,
            _queue_name=settings.arq_queue_name,
        )

        if enqueued_job is None:
            logger.info(
                "workflow.retry.deduplicated",
                run_id=str(run_id),
                job_id=job_id,
            )

    except HTTPException:
        raise
    except Exception:
        logger.error(
            "workflow.retry.enqueue_failed",
            run_id=str(run_id),
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "workflow_enqueue_failed",
                "message": "The workflow retry job could not be enqueued. "
                "The committed PENDING run remains available for "
                "reconciliation.",
            },
        ) from None
    finally:
        if pool is not None:
            await pool.close()

    return WorkflowRetryResponse(
        run_id=run.id,
        state=WorkflowState(run.state),
        location=_build_location(run.id),
    )
