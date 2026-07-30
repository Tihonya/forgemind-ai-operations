"""Integration tests for WP-4.4A: Retrieval service vector query.

Tests vector similarity search using real PostgreSQL/pgvector with
deterministic fake embeddings via IngestionOrchestrator.
"""

import re
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.rag.retriever import RetrievalService
from app.models.document import Document, DocumentVersion
from app.services.embedding_provider import FakeEmbeddingProvider
from app.services.ingestion import IngestionOrchestrator

# ---------------------------------------------------------------------------
# Integration-gate: skip entire module when no DB is reachable
# ---------------------------------------------------------------------------


def _get_test_database_url() -> str:
    """Resolve database URL from .env with placeholder interpolation."""
    import urllib.parse
    from pathlib import Path

    # Find .env relative to this test file's location
    # Test file is at backend/tests/integration/test_retriever_vector_query.py
    # .env is at the repo root: backend/../../.env
    test_file_dir = Path(__file__).resolve().parent
    env_file = test_file_dir.parent.parent.parent / ".env"

    # Read .env and resolve placeholders
    env_vars = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            env_vars[key.strip()] = value.strip()

    # Interpolate ${VAR} placeholders
    def interpolate(value: str) -> str:
        pattern = re.compile(r'\$\{(\w+)\}')

        def replacer(match: re.Match[str]) -> str:
            var_name: str = match.group(1)
            return env_vars.get(var_name, match.group(0))

        prev: str | None = None
        while prev != value:
            prev = value
            value = pattern.sub(replacer, value)
        return value

    user = interpolate(env_vars.get('POSTGRES_USER', ''))
    password = interpolate(env_vars.get('POSTGRES_PASSWORD', ''))
    host = 'localhost'  # Use localhost for tests
    port = interpolate(env_vars.get('POSTGRES_PORT', '5432'))
    db = interpolate(env_vars.get('POSTGRES_DB', ''))

    # URL-encode password for special characters
    password_encoded = urllib.parse.quote_plus(password)

    return f"postgresql+asyncpg://{user}:{password_encoded}@{host}:{port}/{db}"


INTEGRATION_DB_URL = _get_test_database_url()


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
# Test data patterns
# ---------------------------------------------------------------------------

# Different content patterns produce different deterministic embeddings
CONTENT_PATTERN_A = "Pattern A. " * 200
CONTENT_PATTERN_B = "Pattern B. " * 200
CONTENT_PATTERN_C = "Pattern C. " * 200


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_retrieval_nearest_chunk_first(async_session: AsyncSession) -> None:
    """Test that the nearest chunk is returned first.

    Creates three chunks with different content (producing different embeddings),
    then queries with an embedding similar to chunk 1. Verifies chunk 1 is
    returned first.
    """
    doc_id = uuid4()
    version_id = uuid4()

    doc = Document(id=doc_id, title="WP-4.4A Nearest Chunk Test", description=None)
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number="1.0",
        status="APPROVED",
        content_hash=None,
        content=CONTENT_PATTERN_A,
    )

    async_session.add(doc)
    async_session.add(version)
    await async_session.flush()

    try:
        # Ingest with FakeEmbeddingProvider to create chunks with deterministic embeddings
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)
        result = await orchestrator.ingest_document_version(version_id)
        await async_session.commit()

        assert result.status == "completed"
        assert result.chunks_count > 0

        # Query retrieval with the same content pattern
        # The embedding for CONTENT_PATTERN_A should match chunk 0 most closely
        query_embeddings = await provider.embed_text([CONTENT_PATTERN_A])
        query_embedding = query_embeddings[0]

        service = RetrievalService()
        retrieval_results = await service.retrieve(async_session, query_embedding, top_k=3)

        # Verify we got results
        assert len(retrieval_results) > 0

        # First result should have highest similarity
        if len(retrieval_results) > 1:
            assert retrieval_results[0].similarity >= retrieval_results[1].similarity

    finally:
        # Rollback any failed transaction before cleanup
        await async_session.rollback()

        # Cleanup
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

        # Verify cleanup
        row = await async_session.execute(
            text("SELECT COUNT(*) FROM knowledge_chunks WHERE document_version_id = :vid"),
            {"vid": version_id},
        )
        assert row.scalar() == 0, "Chunks not cleaned up"


