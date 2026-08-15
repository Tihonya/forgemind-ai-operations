"""Pydantic schemas for the approval-request API (WP-REC-04A).

Request schemas validate the bounded create/decision inputs; response
schemas expose safe approval-request fields. No secret, vendor, price,
amount, currency, payment, or financial field is ever present.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.approval import ApprovalStatus


class ApprovalRequestCreate(BaseModel):
    """Request body for POST /approval-requests.

    Attributes:
        recommendation_id: Authoritative recommendation UUID.
        risk_id: Originating risk identifier (e.g. ``RISK-001``).
        action_type: Action type (``CREATE_PROCUREMENT_TASK``).
        component_code: Component/item identity for the controlled action
            (e.g. ``CTRL-X4``). Verified against the deterministic risk
            engine at creation and persisted in the action snapshot.
        quantity: Executable quantity for the controlled action, derived
            from the authoritative shortage. Must be positive; verified
            against the risk engine at creation and persisted in the
            action snapshot.
    """

    model_config = ConfigDict(extra="forbid")

    recommendation_id: UUID = Field(
        ..., description="Authoritative recommendation UUID"
    )
    risk_id: str = Field(
        ..., min_length=1, max_length=100, description="Risk identifier (e.g. RISK-001)"
    )
    action_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Action type (CREATE_PROCUREMENT_TASK)",
    )
    component_code: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Component/item identity (e.g. CTRL-X4)",
    )
    quantity: Decimal = Field(
        ...,
        gt=0,
        description="Positive executable quantity (authoritative shortage)",
    )

    @field_validator("risk_id", "action_type", "component_code")
    @classmethod
    def _reject_whitespace(cls, v: str) -> str:
        if v.strip() == "":
            raise ValueError("must not be whitespace-only")
        if v != v.strip():
            raise ValueError("must not contain leading or trailing whitespace")
        return v


class DecisionRequest(BaseModel):
    """Request body for the approve/reject decision endpoints.

    The single ``comment`` field carries the approval comment on
    ``/approve`` and the rejection reason on ``/reject``.
    """

    model_config = ConfigDict(extra="forbid")

    comment: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Approval comment (approve) or rejection reason (reject)",
    )

    @field_validator("comment")
    @classmethod
    def _reject_whitespace_only(cls, v: str) -> str:
        if v.strip() == "":
            raise ValueError("comment must not be whitespace-only")
        return v


class ApprovalRequestResponse(BaseModel):
    """Read/response schema for a single approval request."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Approval request UUID")
    correlation_id: UUID = Field(..., description="Correlation UUID v4")
    recommendation_id: UUID = Field(..., description="Authoritative recommendation UUID")
    workflow_run_id: UUID = Field(..., description="Workflow run UUID")
    risk_id: str = Field(..., description="Originating risk identifier")
    action_type: str = Field(..., description="Bound action type")
    action_snapshot: dict[str, Any] = Field(
        ..., description="Immutable canonical action snapshot"
    )
    binding_hash: str = Field(..., description="SHA-256 binding hash")
    requested_by: UUID = Field(..., description="Requester user UUID")
    requested_by_username: str = Field(..., description="Requester username snapshot")
    status: ApprovalStatus = Field(..., description="Approval status")
    decided_by: UUID | None = Field(
        default=None, description="Decision actor user UUID"
    )
    decided_by_username: str | None = Field(
        default=None, description="Decision actor username snapshot"
    )
    decision_comment: str | None = Field(
        default=None, description="Approval comment or rejection reason"
    )
    requested_at: datetime = Field(..., description="Creation timestamp")
    decided_at: datetime | None = Field(
        default=None, description="Decision timestamp"
    )


class ApprovalRequestListResponse(BaseModel):
    """Paginated list response for GET /approval-requests."""

    items: list[ApprovalRequestResponse] = Field(
        default_factory=list, description="Approval requests (newest first)"
    )
    limit: int = Field(..., description="Requested limit")
    offset: int = Field(..., description="Requested offset")
    total: int = Field(..., description="Total number of approval requests")
