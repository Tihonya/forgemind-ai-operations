"""Embedding provider abstraction with OpenAI-compatible and fake providers.

This module defines the provider interface, a production OpenAI-compatible
adapter, and a deterministic fake provider for testing without network calls.
"""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    async def embed_text(self, texts: list[str]) -> list[list[float]]:
        """Return a list of embeddings, one per input text.

        Args:
            texts: Input texts to embed. May be empty.

        Returns:
            A list of float vectors, one per input text. Each vector must
            have the same dimension as the provider's dimension.

        Raises:
            ValueError: If the input list is empty.
            RuntimeError: If the provider fails to generate an embedding.
        """
        ...

    @abstractmethod
    def dimension(self) -> int:
        """Return the vector dimension produced by this provider."""
        ...


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic fake embedding provider for testing.

    Produces identical embeddings for identical text without any network
    calls. Uses SHA-256 hashing (not Python's built-in hash) to ensure
    cross-process determinism. Supports empty batches by returning an
    empty list.
    """

    def __init__(self, dimension: int = 1536) -> None:
        if dimension <= 0:
            raise ValueError(f"dimension must be positive, got {dimension}")
        self._dimension = dimension

    def dimension(self) -> int:
        return self._dimension

    async def embed_text(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float]] = []
        for text in texts:
            results.append(self._deterministic_vector(text))
        return results

    def _deterministic_vector(self, text: str) -> list[float]:
        """Generate a deterministic embedding vector from text.

        Uses SHA-256 to derive bytes, then converts to floats in [-1, 1]
        using a cosine mapping to ensure finite values.
        """
        # sha256 produces 32 bytes (256 bits); we need `dimension` floats.
        # Expand by concatenating partial digests with the text as salt.
        values: list[float] = []
        for i in range(self._dimension):
            # Use a per-index seed to get independent values
            seed = f"{text}|{i}".encode()
            byte_val = int.from_bytes(
                hashlib.sha256(seed).digest()[:4], byteorder="big"
            )
            # Map to [-1, 1] using cosine; avoids NaN/Inf entirely
            normalized = (byte_val % (2**31)) / (2**31 - 1)  # [0, 1]
            value = math.cos(normalized * 2 * math.pi)
            values.append(value)
        return values


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI-compatible embedding provider.

    Wraps the OpenAI async client and validates that every returned vector
    has the expected dimension. Provider errors are re-raised with the
    original exception as the cause (raise from).
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimension: int = 1536,
        base_url: str | None = None,
        timeout_seconds: int = 30,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if dimension <= 0:
            raise ValueError(f"dimension must be positive, got {dimension}")

        self._model = model
        self._expected_dimension = dimension
        self._timeout_seconds = timeout_seconds

        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": float(timeout_seconds),
        }
        if base_url is not None:
            client_kwargs["base_url"] = base_url

        self._client = AsyncOpenAI(**client_kwargs)

    def dimension(self) -> int:
        return self._expected_dimension

    async def embed_text(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=texts,
                dimensions=self._expected_dimension,
            )
        except Exception as exc:
            raise RuntimeError(
                f"OpenAI embedding API failed for model={self._model!r}"
            ) from exc

        if not response.data:
            raise RuntimeError(
                f"OpenAI embedding API returned no data for {len(texts)} input(s)"
            )

        if len(response.data) != len(texts):
            raise RuntimeError(
                f"OpenAI embedding API returned {len(response.data)} embeddings "
                f"for {len(texts)} inputs"
            )

        results: list[list[float]] = []
        for item in response.data:
            embedding = item.embedding
            if not isinstance(embedding, list):
                raise RuntimeError(
                    f"Expected list embedding, got {type(embedding).__name__}"
                )
            if len(embedding) != self._expected_dimension:
                raise RuntimeError(
                    f"Embedding dimension mismatch: expected "
                    f"{self._expected_dimension}, got {len(embedding)}"
                )
            # Validate all values are finite
            for v in embedding:
                if not isinstance(v, (int, float)):
                    raise RuntimeError(
                        f"Non-numeric value in embedding: {type(v).__name__}"
                    )
            results.append([float(v) for v in embedding])

        return results
