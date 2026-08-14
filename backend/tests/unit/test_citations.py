"""Unit tests for WP-4.4C: Citation construction.

Tests the Citation dataclass and build_citation function.
"""

from uuid import uuid4

import pytest

from app.ai.rag.citations import build_citation
from app.ai.rag.retriever import RetrievalResult


def test_citation_identity_fields_copied_from_result() -> None:
    """Citation identity fields are copied exactly from RetrievalResult."""
    doc_id = uuid4()
    version_id = uuid4()
    chunk_id = uuid4()

    result = RetrievalResult(
        document_id=doc_id,
        version_id=version_id,
        version_number="1.0",
        chunk_id=chunk_id,
        chunk_index=5,
        chunk_text="test chunk text",
        metadata={"key": "value"},
        similarity=0.87,
    )

    citation = build_citation(result)

    assert citation.document_id == doc_id
    assert citation.version_id == version_id
    assert citation.version_number == "1.0"
    assert citation.chunk_id == chunk_id
    assert citation.chunk_index == 5
    assert citation.similarity == 0.87


def test_citation_chunk_index_preserved() -> None:
    """chunk_index is preserved from RetrievalResult."""
    result = RetrievalResult(
        document_id=uuid4(),
        version_id=uuid4(),
        version_number="1.0",
        chunk_id=uuid4(),
        chunk_index=0,
        chunk_text="first chunk",
        metadata=None,
        similarity=0.95,
    )

    citation = build_citation(result)

    assert citation.chunk_index == 0


def test_citation_similarity_preserved() -> None:
    """similarity score is preserved from RetrievalResult."""
    result = RetrievalResult(
        document_id=uuid4(),
        version_id=uuid4(),
        version_number="1.0",
        chunk_id=uuid4(),
        chunk_index=0,
        chunk_text="test",
        metadata=None,
        similarity=0.123456789,
    )

    citation = build_citation(result)

    assert citation.similarity == 0.123456789


def test_citation_metadata_not_included() -> None:
    """metadata is not part of Citation identity."""
    result = RetrievalResult(
        document_id=uuid4(),
        version_id=uuid4(),
        version_number="1.0",
        chunk_id=uuid4(),
        chunk_index=0,
        chunk_text="test",
        metadata={"key": "value"},
        similarity=0.9,
    )

    citation = build_citation(result)

    # Citation does not have metadata field
    assert not hasattr(citation, "metadata")


def test_citation_immutable() -> None:
    """Citation is frozen (immutable)."""
    doc_id = uuid4()
    version_id = uuid4()
    chunk_id = uuid4()

    result = RetrievalResult(
        document_id=doc_id,
        version_id=version_id,
        version_number="1.0",
        chunk_id=chunk_id,
        chunk_index=0,
        chunk_text="test",
        metadata=None,
        similarity=0.9,
    )

    citation = build_citation(result)

    # Attempting to modify should raise AttributeError
    try:
        citation.document_id = uuid4()  # type: ignore[misc]
    except AttributeError:
        pass  # Expected — frozen dataclass rejects mutation
    else:
        pytest.fail("Should not be able to modify frozen dataclass")


def test_citation_typed_fields() -> None:
    """Citation fields have correct types."""
    result = RetrievalResult(
        document_id=uuid4(),
        version_id=uuid4(),
        version_number="1.0",
        chunk_id=uuid4(),
        chunk_index=3,
        chunk_text="test",
        metadata=None,
        similarity=0.75,
    )

    citation = build_citation(result)

    from uuid import UUID
    assert isinstance(citation.document_id, UUID)
    assert isinstance(citation.version_id, UUID)
    assert isinstance(citation.chunk_id, UUID)
    assert isinstance(citation.chunk_index, int)
    assert isinstance(citation.similarity, float)
