"""WP-2.9 integration tests for GET /api/v1/production-plans/{plan_code}/risks.

Required scenarios:
 1.  Authenticated request returns 200
 2.  Response contains exactly 3 risks
 3.  Response schema matches RiskRecordWithId
 4.  Risk IDs are RISK-001, RISK-002, RISK-003
 5.  Ordering matches WP-2.8 ordering (component_code, affected_wo_code)
 6.  Decimal fields are JSON strings
 7.  Decimal strings have exactly four decimal places
 8.  Unknown plan returns exact 404 body
 9.  Missing authentication returns canonical 401
10.  Repeated requests return identical deterministic IDs/ordering
11.  No persistence side effect (call twice → same result)
"""

# ruff: noqa: B008 - FastAPI Depends patterns.

from __future__ import annotations

from collections.abc import AsyncIterator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

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


def _get_sync_engine() -> Engine:
    url = _INTEGRATION_DB_URL
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "+psycopg")
    return create_engine(url, echo=False, pool_pre_ping=True)


def _get_async_engine() -> AsyncEngine:
    async_url = _INTEGRATION_DB_URL
    if "+psycopg" in async_url:
        async_url = async_url.replace("+psycopg", "+asyncpg")
    return create_async_engine(async_url, echo=False, pool_pre_ping=True)


pytestmark = pytest.mark.skipif(
    not _can_connect(),
    reason="Integration database not available",
)


