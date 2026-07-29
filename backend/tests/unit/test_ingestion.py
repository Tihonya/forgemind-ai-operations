"""Unit tests for the ingestion orchestration service.

Tests cover the full ingestion pipeline: document version loading,
chunking, embedding generation, knowledge chunk storage, error
handling, transaction rollback, and idempotent atomic replacement.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.document import DocumentVersion
from app.models.knowledge import KnowledgeChunk
from app.services.embedding_provider import EmbeddingProvider, FakeEmbeddingProvider
from app.services.ingestion import (
    IngestionOrchestrator,
    IngestionResult,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock AsyncSession with correct async/sync method types.

    execute, flush, delete are async (awaitable).
    add is synchronous.
    """
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    # add is synchronous — must NOT be AsyncMock
    session.add = MagicMock()
    return session

@pytest.fixture
def embedding_provider() -> FakeEmbeddingProvider:
    """Create a fake embedding provider for testing."""
    return FakeEmbeddingProvider(dimension=64)

@pytest.fixture
def orchestrator(
    mock_session: MagicMock,
    embedding_provider: FakeEmbeddingProvider,
) -> IngestionOrchestrator:
    """Create an IngestionOrchestrator with mock dependencies."""
    return IngestionOrchestrator(mock_session, embedding_provider)

@pytest.fixture
def doc_version_id() -> UUID:
    """A random document version ID."""
    return uuid4()

@pytest.fixture
def sample_doc_version(doc_version_id: UUID) -> DocumentVersion:
    """Create a sample DocumentVersion with content."""
    dv = MagicMock(spec=DocumentVersion)
    dv.id = doc_version_id
    dv.content = "A" * 2000  # Enough for multiple chunks
    dv.document = MagicMock()
    return dv

@pytest.fixture
def mock_embedding_provider() -> AsyncMock:
    """Create a mock EmbeddingProvider that returns proper-length vectors."""
    provider = AsyncMock(spec=EmbeddingProvider)
    provider.dimension.return_value = 64

    async def _fake_embed(texts: list[str]) -> list[list[float]]:
        return [[0.1] * 64 for _ in texts]

    provider.embed_text.side_effect = _fake_embed
    return provider

# ---------------------------------------------------------------------------
# IngestionResult dataclass
# ---------------------------------------------------------------------------

class TestIngestionResult:
    def test_creation(self, doc_version_id: UUID) -> None:
        result = IngestionResult(
            document_version_id=doc_version_id,
            chunks_count=2,
            embeddings_count=2,
            status="completed",
        )
        assert result.document_version_id == doc_version_id
        assert result.chunks_count == 2
        assert result.embeddings_count == 2
        assert result.status == "completed"

    def test_is_frozen(self) -> None:
        result = IngestionResult(
            document_version_id=uuid4(),
            chunks_count=1,
            embeddings_count=1,
            status="completed",
        )
        with pytest.raises(FrozenInstanceError):
            result.chunks_count = 5  # type: ignore

