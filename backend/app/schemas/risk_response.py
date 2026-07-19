"""Risk response schema for WP-2.9 API.

Defines the response shape for GET /api/v1/production-plans/{plan_code}/risks.

The response wraps a WP-2.8 ``RiskRecord`` and adds an ephemeral ``risk_id``
assigned per-response (RISK-001, RISK-002, ...). Risk IDs are regenerated on
every request, are not accepted as input, and are not persisted.

Decimal serialization contract (WP-2.9):
    The five quantity fields (required, available, confirmed_early,
    confirmed_late, shortage) are serialized as JSON strings with exactly
    four decimal places (e.g. "20.0000", "0.0000").

    Formatting is performed with the Decimal-native ``format(value, ".4f")``
    builtin — NEVER via binary floating-point conversion (no ``float(d)``
    at any stage). ``Decimal("12345678901234567890.1234")`` serializes to
    ``"12345678901234567890.1234"`` without precision loss.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, PlainSerializer


def format_decimal_4(value: Decimal) -> str:
    """Format a ``Decimal`` as a JSON string with exactly 4 fractional digits.

    Uses the Decimal-native ``format(value, ".4f")`` — no ``float()`` call,
    no binary floating-point path. Preserves full precision for arbitrarily
    large ``Decimal`` values.

    Args:
        value: The Decimal to format.

    Returns:
        A string like ``"20.0000"`` or ``"0.1234"``.
    """
    # ``format(Decimal, ".4f")`` is Decimal-native (CPython uses Decimal.__format__
    # directly). It does NOT go through binary float. The output is guaranteed
    # to have exactly four fractional digits, with no rounding beyond the
    # specified precision.
    return format(value, ".4f")


# Decimal serialized as a JSON string with exactly 4 decimal places.
# ``format_decimal_4`` is used instead of ``str(x)`` so that ``Decimal("20")``
# becomes "20.0000" rather than "20". Critically, the implementation never
# passes the Decimal through ``float()`` — precision is preserved for
# arbitrarily large values.
DecimalStr4 = Annotated[
    Decimal,
    PlainSerializer(format_decimal_4, return_type=str),
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
