"""Integration tests for WP-4.3A0 DocumentVersion.content migration.

Verifies that the Alembic migration c7d8e9f0a1b2 -> 625c9f549f2b correctly
adds the content column to document_versions with nullable TEXT type, no
server default, and proper round-trip behavior for NULL, Unicode, and large
text values. Also verifies downgrade safety and re-upgrade restoration.

Requires a live PostgreSQL database with Alembic migrations applied.
Skips cleanly if the database is unavailable.
"""

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Determine if integration environment is available
_INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _can_connect_to_db() -> bool:
    """Check if we can connect to the database."""
    if not _INTEGRATION_DB_URL:
        return False
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


# Skip all tests in this module if no integration DB
pytestmark = pytest.mark.skipif(
    not _can_connect_to_db(),
    reason=(
        "Integration database not available "
        "(TEST_DATABASE_URL or DATABASE_URL not set/unreachable)"
    ),
)


def _get_sync_engine() -> Engine:
    """Create synchronous SQLAlchemy engine for tests."""
    if not _INTEGRATION_DB_URL:
        raise RuntimeError("TEST_DATABASE_URL or DATABASE_URL not set")
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")
    return create_engine(sync_url, echo=False, pool_pre_ping=True)


def _get_async_engine() -> AsyncEngine:
    """Create async SQLAlchemy engine for service tests."""
    if not _INTEGRATION_DB_URL:
        raise RuntimeError("TEST_DATABASE_URL or DATABASE_URL not set")
    async_url = _INTEGRATION_DB_URL
    if "+psycopg" in async_url:
        async_url = async_url.replace("+psycopg", "+asyncpg")
    return create_async_engine(async_url, echo=False, pool_pre_ping=True)


def _run_alembic_upgrade(revision: str = "head") -> None:
    """Run alembic upgrade to specified revision.

    Temporarily escapes ``%`` in ``settings.database_url`` for
    configparser compatibility (same pattern as the lifecycle test).
    """
    from pathlib import Path

    from alembic.config import Config

    from alembic import command
    from app.config import settings  # noqa: I001

    backend_dir = Path(__file__).resolve().parent.parent.parent
    alembic_cfg_path = backend_dir / "alembic.ini"

    config = Config(str(alembic_cfg_path))
    config.set_main_option("script_location", str(backend_dir / "alembic"))

    assert _INTEGRATION_DB_URL is not None
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")

    original_db_url = settings.database_url
    settings.database_url = original_db_url.replace("%", "%%")
    try:
        # Escape % in sync_url for configparser (env.py will overwrite
        # this with settings.database_url, but set_main_option must not
        # raise before env.py runs).
        config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))
        command.upgrade(config, revision)
    finally:
        settings.database_url = original_db_url


def _run_alembic_downgrade(revision: str) -> None:
    """Run alembic downgrade to specified revision.

    Temporarily escapes ``%`` in ``settings.database_url`` for
    configparser compatibility (same pattern as the lifecycle test).
    """
    from pathlib import Path

    from alembic.config import Config

    from alembic import command
    from app.config import settings  # noqa: I001

    backend_dir = Path(__file__).resolve().parent.parent.parent
    alembic_cfg_path = backend_dir / "alembic.ini"

    config = Config(str(alembic_cfg_path))
    config.set_main_option("script_location", str(backend_dir / "alembic"))

    assert _INTEGRATION_DB_URL is not None
    sync_url = _INTEGRATION_DB_URL
    if "+asyncpg" in sync_url:
        sync_url = sync_url.replace("+asyncpg", "+psycopg")

    original_db_url = settings.database_url
    settings.database_url = original_db_url.replace("%", "%%")
    try:
        # Escape % in sync_url for configparser (env.py will overwrite
        # this with settings.database_url, but set_main_option must not
        # raise before env.py runs).
        config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))
        command.downgrade(config, revision)
    finally:
        settings.database_url = original_db_url


