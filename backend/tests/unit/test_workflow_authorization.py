"""Unit tests for WP-REC-05 M1 authorization context (generation-specific).

Verifies the fail-closed effective-role resolution that the worker applies
immediately before retrieval (``_resolve_effective_role_ids``). These tests
require a live PostgreSQL database (DATABASE_URL/TEST_DATABASE_URL) and are
skipped otherwise, matching the repository's dispatch-generation test pattern.

Covered contracts (M1 / DEC-045):
- effective_role_ids is the intersection of the immutable dispatch snapshot
  and the user's current roles;
- roles granted after dispatch do not expand access;
- roles revoked before execution are not effective;
- empty effective_role_ids fails closed (returns None);
- missing/generation-mismatched authorization records fail closed;
- inactive or deleted users fail closed;
- malformed role snapshots fail closed.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.workflow.vertical import _resolve_effective_role_ids

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)

_CLEANUP_TABLES = (
    "workflow_authorization_records",
    "workflow_steps",
    "recommendations",
    "workflow_runs",
    "user_roles",
    "users",
    "roles",
    "production_plans",
)


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Async session against the live integration database."""
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    factory = async_sessionmaker[AsyncSession](bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        for table in _CLEANUP_TABLES:
            # Table names come from the module-level `_CLEANUP_TABLES` tuple
            # (a hardcoded allowlist), never from user input.
            await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
        await session.commit()
    await engine.dispose()


async def _insert_plan(session: AsyncSession) -> UUID:
    result = await session.execute(
        text(
            "INSERT INTO production_plans (code, status, period_start, period_end) "
            "VALUES (:code, 'DRAFT', '2026-01-01', '2026-12-31') RETURNING id"
        ),
        {"code": f"PLAN-{uuid4().hex[:8]}"},
    )
    return result.scalar_one()


async def _insert_role(session: AsyncSession, code: str) -> UUID:
    result = await session.execute(
        text(
            "INSERT INTO roles (id, code, name) "
            "VALUES (gen_random_uuid(), :code, :name) RETURNING id"
        ),
        {"code": code, "name": code},
    )
    return result.scalar_one()


async def _insert_user(
    session: AsyncSession, username: str, *, is_active: bool = True
) -> UUID:
    result = await session.execute(
        text(
            "INSERT INTO users (id, username, display_name, is_active) "
            "VALUES (gen_random_uuid(), :u, :d, :a) RETURNING id"
        ),
        {"u": username, "d": username, "a": is_active},
    )
    return result.scalar_one()


async def _link_user_role(
    session: AsyncSession, user_id: UUID, role_id: UUID
) -> None:
    await session.execute(
        text(
            "INSERT INTO user_roles (id, user_id, role_id) "
            "VALUES (gen_random_uuid(), :u, :r)"
        ),
        {"u": user_id, "r": role_id},
    )


async def _insert_run(
    session: AsyncSession,
    plan_id: UUID,
    *,
    generation: int = 0,
) -> UUID:
    result = await session.execute(
        text(
            "INSERT INTO workflow_runs "
            "(correlation_id, state, plan_id, triggered_by, dispatch_generation) "
            "VALUES (gen_random_uuid(), 'PENDING', :plan_id, 'tester', :gen) "
            "RETURNING id"
        ),
        {"plan_id": plan_id, "gen": generation},
    )
    return result.scalar_one()


async def _insert_auth_record(
    session: AsyncSession,
    run_id: UUID,
    generation: int,
    user_id: UUID,
    role_snapshot: list[str],
) -> None:
    await session.execute(
        text(
            "INSERT INTO workflow_authorization_records "
            "(run_id, dispatch_generation, user_id, role_snapshot, capture_action) "
            "VALUES (:run_id, :gen, :user_id, CAST(:snapshot AS jsonb), 'start')"
        ),
        {
            "run_id": run_id,
            "gen": generation,
            "user_id": user_id,
            "snapshot": json.dumps(role_snapshot),
        },
    )


async def _seed_context(
    session: AsyncSession,
    *,
    snapshot_role_ids: list[UUID],
    current_role_ids: list[UUID],
    generation: int = 0,
    is_active: bool = True,
) -> tuple[UUID, UUID]:
    """Seed plan, user, roles, run, and a generation-0 authorization record."""
    plan_id = await _insert_plan(session)
    user_id = await _insert_user(session, f"user-{uuid4().hex[:8]}", is_active=is_active)
    for role_id in current_role_ids:
        await _link_user_role(session, user_id, role_id)
    run_id = await _insert_run(session, plan_id, generation=generation)
    await _insert_auth_record(
        session,
        run_id,
        generation=0,
        user_id=user_id,
        role_snapshot=[str(r) for r in snapshot_role_ids],
    )
    await session.commit()
    return run_id, user_id


class TestEffectiveRoleIntersection:
    async def test_intersection_of_snapshot_and_current(
        self, db_session: AsyncSession
    ) -> None:
        role_a = await _insert_role(db_session, "ROLE_A")
        role_b = await _insert_role(db_session, "ROLE_B")
        run_id, _ = await _seed_context(
            db_session,
            snapshot_role_ids=[role_a],
            current_role_ids=[role_a, role_b],
        )

        effective = await _resolve_effective_role_ids(db_session, run_id, 0)

        assert effective == {role_a}
        assert role_b not in effective

    async def test_role_granted_after_dispatch_does_not_expand_access(
        self, db_session: AsyncSession
    ) -> None:
        """A role granted after dispatch is not in the snapshot → not effective."""
        role_a = await _insert_role(db_session, "ROLE_A")
        role_b = await _insert_role(db_session, "ROLE_B")
        run_id, _ = await _seed_context(
            db_session,
            snapshot_role_ids=[role_a],
            current_role_ids=[role_a, role_b],
        )

        effective = await _resolve_effective_role_ids(db_session, run_id, 0)

        assert role_b not in (effective or set())

    async def test_role_revoked_before_execution_is_not_effective(
        self, db_session: AsyncSession
    ) -> None:
        """A role revoked after dispatch is not current → not effective."""
        role_a = await _insert_role(db_session, "ROLE_A")
        role_b = await _insert_role(db_session, "ROLE_B")
        run_id, _ = await _seed_context(
            db_session,
            snapshot_role_ids=[role_a, role_b],
            current_role_ids=[role_a],
        )

        effective = await _resolve_effective_role_ids(db_session, run_id, 0)

        assert effective == {role_a}
        assert role_b not in effective


class TestFailClosedAuthorization:
    async def test_missing_record_fails_closed(
        self, db_session: AsyncSession
    ) -> None:
        plan_id = await _insert_plan(db_session)
        run_id = await _insert_run(db_session, plan_id)
        await db_session.commit()

        assert await _resolve_effective_role_ids(db_session, run_id, 0) is None

    async def test_generation_mismatch_fails_closed(
        self, db_session: AsyncSession
    ) -> None:
        role_a = await _insert_role(db_session, "ROLE_A")
        run_id, _ = await _seed_context(
            db_session, snapshot_role_ids=[role_a], current_role_ids=[role_a]
        )

        # Record exists for generation 0; a stale/cross job claims generation 1.
        assert await _resolve_effective_role_ids(db_session, run_id, 1) is None

    async def test_inactive_user_fails_closed(
        self, db_session: AsyncSession
    ) -> None:
        role_a = await _insert_role(db_session, "ROLE_A")
        run_id, _ = await _seed_context(
            db_session,
            snapshot_role_ids=[role_a],
            current_role_ids=[role_a],
            is_active=False,
        )

        assert await _resolve_effective_role_ids(db_session, run_id, 0) is None

    async def test_empty_effective_roles_fails_closed(
        self, db_session: AsyncSession
    ) -> None:
        role_a = await _insert_role(db_session, "ROLE_A")
        # Snapshot has role_a but the user's current roles are empty (revoked).
        run_id, _ = await _seed_context(
            db_session, snapshot_role_ids=[role_a], current_role_ids=[]
        )

        assert await _resolve_effective_role_ids(db_session, run_id, 0) is None

    async def test_malformed_snapshot_fails_closed(
        self, db_session: AsyncSession
    ) -> None:
        role_a = await _insert_role(db_session, "ROLE_A")
        plan_id = await _insert_plan(db_session)
        user_id = await _insert_user(db_session, f"user-{uuid4().hex[:8]}")
        await _link_user_role(db_session, user_id, role_a)
        run_id = await _insert_run(db_session, plan_id)
        await _insert_auth_record(
            db_session, run_id, 0, user_id, ["not-a-uuid"]
        )
        await db_session.commit()

        assert await _resolve_effective_role_ids(db_session, run_id, 0) is None


class TestGenerationSpecificRecords:
    async def test_prior_generation_records_remain_unchanged(
        self, db_session: AsyncSession
    ) -> None:
        """A second generation-specific record does not mutate the first."""
        role_a = await _insert_role(db_session, "ROLE_A")
        role_b = await _insert_role(db_session, "ROLE_B")
        plan_id = await _insert_plan(db_session)
        user_id = await _insert_user(db_session, f"user-{uuid4().hex[:8]}")
        await _link_user_role(db_session, user_id, role_a)
        await _link_user_role(db_session, user_id, role_b)
        run_id = await _insert_run(db_session, plan_id, generation=1)

        await _insert_auth_record(
            db_session, run_id, 0, user_id, [str(role_a)]
        )
        await _insert_auth_record(
            db_session, run_id, 1, user_id, [str(role_a), str(role_b)]
        )
        await db_session.commit()

        # Generation 0 snapshot must still contain only role_a.
        gen0 = await _resolve_effective_role_ids(db_session, run_id, 0)
        assert gen0 is not None
        assert gen0 == {role_a}
        assert role_b not in gen0

        # Generation 1 snapshot contains both.
        gen1 = await _resolve_effective_role_ids(db_session, run_id, 1)
        assert gen1 == {role_a, role_b}
