"""Integration tests for WP-4.2 knowledge_chunks migration.

Verifies that the Alembic migration creates the correct tables,
columns, indexes, constraints, and foreign keys in a live PostgreSQL
instance with pgvector.

Uses the downgrade -> upgrade -> re-upgrade cycle to verify reversibility.
"""
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

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


def _run_downgrade(target: str = "a1b2c3d4e5f6") -> None:
    """Run alembic downgrade to the given revision."""
    from alembic.config import Config

    from alembic import command

    sync_url = _get_sync_url()
    sync_engine = create_engine(sync_url, echo=False)
    alembic_cfg = Config(str(_ALEMBIC_INI))
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)

    with sync_engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.downgrade(alembic_cfg, target)
    sync_engine.dispose()


def _run_upgrade(target: str = "head") -> None:
    """Run alembic upgrade to the given revision."""
    from alembic.config import Config

    from alembic import command

    sync_url = _get_sync_url()
    sync_engine = create_engine(sync_url, echo=False)
    alembic_cfg = Config(str(_ALEMBIC_INI))
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)

    with sync_engine.begin() as conn:
        alembic_cfg.attributes["connection"] = conn
        command.upgrade(alembic_cfg, target)
    sync_engine.dispose()


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Create async database session for integration tests."""
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    session_factory = async_sessionmaker[AsyncSession](
        bind=engine, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


class TestKnowledgeChunksMigrationUpgrade:
    """Tests run after 'alembic upgrade head' (WP-4.2 migration applied)."""

    async def test_vector_extension_exists(
        self, db_session: AsyncSession
    ) -> None:
        """pgvector extension is installed after upgrade."""
        result = await db_session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            )
        )
        assert result.scalar() is True

    async def test_knowledge_chunks_table_exists(
        self, db_session: AsyncSession
    ) -> None:
        """knowledge_chunks table exists after upgrade."""
        result = await db_session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                "WHERE table_name = 'knowledge_chunks')"
            )
        )
        assert result.scalar() is True

    async def test_all_columns_exist_with_correct_types(
        self, db_session: AsyncSession
    ) -> None:
        """All knowledge_chunks columns exist with correct PostgreSQL types."""
        result = await db_session.execute(
            text(
                "SELECT column_name, data_type, udt_name, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_name = 'knowledge_chunks' "
                "ORDER BY ordinal_position"
            )
        )
        columns: dict = {}
        for row in result:
            columns[row[0]] = {
                "type": row[1],
                "udt_name": row[2],
                "nullable": row[3],
            }

        expected_columns: dict = {
            "id": {"type": "uuid", "nullable": "NO"},
            "document_version_id": {"type": "uuid", "nullable": "NO"},
            "chunk_index": {"type": "integer", "nullable": "NO"},
            "chunk_text": {"type": "text", "nullable": "NO"},
            "token_count": {"type": "integer", "nullable": "YES"},
            "metadata": {"type": "jsonb", "nullable": "YES"},
            "content_hash": {
                "type": "character varying",
                "nullable": "YES",
            },
            "embedding": {"nullable": "YES"},
            "created_at": {"nullable": "NO"},
        }

        for col_name, expected in expected_columns.items():
            assert col_name in columns, (
                f"Column '{col_name}' not found"
            )
            actual = columns[col_name]
            for key, value in expected.items():
                if col_name == "embedding" and key in (
                    "type",
                    "udt_name",
                ):
                    continue
                assert actual.get(key) == value, (
                    f"Column {col_name}.{key}: "
                    f"expected {value}, got {actual.get(key)}"
                )

    async def test_embedding_column_is_vector_type(
        self, db_session: AsyncSession
    ) -> None:
        """embedding column is vector type with dimension 1536."""
        result = await db_session.execute(
            text(
                "SELECT data_type, udt_name "
                "FROM information_schema.columns "
                "WHERE table_name = 'knowledge_chunks' "
                "AND column_name = 'embedding'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[1] == "vector"

    async def test_embedding_dimension_is_1536(
        self, db_session: AsyncSession
    ) -> None:
        """embedding vector dimension is 1536."""
        result = await db_session.execute(
            text(
                "SELECT atttypmod "
                "FROM pg_attribute "
                "WHERE attrelid = 'knowledge_chunks'::regclass "
                "AND attname = 'embedding'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == 1536

    async def test_metadata_column_is_jsonb_type(
        self, db_session: AsyncSession
    ) -> None:
        """metadata column is jsonb type."""
        result = await db_session.execute(
            text(
                "SELECT udt_name "
                "FROM information_schema.columns "
                "WHERE table_name = 'knowledge_chunks' "
                "AND column_name = 'metadata'"
            )
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "jsonb"

    async def test_fk_points_to_document_versions_id(
        self, db_session: AsyncSession
    ) -> None:
        """FK from knowledge_chunks points to document_versions.id."""
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
                "WHERE tc.table_name = 'knowledge_chunks' "
                "AND tc.constraint_type = 'FOREIGN KEY'"
            )
        )
        foreign_keys = result.fetchall()
        assert len(foreign_keys) >= 1
        fk_by_column = {fk[1]: fk for fk in foreign_keys}
        assert "document_version_id" in fk_by_column
        fk = fk_by_column["document_version_id"]
        assert fk[2] == "document_versions"
        assert fk[3] == "id"

    async def test_fk_deletion_behavior_is_cascade(
        self, db_session: AsyncSession
    ) -> None:
        """FK on knowledge_chunks.document_version_id has ON DELETE CASCADE."""
        result = await db_session.execute(
            text(
                "SELECT conname, confdeltype "
                "FROM pg_constraint "
                "WHERE conrelid = 'knowledge_chunks'::regclass "
                "AND contype = 'f' "
                "AND confrelid = 'document_versions'::regclass"
            )
        )
        row = result.fetchone()
        assert row is not None, (
            "FK constraint from knowledge_chunks to document_versions "
            "not found"
        )
        # confdeltype b'c' = CASCADE (PostgreSQL returns bytes via asyncpg)
        assert row[1] == b"c", (
            f"FK deletion behavior is {row[1]}, "
            "expected b'c' (CASCADE)"
        )

    async def test_unique_constraint_on_document_version_id_chunk_index(
        self, db_session: AsyncSession
    ) -> None:
        """Unique constraint exists on (document_version_id, chunk_index)."""
        result = await db_session.execute(
            text(
                "SELECT conname "
                "FROM pg_constraint "
                "WHERE conrelid = 'knowledge_chunks'::regclass "
                "AND contype = 'u' "
                "AND conname = "
                "'uq_knowledge_chunks_document_version_id_chunk_index'"
            )
        )
        row = result.fetchone()
        assert row is not None, (
            "Unique constraint "
            "'uq_knowledge_chunks_document_version_id_chunk_index' "
            "not found"
        )

    async def test_ix_knowledge_chunks_document_version_id_index_exists(
        self, db_session: AsyncSession
    ) -> None:
        """ix_knowledge_chunks_document_version_id btree index exists."""
        result = await db_session.execute(
            text(
                "SELECT indexname "
                "FROM pg_indexes "
                "WHERE tablename = 'knowledge_chunks' "
                "AND indexname = "
                "'ix_knowledge_chunks_document_version_id'"
            )
        )
        index = result.scalar()
        assert index == "ix_knowledge_chunks_document_version_id"

    async def test_no_ann_index_exists(
        self, db_session: AsyncSession
    ) -> None:
        """No HNSW or IVFFlat index exists on knowledge_chunks."""
        result = await db_session.execute(
            text(
                "SELECT indexname, indexdef "
                "FROM pg_indexes "
                "WHERE tablename = 'knowledge_chunks'"
            )
        )
        indexes = result.fetchall()
        for idx_name, idx_def in indexes:
            assert "hnsw" not in idx_def.lower(), (
                f"HNSW index found: {idx_name}"
            )
            assert "ivfflat" not in idx_def.lower(), (
                f"IVFFlat index found: {idx_name}"
            )


class TestKnowledgeChunksMigrationDowngrade:
    """Tests for downgrade: remove knowledge_chunks, verify predecessor."""

    async def test_downgrade_removes_knowledge_chunks_table(
        self, db_session: AsyncSession
    ) -> None:
        """knowledge_chunks table is removed after downgrade."""
        _run_downgrade("a1b2c3d4e5f6")

        result = await db_session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                "WHERE table_name = 'knowledge_chunks')"
            )
        )
        assert result.scalar() is False

        # Re-upgrade for subsequent tests
        _run_upgrade("head")

    async def test_predecessor_wp41_tables_remain_after_downgrade(
        self, db_session: AsyncSession
    ) -> None:
        """WP-4.1 tables remain after downgrade."""
        _run_downgrade("a1b2c3d4e5f6")

        # Check documents table still exists
        result = await db_session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                "WHERE table_name = 'documents')"
            )
        )
        assert result.scalar() is True

        # Check document_versions table still exists
        result = await db_session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                "WHERE table_name = 'document_versions')"
            )
        )
        assert result.scalar() is True

        # Re-upgrade for subsequent tests
        _run_upgrade("head")

    async def test_re_upgrade_restores_knowledge_chunks_table(
        self, db_session: AsyncSession
    ) -> None:
        """Re-upgrade from a1b2c3d4e5f6 restores knowledge_chunks table."""
        _run_downgrade("a1b2c3d4e5f6")
        _run_upgrade("head")

        result = await db_session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT FROM information_schema.tables "
                "WHERE table_name = 'knowledge_chunks')"
            )
        )
        assert result.scalar() is True

    async def test_vector_extension_remains_after_downgrade(
        self, db_session: AsyncSession
    ) -> None:
        """pgvector extension remains installed after downgrade."""
        _run_downgrade("a1b2c3d4e5f6")

        result = await db_session.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            )
        )
        assert result.scalar() is True

        # Re-upgrade for subsequent tests
        _run_upgrade("head")
