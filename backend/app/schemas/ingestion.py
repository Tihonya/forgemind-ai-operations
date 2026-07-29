"""Ingestion job API schemas.

Defines typed Pydantic models for the document ingestion enqueue endpoint.
Only approved public fields are exposed. No ORM objects or internal Redis
job objects leak to the HTTP contract.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class IngestionEnqueueResponse(BaseModel):
    """Response for POST /api/v1/documents/{document_id}/versions/{version_id}/ingest.

    HTTP 202
    {
        "job_id": "document-ingestion:<version_id>",
        "document_id": "<document-uuid>",
        "document_version_id": "<version-uuid>",
        "correlation_id": "<uuid-v4>",
        "status": "pending"
    }

    Attributes:
        job_id: Deterministic ARQ job id derived from the document version UUID.
        document_id: UUID of the parent document.
        document_version_id: UUID of the document version being ingested.
        correlation_id: UUID v4 of the request correlation context.
        status: Lifecycle status at the moment of enqueuing. Always "pending".
    """

    job_id: str = Field(..., description="Deterministic ARQ job id")
    document_id: str = Field(..., description="Document UUID")
    document_version_id: str = Field(..., description="Document version UUID")
    correlation_id: str = Field(..., description="Request correlation UUID v4")
    status: Literal["pending"] = Field(
        ..., description="Lifecycle status; always 'pending' on creation"
    )
