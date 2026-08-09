"""Pydantic schemas for workflow run and step (WP-REC-03B).

These schemas expose safe workflow lifecycle data for internal use and
future API consumption (WP-REC-03E owns the API endpoints). They
prevent accidental exposure of internal exception details or secrets.

WP-REC-03B owns only workflow-run and workflow-step schemas. The
recommendation wire schema (``backend/app/schemas/recommendation.py``)
is owned exclusively by WP-REC-03C. No HTTP request/response contracts
for start/retry endpoints are defined here (those belong to 03F).

WP-REC-03E extends this module with read-only API response schemas:
``RecommendationResponse``, ``WorkflowRunDetailResponse``,
``WorkflowRunSummarySchema``, and ``WorkflowRunListResponse``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.ai.workflow.state_machine import WorkflowState
from app.schemas.recommendation import RecommendationData


class WorkflowStepSchema(BaseModel):
    """Schema for a single workflow step record.

    Exposes safe step metadata: step name, status, model metadata,
    timing, and safe error data. Does not expose prompts, raw provider
    payloads, or internal exception details.

    Attributes:
        id: Step UUID.
        run_id: Parent run UUID.
        correlation_id: Correlation UUID (DEC-024).
        seq: Zero-based sequence within the run.
        step_name: Canonical step name.
        status: Step status (started, completed, failed).
        model_name: Model name for provider-call steps (null otherwise).
        latency_ms: Step duration in milliseconds (null if not completed).
        token_usage: Token usage dict (null for non-provider steps).
        step_metadata: Safe metadata (finish_reason, provider, etc.).
        error_code: Safe error classification code (null if no error).
        error_detail: Safe bounded error summary (null if no error).
        started_at: ISO-8601 timestamp when step started.
        completed_at: ISO-8601 timestamp when step completed/failed.
        created_at: ISO-8601 row creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Step UUID")
    run_id: UUID = Field(..., description="Parent run UUID")
    correlation_id: UUID = Field(..., description="Correlation UUID v4")
    seq: int = Field(..., description="Zero-based step sequence")
    step_name: str = Field(..., description="Canonical step name")
    status: str = Field(
        ...,
        description="Step status: started, completed, failed",
    )
    model_name: str | None = Field(
        default=None,
        description="Model name for provider-call steps",
    )
    latency_ms: int | None = Field(
        default=None,
        description="Step duration in milliseconds",
    )
    token_usage: dict[str, Any] | None = Field(
        default=None,
        description="Token usage stats from provider",
    )
    step_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Safe step metadata (finish_reason, provider, etc.)",
    )
    error_code: str | None = Field(
        default=None,
        description="Safe error classification code",
    )
    error_detail: str | None = Field(
        default=None,
        description="Safe bounded error summary",
    )
    started_at: datetime = Field(..., description="Step start timestamp")
    completed_at: datetime | None = Field(
        default=None,
        description="Step completion timestamp",
    )
    created_at: datetime = Field(..., description="Row creation timestamp")


