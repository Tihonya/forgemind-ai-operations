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
