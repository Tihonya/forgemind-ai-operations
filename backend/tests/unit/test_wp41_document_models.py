"""Unit tests for WP-4.1 document schema models.

Tests SQLAlchemy model definitions without database interaction.
"""
from typing import cast

from sqlalchemy import String, Table, inspect

from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.enums import DocumentVersionStatus


class TestDocumentModel:
    """Test Document model definition."""

    def test_document_table_name(self):
        """Document table name is 'documents'."""
        assert Document.__tablename__ == "documents"

    def test_document_columns(self):
        """Document has expected columns."""
        mapper = inspect(Document)
        columns = {c.key for c in mapper.columns}
        expected = {"id", "title", "description", "created_at", "updated_at"}
        assert columns == expected

    def test_document_id_primary_key(self):
        """Document.id is primary key."""
        mapper = inspect(Document)
        pk_columns = {c.key for c in mapper.primary_key}
        assert pk_columns == {"id"}

    def test_document_title_not_nullable(self):
        """Document.title is NOT NULL."""
        mapper = inspect(Document)
        title_col = mapper.columns.title
        assert title_col.nullable is False

    def test_document_title_max_length(self):
        """Document.title has max length 500."""
        mapper = inspect(Document)
        title_col = mapper.columns.title
        assert cast(String, title_col.type).length == 500

    def test_document_description_nullable(self):
        """Document.description is nullable."""
        mapper = inspect(Document)
        desc_col = mapper.columns.description
        assert desc_col.nullable is True

    def test_document_timestamps_not_nullable(self):
        """Document timestamps are NOT NULL."""
        mapper = inspect(Document)
        assert mapper.columns.created_at.nullable is False
        assert mapper.columns.updated_at.nullable is False

    def test_document_relationships(self):
        """Document has versions and permissions relationships."""
        mapper = inspect(Document)
        relationships = {r.key for r in mapper.relationships}
        assert relationships == {"versions", "permissions"}


class TestDocumentVersionModel:
    """Test DocumentVersion model definition."""

    def test_document_version_table_name(self):
        """DocumentVersion table name is 'document_versions'."""
        assert DocumentVersion.__tablename__ == "document_versions"

    def test_document_version_columns(self):
        """DocumentVersion has expected columns."""
        mapper = inspect(DocumentVersion)
        columns = {c.key for c in mapper.columns}
        expected = {
            "id",
            "document_id",
            "version_number",
            "status",
            "content_hash",
            "content",
            "created_at",
        }
        assert columns == expected

    def test_document_version_id_primary_key(self):
        """DocumentVersion.id is primary key."""
        mapper = inspect(DocumentVersion)
        pk_columns = {c.key for c in mapper.primary_key}
        assert pk_columns == {"id"}

    def test_document_version_document_id_foreign_key(self):
        """DocumentVersion.document_id references documents.id."""
        mapper = inspect(DocumentVersion)
        fk_columns = list(mapper.columns.document_id.foreign_keys)
        assert len(fk_columns) == 1
        fk_target = fk_columns[0].target_fullname
        assert fk_target == "documents.id"

    def test_document_version_document_id_not_nullable(self):
        """DocumentVersion.document_id is NOT NULL."""
        mapper = inspect(DocumentVersion)
        doc_id_col = mapper.columns.document_id
        assert doc_id_col.nullable is False

    def test_document_version_version_number_not_nullable(self):
        """DocumentVersion.version_number is NOT NULL."""
        mapper = inspect(DocumentVersion)
        vn_col = mapper.columns.version_number
        assert vn_col.nullable is False

    def test_document_version_version_number_max_length(self):
        """DocumentVersion.version_number has max length 50."""
        mapper = inspect(DocumentVersion)
        vn_col = mapper.columns.version_number
        assert cast(String, vn_col.type).length == 50

    def test_document_version_status_not_nullable(self):
        """DocumentVersion.status is NOT NULL."""
        mapper = inspect(DocumentVersion)
        status_col = mapper.columns.status
        assert status_col.nullable is False

    def test_document_version_content_hash_nullable(self):
        """DocumentVersion.content_hash is nullable."""
        mapper = inspect(DocumentVersion)
        hash_col = mapper.columns.content_hash
        assert hash_col.nullable is True

    def test_document_version_content_hash_max_length(self):
        """DocumentVersion.content_hash has max length 64."""
        mapper = inspect(DocumentVersion)
        hash_col = mapper.columns.content_hash
        assert cast(String, hash_col.type).length == 64

    def test_document_version_indexes(self):
        """DocumentVersion has expected indexes."""
        tbl = cast(Table, DocumentVersion.__table__)
        indexes = {idx.name for idx in tbl.indexes}
        assert "idx_document_versions_document_id" in indexes

    def test_document_version_relationship(self):
        """DocumentVersion has document relationship."""
        mapper = inspect(DocumentVersion)
        relationships = {r.key for r in mapper.relationships}
        assert relationships == {"document"}


