"""Risk schema for supply risk intelligence.

Defines the output structure of the deterministic risk engine.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class RiskRecord(BaseModel):
    """Deterministic supply risk record.

    A risk record represents a material shortage for a specific component
    affecting a specific work order, with severity derived from deterministic rules.

    Attributes:
        component_code: Natural identifier of the component (e.g., CTRL-X4)
        component_name: Human-readable component name
        affected_wo_code: Work order code affected by this risk
        required: Total quantity required (WO.quantity * BOM.quantity_per_unit)
        available: Available inventory (on_hand - other active reservations)
        confirmed_early: Confirmed supply arriving before need_date
        confirmed_late: Confirmed supply arriving after need_date
        shortage: max(0, required - available - confirmed_early)
        severity: CRITICAL, HIGH, MEDIUM, or LOW based on precedence rules
        has_approved_alternative: Whether an APPROVED alternative exists
        has_proposed_alternative: Whether a PROPOSED alternative exists
        need_date: Date when the component is needed
        plan_code: Production plan code containing the affected work order
    """

    model_config = ConfigDict(from_attributes=True)

    component_code: str
    component_name: str
    affected_wo_code: str
    required: Decimal
    available: Decimal
    confirmed_early: Decimal
    confirmed_late: Decimal
    shortage: Decimal
    severity: str
    has_approved_alternative: bool
    has_proposed_alternative: bool
    need_date: date
    plan_code: str
