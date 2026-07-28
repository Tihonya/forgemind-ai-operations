"""Focused unit tests for the chunking service."""

from __future__ import annotations

import hashlib
from dataclasses import FrozenInstanceError

import pytest
import tiktoken

from app.services.chunking import chunk_text

_ENCODER = tiktoken.get_encoding("cl100k_base")

# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------

class TestParameterValidation:
    def test_zero_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size"):
            chunk_text("hello", chunk_size=0)

    def test_negative_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size"):
            chunk_text("hello", chunk_size=-1)

    def test_negative_overlap_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            chunk_text("hello", chunk_size=100, overlap=-1)

    def test_overlap_equal_to_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            chunk_text("hello", chunk_size=100, overlap=100)

    def test_overlap_greater_than_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            chunk_text("hello", chunk_size=100, overlap=200)

    def test_zero_overlap_is_allowed(self) -> None:
        result = chunk_text("hello world", chunk_size=5, overlap=0)
        # Two non-overlapping chunks: "hello", " worl", "d" (stride=5)
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Empty / short text
# ---------------------------------------------------------------------------

class TestEmptyAndShortText:
    def test_empty_string_returns_no_chunks(self) -> None:
        result = chunk_text("")
        assert result == []

    def test_shorter_than_chunk_size_returns_one_chunk(self) -> None:
        text = "short"
        result = chunk_text(text, chunk_size=100, overlap=0)
        assert len(result) == 1
        assert result[0].chunk_text == text

    def test_exactly_chunk_size_returns_one_chunk(self) -> None:
        text = "x" * 100
        result = chunk_text(text, chunk_size=100, overlap=0)
        assert len(result) == 1
        assert result[0].chunk_text == text


# ---------------------------------------------------------------------------
# Chunking behavior
# ---------------------------------------------------------------------------

class TestChunkingBehavior:
    def test_single_chunk_text(self) -> None:
        text = "A" * 50
        result = chunk_text(text, chunk_size=100, overlap=0)
        assert len(result) == 1
        assert result[0].chunk_text == text

    def test_two_chunks_with_overlap(self) -> None:
        text = "A" * 1500
        result = chunk_text(text, chunk_size=1000, overlap=200)
        assert len(result) == 2
        assert result[0].chunk_text == "A" * 1000
        assert result[1].chunk_text == "A" * 700  # 1500 - 800 = 700

    def test_three_chunks(self) -> None:
        text = "A" * 2600
        result = chunk_text(text, chunk_size=1000, overlap=200)
        # stride=800: [0:1000], [800:1800], [1600:2600], [2400:2600]
        assert len(result) == 4
        assert result[0].chunk_text == "A" * 1000
        assert result[1].chunk_text == "A" * 1000
        assert result[2].chunk_text == "A" * 1000
        assert result[3].chunk_text == "A" * 200

    def test_no_overlap_chunks(self) -> None:
        text = "A" * 3005
        result = chunk_text(text, chunk_size=1000, overlap=0)
        assert len(result) == 4
        assert result[0].chunk_text == "A" * 1000
        assert result[1].chunk_text == "A" * 1000
        assert result[2].chunk_text == "A" * 1000
        assert result[3].chunk_text == "A" * 5

    def test_last_chunk_can_be_shorter(self) -> None:
        text = "A" * 1050
        result = chunk_text(text, chunk_size=1000, overlap=0)
        assert len(result) == 2
        assert len(result[0].chunk_text) == 1000
        assert len(result[1].chunk_text) == 50


# ---------------------------------------------------------------------------
# Chunk index ordering
# ---------------------------------------------------------------------------

class TestChunkIndexing:
    def test_zero_based_sequential_index(self) -> None:
        text = "A" * 3000
        result = chunk_text(text, chunk_size=1000, overlap=0)
        assert [c.chunk_index for c in result] == [0, 1, 2]

    def test_single_chunk_has_index_zero(self) -> None:
        result = chunk_text("hello", chunk_size=100, overlap=0)
        assert result[0].chunk_index == 0


# ---------------------------------------------------------------------------
# Content hash
# ---------------------------------------------------------------------------

