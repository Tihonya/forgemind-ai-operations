"""Unit tests for the embedding provider abstraction.

Tests cover:
- FakeEmbeddingProvider: determinism, dimension, empty batch, finite values
- OpenAIEmbeddingProvider: mocked API responses, dimension validation,
  error handling with typed exceptions and chaining, no network calls
- Exception hierarchy: correct subclass relationships
- Configuration: provider selection, model name, dimension, max_retries=0
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.services.embedding_provider import (
    EmbeddingProvider,
    EmbeddingProviderConfigurationError,
    EmbeddingProviderError,
    FakeEmbeddingProvider,
    OpenAIEmbeddingProvider,
    PermanentEmbeddingProviderError,
    TransientEmbeddingProviderError,
)

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Verify the exception class hierarchy."""

    def test_base_is_exception(self) -> None:
        assert issubclass(EmbeddingProviderError, Exception)

    def test_transient_is_subclass_of_base(self) -> None:
        assert issubclass(TransientEmbeddingProviderError, EmbeddingProviderError)

    def test_permanent_is_subclass_of_base(self) -> None:
        assert issubclass(PermanentEmbeddingProviderError, EmbeddingProviderError)

    def test_configuration_is_subclass_of_base(self) -> None:
        assert issubclass(EmbeddingProviderConfigurationError, EmbeddingProviderError)

    def test_transient_not_subclass_of_permanent(self) -> None:
        assert not issubclass(TransientEmbeddingProviderError, PermanentEmbeddingProviderError)

    def test_permanent_not_subclass_of_transient(self) -> None:
        assert not issubclass(PermanentEmbeddingProviderError, TransientEmbeddingProviderError)

# ---------------------------------------------------------------------------
# FakeEmbeddingProvider
# ---------------------------------------------------------------------------


class TestFakeEmbeddingProviderDimension:
    def test_default_dimension_is_1536(self) -> None:
        provider = FakeEmbeddingProvider()
        assert provider.dimension() == 1536

    def test_custom_dimension(self) -> None:
        provider = FakeEmbeddingProvider(dimension=768)
        assert provider.dimension() == 768

    def test_zero_dimension_raises(self) -> None:
        with pytest.raises(ValueError, match="dimension"):
            FakeEmbeddingProvider(dimension=0)

    def test_negative_dimension_raises(self) -> None:
        with pytest.raises(ValueError, match="dimension"):
            FakeEmbeddingProvider(dimension=-1)


class TestFakeEmbeddingProviderDeterminism:
    """Same text must produce the same embedding across calls."""

    @pytest.mark.asyncio
    async def test_same_text_same_embedding(self) -> None:
        provider = FakeEmbeddingProvider(dimension=64)
        text = "deterministic test text"
        emb1 = await provider.embed_text([text])
        emb2 = await provider.embed_text([text])
        assert emb1 == emb2

    @pytest.mark.asyncio
    async def test_same_text_across_instances(self) -> None:
        text = "cross instance determinism"
        p1 = FakeEmbeddingProvider(dimension=64)
        p2 = FakeEmbeddingProvider(dimension=64)
        emb1 = await p1.embed_text([text])
        emb2 = await p2.embed_text([text])
        assert emb1 == emb2

    @pytest.mark.asyncio
    async def test_different_text_different_embedding(self) -> None:
        provider = FakeEmbeddingProvider(dimension=64)
        emb1 = await provider.embed_text(["text A"])
        emb2 = await provider.embed_text(["text B"])
        assert emb1 != emb2


class TestFakeEmbeddingProviderDimensionValidation:
    """Each embedding must be exactly the configured dimension of floats."""

    @pytest.mark.asyncio
    async def test_embedding_has_correct_length(self) -> None:
        provider = FakeEmbeddingProvider(dimension=1536)
        result = await provider.embed_text(["hello"])
        assert len(result) == 1
        assert len(result[0]) == 1536

    @pytest.mark.asyncio
    async def test_all_values_are_floats(self) -> None:
        provider = FakeEmbeddingProvider(dimension=32)
        result = await provider.embed_text(["floats"])
        for v in result[0]:
            assert isinstance(v, float)


