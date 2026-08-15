"""Pydantic schemas for the read-only audit API (WP-REC-04B).

These schemas expose safe audit-event fields for list/detail retrieval.
They never expose secrets: the service redacts secret-bearing structured
fields before persistence, and these response schemas carry no prompt,
provider-payload, token, or credential fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AuditEntityType, AuditEventType


class AuditEventResponse(BaseModel):
    """Read-only API response for a single audit event.

    Attributes:
        id: Audit event UUID.
        correlation_id: Correlation UUID v4.
        event_type: Canonical event type.
        actor_id: Actor user UUID (null for system events).
        actor_username: Actor username snapshot (null for system events).
        entity_type: Canonical entity type.
        entity_id: Logical entity UUID.
        workflow_run_id: Optional workflow run linkage.
        risk_id: Optional business risk identifier.
        before_summary: Optional structured pre-state summary.
        after_summary: Optional structured post-state summary.
        event_metadata: Optional structured event metadata.
        created_at: Row creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Audit event UUID")
    correlation_id: UUID = Field(..., description="Correlation UUID v4")
    event_type: AuditEventType = Field(..., description="Canonical event type")
    actor_id: UUID | None = Field(
        default=None, description="Actor user UUID (null for system events)"
    )
    actor_username: str | None = Field(
        default=None, description="Actor username snapshot"
    )
    entity_type: AuditEntityType = Field(..., description="Canonical entity type")
    entity_id: UUID = Field(..., description="Logical entity UUID")
    workflow_run_id: UUID | None = Field(
        default=None, description="Workflow run linkage"
    )
    risk_id: str | None = Field(
        default=None, description="Business risk identifier"
    )
    before_summary: dict[str, Any] | None = Field(
        default=None, description="Structured pre-state summary"
    )
    after_summary: dict[str, Any] | None = Field(
        default=None, description="Structured post-state summary"
    )
    event_metadata: dict[str, Any] | None = Field(
        default=None, description="Structured event metadata"
    )
    created_at: datetime = Field(..., description="Row creation timestamp")


class AuditEventListResponse(BaseModel):
    """Paginated list response for GET /audit-events.

    Attributes:
        items: Audit events ordered by created_at DESC, id DESC.
        limit: Requested limit.
        offset: Requested offset.
        total: Total number of audit events.
    """

    items: list[AuditEventResponse] = Field(
        default_factory=list, description="Audit events (newest first)"
    )
    limit: int = Field(..., description="Requested limit")
    offset: int = Field(..., description="Requested offset")
    total: int = Field(..., description="Total number of audit events")
