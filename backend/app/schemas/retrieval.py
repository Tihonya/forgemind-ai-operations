"""Retrieval API schemas for WP-4.4C.

Defines typed Pydantic models for the retrieval endpoint.
Request/response contracts follow repository conventions.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class RetrievalRequest(BaseModel):
    """Request body for POST /api/v1/retrieval.

    Attributes:
        query_embedding: Query vector (must match expected dimension 1536).
        top_k: Maximum number of results (1..100, default 10).
    """

    query_embedding: list[float] = Field(
        ..., description="Query vector for similarity search"
    )
    top_k: int = Field(default=10, ge=1, le=100, description="Maximum results to return")


class CitationResponse(BaseModel):
    """Citation identity in API response.

    Attributes:
        document_id: UUID of the parent document.
        version_id: UUID of the document version.
        chunk_id: UUID of the knowledge chunk.
        chunk_index: Zero-based index within the version.
        similarity: Cosine similarity score.
    """

    document_id: UUID = Field(..., description="Document UUID")
    version_id: UUID = Field(..., description="Document version UUID")
    chunk_id: UUID = Field(..., description="Knowledge chunk UUID")
    chunk_index: int = Field(..., description="Zero-based chunk index")
    similarity: float = Field(..., description="Cosine similarity score")


class RetrievalResultResponse(BaseModel):
    """Single retrieval result in API response.

    Attributes:
        document_id: UUID of the parent document.
        version_id: UUID of the document version.
        chunk_id: UUID of the knowledge chunk.
        chunk_index: Zero-based index within the version.
        chunk_text: Text content of the chunk.
        similarity: Cosine similarity score.
        metadata: Optional JSON metadata from the chunk.
        citation: Citation identity for this result.
    """

    document_id: UUID = Field(..., description="Document UUID")
    version_id: UUID = Field(..., description="Document version UUID")
    chunk_id: UUID = Field(..., description="Knowledge chunk UUID")
    chunk_index: int = Field(..., description="Zero-based chunk index")
    chunk_text: str = Field(..., description="Text content of the chunk")
    similarity: float = Field(..., description="Cosine similarity score")
    metadata: dict[str, Any] | None = Field(default=None, description="Chunk metadata")
    citation: CitationResponse = Field(..., description="Citation identity")


class RetrievalResponse(BaseModel):
    """Response body for POST /api/v1/retrieval.

    Attributes:
        results: List of retrieval results with citations.
        total_results: Number of results returned.
        query_embedding_dimension: Dimension of the query embedding.
    """

    results: list[RetrievalResultResponse] = Field(
        default_factory=list, description="Retrieval results"
    )
    total_results: int = Field(..., description="Number of results returned")
    query_embedding_dimension: int = Field(
        ..., description="Dimension of the query embedding"
    )
