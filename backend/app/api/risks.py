"""Production plan risks API router for WP-2.9.

Endpoint:
- GET /api/v1/production-plans/{plan_code}/risks

Returns deterministic risk records with ephemeral IDs (RISK-001, RISK-002, ...).

Authentication:
- Any authenticated user (no role restriction in Phase 2).
- Uses existing ``get_current_user`` dependency.
- Canonical 401 behavior from WP-2.6 preserved.

Error behavior:
- Unknown plan → HTTP 404 with detail: "Production plan '<code>' not found"
- Missing/invalid auth → canonical 401 from WP-2.6

Deterministic ordering:
- WP-2.8 sorts by (component_code ASC, affected_wo_code ASC).
- WP-2.9 assigns risk_id by position (1-indexed, RISK-001, RISK-002, ...).
- risk_id is per-response, not persisted, not accepted as input.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_async_session
from app.dependencies import get_current_user
from app.schemas.risk import RiskRecord
from app.schemas.risk_response import RiskRecordWithId
from app.services.auth_service import AuthenticatedUser
from app.services.risk_engine import analyze_plan

router = APIRouter(tags=["Risks"])


@router.get(
    "/production-plans/{plan_code}/risks",
    response_model=list[RiskRecordWithId],
    status_code=status.HTTP_200_OK,
)
async def get_production_plan_risks(
    plan_code: str,
    current_user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> list[RiskRecordWithId]:
    """Return supply risk records for a production plan.

    Args:
        plan_code: Natural code of the production plan (e.g. PLAN-2026-W31).
        current_user: Authenticated user (dependency-injected).
        session: Async database session (dependency-injected).

    Returns:
        List[RiskRecordWithId]: Ephemeral risk records with deterministic IDs.

    Raises:
        HTTPException(404): Production plan not found.
        HTTPException(401): Missing or invalid authentication (from dependency).
    """
    try:
        risks: list[RiskRecord] = await analyze_plan(session, plan_code)
    except ValueError as exc:
        # analyze_plan raises ValueError("Plan '<code>' not found")
        # Convert to canonical 404
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Production plan '{plan_code}' not found",
        ) from exc

    # Assign ephemeral risk IDs by position (1-indexed, zero-padded 3 digits)
    return [
        RiskRecordWithId(
            risk_id=f"RISK-{idx:03d}",
            component_code=r.component_code,
            component_name=r.component_name,
            affected_wo_code=r.affected_wo_code,
            required=r.required,
            available=r.available,
            confirmed_early=r.confirmed_early,
            confirmed_late=r.confirmed_late,
            shortage=r.shortage,
            severity=r.severity,
            has_approved_alternative=r.has_approved_alternative,
            has_proposed_alternative=r.has_proposed_alternative,
            need_date=r.need_date,
            plan_code=r.plan_code,
        )
        for idx, r in enumerate(risks, start=1)
    ]
