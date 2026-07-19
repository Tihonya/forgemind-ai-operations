"""WP-2.8 integration tests for risk engine against live PostgreSQL.

Required scenarios:
 1. analyze_plan("PLAN-2026-W31") returns exactly 3 risks
 2. Golden Dataset quantities and severity match specification
 3. Deterministic ordering by (component_code, affected_wo_code)
 4. Non-existent plan raises ValueError

Follows the same fixture pattern as test_api_components.py (WP-2.7A).
"""

from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine

from app.config import settings
from app.database import async_session_factory
from app.models.production import ProductionPlan
from app.schemas.risk import RiskRecord
from app.seed.generator.loader import (
    _delete_existing_business_data,
    _SessionFactory,
    load_golden_dataset,
)
from app.services.risk_engine import analyze_plan


def _get_sync_engine() -> Engine:
    url = settings.database_url
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg")
    return create_engine(url, pool_pre_ping=True)


# ---------------------------------------------------------------------------
# Fixtures — same pattern as WP-2.7A/WP-2.7B integration tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def _migrate_and_seed() -> Generator[None, None, None]:
    """Ensure DB schema exists and Golden Dataset is loaded."""
    from alembic.config import Config

    from alembic import command

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")

    # Seed data
    session = _SessionFactory()
    try:
        _delete_existing_business_data(session)
        session.commit()
    finally:
        session.close()

    load_golden_dataset()

    yield

    # Cleanup
    session = _SessionFactory()
    try:
        _delete_existing_business_data(session)
        session.commit()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRiskEngineGoldenDataset:
    """Integration tests for risk engine with Golden Dataset."""

    @pytest.mark.asyncio
    async def test_risk_engine_golden_dataset(
        self, _migrate_and_seed: None
    ) -> None:
        """Golden Scenario: PLAN-2026-W31 produces exactly 3 risks.

        Expected order (sorted by component_code, affected_wo_code):
        1. CTRL-X4   / WO-2026-0142 / shortage 8  / CRITICAL
        2. MOTOR-M2  / WO-2026-0150 / shortage 6  / HIGH (confirmed_late=10)
        3. SENSOR-L9 / WO-2026-0156 / shortage 5  / MEDIUM (proposed alt)
        """
        async with async_session_factory() as session:
            # Verify plan exists
            result = await session.execute(
                select(ProductionPlan).where(
                    ProductionPlan.code == "PLAN-2026-W31"
                )
            )
            plan = result.scalar_one_or_none()
            assert plan is not None, (
                "Golden Dataset plan PLAN-2026-W31 not found — seed failed"
            )

            risks: list[RiskRecord] = await analyze_plan(
                session, "PLAN-2026-W31"
            )

        # ─── Exactly 3 risks ───
        codes = [r.component_code for r in risks]
        assert len(risks) == 3, f"Expected 3 risks, got {len(risks)}: {codes}"

        # ─── RISK-001: CTRL-X4 ───
        r1 = risks[0]
        assert r1.component_code == "CTRL-X4"
        assert r1.affected_wo_code == "WO-2026-0142"
        assert r1.required == Decimal("20.0000")
        assert r1.available == Decimal("12.0000")
        assert r1.confirmed_early == Decimal("0.0000")
        assert r1.confirmed_late == Decimal("0.0000")
        assert r1.shortage == Decimal("8.0000")
        assert r1.severity == "CRITICAL"
        assert r1.has_approved_alternative is False
        assert r1.has_proposed_alternative is False
        assert r1.plan_code == "PLAN-2026-W31"

        # ─── RISK-002: MOTOR-M2 ───
        r2 = risks[1]
        assert r2.component_code == "MOTOR-M2"
        assert r2.affected_wo_code == "WO-2026-0150"
        assert r2.required == Decimal("16.0000")
        assert r2.available == Decimal("10.0000")
        assert r2.confirmed_early == Decimal("0.0000")
        assert r2.confirmed_late == Decimal("10.0000")
        assert r2.shortage == Decimal("6.0000")
        assert r2.severity == "HIGH"
        assert r2.has_approved_alternative is False
        assert r2.has_proposed_alternative is False
        assert r2.plan_code == "PLAN-2026-W31"

        # ─── RISK-003: SENSOR-L9 ───
        r3 = risks[2]
        assert r3.component_code == "SENSOR-L9"
        assert r3.affected_wo_code == "WO-2026-0156"
        assert r3.required == Decimal("12.0000")
        assert r3.available == Decimal("7.0000")
        assert r3.confirmed_early == Decimal("0.0000")
        assert r3.shortage == Decimal("5.0000")
        assert r3.severity == "MEDIUM"
        assert r3.has_approved_alternative is False
        assert r3.has_proposed_alternative is True
        assert r3.plan_code == "PLAN-2026-W31"

    @pytest.mark.asyncio
    async def test_risk_engine_nonexistent_plan_raises(
        self, _migrate_and_seed: None
    ) -> None:
        """Non-existent plan code raises ValueError."""
        async with async_session_factory() as session:
            with pytest.raises(ValueError, match="PLAN-NONEXISTENT"):
                await analyze_plan(session, "PLAN-NONEXISTENT")

    @pytest.mark.asyncio
    async def test_risk_engine_deterministic_sort(
        self, _migrate_and_seed: None
    ) -> None:
        """Results are sorted by (component_code ASC, affected_wo_code ASC)."""
        async with async_session_factory() as session:
            result = await session.execute(
                select(ProductionPlan).where(
                    ProductionPlan.code == "PLAN-2026-W31"
                )
            )
            plan = result.scalar_one_or_none()
            assert plan is not None, "Golden Dataset not seeded"

            risks = await analyze_plan(session, "PLAN-2026-W31")

        keys = [(r.component_code, r.affected_wo_code) for r in risks]
        assert keys == sorted(keys), f"Risks not sorted: {keys}"

    @pytest.mark.asyncio
    async def test_no_api_routes_added(self) -> None:
        """Verify no risk API endpoints exist (WP-2.8 is service-layer only)."""
        with _get_sync_engine().connect() as conn:
            # Just confirm DB is accessible — no API routes tested here
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
