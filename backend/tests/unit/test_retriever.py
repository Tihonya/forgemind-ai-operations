"""Unit tests for WP-4.4A retrieval service.

Tests input validation and result mapping without database access.
"""

from __future__ import annotations

import uuid

import pytest

from app.ai.rag.retriever import (
    EXPECTED_EMBEDDING_DIMENSION,
    TOP_K_DEFAULT,
    TOP_K_MAX,
    TOP_K_MIN,
    RetrievalResult,
    RetrievalService,
    RetrievalValidationError,
)


class TestRetrievalServiceValidation:
    """Test input validation for retrieval service."""

    @pytest.fixture
    def service(self) -> RetrievalService:
        return RetrievalService()

    @pytest.fixture
    def valid_embedding(self) -> list[float]:
        """Create a valid non-zero embedding."""
        return [0.1] * EXPECTED_EMBEDDING_DIMENSION

    def test_top_k_default(self, service: RetrievalService) -> None:
        """Test that default top_k is used when not specified."""
        # Cannot test without mock session, but we can verify constants
        assert TOP_K_DEFAULT == 10
        assert TOP_K_MIN == 1
        assert TOP_K_MAX == 100

    @pytest.mark.asyncio
    async def test_top_k_below_minimum_rejected(
        self, service: RetrievalService, valid_embedding: list[float]
    ) -> None:
        """Test that top_k < 1 is rejected."""
        with pytest.raises(RetrievalValidationError, match="top_k must be at least 1"):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=valid_embedding,
                top_k=0,
            )

        with pytest.raises(RetrievalValidationError, match="top_k must be at least 1"):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=valid_embedding,
                top_k=-1,
            )

    @pytest.mark.asyncio
    async def test_top_k_above_maximum_rejected(
        self, service: RetrievalService, valid_embedding: list[float]
    ) -> None:
        """Test that top_k > 100 is rejected."""
        with pytest.raises(RetrievalValidationError, match="top_k must be at most 100"):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=valid_embedding,
                top_k=101,
            )

        with pytest.raises(RetrievalValidationError, match="top_k must be at most 100"):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=valid_embedding,
                top_k=1000,
            )

    @pytest.mark.asyncio
    async def test_top_k_minimum_accepted(
        self, service: RetrievalService, valid_embedding: list[float]
    ) -> None:
        """Test that top_k = 1 is accepted (validation passes)."""
        # Will fail at session level, but validation should pass
        # We expect a different error than RetrievalValidationError
        try:
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=valid_embedding,
                top_k=1,
            )
        except RetrievalValidationError:
            pytest.fail("top_k=1 should pass validation")
        except (TypeError, AttributeError):
            # Expected: will fail when trying to use None as session
            pass

    @pytest.mark.asyncio
    async def test_top_k_maximum_accepted(
        self, service: RetrievalService, valid_embedding: list[float]
    ) -> None:
        """Test that top_k = 100 is accepted (validation passes)."""
        try:
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=valid_embedding,
                top_k=100,
            )
        except RetrievalValidationError:
            pytest.fail("top_k=100 should pass validation")
        except (TypeError, AttributeError):
            # Expected: will fail when trying to use None as session
            pass

    @pytest.mark.asyncio
    async def test_wrong_dimension_rejected(
        self, service: RetrievalService
    ) -> None:
        """Test that embedding with wrong dimension is rejected."""
        # Too short
        short_embedding = [0.1] * (EXPECTED_EMBEDDING_DIMENSION - 1)
        with pytest.raises(
            RetrievalValidationError,
            match=f"must have dimension {EXPECTED_EMBEDDING_DIMENSION}",
        ):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=short_embedding,
                top_k=10,
            )

        # Too long
        long_embedding = [0.1] * (EXPECTED_EMBEDDING_DIMENSION + 1)
        with pytest.raises(
            RetrievalValidationError,
            match=f"must have dimension {EXPECTED_EMBEDDING_DIMENSION}",
        ):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=long_embedding,
                top_k=10,
            )

    @pytest.mark.asyncio
    async def test_nan_rejected(
        self, service: RetrievalService, valid_embedding: list[float]
    ) -> None:
        """Test that embedding containing NaN is rejected."""
        bad_embedding = valid_embedding.copy()
        bad_embedding[100] = float("nan")

        with pytest.raises(
            RetrievalValidationError,
            match=r"query_embedding\[100\] must be finite",
        ):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=bad_embedding,
                top_k=10,
            )

    @pytest.mark.asyncio
    async def test_inf_rejected(
        self, service: RetrievalService, valid_embedding: list[float]
    ) -> None:
        """Test that embedding containing Inf is rejected."""
        bad_embedding = valid_embedding.copy()
        bad_embedding[200] = float("inf")

        with pytest.raises(
            RetrievalValidationError,
            match=r"query_embedding\[200\] must be finite",
        ):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=bad_embedding,
                top_k=10,
            )

        # Also test -inf
        bad_embedding[200] = float("-inf")
        with pytest.raises(
            RetrievalValidationError,
            match=r"query_embedding\[200\] must be finite",
        ):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=bad_embedding,
                top_k=10,
            )

    @pytest.mark.asyncio
    async def test_zero_norm_rejected(
        self, service: RetrievalService
    ) -> None:
        """Test that zero-norm embedding is rejected."""
        zero_embedding = [0.0] * EXPECTED_EMBEDDING_DIMENSION

        with pytest.raises(
            RetrievalValidationError,
            match="must not be zero-norm",
        ):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=zero_embedding,
                top_k=10,
            )

    @pytest.mark.asyncio
    async def test_non_numeric_rejected(
        self, service: RetrievalService, valid_embedding: list[float]
    ) -> None:
        """Test that embedding containing non-numeric values is rejected."""
        bad_embedding = valid_embedding.copy()
        bad_embedding[50] = "not a number"  # type: ignore[call-overload]

        with pytest.raises(
            RetrievalValidationError,
            match=r"query_embedding\[50\] must be numeric",
        ):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=bad_embedding,
                top_k=10,
            )

    @pytest.mark.asyncio
    async def test_non_list_embedding_rejected(
        self, service: RetrievalService
    ) -> None:
        """Test that non-list embedding is rejected."""
        with pytest.raises(
            RetrievalValidationError,
            match="query_embedding must be a list",
        ):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding="not a list",  # type: ignore[arg-type]
                top_k=10,
            )

    @pytest.mark.asyncio
    async def test_invalid_top_k_type_rejected(
        self, service: RetrievalService, valid_embedding: list[float]
    ) -> None:
        """Test that non-integer top_k is rejected."""
        with pytest.raises(
            RetrievalValidationError,
            match="top_k must be an integer",
        ):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=valid_embedding,
                top_k=10.5,  # type: ignore[arg-type]
            )

        with pytest.raises(
            RetrievalValidationError,
            match="top_k must be an integer",
        ):
            await service.retrieve(
                session=None,  # type: ignore[arg-type]
                query_embedding=valid_embedding,
                top_k=True,
            )