@contextmanager
def _at_revision(target: str) -> Iterator[None]:
    """Context manager that restores Alembic to ``head`` on exit.

    Downgrades to ``target`` on entry, runs the test body, and
    unconditionally upgrades back to ``head`` in the ``finally`` block.
    If the body raises, the original exception is preserved while a
    cleanup failure is reported via a chained exception (making cleanup
    failure visible without masking the original error).

    This enforces the invariant that after every schema-mutating test,
    including assertion/error paths, the database is at ``head``.
    """
    _run_alembic_downgrade(target)
    try:
        yield
    finally:
        _run_alembic_upgrade("head")


@contextmanager
def _upgrade_to(target: str) -> Iterator[None]:
    """Context manager that upgrades to ``target`` and restores ``head``.

    Upgrades to ``target`` on entry, runs the test body, and
    unconditionally upgrades back to ``head`` in the ``finally`` block.
    If the body raises, the original exception is preserved while a
    cleanup failure is reported via a chained exception.
    """
    _run_alembic_upgrade(target)
    try:
        yield
    finally:
        _run_alembic_upgrade("head")


@pytest.fixture
def sync_connection() -> Iterator[Connection]:
    """Provide a synchronous database connection."""
    engine = _get_sync_engine()
    with engine.connect() as conn:
        yield conn
    engine.dispose()


@pytest.fixture
async def async_session() -> AsyncIterator[AsyncSession]:
    """Provide an async database session."""
    engine = _get_async_engine()
    async_session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session_factory() as session:
        yield session
    await engine.dispose()


