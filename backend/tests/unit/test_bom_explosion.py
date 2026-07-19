"""Unit tests for BOM explosion service.

Tests cover:
- required quantity = wo.quantity * bom.quantity_per_unit
- Decimal precision (no float drift)
- ValueError on missing plan
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.bom_explosion import BomExplosionRow, explode_plan


@pytest.fixture
def sample_plan():
    """Create a sample plan with 2 WOs and 3 components each."""
    ctrl_x4 = SimpleNamespace(
        id=uuid.uuid4(), code="CTRL-X4", name="Control Unit X4"
    )
    valve_v3 = SimpleNamespace(
        id=uuid.uuid4(), code="VALVE-V3", name="Valve V3"
    )
    pipe_p1 = SimpleNamespace(id=uuid.uuid4(), code="PIPE-P1", name="Pipe P1")

    bom_2_1 = [
        SimpleNamespace(component=ctrl_x4, quantity_per_unit=Decimal("1.0000")),
        SimpleNamespace(component=valve_v3, quantity_per_unit=Decimal("2.0000")),
        SimpleNamespace(component=pipe_p1, quantity_per_unit=Decimal("3.0000")),
    ]
    bom_2_2 = [
        SimpleNamespace(component=ctrl_x4, quantity_per_unit=Decimal("4.0000")),
        SimpleNamespace(component=valve_v3, quantity_per_unit=Decimal("1.5000")),
        SimpleNamespace(component=pipe_p1, quantity_per_unit=Decimal("0.2500")),
    ]

    pv_2_1 = SimpleNamespace(bom_items=bom_2_1)
    pv_2_2 = SimpleNamespace(bom_items=bom_2_2)

    wo_142 = SimpleNamespace(
        id=uuid.uuid4(),
        code="WO-2026-0142",
        need_date=date(2026, 8, 3),
        quantity=Decimal("20.0000"),
        product_version=pv_2_1,
    )
    wo_150 = SimpleNamespace(
        id=uuid.uuid4(),
        code="WO-2026-0150",
        need_date=date(2026, 8, 3),
        quantity=Decimal("16.0000"),
        product_version=pv_2_2,
    )

    return SimpleNamespace(
        code="PLAN-2026-W31", production_orders=[wo_142, wo_150]
    )


@pytest.mark.asyncio
async def test_explode_plan_required_quantity(sample_plan):
    """required = wo.quantity * bom.quantity_per_unit."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_plan
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    rows = await explode_plan(session, "PLAN-2026-W31")

    # WO-2026-0142 (qty=20): CTRL-X4 20*1=20, VALVE-V3 20*2=40, PIPE-P1 20*3=60
    # WO-2026-0150 (qty=16): CTRL-X4 16*4=64, VALVE-V3 16*1.5=24, PIPE-P1 16*0.25=4
    assert len(rows) == 6

    wo_142_rows = [r for r in rows if r.wo_code == "WO-2026-0142"]
    wo_150_rows = [r for r in rows if r.wo_code == "WO-2026-0150"]
    assert len(wo_142_rows) == 3
    assert len(wo_150_rows) == 3

    ctrl_x4_142 = next(r for r in wo_142_rows if r.component_code == "CTRL-X4")
    assert ctrl_x4_142.required == Decimal("20.0000")

    valve_v3_142 = next(r for r in wo_142_rows if r.component_code == "VALVE-V3")
    assert valve_v3_142.required == Decimal("40.0000")

    pipe_p1_142 = next(r for r in wo_142_rows if r.component_code == "PIPE-P1")
    assert pipe_p1_142.required == Decimal("60.0000")

    ctrl_x4_150 = next(r for r in wo_150_rows if r.component_code == "CTRL-X4")
    assert ctrl_x4_150.required == Decimal("64.0000")

    valve_v3_150 = next(r for r in wo_150_rows if r.component_code == "VALVE-V3")
    assert valve_v3_150.required == Decimal("24.0000")

    pipe_p1_150 = next(r for r in wo_150_rows if r.component_code == "PIPE-P1")
    assert pipe_p1_150.required == Decimal("4.0000")


@pytest.mark.asyncio
async def test_explode_plan_decimal_precision():
    """Verify Decimal precision is preserved (no float drift)."""
    component = SimpleNamespace(
        id=uuid.uuid4(), code="COMP-A", name="Component A"
    )
    bom = [
        SimpleNamespace(component=component, quantity_per_unit=Decimal("0.0001")),
    ]
    pv = SimpleNamespace(bom_items=bom)
    wo = SimpleNamespace(
        id=uuid.uuid4(),
        code="WO-DEC",
        need_date=date(2026, 8, 1),
        quantity=Decimal("99999.9999"),
        product_version=pv,
    )
    plan = SimpleNamespace(code="PLAN-DEC", production_orders=[wo])

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = plan
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    rows = await explode_plan(session, "PLAN-DEC")
    assert len(rows) == 1

    # 99999.9999 * 0.0001 = 9.99999999 (exact Decimal, not float)
    expected = Decimal("99999.9999") * Decimal("0.0001")
    assert rows[0].required == expected
    assert isinstance(rows[0].required, Decimal)


@pytest.mark.asyncio
async def test_explode_plan_raises_on_missing_plan():
    """ValueError if the plan code does not exist."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(ValueError, match="PLAN-NONEXISTENT"):
        await explode_plan(session, "PLAN-NONEXISTENT")


@pytest.mark.asyncio
async def test_explode_plan_row_fields(sample_plan):
    """Verify all BomExplosionRow fields are populated correctly."""
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = sample_plan
    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    rows = await explode_plan(session, "PLAN-2026-W31")

    ctrl_x4_row = next(r for r in rows if r.component_code == "CTRL-X4")
    assert isinstance(ctrl_x4_row, BomExplosionRow)
    assert ctrl_x4_row.component_name == "Control Unit X4"
    assert ctrl_x4_row.plan_code == "PLAN-2026-W31"
    assert ctrl_x4_row.need_date == date(2026, 8, 3)
    assert isinstance(ctrl_x4_row.production_order_id, uuid.UUID)
    assert isinstance(ctrl_x4_row.component_id, uuid.UUID)
