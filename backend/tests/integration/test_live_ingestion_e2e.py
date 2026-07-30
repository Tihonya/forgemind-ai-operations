"""End-to-end test for live ingestion pipeline (WP-4.3B5 Scenario A).

Verifies that IngestionOrchestrator can ingest a DocumentVersion with
real content, chunk it, generate embeddings via FakeEmbeddingProvider,
and persist KnowledgeChunk rows (including pgvector embeddings) into
a live PostgreSQL database.
"""

import contextlib
import os
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.document import Document, DocumentVersion
from app.models.knowledge import KnowledgeChunk
from app.services.embedding_provider import (
    EmbeddingProvider,
    FakeEmbeddingProvider,
    PermanentEmbeddingProviderError,
)
from app.services.ingestion import IngestionOrchestrator

# ---------------------------------------------------------------------------
# Integration-gate: skip entire module when no DB is reachable
# ---------------------------------------------------------------------------

INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _can_connect() -> bool:
    if not INTEGRATION_DB_URL:
        return False
    try:
        from sqlalchemy import create_engine

        url = INTEGRATION_DB_URL.replace("+asyncpg", "+psycopg")
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect(),
    reason="Integration database not available",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _get_async_engine() -> AsyncEngine:
    assert INTEGRATION_DB_URL is not None
    url = INTEGRATION_DB_URL
    if "+psycopg" in url:
        url = url.replace("+psycopg", "+asyncpg")
    return create_async_engine(url, echo=False, pool_pre_ping=True)


@pytest.fixture
async def async_session() -> AsyncIterator[AsyncSession]:
    engine = _get_async_engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_direct_ingestion_persists_pgvector_chunks(
    async_session: AsyncSession,
) -> None:
    """Full ingestion pipeline: document -> chunks -> embeddings -> DB."""

    # Arrange — create a document and version with enough content
    # to produce multiple chunks (default chunk_size=1000, overlap=200).
    doc_id = uuid4()
    version_id = uuid4()

    known_content = (
        "Section A. " * 200 + "Section B. " * 200 + "Section C. " * 200
    )

    doc = Document(id=doc_id, title="WP-4.3B5 E2E Integration Test", description=None)
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number="1.0",
        status="draft",
        content_hash=None,
        content=known_content,
    )

    async_session.add(doc)
    async_session.add(version)
    await async_session.flush()

    try:
        # Act — run ingestion
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)
        result = await orchestrator.ingest_document_version(version_id)
        await async_session.commit()

        # Assert — pipeline result
        assert result.status == "completed"
        assert result.document_version_id == version_id
        assert result.chunks_count > 0
        assert result.embeddings_count == result.chunks_count

        # Assert — query real PostgreSQL for persisted chunks
        chunk_result = await async_session.execute(
            select(KnowledgeChunk)
            .where(KnowledgeChunk.document_version_id == version_id)
            .order_by(KnowledgeChunk.chunk_index)
        )
        chunks = chunk_result.scalars().all()

        assert len(chunks) == result.chunks_count
        assert len(chunks) > 0

        for i, chunk in enumerate(chunks):
            assert chunk.document_version_id == version_id
            assert chunk.chunk_index == i
            assert chunk.chunk_text and len(chunk.chunk_text) > 0
            assert chunk.embedding is not None
            assert len(chunk.embedding) == 1536

    finally:
        # Cleanup — always remove test data
        await async_session.execute(
            text("DELETE FROM knowledge_chunks WHERE document_version_id = :vid"),
            {"vid": version_id},
        )
        await async_session.execute(
            text("DELETE FROM document_versions WHERE id = :vid"),
            {"vid": version_id},
        )
        await async_session.execute(
            text("DELETE FROM documents WHERE id = :did"),
            {"did": doc_id},
        )
        await async_session.commit()

        # Verify cleanup: query database to confirm zero rows remain
        chunk_row = await async_session.execute(
            text("SELECT COUNT(*) FROM knowledge_chunks WHERE document_version_id = :vid"),
            {"vid": version_id},
        )
        chunk_count = chunk_row.scalar()
        assert chunk_count == 0, f"Expected 0 chunks after cleanup, got {chunk_count}"

        version_row = await async_session.execute(
            text("SELECT COUNT(*) FROM document_versions WHERE id = :vid"),
            {"vid": version_id},
        )
        version_count = version_row.scalar()
        assert version_count == 0, f"Expected 0 versions after cleanup, got {version_count}"

        doc_row = await async_session.execute(
            text("SELECT COUNT(*) FROM documents WHERE id = :did"),
            {"did": doc_id},
        )
        doc_count = doc_row.scalar()
        assert doc_count == 0, f"Expected 0 documents after cleanup, got {doc_count}"


class _FailingEmbeddingProvider(EmbeddingProvider):
    """Embedding provider that always raises a permanent error."""

    async def embed_text(self, texts: list[str]) -> list[list[float]]:
        raise PermanentEmbeddingProviderError("Simulated deterministic failure")

    def dimension(self) -> int:
        return 1536


