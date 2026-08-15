"""Integration tests for the WP-REC-04C ``procurement_tasks`` migration.

Verifies against a live PostgreSQL database:

- ``alembic upgrade head`` creates the table, columns, CHECK constraints,
  foreign keys, unique constraint, and indexes matching the ORM.
- Downgrade to the parent revision drops the table cleanly.
- Re-upgrade restores it.
- Exactly one Alembic head exists (no branch / multiple-head state).

Skips cleanly if the database is unavailable. No provider call occurs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text

_INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

PROCUREMENT_REVISION = "d00f71c78f67"
PARENT_REVISION = "3e619e551708"

_EXPECTED_COLUMNS = {
    "id",
    "correlation_id",
    "approval_request_id",
    "recommendation_id",
    "workflow_run_id",
    "risk_id",
    "action_type",
    "component_code",
    "quantity",
    "binding_hash",
    "task_state",
    "requested_by",
    "requested_by_username",
    "approved_by",
    "approved_by_username",
    "created_at",
}

_EXPECTED_CHECK_CONSTRAINTS = {
    "ck_procurement_tasks_action_type",
    "ck_procurement_tasks_task_state",
    "ck_procurement_tasks_quantity_positive",
}

_EXPECTED_FOREIGN_KEYS = {
    "procurement_tasks_approval_request_id_fkey",
    "procurement_tasks_recommendation_id_fkey",
    "procurement_tasks_workflow_run_id_fkey",
    "procurement_tasks_requested_by_fkey",
    "procurement_tasks_approved_by_fkey",
}

_EXPECTED_INDEXES = {
    "idx_procurement_tasks_correlation_id",
    "idx_procurement_tasks_recommendation_id",
    "idx_procurement_tasks_workflow_run_id",
    "idx_procurement_tasks_risk_id",
    "idx_procurement_tasks_requested_by",
    "idx_procurement_tasks_approved_by",
    "idx_procurement_tasks_created_at",
    "uq_procurement_tasks_approval_request_id",
}


def _can_connect() -> bool:
    if not _INTEGRATION_DB_URL:
        return False
    try:
        sync_url = _INTEGRATION_DB_URL
        if "+asyncpg" in sync_url:
            sync_url = sync_url.replace("+asyncpg", "+psycopg")
        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect(),
    reason="Integration database not available",
)


def _get_sync_engine() -> Engine:
    assert _INTEGRATION_DB_URL is not None
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")
    return create_engine(sync_url, echo=False, pool_pre_ping=True)


def _alembic_config() -> Any:
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent.parent.parent
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    return config


def _run_alembic(action: str, revision: str) -> None:
    """Run ``alembic upgrade`` or ``alembic downgrade`` to ``revision``."""
    from alembic import command
    from app.config import settings

    assert _INTEGRATION_DB_URL is not None
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")

    config = _alembic_config()
    original_db_url = settings.database_url
    settings.database_url = original_db_url.replace("%", "%%")
    try:
        config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))
        if action == "upgrade":
            command.upgrade(config, revision)
        else:
            command.downgrade(config, revision)
    finally:
        settings.database_url = original_db_url


def _query(engine: Engine, sql: str) -> set[str]:
    with engine.connect() as conn:
        return {row[0] for row in conn.execute(text(sql))}


def _table_names(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        }


class TestProcurementMigration:
    def test_single_alembic_head(self) -> None:
        from alembic.script import ScriptDirectory

        script = ScriptDirectory.from_config(_alembic_config())
        heads = script.get_heads()
        assert heads == [PROCUREMENT_REVISION]

    def test_upgrade_creates_schema(self) -> None:
        _run_alembic("upgrade", "head")
        engine = _get_sync_engine()
        try:
            assert "procurement_tasks" in _table_names(engine)

            columns = _query(
                engine,
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'procurement_tasks'",
            )
            assert columns == _EXPECTED_COLUMNS

            check_constraints = _query(
                engine,
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'procurement_tasks'::regclass AND contype = 'c'",
            )
            assert check_constraints == _EXPECTED_CHECK_CONSTRAINTS

            foreign_keys = _query(
                engine,
                "SELECT conname FROM pg_constraint "
                "WHERE conrelid = 'procurement_tasks'::regclass AND contype = 'f'",
            )
            assert foreign_keys == _EXPECTED_FOREIGN_KEYS

            indexes = _query(
                engine,
                "SELECT indexname FROM pg_indexes WHERE tablename = 'procurement_tasks'",
            )
            assert indexes >= _EXPECTED_INDEXES
        finally:
            engine.dispose()

    def test_downgrade_drops_table_and_reupgrade_restores(self) -> None:
        _run_alembic("upgrade", "head")

        _run_alembic("downgrade", PARENT_REVISION)
        engine = _get_sync_engine()
        try:
            assert "procurement_tasks" not in _table_names(engine)
        finally:
            engine.dispose()

        _run_alembic("upgrade", "head")
        engine = _get_sync_engine()
        try:
            assert "procurement_tasks" in _table_names(engine)
        finally:
            engine.dispose()
