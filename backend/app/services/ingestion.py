"""Ingestion orchestration service.

Coordinates the ingestion pipeline: document version loading,
text chunking, embedding generation, and knowledge chunk storage.
Implements idempotent atomic replacement — re-ingesting the same
document version replaces all existing chunks in a single transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import DocumentVersion
from app.models.knowledge import KnowledgeChunk
from app.services.chunking import ChunkData, chunk_text
from app.services.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderError,
)


@dataclass(frozen=True)
class IngestionResult:
    """Result of a document ingestion pipeline."""

    document_version_id: UUID
    chunks_count: int
    embeddings_count: int
    status: str


class IngestionOrchestrator:
    """Orchestrates the document ingestion pipeline.

    Responsibilities:
    - load a DocumentVersion from the database
    - chunk its content using the chunking service
    - generate embeddings for each chunk via an EmbeddingProvider
    - atomically replace all KnowledgeChunk rows for that version

    The service does NOT commit; the caller owns the transaction.
    A flush is performed after storage so that rows are visible
    within the current transaction.
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._session = session
        self._embedding_provider = embedding_provider

    async def ingest_document_version(
        self,
        document_version_id: UUID,
        *,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> IngestionResult:
        """Run the full ingestion pipeline for a single document version.

        Steps:
        1. Load the DocumentVersion by ID.
        2. Validate that content is present and non-empty.
        3. Chunk the content.
        4. Generate embeddings for all chunk texts.
        5. Delete existing KnowledgeChunk rows for this version.
        6. Insert new KnowledgeChunk rows with embeddings.
        7. Flush (do NOT commit).

        Args:
            document_version_id: The UUID of the document version to ingest.
            chunk_size: Characters per chunk (default 1000).
            chunk_overlap: Overlapping characters between chunks (default 200).

        Returns:
            An IngestionResult with counts and status.

        Raises:
            ValueError: If the document version is not found or has no content.
            EmbeddingProviderError: If embedding generation fails.
                Typed provider errors propagate unchanged.
        """
        # Step 1 — load document version
        doc_version = await self._load_document_version(document_version_id)

        # Step 2 — validate content
        self._validate_content(doc_version)

        # Step 3 — chunk content
        # content is guaranteed non-None by _validate_content
        content = doc_version.content
        assert content is not None
        chunks = self._chunk_content(
            content, chunk_size, chunk_overlap
        )

        # Step 4 — generate embeddings
        embeddings = await self._generate_embeddings(chunks)

        # Step 5 & 6 — atomic replace of knowledge chunks
        await self._store_knowledge_chunks(
            document_version_id, chunks, embeddings
        )

        # Step 7 — flush (caller owns commit)
        await self._session.flush()

        return IngestionResult(
            document_version_id=document_version_id,
            chunks_count=len(chunks),
            embeddings_count=len(embeddings),
            status="completed",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _load_document_version(
        self,
        document_version_id: UUID,
    ) -> DocumentVersion:
        """Load a DocumentVersion by ID.

        Raises:
            ValueError: If the document version is not found.
        """
        result = await self._session.execute(
            select(DocumentVersion)
            .where(DocumentVersion.id == document_version_id)
            .options(selectinload(DocumentVersion.document))
        )
        doc_version = result.scalar_one_or_none()
        if doc_version is None:
            raise ValueError(
                f"DocumentVersion {document_version_id} not found"
            )
        return doc_version

    @staticmethod
    def _validate_content(doc_version: DocumentVersion) -> None:
        """Validate that the document version has content.

        Raises:
            ValueError: If content is None or empty.
        """
        if doc_version.content is None or doc_version.content.strip() == "":
            raise ValueError(
                f"DocumentVersion {doc_version.id} has no content"
            )

    def _chunk_content(
        self,
        content: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[ChunkData]:
        """Split document content into chunks.

        Args:
            content: The raw document text.
            chunk_size: Characters per chunk.
            chunk_overlap: Overlapping characters between chunks.

        Returns:
            A list of ChunkData objects.

        Raises:
            ValueError: If chunking parameters are invalid.
        """
        try:
            return chunk_text(content, chunk_size=chunk_size, overlap=chunk_overlap)
        except ValueError as exc:
            raise ValueError(f"Chunking failed: {exc}") from exc

    async def _generate_embeddings(
        self,
        chunks: list[ChunkData],
    ) -> list[list[float]]:
        """Generate embeddings for a list of chunks.

        Args:
            chunks: ChunkData objects from the chunking step.

        Returns:
            A list of embedding vectors, one per chunk.

        Raises:
            EmbeddingProviderError: If the embedding provider fails.
                Typed provider errors propagate unchanged.
        """
        if not chunks:
            return []

        texts = [chunk.chunk_text for chunk in chunks]
        try:
            return await self._embedding_provider.embed_text(texts)
        except EmbeddingProviderError:
            # Typed provider errors propagate unchanged
            raise
        except Exception as exc:
            raise RuntimeError(f"Embedding generation failed: {exc}") from exc

    async def _store_knowledge_chunks(
        self,
        document_version_id: UUID,
        chunks: list[ChunkData],
        embeddings: list[list[float]],
    ) -> list[KnowledgeChunk]:
        """Atomically replace all knowledge chunks for a document version.

        Deletes existing rows, then inserts new ones. The entire
        operation happens within the caller's transaction.

        Args:
            document_version_id: The document version to store chunks for.
            chunks: ChunkData objects.
            embeddings: Corresponding embedding vectors.

        Returns:
            The list of newly created KnowledgeChunk ORM objects.
        """
        # Delete existing chunks for this document version
        result = await self._session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_version_id == document_version_id
            )
        )
        existing_chunks = result.scalars().all()
        for existing_chunk in existing_chunks:
            await self._session.delete(existing_chunk)

        # Insert new chunks
        knowledge_chunks: list[KnowledgeChunk] = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            kc = KnowledgeChunk(
                document_version_id=document_version_id,
                chunk_index=chunk.chunk_index,
                chunk_text=chunk.chunk_text,
                token_count=chunk.token_count,
                content_hash=chunk.content_hash,
                embedding=embedding,
            )
            self._session.add(kc)
            knowledge_chunks.append(kc)

        return knowledge_chunks
