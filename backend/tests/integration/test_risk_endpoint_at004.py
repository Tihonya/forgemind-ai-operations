"""AT-004 acceptance test: Golden Dataset exactly at the API boundary.

Proves that GET /api/v1/production-plans/PLAN-2026-W31/risks returns
exactly the 3 expected risk records with the exact values specified in
docs/planning/phase_2_business_model_spec.md §7–8.

AT-004 is the Phase 2 Golden Scenario end-to-end evidence: the entire
deterministic chain (BOM explosion → inventory availability → supply
calculation → severity rules → ordering → ID assignment → serialization)
is verified by exact comparison against the specification.
"""

# ruff: noqa: B008 - FastAPI Depends patterns.

from __future__ import annotations

from collections.abc import AsyncIterator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text

from app.config import settings
from app.main import app
from app.seed.generator.loader import (
    _delete_existing_auth_data,
    _delete_existing_business_data,
    _SessionFactory,
    load_golden_dataset,
)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

_INTEGRATION_DB_URL = settings.database_url

DEMO_PASSWORDS = {
    "manager.demo": "ManagerPass123!",
    "procurement.demo": "ProcurementPass123!",
    "engineer.demo": "EngineerPass123!",
    "admin.demo": "AdminPass123!",
    "auditor.demo": "AuditorPass123!",
}

PLAN_CODE = "PLAN-2026-W31"
ENDPOINT = f"/api/v1/production-plans/{PLAN_CODE}/risks"


def _can_connect() -> bool:
    try:
        sync_url = _INTEGRATION_DB_URL
        if "+asyncpg" in sync_url:
            sync_url = sync_url.replace("+asyncpg", "+psycopg")
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect(),
    reason="Integration database not available",
)


# ---------------------------------------------------------------------------
# Fixtures (mirror test_api_risks.py)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _seed_golden_dataset() -> Generator[None, None, None]:
    session = _SessionFactory()
    try:
        _delete_existing_auth_data(session)
        _delete_existing_business_data(session)
        session.commit()
    finally:
        session.close()

    load_golden_dataset()
    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _login(client: AsyncClient, username: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": DEMO_PASSWORDS[username]},
    )
    assert response.status_code == 200, (
        f"seed login failed: {response.status_code} {response.text}"
    )
    data: dict[str, object] = response.json()
    return str(data["access_token"])


# ---------------------------------------------------------------------------
# Golden Dataset reference values (per phase_2_business_model_spec.md §7–8)
# ---------------------------------------------------------------------------

EXPECTED_RISK_001 = {
    "risk_id": "RISK-001",
    "component_code": "CTRL-X4",
    "component_name": "Control Unit X4",
    "affected_wo_code": "WO-2026-0142",
    "required": "20.0000",
    "available": "12.0000",
    "confirmed_early": "0.0000",
    "confirmed_late": "0.0000",
    "shortage": "8.0000",
    "severity": "CRITICAL",
    "has_approved_alternative": False,
    "has_proposed_alternative": False,
    "need_date": "2026-08-03",
    "plan_code": "PLAN-2026-W31",
}

EXPECTED_RISK_002 = {
    "risk_id": "RISK-002",
    "component_code": "MOTOR-M2",
    "component_name": "Motor M2",
    "affected_wo_code": "WO-2026-0150",
    "required": "16.0000",
    "available": "10.0000",
    "confirmed_early": "0.0000",
    "confirmed_late": "10.0000",
    "shortage": "6.0000",
    "severity": "HIGH",
    "has_approved_alternative": False,
    "has_proposed_alternative": False,
    "need_date": "2026-08-03",
    "plan_code": "PLAN-2026-W31",
}

EXPECTED_RISK_003 = {
    "risk_id": "RISK-003",
    "component_code": "SENSOR-L9",
    "component_name": "Sensor L9",
    "affected_wo_code": "WO-2026-0156",
    "required": "12.0000",
    "available": "7.0000",
    "confirmed_early": "0.0000",
    "confirmed_late": "0.0000",
    "shortage": "5.0000",
    "severity": "MEDIUM",
    "has_approved_alternative": False,
    "has_proposed_alternative": True,
    "need_date": "2026-08-05",
    "plan_code": "PLAN-2026-W31",
}

