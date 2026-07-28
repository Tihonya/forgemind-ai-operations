"""Unit tests for WP-4.3a DocumentVersion.content field (ORM model only).

Tests SQLAlchemy model definitions without database interaction.
"""
from sqlalchemy import Text, inspect

from app.models.document import DocumentVersion


class TestDocumentVersionContentField:
    """Test DocumentVersion.content field definition."""

    def test_document_version_has_content_attribute(self):
        """DocumentVersion class has 'content' attribute."""
        assert hasattr(DocumentVersion, "content")

    def test_content_field_is_nullable(self):
        """Content field has nullable=True."""
        mapper = inspect(DocumentVersion)
        content_col = mapper.columns.content
        assert content_col.nullable is True

    def test_content_field_has_no_server_default(self):
        """Content field has no server_default."""
        mapper = inspect(DocumentVersion)
        content_col = mapper.columns.content
        assert content_col.server_default is None

    def test_content_field_column_name(self):
        """Mapped column name is 'content'."""
        mapper = inspect(DocumentVersion)
        content_col = mapper.columns.content
        assert content_col.name == "content"

    def test_content_field_type(self):
        """SQLAlchemy column type is Text."""
        mapper = inspect(DocumentVersion)
        content_col = mapper.columns.content
        assert isinstance(content_col.type, Text)

    def test_content_field_in_mapper_columns(self):
        """Content field appears in DocumentVersion mapper columns."""
        mapper = inspect(DocumentVersion)
        column_keys = {c.key for c in mapper.columns}
        assert "content" in column_keys
