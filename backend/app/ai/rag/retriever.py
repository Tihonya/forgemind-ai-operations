"""Retrieval service for RAG vector search (WP-4.4A, WP-4.4B).

Implements the retrieval domain contract: cosine similarity search over
knowledge chunks using pgvector, with deterministic ordering, strict
input validation, and document access filtering via document_permissions.
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
        version_number: The document version's version_number string
            (e.g. ``"1.0"``) — required by the WP-REC-05 M3 citation
            identity contract.
        chunk_id: UUID of the knowledge chunk.
        chunk_index: Zero-based index of the chunk within the version.
        chunk_text: The text content of the chunk.
        metadata: Optional JSON metadata from the chunk.
        similarity: Cosine similarity score (1 - cosine_distance).
    """

    document_id: UUID
    version_id: UUID
    version_number: str
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
    Applies document permission filtering via SQL join on
    document_permissions (WP-4.4B).
    """

    async def retrieve(
        self,
        session: AsyncSession,
        query_embedding: list[float],
        allowed_role_ids: set[UUID],
        top_k: int = TOP_K_DEFAULT,
    ) -> list[RetrievalResult]:
        """Execute vector similarity search over knowledge chunks.

        Access filtering is enforced inside the PostgreSQL query via a
        join on document_permissions. Only chunks whose parent document
        has at least one permission row matching an allowed_role_id are
        returned. Post-query filtering is never applied.

        Args:
            session: Async SQLAlchemy session.
            query_embedding: Query vector (must match EXPECTED_EMBEDDING_DIMENSION).
            allowed_role_ids: Set of role UUIDs the caller is authorized for.
                Must be non-empty. Documents without a matching permission
                row are excluded.
            top_k: Maximum number of results (1..100, default 10).

        Returns:
            List of RetrievalResult ordered by similarity DESC, then deterministic
            tie-breakers. Only authorized chunks are included.

        Raises:
            RetrievalValidationError: If input validation fails.
        """
        # Validate allowed_role_ids
        if not isinstance(allowed_role_ids, set):
            raise RetrievalValidationError(
                f"allowed_role_ids must be a set, got {type(allowed_role_ids).__name__}"
            )
        if len(allowed_role_ids) == 0:
            raise RetrievalValidationError(
                "allowed_role_ids must be non-empty"
            )
        for role_id in allowed_role_ids:
            if not isinstance(role_id, UUID):
                raise RetrievalValidationError(
                    f"each allowed_role_ids element must be a UUID, "
                    f"got {type(role_id).__name__}"
                )

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

        # Convert allowed_role_ids to list for SQL parameter binding
        role_ids_list = list(allowed_role_ids)

        # SQL query with access filtering via document_permissions join.
        # The subquery in the WHERE clause ensures only chunks whose parent
        # document has a matching permission row for one of the allowed roles
        # are eligible. top_k (LIMIT) is applied AFTER authorization filtering.
        query = text(
            """
            SELECT
                kc.id AS chunk_id,
                kc.chunk_index,
                kc.chunk_text,
                kc.metadata,
                dv.id AS version_id,
                dv.version_number AS version_number,
                d.id AS document_id,
                1 - (kc.embedding <=> CAST(:query_vector AS vector)) AS similarity
            FROM knowledge_chunks kc
            JOIN document_versions dv ON dv.id = kc.document_version_id
            JOIN documents d ON d.id = dv.document_id
            WHERE kc.embedding IS NOT NULL
              AND dv.status = 'APPROVED'
              AND d.id IN (
                  SELECT dp.document_id
                  FROM document_permissions dp
                  WHERE dp.role_id = ANY(:allowed_role_ids)
              )
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
            query,
            {
                "query_vector": vector_str,
                "allowed_role_ids": role_ids_list,
                "top_k": top_k,
            },
        )
        rows = result.fetchall()

        # Map rows to RetrievalResult
        results = []
        for row in rows:
            results.append(
                RetrievalResult(
                    document_id=row.document_id,
                    version_id=row.version_id,
                    version_number=row.version_number,
                    chunk_id=row.chunk_id,
                    chunk_index=row.chunk_index,
                    chunk_text=row.chunk_text,
                    metadata=row.metadata,
                    similarity=float(row.similarity),
                )
            )

        return results
