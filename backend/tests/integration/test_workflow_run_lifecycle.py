"""Integration tests for workflow run lifecycle (WP-REC-03B).

Tests run against a live PostgreSQL database using the repository's
integration-test database path. Coverage:

- Lifecycle persistence: create → run → documented 03B terminal boundary
- Failed-provider run persistence
- Failed-internal run persistence
- Run and step reload from a new session
- Correlation ID continuity
- Recommendation ORM model existence without persistence path
- Migration upgrade/downgrade verification (table creation/removal)
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import TransientChatProviderError
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.state_machine import WorkflowState
from app.models.workflow import Recommendation, WorkflowRun, WorkflowStep

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

_ALEMBIC_INI = (
    Path := __import__("pathlib").Path  # noqa: E731
)(__file__).resolve().parent.parent.parent / "alembic.ini"


def _get_sync_url() -> str:
    url = _INTEGRATION_DB_URL
    if url is None:
        raise RuntimeError(
            "DATABASE_URL or TEST_DATABASE_URL must be set"
        )
    return url.replace("+asyncpg", "+psycopg")


def _run_alembic(command_name: str, target: str) -> None:
    """Run an alembic command with the sync URL.

    The alembic env.py module reads ``settings.database_url`` at import
    time and calls ``config.set_main_option``, which uses configparser
    interpolation. A URL-encoded password containing ``%`` triggers
    ``ValueError: invalid interpolation syntax``. We work around this
    by temporarily patching ``settings.database_url`` to the
    ``%%``-escaped form so configparser correctly interprets ``%%`` as
    a literal ``%``.

    This is a pre-existing environment limitation affecting all alembic
    downgrade tests with URL-encoded passwords containing ``%``.
    """
    from alembic.config import Config

    from alembic import command
    from app.config import settings  # noqa: I001

    sync_url = _get_sync_url()
    sync_engine = create_engine(sync_url, echo=False)
    alembic_cfg = Config(str(_ALEMBIC_INI))

    # Temporarily escape database_url for configparser
    original_db_url = settings.database_url
    settings.database_url = original_db_url.replace("%", "%%")

    try:
        with sync_engine.begin() as conn:
            alembic_cfg.attributes["connection"] = conn
            getattr(command, command_name)(alembic_cfg, target)
    finally:
        settings.database_url = original_db_url

    sync_engine.dispose()


# ---------------------------------------------------------------------------
# Skip if no database URL
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeProvider(ChatProvider):
    """Fake provider with configurable result/exception."""

    def __init__(
        self,
        *,
        result: ChatResult | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._result = result
        self._exc = exc

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        if self._exc is not None:
            raise self._exc
        if self._result is None:
            return ChatResult(
                content="{}",
                model="fake-model",
                finish_reason="stop",
            )
        return self._result


def _make_chat_result(**kwargs: Any) -> ChatResult:
    defaults: dict[str, Any] = {
        "content": '{"test": true}',
        "model": "fake-model",
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "metadata": {"latency_ms": 42.0, "provider": "fake"},
    }
    defaults.update(kwargs)
    return ChatResult(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Async session against the live integration database.

    Workflow data is cleaned up after each test to prevent contamination.
    """
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    session_factory = async_sessionmaker[AsyncSession](
        bind=engine, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        # Clean up workflow data created by this test
        await session.execute(text("DELETE FROM recommendations"))
        await session.execute(text("DELETE FROM workflow_steps"))
        await session.execute(text("DELETE FROM workflow_runs"))
        await session.commit()
    await engine.dispose()


@pytest.fixture
async def plan_id(db_session: AsyncSession) -> Any:
    """Get a real production plan ID from the database."""
    result = await db_session.execute(
        text("SELECT id FROM production_plans LIMIT 1")
    )
    row = result.fetchone()
    if row is None:
        pytest.skip("No production plans in database")
    return row[0]


# ---------------------------------------------------------------------------
# Migration tests
# ---------------------------------------------------------------------------


class TestWorkflowMigrationUpgrade:
    """Tests run after 'alembic upgrade head' (migration already applied)."""

    async def test_workflow_runs_table_exists(self, db_session) -> None:
        result = await db_session.execute(
            text(
                "SELECT EXISTS (SELECT FROM information_schema.tables "
                "WHERE table_name = 'workflow_runs')"
            )
        )
        assert result.scalar() is True

    async def test_workflow_steps_table_exists(self, db_session) -> None:
        result = await db_session.execute(
            text(
                "SELECT EXISTS (SELECT FROM information_schema.tables "
                "WHERE table_name = 'workflow_steps')"
            )
        )
        assert result.scalar() is True

    async def test_recommendations_table_exists(self, db_session) -> None:
        result = await db_session.execute(
            text(
                "SELECT EXISTS (SELECT FROM information_schema.tables "
                "WHERE table_name = 'recommendations')"
            )
        )
        assert result.scalar() is True

    async def test_workflow_runs_state_check_constraint(self, db_session) -> None:
        result = await db_session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conname = 'ck_workflow_runs_state'"
            )
        )
        assert result.fetchone() is not None

    async def test_workflow_steps_status_check_constraint(
        self, db_session
    ) -> None:
        result = await db_session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conname = 'ck_workflow_steps_status'"
            )
        )
        assert result.fetchone() is not None

    async def test_recommendations_status_check_constraint(
        self, db_session
    ) -> None:
        result = await db_session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conname = 'ck_recommendations_status'"
            )
        )
        assert result.fetchone() is not None

    async def test_recommendations_run_id_unique_constraint(
        self, db_session
    ) -> None:
        result = await db_session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE conname = 'uq_recommendations_run_id'"
            )
        )
        assert result.fetchone() is not None

    async def test_workflow_runs_correlation_id_index(self, db_session) -> None:
        result = await db_session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'workflow_runs' "
                "AND indexname = 'idx_workflow_runs_correlation_id'"
            )
        )
        assert result.fetchone() is not None

    async def test_workflow_steps_run_id_seq_index(self, db_session) -> None:
        result = await db_session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'workflow_steps' "
                "AND indexname = 'idx_workflow_steps_run_id_seq'"
            )
        )
        assert result.fetchone() is not None

    async def test_workflow_runs_plan_id_fk(self, db_session) -> None:
        result = await db_session.execute(
            text(
                "SELECT ccu.table_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.constraint_column_usage ccu "
                "ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.table_name = 'workflow_runs' "
                "AND tc.constraint_type = 'FOREIGN KEY'"
            )
        )
        fk_tables = [r[0] for r in result]
        assert "production_plans" in fk_tables

    async def test_workflow_steps_run_id_fk_cascade(self, db_session) -> None:
        result = await db_session.execute(
            text(
                "SELECT confdeltype FROM pg_constraint "
                "WHERE conrelid = 'workflow_steps'::regclass "
                "AND contype = 'f' "
                "AND confrelid = 'workflow_runs'::regclass"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == b"c"  # CASCADE


class TestWorkflowMigrationDowngrade:
    """Tests for migration downgrade and re-upgrade."""

    def test_downgrade_removes_workflow_tables(self) -> None:
        _run_alembic("downgrade", "625c9f549f2b")

        sync_url = _get_sync_url()
        engine = create_engine(sync_url, echo=False)
        with engine.connect() as conn:
            for table in ("workflow_runs", "workflow_steps", "recommendations"):
                result = conn.execute(
                    text(
                        "SELECT EXISTS (SELECT FROM information_schema.tables "
                        "WHERE table_name = :table_name)"
                    ),
                    {"table_name": table},
                )
                assert result.scalar() is False, f"{table} should not exist"
        engine.dispose()

        # Re-upgrade for subsequent tests
        _run_alembic("upgrade", "head")

    def test_re_upgrade_restores_workflow_tables(self) -> None:
        _run_alembic("downgrade", "625c9f549f2b")
        _run_alembic("upgrade", "head")

        sync_url = _get_sync_url()
        engine = create_engine(sync_url, echo=False)
        with engine.connect() as conn:
            for table in ("workflow_runs", "workflow_steps", "recommendations"):
                result = conn.execute(
                    text(
                        "SELECT EXISTS (SELECT FROM information_schema.tables "
                        "WHERE table_name = :table_name)"
                    ),
                    {"table_name": table},
                )
                assert result.scalar() is True, f"{table} should exist"
        engine.dispose()


# ---------------------------------------------------------------------------
# Lifecycle persistence
# ---------------------------------------------------------------------------


class TestWorkflowRunLifecycle:
    """Full lifecycle: create → run → documented 03B terminal boundary."""

    async def test_successful_run_reaches_awaiting_validation(
        self, db_session, plan_id
    ) -> None:
        provider = _FakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        assert run.state == WorkflowState.PENDING.value

        result = await engine.execute_provider_call(run, prompt="test prompt")
        await db_session.commit()

        assert result is not None
        assert run.state == WorkflowState.AWAITING_VALIDATION.value
        assert run.started_at is not None
        assert run.completed_at is None  # Not COMPLETED in 03B

    async def test_failed_provider_run_persisted(
        self, db_session, plan_id
    ) -> None:
        provider = _FakeProvider(
            exc=TransientChatProviderError("connection refused")
        )
        engine = WorkflowEngine(provider=provider, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        result = await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        assert result is None
        assert run.state == WorkflowState.FAILED_PROVIDER.value
        assert run.completed_at is not None
        assert run.error_code == "PROVIDER_TRANSIENT"

    async def test_failed_internal_run_persisted(
        self, db_session, plan_id
    ) -> None:
        provider = _FakeProvider(
            exc=RuntimeError("unexpected internal error")
        )
        engine = WorkflowEngine(provider=provider, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        result = await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        assert result is None
        assert run.state == WorkflowState.FAILED_INTERNAL.value
        assert run.completed_at is not None
        assert run.error_code == "INTERNAL_ERROR"


class TestRunAndStepReload:
    """Run and step reload from a new session."""

    async def test_run_reloaded_from_new_session(
        self, db_session, plan_id
    ) -> None:
        provider = _FakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)

        run = await engine.create_run(
            plan_id=plan_id,
            correlation_id=uuid4(),
            triggered_by="manager.demo",
        )
        await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()
        run_id = run.id
        corr_id = run.correlation_id

        # New session
        assert _INTEGRATION_DB_URL is not None
        engine2 = create_async_engine(_INTEGRATION_DB_URL, echo=False)
        factory2 = async_sessionmaker[AsyncSession](
            bind=engine2, expire_on_commit=False
        )
        async with factory2() as session2:
            reloaded = await session2.get(WorkflowRun, run_id)
            assert reloaded is not None
            assert reloaded.state == WorkflowState.AWAITING_VALIDATION.value
            assert reloaded.correlation_id == corr_id
            assert reloaded.triggered_by == "manager.demo"
            assert reloaded.plan_id == plan_id
        await engine2.dispose()

    async def test_step_reloaded_from_new_session(
        self, db_session, plan_id
    ) -> None:
        provider = _FakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()
        run_id = run.id

        # New session
        assert _INTEGRATION_DB_URL is not None
        engine2 = create_async_engine(_INTEGRATION_DB_URL, echo=False)
        factory2 = async_sessionmaker[AsyncSession](
            bind=engine2, expire_on_commit=False
        )
        async with factory2() as session2:
            result = await session2.execute(
                select(WorkflowStep).where(WorkflowStep.run_id == run_id)
            )
            steps = result.scalars().all()
            assert len(steps) == 1
            step = steps[0]
            assert step.step_name == "provider_call"
            assert step.status == "completed"
            assert step.model_name == "fake-model"
        await engine2.dispose()


class TestCorrelationIdContinuity:
    """Correlation ID continuity across run and steps."""

    async def test_correlation_id_same_in_run_and_step(
        self, db_session, plan_id
    ) -> None:
        provider = _FakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)

        corr = uuid4()
        run = await engine.create_run(
            plan_id=plan_id,
            correlation_id=corr,
        )
        await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        result = await db_session.execute(
            select(WorkflowStep).where(WorkflowStep.run_id == run.id)
        )
        step = result.scalar_one()
        assert step.correlation_id == corr
        assert run.correlation_id == corr


class TestRecommendationModelExistence:
    """Recommendation ORM model exists but no persistence path in 03B."""

    async def test_recommendation_table_exists_but_empty(
        self, db_session, plan_id
    ) -> None:
        """Recommendation table exists but 03B does not write to it."""
        result = await db_session.execute(select(Recommendation))
        recommendations = result.scalars().all()
        # 03B does not persist recommendations
        assert len(recommendations) == 0

    async def test_recommendation_can_be_manually_inserted(
        self, db_session, plan_id
    ) -> None:
        """The ORM model is functional — a row can be inserted manually.

        This verifies the model is correctly mapped. The validated
        persistence path (writing from validated provider output) is
        owned by WP-REC-03F and is NOT tested here.
        """
        provider = _FakeProvider(result=_make_chat_result())
        engine = WorkflowEngine(provider=provider, session=db_session)

        run = await engine.create_run(plan_id=plan_id)
        await engine.execute_provider_call(run, prompt="test")
        await db_session.commit()

        # Manually insert a recommendation (simulating what 03F would do)
        rec = Recommendation(
            run_id=run.id,
            plan_id=plan_id,
            status="VALIDATED",
            content={"schema_version": "1.0", "test": True},
            schema_version="1.0",
        )
        db_session.add(rec)
        await db_session.commit()

        # Verify it can be read back
        reloaded = await db_session.get(Recommendation, rec.id)
        assert reloaded is not None
        assert reloaded.status == "VALIDATED"
        assert reloaded.run_id == run.id

        # Clean up
        await db_session.delete(reloaded)
        await db_session.commit()
