"""Risk response schema for WP-2.9 API.

Defines the response shape for GET /api/v1/production-plans/{plan_code}/risks.

The response wraps a WP-2.8 ``RiskRecord`` and adds an ephemeral ``risk_id``
assigned per-response (RISK-001, RISK-002, ...). Risk IDs are regenerated on
every request, are not accepted as input, and are not persisted.

Decimal serialization:
    The five quantity fields (required, available, confirmed_early,
    confirmed_late, shortage) are serialized as JSON strings with exactly
    four decimal places (e.g. "20.0000", "0.0000"). Formatting is performed
    explicitly — never via float conversion.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer

# Decimal serialized as a JSON string with exactly 4 decimal places.
# ``f"{x:.4f}"`` is used instead of ``str(x)`` so that ``Decimal("20")``
# becomes "20.0000" rather than "20".
DecimalStr4 = Annotated[
    Decimal,
    PlainSerializer(lambda x: f"{x:.4f}", return_type=str),
]


class RiskRecordWithId(BaseModel):
    """A single supply risk with an ephemeral deterministic ID.

    The ``risk_id`` is assigned by position (1-indexed, zero-padded 3 digits)
    over the WP-2.8 deterministic sort (``component_code`` ASC,
    ``affected_wo_code`` ASC).
    """

    model_config = ConfigDict(from_attributes=False)

    risk_id: str
    component_code: str
    component_name: str
    affected_wo_code: str
    required: DecimalStr4
    available: DecimalStr4
    confirmed_early: DecimalStr4
    confirmed_late: DecimalStr4
    shortage: DecimalStr4
    severity: str
    has_approved_alternative: bool
    has_proposed_alternative: bool
    need_date: date
    plan_code: str


__all__ = ["DecimalStr4", "RiskRecordWithId"]