class TestRetrievalResult:
    """Test RetrievalResult dataclass."""

    def test_result_creation(self) -> None:
        """Test that RetrievalResult can be created with all fields."""
        doc_id = uuid.uuid4()
        ver_id = uuid.uuid4()
        chunk_id = uuid.uuid4()

        result = RetrievalResult(
            document_id=doc_id,
            version_id=ver_id,
            chunk_id=chunk_id,
            chunk_index=5,
            chunk_text="Test chunk text",
            metadata={"key": "value"},
            similarity=0.95,
        )

        assert result.document_id == doc_id
        assert result.version_id == ver_id
        assert result.chunk_id == chunk_id
        assert result.chunk_index == 5
        assert result.chunk_text == "Test chunk text"
        assert result.metadata == {"key": "value"}
        assert result.similarity == 0.95

    def test_result_immutable(self) -> None:
        """Test that RetrievalResult is immutable (frozen dataclass)."""
        result = RetrievalResult(
            document_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            chunk_index=0,
            chunk_text="text",
            metadata=None,
            similarity=0.5,
        )

        with pytest.raises(AttributeError):
            result.chunk_index = 10  # type: ignore[misc]

        with pytest.raises(AttributeError):
            result.similarity = 0.9  # type: ignore[misc]

    def test_result_with_none_metadata(self) -> None:
        """Test that RetrievalResult accepts None metadata."""
        result = RetrievalResult(
            document_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            chunk_id=uuid.uuid4(),
            chunk_index=0,
            chunk_text="text",
            metadata=None,
            similarity=0.5,
        )

        assert result.metadata is None
