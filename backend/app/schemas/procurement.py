"""Pydantic schemas for the procurement-task API (WP-REC-04C).

The request schema carries only the source approval-request identity — the
executable ``component_code`` and ``quantity`` are never client-controlled
and are re-read from the WP-REC-04A persisted snapshot (task §4). Response
schemas expose safe procurement-task fields; no vendor, supplier, price,
amount, currency, payment, bank/account, provider, or secret field exists.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.procurement import ProcurementTaskState


class ProcurementTaskCreate(BaseModel):
    """Request body for POST /procurement-tasks.

    The only client-controlled input is the source approval-request UUID.
    Every executable parameter is derived server-side from the immutable
    approval snapshot.
    """

    model_config = ConfigDict(extra="forbid")

    approval_request_id: UUID = Field(
        ..., description="Source approval request UUID (must be APPROVED)"
    )


class ProcurementTaskResponse(BaseModel):
    """Read/response schema for a single procurement task."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Procurement task UUID")
    correlation_id: UUID = Field(..., description="Correlation UUID v4")
    approval_request_id: UUID = Field(..., description="Source approval request UUID")
    recommendation_id: UUID = Field(..., description="Authoritative recommendation UUID")
    workflow_run_id: UUID = Field(..., description="Originating workflow run UUID")
    risk_id: str = Field(..., description="Originating risk identifier")
    action_type: str = Field(..., description="Bound action type")
    component_code: str = Field(..., description="Approved component/item identity")
    quantity: Decimal = Field(..., description="Approved positive quantity")
    binding_hash: str = Field(..., description="Approved SHA-256 binding hash")
    task_state: ProcurementTaskState = Field(..., description="Synthetic task state")
    requested_by: UUID = Field(..., description="Requester user UUID")
    requested_by_username: str = Field(..., description="Requester username snapshot")
    approved_by: UUID = Field(..., description="Approver user UUID")
    approved_by_username: str = Field(..., description="Approver username snapshot")
    created_at: datetime = Field(..., description="Creation timestamp")


class ProcurementTaskListResponse(BaseModel):
    """Paginated list response for GET /procurement-tasks."""

    items: list[ProcurementTaskResponse] = Field(
        default_factory=list, description="Procurement tasks (newest first)"
    )
    limit: int = Field(..., description="Requested limit")
    offset: int = Field(..., description="Requested offset")
    total: int = Field(..., description="Total number of procurement tasks")
