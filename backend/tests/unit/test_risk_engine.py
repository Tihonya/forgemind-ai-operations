"""Unit tests for risk engine severity rules and orchestration.

Tests the _determine_severity function (pure) and analyze_plan orchestration
using mocked sub-services.

Severity precedence (first-match-wins):
1. shortage <= 0 → no risk
2. PROPOSED → MEDIUM
3. confirmed_late > 0 → HIGH
4. no APPROVED → CRITICAL
5. APPROVED → LOW
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.risk import RiskRecord
from app.services.bom_explosion import BomExplosionRow
from app.services.inventory_service import InventoryAvailability
from app.services.risk_engine import _determine_severity, analyze_plan

# ──────────────────────────────────────────────────────────────
# _determine_severity — pure logic tests
# ──────────────────────────────────────────────────────────────


class TestDetermineSeverity:
    """Test the pure severity determination function."""

    def test_shortage_zero_no_risk(self) -> None:
        """shortage == 0 → None (no risk emitted)."""
        assert _determine_severity(
            shortage=Decimal("0"),
            has_approved_alternative=False,
            has_proposed_alternative=False,
            confirmed_late=Decimal("0"),
        ) is None

    def test_shortage_negative_no_risk(self) -> None:
        """shortage < 0 → None."""
        assert _determine_severity(
            shortage=Decimal("-5"),
            has_approved_alternative=False,
            has_proposed_alternative=False,
            confirmed_late=Decimal("0"),
        ) is None

    def test_proposed_alternative_gives_medium(self) -> None:
        """PROPOSED alternative + shortage > 0 → MEDIUM."""
        assert _determine_severity(
            shortage=Decimal("5"),
            has_approved_alternative=False,
            has_proposed_alternative=True,
            confirmed_late=Decimal("0"),
        ) == "MEDIUM"

    def test_proposed_beats_high(self) -> None:
        """PROPOSED beats HIGH — even if confirmed_late > 0, PROPOSED wins."""
        assert _determine_severity(
            shortage=Decimal("10"),
            has_approved_alternative=False,
            has_proposed_alternative=True,
            confirmed_late=Decimal("20"),
        ) == "MEDIUM"

    def test_proposed_beats_critical(self) -> None:
        """PROPOSED beats CRITICAL — even with no approved alternative."""
        assert _determine_severity(
            shortage=Decimal("10"),
            has_approved_alternative=False,
            has_proposed_alternative=True,
            confirmed_late=Decimal("0"),
        ) == "MEDIUM"

    def test_late_supply_gives_high(self) -> None:
        """confirmed_late > 0 + no PROPOSED → HIGH."""
        assert _determine_severity(
            shortage=Decimal("6"),
            has_approved_alternative=False,
            has_proposed_alternative=False,
            confirmed_late=Decimal("10"),
        ) == "HIGH"

    def test_high_beats_critical(self) -> None:
        """HIGH beats CRITICAL — even without approved alternative."""
        assert _determine_severity(
            shortage=Decimal("10"),
            has_approved_alternative=False,
            has_proposed_alternative=False,
            confirmed_late=Decimal("5"),
        ) == "HIGH"

    def test_no_approved_alternative_gives_critical(self) -> None:
        """No approved alternative + shortage > 0 + no late supply → CRITICAL."""
        assert _determine_severity(
            shortage=Decimal("8"),
            has_approved_alternative=False,
            has_proposed_alternative=False,
            confirmed_late=Decimal("0"),
        ) == "CRITICAL"

    def test_approved_alternative_gives_low(self) -> None:
        """APPROVED alternative + shortage > 0 + no late supply → LOW."""
        assert _determine_severity(
            shortage=Decimal("3"),
            has_approved_alternative=True,
            has_proposed_alternative=False,
            confirmed_late=Decimal("0"),
        ) == "LOW"

    def test_approved_does_not_override_high(self) -> None:
        """APPROVED with late supply — HIGH wins over LOW (precedence 3 > 5)."""
        assert _determine_severity(
            shortage=Decimal("5"),
            has_approved_alternative=True,
            has_proposed_alternative=False,
            confirmed_late=Decimal("10"),
        ) == "HIGH"

    def test_approved_does_not_override_medium(self) -> None:
        """PROPOSED wins over APPROVED (precedence 2 > 5)."""
        assert _determine_severity(
            shortage=Decimal("5"),
            has_approved_alternative=True,
            has_proposed_alternative=True,
            confirmed_late=Decimal("0"),
        ) == "MEDIUM"

    def test_rejected_alternative_has_no_effect(self) -> None:
        """Rejected alternative means has_approved=False, has_proposed=False → CRITICAL."""
        # A rejected alternative is not approved or proposed
        assert _determine_severity(
            shortage=Decimal("8"),
            has_approved_alternative=False,
            has_proposed_alternative=False,
            confirmed_late=Decimal("0"),
        ) == "CRITICAL"


# ──────────────────────────────────────────────────────────────
# analyze_plan orchestration tests
# ──────────────────────────────────────────────────────────────

def _make_row(
    wo_code: str,
    component_code: str,
    required: Decimal,
    need_date: date = date(2026, 8, 3),
) -> BomExplosionRow:
    return BomExplosionRow(
        production_order_id=uuid.uuid4(),
        wo_code=wo_code,
        need_date=need_date,
        component_id=uuid.uuid4(),
        component_code=component_code,
        component_name=f"Component {component_code}",
        required=required,
        plan_code="PLAN-2026-W31",
    )


def _make_availability(
    available: Decimal = Decimal("0"),
    confirmed_early: Decimal = Decimal("0"),
    confirmed_late: Decimal = Decimal("0"),
    has_approved: bool = False,
    has_proposed: bool = False,
) -> InventoryAvailability:
    return InventoryAvailability(
        component_id=uuid.uuid4(),
        available=available,
        confirmed_early=confirmed_early,
        confirmed_late=confirmed_late,
        has_approved_alternative=has_approved,
        has_proposed_alternative=has_proposed,
    )


@pytest.mark.asyncio
async def test_analyze_plan_no_risk_when_sufficient() -> None:
    """If shortage <= 0, no risk is emitted."""
    row = _make_row("WO-1", "COMP-A", Decimal("10"))
    avail = _make_availability(available=Decimal("20"))

    session = AsyncMock()
    with (
        patch(
            "app.services.risk_engine.explode_plan",
            new_callable=AsyncMock,
            return_value=[row],
        ),
        patch(
            "app.services.risk_engine.calculate_inventory_availability",
            new_callable=AsyncMock,
            return_value=avail,
        ),
    ):
        risks = await analyze_plan(session, "PLAN-2026-W31")
    assert risks == []


@pytest.mark.asyncio
async def test_analyze_plan_critical() -> None:
    """CRITICAL: shortage > 0, no alternative."""
    row = _make_row("WO-1", "COMP-A", Decimal("20"))
    avail = _make_availability(available=Decimal("12"))

    session = AsyncMock()
    with (
        patch(
            "app.services.risk_engine.explode_plan",
            new_callable=AsyncMock,
            return_value=[row],
        ),
        patch(
            "app.services.risk_engine.calculate_inventory_availability",
            new_callable=AsyncMock,
            return_value=avail,
        ),
    ):
        risks = await analyze_plan(session, "PLAN-2026-W31")

    assert len(risks) == 1
    assert risks[0].severity == "CRITICAL"
    assert risks[0].shortage == Decimal("8")
    assert risks[0].required == Decimal("20")
    assert risks[0].available == Decimal("12")


@pytest.mark.asyncio
async def test_analyze_plan_proposed_beats_high() -> None:
    """PROPOSED + late supply → MEDIUM (not HIGH)."""
    row = _make_row("WO-1", "COMP-A", Decimal("20"))
    avail = _make_availability(
        available=Decimal("10"),
        confirmed_late=Decimal("10"),
        has_proposed=True,
    )

    session = AsyncMock()
    with (
        patch(
            "app.services.risk_engine.explode_plan",
            new_callable=AsyncMock,
            return_value=[row],
        ),
        patch(
            "app.services.risk_engine.calculate_inventory_availability",
            new_callable=AsyncMock,
            return_value=avail,
        ),
    ):
        risks = await analyze_plan(session, "PLAN-2026-W31")

    assert len(risks) == 1
    assert risks[0].severity == "MEDIUM"


@pytest.mark.asyncio
async def test_analyze_plan_high() -> None:
    """HIGH: shortage > 0, confirmed_late > 0, no PROPOSED."""
    row = _make_row("WO-1", "COMP-A", Decimal("20"))
    avail = _make_availability(
        available=Decimal("10"),
        confirmed_late=Decimal("10"),
    )

    session = AsyncMock()
    with (
        patch(
            "app.services.risk_engine.explode_plan",
            new_callable=AsyncMock,
            return_value=[row],
        ),
        patch(
            "app.services.risk_engine.calculate_inventory_availability",
            new_callable=AsyncMock,
            return_value=avail,
        ),
    ):
        risks = await analyze_plan(session, "PLAN-2026-W31")

    assert len(risks) == 1
    assert risks[0].severity == "HIGH"


@pytest.mark.asyncio
async def test_analyze_plan_low() -> None:
    """LOW: shortage > 0, APPROVED alternative, no late supply, no PROPOSED."""
    row = _make_row("WO-1", "COMP-A", Decimal("20"))
    avail = _make_availability(
        available=Decimal("15"),
        has_approved=True,
    )

    session = AsyncMock()
    with (
        patch(
            "app.services.risk_engine.explode_plan",
            new_callable=AsyncMock,
            return_value=[row],
        ),
        patch(
            "app.services.risk_engine.calculate_inventory_availability",
            new_callable=AsyncMock,
            return_value=avail,
        ),
    ):
        risks = await analyze_plan(session, "PLAN-2026-W31")

    assert len(risks) == 1
    assert risks[0].severity == "LOW"
    assert risks[0].shortage == Decimal("5")
    assert risks[0].has_approved_alternative is True


@pytest.mark.asyncio
async def test_analyze_plan_deterministic_ordering() -> None:
    """Risks are sorted by (component_code ASC, affected_wo_code ASC)."""
    rows = [
        _make_row("WO-3", "ZETA", Decimal("10")),
        _make_row("WO-1", "ALPHA", Decimal("10")),
        _make_row("WO-2", "BETA", Decimal("10")),
        _make_row("WO-1", "ALPHA-2", Decimal("10")),
    ]
    # All have shortage → all CRITICAL
    avail = _make_availability(available=Decimal("0"))

    async def mock_availability(*args, **kwargs):
        return avail

    session = AsyncMock()
    with (
        patch(
            "app.services.risk_engine.explode_plan",
            new_callable=AsyncMock,
            return_value=rows,
        ),
        patch(
            "app.services.risk_engine.calculate_inventory_availability",
            new=mock_availability,
        ),
    ):
        risks = await analyze_plan(session, "PLAN-2026-W31")

    codes = [(r.component_code, r.affected_wo_code) for r in risks]
    assert codes == [
        ("ALPHA", "WO-1"),
        ("ALPHA-2", "WO-1"),
        ("BETA", "WO-2"),
        ("ZETA", "WO-3"),
    ]


@pytest.mark.asyncio
async def test_analyze_plan_early_supply_reduces_shortage() -> None:
    """confirmed_early reduces the shortage."""
    row = _make_row("WO-1", "COMP-A", Decimal("20"))
    avail = _make_availability(
        available=Decimal("5"),
        confirmed_early=Decimal("10"),
    )

    session = AsyncMock()
    with (
        patch(
            "app.services.risk_engine.explode_plan",
            new_callable=AsyncMock,
            return_value=[row],
        ),
        patch(
            "app.services.risk_engine.calculate_inventory_availability",
            new_callable=AsyncMock,
            return_value=avail,
        ),
    ):
        risks = await analyze_plan(session, "PLAN-2026-W31")

    assert len(risks) == 1
    # shortage = max(0, 20 - 5 - 10) = 5
    assert risks[0].shortage == Decimal("5")
    assert risks[0].confirmed_early == Decimal("10")


@pytest.mark.asyncio
async def test_analyze_plan_late_supply_does_not_reduce_shortage() -> None:
    """confirmed_late does NOT reduce the shortage."""
    row = _make_row("WO-1", "COMP-A", Decimal("20"))
    avail = _make_availability(
        available=Decimal("10"),
        confirmed_late=Decimal("10"),
    )

    session = AsyncMock()
    with (
        patch(
            "app.services.risk_engine.explode_plan",
            new_callable=AsyncMock,
            return_value=[row],
        ),
        patch(
            "app.services.risk_engine.calculate_inventory_availability",
            new_callable=AsyncMock,
            return_value=avail,
        ),
    ):
        risks = await analyze_plan(session, "PLAN-2026-W31")

    assert len(risks) == 1
    # shortage = max(0, 20 - 10 - 0) = 10 (confirmed_early is 0)
    assert risks[0].shortage == Decimal("10")
    assert risks[0].confirmed_late == Decimal("10")


@pytest.mark.asyncio
async def test_analyze_plan_decimal_precision() -> None:
    """Verify Decimal arithmetic precision is preserved."""
    row = _make_row("WO-1", "COMP-A", Decimal("99999.9999"))
    avail = _make_availability(
        available=Decimal("99999.9998"),
    )

    session = AsyncMock()
    with (
        patch(
            "app.services.risk_engine.explode_plan",
            new_callable=AsyncMock,
            return_value=[row],
        ),
        patch(
            "app.services.risk_engine.calculate_inventory_availability",
            new_callable=AsyncMock,
            return_value=avail,
        ),
    ):
        risks = await analyze_plan(session, "PLAN-2026-W31")

    assert len(risks) == 1
    assert risks[0].shortage == Decimal("0.0001")


@pytest.mark.asyncio
async def test_analyze_plan_risk_record_fields() -> None:
    """Verify all RiskRecord fields are populated correctly."""
    wo_id = uuid.uuid4()
    comp_id = uuid.uuid4()
    row = BomExplosionRow(
        production_order_id=wo_id,
        wo_code="WO-2026-0142",
        need_date=date(2026, 8, 3),
        component_id=comp_id,
        component_code="CTRL-X4",
        component_name="Control Unit X4",
        required=Decimal("20.0000"),
        plan_code="PLAN-2026-W31",
    )
    avail = InventoryAvailability(
        component_id=comp_id,
        available=Decimal("12.0000"),
        confirmed_early=Decimal("0.0000"),
        confirmed_late=Decimal("0.0000"),
        has_approved_alternative=False,
        has_proposed_alternative=False,
    )

    session = AsyncMock()
    with (
        patch(
            "app.services.risk_engine.explode_plan",
            new_callable=AsyncMock,
            return_value=[row],
        ),
        patch(
            "app.services.risk_engine.calculate_inventory_availability",
            new_callable=AsyncMock,
            return_value=avail,
        ),
    ):
        risks = await analyze_plan(session, "PLAN-2026-W31")

    assert len(risks) == 1
    risk = risks[0]
    assert isinstance(risk, RiskRecord)
    assert risk.component_code == "CTRL-X4"
    assert risk.component_name == "Control Unit X4"
    assert risk.affected_wo_code == "WO-2026-0142"
    assert risk.required == Decimal("20.0000")
    assert risk.available == Decimal("12.0000")
    assert risk.confirmed_early == Decimal("0.0000")
    assert risk.confirmed_late == Decimal("0.0000")
    assert risk.shortage == Decimal("8.0000")
    assert risk.severity == "CRITICAL"
    assert risk.has_approved_alternative is False
    assert risk.has_proposed_alternative is False
    assert risk.need_date == date(2026, 8, 3)
    assert risk.plan_code == "PLAN-2026-W31"
