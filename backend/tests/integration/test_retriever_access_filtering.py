"""Integration tests for WP-4.4B: Document access filtering.

Tests that vector retrieval returns only chunks from documents that the
requesting user is authorized to access via document_permissions.

Access filtering is enforced inside the PostgreSQL query before rows are
returned or materialized.
"""

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.rag.retriever import RetrievalService
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.user import Role
from app.services.embedding_provider import FakeEmbeddingProvider
from app.services.ingestion import IngestionOrchestrator
from tests._db_url import get_test_database_url

# ---------------------------------------------------------------------------
# Integration-gate: skip entire module when no DB is reachable
# ---------------------------------------------------------------------------


INTEGRATION_DB_URL = get_test_database_url()


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
ALLOWED_CONTENT = "This is allowed content for testing access control. " * 200
RESTRICTED_CONTENT = "This is restricted content that should be filtered out. " * 200


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


async def _create_role(
    session: AsyncSession,
    role_code: str,
) -> Role:
    """Create a Role for testing."""
    role_id = uuid4()
    role = Role(id=role_id, code=role_code, name=f"Test Role {role_code}")
    session.add(role)
    await session.flush()
    return role


async def _create_document_with_permission(
    session: AsyncSession,
    title: str,
    content: str,
    role_id: UUID,
    status: str = "APPROVED",
) -> tuple[UUID, UUID]:
    """Create a document, version, and permission record.

    Returns (doc_id, version_id).
    """
    doc_id = uuid4()
    version_id = uuid4()

    doc = Document(id=doc_id, title=title, description=None)
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number="1.0",
        status=status,
        content_hash=None,
        content=content,
    )

    session.add(doc)
    session.add(version)
    await session.flush()

    # Create permission
    perm = DocumentPermission(
        id=uuid4(),
        document_id=doc_id,
        role_id=role_id,
    )
    session.add(perm)
    await session.flush()

    return doc_id, version_id


async def _cleanup_test_data(
    session: AsyncSession,
    doc_ids: list[UUID],
    version_ids: list[UUID],
    role_ids: list[UUID],
) -> None:
    """Clean up all test-owned rows."""
    await session.rollback()

    for vid in version_ids:
        await session.execute(
            text("DELETE FROM knowledge_chunks WHERE document_version_id = :vid"),
            {"vid": vid},
        )
        await session.execute(
            text("DELETE FROM document_versions WHERE id = :vid"),
            {"vid": vid},
        )

    for did in doc_ids:
        await session.execute(
            text("DELETE FROM document_permissions WHERE document_id = :did"),
            {"did": did},
        )
        await session.execute(
            text("DELETE FROM documents WHERE id = :did"),
            {"did": did},
        )

    for rid in role_ids:
        await session.execute(
            text("DELETE FROM user_roles WHERE role_id = :rid"),
            {"rid": rid},
        )
        await session.execute(
            text("DELETE FROM roles WHERE id = :rid"),
            {"rid": rid},
        )

    await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_user_with_permission_retrieves_chunk(async_session: AsyncSession) -> None:
    """Test that a user with permission retrieves the allowed document chunk."""
    allowed_role = await _create_role(async_session, "WP44B_ALLOWED_ROLE")

    doc_id, version_id = await _create_document_with_permission(
        async_session,
        "WP-4.4B Allowed Document",
        ALLOWED_CONTENT,
        allowed_role.id,
    )

    try:
        # Ingest to create chunks
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)
        result = await orchestrator.ingest_document_version(version_id)
        await async_session.commit()

        assert result.chunks_count > 0

        # Query with the allowed role
        query_embeddings = await provider.embed_text([ALLOWED_CONTENT])
        query_embedding = query_embeddings[0]

        service = RetrievalService()
        retrieval_results = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={allowed_role.id},
            top_k=10,
        )

        # Should get results because user has permission
        assert len(retrieval_results) > 0

        # All results should be from the allowed document
        for res in retrieval_results:
            assert res.document_id == doc_id

    finally:
        await _cleanup_test_data(
            async_session, [doc_id], [version_id], [allowed_role.id]
        )


