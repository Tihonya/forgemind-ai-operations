"""Integration test fixtures.

These fixtures ensure clean state for tests against a live PostgreSQL database.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import engine as app_async_engine

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)


@pytest.fixture(autouse=True)
async def reset_app_db_pool() -> AsyncGenerator[None, None]:
    """Prevent stale connection pool across test event loops.

    pytest-asyncio creates a new event loop per test. The module-level async
    engine's connection pool retains connections bound to the previous (closed)
    event loop, causing 'Event loop is closed' errors when the NEXT test's
    endpoint call attempts to reuse them.

    Disposing the pool before each test ensures a fresh pool on this loop.
    """
    await app_async_engine.dispose()
    yield
    await app_async_engine.dispose()


@pytest.fixture
async def acceptance_db_session() -> AsyncIterator[AsyncSession]:
    """Isolated async session for acceptance integration tests.

    Creates its own engine from TEST_DATABASE_URL or DATABASE_URL and
    cleans up workflow tables after each test.
    """
    assert _INTEGRATION_DB_URL is not None, (
        "DATABASE_URL or TEST_DATABASE_URL must be set"
    )
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    session_factory = async_sessionmaker[AsyncSession](
        bind=engine, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.execute(text("DELETE FROM recommendations"))
        await session.execute(text("DELETE FROM workflow_steps"))
        await session.execute(text("DELETE FROM workflow_runs"))
        await session.commit()
    await engine.dispose()


async def _get_seed_plan_id(session: AsyncSession) -> Any:
    """Return the first production_plan id or skip if none seeded."""
    result = await session.execute(
        text("SELECT id FROM production_plans LIMIT 1")
    )
    row = result.fetchone()
    if row is None:
        pytest.skip("No production plans in database — seed required")
    return row[0]
