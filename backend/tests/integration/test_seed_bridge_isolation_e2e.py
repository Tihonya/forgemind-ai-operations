"""End-to-end test for seed bridge per-version isolation (WP-4.3B5 Scenario C).

Verifies that _ingest_seed_documents processes three versions sequentially:
  - Version 1: success (chunks committed)
  - Version 2: deterministic embedding failure (rollback, no chunks)
  - Version 3: success (chunks committed despite Version 2 failure)

Proves that each version gets its own transaction boundary and that a
failure in one version does not affect previously committed or subsequent
successful versions.

Uses real PostgreSQL + pgvector. No mocks of persistence.
"""

import os
from collections.abc import AsyncIterator
from contextlib import suppress
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.document import Document, DocumentVersion
from app.services.embedding_provider import (
    EmbeddingProvider,
    FakeEmbeddingProvider,
    PermanentEmbeddingProviderError,
)

# ---------------------------------------------------------------------------
# Integration-gate: skip entire module when no DB is reachable
# ---------------------------------------------------------------------------

INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
    "DATABASE_URL"
)


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
# Constants
# ---------------------------------------------------------------------------

FAILURE_MARKER = "WP43B5_FORCE_EMBEDDING_FAILURE"
VECTOR_DIMENSION = 1536
NORMAL_CONTENT = ("Section A. " * 200 + "Section B. " * 200 + "Section C. " * 200)
FAIL_CONTENT = (
    "Section X. " * 200 + f" {FAILURE_MARKER} " + "Section Y. " * 200
)


# ---------------------------------------------------------------------------
# Content-gated embedding provider
# ---------------------------------------------------------------------------