# ---------------------------------------------------------------------------
# Successful ingestion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestSuccessfulIngestion:
    async def test_ingest_returns_result(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        sample_doc_version: DocumentVersion,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Full successful ingestion pipeline."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_doc_version
        mock_session.execute.return_value = mock_result

        result = await orchestrator.ingest_document_version(doc_version_id)

        assert isinstance(result, IngestionResult)
        assert result.document_version_id == doc_version_id
        assert result.status == "completed"
        assert result.chunks_count > 0
        assert result.embeddings_count == result.chunks_count

    async def test_ingest_result_counts_match(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        sample_doc_version: DocumentVersion,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Chunks count and embeddings count match the actual chunks."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_doc_version
        mock_session.execute.return_value = mock_result

        result = await orchestrator.ingest_document_version(doc_version_id)

        assert result.chunks_count == result.embeddings_count

    async def test_flush_is_called(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        sample_doc_version: DocumentVersion,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """flush() is called after storage."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_doc_version
        mock_session.execute.return_value = mock_result

        await orchestrator.ingest_document_version(doc_version_id)

        mock_session.flush.assert_called_once()

    async def test_commit_is_not_called(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        sample_doc_version: DocumentVersion,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Service does NOT call session.commit()."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_doc_version
        mock_session.execute.return_value = mock_result

        await orchestrator.ingest_document_version(doc_version_id)

        mock_session.commit.assert_not_called()

# ---------------------------------------------------------------------------
# Document version loading and validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDocumentVersionValidation:
    async def test_missing_document_version_raises(
        self,
        orchestrator: IngestionOrchestrator,
        mock_session: MagicMock,
        doc_version_id: UUID,
    ) -> None:
        """ValueError when document version is not found."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="not found"):
            await orchestrator.ingest_document_version(doc_version_id)

    async def test_none_content_raises(
        self,
        orchestrator: IngestionOrchestrator,
        mock_session: MagicMock,
        doc_version_id: UUID,
    ) -> None:
        """ValueError when content is None."""
        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="no content"):
            await orchestrator.ingest_document_version(doc_version_id)

    async def test_empty_content_raises(
        self,
        orchestrator: IngestionOrchestrator,
        mock_session: MagicMock,
        doc_version_id: UUID,
    ) -> None:
        """ValueError when content is empty string."""
        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = ""

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="no content"):
            await orchestrator.ingest_document_version(doc_version_id)

    async def test_whitespace_only_content_raises(
        self,
        orchestrator: IngestionOrchestrator,
        mock_session: MagicMock,
        doc_version_id: UUID,
    ) -> None:
        """ValueError when content is only whitespace."""
        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "   "

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        with pytest.raises(ValueError, match="no content"):
            await orchestrator.ingest_document_version(doc_version_id)

# ---------------------------------------------------------------------------
# Chunking integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestChunkingIntegration:
    async def test_chunking_called_with_correct_params(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        sample_doc_version: DocumentVersion,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """chunk_text is called with correct chunk_size and overlap."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_doc_version
        mock_session.execute.return_value = mock_result

        with patch(
            "app.services.ingestion.chunk_text",
            return_value=[],
        ) as mock_chunk:
            await orchestrator.ingest_document_version(
                doc_version_id,
                chunk_size=500,
                chunk_overlap=100,
            )

            mock_chunk.assert_called_once_with(
                sample_doc_version.content,
                chunk_size=500,
                overlap=100,
            )

    async def test_configurable_chunk_size_and_overlap(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Custom chunk_size and chunk_overlap are respected."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )
        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 5000
        dv.document = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        result = await orchestrator.ingest_document_version(
            doc_version_id,
            chunk_size=1000,
            chunk_overlap=100,
        )

        assert result.chunks_count > 0
        assert result.status == "completed"

    async def test_chunking_error_propagated_with_context(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Chunking errors are wrapped with context."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )
        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        with (
            patch(
                "app.services.ingestion.chunk_text",
                side_effect=ValueError("overlap >= chunk_size"),
            ),
            pytest.raises(ValueError, match="Chunking failed"),
        ):
            await orchestrator.ingest_document_version(
                doc_version_id,
                chunk_size=500,
                chunk_overlap=600,
            )

# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEmbeddingGeneration:
    async def test_embeddings_generated_for_all_chunks(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """All chunk texts are passed to the embedding provider."""
        from app.services.chunking import chunk_text as real_chunk_text

        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = dv

        chunks_result = MagicMock()
        chunks_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [dv_result, chunks_result]

        chunks = real_chunk_text(dv.content, 1000, 200)
        chunk_texts = [c.chunk_text for c in chunks]

        await orchestrator.ingest_document_version(doc_version_id)

        mock_embedding_provider.embed_text.assert_called_once()
        call_texts = mock_embedding_provider.embed_text.call_args[0][0]
        assert len(call_texts) == len(chunk_texts)

    async def test_embedding_failure_raises_runtime_error(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Embedding provider failures propagate as RuntimeError."""
        mock_embedding_provider.embed_text = AsyncMock(
            side_effect=RuntimeError("API down")
        )
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        with pytest.raises(RuntimeError, match="Embedding generation failed"):
            await orchestrator.ingest_document_version(doc_version_id)

    async def test_embedding_failure_preserves_cause(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Original exception is preserved as __cause__."""
        original = RuntimeError("upstream failure")
        mock_embedding_provider.embed_text = AsyncMock(side_effect=original)

        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        with pytest.raises(RuntimeError) as exc_info:
            await orchestrator.ingest_document_version(doc_version_id)

        assert exc_info.value.__cause__ is original

# ---------------------------------------------------------------------------
# Typed error propagation through orchestrator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTypedErrorPropagation:
    """Verify that typed EmbeddingProviderError subclasses propagate
    unchanged through IngestionOrchestrator._generate_embeddings."""

    async def test_transient_error_propagates_unchanged(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """TransientEmbeddingProviderError propagates without wrapping."""
        from app.services.embedding_provider import (
            TransientEmbeddingProviderError,
        )

        original = TransientEmbeddingProviderError("network failure")
        mock_embedding_provider.embed_text = AsyncMock(side_effect=original)

        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        with pytest.raises(TransientEmbeddingProviderError) as exc_info:
            await orchestrator.ingest_document_version(doc_version_id)

        # Same instance — no wrapping
        assert exc_info.value is original

    async def test_permanent_error_propagates_unchanged(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """PermanentEmbeddingProviderError propagates without wrapping."""
        from app.services.embedding_provider import (
            PermanentEmbeddingProviderError,
        )

        original = PermanentEmbeddingProviderError("invalid model")
        mock_embedding_provider.embed_text = AsyncMock(side_effect=original)

        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        with pytest.raises(PermanentEmbeddingProviderError) as exc_info:
            await orchestrator.ingest_document_version(doc_version_id)

        assert exc_info.value is original

    async def test_configuration_error_propagates_unchanged(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """EmbeddingProviderConfigurationError propagates without wrapping."""
        from app.services.embedding_provider import (
            EmbeddingProviderConfigurationError,
        )

        original = EmbeddingProviderConfigurationError("missing key")
        mock_embedding_provider.embed_text = AsyncMock(side_effect=original)

        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        with pytest.raises(EmbeddingProviderConfigurationError) as exc_info:
            await orchestrator.ingest_document_version(doc_version_id)

        assert exc_info.value is original

# ---------------------------------------------------------------------------
# Knowledge chunk storage and idempotent replacement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestKnowledgeChunkStorage:
    async def test_existing_chunks_deleted_before_insert(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Existing KnowledgeChunk rows are deleted before new ones."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        existing_chunk = MagicMock(spec=KnowledgeChunk)

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = MagicMock(
            spec=DocumentVersion,
            id=doc_version_id,
            content="A" * 2000,
        )

        chunks_result = MagicMock()
        chunks_result.scalars.return_value.all.return_value = [existing_chunk]

        mock_session.execute.side_effect = [
            dv_result, chunks_result,
        ]

        await orchestrator.ingest_document_version(doc_version_id)

        mock_session.delete.assert_called_once_with(existing_chunk)

    async def test_new_chunks_stored_with_correct_fields(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """KnowledgeChunk rows have correct fields from chunking."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = dv

        chunks_result = MagicMock()
        chunks_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [dv_result, chunks_result]

        await orchestrator.ingest_document_version(doc_version_id)

        add_calls = mock_session.add.call_args_list
        assert len(add_calls) > 0

        first_chunk = add_calls[0][0][0]
        assert first_chunk.document_version_id == doc_version_id
        assert first_chunk.chunk_index == 0
        assert first_chunk.embedding is not None

    async def test_knowledge_chunks_stored_with_embeddings(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Each KnowledgeChunk has a valid embedding vector."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = dv

        chunks_result = MagicMock()
        chunks_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [dv_result, chunks_result]

        await orchestrator.ingest_document_version(doc_version_id)

        add_calls = mock_session.add.call_args_list
        for call_obj in add_calls:
            kc = call_obj[0][0]
            assert kc.embedding is not None

    async def test_no_existing_chunks_no_delete(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """When no existing chunks, no delete is called."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = dv

        chunks_result = MagicMock()
        chunks_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [dv_result, chunks_result]

        await orchestrator.ingest_document_version(doc_version_id)

        mock_session.delete.assert_not_called()

# ---------------------------------------------------------------------------
# Transaction rollback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTransactionRollback:
    async def test_rollback_on_embedding_failure(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """No chunks are stored when embedding fails (no commit)."""
        mock_embedding_provider.embed_text = AsyncMock(
            side_effect=RuntimeError("API down")
        )
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = mock_result

        with pytest.raises(RuntimeError):
            await orchestrator.ingest_document_version(doc_version_id)

        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_called()

    async def test_rollback_on_storage_failure(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Storage failure does not commit."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "A" * 2000
        dv.document = MagicMock()

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = dv

        chunks_result = MagicMock()
        chunks_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [
            dv_result,
            chunks_result,  # only 2 execute calls now
        ]
        mock_session.flush.side_effect = IntegrityError("", None, Exception())

        with pytest.raises(IntegrityError):
            await orchestrator.ingest_document_version(doc_version_id)

        mock_session.commit.assert_not_called()

# ---------------------------------------------------------------------------
# FakeEmbeddingProvider integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestFakeEmbeddingProviderIntegration:
    async def test_full_pipeline_with_fake_provider(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
    ) -> None:
        """End-to-end ingestion with FakeEmbeddingProvider."""
        provider = FakeEmbeddingProvider(dimension=64)
        orchestrator = IngestionOrchestrator(mock_session, provider)

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "Integration test content for fake provider." * 50
        dv.document = MagicMock()

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = dv

        chunks_result = MagicMock()
        chunks_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [dv_result, chunks_result]

        result = await orchestrator.ingest_document_version(doc_version_id)

        assert result.chunks_count > 0
        assert result.embeddings_count == result.chunks_count
        assert result.status == "completed"

    async def test_fake_provider_dimension_consistency(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
    ) -> None:
        """Embeddings from FakeEmbeddingProvider match configured dimension."""
        provider = FakeEmbeddingProvider(dimension=128)
        orchestrator = IngestionOrchestrator(mock_session, provider)

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "Dimension check content." * 50
        dv.document = MagicMock()

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = dv

        chunks_result = MagicMock()
        chunks_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [dv_result, chunks_result]

        await orchestrator.ingest_document_version(doc_version_id)

        for call_obj in mock_session.add.call_args_list:
            kc = call_obj[0][0]
            assert len(kc.embedding) == 128

# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestIdempotency:
    async def test_re_ingestion_replaces_chunks(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Re-ingesting the same version replaces old chunks."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "Re-ingestion test content." * 50
        dv.document = MagicMock()

        existing_chunk = MagicMock(spec=KnowledgeChunk)

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = dv

        chunks_result = MagicMock()
        chunks_result.scalars.return_value.all.return_value = [existing_chunk]

        mock_session.execute.side_effect = [
            dv_result, chunks_result,
        ]

        result = await orchestrator.ingest_document_version(doc_version_id)

        assert result.status == "completed"
        mock_session.delete.assert_called_once_with(existing_chunk)
        assert mock_session.add.call_count > 0

# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestEdgeCases:
    async def test_single_chunk_document(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Document shorter than chunk_size produces one chunk."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = "Short document"
        dv.document = MagicMock()

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = dv

        chunks_result = MagicMock()
        chunks_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [dv_result, chunks_result]

        result = await orchestrator.ingest_document_version(doc_version_id)

        assert result.chunks_count == 1
        assert result.embeddings_count == 1

    async def test_empty_content_raises_before_chunking(
        self,
        mock_session: MagicMock,
        doc_version_id: UUID,
        mock_embedding_provider: AsyncMock,
    ) -> None:
        """Empty content raises ValueError before chunking is attempted."""
        orchestrator = IngestionOrchestrator(
            mock_session, mock_embedding_provider
        )

        dv = MagicMock(spec=DocumentVersion)
        dv.id = doc_version_id
        dv.content = ""
        dv.document = MagicMock()

        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = dv
        mock_session.execute.return_value = dv_result

        with pytest.raises(ValueError, match="no content"):
            await orchestrator.ingest_document_version(doc_version_id)