async def test_user_without_permission_receives_no_chunks(
    async_session: AsyncSession,
) -> None:
    """Test that a user without permission receives no chunks from that document."""
    allowed_role = await _create_role(async_session, "WP44B_ALLOWED_ROLE_2")
    other_role = await _create_role(async_session, "WP44B_OTHER_ROLE")

    # Create document with permission only for allowed_role
    doc_id, version_id = await _create_document_with_permission(
        async_session,
        "WP-4.4B Restricted Document",
        RESTRICTED_CONTENT,
        allowed_role.id,
    )

    try:
        # Ingest to create chunks
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)
        result = await orchestrator.ingest_document_version(version_id)
        await async_session.commit()

        assert result.chunks_count > 0

        # Query with OTHER role (no permission)
        query_embeddings = await provider.embed_text([RESTRICTED_CONTENT])
        query_embedding = query_embeddings[0]

        service = RetrievalService()
        retrieval_results = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={other_role.id},
            top_k=10,
        )

        # Should get NO results because user lacks permission
        assert len(retrieval_results) == 0

    finally:
        await _cleanup_test_data(
            async_session,
            [doc_id],
            [version_id],
            [allowed_role.id, other_role.id],
        )


async def test_mixed_permission_query_returns_only_allowed(
    async_session: AsyncSession,
) -> None:
    """Test that a query matching both allowed and restricted documents returns only allowed."""
    allowed_role = await _create_role(async_session, "WP44B_MIXED_ALLOWED")
    other_role = await _create_role(async_session, "WP44B_MIXED_OTHER")

    # Create allowed document
    allowed_doc_id, allowed_version_id = await _create_document_with_permission(
        async_session,
        "WP-4.4B Allowed Doc",
        ALLOWED_CONTENT,
        allowed_role.id,
    )

    # Create restricted document (permission for other_role, not allowed_role)
    restricted_doc_id, restricted_version_id = await _create_document_with_permission(
        async_session,
        "WP-4.4B Restricted Doc",
        RESTRICTED_CONTENT,
        other_role.id,
    )

    try:
        # Ingest both documents
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)

        result1 = await orchestrator.ingest_document_version(allowed_version_id)
        await async_session.commit()
        assert result1.chunks_count > 0

        result2 = await orchestrator.ingest_document_version(restricted_version_id)
        await async_session.commit()
        assert result2.chunks_count > 0

        # Query with allowed_role
        query_embeddings = await provider.embed_text([ALLOWED_CONTENT + " " + RESTRICTED_CONTENT])
        query_embedding = query_embeddings[0]

        service = RetrievalService()
        retrieval_results = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={allowed_role.id},
            top_k=20,
        )

        # Should get results only from allowed document
        assert len(retrieval_results) > 0

        for res in retrieval_results:
            assert res.document_id == allowed_doc_id
            assert res.document_id != restricted_doc_id

    finally:
        await _cleanup_test_data(
            async_session,
            [allowed_doc_id, restricted_doc_id],
            [allowed_version_id, restricted_version_id],
            [allowed_role.id, other_role.id],
        )


async def test_document_without_permission_is_inaccessible(
    async_session: AsyncSession,
) -> None:
    """Test that a document without any permission record is inaccessible."""
    allowed_role = await _create_role(async_session, "WP44B_NO_PERM_ROLE")

    # Create document WITHOUT permission record
    doc_id = uuid4()
    version_id = uuid4()

    doc = Document(id=doc_id, title="WP-4.4B No Permission Doc", description=None)
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number="1.0",
        status="APPROVED",
        content_hash=None,
        content=ALLOWED_CONTENT,
    )

    async_session.add(doc)
    async_session.add(version)
    await async_session.flush()

    try:
        # Ingest to create chunks
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)
        result = await orchestrator.ingest_document_version(version_id)
        await async_session.commit()

        assert result.chunks_count > 0

        # Query with any role
        query_embeddings = await provider.embed_text([ALLOWED_CONTENT])
        query_embedding = query_embeddings[0]

        service = RetrievalService()
        retrieval_results = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={allowed_role.id},
            top_k=10,
        )

        # Should get NO results because document has no permission record
        assert len(retrieval_results) == 0

    finally:
        await _cleanup_test_data(
            async_session, [doc_id], [version_id], [allowed_role.id]
        )


