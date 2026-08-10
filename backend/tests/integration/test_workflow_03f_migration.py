"""Integration tests for WP-REC-03F migration (D5/D6).

Tests cover:
- dispatch_generation column exists with server_default=0.
- pending_since column exists and is nullable.
- Non-negative CHECK constraint on dispatch_generation.
- Partial PENDING index exists.
- Migration upgrade adds columns and index.
- Migration downgrade removes columns and index.
- Existing rows receive generation 0.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

_ALEMBIC_INI = (
    Path(__file__).resolve().parent.parent.parent / "alembic.ini"
)


def _get_sync_url() -> str:
    url = _INTEGRATION_DB_URL
    if url is None:
        raise RuntimeError(
            "DATABASE_URL or TEST_DATABASE_URL must be set"
        )
    return url.replace("+asyncpg", "+psycopg")


def _run_alembic(command_name: str, target: str) -> None:
    """Run an alembic command with the sync URL."""
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(_ALEMBIC_INI))
    sync_url = _get_sync_url()
    # Escape % for configparser.
    cfg.set_main_option(
        "sqlalchemy.url",
        sync_url.replace("%", "%%"),
    )
    if command_name == "upgrade":
        command.upgrade(cfg, target)
    elif command_name == "downgrade":
        command.downgrade(cfg, target)


pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)


@pytest.fixture
def sync_engine() -> Any:
    """Sync engine for migration verification."""
    engine = create_engine(_get_sync_url())
    yield engine
    engine.dispose()


class TestMigrationUpgrade:
    """Verify the D5/D6 migration upgrade."""

    def test_dispatch_generation_column_exists(self, sync_engine: Any) -> None:
        with sync_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = 'workflow_runs' "
                "AND column_name = 'dispatch_generation'"
            ))
            row = result.fetchone()
            assert row is not None
            assert row[1] == "integer"
            assert row[2] == "NO"  # non-null
            assert "0" in (row[3] or "")  # server_default=0

    def test_pending_since_column_exists(self, sync_engine: Any) -> None:
        with sync_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'workflow_runs' "
                "AND column_name = 'pending_since'"
            ))
            row = result.fetchone()
            assert row is not None
            assert row[1] == "timestamp with time zone"
            assert row[2] == "YES"  # nullable

    def test_dispatch_generation_nonneg_check_constraint(
        self, sync_engine: Any
    ) -> None:
        with sync_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT conname, pg_get_constraintdef(oid) "
                "FROM pg_constraint "
                "WHERE conrelid = 'workflow_runs'::regclass "
                "AND conname = 'ck_workflow_runs_dispatch_generation_nonneg'"
            ))
            row = result.fetchone()
            assert row is not None
            assert "dispatch_generation >= 0" in row[1]

    def test_partial_pending_index_exists(self, sync_engine: Any) -> None:
        with sync_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT indexname, indexdef "
                "FROM pg_indexes "
                "WHERE tablename = 'workflow_runs' "
                "AND indexname = 'idx_workflow_runs_pending_since'"
            ))
            row = result.fetchone()
            assert row is not None
            assert "pending_since" in row[1]
            assert "PENDING" in row[1]

    def test_unique_constraint_on_steps_exists(self, sync_engine: Any) -> None:
        """D1 §10: unique constraint on (run_id, seq) enforces append-only."""
        with sync_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT conname, pg_get_constraintdef(oid) "
                "FROM pg_constraint "
                "WHERE conrelid = 'workflow_steps'::regclass "
                "AND conname = 'uq_workflow_steps_run_id_seq'"
            ))
            row = result.fetchone()
            assert row is not None
            assert "run_id" in row[1]
            assert "seq" in row[1]

    def test_existing_rows_have_generation_zero(
        self, sync_engine: Any
    ) -> None:
        """D5 §2: existing rows receive generation 0 via server_default."""
        with sync_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM workflow_runs "
                "WHERE dispatch_generation != 0"
            ))
            count = result.scalar()
            # All existing rows should have generation 0.
            assert count == 0


class TestMigrationDowngrade:
    """Verify the D5/D6 migration downgrade."""

    def test_downgrade_removes_columns_and_index(
        self, sync_engine: Any
    ) -> None:
        """Downgrade removes the partial index, unique constraint, and columns."""
        _run_alembic("downgrade", "f1a2b3c4d5e6")
        try:
            with sync_engine.connect() as conn:
                # dispatch_generation should not exist.
                result = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'workflow_runs' "
                    "AND column_name = 'dispatch_generation'"
                ))
                assert result.fetchone() is None

                # pending_since should not exist.
                result = conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'workflow_runs' "
                    "AND column_name = 'pending_since'"
                ))
                assert result.fetchone() is None

                # Index should not exist.
                result = conn.execute(text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'workflow_runs' "
                    "AND indexname = 'idx_workflow_runs_pending_since'"
                ))
                assert result.fetchone() is None

                # Unique constraint on (run_id, seq) should not exist.
                result = conn.execute(text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'workflow_steps'::regclass "
                    "AND conname = 'uq_workflow_steps_run_id_seq'"
                ))
                assert result.fetchone() is None
        finally:
            # Re-upgrade to restore state for other tests.
            _run_alembic("upgrade", "a3b4c5d6e7f8")

    def test_re_upgrade_restores_columns_and_index(
        self, sync_engine: Any
    ) -> None:
        """Re-upgrade restores the columns and index."""
        # This test runs after the downgrade/upgrade cycle above.
        with sync_engine.connect() as conn:
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'workflow_runs' "
                "AND column_name = 'dispatch_generation'"
            ))
            assert result.fetchone() is not None