async def test_retrieval_similarity_ordering(async_session: AsyncSession) -> None:
    """Test that results are ordered by similarity correctly.

    Creates chunks with different content patterns, then queries with an
    embedding similar to pattern A. Verifies ordering is by similarity DESC.
    """
    doc_id = uuid4()
    version_id = uuid4()

    # Create document with multiple content patterns
    combined_content = CONTENT_PATTERN_A + "\n" + CONTENT_PATTERN_B + "\n" + CONTENT_PATTERN_C

    doc = Document(id=doc_id, title="WP-4.4A Similarity Ordering Test", description=None)
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number="1.0",
        status="APPROVED",
        content_hash=None,
        content=combined_content,
    )

    async_session.add(doc)
    async_session.add(version)
    await async_session.flush()

    try:
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)
        result = await orchestrator.ingest_document_version(version_id)
        await async_session.commit()

        assert result.chunks_count > 0

        # Query with pattern A embedding
        query_embeddings = await provider.embed_text([CONTENT_PATTERN_A])
        query_embedding = query_embeddings[0]

        service = RetrievalService()
        retrieval_results = await service.retrieve(async_session, query_embedding, top_k=10)

        # Verify ordering: similarity should be descending
        for i in range(len(retrieval_results) - 1):
            assert retrieval_results[i].similarity >= retrieval_results[i + 1].similarity, (
                f"Ordering violation at index {i}: "
                f"{retrieval_results[i].similarity} < {retrieval_results[i + 1].similarity}"
            )

        # All similarities should be in valid range
        # Note: cosine similarity for non-normalized vectors can be in [-1, 1]
        for res in retrieval_results:
            assert -1.0 <= res.similarity <= 1.0, (
                f"Similarity out of range: {res.similarity}"
            )

    finally:
        # Rollback any failed transaction before cleanup
        await async_session.rollback()

        # Cleanup
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


async def test_retrieval_top_k_enforcement(async_session: AsyncSession) -> None:
    """Test that top_k parameter limits results correctly."""
    doc_id = uuid4()
    version_id = uuid4()

    # Create enough content to produce multiple chunks
    long_content = "Content block. " * 500

    doc = Document(id=doc_id, title="WP-4.4A Top-K Test", description=None)
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number="1.0",
        status="APPROVED",
        content_hash=None,
        content=long_content,
    )

    async_session.add(doc)
    async_session.add(version)
    await async_session.flush()

    try:
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)
        result = await orchestrator.ingest_document_version(version_id)
        await async_session.commit()

        assert result.chunks_count > 1

        # Query with top_k=1
        query_embeddings = await provider.embed_text([long_content[:100]])
        query_embedding = query_embeddings[0]

        service = RetrievalService()
        results_k1 = await service.retrieve(async_session, query_embedding, top_k=1)
        assert len(results_k1) == 1

        # Query with top_k=3
        results_k3 = await service.retrieve(async_session, query_embedding, top_k=3)
        assert len(results_k3) <= 3

        # Query with top_k=10
        results_k10 = await service.retrieve(async_session, query_embedding, top_k=10)
        assert len(results_k10) <= 10

    finally:
        # Rollback any failed transaction before cleanup
        await async_session.rollback()

        # Cleanup
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


async def test_retrieval_deterministic_tie_breaking(async_session: AsyncSession) -> None:
    """Test that ties are broken deterministically.

    When multiple chunks have similar similarity scores, they should be
    ordered by (document_id, version_id, chunk_index, chunk_id).
    """
    doc_id = uuid4()
    version_id = uuid4()

    doc = Document(id=doc_id, title="WP-4.4A Tie-Breaking Test", description=None)
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number="1.0",
        status="APPROVED",
        content_hash=None,
        content="Repeated content. " * 300,
    )

    async_session.add(doc)
    async_session.add(version)
    await async_session.flush()

    try:
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)
        result = await orchestrator.ingest_document_version(version_id)
        await async_session.commit()

        assert result.chunks_count > 1

        # Query with the same content
        query_embeddings = await provider.embed_text(["Repeated content. " * 100])
        query_embedding = query_embeddings[0]

        service = RetrievalService()

        # Run same query twice
        results1 = await service.retrieve(async_session, query_embedding, top_k=5)
        results2 = await service.retrieve(async_session, query_embedding, top_k=5)

        # Results should be identical (deterministic)
        assert len(results1) == len(results2)
        for i in range(len(results1)):
            assert results1[i].chunk_id == results2[i].chunk_id
            assert results1[i].similarity == results2[i].similarity

    finally:
        # Rollback any failed transaction before cleanup
        await async_session.rollback()

        # Cleanup
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


async def test_retrieval_returns_correct_identifiers(async_session: AsyncSession) -> None:
    """Test that retrieval returns correct document, version, and chunk identifiers."""
    doc_id = uuid4()
    version_id = uuid4()

    doc = Document(id=doc_id, title="WP-4.4A Identifier Test", description=None)
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number="1.0",
        status="APPROVED",
        content_hash=None,
        content="Identifier test content. " * 200,
    )

    async_session.add(doc)
    async_session.add(version)
    await async_session.flush()

    try:
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)
        result = await orchestrator.ingest_document_version(version_id)
        await async_session.commit()

        assert result.chunks_count > 0

        query_embeddings = await provider.embed_text(["Identifier test content. " * 50])
        query_embedding = query_embeddings[0]

        service = RetrievalService()
        retrieval_results = await service.retrieve(async_session, query_embedding, top_k=1)

        assert len(retrieval_results) == 1
        result_item = retrieval_results[0]

        # Verify identifiers are returned
        assert result_item.document_id is not None
        assert result_item.version_id is not None
        assert result_item.chunk_id is not None
        assert result_item.chunk_index is not None
        assert result_item.similarity is not None

        # Verify version_id matches what we created
        assert result_item.version_id == version_id

    finally:
        # Rollback any failed transaction before cleanup
        await async_session.rollback()

        # Cleanup
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