class TestContentHash:
    def test_sha256_hash_is_deterministic(self) -> None:
        text = "hello world"
        result = chunk_text(text, chunk_size=100, overlap=0)
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert result[0].content_hash == expected

    def test_different_chunks_have_different_hashes(self) -> None:
        text = "A" * 1000 + "B" * 1000
        result = chunk_text(text, chunk_size=1000, overlap=0)
        assert result[0].content_hash != result[1].content_hash

    def test_same_text_same_hash_across_calls(self) -> None:
        text = "deterministic"
        r1 = chunk_text(text, chunk_size=100, overlap=0)
        r2 = chunk_text(text, chunk_size=100, overlap=0)
        assert r1[0].content_hash == r2[0].content_hash


# ---------------------------------------------------------------------------
# Token count
# ---------------------------------------------------------------------------

class TestTokenCount:
    def test_token_count_is_deterministic(self) -> None:
        text = "hello world"
        result = chunk_text(text, chunk_size=100, overlap=0)
        expected = len(_ENCODER.encode("hello world"))
        assert result[0].token_count == expected

    def test_token_count_matches_tiktoken(self) -> None:
        text = "The quick brown fox jumps over the lazy dog."
        result = chunk_text(text, chunk_size=200, overlap=0)
        assert result[0].token_count == len(_ENCODER.encode(text))

    def test_token_count_reproducible_across_calls(self) -> None:
        text = "reproducible token count test"
        r1 = chunk_text(text)
        r2 = chunk_text(text)
        assert r1[0].token_count == r2[0].token_count


# ---------------------------------------------------------------------------
# ChunkData attributes
# ---------------------------------------------------------------------------

class TestChunkDataAttributes:
    def test_chunk_size_and_overlap_reflected(self) -> None:
        text = "A" * 2000
        result = chunk_text(text, chunk_size=800, overlap=300)
        for chunk in result:
            assert chunk.chunk_size == 800
            assert chunk.overlap == 300

    def test_chunk_text_is_correct_length(self) -> None:
        text = "A" * 2500
        result = chunk_text(text, chunk_size=1000, overlap=200)
        # stride=800: [0:1000], [800:1800], [1600:2500], [2400:2500]
        assert len(result) == 4
        assert len(result[0].chunk_text) == 1000
        assert len(result[1].chunk_text) == 1000
        assert len(result[2].chunk_text) == 900
        assert len(result[3].chunk_text) == 100

    def test_chunk_text_concatenation_preserves_content_with_overlap(self) -> None:
        text = "ABCDEF"
        result = chunk_text(text, chunk_size=4, overlap=2)
        # stride=2, chunks: [0:4]=ABCD, [2:6]=CDEF
        assert result[0].chunk_text == "ABCD"
        assert result[1].chunk_text == "CDEF"

    def test_chunk_data_is_frozen(self) -> None:
        text = "hello"
        result = chunk_text(text, chunk_size=100, overlap=0)
        with pytest.raises(FrozenInstanceError):
            result[0].chunk_text = "modified"  # type: ignore


# ---------------------------------------------------------------------------
# Determinism end-to-end
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_full_deterministic_output(self) -> None:
        text = "Deterministic output test with enough text to produce multiple chunks." * 10
        params = {"chunk_size": 500, "overlap": 100}
        r1 = chunk_text(text, **params)
        r2 = chunk_text(text, **params)

        assert len(r1) == len(r2)
        for c1, c2 in zip(r1, r2, strict=True):
            assert c1.chunk_index == c2.chunk_index
            assert c1.chunk_text == c2.chunk_text
            assert c1.content_hash == c2.content_hash
            assert c1.token_count == c2.token_count
            assert c1.chunk_size == c2.chunk_size
            assert c1.overlap == c2.overlap

    def test_no_python_hash_used(self) -> None:
        """Ensure hash() is never used — only hashlib.sha256."""
        text = "test"
        result = chunk_text(text)
        # If Python hash() were used, the value would be random per process.
        # Our implementation uses sha256, so it is deterministic.
        expected = hashlib.sha256(b"test").hexdigest()
        assert result[0].content_hash == expected