class TestDocumentPermissionModel:
    """Test DocumentPermission model definition."""

    def test_document_permission_table_name(self):
        """DocumentPermission table name is 'document_permissions'."""
        assert DocumentPermission.__tablename__ == "document_permissions"

    def test_document_permission_columns(self):
        """DocumentPermission has expected columns."""
        mapper = inspect(DocumentPermission)
        columns = {c.key for c in mapper.columns}
        expected = {"id", "document_id", "role_id"}
        assert columns == expected

    def test_document_permission_id_primary_key(self):
        """DocumentPermission.id is primary key."""
        mapper = inspect(DocumentPermission)
        pk_columns = {c.key for c in mapper.primary_key}
        assert pk_columns == {"id"}

    def test_document_permission_document_id_foreign_key(self):
        """DocumentPermission.document_id references documents.id."""
        mapper = inspect(DocumentPermission)
        fk_columns = list(mapper.columns.document_id.foreign_keys)
        assert len(fk_columns) == 1
        fk_target = fk_columns[0].target_fullname
        assert fk_target == "documents.id"

    def test_document_permission_role_id_foreign_key(self):
        """DocumentPermission.role_id references roles.id."""
        mapper = inspect(DocumentPermission)
        fk_columns = list(mapper.columns.role_id.foreign_keys)
        assert len(fk_columns) == 1
        fk_target = fk_columns[0].target_fullname
        assert fk_target == "roles.id"

    def test_document_permission_document_id_not_nullable(self):
        """DocumentPermission.document_id is NOT NULL."""
        mapper = inspect(DocumentPermission)
        doc_id_col = mapper.columns.document_id
        assert doc_id_col.nullable is False

    def test_document_permission_role_id_not_nullable(self):
        """DocumentPermission.role_id is NOT NULL."""
        mapper = inspect(DocumentPermission)
        role_id_col = mapper.columns.role_id
        assert role_id_col.nullable is False

    def test_document_permission_unique_constraint(self):
        """DocumentPermission has unique index on (document_id, role_id)."""
        tbl = cast(Table, DocumentPermission.__table__)
        idx_names = {idx.name for idx in tbl.indexes}
        assert "idx_document_permissions_document_id_role_id" in idx_names
        for idx in tbl.indexes:
            if idx.name == "idx_document_permissions_document_id_role_id":
                assert idx.unique is True
                cols = {c.name for c in idx.columns}
                assert cols == {"document_id", "role_id"}
                return

    def test_document_permission_indexes(self):
        """DocumentPermission has expected indexes."""
        tbl = cast(Table, DocumentPermission.__table__)
        indexes = {idx.name for idx in tbl.indexes}
        assert "idx_document_permissions_document_id" in indexes
        assert "idx_document_permissions_role_id" in indexes

    def test_document_permission_relationships(self):
        """DocumentPermission has document and role relationships."""
        mapper = inspect(DocumentPermission)
        relationships = {r.key for r in mapper.relationships}
        assert relationships == {"document", "role"}


class TestDocumentVersionStatusEnum:
    """Test DocumentVersionStatus enum."""

    def test_document_version_status_values(self):
        """DocumentVersionStatus has expected values."""
        expected_values = {"DRAFT", "APPROVED", "OBSOLETE"}
        actual_values = {status.value for status in DocumentVersionStatus}
        assert actual_values == expected_values

    def test_document_version_status_draft(self):
        """DocumentVersionStatus.DRAFT exists."""
        assert DocumentVersionStatus.DRAFT.value == "DRAFT"

    def test_document_version_status_approved(self):
        """DocumentVersionStatus.APPROVED exists."""
        assert DocumentVersionStatus.APPROVED.value == "APPROVED"

    def test_document_version_status_obsolete(self):
        """DocumentVersionStatus.OBSOLETE exists."""
        assert DocumentVersionStatus.OBSOLETE.value == "OBSOLETE"

    def test_document_version_status_is_string(self):
        """DocumentVersionStatus values are strings."""
        for status in DocumentVersionStatus:
            assert isinstance(status.value, str)
