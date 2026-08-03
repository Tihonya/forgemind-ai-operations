#!/usr/bin/env python3
"""
Unit tests for manifest_loader.py — canonical manifest schema validation.

Tests cover:
- Required fields validation
- Schema version and project identity
- Path validation (gitwildmatch, no traversal, no absolute)
- Gate ID validation and override rules
- Repair budget constraints
- Model routing hints (tool-independent)
- Runtime field rejection
- Legacy schema rejection
- Strict top-level field allowlist
"""

import json
import tempfile
from pathlib import Path

import pytest

# Import manifest_loader from parent directory
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
import manifest_loader


# ============================================================================
# FIXTURES
# ============================================================================

def make_minimal_valid_manifest():
    """Return minimal valid manifest with all required fields."""
    return {
        "schema_version": "1.0",
        "project_id": "forgemind",
        "story_id": "TEST-001",
        "title": "Test Story",
        "description": "Test description",
        "base_commit": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        "expected_branch": "test/branch",
        "path_pattern_type": "gitwildmatch",
        "allowed_paths": ["src/**"],
        "forbidden_paths": ["secret/**"],
        "required_gates": ["scope", "json_syntax", "yaml_syntax", "targeted_tests", "lint", "secrets", "git_diff_check"],
        "test_commands": {
            "targeted_args": ["test_file.py", "-v"]
        },
        "environment_requirements": {
            "database": {"required": False, "auto_start": False},
            "redis": {"required": False, "auto_start": False},
            "external_network": {"allowed": False}
        },
        "expected_outputs": ["output.json"],
        "acceptance_criteria": ["Criterion 1"],
        "repair_budget": 3,
        "model_routing_hints": {
            "implementation_role": "implementer",
            "review_role": "reviewer",
            "complexity": "standard",
            "local_worker_allowed": True
        },
        "dependencies": [],
        "conflict_domains": []
    }


