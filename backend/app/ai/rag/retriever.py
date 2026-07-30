"""Retrieval service for RAG vector search (WP-4.4A).

Implements the retrieval domain contract: cosine similarity search over
knowledge chunks using pgvector, with deterministic ordering and strict
input validation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Constants
EXPECTED_EMBEDDING_DIMENSION = 1536
TOP_K_MIN = 1
TOP_K_DEFAULT = 10
TOP_K_MAX = 100


@dataclass(frozen=True)
class RetrievalResult:
    """Immutable retrieval result containing document and chunk identifiers.

    Attributes:
        document_id: UUID of the parent document.
        version_id: UUID of the document version.
        chunk_id: UUID of the knowledge chunk.
        chunk_index: Zero-based index of the chunk within the version.
        chunk_text: The text content of the chunk.
        metadata: Optional JSON metadata from the chunk.
        similarity: Cosine similarity score (1 - cosine_distance).
    """

    document_id: UUID
    version_id: UUID
    chunk_id: UUID
    chunk_index: int
    chunk_text: str
    metadata: dict[str, Any] | None
    similarity: float


class RetrievalValidationError(ValueError):
    """Raised when retrieval input validation fails."""


class RetrievalService:
    """Async retrieval service for vector similarity search.

    Uses PostgreSQL/pgvector for cosine similarity computation.
    Does not apply document permission filtering (deferred to WP-4.4B).
    """

    async def retrieve(
        self,
        session: AsyncSession,
        query_embedding: list[float],
        top_k: int = TOP_K_DEFAULT,
    ) -> list[RetrievalResult]:
        """Execute vector similarity search over knowledge chunks.

        Args:
            session: Async SQLAlchemy session.
            query_embedding: Query vector (must match EXPECTED_EMBEDDING_DIMENSION).
            top_k: Maximum number of results (1..100, default 10).

        Returns:
            List of RetrievalResult ordered by similarity DESC, then deterministic
            tie-breakers.

        Raises:
            RetrievalValidationError: If input validation fails.
        """
        # Validate top_k
        if not isinstance(top_k, int) or isinstance(top_k, bool):
            raise RetrievalValidationError(
                f"top_k must be an integer, got {type(top_k).__name__}"
            )
        if top_k < TOP_K_MIN:
            raise RetrievalValidationError(
                f"top_k must be at least {TOP_K_MIN}, got {top_k}"
            )
        if top_k > TOP_K_MAX:
            raise RetrievalValidationError(
                f"top_k must be at most {TOP_K_MAX}, got {top_k}"
            )

        # Validate query_embedding
        if not isinstance(query_embedding, list):
            raise RetrievalValidationError(
                f"query_embedding must be a list, got {type(query_embedding).__name__}"
            )
        if len(query_embedding) != EXPECTED_EMBEDDING_DIMENSION:
            raise RetrievalValidationError(
                f"query_embedding must have dimension {EXPECTED_EMBEDDING_DIMENSION}, "
                f"got {len(query_embedding)}"
            )

        # Validate all values are numeric and finite
        for i, v in enumerate(query_embedding):
            if not isinstance(v, (int, float)):
                raise RetrievalValidationError(
                    f"query_embedding[{i}] must be numeric, got {type(v).__name__}"
                )
            if not math.isfinite(v):
                raise RetrievalValidationError(
                    f"query_embedding[{i}] must be finite, got {v}"
                )

        # Check for zero-norm embedding
        norm_squared = sum(v * v for v in query_embedding)
        if norm_squared == 0.0:
            raise RetrievalValidationError(
                "query_embedding must not be zero-norm (cosine distance undefined)"
            )

        # Execute vector similarity query using pgvector
        # Convert list to proper format for pgvector
        vector_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        query = text(
            """
            SELECT
                kc.id AS chunk_id,
                kc.chunk_index,
                kc.chunk_text,
                kc.metadata,
                dv.id AS version_id,
                d.id AS document_id,
                1 - (kc.embedding <=> CAST(:query_vector AS vector)) AS similarity
            FROM knowledge_chunks kc
            JOIN document_versions dv ON dv.id = kc.document_version_id
            JOIN documents d ON d.id = dv.document_id
            WHERE kc.embedding IS NOT NULL
              AND dv.status = 'APPROVED'
            ORDER BY
                (kc.embedding <=> CAST(:query_vector AS vector)) ASC,
                d.id ASC,
                dv.id ASC,
                kc.chunk_index ASC,
                kc.id ASC
            LIMIT :top_k
            """
        )

        result = await session.execute(
            query, {"query_vector": vector_str, "top_k": top_k}
        )
        rows = result.fetchall()

        # Map rows to RetrievalResult
        results = []
        for row in rows:
            results.append(
                RetrievalResult(
                    document_id=row.document_id,
                    version_id=row.version_id,
                    chunk_id=row.chunk_id,
                    chunk_index=row.chunk_index,
                    chunk_text=row.chunk_text,
                    metadata=row.metadata,
                    similarity=float(row.similarity),
                )
            )

        return results