class TestFakeEmbeddingProviderFiniteValues:
    """No NaN or Inf values should appear in embeddings."""

    @pytest.mark.asyncio
    async def test_no_nan(self) -> None:
        provider = FakeEmbeddingProvider(dimension=256)
        result = await provider.embed_text(["no nan"])
        for v in result[0]:
            assert math.isfinite(v), f"Found non-finite value: {v}"

    @pytest.mark.asyncio
    async def test_no_inf(self) -> None:
        provider = FakeEmbeddingProvider(dimension=256)
        result = await provider.embed_text(["no inf"])
        for v in result[0]:
            assert not math.isinf(v), f"Found infinity: {v}"

    @pytest.mark.asyncio
    async def test_values_in_range(self) -> None:
        provider = FakeEmbeddingProvider(dimension=256)
        result = await provider.embed_text(["in range"])
        for v in result[0]:
            assert -1.0 <= v <= 1.0, f"Value out of [-1, 1]: {v}"


class TestFakeEmbeddingProviderEmptyBatch:
    """Empty batch input must return empty list."""

    @pytest.mark.asyncio
    async def test_empty_batch_returns_empty_list(self) -> None:
        provider = FakeEmbeddingProvider()
        result = await provider.embed_text([])
        assert result == []


class TestFakeEmbeddingProviderMultipleTexts:
    """Multiple texts in one call must return multiple embeddings."""

    @pytest.mark.asyncio
    async def test_batch_embeddings(self) -> None:
        provider = FakeEmbeddingProvider(dimension=32)
        texts = ["first", "second", "third"]
        result = await provider.embed_text(texts)
        assert len(result) == 3
        assert len(result[0]) == 32
        assert len(result[1]) == 32
        assert len(result[2]) == 32

    @pytest.mark.asyncio
    async def test_batch_embeddings_are_different(self) -> None:
        provider = FakeEmbeddingProvider(dimension=32)
        result = await provider.embed_text(["a", "b", "c"])
        assert result[0] != result[1]
        assert result[1] != result[2]


# ---------------------------------------------------------------------------
# OpenAIEmbeddingProvider
# ---------------------------------------------------------------------------


class TestOpenAIEmbeddingProviderInit:
    def test_default_model_and_dimension(self) -> None:
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
        assert provider.dimension() == 1536

    def test_custom_model_and_dimension(self) -> None:
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="test-key",
                model="custom-model",
                dimension=512,
            )
        assert provider.dimension() == 512

    def test_empty_api_key_raises_configuration_error(self) -> None:
        with pytest.raises(EmbeddingProviderConfigurationError, match="api_key"):
            OpenAIEmbeddingProvider(api_key="")

    def test_zero_dimension_raises_configuration_error(self) -> None:
        with pytest.raises(EmbeddingProviderConfigurationError, match="dimension"):
            OpenAIEmbeddingProvider(api_key="test-key", dimension=0)

    def test_negative_dimension_raises_configuration_error(self) -> None:
        with pytest.raises(EmbeddingProviderConfigurationError, match="dimension"):
            OpenAIEmbeddingProvider(api_key="test-key", dimension=-1)

    def test_max_retries_zero_is_passed(self) -> None:
        """AsyncOpenAI must be constructed with max_retries=0."""
        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=AsyncMock(),
        ) as mock_async_openai:
            OpenAIEmbeddingProvider(api_key="test-key")
            call_kwargs = mock_async_openai.call_args[1]
            assert call_kwargs["max_retries"] == 0


