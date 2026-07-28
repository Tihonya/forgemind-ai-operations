"""Unit tests for WP-4.3a document_version_content migration file structure.

Tests the migration file exists and has the correct revision IDs,
upgrade/downgrade functions, and expected operations — without
requiring a live database.
"""
import ast
import importlib.util
from pathlib import Path


def _load_migration_module():
    """Load the migration module by file path (no alembic context needed).

    Returns:
        Tuple of (module, file_path).
    """
    migration_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    migration_file = migration_dir / "625c9f549f2b_add_document_version_content.py"
    assert migration_file.exists(), f"Migration file not found: {migration_file}"

    spec = importlib.util.spec_from_file_location(
        "migration_module", str(migration_file)
    )
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod, migration_file


def _read_migration_source():
    """Read the raw source of the migration file."""
    migration_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
    migration_file = migration_dir / "625c9f549f2b_add_document_version_content.py"
    return migration_file.read_text()


def _parse_migration_tree():
    """Parse the migration source into an AST."""
    return ast.parse(_read_migration_source())


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef:
    """Return the top-level function node with *name*, or raise."""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"Function '{name}' not found in migration AST")


def _call_args(calls: list[ast.Call]) -> list[ast.Constant]:
    """Extract the first positional argument from each call (must be a str const)."""
    args: list[ast.Constant] = []
    for call in calls:
        for arg in call.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                args.append(arg)
                break
    return args


def _collect_calls(tree, func_name: str):
    """Walk *tree* and collect all ``Call`` nodes whose func is ``op.<func_name>``."""
    calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "op"
                and func.attr == func_name
            ):
                calls.append(node)
    return calls


class TestMigrationFileStructure:
    """Test migration file exists and has correct metadata."""

    def test_migration_file_exists(self):
        """Verify migration file exists at expected path."""
        migration_dir = Path(__file__).resolve().parents[2] / "alembic" / "versions"
        migration_file = migration_dir / "625c9f549f2b_add_document_version_content.py"
        assert migration_file.exists(), f"Migration file not found: {migration_file}"

    def test_migration_revision_id(self):
        """Verify revision ID is 625c9f549f2b."""
        mod, _ = _load_migration_module()
        assert mod.revision == "625c9f549f2b"

    def test_migration_down_revision(self):
        """Verify down_revision is c7d8e9f0a1b2."""
        mod, _ = _load_migration_module()
        assert mod.down_revision == "c7d8e9f0a1b2"

    def test_migration_upgrade_function(self):
        """Verify upgrade() function exists and is callable."""
        mod, _ = _load_migration_module()
        assert hasattr(mod, "upgrade")
        assert callable(mod.upgrade)

    def test_migration_downgrade_function(self):
        """Verify downgrade() function exists and is callable."""
        mod, _ = _load_migration_module()
        assert hasattr(mod, "downgrade")
        assert callable(mod.downgrade)


class TestMigrationUpgradeOperations:
    """Test that upgrade adds the content column."""

    def test_migration_upgrade_adds_content_column(self):
        """Verify upgrade() adds content column to document_versions.

        Uses AST to inspect the upgrade function — quote-style agnostic.
        """
        tree = _parse_migration_tree()
        upgrade_fn = _find_function(tree, "upgrade")

        # Collect op.add_column calls inside the upgrade function
        add_column_calls = _collect_calls(upgrade_fn, "add_column")
        assert add_column_calls, "upgrade() should call op.add_column"

        # The first positional arg of add_column is the table name
        table_args = _call_args(add_column_calls)
        assert any(
            arg.value == "document_versions" for arg in table_args
        ), (
            "upgrade() should target 'document_versions' table via op.add_column"
        )

        # Check that 'content' and Text appear somewhere in the upgrade body
        upgrade_body = ast.unparse(upgrade_fn)
        assert "content" in upgrade_body, (
            "upgrade() should add 'content' column"
        )
        assert "Text" in upgrade_body, (
            "upgrade() should specify Text type for content column"
        )


class TestMigrationDowngradeOperations:
    """Test that downgrade drops the content column."""

    def test_migration_downgrade_drops_content_column(self):
        """Verify downgrade() drops content column from document_versions.

        Uses AST to inspect the downgrade function — quote-style agnostic.
        """
        tree = _parse_migration_tree()
        downgrade_fn = _find_function(tree, "downgrade")

        # Collect op.drop_column calls inside the downgrade function
        drop_column_calls = _collect_calls(downgrade_fn, "drop_column")
        assert drop_column_calls, "downgrade() should call op.drop_column"

        # The first positional arg is the table name
        table_args = _call_args(drop_column_calls)
        assert any(
            arg.value == "document_versions" for arg in table_args
        ), (
            "downgrade() should target 'document_versions' table via op.drop_column"
        )

        # The second positional arg is the column name
        for call in drop_column_calls:
            col_args = [
                a
                for a in call.args
                if isinstance(a, ast.Constant) and isinstance(a.value, str)
            ]
            assert any(
                arg.value == "content" for arg in col_args
            ), (
                "downgrade() should drop 'content' column"
            )
