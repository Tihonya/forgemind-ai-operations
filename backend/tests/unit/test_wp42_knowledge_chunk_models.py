"""Unit tests for WP-4.2 knowledge_chunks model (KnowledgeChunk)."""
from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Integer, String, Text, inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID

from app.models import KnowledgeChunk
from app.models.document import DocumentVersion


class TestKnowledgeChunkTableName:
    def test_table_name(self):
        assert KnowledgeChunk.__tablename__ == "knowledge_chunks"


class TestKnowledgeChunkColumns:
    def test_all_nine_columns_present(self):
        mapper = inspect(KnowledgeChunk)
        columns = {c.key for c in mapper.columns}
        expected = {
            "id",
            "document_version_id",
            "chunk_index",
            "chunk_text",
            "token_count",
            "metadata",
            "content_hash",
            "embedding",
            "created_at",
        }
        assert columns == expected

    def test_id_type_is_uuid(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.id
        assert isinstance(col.type, PGUUID)
        assert col.type.as_uuid is True

    def test_document_version_id_type_is_uuid(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.document_version_id
        assert isinstance(col.type, PGUUID)
        assert col.type.as_uuid is True

    def test_chunk_index_type_is_integer(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.chunk_index
        assert isinstance(col.type, Integer)

    def test_chunk_text_type_is_text(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.chunk_text
        assert isinstance(col.type, Text)

    def test_token_count_type_is_integer(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.token_count
        assert isinstance(col.type, Integer)

    def test_chunk_metadata_type_is_jsonb(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.chunk_metadata
        assert isinstance(col.type, JSONB)

    def test_content_hash_type_is_string_64(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.content_hash
        assert isinstance(col.type, String)
        assert col.type.length == 64

    def test_embedding_type_is_vector_1536(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.embedding
        assert isinstance(col.type, Vector)
        assert col.type.dim == 1536

    def test_created_at_type_is_datetime_tz(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.created_at
        assert isinstance(col.type, DateTime)
        assert col.type.timezone is True


class TestKnowledgeChunkPythonAttributeMetadata:
    def test_python_attribute_is_chunk_metadata(self):
        mapper = inspect(KnowledgeChunk)
        assert hasattr(mapper.columns, "chunk_metadata")

    def test_db_column_name_is_metadata(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.chunk_metadata
        # The mapped_column("metadata", ...) means the physical column name is "metadata"
        assert col.name == "metadata"


class TestKnowledgeChunkNullability:
    def test_id_not_nullable(self):
        mapper = inspect(KnowledgeChunk)
        assert mapper.columns.id.nullable is False

    def test_document_version_id_not_nullable(self):
        mapper = inspect(KnowledgeChunk)
        assert mapper.columns.document_version_id.nullable is False

    def test_chunk_index_not_nullable(self):
        mapper = inspect(KnowledgeChunk)
        assert mapper.columns.chunk_index.nullable is False

    def test_chunk_text_not_nullable(self):
        mapper = inspect(KnowledgeChunk)
        assert mapper.columns.chunk_text.nullable is False

    def test_token_count_nullable(self):
        mapper = inspect(KnowledgeChunk)
        assert mapper.columns.token_count.nullable is True

    def test_chunk_metadata_nullable(self):
        mapper = inspect(KnowledgeChunk)
        assert mapper.columns.chunk_metadata.nullable is True

    def test_content_hash_nullable(self):
        mapper = inspect(KnowledgeChunk)
        assert mapper.columns.content_hash.nullable is True

    def test_embedding_nullable(self):
        mapper = inspect(KnowledgeChunk)
        assert mapper.columns.embedding.nullable is True

    def test_created_at_not_nullable(self):
        mapper = inspect(KnowledgeChunk)
        assert mapper.columns.created_at.nullable is False


class TestKnowledgeChunkPrimaryKey:
    def test_primary_key_is_id(self):
        mapper = inspect(KnowledgeChunk)
        pk_columns = {c.key for c in mapper.primary_key}
        assert pk_columns == {"id"}


class TestKnowledgeChunkServerDefaults:
    def test_id_server_default_is_gen_random_uuid(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.id
        assert col.server_default is not None
        assert "gen_random_uuid" in str(col.server_default.arg)

    def test_created_at_server_default_is_now(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.created_at
        assert col.server_default is not None
        assert "now" in str(col.server_default.arg)


class TestKnowledgeChunkForeignKey:
    def test_fk_target_is_document_versions_id(self):
        mapper = inspect(KnowledgeChunk)
        fk_cols = list(mapper.columns.document_version_id.foreign_keys)
        assert len(fk_cols) == 1
        assert fk_cols[0].target_fullname == "document_versions.id"

    def test_fk_ondelete_is_cascade(self):
        mapper = inspect(KnowledgeChunk)
        fk_cols = list(mapper.columns.document_version_id.foreign_keys)
        assert len(fk_cols) == 1
        assert fk_cols[0].ondelete == "CASCADE"


class TestKnowledgeChunkUniqueConstraint:
    def test_unique_constraint_on_document_version_id_chunk_index(self):
        tbl = KnowledgeChunk.__table__
        indexes = {idx.name: idx for idx in tbl.indexes}
        uq_name = "uq_knowledge_chunks_document_version_id_chunk_index"
        assert uq_name in indexes
        idx = indexes[uq_name]
        assert idx.unique is True
        cols = {c.name for c in idx.columns}
        assert cols == {"document_version_id", "chunk_index"}


class TestKnowledgeChunkIndexes:
    def test_btree_index_on_document_version_id_exists(self):
        tbl = KnowledgeChunk.__table__
        index_names = {idx.name for idx in tbl.indexes}
        assert "ix_knowledge_chunks_document_version_id" in index_names

    def test_no_hnsw_index(self):
        tbl = KnowledgeChunk.__table__
        for idx in tbl.indexes:
            # Check that no index has hnsw in its kwargs (pgvector ANN index)
            kwargs = getattr(idx, "kwargs", {})
            assert "hnsw" not in str(kwargs).lower()

    def test_no_ivfflat_index(self):
        tbl = KnowledgeChunk.__table__
        for idx in tbl.indexes:
            kwargs = getattr(idx, "kwargs", {})
            assert "ivfflat" not in str(kwargs).lower()


class TestKnowledgeChunkRelationships:
    def test_document_version_relationship_exists(self):
        mapper = inspect(KnowledgeChunk)
        rel_names = {r.key for r in mapper.relationships}
        assert "document_version" in rel_names

    def test_document_version_relationship_target_is_document_version(self):
        mapper = inspect(KnowledgeChunk)
        rel = mapper.relationships["document_version"]
        assert rel.mapper.class_ == DocumentVersion

    def test_document_version_has_no_chunks_back_populates(self):
        mapper = inspect(DocumentVersion)
        rel_names = {r.key for r in mapper.relationships}
        assert "chunks" not in rel_names


class TestKnowledgeChunkExport:
    def test_knowledge_chunk_in_app_models_all(self):
        from app.models import __all__

        assert "KnowledgeChunk" in __all__


class TestKnowledgeChunkChunkIndexComment:
    def test_chunk_index_comment_is_zero_based(self):
        mapper = inspect(KnowledgeChunk)
        col = mapper.columns.chunk_index
        assert col.comment == "zero-based"