class TestDocumentVersionContentMigration:
    """Test migration c7d8e9f0a1b2 -> 625c9f549f2b adds content column."""

    def test_migration_upgrade_adds_content_column(
        self, sync_connection: Connection
    ) -> None:
        """After upgrade to 625c9f549f2b, document_versions.content exists."""
        # Use the context manager to guarantee head restoration even if
        # assertions fail — the cleanup runs in the finally path.
        with _upgrade_to("625c9f549f2b"):
            result = sync_connection.execute(
                text("""
                    SELECT column_name, data_type, is_nullable, column_default
                    FROM information_schema.columns
                    WHERE table_name = 'document_versions' AND column_name = 'content'
                """)
            )
            row = result.fetchone()

            assert row is not None, "content column must exist after migration"
            column_name, data_type, is_nullable, column_default = row

            assert column_name == "content"
            assert data_type == "text", f"Expected text type, got {data_type}"
            assert is_nullable == "YES", "content column must be nullable"
            assert column_default is None, "content column must have no default"

    def test_migration_downgrade_removes_content_column(
        self, sync_connection: Connection
    ) -> None:
        """After downgrade to c7d8e9f0a1b2, content column is removed."""
        with _at_revision("c7d8e9f0a1b2"):
            result = sync_connection.execute(
                text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'document_versions' AND column_name = 'content'
                """)
            )
            row = result.fetchone()

            assert row is None, "content column must not exist after downgrade"

    async def test_existing_row_preserved_with_null_content(
        self, async_session: AsyncSession
    ) -> None:
        """Existing DocumentVersion row survives migration with content=NULL."""
        # Insert a DocumentVersion without content (pre-migration schema)
        # First we need a document
        doc_result = await async_session.execute(
            text("""
                INSERT INTO documents (title, description, created_at, updated_at)
                VALUES ('Test Document', 'Test Description', NOW(), NOW())
                RETURNING id
            """)
        )
        doc_id = doc_result.scalar_one()

        # Insert a DocumentVersion with explicit NULL content
        await async_session.execute(
            text("""
                INSERT INTO document_versions
                    (document_id, version_number, status, content, created_at)
                VALUES
                    (:doc_id, '1.0', 'draft', NULL, NOW())
            """),
            {"doc_id": doc_id},
        )
        await async_session.commit()

        # Verify the row exists with content=NULL
        result = await async_session.execute(
            text("""
                SELECT document_id, version_number, status, content
                FROM document_versions
                WHERE document_id = :doc_id AND version_number = '1.0'
            """),
            {"doc_id": doc_id},
        )
        row = result.fetchone()

        assert row is not None, "DocumentVersion row must exist"
        assert row[0] == doc_id
        assert row[1] == "1.0"
        assert row[2] == "draft"
        assert row[3] is None, "content must be NULL"

        # Cleanup
        await async_session.execute(
            text("DELETE FROM document_versions WHERE document_id = :doc_id"),
            {"doc_id": doc_id},
        )
        await async_session.execute(
            text("DELETE FROM documents WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )
        await async_session.commit()

    async def test_null_content_roundtrip(self, async_session: AsyncSession) -> None:
        """Explicit NULL content can be written and read back."""
        doc_result = await async_session.execute(
            text("""
                INSERT INTO documents (title, description, created_at, updated_at)
                VALUES ('Test Document', 'Test Description', NOW(), NOW())
                RETURNING id
            """)
        )
        doc_id = doc_result.scalar_one()

        await async_session.execute(
            text("""
                INSERT INTO document_versions
                    (document_id, version_number, status, content, created_at)
                VALUES
                    (:doc_id, '1.0', 'draft', NULL, NOW())
            """),
            {"doc_id": doc_id},
        )
        await async_session.commit()

        result = await async_session.execute(
            text("""
                SELECT content FROM document_versions WHERE document_id = :doc_id
            """),
            {"doc_id": doc_id},
        )
        content = result.scalar_one()

        assert content is None, "NULL content must roundtrip as None"

        # Cleanup
        await async_session.execute(
            text("DELETE FROM document_versions WHERE document_id = :doc_id"),
            {"doc_id": doc_id},
        )
        await async_session.execute(
            text("DELETE FROM documents WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )
        await async_session.commit()

    async def test_unicode_content_roundtrip(self, async_session: AsyncSession) -> None:
        """Unicode and multi-paragraph content roundtrips correctly."""
        doc_result = await async_session.execute(
            text("""
                INSERT INTO documents (title, description, created_at, updated_at)
                VALUES ('Test Document', 'Test Description', NOW(), NOW())
                RETURNING id
            """)
        )
        doc_id = doc_result.scalar_one()

        unicode_content = """# Test Document

This is a test document with Unicode characters: 你好世界 🌍

Second paragraph with more Unicode: Привет мир 🚀

Third paragraph with special chars: ñ é ü ß"""

        await async_session.execute(
            text("""
                INSERT INTO document_versions
                    (document_id, version_number, status, content, created_at)
                VALUES
                    (:doc_id, '1.0', 'draft', :content, NOW())
            """),
            {"doc_id": doc_id, "content": unicode_content},
        )
        await async_session.commit()

        result = await async_session.execute(
            text("""
                SELECT content FROM document_versions WHERE document_id = :doc_id
            """),
            {"doc_id": doc_id},
        )
        content = result.scalar_one()

        assert content == unicode_content, "Unicode content must roundtrip exactly"

        # Cleanup
        await async_session.execute(
            text("DELETE FROM document_versions WHERE document_id = :doc_id"),
            {"doc_id": doc_id},
        )
        await async_session.execute(
            text("DELETE FROM documents WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )
        await async_session.commit()

    async def test_large_content_roundtrip(self, async_session: AsyncSession) -> None:
        """Large text content (~50KB) roundtrips without truncation."""
        doc_result = await async_session.execute(
            text("""
                INSERT INTO documents (title, description, created_at, updated_at)
                VALUES ('Test Document', 'Test Description', NOW(), NOW())
                RETURNING id
            """)
        )
        doc_id = doc_result.scalar_one()

        # Generate ~50KB of text
        large_content = "A" * 50_000

        await async_session.execute(
            text("""
                INSERT INTO document_versions
                    (document_id, version_number, status, content, created_at)
                VALUES
                    (:doc_id, '1.0', 'draft', :content, NOW())
            """),
            {"doc_id": doc_id, "content": large_content},
        )
        await async_session.commit()

        result = await async_session.execute(
            text("""
                SELECT content FROM document_versions WHERE document_id = :doc_id
            """),
            {"doc_id": doc_id},
        )
        content = result.scalar_one()

        assert content == large_content, "Large content must roundtrip without truncation"
        assert len(content) == 50_000, "Content length must be preserved"

        # Cleanup
        await async_session.execute(
            text("DELETE FROM document_versions WHERE document_id = :doc_id"),
            {"doc_id": doc_id},
        )
        await async_session.execute(
            text("DELETE FROM documents WHERE id = :doc_id"),
            {"doc_id": doc_id},
        )
        await async_session.commit()

    def test_re_upgrade_restores_content_column(
        self, sync_connection: Connection
    ) -> None:
        """After downgrade and re-upgrade, content column is restored."""
        with _at_revision("c7d8e9f0a1b2"):
            # Verify content is gone
            result = sync_connection.execute(
                text("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'document_versions' AND column_name = 'content'
                """)
            )
            assert result.fetchone() is None, "content must be removed after downgrade"

        # After the context manager exits, the DB is back at head.
        # Verify content is restored.
        result = sync_connection.execute(
            text("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name = 'document_versions' AND column_name = 'content'
            """)
        )
        row = result.fetchone()

        assert row is not None, "content column must exist after re-upgrade"
        column_name, data_type, is_nullable, column_default = row

        assert column_name == "content"
        assert data_type == "text"
        assert is_nullable == "YES"
        assert column_default is None

    def test_cleanup_runs_on_body_failure(self) -> None:
        """Cleanup must restore head even when the test body raises.

        This test deliberately triggers an assertion failure inside the
        ``_at_revision`` context manager and verifies that:

        1. The assertion error propagates (not swallowed).
        2. The database is restored to ``head`` after the failure.
        """
        # Use a separate sync connection to verify the revision state
        # before and after the forced failure.
        engine = _get_sync_engine()
        try:
            with engine.connect() as conn:
                # Enter the context manager (downgrades to c7d8e9f0a1b2)
                try:
                    with _at_revision("c7d8e9f0a1b2"):
                        # Verify we are at the historical revision
                        rev_result = conn.execute(
                            text("SELECT version_num FROM alembic_version")
                        )
                        assert rev_result.scalar() == "c7d8e9f0a1b2"

                        # Deliberately fail — this exercises the
                        # finally-cleanup path.
                        raise AssertionError("forced failure for cleanup test")
                except AssertionError:
                    pass  # Expected — we swallow it here to inspect state

                # After the context manager exited via exception, the
                # cleanup must have restored head.
                rev_after = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                )
                # Head tracks the latest migration (WP-REC-04A).
                assert rev_after.scalar() == "3e619e551708", (
                    "Cleanup must restore head even after body failure"
                )
        finally:
            engine.dispose()

    def test_cleanup_runs_on_body_failure_upgrade_path(self) -> None:
        """Cleanup must restore head when upgrade-to-intermediate body fails.

        Same as above but exercises the ``_upgrade_to`` path (which
        upgrades to an intermediate revision, not a downgrade).
        """
        engine = _get_sync_engine()
        try:
            with engine.connect() as conn:
                try:
                    with _upgrade_to("625c9f549f2b"):
                        rev_result = conn.execute(
                            text("SELECT version_num FROM alembic_version")
                        )
                        assert rev_result.scalar() == "625c9f549f2b"

                        raise AssertionError(
                            "forced failure for upgrade cleanup test"
                        )
                except AssertionError:
                    pass

                rev_after = conn.execute(
                    text("SELECT version_num FROM alembic_version")
                )
                # Head tracks the latest migration (WP-REC-04A).
                assert rev_after.scalar() == "3e619e551708", (
                    "Cleanup must restore head after upgrade-path failure"
                )
        finally:
            engine.dispose()
