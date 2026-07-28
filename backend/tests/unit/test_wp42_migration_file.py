"""Unit tests for WP-4.2 knowledge_chunks migration file.

Inspects the migration file as text and as a Python module without
executing it against a live database.
"""
import ast
from pathlib import Path

MIGRATION_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "alembic" / "versions"
    / "c7d8e9f0a1b2_add_knowledge_chunks_schema.py"
)


def _read_source() -> str:
    return MIGRATION_FILE.read_text(encoding="utf-8")


def _get_upgrade_body(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return ast.get_source_segment(source, node) or ""
    return ""


def _get_downgrade_body(source: str) -> str:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "downgrade":
            return ast.get_source_segment(source, node) or ""
    return ""


class TestMigrationFileExists:
    def test_migration_file_exists(self):
        assert MIGRATION_FILE.exists(), f"Migration file not found: {MIGRATION_FILE}"


class TestMigrationRevisionIds:
    def test_revision_is_c7d8e9f0a1b2(self):
        source = _read_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "revision":
                        assert isinstance(node.value, ast.Constant)
                        assert node.value.value == "c7d8e9f0a1b2"

    def test_down_revision_is_a1b2c3d4e5f6(self):
        source = _read_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "down_revision":
                        assert isinstance(node.value, ast.Constant)
                        assert node.value.value == "a1b2c3d4e5f6"


class TestMigrationUpgradeCreateExtension:
    def test_create_extension_if_not_exists_vector_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert "CREATE EXTENSION IF NOT EXISTS vector" in upgrade

    def test_extension_creation_precedes_table_creation(self):
        upgrade = _get_upgrade_body(_read_source())
        ext_pos = upgrade.index("CREATE EXTENSION IF NOT EXISTS vector")
        table_pos = upgrade.index("create_table")
        assert ext_pos < table_pos, (
            "CREATE EXTENSION must precede create_table in upgrade"
        )


class TestMigrationUpgradeTable:
    def test_knowledge_chunks_table_created(self):
        upgrade = _get_upgrade_body(_read_source())
        assert 'create_table' in upgrade
        assert '"knowledge_chunks"' in upgrade

    def test_id_column_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert '"id"' in upgrade

    def test_document_version_id_column_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert '"document_version_id"' in upgrade

    def test_chunk_index_column_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert '"chunk_index"' in upgrade

    def test_chunk_text_column_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert '"chunk_text"' in upgrade

    def test_token_count_column_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert '"token_count"' in upgrade

    def test_metadata_column_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert '"metadata"' in upgrade

    def test_content_hash_column_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert '"content_hash"' in upgrade

    def test_embedding_column_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert '"embedding"' in upgrade

    def test_created_at_column_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert '"created_at"' in upgrade

    def test_vector_1536_column(self):
        upgrade = _get_upgrade_body(_read_source())
        assert "Vector(1536)" in upgrade


class TestMigrationUpgradeForeignKey:
    def test_fk_to_document_versions_id_with_cascade(self):
        upgrade = _get_upgrade_body(_read_source())
        assert '"document_versions.id"' in upgrade
        assert 'ondelete="CASCADE"' in upgrade


class TestMigrationUpgradeConstraints:
    def test_unique_constraint_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert "uq_knowledge_chunks_document_version_id_chunk_index" in upgrade


class TestMigrationUpgradeIndexes:
    def test_ordinary_btree_index_present(self):
        upgrade = _get_upgrade_body(_read_source())
        assert "ix_knowledge_chunks_document_version_id" in upgrade

    def test_no_hnsw_declaration(self):
        upgrade = _get_upgrade_body(_read_source())
        assert "hnsw" not in upgrade.lower()

    def test_no_ivfflat_declaration(self):
        upgrade = _get_upgrade_body(_read_source())
        assert "ivfflat" not in upgrade.lower()


class TestMigrationDowngradeOrder:
    def test_drop_index_before_drop_table(self):
        downgrade = _get_downgrade_body(_read_source())
        drop_index_pos = downgrade.index("drop_index")
        drop_table_pos = downgrade.index("drop_table")
        assert drop_index_pos < drop_table_pos, (
            "drop_index must precede drop_table in downgrade"
        )

    def test_extension_not_dropped_in_downgrade(self):
        downgrade = _get_downgrade_body(_read_source())
        assert "DROP EXTENSION" not in downgrade.upper()
        assert "drop_extension" not in downgrade.lower()