class WorkflowRunSchema(BaseModel):
    """Schema for a workflow run record.

    Exposes safe run lifecycle data: state, correlation ID, timing,
    and safe error data. Does not expose internal exception details,
    API keys, or provider payloads.

    Attributes:
        id: Run UUID (also serves as run_id).
        correlation_id: Correlation UUID (DEC-024).
        state: Current workflow state (WorkflowState).
        plan_id: Production plan UUID.
        triggered_by: User/system that initiated the run.
        error_code: Safe error classification code (null if no error).
        error_detail: Safe bounded error summary (null if no error).
        started_at: ISO-8601 timestamp when run started (RUNNING).
        completed_at: ISO-8601 timestamp when run reached terminal state.
        created_at: ISO-8601 row creation timestamp.
        updated_at: ISO-8601 last-update timestamp.
        steps: List of workflow step records (optional, populated on
            eager load).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Run UUID (run_id)")
    correlation_id: UUID = Field(..., description="Correlation UUID v4")
    state: WorkflowState = Field(..., description="Current workflow state")
    plan_id: UUID = Field(..., description="Production plan UUID")
    triggered_by: str | None = Field(
        default=None,
        description="User/system that initiated the run",
    )
    error_code: str | None = Field(
        default=None,
        description="Safe error classification code",
    )
    error_detail: str | None = Field(
        default=None,
        description="Safe bounded error summary",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Run start timestamp (RUNNING)",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Terminal state timestamp",
    )
    created_at: datetime = Field(..., description="Row creation timestamp")
    updated_at: datetime = Field(..., description="Last-update timestamp")
    steps: list[WorkflowStepSchema] = Field(
        default_factory=list,
        description="Workflow step records",
    )


class RecommendationResponse(BaseModel):
    """Read-only API response schema for a Recommendation (WP-REC-03E).

    Wraps the ORM ``Recommendation`` model and parses ``content`` (JSONB)
    against the ``RecommendationData`` wire schema. If ``content`` is
    ``None`` (03F has not written yet), ``content`` is ``None`` in the
    response — a safe absence, not an error.

    Schema-invalid non-null ``content`` is an integrity failure. The
    API endpoint (not this schema) catches ``ValidationError`` and
    returns HTTP 500 with ``{"error": "invalid_recommendation_content"}``.

    Attributes:
        id: Recommendation UUID.
        status: Recommendation status (only "VALIDATED" in 03B).
        schema_version: Schema version string (e.g. "1.0").
        content: Validated recommendation payload, or None if not
            yet persisted.
        created_at: Row creation timestamp.
        updated_at: Last-update timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Recommendation UUID")
    status: Literal["VALIDATED"] = Field(
        ..., description="Recommendation status"
    )
    schema_version: str | None = Field(
        default=None,
        description="Recommendation schema version (e.g. 1.0)",
    )
    content: RecommendationData | None = Field(
        default=None,
        description="Validated recommendation payload, or None if not persisted",
    )
    created_at: datetime = Field(..., description="Row creation timestamp")
    updated_at: datetime = Field(..., description="Last-update timestamp")


class WorkflowRunDetailResponse(WorkflowRunSchema):
    """Detail API response for GET /workflow-runs/{run_id} (WP-REC-03E).

    Extends ``WorkflowRunSchema`` with the optional typed recommendation.

    Attributes:
        recommendation: Validated recommendation response, or None if
            no Recommendation row exists for this run.
    """

    recommendation: RecommendationResponse | None = Field(
        default=None,
        description="Validated recommendation, or None if no row exists",
    )


class WorkflowRunSummarySchema(BaseModel):
    """Lightweight summary for the paginated list endpoint (WP-REC-03E).

    Same fields as ``WorkflowRunSchema`` but WITHOUT steps and WITHOUT
    recommendation. Used for GET /workflow-runs list responses.

    Attributes:
        id: Run UUID (also serves as run_id).
        correlation_id: Correlation UUID (DEC-024).
        state: Current workflow state (WorkflowState).
        plan_id: Production plan UUID.
        triggered_by: User/system that initiated the run.
        error_code: Safe error classification code (null if no error).
        error_detail: Safe bounded error summary (null if no error).
        started_at: ISO-8601 timestamp when run started (RUNNING).
        completed_at: ISO-8601 timestamp when run reached terminal state.
        created_at: ISO-8601 row creation timestamp.
        updated_at: ISO-8601 last-update timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Run UUID (run_id)")
    correlation_id: UUID = Field(..., description="Correlation UUID v4")
    state: WorkflowState = Field(..., description="Current workflow state")
    plan_id: UUID = Field(..., description="Production plan UUID")
    triggered_by: str | None = Field(
        default=None,
        description="User/system that initiated the run",
    )
    error_code: str | None = Field(
        default=None,
        description="Safe error classification code",
    )
    error_detail: str | None = Field(
        default=None,
        description="Safe bounded error summary",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Run start timestamp (RUNNING)",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Terminal state timestamp",
    )
    created_at: datetime = Field(..., description="Row creation timestamp")
    updated_at: datetime = Field(..., description="Last-update timestamp")


class WorkflowRunListResponse(BaseModel):
    """Paginated list response for GET /workflow-runs (WP-REC-03E).

    Attributes:
        items: List of workflow run summaries ordered by
            created_at DESC, id DESC.
        limit: Requested limit.
        offset: Requested offset.
        total: Total number of workflow runs.
    """

    items: list[WorkflowRunSummarySchema] = Field(
        default_factory=list,
        description="Workflow run summaries",
    )
    limit: int = Field(..., description="Requested limit")
    offset: int = Field(..., description="Requested offset")
    total: int = Field(..., description="Total number of workflow runs")
