"""Risk engine service.

Orchestrates BOM explosion, inventory availability, and supply calculations
to produce deterministic risk records for a production plan.

All arithmetic uses Decimal. Severity is derived deterministically from
shortage and supply evidence by ordered precedence.

Output is sorted by (component_code ASC, affected_wo_code ASC).
"""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.risk import RiskRecord
from app.services.bom_explosion import BomExplosionRow, explode_plan
from app.services.inventory_service import calculate_inventory_availability


async def analyze_plan(
    session: AsyncSession,
    plan_code: str,
) -> list[RiskRecord]:
    """Analyse a production plan and return all supply risks.

    Entry point for the deterministic risk engine.

    Args:
        session: Async database session.
        plan_code: Natural code of the production plan to analyse (e.g. PLAN-2026-W31).

    Returns:
        List of RiskRecord instances sorted by (component_code, affected_wo_code).
        May be empty if no component has a shortage.

    Raises:
        ValueError: If the plan does not exist.
    """
    # Step 1: Explode BOM for all WOs in the plan
    explosion_rows: Sequence[BomExplosionRow] = await explode_plan(session, plan_code)

    risks: list[RiskRecord] = []

    for row in explosion_rows:
        # Step 2: Calculate inventory availability for this (component, WO, need_date)
        availability = await calculate_inventory_availability(
            session=session,
            component_id=row.component_id,
            need_date=row.need_date,
            exclude_wo_id=row.production_order_id,
        )

        # Step 3: Calculate shortage
        shortage = max(
            Decimal("0"),
            row.required - availability.available - availability.confirmed_early,
        )

        # Step 4: Determine severity by ordered precedence
        severity = _determine_severity(
            shortage=shortage,
            has_approved_alternative=availability.has_approved_alternative,
            has_proposed_alternative=availability.has_proposed_alternative,
            confirmed_late=availability.confirmed_late,
        )

        # Step 5: Skip if no risk
        if severity is None:
            continue

        # Step 6: Build risk record
        risks.append(
            RiskRecord(
                component_code=row.component_code,
                component_name=row.component_name,
                affected_wo_code=row.wo_code,
                required=row.required,
                available=availability.available,
                confirmed_early=availability.confirmed_early,
                confirmed_late=availability.confirmed_late,
                shortage=shortage,
                severity=severity,
                has_approved_alternative=availability.has_approved_alternative,
                has_proposed_alternative=availability.has_proposed_alternative,
                need_date=row.need_date,
                plan_code=row.plan_code,
            )
        )

    # Step 7: Deterministic sort
    risks.sort(key=lambda r: (r.component_code, r.affected_wo_code))

    return risks


def _determine_severity(
    *,
    shortage: Decimal,
    has_approved_alternative: bool,
    has_proposed_alternative: bool,
    confirmed_late: Decimal,
) -> str | None:
    """Determine risk severity by ordered precedence.

    Precedence (first match wins):
        1. shortage <= 0 → None (no risk)
        2. shortage > 0 AND has_proposed_alternative → MEDIUM
        3. shortage > 0 AND confirmed_late > 0 → HIGH
        4. shortage > 0 AND NOT has_approved_alternative → CRITICAL
        5. shortage > 0 AND has_approved_alternative → LOW

    Args:
        shortage: Required minus available minus confirmed early (non-negative).
        has_approved_alternative: Whether an APPROVED alternative exists.
        has_proposed_alternative: Whether a PROPOSED alternative exists.
        confirmed_late: Confirmed supply arriving after need_date.

    Returns:
        Severity string ("CRITICAL", "HIGH", "MEDIUM", "LOW") or None if no risk.
    """
    # Rule 1: No shortage → no risk emitted
    if shortage <= 0:
        return None

    # Rule 2: Proposed alternative exists → MEDIUM
    if has_proposed_alternative:
        return "MEDIUM"

    # Rule 3: Confirmed late supply exists → HIGH
    if confirmed_late > 0:
        return "HIGH"

    # Rule 4: No approved alternative → CRITICAL
    if not has_approved_alternative:
        return "CRITICAL"

    # Rule 5: Approved alternative exists → LOW
    return "LOW"
