"""Narrowly-scoped shared test helpers for WP-REC-05 F1/F2 remediation.

Provides the minimum shared surface the affected integration tests need to
satisfy the WP-REC-05 M1 authorization contract at the ``execute_workflow``
boundary without duplicating seed/cleanup logic across files:

- ``RecordingEmbeddingProvider`` — deterministic fake embedding provider that
  records every ``embed_text`` call (F2 evidence).
- ``seed_production_plan`` — insert a minimal production plan (so risk
  analysis has a plan to read and the vertical tests execute rather than
  skip).
- ``insert_role`` / ``insert_user`` / ``link_user_role`` /
  ``insert_auth_record`` — building blocks for a real, active user + role +
  generation-specific ``WorkflowAuthorizationRecord``.
- ``seed_authorization_context`` — convenience wrapper for the common
  non-empty single-role authorization context.
- ``WORKFLOW_CLEANUP_TABLES`` + ``cleanup_workflow_tables`` — FK-safe teardown
  for the tables these tests touch.

All inserts use server-generated UUIDs (``gen_random_uuid()``) with unique
suffixes so they are self-contained and never collide with seeded data.
"""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.embedding_provider import FakeEmbeddingProvider


class RecordingEmbeddingProvider(FakeEmbeddingProvider):
    """FakeEmbeddingProvider that records every ``embed_text`` call."""

    def __init__(self, dimension: int = 1536) -> None:
        super().__init__(dimension=dimension)
        self.calls: list[list[str]] = []

    async def embed_text(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return await super().embed_text(texts)


# FK-safe teardown order (children before parents).
WORKFLOW_CLEANUP_TABLES: tuple[str, ...] = (
    "recommendations",
    "workflow_steps",
    "workflow_authorization_records",
    "workflow_runs",
    "user_roles",
    "users",
    "roles",
    "production_plans",
)


async def cleanup_workflow_tables(session: AsyncSession) -> None:
    """Delete all rows touched by the WP-REC-05 F1/F2 tests (FK-safe order)."""
    for table in WORKFLOW_CLEANUP_TABLES:
        # Table names come from the module-level WORKFLOW_CLEANUP_TABLES tuple
        # (a hardcoded allowlist), never from user input.
        await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    await session.commit()


async def seed_production_plan(
    session: AsyncSession, *, code: str | None = None
) -> UUID:
    """Insert a minimal production plan and return its UUID."""
    plan_code = code or f"PLAN-TEST-{uuid4().hex[:8]}"
    result = await session.execute(
        text(
            "INSERT INTO production_plans (code, status, period_start, period_end) "
            "VALUES (:code, 'DRAFT', '2026-01-01', '2026-12-31') RETURNING id"
        ),
        {"code": plan_code},
    )
    return cast(UUID, result.scalar_one())


async def insert_role(session: AsyncSession, code: str) -> UUID:
    """Insert a role row and return its UUID."""
    result = await session.execute(
        text(
            "INSERT INTO roles (id, code, name) "
            "VALUES (gen_random_uuid(), :code, :name) RETURNING id"
        ),
        {"code": code, "name": code},
    )
    return cast(UUID, result.scalar_one())


async def insert_user(
    session: AsyncSession, username: str, *, is_active: bool = True
) -> UUID:
    """Insert a user row and return its UUID."""
    result = await session.execute(
        text(
            "INSERT INTO users (id, username, display_name, is_active) "
            "VALUES (gen_random_uuid(), :u, :d, :a) RETURNING id"
        ),
        {"u": username, "d": username, "a": is_active},
    )
    return cast(UUID, result.scalar_one())


async def link_user_role(
    session: AsyncSession, user_id: UUID, role_id: UUID
) -> None:
    """Link a user to a role via the user_roles join table."""
    await session.execute(
        text(
            "INSERT INTO user_roles (id, user_id, role_id) "
            "VALUES (gen_random_uuid(), :u, :r)"
        ),
        {"u": user_id, "r": role_id},
    )


async def insert_auth_record(
    session: AsyncSession,
    *,
    run_id: UUID,
    dispatch_generation: int,
    user_id: UUID,
    role_snapshot: list[UUID] | list[str],
    capture_action: str = "start",
) -> None:
    """Insert a generation-specific WorkflowAuthorizationRecord."""
    snapshot = [str(r) for r in role_snapshot]
    await session.execute(
        text(
            "INSERT INTO workflow_authorization_records "
            "(run_id, dispatch_generation, user_id, role_snapshot, capture_action) "
            "VALUES (:run_id, :gen, :user_id, CAST(:snapshot AS jsonb), :action)"
        ),
        {
            "run_id": run_id,
            "gen": dispatch_generation,
            "user_id": user_id,
            "snapshot": json.dumps(snapshot),
            "action": capture_action,
        },
    )


async def seed_authorization_context(
    session: AsyncSession,
    *,
    run_id: UUID,
    dispatch_generation: int,
    capture_action: str = "start",
    is_active: bool = True,
) -> tuple[UUID, UUID]:
    """Seed a real active user + role + generation-specific auth record.

    The user's single role is the snapshot role, so the effective role set
    resolves to exactly that role UUID at execution time.

    Returns ``(user_id, role_id)``.
    """
    suffix = uuid4().hex[:8]
    role_id = await insert_role(session, f"ROLE-{suffix}")
    user_id = await insert_user(
        session, f"user-{suffix}", is_active=is_active
    )
    await link_user_role(session, user_id, role_id)
    await insert_auth_record(
        session,
        run_id=run_id,
        dispatch_generation=dispatch_generation,
        user_id=user_id,
        role_snapshot=[role_id],
        capture_action=capture_action,
    )
    return user_id, role_id