async def test_permissions_are_role_specific(async_session: AsyncSession) -> None:
    """Test that permissions for one user do not grant access to another user."""
    role_a = await _create_role(async_session, "WP44B_ROLE_A")
    role_b = await _create_role(async_session, "WP44B_ROLE_B")

    # Create document with permission for role_a only
    doc_id, version_id = await _create_document_with_permission(
        async_session,
        "WP-4.4B Role-Specific Doc",
        ALLOWED_CONTENT,
        role_a.id,
    )

    try:
        # Ingest
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)
        result = await orchestrator.ingest_document_version(version_id)
        await async_session.commit()

        assert result.chunks_count > 0

        query_embeddings = await provider.embed_text([ALLOWED_CONTENT])
        query_embedding = query_embeddings[0]

        service = RetrievalService()

        # Query with role_a (has permission)
        results_a = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={role_a.id},
            top_k=10,
        )
        assert len(results_a) > 0

        # Query with role_b (no permission)
        results_b = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={role_b.id},
            top_k=10,
        )
        assert len(results_b) == 0

    finally:
        await _cleanup_test_data(
            async_session, [doc_id], [version_id], [role_a.id, role_b.id]
        )


async def test_top_k_applied_after_permission_filtering(
    async_session: AsyncSession,
) -> None:
    """Test that top_k is applied after permission filtering."""
    allowed_role = await _create_role(async_session, "WP44B_TOPK_ROLE")
    other_role = await _create_role(async_session, "WP44B_TOPK_OTHER")

    # Create 3 allowed documents
    allowed_ids = []
    version_ids = []
    for i in range(3):
        doc_id, version_id = await _create_document_with_permission(
            async_session,
            f"WP-4.4B Allowed Doc {i}",
            ALLOWED_CONTENT,
            allowed_role.id,
        )
        allowed_ids.append(doc_id)
        version_ids.append(version_id)

    # Create 2 restricted documents (permission for other_role)
    restricted_ids = []
    for i in range(2):
        doc_id, version_id = await _create_document_with_permission(
            async_session,
            f"WP-4.4B Restricted Doc {i}",
            RESTRICTED_CONTENT,
            other_role.id,
        )
        restricted_ids.append(doc_id)
        version_ids.append(version_id)

    try:
        # Ingest all documents
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)

        for vid in version_ids:
            result = await orchestrator.ingest_document_version(vid)
            await async_session.commit()
            assert result.chunks_count > 0

        # Query with allowed_role
        query_embeddings = await provider.embed_text([ALLOWED_CONTENT + " " + RESTRICTED_CONTENT])
        query_embedding = query_embeddings[0]

        service = RetrievalService()

        # Query with top_k=2
        results = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={allowed_role.id},
            top_k=2,
        )

        # Should get at most 2 results (top_k enforced)
        assert len(results) <= 2

        # All results should be from allowed documents only
        for res in results:
            assert res.document_id in allowed_ids
            assert res.document_id not in restricted_ids

    finally:
        await _cleanup_test_data(
            async_session,
            allowed_ids + restricted_ids,
            version_ids,
            [allowed_role.id, other_role.id],
        )


async def test_deterministic_ordering_among_authorized_results(
    async_session: AsyncSession,
) -> None:
    """Test that deterministic ordering remains stable among authorized results."""
    allowed_role = await _create_role(async_session, "WP44B_DETERMINISTIC_ROLE")

    # Create 2 allowed documents
    doc_id_1, version_id_1 = await _create_document_with_permission(
        async_session,
        "WP-4.4B Deterministic Doc 1",
        ALLOWED_CONTENT,
        allowed_role.id,
    )

    doc_id_2, version_id_2 = await _create_document_with_permission(
        async_session,
        "WP-4.4B Deterministic Doc 2",
        ALLOWED_CONTENT,
        allowed_role.id,
    )

    try:
        # Ingest
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)

        result1 = await orchestrator.ingest_document_version(version_id_1)
        await async_session.commit()
        assert result1.chunks_count > 0

        result2 = await orchestrator.ingest_document_version(version_id_2)
        await async_session.commit()
        assert result2.chunks_count > 0

        query_embeddings = await provider.embed_text([ALLOWED_CONTENT])
        query_embedding = query_embeddings[0]

        service = RetrievalService()

        # Run same query twice
        results_1 = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={allowed_role.id},
            top_k=10,
        )

        results_2 = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={allowed_role.id},
            top_k=10,
        )

        # Results should be identical (deterministic)
        assert len(results_1) == len(results_2)
        for i in range(len(results_1)):
            assert results_1[i].chunk_id == results_2[i].chunk_id
            assert results_1[i].similarity == results_2[i].similarity
            assert results_1[i].document_id == results_2[i].document_id

    finally:
        await _cleanup_test_data(
            async_session,
            [doc_id_1, doc_id_2],
            [version_id_1, version_id_2],
            [allowed_role.id],
        )