# ---------------------------------------------------------------------------
# Fixtures — same pattern as WP-2.7A/WP-2.7B/wp26 integration tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _seed_golden_dataset() -> Generator[None, None, None]:
    """Re-seed auth + business data before each test."""
    session = _SessionFactory()
    try:
        _delete_existing_auth_data(session)
        _delete_existing_business_data(session)
        session.commit()
    finally:
        session.close()

    load_golden_dataset()
    yield

    # No business-side cleanup needed: seed is deterministic & idempotent,
    # and the next test's autouse fixture re-cleans anyway.


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _login(client: AsyncClient, username: str, password: str) -> str:
    """Log in and return a bearer access token."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, (
        f"seed login failed: {response.status_code} {response.text}"
    )
    data = response.json()
    token: str = data["access_token"]
    return token


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAN_CODE = "PLAN-2026-W31"
ENDPOINT = f"/api/v1/production-plans/{PLAN_CODE}/risks"

EXPECTED_DECIMAL_FIELDS = (
    "required",
    "available",
    "confirmed_early",
    "confirmed_late",
    "shortage",
)

EXPECTED_SCHEMA_KEYS = {
    "risk_id",
    "component_code",
    "component_name",
    "affected_wo_code",
    "required",
    "available",
    "confirmed_early",
    "confirmed_late",
    "shortage",
    "severity",
    "has_approved_alternative",
    "has_proposed_alternative",
    "need_date",
    "plan_code",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestApiRisksEndpoint:
    """Canonical behaviour tests for GET /api/v1/production-plans/{code}/risks."""

    async def test_authenticated_request_returns_200(
        self, client: AsyncClient
    ) -> None:
        """Scenario 1: any authenticated user gets 200."""
        token = await _login(client, "engineer.demo", DEMO_PASSWORDS["engineer.demo"])
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

    async def test_response_contains_exactly_three_risks(
        self, client: AsyncClient
    ) -> None:
        """Scenario 2: Golden Dataset yields exactly 3 risks."""
        token = await _login(client, "admin.demo", DEMO_PASSWORDS["admin.demo"])
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3

    async def test_response_schema_matches_risk_record_with_id(
        self, client: AsyncClient
    ) -> None:
        """Scenario 3: every item has exactly the RiskRecordWithId fields."""
        token = await _login(client, "engineer.demo", DEMO_PASSWORDS["engineer.demo"])
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        records = response.json()
        for record in records:
            assert set(record.keys()) == EXPECTED_SCHEMA_KEYS

    async def test_risk_ids_are_risk_001_002_003(
        self, client: AsyncClient
    ) -> None:
        """Scenario 4: risk IDs are sequentially assigned RISK-001..RISK-003."""
        token = await _login(client, "manager.demo", DEMO_PASSWORDS["manager.demo"])
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        ids = [r["risk_id"] for r in response.json()]
        assert ids == ["RISK-001", "RISK-002", "RISK-003"]

    async def test_ordering_matches_wp28_sort(
        self, client: AsyncClient
    ) -> None:
        """Scenario 5: ordering = (component_code ASC, affected_wo_code ASC).

        Expected Golden Dataset order (WP-2.8):
          RISK-001 → CTRL-X4   / WO-2026-0142
          RISK-002 → MOTOR-M2  / WO-2026-0150
          RISK-003 → SENSOR-L9 / WO-2026-0156
        """
        token = await _login(client, "engineer.demo", DEMO_PASSWORDS["engineer.demo"])
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        records = response.json()
        keys = [(r["component_code"], r["affected_wo_code"]) for r in records]
        assert keys == sorted(keys)
        assert keys == [
            ("CTRL-X4", "WO-2026-0142"),
            ("MOTOR-M2", "WO-2026-0150"),
            ("SENSOR-L9", "WO-2026-0156"),
        ]

    async def test_decimal_fields_are_json_strings(
        self, client: AsyncClient
    ) -> None:
        """Scenario 6: the five quantity fields are encoded as JSON strings."""
        token = await _login(client, "engineer.demo", DEMO_PASSWORDS["engineer.demo"])
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        for record in response.json():
            for field in EXPECTED_DECIMAL_FIELDS:
                assert isinstance(record[field], str), (
                    f"{field}={record[field]!r} is not a JSON string"
                )

    async def test_decimal_strings_have_four_decimal_places(
        self, client: AsyncClient
    ) -> None:
        """Scenario 7: every decimal string has exactly four decimal places."""
        token = await _login(client, "engineer.demo", DEMO_PASSWORDS["engineer.demo"])
        response = await client.get(
            ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
        )
        for record in response.json():
            for field in EXPECTED_DECIMAL_FIELDS:
                value = record[field]
                assert "." in value, f"{field}={value!r} missing decimal point"
                _, fractional = value.split(".")
                assert len(fractional) == 4, (
                    f"{field}={value!r} has {len(fractional)} fractional digits, "
                    f"expected 4"
                )

    async def test_unknown_plan_returns_exact_404(
        self, client: AsyncClient
    ) -> None:
        """Scenario 8: unknown plan → 404 with canonical detail string."""
        token = await _login(client, "engineer.demo", DEMO_PASSWORDS["engineer.demo"])
        response = await client.get(
            "/api/v1/production-plans/PLAN-DOES-NOT-EXIST/risks",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        assert response.json() == {
            "detail": "Production plan 'PLAN-DOES-NOT-EXIST' not found"
        }

    async def test_missing_authentication_returns_canonical_401(
        self, client: AsyncClient
    ) -> None:
        """Scenario 9: no bearer token → canonical 401 from WP-2.6."""
        response = await client.get(ENDPOINT)
        assert response.status_code == 401
        body = response.json()
        assert body["detail"]["error"] == "missing_authentication"

    async def test_repeated_requests_return_same_ids_and_ordering(
        self, client: AsyncClient
    ) -> None:
        """Scenario 10: calling twice yields identical IDs and ordering."""
        token = await _login(client, "engineer.demo", DEMO_PASSWORDS["engineer.demo"])
        headers = {"Authorization": f"Bearer {token}"}

        first = await client.get(ENDPOINT, headers=headers)
        second = await client.get(ENDPOINT, headers=headers)

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json() == second.json()

    async def test_no_persistence_side_effect(
        self, client: AsyncClient
    ) -> None:
        """Scenario 11: endpoint does not mutate DB state.

        Call twice — results are identical (risk_id is per-response only).
        """
        token = await _login(client, "engineer.demo", DEMO_PASSWORDS["engineer.demo"])
        headers = {"Authorization": f"Bearer {token}"}

        first = (await client.get(ENDPOINT, headers=headers)).json()
        second = (await client.get(ENDPOINT, headers=headers)).json()
        third = (await client.get(ENDPOINT, headers=headers)).json()

        assert first == second == third

    async def test_endpoint_is_read_only(
        self, client: AsyncClient
    ) -> None:
        """Sanity: POST/PUT/PATCH/DELETE on this path are not served (405 or 404)."""
        token = await _login(client, "engineer.demo", DEMO_PASSWORDS["engineer.demo"])
        headers = {"Authorization": f"Bearer {token}"}

        # Methods that accept a JSON body
        for method in ("post", "put", "patch"):
            response = await getattr(client, method)(ENDPOINT, headers=headers, json={})
            assert response.status_code in (404, 405), (
                f"{method.upper()} unexpectedly returned {response.status_code}"
            )

        # DELETE has no body
        response = await client.delete(ENDPOINT, headers=headers)
        assert response.status_code in (404, 405), (
            f"DELETE unexpectedly returned {response.status_code}"
        )
