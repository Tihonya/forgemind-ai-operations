"""Tests for correlation ID utilities."""

from __future__ import annotations

import uuid

import pytest

from app.core.correlation import (
    CORRELATION_HEADER,
    InvalidCorrelationIdError,
    generate_correlation_id,
    validate_correlation_id,
)


class TestGenerateCorrelationId:
    """Tests for generate_correlation_id()."""

    def test_returns_valid_uuid_v4(self) -> None:
        result = generate_correlation_id()
        parsed = uuid.UUID(result)
        assert parsed.version == 4

    def test_returns_lowercase_canonical_form(self) -> None:
        result = generate_correlation_id()
        assert result == result.lower()
        assert len(result) == 36  # UUID with hyphens

    def test_unique_values(self) -> None:
        ids = {generate_correlation_id() for _ in range(100)}
        assert len(ids) == 100


class TestValidateCorrelationId:
    """Tests for validate_correlation_id()."""

    def test_valid_uuid_v4_returned_as_is(self) -> None:
        value = "550e8400-e29b-41d4-a716-446655440000"
        result = validate_correlation_id(value)
        assert result == value

    def test_uppercase_normalizes_to_lowercase(self) -> None:
        value = "550E8400-E29B-41D4-A716-446655440000"
        result = validate_correlation_id(value)
        assert result == value.lower()
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_mixed_case_normalizes_to_lowercase(self) -> None:
        value = "550e8400-E29b-41D4-a716-446655440000"
        result = validate_correlation_id(value)
        assert result == "550e8400-e29b-41d4-a716-446655440000"

    def test_rejects_malformed_string(self) -> None:
        with pytest.raises(InvalidCorrelationIdError):
            validate_correlation_id("not-a-uuid")

    def test_rejects_empty_string(self) -> None:
        with pytest.raises(InvalidCorrelationIdError):
            validate_correlation_id("")

    def test_rejects_truncated_uuid(self) -> None:
        with pytest.raises(InvalidCorrelationIdError):
            validate_correlation_id("550e8400-e29b-41d4")

    def test_rejects_uuid_v1(self) -> None:
        # UUID v1 (time-based) — version field is 1, not 4
        value = "550e8400-e29b-11d4-a716-446655440000"
        with pytest.raises(InvalidCorrelationIdError):
            validate_correlation_id(value)

    def test_rejects_uuid_v3(self) -> None:
        # UUID v3 (MD5 name-based) — version field is 3, not 4
        value = "550e8400-e29b-31d4-a716-446655440000"
        with pytest.raises(InvalidCorrelationIdError):
            validate_correlation_id(value)

    def test_generated_id_passes_validation(self) -> None:
        generated = generate_correlation_id()
        normalized = validate_correlation_id(generated)
        assert normalized == generated


class TestCorrelationHeader:
    """Tests for the CORRELATION_HEADER constant."""

    def test_header_value(self) -> None:
        assert CORRELATION_HEADER == "X-Correlation-ID"
