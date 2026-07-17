"""Diagnostic job API schemas.

Defines typed Pydantic models for the diagnostic enqueue endpoint.
Only approved public fields (plan §11.1) are exposed. No ORM objects
or internal Redis job objects leak to the HTTP contract.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class DiagnosticCreateResponse(BaseModel):
    """Response for ``POST /api/v1/system/diagnostics``.

    Approved contract §11.1:

        HTTP 202
        {
            "job_id": "uuid",
            "correlation_id": "uuid-v4",
            "status": "pending"
        }

    Attributes:
        job_id: UUID of the diagnostic job row in ``diagnostic_jobs``.
        correlation_id: UUID v4 of the request correlation context
            (inherited from the request, not regenerated).
        status: Lifecycle status at the moment of enqueuing.
            Always ``"pending"`` for a freshly-created job.
    """

    job_id: UUID = Field(..., description="UUID of the diagnostic job row")
    correlation_id: UUID = Field(..., description="Request correlation UUID v4")
    status: str = Field(
        ...,
        pattern=r"^pending$",
        description="Lifecycle status; always 'pending' on creation",
    )


class DiagnosticJobResponse(BaseModel):
    """Response for ``GET /api/v1/system/diagnostics/{job_id}``.

    Approved contract §11.1:

        HTTP 200
        {
            "id": "uuid",
            "correlation_id": "uuid-v4",
            "status": "pending" | "running" | "completed" | "failed",
            "checks": {...} | null,
            "error_message": null | "...",
            "started_at": "2026-07-15T14:00:00Z" | null,
            "completed_at": "2026-07-15T14:00:01Z" | null,
            "duration_ms": 150 | null,
            "created_at": "2026-07-15T14:00:00Z"
        }

    Attributes:
        id: UUID of the diagnostic job row.
        correlation_id: UUID v4 of the request that enqueued this job.
        status: Current lifecycle status (pending/running/completed/failed).
        checks: Diagnostic check results (null for pending/running jobs).
        error_message: Safe, bounded error text (null unless failed).
        started_at: ISO-8601 timestamp when job started (null if pending).
        completed_at: ISO-8601 timestamp when job finished (null if not terminal).
        duration_ms: Execution duration in milliseconds (null if not completed).
        created_at: ISO-8601 timestamp when job row was created.
    """

    id: UUID = Field(..., description="Diagnostic job UUID")
    correlation_id: UUID = Field(..., description="Request correlation UUID v4")
    status: str = Field(
        ...,
        description="Lifecycle status: pending, running, completed, or failed",
    )
    checks: dict[str, str] | None = Field(
        default=None,
        description="Diagnostic check results (null for non-completed jobs)",
    )
    error_message: str | None = Field(
        default=None,
        description="Safe bounded error text (null unless job failed)",
    )
    started_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when job started (null if pending)",
    )
    completed_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp when job finished (null if not terminal)",
    )
    duration_ms: int | None = Field(
        default=None,
        description="Execution duration in milliseconds (null if not completed)",
    )
    created_at: str = Field(..., description="ISO-8601 timestamp when job was created")
