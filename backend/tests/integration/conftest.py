"""Integration test fixtures.

These fixtures ensure clean state for tests against a live PostgreSQL database.
"""

from collections.abc import AsyncGenerator

import pytest

from app.database import engine as app_async_engine


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
