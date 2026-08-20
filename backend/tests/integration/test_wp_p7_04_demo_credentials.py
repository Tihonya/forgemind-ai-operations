"""WP-P7-04 credential contract tests.

Purpose (task §16 and §18):
  - prove the repository-owned plaintext demo credentials authenticate
    exactly their canonical seeded demo users through the real auth API;
  - reconcile the frontend-owned public demo-account catalogue (single module
    imported at test time) with this canonical contract so any drift between
    displayed credentials and authenticated identities fails CI;
  - assert the two non-public identities (admin.demo, engineer.demo) are
    absent from the public UX catalogue.

Offline-only: exercises seeded bcrypt verification and JWT issuance against
a local test database. No provider calls, no network access.

Naming: test_api_* per repository integration-test convention.
Note: plaintext demo credentials are reproduced only as references to the
repository-owned canonical demo contract; this is the established convention
of every existing backend integration module (test_api_risks.py,
test_api_approval.py, ...). The credentials authenticate only the synthetic
disposable Demo identities created by DEC-028/DEC-056.
"""
# ruff: noqa: B008 - FastAPI Depends patterns.

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Generator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.seed.generator.auth_dataset import DEMO_USERS

_INTEGRATION_DB_URL = settings.database_url

# Bounded plaintext contract mirroring the canonical repo-owned demo
# credential convention (values already live in backend integration tests and
# frontend acceptance specs). Never extend with non-Demo identities.
PUBLIC_DEMO_CREDENTIALS: dict[str, str] = {
    "manager.demo": "ManagerPass123!",
    "procurement.demo": "ProcurementPass123!",
    "auditor.demo": "AuditorPass123!",
}

PUBLIC_ROLE_EXPECTATIONS: dict[str, str] = {
    "manager.demo": "PRODUCTION_MANAGER",
    "procurement.demo": "PROCUREMENT_SPECIALIST",
    "auditor.demo": "AUDITOR",
}

USERNAME_PATTERN = re.compile(r"^[a-z0-9.-]+$")


def _can_connect() -> bool:
    if not _INTEGRATION_DB_URL:
        return False
    try:
        from sqlalchemy import create_engine, text

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


@pytest.fixture(scope="module")
def _seeded_golden_dataset() -> Generator[None, None, None]:
    """Migrate to head and seed the canonical Golden Dataset for this module."""
    from alembic.config import Config

    from alembic import command as alembic_command
    from app.seed.generator.loader import _find_alembic_ini, load_golden_dataset

    alembic_command.upgrade(Config(str(_find_alembic_ini())), "head")
    load_golden_dataset()
    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _frontend_public_demo_entries() -> tuple[frozenset[str], dict[str, str]]:
    """Parse the frontend-owned demo-accounts module (source-level, no build)."""
    frontend_module = (
        Path(__file__).resolve().parents[3] / "frontend" / "src" / "config" / "demo-accounts.ts"
    )
    source = frontend_module.read_text(encoding="utf-8")

    usernames: set[str] = set()
    password_map: dict[str, str] = {}

    block_pattern = re.compile(r"username:\s*'([^']+)',.*?password:\s*'([^']+)'", re.DOTALL)
    for match in block_pattern.finditer(source):
        username = match.group(1)
        password = match.group(2)
        if not USERNAME_PATTERN.match(username):
            continue
        usernames.add(username)
        password_map[username] = password

    return frozenset(usernames), password_map


def test_seed_owns_all_five_demo_identities() -> None:
    """Canonical seed dataset defines exactly the five DEC-028 demo users."""
    seeded = {str(user["username"]) for user in DEMO_USERS}
    assert seeded == {
        "manager.demo",
        "procurement.demo",
        "engineer.demo",
        "admin.demo",
        "auditor.demo",
    }


