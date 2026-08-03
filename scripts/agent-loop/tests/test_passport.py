#!/usr/bin/env python3
"""
Unit tests for CyclePassport validation logic.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Import passport module (path inserted at runtime)
import sys
_LIB_DIR = str(Path(__file__).parent.parent / "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from passport import (  # type: ignore[import-not-found]
    CyclePassport,
    create_passport,
    write_error_artifact,
    bootstrap_guard,
)


@pytest.fixture
def sample_passport_data():
    """Sample valid passport data."""
    return {
        "schema_version": "1.0",
        "project_id": "forgemind",
        "run_id": "STORY-001_20260802_120000_123456",
        "slot_id": "slot-001",
        "story_id": "STORY-001",
        "role": "implementer",
        "phase": "implement",
        "workspace_type": "source",
        "workspace_root": "/tmp/test-workspace",
        "expected_branch": "chore/agent-loop-infrastructure",
        "base_commit": "abc123",
        "manifest_path": "/tmp/test-workspace/manifest.json",
        "artifact_root": "/tmp/test-workspace/.ralph-tui/artifacts/STORY-001_20260802_120000_123456",
        "candidate_commit": None
    }


@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace with git repo."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    # Initialize git repo
    subprocess.run(["git", "init"], cwd=workspace, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=workspace, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=workspace, capture_output=True, check=True)

    # Create initial commit
    test_file = workspace / "test.txt"
    test_file.write_text("test")
    subprocess.run(["git", "add", "test.txt"], cwd=workspace, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=workspace, capture_output=True, check=True)

    # Get commit hash
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=workspace, capture_output=True, text=True, check=True)
    commit_hash = result.stdout.strip()

    return workspace, commit_hash


def test_create_passport(sample_passport_data):
    """Test passport creation."""
    passport = create_passport(
        project_id=sample_passport_data["project_id"],
        run_id=sample_passport_data["run_id"],
        slot_id=sample_passport_data["slot_id"],
        story_id=sample_passport_data["story_id"],
        role=sample_passport_data["role"],
        phase=sample_passport_data["phase"],
        workspace_type=sample_passport_data["workspace_type"],
        workspace_root=sample_passport_data["workspace_root"],
        expected_branch=sample_passport_data["expected_branch"],
        base_commit=sample_passport_data["base_commit"],
        manifest_path=sample_passport_data["manifest_path"],
        artifact_root=sample_passport_data["artifact_root"]
    )

    assert passport.project_id == "forgemind"
    assert passport.run_id == sample_passport_data["run_id"]
    assert passport.slot_id == sample_passport_data["slot_id"]
    assert passport.story_id == sample_passport_data["story_id"]
    assert passport.role == "implementer"
    assert passport.phase == "implement"


def test_passport_to_json(sample_passport_data):
    """Test passport serialization."""
    passport = CyclePassport(**sample_passport_data)
    json_str = passport.to_json()

    # Parse back
    data = json.loads(json_str)
    assert data["project_id"] == "forgemind"
    assert data["run_id"] == sample_passport_data["run_id"]


def test_passport_save_load(tmp_path, sample_passport_data):
    """Test passport save and load."""
    # Mock harness module via sys.modules
    import sys
    mock_harness = MagicMock()

    def fake_atomic_write(path, data):
        with open(path, 'w') as f:
            json.dump(data, f)

    mock_harness.atomic_json_write.side_effect = fake_atomic_write

    # Save original and inject mock
    original_modules = dict(sys.modules)
    sys.modules['harness'] = mock_harness

    try:
        passport = CyclePassport(**sample_passport_data)
        passport_path = tmp_path / "passport.json"

        passport.save(passport_path)

        # Verify file was written
        assert passport_path.exists()

        # Load back
        loaded = CyclePassport.load(passport_path)
        assert loaded.project_id == passport.project_id
        assert loaded.run_id == passport.run_id
    finally:
        # Restore original modules
        sys.modules.clear()
        sys.modules.update(original_modules)


def test_validate_workspace_success(temp_workspace, sample_passport_data):
    """Test workspace validation success."""
    workspace, commit_hash = temp_workspace

    # Update passport with real workspace
    sample_passport_data["workspace_root"] = str(workspace)
    sample_passport_data["base_commit"] = commit_hash
    sample_passport_data["expected_branch"] = "master"  # git init creates master

    passport = CyclePassport(**sample_passport_data)

    # Change to workspace directory
    with patch('passport.Path.cwd', return_value=workspace):
        valid, msg = passport.validate_workspace()
        assert valid, f"Validation failed: {msg}"


def test_validate_workspace_wrong_branch(temp_workspace, sample_passport_data):
    """Test workspace validation fails on wrong branch."""
    workspace, commit_hash = temp_workspace

    sample_passport_data["workspace_root"] = str(workspace)
    sample_passport_data["base_commit"] = commit_hash
    sample_passport_data["expected_branch"] = "wrong-branch"

    passport = CyclePassport(**sample_passport_data)

    with patch('passport.Path.cwd', return_value=workspace):
        valid, msg = passport.validate_workspace()
        assert not valid
        assert "branch" in msg.lower()


def test_validate_workspace_wrong_root(temp_workspace, sample_passport_data):
    """Test workspace validation fails on wrong workspace_root."""
    workspace, commit_hash = temp_workspace

    sample_passport_data["workspace_root"] = "/wrong/path"
    sample_passport_data["base_commit"] = commit_hash

    passport = CyclePassport(**sample_passport_data)

    with patch('passport.Path.cwd', return_value=workspace):
        valid, msg = passport.validate_workspace()
        assert not valid
        assert "pwd" in msg.lower() or "workspace_root" in msg.lower()


def test_validate_identity_success(sample_passport_data):
    """Test identity validation success."""
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_identity(
        run_id=sample_passport_data["run_id"],
        slot_id=sample_passport_data["slot_id"],
        story_id=sample_passport_data["story_id"],
        role=sample_passport_data["role"]
    )

    assert valid


def test_validate_identity_wrong_run_id(sample_passport_data):
    """Test identity validation fails on wrong run_id."""
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_identity(
        run_id="wrong-run-id",
        slot_id=sample_passport_data["slot_id"],
        story_id=sample_passport_data["story_id"],
        role=sample_passport_data["role"]
    )

    assert not valid
    assert "run_id" in msg.lower()


def test_validate_identity_wrong_slot_id(sample_passport_data):
    """Test identity validation fails on wrong slot_id."""
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_identity(
        run_id=sample_passport_data["run_id"],
        slot_id="wrong-slot-id",
        story_id=sample_passport_data["story_id"],
        role=sample_passport_data["role"]
    )

    assert not valid
    assert "slot_id" in msg.lower()


def test_validate_identity_wrong_story_id(sample_passport_data):
    """Test identity validation fails on wrong story_id."""
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_identity(
        run_id=sample_passport_data["run_id"],
        slot_id=sample_passport_data["slot_id"],
        story_id="wrong-story-id",
        role=sample_passport_data["role"]
    )

    assert not valid
    assert "story_id" in msg.lower()


def test_validate_identity_wrong_role(sample_passport_data):
    """Test identity validation fails on wrong role."""
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_identity(
        run_id=sample_passport_data["run_id"],
        slot_id=sample_passport_data["slot_id"],
        story_id=sample_passport_data["story_id"],
        role="wrong-role"
    )

    assert not valid
    assert "role" in msg.lower()


def test_validate_manifest_ownership_success(tmp_path, sample_passport_data):
    """Test manifest ownership validation success."""
    # Create manifest with matching IDs
    manifest_data = {
        "project_id": sample_passport_data["project_id"],
        "run_id": sample_passport_data["run_id"],
        "slot_id": sample_passport_data["slot_id"],
        "story_id": sample_passport_data["story_id"],
        "title": "Test Story"
    }

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data))

    sample_passport_data["manifest_path"] = str(manifest_path)
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_manifest_ownership(manifest_path)
    assert valid


def test_validate_manifest_ownership_wrong_story_id(tmp_path, sample_passport_data):
    """Test manifest ownership validation fails on wrong story_id."""
    manifest_data = {
        "project_id": sample_passport_data["project_id"],
        "run_id": sample_passport_data["run_id"],
        "slot_id": sample_passport_data["slot_id"],
        "story_id": "wrong-story-id",
        "title": "Test Story"
    }

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest_data))

    sample_passport_data["manifest_path"] = str(manifest_path)
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_manifest_ownership(manifest_path)
    assert not valid
    assert "story_id" in msg.lower()


def test_validate_manifest_ownership_missing_file(sample_passport_data):
    """Test manifest ownership validation fails on missing file."""
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_manifest_ownership(Path("/nonexistent/manifest.json"))
    assert not valid
    assert "not found" in msg.lower()


def test_validate_artifact_root_success(tmp_path, sample_passport_data):
    """Test artifact root validation success."""
    artifact_root = tmp_path / "artifacts" / sample_passport_data["run_id"]
    artifact_root.mkdir(parents=True)

    sample_passport_data["workspace_root"] = str(tmp_path)
    sample_passport_data["artifact_root"] = str(artifact_root)

    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_artifact_root()
    assert valid


def test_validate_artifact_root_wrong_slot(tmp_path, sample_passport_data):
    """Test artifact root validation fails when it belongs to different slot."""
    artifact_root = tmp_path / "artifacts" / "different-run-id"
    artifact_root.mkdir(parents=True)

    sample_passport_data["workspace_root"] = str(tmp_path)
    sample_passport_data["artifact_root"] = str(artifact_root)

    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_artifact_root()
    assert not valid
    assert "run_id" in msg.lower() or "slot_id" in msg.lower()


def test_validate_workspace_type_success(sample_passport_data):
    """Test workspace type validation success."""
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_workspace_type("source")
    assert valid


def test_validate_workspace_type_mismatch(sample_passport_data):
    """Test workspace type validation fails on mismatch."""
    sample_passport_data["workspace_type"] = "validation"
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_workspace_type("source")
    assert not valid
    assert "workspace type" in msg.lower()


def test_validate_phase_role_success(sample_passport_data):
    """Test phase role validation success."""
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_phase_role("implement", "implementer")
    assert valid


def test_validate_phase_role_not_allowed(sample_passport_data):
    """Test phase role validation fails when role not allowed."""
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_phase_role("implement", "reviewer")
    assert not valid
    assert "not allowed" in msg.lower()


def test_validate_phase_role_unknown_phase(sample_passport_data):
    """Test phase role validation fails on unknown phase."""
    passport = CyclePassport(**sample_passport_data)

    valid, msg = passport.validate_phase_role("unknown-phase", "implementer")
    assert not valid
    assert "unknown phase" in msg.lower()


def test_write_error_artifact(tmp_path):
    """Test error artifact writing."""
    error_path = tmp_path / "error.json"

    import sys
    mock_harness = MagicMock()

    def fake_atomic_write(path, data):
        with open(path, 'w') as f:
            json.dump(data, f)

    mock_harness.atomic_json_write.side_effect = fake_atomic_write

    original_modules = dict(sys.modules)
    sys.modules['harness'] = mock_harness

    try:
        write_error_artifact(
            output_path=error_path,
            status="INFRASTRUCTURE_ERROR",
            error_code="TEST_ERROR",
            phase="implement",
            failed_check="test_check",
            expected="expected_value",
            actual="actual_value",
            project_id="test-project",
            run_id="test-run",
            slot_id="test-slot",
            story_id="test-story"
        )

        # Verify file was written
        assert error_path.exists()

        # Load and verify content
        with open(error_path) as f:
            error_data = json.load(f)

        assert error_data["status"] == "INFRASTRUCTURE_ERROR"
        assert error_data["error_code"] == "TEST_ERROR"
        assert error_data["project_id"] == "test-project"
    finally:
        sys.modules.clear()
        sys.modules.update(original_modules)


def test_bootstrap_guard_success(temp_workspace):
    """Test bootstrap guard success."""
    workspace, commit_hash = temp_workspace

    valid, msg = bootstrap_guard(
        workspace_root=str(workspace),
        expected_branch="master",
        main_worktree="/forbidden/main/worktree"
    )

    assert valid


def test_bootstrap_guard_main_worktree_forbidden(temp_workspace):
    """Test bootstrap guard fails when workspace equals main worktree."""
    workspace, commit_hash = temp_workspace

    valid, msg = bootstrap_guard(
        workspace_root=str(workspace),
        expected_branch="master",
        main_worktree=str(workspace)  # Same as workspace
    )

    assert not valid
    assert "main worktree" in msg.lower()


def test_bootstrap_guard_wrong_branch(temp_workspace):
    """Test bootstrap guard fails on wrong branch."""
    workspace, commit_hash = temp_workspace

    valid, msg = bootstrap_guard(
        workspace_root=str(workspace),
        expected_branch="wrong-branch",
        main_worktree="/forbidden/main/worktree"
    )

    assert not valid
    assert "branch" in msg.lower()


def test_bootstrap_guard_not_git_repo(tmp_path):
    """Test bootstrap guard fails when not a git repo."""
    non_git_dir = tmp_path / "not-git"
    non_git_dir.mkdir()

    valid, msg = bootstrap_guard(
        workspace_root=str(non_git_dir),
        expected_branch="master",
        main_worktree="/forbidden/main/worktree"
    )

    assert not valid
    assert "git" in msg.lower()


def test_malformed_passport_json(tmp_path):
    """Test loading malformed JSON passport."""
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text("{invalid json")

    with pytest.raises(json.JSONDecodeError):
        CyclePassport.load(malformed_path)


def test_missing_required_field(tmp_path, sample_passport_data):
    """Test loading passport with missing required field."""
    del sample_passport_data["run_id"]

    passport_path = tmp_path / "passport.json"
    passport_path.write_text(json.dumps(sample_passport_data))

    with pytest.raises((TypeError, KeyError)):
        CyclePassport.load(passport_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
