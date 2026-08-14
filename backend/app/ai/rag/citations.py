"""Citation construction for RAG retrieval results (WP-4.4C).

Provides immutable Citation dataclass and builder function to construct
citation identity from RetrievalResult. Citations contain the minimal
tuple that uniquely identifies the source of a retrieval result.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.ai.rag.retriever import RetrievalResult


@dataclass(frozen=True)
class Citation:
    """Immutable citation identity for a retrieval result.

    Contains the minimal tuple that uniquely identifies the source chunk:
    - document_id: UUID of the parent document
    - version_id: UUID of the document version
    - version_number: the document version's version_number string
      (e.g. "1.0") — required by the WP-REC-05 M3 citation identity
    - chunk_id: UUID of the knowledge chunk
    - chunk_index: Zero-based index within the version
    - similarity: Cosine similarity score (1 - cosine_distance)

    Frozen dataclass ensures immutability and hashability.
    """

    document_id: UUID
    version_id: UUID
    version_number: str
    chunk_id: UUID
    chunk_index: int
    similarity: float


def build_citation(result: RetrievalResult) -> Citation:
    """Build a Citation from a RetrievalResult.

    Copies identity fields directly from the retrieval result. No
    transformation or computation is applied. The citation is an
    immutable snapshot of the result's identity.

    Args:
        result: RetrievalResult from RetrievalService.retrieve()

    Returns:
        Citation with identity fields copied from result.
    """
    return Citation(
        document_id=result.document_id,
        version_id=result.version_id,
        version_number=result.version_number,
        chunk_id=result.chunk_id,
        chunk_index=result.chunk_index,
        similarity=result.similarity,
    )
