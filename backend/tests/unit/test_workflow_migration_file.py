"""Unit tests for the WP-REC-03B workflow migration file.

Inspects the migration file as text and as a Python module without
requiring a live database. Follows the same pattern as
test_wp42_migration_file.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

MIGRATION_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "alembic"
    / "versions"
    / "f1a2b3c4d5e6_add_workflow_tables.py"
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
    def test_migration_file_exists(self) -> None:
        assert MIGRATION_FILE.exists(), f"Migration file not found: {MIGRATION_FILE}"


class TestMigrationRevisionIds:
    def test_revision_is_f1a2b3c4d5e6(self) -> None:
        source = _read_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "revision":
                        assert isinstance(node.value, ast.Constant)
                        assert node.value.value == "f1a2b3c4d5e6"

    def test_down_revision_is_625c9f549f2b(self) -> None:
        source = _read_source()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "down_revision":
                        assert isinstance(node.value, ast.Constant)
                        assert node.value.value == "625c9f549f2b"


class TestMigrationUpgradeTables:
    def test_workflow_runs_table_created(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert "create_table" in upgrade
        assert '"workflow_runs"' in upgrade

    def test_workflow_steps_table_created(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"workflow_steps"' in upgrade

    def test_recommendations_table_created(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"recommendations"' in upgrade


class TestMigrationUpgradeColumns:
    def test_workflow_runs_has_id_column(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"id"' in upgrade

    def test_workflow_runs_has_correlation_id(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"correlation_id"' in upgrade

    def test_workflow_runs_has_state_column(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"state"' in upgrade

    def test_workflow_runs_has_plan_id(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"plan_id"' in upgrade

    def test_workflow_runs_has_error_code(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"error_code"' in upgrade

    def test_workflow_runs_has_error_detail(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"error_detail"' in upgrade

    def test_workflow_steps_has_run_id(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"run_id"' in upgrade

    def test_workflow_steps_has_step_name(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"step_name"' in upgrade

    def test_workflow_steps_has_model_name(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"model_name"' in upgrade

    def test_workflow_steps_has_token_usage(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"token_usage"' in upgrade

    def test_recommendations_has_content_column(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"content"' in upgrade

    def test_recommendations_has_schema_version(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"schema_version"' in upgrade


class TestMigrationUpgradeConstraints:
    def test_workflow_runs_state_check_constraint(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert "ck_workflow_runs_state" in upgrade

    def test_workflow_steps_status_check_constraint(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert "ck_workflow_steps_status" in upgrade

    def test_recommendations_status_check_constraint(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert "ck_recommendations_status" in upgrade

    def test_recommendations_run_id_unique(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert "uq_recommendations_run_id" in upgrade


class TestMigrationUpgradeForeignKeys:
    def test_workflow_runs_fk_to_production_plans(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"production_plans.id"' in upgrade

    def test_workflow_steps_fk_to_workflow_runs(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert '"workflow_runs.id"' in upgrade

    def test_recommendations_fk_to_workflow_runs(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        # recommendations table has FK to workflow_runs.id
        assert '"workflow_runs.id"' in upgrade


class TestMigrationUpgradeIndexes:
    def test_workflow_runs_correlation_id_index(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert "idx_workflow_runs_correlation_id" in upgrade

    def test_workflow_runs_state_index(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert "idx_workflow_runs_state" in upgrade

    def test_workflow_steps_run_id_seq_index(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert "idx_workflow_steps_run_id_seq" in upgrade

    def test_recommendations_run_id_index(self) -> None:
        upgrade = _get_upgrade_body(_read_source())
        assert "idx_recommendations_run_id" in upgrade


class TestMigrationDowngradeOrder:
    def test_drop_order_recommendations_before_workflow_runs(self) -> None:
        """recommendations must be dropped before workflow_runs (FK dependency)."""
        downgrade = _get_downgrade_body(_read_source())
        rec_pos = downgrade.index("recommendations")
        runs_pos = downgrade.index("workflow_runs")
        assert rec_pos < runs_pos, (
            "recommendations must be dropped before workflow_runs"
        )

    def test_drop_steps_before_runs(self) -> None:
        """workflow_steps must be dropped before workflow_runs (FK dependency)."""
        downgrade = _get_downgrade_body(_read_source())
        steps_pos = downgrade.index('"workflow_steps"')
        runs_pos = downgrade.index('"workflow_runs"')
        assert steps_pos < runs_pos, (
            "workflow_steps must be dropped before workflow_runs"
        )

    def test_all_three_tables_dropped_in_downgrade(self) -> None:
        downgrade = _get_downgrade_body(_read_source())
        assert "drop_table" in downgrade
        assert '"recommendations"' in downgrade
        assert '"workflow_steps"' in downgrade
        assert '"workflow_runs"' in downgrade

    def test_indexes_dropped_before_tables(self) -> None:
        """Indexes must be dropped before their parent tables."""
        downgrade = _get_downgrade_body(_read_source())
        # Find the first drop_index and first drop_table
        drop_index_pos = downgrade.index("drop_index")
        drop_table_pos = downgrade.index("drop_table")
        assert drop_index_pos < drop_table_pos, (
            "drop_index must precede drop_table in downgrade"
        )


class TestMigrationNoLangGraph:
    def test_no_langgraph_imports(self) -> None:
        source = _read_source()
        assert "langgraph" not in source.lower()

    def test_no_arq_imports(self) -> None:
        source = _read_source()
        assert "arq" not in source.lower()