ALL_EXPECTED = [EXPECTED_RISK_001, EXPECTED_RISK_002, EXPECTED_RISK_003]


# ---------------------------------------------------------------------------
# AT-004 Test
# ---------------------------------------------------------------------------


def _assert_field_exact(actual: dict[str, object], expected: dict[str, object], label: str) -> None:
    """Compare all Golden Dataset fields exactly.

    Raises AssertionError with a clear diff on any mismatch.
    """
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        assert actual_value == expected_value, (
            f"[{label}] field {key!r}: expected {expected_value!r}, "
            f"got {actual_value!r}"
        )
    extra_keys = set(actual.keys()) - set(expected.keys())
    assert not extra_keys, (
        f"[{label}] unexpected fields in response: {sorted(extra_keys)}"
    )


class TestAt004GoldenScenario:
    """AT-004 acceptance test: exact Golden Scenario end-to-end evidence."""

    async def test_at004_golden_dataset_exact_response(
        self, client: AsyncClient
    ) -> None:
        """AT-004: GET /risks for PLAN-2026-W31 matches spec exactly.

        Verifies for all 3 risks:
        - exact risk_id (RISK-001, RISK-002, RISK-003)
        - exact component_code, component_name, affected_wo_code
        - exact decimal strings for required/available/confirmed_early/
          confirmed_late/shortage (4 fractional digits)
        - exact severity (CRITICAL / HIGH / MEDIUM)
        - exact flags (has_approved_alternative, has_proposed_alternative)
        - exact need_date (ISO 8601 dates)
        - exact plan_code
        """
        token = await _login(client, "engineer.demo")
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, (
            f"AT-004 endpoint returned {response.status_code}: {response.text}"
        )

        records = response.json()
        assert isinstance(records, list), f"AT-004 expected list, got {type(records)}"
        assert len(records) == 3, (
            f"AT-004 expected exactly 3 risks, got {len(records)}"
        )

        # Per-risk exact comparisons (preserves positional ordering assertion)
        for idx, expected in enumerate(ALL_EXPECTED):
            actual = records[idx]
            _assert_field_exact(actual, expected, label=str(expected["risk_id"]))

    async def test_at004_no_extra_records(
        self, client: AsyncClient
    ) -> None:
        """AT-004 safety: response does not contain extra risks."""
        token = await _login(client, "admin.demo")
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert len(response.json()) == 3

    async def test_at004_severity_distribution(
        self, client: AsyncClient
    ) -> None:
        """AT-004 safety: each severity level in Golden Dataset appears exactly once."""
        token = await _login(client, "manager.demo")
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        severities = [r["severity"] for r in response.json()]
        assert severities == ["CRITICAL", "HIGH", "MEDIUM"]

    async def test_at004_need_dates_exact(
        self, client: AsyncClient
    ) -> None:
        """AT-004 safety: need_dates match spec (RISK-003 falls after RISK-001/002)."""
        token = await _login(client, "engineer.demo")
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        dates = [r["need_date"] for r in response.json()]
        assert dates == ["2026-08-03", "2026-08-03", "2026-08-05"]

    async def test_at004_alternative_flags(
        self, client: AsyncClient
    ) -> None:
        """AT-004 safety: only SENSOR-L9 has a PROPOSED alternative.

        This flag is what drives SENSOR-L9's severity to MEDIUM instead of CRITICAL.
        """
        token = await _login(client, "engineer.demo")
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        records = response.json()

        # RISK-001/002: no alternatives of any kind
        assert records[0]["has_approved_alternative"] is False
        assert records[0]["has_proposed_alternative"] is False
        assert records[1]["has_approved_alternative"] is False
        assert records[1]["has_proposed_alternative"] is False

        # RISK-003: proposed alternative exists (mitigates to MEDIUM)
        assert records[2]["has_approved_alternative"] is False
        assert records[2]["has_proposed_alternative"] is True