async def test_restricted_chunks_never_appear_in_results(
    async_session: AsyncSession,
) -> None:
    """Test that restricted chunk identifiers and text never appear in returned results."""
    allowed_role = await _create_role(async_session, "WP44B_NO_LEAK_ROLE")
    other_role = await _create_role(async_session, "WP44B_NO_LEAK_OTHER")

    # Create allowed document
    allowed_doc_id, allowed_version_id = await _create_document_with_permission(
        async_session,
        "WP-4.4B Allowed Doc",
        ALLOWED_CONTENT,
        allowed_role.id,
    )

    # Create restricted document
    restricted_doc_id, restricted_version_id = await _create_document_with_permission(
        async_session,
        "WP-4.4B Restricted Doc",
        RESTRICTED_CONTENT,
        other_role.id,
    )

    try:
        # Ingest both
        provider = FakeEmbeddingProvider(dimension=1536)
        orchestrator = IngestionOrchestrator(async_session, provider)

        await orchestrator.ingest_document_version(allowed_version_id)
        await async_session.commit()

        await orchestrator.ingest_document_version(restricted_version_id)
        await async_session.commit()

        # Get restricted chunk IDs before querying
        result = await async_session.execute(
            text(
                "SELECT id, chunk_text FROM knowledge_chunks "
                "WHERE document_version_id = :vid"
            ),
            {"vid": restricted_version_id},
        )
        restricted_chunks = result.fetchall()
        restricted_chunk_ids = {row.id for row in restricted_chunks}
        restricted_texts = {row.chunk_text for row in restricted_chunks}

        # Query with allowed_role
        query_embeddings = await provider.embed_text([ALLOWED_CONTENT + " " + RESTRICTED_CONTENT])
        query_embedding = query_embeddings[0]

        service = RetrievalService()
        retrieval_results = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={allowed_role.id},
            top_k=50,
        )

        # Verify no restricted chunk appears in results
        returned_chunk_ids = {res.chunk_id for res in retrieval_results}
        returned_texts = {res.chunk_text for res in retrieval_results}

        # No overlap
        assert len(returned_chunk_ids & restricted_chunk_ids) == 0
        assert len(returned_texts & restricted_texts) == 0

        # All returned chunks are from allowed document
        for res in retrieval_results:
            assert res.document_id == allowed_doc_id

    finally:
        await _cleanup_test_data(
            async_session,
            [allowed_doc_id, restricted_doc_id],
            [allowed_version_id, restricted_version_id],
            [allowed_role.id, other_role.id],
        )


async def test_cleanup_verification(async_session: AsyncSession) -> None:
    """Test that all test-owned permissions, chunks, versions and documents are removed."""
    # This test verifies the cleanup helper works correctly
    role = await _create_role(async_session, "WP44B_CLEANUP_TEST")
    role_id = role.id  # Capture ID before session operations

    doc_id, version_id = await _create_document_with_permission(
        async_session,
        "WP-4.4B Cleanup Test Doc",
        ALLOWED_CONTENT,
        role_id,
    )

    # Ingest to create chunks
    provider = FakeEmbeddingProvider(dimension=1536)
    orchestrator = IngestionOrchestrator(async_session, provider)
    await orchestrator.ingest_document_version(version_id)
    await async_session.commit()

    # Verify data exists before cleanup
    result = await async_session.execute(
        text("SELECT COUNT(*) FROM knowledge_chunks WHERE document_version_id = :vid"),
        {"vid": version_id},
    )
    count = result.scalar()
    assert count is not None and count > 0, "Chunks should exist before cleanup"

    # Perform cleanup
    await _cleanup_test_data(async_session, [doc_id], [version_id], [role_id])

    # Verify all data is removed
    result = await async_session.execute(
        text("SELECT COUNT(*) FROM knowledge_chunks WHERE document_version_id = :vid"),
        {"vid": version_id},
    )
    assert result.scalar() == 0, "Chunks not cleaned up"

    result = await async_session.execute(
        text("SELECT COUNT(*) FROM document_permissions WHERE document_id = :did"),
        {"did": doc_id},
    )
    assert result.scalar() == 0, "Permissions not cleaned up"

    result = await async_session.execute(
        text("SELECT COUNT(*) FROM documents WHERE id = :did"),
        {"did": doc_id},
    )
    assert result.scalar() == 0, "Documents not cleaned up"

    result = await async_session.execute(
        text("SELECT COUNT(*) FROM roles WHERE id = :rid"),
        {"rid": role_id},
    )
    assert result.scalar() == 0, "Roles not cleaned up"