def write_temp_manifest(data):
    """Write manifest data to temp file and return path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with open(path, "w") as f:
        json.dump(data, f)
    return path


# ============================================================================
# VALID MANIFEST TESTS
# ============================================================================

def test_valid_manifest_all_required_fields():
    """Valid manifest with all required fields should pass."""
    manifest = make_minimal_valid_manifest()
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
        assert result == "TEST-001"
    finally:
        Path(path).unlink()


def test_valid_manifest_with_optional_gate_overrides():
    """Valid manifest with optional gate_overrides should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["gate_overrides"] = {
        "targeted_tests": {"assertion_gate": True},
        "lint": {"scope_to_diff": True}
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


def test_valid_manifest_with_optional_repair_guidance():
    """Valid manifest with optional repair_guidance should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["repair_guidance"] = ["Guidance 1", "Guidance 2"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


def test_load_manifest_returns_dict():
    """load_manifest should return validated manifest dict."""
    manifest = make_minimal_valid_manifest()
    path = write_temp_manifest(manifest)
    try:
        result = manifest_loader.load_manifest(path)
        assert isinstance(result, dict)
        assert result["story_id"] == "TEST-001"
    finally:
        Path(path).unlink()


# ============================================================================
# SCHEMA VERSION AND PROJECT ID TESTS
# ============================================================================

def test_missing_schema_version():
    """Manifest without schema_version should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["schema_version"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "SCHEMA_VERSION_MISSING" in result
    finally:
        Path(path).unlink()


def test_schema_version_mismatch():
    """Manifest with wrong schema_version should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["schema_version"] = "2.0"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "SCHEMA_VERSION_MISMATCH" in result
    finally:
        Path(path).unlink()


def test_missing_project_id():
    """Manifest without project_id should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["project_id"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PROJECT_ID_MISSING" in result
    finally:
        Path(path).unlink()


def test_project_id_mismatch():
    """Manifest with wrong project_id should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["project_id"] = "other-project"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PROJECT_ID_MISMATCH" in result
    finally:
        Path(path).unlink()


# ============================================================================
# STORY ID TESTS
# ============================================================================

def test_missing_story_id():
    """Manifest without story_id should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["story_id"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "STORY_ID_MISSING" in result
    finally:
        Path(path).unlink()


def test_empty_story_id():
    """Manifest with empty story_id should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["story_id"] = ""
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "STORY_ID_EMPTY" in result
    finally:
        Path(path).unlink()


def test_whitespace_only_story_id():
    """Manifest with whitespace-only story_id should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["story_id"] = "   "
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "STORY_ID_EMPTY" in result
    finally:
        Path(path).unlink()


# ============================================================================
# TITLE AND DESCRIPTION TESTS
# ============================================================================

def test_missing_title():
    """Manifest without title should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["title"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "TITLE_MISSING" in result
    finally:
        Path(path).unlink()


def test_missing_description():
    """Manifest without description should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["description"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "DESCRIPTION_MISSING" in result
    finally:
        Path(path).unlink()


# ============================================================================
# BASE COMMIT TESTS
# ============================================================================

def test_missing_base_commit():
    """Manifest without base_commit should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["base_commit"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "BASE_COMMIT_MISSING" in result
    finally:
        Path(path).unlink()


def test_base_commit_symbolic_HEAD():
    """Manifest with base_commit='HEAD' should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["base_commit"] = "HEAD"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "BASE_COMMIT_SYMBOLIC" in result
    finally:
        Path(path).unlink()


def test_base_commit_symbolic_main():
    """Manifest with base_commit='main' should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["base_commit"] = "main"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "BASE_COMMIT_SYMBOLIC" in result
    finally:
        Path(path).unlink()


def test_base_commit_symbolic_origin():
    """Manifest with base_commit='origin/main' should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["base_commit"] = "origin/main"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "BASE_COMMIT_SYMBOLIC" in result
    finally:
        Path(path).unlink()


def test_base_commit_concrete_SHA():
    """Manifest with concrete SHA should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["base_commit"] = "abcdef1234567890abcdef1234567890abcdef12"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


def test_base_commit_short_SHA():
    """Manifest with short SHA (< 40 chars) should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["base_commit"] = "abc123"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "BASE_COMMIT_INVALID" in result
    finally:
        Path(path).unlink()


def test_base_commit_non_hex():
    """Manifest with non-hex SHA should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["base_commit"] = "xyz" * 13 + "xyz1"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "BASE_COMMIT_INVALID" in result
    finally:
        Path(path).unlink()


# ============================================================================
# EXPECTED BRANCH TESTS
# ============================================================================

def test_missing_expected_branch():
    """Manifest without expected_branch should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["expected_branch"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "EXPECTED_BRANCH_MISSING" in result
    finally:
        Path(path).unlink()


# ============================================================================
# PATH PATTERN TYPE TESTS
# ============================================================================

def test_missing_path_pattern_type():
    """Manifest without path_pattern_type should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["path_pattern_type"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PATH_PATTERN_TYPE_MISSING" in result
    finally:
        Path(path).unlink()


def test_path_pattern_type_unsupported():
    """Manifest with unsupported path_pattern_type should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["path_pattern_type"] = "regex"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PATH_PATTERN_TYPE_UNSUPPORTED" in result
    finally:
        Path(path).unlink()


def test_path_pattern_type_gitwildmatch():
    """Manifest with path_pattern_type='gitwildmatch' should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["path_pattern_type"] = "gitwildmatch"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


# ============================================================================
# PATH VALIDATION TESTS (allowed_paths, forbidden_paths, expected_outputs)
# ============================================================================

def test_missing_allowed_paths():
    """Manifest without allowed_paths should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["allowed_paths"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "ALLOWED_PATHS_MISSING" in result
    finally:
        Path(path).unlink()


def test_allowed_paths_not_array():
    """Manifest with allowed_paths not array should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["allowed_paths"] = "src/**"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "ALLOWED_PATHS_NOT_ARRAY" in result
    finally:
        Path(path).unlink()


def test_allowed_paths_absolute_path():
    """Manifest with absolute path in allowed_paths should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["allowed_paths"] = ["/absolute/path"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PATH_ABSOLUTE" in result
    finally:
        Path(path).unlink()


def test_allowed_paths_traversal_dotdot():
    """Manifest with '..' in allowed_paths should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["allowed_paths"] = ["../escape"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PATH_TRAVERSAL" in result
    finally:
        Path(path).unlink()


def test_allowed_paths_empty_string():
    """Manifest with empty string in allowed_paths should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["allowed_paths"] = [""]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PATH_EMPTY" in result
    finally:
        Path(path).unlink()


def test_allowed_paths_NUL_character():
    """Manifest with NUL character in allowed_paths should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["allowed_paths"] = ["path\x00with\x00nul"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PATH_NUL" in result
    finally:
        Path(path).unlink()


def test_allowed_paths_windows_drive():
    """Manifest with Windows drive path should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["allowed_paths"] = ["C:/path"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PATH_ABSOLUTE" in result
    finally:
        Path(path).unlink()


def test_allowed_paths_valid_glob():
    """Manifest with valid gitwildmatch patterns should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["allowed_paths"] = ["src/**", "tests/**/*.py", "docs/*.md"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


def test_missing_forbidden_paths():
    """Manifest without forbidden_paths should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["forbidden_paths"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "FORBIDDEN_PATHS_MISSING" in result
    finally:
        Path(path).unlink()


def test_forbidden_paths_absolute_path():
    """Manifest with absolute path in forbidden_paths should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["forbidden_paths"] = ["/secret/**"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PATH_ABSOLUTE" in result
    finally:
        Path(path).unlink()


# ============================================================================
# REQUIRED GATES TESTS
# ============================================================================

def test_missing_required_gates():
    """Manifest without required_gates should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["required_gates"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "REQUIRED_GATES_MISSING" in result
    finally:
        Path(path).unlink()


def test_required_gates_not_array():
    """Manifest with required_gates not array should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["required_gates"] = "scope"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "REQUIRED_GATES_NOT_ARRAY" in result
    finally:
        Path(path).unlink()


def test_required_gates_unknown_gate_id():
    """Manifest with unknown gate ID should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["required_gates"] = ["scope", "unknown_gate"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "GATE_UNKNOWN" in result
    finally:
        Path(path).unlink()


def test_required_gates_missing_canonical():
    """Manifest missing canonical required gates should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["required_gates"] = ["scope", "json_syntax"]  # missing others
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "GATE_MISSING_GLOBAL" in result
    finally:
        Path(path).unlink()


def test_required_gates_canonical_ids():
    """Manifest with all canonical gate IDs should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["required_gates"] = [
        "scope", "json_syntax", "yaml_syntax",
        "targeted_tests", "lint", "secrets", "git_diff_check"
    ]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


def test_required_gates_duplicate():
    """Manifest with duplicate gate IDs should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["required_gates"] = ["scope", "scope", "json_syntax"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "GATE_DUPLICATE" in result
    finally:
        Path(path).unlink()


# ============================================================================
# GATE OVERRIDES TESTS
# ============================================================================

def test_gate_overrides_allowlisted_field():
    """Manifest with allowlisted gate override should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["gate_overrides"] = {
        "targeted_tests": {"assertion_gate": True}
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


def test_gate_overrides_unknown_field():
    """Manifest with unknown gate override field should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["gate_overrides"] = {
        "targeted_tests": {"unknown_field": True}
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "OVERRIDE_UNKNOWN_FIELD" in result
    finally:
        Path(path).unlink()


def test_gate_overrides_required_forbidden():
    """Manifest overriding 'required' should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["gate_overrides"] = {
        "targeted_tests": {"required": False}
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "OVERRIDE_FORBIDDEN_FIELD" in result
    finally:
        Path(path).unlink()


def test_gate_overrides_enabled_forbidden():
    """Manifest overriding 'enabled' should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["gate_overrides"] = {
        "targeted_tests": {"enabled": False}
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "OVERRIDE_FORBIDDEN_FIELD" in result
    finally:
        Path(path).unlink()


def test_gate_overrides_non_required_gate():
    """Manifest overriding non-required gate should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["gate_overrides"] = {
        "nonexistent_gate": {"assertion_gate": True}
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "OVERRIDE_UNKNOWN_GATE" in result
    finally:
        Path(path).unlink()


# ============================================================================
# TEST COMMANDS TESTS
# ============================================================================

def test_missing_test_commands():
    """Manifest without test_commands should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["test_commands"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "TEST_COMMANDS_MISSING" in result
    finally:
        Path(path).unlink()


def test_test_commands_targeted_args_retained():
    """Manifest with test_commands.targeted_args should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["test_commands"] = {
        "targeted_args": ["test.py", "-v"]
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


def test_test_commands_missing_targeted_args():
    """Manifest without targeted_args should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["test_commands"] = {}
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "TARGETED_ARGS_MISSING" in result
    finally:
        Path(path).unlink()


def test_test_commands_targeted_args_not_array():
    """Manifest with targeted_args not array should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["test_commands"] = {
        "targeted_args": "test.py"
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "TARGETED_ARGS_NOT_ARRAY" in result
    finally:
        Path(path).unlink()


# ============================================================================
# ENVIRONMENT REQUIREMENTS TESTS
# ============================================================================

def test_missing_environment_requirements():
    """Manifest without environment_requirements should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["environment_requirements"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "ENVIRONMENT_REQUIREMENTS_MISSING" in result
    finally:
        Path(path).unlink()


def test_environment_requirements_structure():
    """Manifest with valid environment_requirements structure should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["environment_requirements"] = {
        "database": {"required": True, "auto_start": False},
        "redis": {"required": False, "auto_start": False},
        "external_network": {"allowed": False}
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


def test_environment_requirements_not_object():
    """Manifest with environment_requirements not object should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["environment_requirements"] = "database"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "ENVIRONMENT_REQUIREMENTS_NOT_OBJECT" in result
    finally:
        Path(path).unlink()


# ============================================================================
# EXPECTED OUTPUTS TESTS
# ============================================================================

def test_missing_expected_outputs():
    """Manifest without expected_outputs should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["expected_outputs"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "EXPECTED_OUTPUTS_MISSING" in result
    finally:
        Path(path).unlink()


def test_expected_outputs_not_array():
    """Manifest with expected_outputs not array should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["expected_outputs"] = "output.json"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "EXPECTED_OUTPUTS_NOT_ARRAY" in result
    finally:
        Path(path).unlink()


def test_expected_outputs_absolute_path():
    """Manifest with absolute path in expected_outputs should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["expected_outputs"] = ["/output.json"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PATH_ABSOLUTE" in result
    finally:
        Path(path).unlink()


def test_expected_outputs_traversal():
    """Manifest with traversal in expected_outputs should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["expected_outputs"] = ["../output.json"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "PATH_TRAVERSAL" in result
    finally:
        Path(path).unlink()


def test_expected_outputs_repo_relative():
    """Manifest with repo-relative paths in expected_outputs should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["expected_outputs"] = ["output.json", "reports/**"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


# ============================================================================
# ACCEPTANCE CRITERIA TESTS
# ============================================================================

def test_missing_acceptance_criteria():
    """Manifest without acceptance_criteria should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["acceptance_criteria"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "ACCEPTANCE_CRITERIA_MISSING" in result
    finally:
        Path(path).unlink()


def test_acceptance_criteria_not_array():
    """Manifest with acceptance_criteria not array should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["acceptance_criteria"] = "Criterion 1"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "ACCEPTANCE_CRITERIA_NOT_ARRAY" in result
    finally:
        Path(path).unlink()


def test_acceptance_criteria_empty_array():
    """Manifest with empty acceptance_criteria should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["acceptance_criteria"] = []
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "ACCEPTANCE_CRITERIA_EMPTY" in result
    finally:
        Path(path).unlink()


# ============================================================================
# REPAIR BUDGET TESTS
# ============================================================================

def test_missing_repair_budget():
    """Manifest without repair_budget should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["repair_budget"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "REPAIR_BUDGET_MISSING" in result
    finally:
        Path(path).unlink()


def test_repair_budget_not_integer():
    """Manifest with non-integer repair_budget should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["repair_budget"] = "3"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "REPAIR_BUDGET_NOT_INT" in result
    finally:
        Path(path).unlink()


def test_repair_budget_negative():
    """Manifest with negative repair_budget should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["repair_budget"] = -1
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "REPAIR_BUDGET_NEGATIVE" in result
    finally:
        Path(path).unlink()


def test_repair_budget_exceeds_global():
    """Manifest with repair_budget > global max should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["repair_budget"] = 10  # global max is 3
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "REPAIR_BUDGET_EXCEEDS_GLOBAL" in result
    finally:
        Path(path).unlink()


def test_repair_budget_narrows_global():
    """Manifest with repair_budget <= global max should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["repair_budget"] = 2  # global max is 3
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


# ============================================================================
# MODEL ROUTING HINTS TESTS
# ============================================================================

def test_missing_model_routing_hints():
    """Manifest without model_routing_hints should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["model_routing_hints"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "MODEL_ROUTING_HINTS_MISSING" in result
    finally:
        Path(path).unlink()


def test_model_routing_hints_not_object():
    """Manifest with model_routing_hints not object should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["model_routing_hints"] = "implementer"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "MODEL_ROUTING_HINTS_NOT_OBJECT" in result
    finally:
        Path(path).unlink()


def test_model_routing_hints_unknown_key():
    """Manifest with unknown routing hint key should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["model_routing_hints"] = {
        "implementation_role": "implementer",
        "unknown_key": "value"
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "ROUTING_UNKNOWN_KEY" in result
    finally:
        Path(path).unlink()


def test_model_routing_hints_invalid_complexity():
    """Manifest with invalid complexity should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["model_routing_hints"] = {
        "implementation_role": "implementer",
        "review_role": "reviewer",
        "complexity": "invalid",
        "local_worker_allowed": True
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "ROUTING_INVALID_COMPLEXITY" in result
    finally:
        Path(path).unlink()


def test_model_routing_hints_tool_name():
    """Manifest with concrete tool name should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["model_routing_hints"] = {
        "implementation_role": "ralph",  # tool name, not role
        "review_role": "reviewer",
        "complexity": "standard",
        "local_worker_allowed": True
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "ROUTING_INVALID_ROLE" in result
    finally:
        Path(path).unlink()


def test_model_routing_hints_valid():
    """Manifest with valid routing hints should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["model_routing_hints"] = {
        "implementation_role": "implementer",
        "review_role": "reviewer",
        "complexity": "high",
        "local_worker_allowed": False
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


# ============================================================================
# DEPENDENCIES AND CONFLICT DOMAINS TESTS
# ============================================================================

def test_missing_dependencies():
    """Manifest without dependencies should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["dependencies"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "DEPENDENCIES_MISSING" in result
    finally:
        Path(path).unlink()


def test_dependencies_not_array():
    """Manifest with dependencies not array should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["dependencies"] = "TEST-002"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "DEPENDENCIES_NOT_ARRAY" in result
    finally:
        Path(path).unlink()


def test_dependencies_empty_item():
    """Manifest with empty dependency item should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["dependencies"] = [""]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "DEPENDENCIES_EMPTY_ITEM" in result
    finally:
        Path(path).unlink()


def test_dependencies_duplicate():
    """Manifest with duplicate dependencies should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["dependencies"] = ["TEST-002", "TEST-002"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "DEPENDENCIES_DUPLICATE" in result
    finally:
        Path(path).unlink()


def test_missing_conflict_domains():
    """Manifest without conflict_domains should fail."""
    manifest = make_minimal_valid_manifest()
    del manifest["conflict_domains"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "CONFLICT_DOMAINS_MISSING" in result
    finally:
        Path(path).unlink()


def test_conflict_domains_not_array():
    """Manifest with conflict_domains not array should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["conflict_domains"] = "backend"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "CONFLICT_DOMAINS_NOT_ARRAY" in result
    finally:
        Path(path).unlink()


def test_conflict_domains_empty_item():
    """Manifest with empty conflict domain item should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["conflict_domains"] = [""]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "CONFLICT_DOMAINS_EMPTY_ITEM" in result
    finally:
        Path(path).unlink()


def test_conflict_domains_duplicate():
    """Manifest with duplicate conflict domains should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["conflict_domains"] = ["backend", "backend"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "CONFLICT_DOMAINS_DUPLICATE" in result
    finally:
        Path(path).unlink()


# ============================================================================
# REPAIR GUIDANCE (OPTIONAL) TESTS
# ============================================================================

def test_repair_guidance_optional():
    """Manifest without repair_guidance should pass."""
    manifest = make_minimal_valid_manifest()
    # repair_guidance not present
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


def test_repair_guidance_present_valid():
    """Manifest with valid repair_guidance should pass."""
    manifest = make_minimal_valid_manifest()
    manifest["repair_guidance"] = ["Guidance 1", "Guidance 2"]
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "OK"
    finally:
        Path(path).unlink()


def test_repair_guidance_not_array():
    """Manifest with repair_guidance not array should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["repair_guidance"] = "Guidance"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "REPAIR_GUIDANCE_NOT_ARRAY" in result
    finally:
        Path(path).unlink()


# ============================================================================
# RUNTIME FIELD REJECTION TESTS
# ============================================================================

def test_runtime_field_run_id_rejected():
    """Manifest with run_id should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["run_id"] = "test-run-123"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "RUNTIME_FIELD_REJECTED" in result
    finally:
        Path(path).unlink()


def test_runtime_field_slot_id_rejected():
    """Manifest with slot_id should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["slot_id"] = "test-slot-123"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "RUNTIME_FIELD_REJECTED" in result
    finally:
        Path(path).unlink()


def test_runtime_field_workspace_root_rejected():
    """Manifest with workspace_root should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["workspace_root"] = "/path/to/workspace"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "RUNTIME_FIELD_REJECTED" in result
    finally:
        Path(path).unlink()


def test_runtime_field_artifact_root_rejected():
    """Manifest with artifact_root should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["artifact_root"] = "/path/to/artifacts"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "RUNTIME_FIELD_REJECTED" in result
    finally:
        Path(path).unlink()


def test_runtime_field_phase_rejected():
    """Manifest with phase should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["phase"] = "implement"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "RUNTIME_FIELD_REJECTED" in result
    finally:
        Path(path).unlink()


def test_runtime_field_role_rejected():
    """Manifest with role should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["role"] = "implementer"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "RUNTIME_FIELD_REJECTED" in result
    finally:
        Path(path).unlink()


# ============================================================================
# LEGACY SCHEMA REJECTION TESTS
# ============================================================================

def test_legacy_gates_dict_rejected():
    """Manifest with legacy 'gates' dict should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["gates"] = {
        "scope": {"required": True, "enabled": True}
    }
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "LEGACY_GATES_REJECTED" in result
    finally:
        Path(path).unlink()


def test_legacy_branch_rejected():
    """Manifest with legacy 'branch' field should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["branch"] = "test/branch"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "LEGACY_BRANCH_REJECTED" in result
    finally:
        Path(path).unlink()


# ============================================================================
# STRICT TOP-LEVEL FIELD ALLOWLIST TEST
# ============================================================================

def test_unknown_top_level_field():
    """Manifest with unknown top-level field should fail."""
    manifest = make_minimal_valid_manifest()
    manifest["unknown_field"] = "value"
    path = write_temp_manifest(manifest)
    try:
        status, result = manifest_loader.validate_manifest(path)
        assert status == "ERROR"
        assert "UNKNOWN_TOP_LEVEL_FIELD" in result
    finally:
        Path(path).unlink()


# ============================================================================
# HARNESS ADAPTER TEST
# ============================================================================

def test_harness_delegate_no_duplicate_rules():
    """harness.py validate_manifest should delegate to manifest_loader."""
    import harness
    manifest = make_minimal_valid_manifest()
    path = write_temp_manifest(manifest)
    try:
        status, result = harness.validate_manifest(path)
        assert status == "OK"
        assert result == "TEST-001"
    finally:
        Path(path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