class TestOpenAIEmbeddingProviderEmbedText:
    """Test with mocked API — no real network calls."""

    @pytest.mark.asyncio
    async def test_successful_embedding(self) -> None:
        mock_item = MagicMock()
        mock_item.embedding = [0.1] * 1536
        mock_response = MagicMock()
        mock_response.data = [mock_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            result = await provider.embed_text(["hello"])

        assert len(result) == 1
        assert len(result[0]) == 1536
        assert all(isinstance(v, float) for v in result[0])

    @pytest.mark.asyncio
    async def test_batch_embedding(self) -> None:
        mock_items = [
            MagicMock(embedding=[0.1] * 64),
            MagicMock(embedding=[0.2] * 64),
        ]
        mock_response = MagicMock()
        mock_response.data = mock_items

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="test-key",
                dimension=64,
            )
            result = await provider.embed_text(["a", "b"])

        assert len(result) == 2
        assert len(result[0]) == 64
        assert len(result[1]) == 64

    @pytest.mark.asyncio
    async def test_empty_batch_returns_empty(self) -> None:
        mock_client = AsyncMock()

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            result = await provider.embed_text([])

        assert result == []
        mock_client.embeddings.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_dimension_mismatch_raises_permanent(self) -> None:
        mock_item = MagicMock()
        mock_item.embedding = [0.1] * 128  # wrong size
        mock_response = MagicMock()
        mock_response.data = [mock_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="test-key",
                dimension=64,
            )
            with pytest.raises(PermanentEmbeddingProviderError, match="dimension mismatch"):
                await provider.embed_text(["hello"])

    # --- Transient error classification ---

    @pytest.mark.asyncio
    async def test_api_connection_error_raises_transient(self) -> None:
        from openai import APIConnectionError

        original_error = APIConnectionError(
            message="Connection refused",
            request=MagicMock(),
        )
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=original_error)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(TransientEmbeddingProviderError) as exc_info:
                await provider.embed_text(["hello"])

            # Verify exception chaining
            assert exc_info.value.__cause__ is original_error

    @pytest.mark.asyncio
    async def test_api_timeout_error_raises_transient(self) -> None:
        from openai import APITimeoutError

        original_error = APITimeoutError(
            request=MagicMock(),
        )
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=original_error)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(TransientEmbeddingProviderError) as exc_info:
                await provider.embed_text(["hello"])
            assert exc_info.value.__cause__ is original_error

    @pytest.mark.asyncio
    async def test_rate_limit_error_raises_transient(self) -> None:
        from openai import RateLimitError

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_response.request = MagicMock()

        original_error = RateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=original_error)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(TransientEmbeddingProviderError) as exc_info:
                await provider.embed_text(["hello"])
            assert exc_info.value.__cause__ is original_error

    @pytest.mark.asyncio
    async def test_internal_server_error_raises_transient(self) -> None:
        from openai import InternalServerError

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.headers = {}
        mock_response.request = MagicMock()

        original_error = InternalServerError(
            message="Internal server error",
            response=mock_response,
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=original_error)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(TransientEmbeddingProviderError) as exc_info:
                await provider.embed_text(["hello"])
            assert exc_info.value.__cause__ is original_error

    # --- Permanent error classification ---

    @pytest.mark.asyncio
    async def test_authentication_error_raises_permanent(self) -> None:
        from openai import AuthenticationError

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        mock_response.request = MagicMock()

        original_error = AuthenticationError(
            message="Invalid API key",
            response=mock_response,
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=original_error)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(PermanentEmbeddingProviderError) as exc_info:
                await provider.embed_text(["hello"])
            assert exc_info.value.__cause__ is original_error

    @pytest.mark.asyncio
    async def test_permission_denied_error_raises_permanent(self) -> None:
        from openai import PermissionDeniedError

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {}
        mock_response.request = MagicMock()

        original_error = PermissionDeniedError(
            message="Permission denied",
            response=mock_response,
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=original_error)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(PermanentEmbeddingProviderError) as exc_info:
                await provider.embed_text(["hello"])
            assert exc_info.value.__cause__ is original_error

    @pytest.mark.asyncio
    async def test_bad_request_error_raises_permanent(self) -> None:
        from openai import BadRequestError

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.headers = {}
        mock_response.request = MagicMock()

        original_error = BadRequestError(
            message="Bad request",
            response=mock_response,
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=original_error)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(PermanentEmbeddingProviderError) as exc_info:
                await provider.embed_text(["hello"])
            assert exc_info.value.__cause__ is original_error

    @pytest.mark.asyncio
    async def test_unprocessable_entity_error_raises_permanent(self) -> None:
        from openai import UnprocessableEntityError

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.headers = {}
        mock_response.request = MagicMock()

        original_error = UnprocessableEntityError(
            message="Unprocessable entity",
            response=mock_response,
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=original_error)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(PermanentEmbeddingProviderError) as exc_info:
                await provider.embed_text(["hello"])
            assert exc_info.value.__cause__ is original_error

    # --- APIStatusError fallback by status code ---

    @pytest.mark.asyncio
    async def test_5xx_api_status_error_raises_transient(self) -> None:
        from openai import APIStatusError

        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.headers = {}
        mock_response.request = MagicMock()

        original_error = APIStatusError(
            message="Service unavailable",
            response=mock_response,
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=original_error)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(TransientEmbeddingProviderError) as exc_info:
                await provider.embed_text(["hello"])
            assert exc_info.value.__cause__ is original_error

    @pytest.mark.asyncio
    async def test_4xx_api_status_error_raises_permanent(self) -> None:
        from openai import APIStatusError

        mock_response = MagicMock()
        mock_response.status_code = 418
        mock_response.headers = {}
        mock_response.request = MagicMock()

        original_error = APIStatusError(
            message="I'm a teapot",
            response=mock_response,
            body=None,
        )
        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(side_effect=original_error)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(PermanentEmbeddingProviderError) as exc_info:
                await provider.embed_text(["hello"])
            assert exc_info.value.__cause__ is original_error

    # --- Validation errors ---

    @pytest.mark.asyncio
    async def test_no_data_response_raises_permanent(self) -> None:
        mock_response = MagicMock()
        mock_response.data = []

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(PermanentEmbeddingProviderError, match="returned no data"):
                await provider.embed_text(["hello"])

    @pytest.mark.asyncio
    async def test_count_mismatch_raises_permanent(self) -> None:
        mock_item = MagicMock()
        mock_item.embedding = [0.1] * 64
        mock_response = MagicMock()
        mock_response.data = [mock_item]  # only 1 for 2 inputs

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="test-key",
                dimension=64,
            )
            with pytest.raises(PermanentEmbeddingProviderError, match="returned"):
                await provider.embed_text(["a", "b"])

    @pytest.mark.asyncio
    async def test_non_list_embedding_raises_permanent(self) -> None:
        mock_item = MagicMock()
        mock_item.embedding = "not-a-list"
        mock_response = MagicMock()
        mock_response.data = [mock_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(api_key="test-key")
            with pytest.raises(PermanentEmbeddingProviderError, match="Expected list"):
                await provider.embed_text(["hello"])

    @pytest.mark.asyncio
    async def test_nan_in_embedding_raises_permanent(self) -> None:
        """NaN values in embeddings are rejected via math.isfinite."""
        mock_item = MagicMock()
        mock_item.embedding = [0.1, float("nan"), 0.3] + [0.0] * 61
        mock_response = MagicMock()
        mock_response.data = [mock_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="test-key",
                dimension=64,
            )
            with pytest.raises(PermanentEmbeddingProviderError, match="Non-finite"):
                await provider.embed_text(["hello"])

    @pytest.mark.asyncio
    async def test_pos_inf_in_embedding_raises_permanent(self) -> None:
        """Positive infinity values in embeddings are rejected via math.isfinite."""
        mock_item = MagicMock()
        mock_item.embedding = [0.1, float("inf"), 0.3] + [0.0] * 61
        mock_response = MagicMock()
        mock_response.data = [mock_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="test-key",
                dimension=64,
            )
            with pytest.raises(PermanentEmbeddingProviderError, match="Non-finite"):
                await provider.embed_text(["hello"])

    @pytest.mark.asyncio
    async def test_neg_inf_in_embedding_raises_permanent(self) -> None:
        """Negative infinity values in embeddings are rejected via math.isfinite."""
        mock_item = MagicMock()
        mock_item.embedding = [0.1, float("-inf"), 0.3] + [0.0] * 61
        mock_response = MagicMock()
        mock_response.data = [mock_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="test-key",
                dimension=64,
            )
            with pytest.raises(PermanentEmbeddingProviderError, match="Non-finite"):
                await provider.embed_text(["hello"])

    @pytest.mark.asyncio
    async def test_non_numeric_in_embedding_raises_permanent(self) -> None:
        mock_item = MagicMock()
        mock_item.embedding = [0.1, None, 0.3] + [0.0] * 61
        mock_response = MagicMock()
        mock_response.data = [mock_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ):
            provider = OpenAIEmbeddingProvider(
                api_key="test-key",
                dimension=64,
            )
            with pytest.raises(PermanentEmbeddingProviderError, match="Non-numeric"):
                await provider.embed_text(["hello"])

    @pytest.mark.asyncio
    async def test_base_url_is_passed(self) -> None:
        mock_item = MagicMock()
        mock_item.embedding = [0.1] * 64
        mock_response = MagicMock()
        mock_response.data = [mock_item]

        mock_client = AsyncMock()
        mock_client.embeddings.create = AsyncMock(return_value=mock_response)

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ) as mock_async_openai:
            OpenAIEmbeddingProvider(
                api_key="test-key",
                base_url="http://localhost:8000/v1",
                dimension=64,
            )
            mock_async_openai.assert_called_once()
            call_kwargs = mock_async_openai.call_args[1]
            assert call_kwargs["base_url"] == "http://localhost:8000/v1"

    @pytest.mark.asyncio
    async def test_timeout_is_passed(self) -> None:
        mock_client = AsyncMock()

        with patch(
            "app.services.embedding_provider.AsyncOpenAI",
            return_value=mock_client,
        ) as mock_async_openai:
            OpenAIEmbeddingProvider(
                api_key="test-key",
                timeout_seconds=45,
            )
            call_kwargs = mock_async_openai.call_args[1]
            assert call_kwargs["timeout"] == 45.0


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class TestEmbeddingProviderABC:
    def test_cannot_instantiate_abstract_base(self) -> None:
        with pytest.raises(TypeError):
            EmbeddingProvider()  # type: ignore[abstract]

    def test_subclass_must_implement_embed_text(self) -> None:
        class IncompleteProvider(EmbeddingProvider):
            def dimension(self) -> int:
                return 1

        with pytest.raises(TypeError):
            IncompleteProvider()  # type: ignore[abstract]

    def test_subclass_must_implement_dimension(self) -> None:
        class IncompleteProvider(EmbeddingProvider):
            async def embed_text(self, texts: list[str]) -> list[list[float]]:
                return []

        with pytest.raises(TypeError):
            IncompleteProvider()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestEmbeddingConfiguration:
    def test_default_provider_is_openai(self) -> None:
        settings = Settings()
        assert settings.embedding_provider == "openai"

    def test_default_model_name(self) -> None:
        settings = Settings()
        assert settings.openai_embedding_model == "text-embedding-3-small"

    def test_default_dimension(self) -> None:
        settings = Settings()
        assert settings.embedding_dimensions == 1536

    def test_default_timeout(self) -> None:
        settings = Settings()
        assert settings.embedding_timeout_seconds == 30

    def test_fake_provider_selection(self) -> None:
        settings = Settings(embedding_provider="fake")
        assert settings.embedding_provider == "fake"

    def test_invalid_provider_raises(self) -> None:
        with pytest.raises(ValueError):
            Settings(embedding_provider="invalid")  # type: ignore[arg-type]

    def test_custom_dimension(self) -> None:
        settings = Settings(embedding_dimensions=768)
        assert settings.embedding_dimensions == 768

    def test_custom_timeout(self) -> None:
        settings = Settings(embedding_timeout_seconds=60)
        assert settings.embedding_timeout_seconds == 60

    def test_zero_dimension_raises(self) -> None:
        with pytest.raises(ValueError):
            Settings(embedding_dimensions=0)

    def test_negative_timeout_raises(self) -> None:
        with pytest.raises(ValueError):
            Settings(embedding_timeout_seconds=-1)

    def test_timeout_below_minimum_raises(self) -> None:
        with pytest.raises(ValueError):
            Settings(embedding_timeout_seconds=4)
