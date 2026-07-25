"""Unit tests for CORS origins configuration parsing."""

import pytest
from pydantic import ValidationError

from app.config import Settings


class TestCORSParsing:
    """Test suite for CORS origins environment variable parsing."""

    def test_comma_separated_origins(self, monkeypatch):
        """Test parsing comma-separated origin strings."""
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost,http://example.com")
        settings = Settings()
        assert settings.cors_origins == ["http://localhost", "http://example.com"]

    def test_json_array_double_quoted(self, monkeypatch):
        """Test parsing JSON array with double quotes."""
        monkeypatch.setenv("CORS_ORIGINS", '["http://localhost", "http://example.com"]')
        settings = Settings()
        assert settings.cors_origins == ["http://localhost", "http://example.com"]

    def test_json_array_single_quoted_in_python(self, monkeypatch):
        """Test parsing JSON array (Python literal with single quotes becomes string)."""
        # When set via os.environ, this is a string representation
        monkeypatch.setenv("CORS_ORIGINS", '["http://localhost", "http://example.com"]')
        settings = Settings()
        assert settings.cors_origins == ["http://localhost", "http://example.com"]

    def test_empty_string_returns_empty_list(self, monkeypatch):
        """Test that empty CORS_ORIGINS returns empty list, not default."""
        monkeypatch.setenv("CORS_ORIGINS", "")
        settings = Settings()
        assert settings.cors_origins == []

    def test_whitespace_only_string_returns_empty_list(self, monkeypatch):
        """Test that whitespace-only CORS_ORIGINS returns empty list."""
        monkeypatch.setenv("CORS_ORIGINS", "   ")
        settings = Settings()
        assert settings.cors_origins == []

    def test_whitespace_around_commas_is_trimmed(self, monkeypatch):
        """Test that whitespace around commas is properly trimmed."""
        monkeypatch.setenv("CORS_ORIGINS", " http://localhost , http://example.com ")
        settings = Settings()
        assert settings.cors_origins == ["http://localhost", "http://example.com"]

    def test_single_origin(self, monkeypatch):
        """Test parsing single origin (no commas)."""
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost")
        settings = Settings()
        assert settings.cors_origins == ["http://localhost"]

    def test_wildcard_origin(self, monkeypatch):
        """Test that wildcard origin is accepted."""
        monkeypatch.setenv("CORS_ORIGINS", "*")
        settings = Settings()
        assert settings.cors_origins == ["*"]

    def test_default_value(self, monkeypatch):
        """Test default CORS origins when env var is not set."""
        monkeypatch.delenv("CORS_ORIGINS", raising=False)
        settings = Settings()
        assert settings.cors_origins == ["http://localhost:5173", "http://localhost:3000"]

    def test_ci_exact_value(self, monkeypatch):
        """Test exact value used in CI environment."""
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost")
        settings = Settings()
        # Should parse as single-item list, not empty list
        assert settings.cors_origins == ["http://localhost"]
        assert len(settings.cors_origins) == 1


class TestCORSErrors:
    """Test CORS origins validation error cases."""

    def test_invalid_json_array_rejected(self, monkeypatch):
        """Test that malformed JSON array raises validation error."""
        monkeypatch.setenv("CORS_ORIGINS", '["http://localhost",')
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "cors_origins" in str(exc_info.value)

    def test_json_non_array_rejected(self, monkeypatch):
        """Test that JSON object (not array) raises validation error."""
        monkeypatch.setenv("CORS_ORIGINS", '{"origins": ["http://localhost"]}')
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "cors_origins" in str(exc_info.value)

    def test_json_array_with_non_string_rejected(self, monkeypatch):
        """Test that JSON array with non-string items raises validation error."""
        monkeypatch.setenv("CORS_ORIGINS", "[42, 100]")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "cors_origins" in str(exc_info.value)

    def test_invalid_origin_scheme_rejected(self, monkeypatch):
        """Test that origins without http/https scheme are rejected."""
        monkeypatch.setenv("CORS_ORIGINS", "ftp://example.com")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "cors_origins" in str(exc_info.value)
        assert "must start with 'http://' or 'https://'" in str(exc_info.value)

    def test_origin_with_path_rejected(self, monkeypatch):
        """Test that origins with path components are rejected."""
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost/api")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "cors_origins" in str(exc_info.value)
        assert "path" in str(exc_info.value).lower()

    def test_origin_with_query_rejected(self, monkeypatch):
        """Test that origins with query strings are rejected."""
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost?param=value")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "cors_origins" in str(exc_info.value)
        assert "query" in str(exc_info.value).lower()

    def test_origin_with_fragment_rejected(self, monkeypatch):
        """Test that origins with fragments are rejected."""
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost#section")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "cors_origins" in str(exc_info.value)
        assert "fragment" in str(exc_info.value).lower()

    def test_invalid_origin_no_scheme_rejected(self, monkeypatch):
        """Test that origins without any scheme are rejected."""
        monkeypatch.setenv("CORS_ORIGINS", "localhost")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "cors_origins" in str(exc_info.value)
        assert "must start with 'http://' or 'https://'" in str(exc_info.value)

    def test_mixed_valid_invalid_origin_rejected(self, monkeypatch):
        """Test that if any origin in a list is invalid, the whole list is rejected."""
        monkeypatch.setenv("CORS_ORIGINS", "http://localhost,invalid.com")
        with pytest.raises(ValidationError) as exc_info:
            Settings()
        assert "cors_origins" in str(exc_info.value)


class TestCORSProgrammaticInit:
    """Test programmatic Settings initialization with lists."""

    def test_direct_list_initialization(self):
        """Test that Settings accepts a list directly."""
        settings = Settings(cors_origins=["http://localhost", "http://example.com"])
        assert settings.cors_origins == ["http://localhost", "http://example.com"]

    def test_direct_list_with_invalid_scheme_rejected(self):
        """Test that programmatic init validates origin schemes."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(cors_origins=["ftp://example.com"])
        assert "cors_origins" in str(exc_info.value)

    def test_direct_list_with_path_rejected(self):
        """Test that programmatic init rejects origins with paths."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(cors_origins=["http://localhost/api"])
        assert "cors_origins" in str(exc_info.value)

    def test_direct_list_with_non_string_rejected(self):
        """Test that programmatic init rejects non-string list items."""
        with pytest.raises(ValidationError):
            Settings(cors_origins=[42, "http://localhost"])  # type: ignore[list-item]