async def test_failed_ingestion_rolls_back_without_affecting_committed_version(
    async_session: AsyncSession,
) -> None:
    """Prove that a provider failure triggers caller-owned rollback
    without touching previously committed successful ingestion rows."""

    # 1. UUIDs
    success_doc_id = uuid4()
    success_vid = uuid4()
    fail_doc_id = uuid4()
    fail_vid = uuid4()

    # 2. Create success document + version with enough content for multiple chunks
    success_doc = Document(
        id=success_doc_id,
        title="WP-4.3B5 Scenario B - Success",
        description=None,
    )
    success_version = DocumentVersion(
        id=success_vid,
        document_id=success_doc_id,
        version_number="1.0",
        status="draft",
        content_hash=None,
        content=(
            "Section A. " * 200
            + "Section B. " * 200
            + "Section C. " * 200
        ),
    )

    # 3. Flush success entities
    async_session.add(success_doc)
    async_session.add(success_version)
    await async_session.flush()

    # 4. Ingest success version (good provider)
    provider = FakeEmbeddingProvider(dimension=1536)
    orchestrator = IngestionOrchestrator(async_session, provider)
    await orchestrator.ingest_document_version(success_vid)

    # 5. Commit success ingestion
    await async_session.commit()

    # 6. Record success chunk count (must be > 0)
    chunk_result = await async_session.execute(
        select(KnowledgeChunk).where(
            KnowledgeChunk.document_version_id == success_vid
        )
    )
    success_chunk_count = len(chunk_result.scalars().all())
    assert success_chunk_count > 0

    # 7. Create fail document + version
    fail_doc = Document(
        id=fail_doc_id,
        title="WP-4.3B5 Scenario B - Fail",
        description=None,
    )
    fail_version = DocumentVersion(
        id=fail_vid,
        document_id=fail_doc_id,
        version_number="1.0",
        status="draft",
        content_hash=None,
        content="Fail section. " * 200 + "Fail section. " * 200,
    )

    # 8. Flush and commit fail entities
    async_session.add(fail_doc)
    async_session.add(fail_version)
    await async_session.flush()
    await async_session.commit()

    try:
        # 9. Attempt ingestion with failing provider — must raise
        failing_provider = _FailingEmbeddingProvider()
        fail_orchestrator = IngestionOrchestrator(async_session, failing_provider)

        # B1: pytest.raises guarantees the exception was actually raised
        with pytest.raises(PermanentEmbeddingProviderError):
            await fail_orchestrator.ingest_document_version(fail_vid)

        # Rollback after the exception
        await async_session.rollback()

        # 12. Assert no chunks for the failed version
        fail_chunk_result = await async_session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_version_id == fail_vid
            )
        )
        fail_chunks = fail_chunk_result.scalars().all()
        assert len(fail_chunks) == 0

        # 13. Assert success chunks are untouched
        success_chunk_result = await async_session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_version_id == success_vid
            )
        )
        remaining_success_chunks = success_chunk_result.scalars().all()
        assert len(remaining_success_chunks) == success_chunk_count

    finally:
        # B2: cleanup always runs, even if assertions above fail
        # Rollback if session is in a failed transaction state
        with contextlib.suppress(Exception):
            await async_session.rollback()

        # Cleanup SQL — delete test data
        await async_session.execute(
            text("DELETE FROM knowledge_chunks WHERE document_version_id = :vid"),
            {"vid": success_vid},
        )
        await async_session.execute(
            text("DELETE FROM knowledge_chunks WHERE document_version_id = :vid"),
            {"vid": fail_vid},
        )
        await async_session.execute(
            text("DELETE FROM document_versions WHERE id = :vid"),
            {"vid": success_vid},
        )
        await async_session.execute(
            text("DELETE FROM document_versions WHERE id = :vid"),
            {"vid": fail_vid},
        )
        await async_session.execute(
            text("DELETE FROM documents WHERE id = :did"),
            {"did": success_doc_id},
        )
        await async_session.execute(
            text("DELETE FROM documents WHERE id = :did"),
            {"did": fail_doc_id},
        )
        await async_session.commit()

        # B3: 6 post-cleanup zero assertions
        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid"
            ),
            {"vid": success_vid},
        )
        assert row.scalar() == 0, (
            f"Expected 0 chunks for success_vid, got {row.scalar()}"
        )

        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid"
            ),
            {"vid": fail_vid},
        )
        assert row.scalar() == 0, (
            f"Expected 0 chunks for fail_vid, got {row.scalar()}"
        )

        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM document_versions WHERE id = :vid"
            ),
            {"vid": success_vid},
        )
        assert row.scalar() == 0, (
            f"Expected 0 versions for success_vid, got {row.scalar()}"
        )

        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM document_versions WHERE id = :vid"
            ),
            {"vid": fail_vid},
        )
        assert row.scalar() == 0, (
            f"Expected 0 versions for fail_vid, got {row.scalar()}"
        )

        row = await async_session.execute(
            text("SELECT COUNT(*) FROM documents WHERE id = :did"),
            {"did": success_doc_id},
        )
        assert row.scalar() == 0, (
            f"Expected 0 documents for success_doc_id, got {row.scalar()}"
        )

        row = await async_session.execute(
            text("SELECT COUNT(*) FROM documents WHERE id = :did"),
            {"did": fail_doc_id},
        )
        assert row.scalar() == 0, (
            f"Expected 0 documents for fail_doc_id, got {row.scalar()}"
        )