def test_public_credentials_cover_only_the_three_public_identities() -> None:
    """Bounded suitability boundary: the public credential set is exactly
    manager/procurement/auditor. admin.demo / engineer.demo excluded."""
    assert set(PUBLIC_DEMO_CREDENTIALS) == {
        "manager.demo",
        "procurement.demo",
        "auditor.demo",
    }
    assert "admin.demo" not in PUBLIC_DEMO_CREDENTIALS
    assert "engineer.demo" not in PUBLIC_DEMO_CREDENTIALS


def test_frontend_catalogue_matches_repository_owned_credential_contract() -> None:
    """Drift guard (section 15/16): the three public identities rendered by
    the login page source exactly match this module's canonical contract."""
    usernames, password_map = _frontend_public_demo_entries()
    assert usernames == frozenset(PUBLIC_DEMO_CREDENTIALS)
    for username, expected in PUBLIC_DEMO_CREDENTIALS.items():
        assert password_map.get(username) == expected
    assert "admin.demo" not in usernames
    assert "engineer.demo" not in usernames


@pytest.mark.parametrize("username", ["manager.demo", "procurement.demo", "auditor.demo"])
async def test_public_demo_credential_authenticates_canonical_user(
    client: AsyncClient,
    _seeded_golden_dataset: None,
    username: str,
) -> None:
    """A: plaintext credential authenticates the intended seeded demo user
    through the real login endpoint and receives role claims."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PUBLIC_DEMO_CREDENTIALS[username]},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert isinstance(token, str) and token

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == username


@pytest.mark.parametrize("username", ["manager.demo", "procurement.demo", "auditor.demo"])
async def test_public_demo_identity_carries_expected_canonical_role(
    client: AsyncClient,
    _seeded_golden_dataset: None,
    username: str,
) -> None:
    """Section 18: role mapping must remain exactly as DEC-028 defines."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": PUBLIC_DEMO_CREDENTIALS[username]},
    )
    token = response.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    roles = me.json()["roles"]
    assert PUBLIC_ROLE_EXPECTATIONS[username] in roles


NON_PUBLIC_IDENTITIES = ("admin.demo", "engineer.demo")

_WRONG_IDENTITY_CASES: tuple[tuple[str, str], ...] = tuple(
    (credential_owner, target)
    for credential_owner in PUBLIC_DEMO_CREDENTIALS
    for target in (*PUBLIC_DEMO_CREDENTIALS, *NON_PUBLIC_IDENTITIES)
    if target != credential_owner
)


@pytest.mark.parametrize(
    ("credential_owner", "target_username"),
    _WRONG_IDENTITY_CASES,
)
async def test_public_demo_password_authenticates_no_other_identity(
    client: AsyncClient,
    _seeded_golden_dataset: None,
    credential_owner: str,
    target_username: str,
) -> None:
    """B: each public credential authenticates ONLY its intended Demo user.

    Complete 3-source x 4-target negative matrix (12 combinations):
      manager credential    -> procurement / auditor / engineer / admin
      procurement credential -> manager / auditor / engineer / admin
      auditor credential    -> manager / procurement / engineer / admin
    """
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "username": target_username,
            "password": PUBLIC_DEMO_CREDENTIALS[credential_owner],
        },
    )
    assert response.status_code == 401


@pytest.mark.parametrize("username", list(NON_PUBLIC_IDENTITIES))
async def test_non_public_identity_absent_from_public_contract_and_credentials(
    client: AsyncClient,
    _seeded_golden_dataset: None,
    username: str,
) -> None:
    """C/D/E (sections 5, 10, 17): admin.demo / engineer.demo have no entry in
    the public credential catalogue and the Demo role mapping set is exactly
    the three approved identities."""
    assert username not in PUBLIC_DEMO_CREDENTIALS
    # Demonstrate admin.demo exists in seed but is NOT presented publicly.
    assert username in {str(user["username"]) for user in DEMO_USERS}
    # The frontend source must never list it.
    usernames, _ = _frontend_public_demo_entries()
    assert username not in usernames
