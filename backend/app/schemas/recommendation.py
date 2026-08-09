"""Pydantic wire schema for structured AI recommendations (WP-REC-03C).

This module defines the versioned wire format that AI model output must
match before it may be persisted as a recommendation. It implements the
structured recommendation schema described in ``02_SYSTEM_BEHAVIOR_AND_DATA.md``
§6 and enforces the architectural contract from DEC-004 / DEC-039 (TD-4):
deterministic code owns quantities, severity, and business-rule
enforcement; the AI enriches validated facts with explanations, business
impact, and structured recommended actions.

Ownership boundaries (WP-REC-03 decomposition §6, N5 resolved):

- **03C owns** this Pydantic wire schema (input/output validation).
- **03B owns** the SQLAlchemy ``Recommendation`` ORM model
  (``backend/app/models/workflow.py``) and its Alembic migration.
- **03F owns** the persistence path (writing a ``Recommendation`` row
  from validated output via 03B's ORM model).
- **03E owns** the read/retrieval API path.

This module performs no persistence and no workflow-state mutation. It
only defines the data contract that the validator
(``backend/app/ai/workflow/schema_validator.py``) enforces.

The ``plan_id`` field in this wire schema is the external plan
identifier (e.g. ``"PLAN-2026-W31"``), not the UUID foreign key used by
the SQLAlchemy ``Recommendation`` ORM model. Mapping the external
identifier to the database entity belongs to the future persistence path
(03F) and is outside 03C scope.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Canonical schema version. The validator rejects output carrying any
# other version. Bumping this constant is a schema-versioning event that
# must be coordinated with the prompt template version
# (``backend/app/ai/workflow/prompts.py``).
RECOMMENDATION_SCHEMA_VERSION: Literal["1.0"] = "1.0"


class Source(BaseModel):
    """A document source citation referenced by a risk recommendation.

    Attributes:
        document_id: External document identifier (e.g. ``"DOC-..."``).
        version: Document version string (e.g. ``"2.1"``).
        chunk_id: UUID of the knowledge chunk cited.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1, description="External document identifier")
    version: str = Field(..., min_length=1, description="Document version string")
    chunk_id: UUID = Field(..., description="Knowledge chunk UUID")


class RecommendedAction(BaseModel):
    """A single recommended action for mitigating a supply risk.

    The ``action_type`` is a free-form string at the wire-schema level
    because the set of valid action types may evolve across schema
    versions. The persistence path (03F) and approval flow (Phase 6)
    enforce action-type-specific constraints.

    ``requires_approval`` must be ``True`` for any action that would
    result in a controlled write (DEC-005).

    Attributes:
        action_type: Action type identifier (e.g.
            ``"CREATE_PROCUREMENT_TASK"``).
        title: Short human-readable action title.
        rationale: Explanation of why this action is recommended.
        requires_approval: Whether human approval is required before
            executing this action. Must be ``True`` for write actions.
    """

    model_config = ConfigDict(extra="forbid")

    action_type: str = Field(..., min_length=1, description="Action type identifier")
    title: str = Field(..., min_length=1, description="Short action title")
    rationale: str = Field(..., min_length=1, description="Action rationale")
    requires_approval: bool = Field(..., description="Whether human approval is required")


class RiskItem(BaseModel):
    """A single risk addressed by the AI recommendation.

    This item carries AI-generated explanations, business impact, and
    recommended actions for a risk that was already computed by the
    deterministic risk engine. It must **not** include fields that
    recalculate deterministic quantities (DEC-004, DEC-039/TD-4):
    shortage, available quantity, severity, and similar deterministic
    values are owned by the risk engine, not the AI.

    Attributes:
        risk_id: Risk identifier from the deterministic risk engine
            (e.g. ``"RISK-001"``).
        summary: AI-generated short summary of the risk.
        business_impact: AI-generated description of business impact.
        recommended_actions: List of recommended mitigation actions.
        sources: List of document source citations. Required field —
            may be empty (RAG integration is deferred to WP-REC-05),
            but empty sources must never be described or logged as
            grounded output.
    """

    model_config = ConfigDict(extra="forbid")

    risk_id: str = Field(..., min_length=1, description="Risk identifier from the risk engine")
    summary: str = Field(..., min_length=1, description="AI-generated risk summary")
    business_impact: str = Field(..., min_length=1, description="AI-generated business impact")
    recommended_actions: list[RecommendedAction] = Field(
        ...,
        description="Recommended mitigation actions",
    )
    sources: list[Source] = Field(
        ...,
        description="Document source citations. May be empty (RAG deferred); "
        "empty sources must never be described or logged as grounded.",
    )


class RecommendationData(BaseModel):
    """The top-level structured recommendation wire schema.

    This is the validated typed object returned by the schema validator
    on successful validation. It matches the structured recommendation
    schema in ``02_SYSTEM_BEHAVIOR_AND_DATA.md`` §6.

    The ``schema_version`` field must be exactly ``"1.0"``. Unsupported
    versions are rejected by the validator.

    The ``run_id`` field is the workflow run UUID. The ``plan_id`` field
    is the external plan identifier (e.g. ``"PLAN-2026-W31"``), not the
    database foreign key — the mapping to the ORM entity belongs to the
    persistence path (03F).

    Attributes:
        schema_version: Schema version, must be ``"1.0"``.
        run_id: Workflow run UUID.
        plan_id: External production plan identifier.
        risks: List of risk items with AI-generated recommendations.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = Field(
        ...,
        description="Recommendation schema version. Must be '1.0'.",
    )
    run_id: UUID = Field(..., description="Workflow run UUID")
    plan_id: str = Field(
        ...,
        min_length=1,
        description="External production plan identifier (e.g. 'PLAN-2026-W31')",
    )
    risks: list[RiskItem] = Field(
        ...,
        min_length=1,
        description="Risk items with AI-generated recommendations. "
        "Must contain at least one risk.",
    )
