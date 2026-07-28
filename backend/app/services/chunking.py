"""Chunking service for document text segmentation.

Provides fixed-size character chunking with configurable overlap, SHA-256
content hashing, and deterministic approximate token counting via tiktoken.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import tiktoken

# Default parameters (cl100k_base encoder used by gpt-3.5/4)
_DEFAULT_CHUNK_SIZE = 1000
_DEFAULT_OVERLAP = 200
_ENCODER = tiktoken.get_encoding("cl100k_base")


@dataclass(frozen=True)
class ChunkData:
    """A single text chunk produced by the chunking service."""

    chunk_index: int
    chunk_text: str
    content_hash: str
    token_count: int
    chunk_size: int
    overlap: int


def chunk_text(
    text: str,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[ChunkData]:
    """Split *text* into fixed-size character chunks with overlap.

    The algorithm produces consecutive windows of ``chunk_size`` characters,
    each shifted forward by ``chunk_size - overlap``.  The final chunk may be
    shorter than ``chunk_size`` if the remaining text is too small to justify
    another full window.

    Args:
        text: The document text to split.
        chunk_size: Number of characters per chunk (default 1000).
        overlap: Number of overlapping characters between consecutive chunks
            (default 200).

    Returns:
        A list of ``ChunkData`` instances ordered by ascending ``chunk_index``
        (zero-based).

    Raises:
        ValueError: If *chunk_size* is not positive, *overlap* is negative,
            or *overlap* is greater than or equal to *chunk_size*.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be a positive integer")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be less than chunk_size")

    if not text:
        return []

    chunks: list[ChunkData] = []
    stride = chunk_size - overlap
    start = 0
    index = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_text = text[start:end]

        content_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
        token_count = len(_ENCODER.encode(chunk_text))

        chunks.append(
            ChunkData(
                chunk_index=index,
                chunk_text=chunk_text,
                content_hash=content_hash,
                token_count=token_count,
                chunk_size=chunk_size,
                overlap=overlap,
            )
        )

        index += 1
        start += stride

        # If the next window would start inside the already-captured tail,
        # we are done (no new content to produce).
        if start >= len(text):
            break

    return chunks