class ContentGatedEmbeddingProvider(EmbeddingProvider):
    """Provider that raises PermanentEmbeddingProviderError when any input
    text contains the failure marker. Otherwise delegates to
    FakeEmbeddingProvider for deterministic embeddings.
    """

    def __init__(self, *, dimension: int = VECTOR_DIMENSION) -> None:
        self._inner = FakeEmbeddingProvider(dimension=dimension)

    def dimension(self) -> int:
        return self._inner.dimension()

    async def embed_text(self, texts: list[str]) -> list[list[float]]:
        for t in texts:
            if FAILURE_MARKER in t:
                raise PermanentEmbeddingProviderError(
                    f"Content-gated embedding failure: marker {FAILURE_MARKER!r} "
                    "detected in input text"
                )
        return await self._inner.embed_text(texts)


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
# Scenario C — per-version isolation: success / fail / success
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_seed_bridge_per_version_isolation_success_fail_success(
    async_session: AsyncSession,
) -> None:
    """Prove that _ingest_seed_documents isolates each version transactionally.

    Version 1 succeeds (chunks committed).
    Version 2 fails (PermanentEmbeddingProviderError — rollback, zero chunks).
    Version 3 succeeds (chunks committed despite Version 2 failure).
    """

    # 1. Generate explicit UUIDs
    doc1_id = uuid4()
    vid1 = uuid4()
    doc2_id = uuid4()
    vid2 = uuid4()
    doc3_id = uuid4()
    vid3 = uuid4()

    # 2. Create Document + DocumentVersion rows
    doc1 = Document(id=doc1_id, title="Scenario C - V1 Success", description=None)
    ver1 = DocumentVersion(
        id=vid1,
        document_id=doc1_id,
        version_number="1.0",
        status="draft",
        content_hash=None,
        content=NORMAL_CONTENT,
    )

    doc2 = Document(id=doc2_id, title="Scenario C - V2 Fail", description=None)
    ver2 = DocumentVersion(
        id=vid2,
        document_id=doc2_id,
        version_number="1.0",
        status="draft",
        content_hash=None,
        content=FAIL_CONTENT,
    )

    doc3 = Document(id=doc3_id, title="Scenario C - V3 Success", description=None)
    ver3 = DocumentVersion(
        id=vid3,
        document_id=doc3_id,
        version_number="1.0",
        status="draft",
        content_hash=None,
        content=NORMAL_CONTENT,
    )

    # 3. Commit seed rows before invoking bridge
    async_session.add_all([doc1, ver1, doc2, ver2, doc3, ver3])
    await async_session.commit()

    try:
        # 5-7. Content-gated provider via monkeypatch of factory seam
        gated_provider = ContentGatedEmbeddingProvider(dimension=VECTOR_DIMENSION)

        # Use the actual imported function reference for patching
        _patch_target = (
            "app.services.embedding_provider_factory.create_embedding_provider"
        )

        # We need to patch the function used inside _ingest_seed_documents.
        # The bridge imports create_embedding_provider at call time, so we
        # patch the factory module attribute.
        from app.services import embedding_provider_factory as factory_module

        original_factory = factory_module.create_embedding_provider
        factory_module.create_embedding_provider = lambda *args, **kwargs: gated_provider  # noqa: E501

        try:
            # 8. Invoke the actual bridge function
            from app.seed.generator.loader import _ingest_seed_documents

            result = await _ingest_seed_documents([vid1, vid2, vid3])
        finally:
            # Restore original factory
            factory_module.create_embedding_provider = original_factory
        assert result.attempted_count == 3, (
            f"attempted_count: expected 3, got {result.attempted_count}"
        )
        assert result.succeeded_count == 2, (
            f"succeeded_count: expected 2, got {result.succeeded_count}"
        )
        assert result.failed_count == 1, (
            f"failed_count: expected 1, got {result.failed_count}"
        )
        assert result.failed_version_ids == [vid2], (
            f"failed_version_ids: expected [{vid2}], got {result.failed_version_ids}"
        )

        # 10. Query real PostgreSQL for per-version chunk state

        # vid1: must have chunks (> 0)
        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid"
            ),
            {"vid": vid1},
        )
        vid1_chunk_count = row.scalar()
        assert vid1_chunk_count is not None and vid1_chunk_count > 0, (
            f"vid1 chunks: expected > 0, got {vid1_chunk_count}"
        )

        # vid2: must have zero chunks (failed, rolled back)
        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid"
            ),
            {"vid": vid2},
        )
        vid2_chunk_count = row.scalar()
        assert vid2_chunk_count == 0, (
            f"vid2 chunks: expected 0 (failed), got {vid2_chunk_count}"
        )

        # vid3: must have chunks (> 0) — succeeds after vid2 failure
        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid"
            ),
            {"vid": vid3},
        )
        vid3_chunk_count = row.scalar()
        assert vid3_chunk_count is not None and vid3_chunk_count > 0, (
            f"vid3 chunks: expected > 0, got {vid3_chunk_count}"
        )

        # Non-null embedding counts
        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid AND embedding IS NOT NULL"
            ),
            {"vid": vid1},
        )
        vid1_nonnull_embeddings = row.scalar()
        assert vid1_nonnull_embeddings == vid1_chunk_count, (
            f"vid1 non-null embeddings: expected {vid1_chunk_count}, "
            f"got {vid1_nonnull_embeddings}"
        )

        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid AND embedding IS NOT NULL"
            ),
            {"vid": vid3},
        )
        vid3_nonnull_embeddings = row.scalar()
        assert vid3_nonnull_embeddings == vid3_chunk_count, (
            f"vid3 non-null embeddings: expected {vid3_chunk_count}, "
            f"got {vid3_nonnull_embeddings}"
        )

        # Vector dimension check
        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid "
                "AND embedding IS NOT NULL "
                "AND vector_dims(embedding) = :dim"
            ),
            {"vid": vid1, "dim": VECTOR_DIMENSION},
        )
        vid1_correct_dim = row.scalar()
        assert vid1_correct_dim == vid1_chunk_count, (
            f"vid1 vectors with dim {VECTOR_DIMENSION}: "
            f"expected {vid1_chunk_count}, got {vid1_correct_dim}"
        )

        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid "
                "AND embedding IS NOT NULL "
                "AND vector_dims(embedding) = :dim"
            ),
            {"vid": vid3, "dim": VECTOR_DIMENSION},
        )
        vid3_correct_dim = row.scalar()
        assert vid3_correct_dim == vid3_chunk_count, (
            f"vid3 vectors with dim {VECTOR_DIMENSION}: "
            f"expected {vid3_chunk_count}, got {vid3_correct_dim}"
        )

    finally:
        # Rollback current test session if needed
        with suppress(Exception):
            await async_session.rollback()

        # 13. Explicit per-UUID cleanup — no wildcards
        await async_session.execute(
            text(
                "DELETE FROM knowledge_chunks WHERE document_version_id = :vid"
            ),
            {"vid": vid1},
        )
        await async_session.execute(
            text(
                "DELETE FROM knowledge_chunks WHERE document_version_id = :vid"
            ),
            {"vid": vid2},
        )
        await async_session.execute(
            text(
                "DELETE FROM knowledge_chunks WHERE document_version_id = :vid"
            ),
            {"vid": vid3},
        )
        await async_session.execute(
            text("DELETE FROM document_versions WHERE id = :vid"),
            {"vid": vid1},
        )
        await async_session.execute(
            text("DELETE FROM document_versions WHERE id = :vid"),
            {"vid": vid2},
        )
        await async_session.execute(
            text("DELETE FROM document_versions WHERE id = :vid"),
            {"vid": vid3},
        )
        await async_session.execute(
            text("DELETE FROM documents WHERE id = :did"),
            {"did": doc1_id},
        )
        await async_session.execute(
            text("DELETE FROM documents WHERE id = :did"),
            {"did": doc2_id},
        )
        await async_session.execute(
            text("DELETE FROM documents WHERE id = :did"),
            {"did": doc3_id},
        )
        await async_session.commit()

        # 15. Nine post-cleanup zero assertions
        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid"
            ),
            {"vid": vid1},
        )
        assert row.scalar() == 0, "C1: vid1 chunks remain after cleanup"

        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid"
            ),
            {"vid": vid2},
        )
        assert row.scalar() == 0, "C2: vid2 chunks remain after cleanup"

        row = await async_session.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks "
                "WHERE document_version_id = :vid"
            ),
            {"vid": vid3},
        )
        assert row.scalar() == 0, "C3: vid3 chunks remain after cleanup"

        row = await async_session.execute(
            text("SELECT COUNT(*) FROM document_versions WHERE id = :vid"),
            {"vid": vid1},
        )
        assert row.scalar() == 0, "C4: DocumentVersion 1 remains after cleanup"

        row = await async_session.execute(
            text("SELECT COUNT(*) FROM document_versions WHERE id = :vid"),
            {"vid": vid2},
        )
        assert row.scalar() == 0, "C5: DocumentVersion 2 remains after cleanup"

        row = await async_session.execute(
            text("SELECT COUNT(*) FROM document_versions WHERE id = :vid"),
            {"vid": vid3},
        )
        assert row.scalar() == 0, "C6: DocumentVersion 3 remains after cleanup"

        row = await async_session.execute(
            text("SELECT COUNT(*) FROM documents WHERE id = :did"),
            {"did": doc1_id},
        )
        assert row.scalar() == 0, "C7: Document 1 remains after cleanup"

        row = await async_session.execute(
            text("SELECT COUNT(*) FROM documents WHERE id = :did"),
            {"did": doc2_id},
        )
        assert row.scalar() == 0, "C8: Document 2 remains after cleanup"

        row = await async_session.execute(
            text("SELECT COUNT(*) FROM documents WHERE id = :did"),
            {"did": doc3_id},
        )
        assert row.scalar() == 0, "C9: Document 3 remains after cleanup"
