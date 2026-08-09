"""Workflow run detail API (WP-REC-03E).

Read-only REST API for viewing workflow run details:

- GET /api/v1/workflow-runs/{run_id} — run with steps and optional
  typed recommendation.
- GET /api/v1/workflow-runs — paginated list of run summaries.

This module is read-only. It does not start, retry, or persist
workflow runs. Recommendation content is validated against the
``RecommendationData`` wire schema at read time; schema-invalid
non-null content raises a stable HTTP 500 without leaking payload
details.

Authentication:
- Any authenticated user (existing ``get_current_user`` dependency).
- Canonical 401 from the auth dependency on missing/invalid token.

Security:
- Model metadata (name, latency) is returned but API keys are never
  exposed.
- No raw exception messages, provider payloads, or validation error
  details are returned.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.context import get_correlation_id
from app.core.logging import get_logger
from app.database import get_async_session
from app.dependencies import get_current_user
from app.models.workflow import Recommendation, WorkflowRun
from app.schemas.workflow import (
    RecommendationResponse,
    WorkflowRunDetailResponse,
    WorkflowRunListResponse,
    WorkflowRunSummarySchema,
)
from app.services.auth_service import AuthenticatedUser

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
