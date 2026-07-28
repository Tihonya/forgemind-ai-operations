"""Integration tests for WP-4.1 document schema migration.

Verifies that the Alembic migration creates the correct tables,
columns, indexes, and constraints in the database.
"""
import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Test database URL - follow repository convention (same as test_dataset_integrity.py)
_INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Create async database session for integration tests.

    Yields:
        AsyncSession: Database session connected to test database.
    """
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    session_factory = async_sessionmaker[AsyncSession](
        bind=engine, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


class TestDocumentSchemaMigration:
    """Test document schema migration."""

    async def test_documents_table_exists(self, db_session: AsyncSession) -> None:
        """documents table exists in database."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                "WHERE table_name = 'documents'"
                ")"
            )
        )
        exists = result.scalar()
        assert exists is True

    async def test_document_versions_table_exists(
        self, db_session: AsyncSession
    ) -> None:
        """document_versions table exists in database."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                "WHERE table_name = 'document_versions'"
                ")"
            )
        )
        exists = result.scalar()
        assert exists is True

    async def test_document_permissions_table_exists(
        self, db_session: AsyncSession
    ) -> None:
        """document_permissions table exists in database."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                "WHERE table_name = 'document_permissions'"
                ")"
            )
        )
        exists = result.scalar()
        assert exists is True

    async def test_documents_columns(self, db_session: AsyncSession) -> None:
        """documents table has expected columns."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'documents' "
                "ORDER BY ordinal_position"
            )
        )
        columns = {row[0]: {"type": row[1], "nullable": row[2]} for row in result}

        assert "id" in columns
        assert "title" in columns
        assert "description" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

        assert columns["title"]["nullable"] == "NO"
        assert columns["description"]["nullable"] == "YES"

    async def test_document_versions_columns(self, db_session: AsyncSession) -> None:
        """document_versions table has expected columns."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'document_versions' "
                "ORDER BY ordinal_position"
            )
        )
        columns = {row[0]: {"type": row[1], "nullable": row[2]} for row in result}

        assert "id" in columns
        assert "document_id" in columns
        assert "version_number" in columns
        assert "status" in columns
        assert "content_hash" in columns
        assert "created_at" in columns

        assert columns["document_id"]["nullable"] == "NO"
        assert columns["version_number"]["nullable"] == "NO"
        assert columns["status"]["nullable"] == "NO"
        assert columns["content_hash"]["nullable"] == "YES"

    async def test_document_permissions_columns(
        self, db_session: AsyncSession
    ) -> None:
        """document_permissions table has expected columns."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'document_permissions' "
                "ORDER BY ordinal_position"
            )
        )
        columns = {row[0]: {"type": row[1], "nullable": row[2]} for row in result}

        assert "id" in columns
        assert "document_id" in columns
        assert "role_id" in columns

        assert columns["document_id"]["nullable"] == "NO"
        assert columns["role_id"]["nullable"] == "NO"

    async def test_document_versions_foreign_keys(
        self, db_session: AsyncSession
    ) -> None:
        """document_versions has correct foreign key to documents."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT tc.constraint_name, kcu.column_name, "
                "ccu.table_name AS foreign_table_name, "
                "ccu.column_name AS foreign_column_name "
                "FROM information_schema.table_constraints AS tc "
                "JOIN information_schema.key_column_usage AS kcu "
                "ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage AS ccu "
                "ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.table_name = 'document_versions' "
                "AND tc.constraint_type = 'FOREIGN KEY'"
            )
        )
        foreign_keys = result.fetchall()

        assert len(foreign_keys) == 1
        fk = foreign_keys[0]
        assert fk[1] == "document_id"
        assert fk[2] == "documents"
        assert fk[3] == "id"

    async def test_document_permissions_foreign_keys(
        self, db_session: AsyncSession
    ) -> None:
        """document_permissions has correct foreign keys."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT tc.constraint_name, kcu.column_name, "
                "ccu.table_name AS foreign_table_name, "
                "ccu.column_name AS foreign_column_name "
                "FROM information_schema.table_constraints AS tc "
                "JOIN information_schema.key_column_usage AS kcu "
                "ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage AS ccu "
                "ON ccu.constraint_name = tc.constraint_name "
                "WHERE tc.table_name = 'document_permissions' "
                "AND tc.constraint_type = 'FOREIGN KEY'"
            )
        )
        foreign_keys = result.fetchall()

        assert len(foreign_keys) == 2

        fk_by_column = {fk[1]: fk for fk in foreign_keys}
        assert "document_id" in fk_by_column
        assert "role_id" in fk_by_column

        assert fk_by_column["document_id"][2] == "documents"
        assert fk_by_column["document_id"][3] == "id"
        assert fk_by_column["role_id"][2] == "roles"
        assert fk_by_column["role_id"][3] == "id"

    async def test_document_permissions_unique_constraint(
        self, db_session: AsyncSession
    ) -> None:
        """document_permissions has unique constraint on (document_id, role_id)."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT tc.constraint_name, kcu.column_name "
                "FROM information_schema.table_constraints AS tc "
                "JOIN information_schema.key_column_usage AS kcu "
                "ON tc.constraint_name = kcu.constraint_name "
                "WHERE tc.table_name = 'document_permissions' "
                "AND tc.constraint_type = 'UNIQUE' "
                "ORDER BY tc.constraint_name, kcu.ordinal_position"
            )
        )
        unique_constraints = result.fetchall()

        # Check that at least one unique constraint exists with both columns
        constraint_columns = {}
        for constraint_name, column_name in unique_constraints:
            if constraint_name not in constraint_columns:
                constraint_columns[constraint_name] = set()
            constraint_columns[constraint_name].add(column_name)

        # Find constraint that has both document_id and role_id
        found = False
        for cols in constraint_columns.values():
            if "document_id" in cols and "role_id" in cols:
                found = True
                break

        assert found, (
            f"Expected unique constraint on "
            f"(document_id, role_id), got: {constraint_columns}"
        )

    async def test_document_versions_index_exists(
        self, db_session: AsyncSession
    ) -> None:
        """idx_document_versions_document_id index exists."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT indexname "
                "FROM pg_indexes "
                "WHERE tablename = 'document_versions' "
                "AND indexname = 'idx_document_versions_document_id'"
            )
        )
        index = result.scalar()
        assert index == "idx_document_versions_document_id"

    async def test_document_permissions_indexes_exist(
        self, db_session: AsyncSession
    ) -> None:
        """document_permissions has expected indexes."""
        from sqlalchemy import text

        result = await db_session.execute(
            text(
                "SELECT indexname "
                "FROM pg_indexes "
                "WHERE tablename = 'document_permissions' "
                "AND indexname IN ("
                "'idx_document_permissions_document_id', "
                "'idx_document_permissions_role_id'"
                ")"
            )
        )
        indexes = {row[0] for row in result}
        assert "idx_document_permissions_document_id" in indexes
        assert "idx_document_permissions_role_id" in indexes
