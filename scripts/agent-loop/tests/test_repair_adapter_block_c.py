"""
Block C: Mock repair actor and harness integration tests.

Tests cover:
  BC-MOCK: Mock repair actor behavior (6 tests)
  BC-CLI: Repair adapter CLI entry point (3 tests)
  BC-E2E: End-to-end scenarios Y/Z/AA (3 tests)

Total: 12 tests

No skips, no xfails, no placeholders.
"""

import subprocess
import sys
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from repair_adapter import (
    ADAPTER_SUCCESS,
    ADAPTER_UNDECLARED_CHANGE,
    run_repair,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------
def _make_valid_repair_request(
    *,
    run_id: str = "run-123",
    story_id: str = "story-456",
    attempt: int = 1,
    max_attempts: int = 3,
    source_revision: str = "a" * 40,
    failure_class: str = "verification_fail",
    failure_summary: str = "Test failure",
    allowed_paths: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Build a minimal valid repair request."""
    if allowed_paths is None:
        allowed_paths = ["**/*"]
    if forbidden_paths is None:
        forbidden_paths = []

    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "story_id": story_id,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "source_revision": source_revision,
        "failure_class": failure_class,
        "failure_summary": failure_summary,
        "failure_context_ref": {
            "path": "failure-context.json",
            "schema_version": "1.0",
            "sha256": "a" * 64,
        },
        "verification_result_ref": {
            "path": "verification-result.json",
            "schema_version": "1.0",
            "sha256": "a" * 64,
        },
        "review_result_ref": None,
        "allowed_paths": allowed_paths,
        "forbidden_paths": forbidden_paths,
        "repair_guidance": [],
        "requested_action": "fix_verification",
        "generated_at": "2026-08-06T12:00:00Z",
    }


def _get_head_sha(repo_root: Path) -> str:
    """Get current HEAD SHA from a git repo."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def temp_git_repo() -> Generator[Path]:
    """Create a temporary git repository with clean baseline."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir()

        subprocess.run(
            ["git", "init"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )

        readme = repo_root / "README.md"
        readme.write_text("# Test\n")
        subprocess.run(
            ["git", "add", "README.md"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )

        yield repo_root


@pytest.fixture
def run_dir(temp_git_repo: Path) -> Generator[Path]:
    """Create run directory outside repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rd = Path(tmpdir) / "runs" / "run-123"
        rd.mkdir(parents=True)
        yield rd


@pytest.fixture
def mock_actor_path() -> Path:
    """Path to mock_repair_actor.py."""
    return Path(__file__).parent.parent / "lib" / "mock_repair_actor.py"


# ===========================================================================
# BC-MOCK: Mock repair actor behavior (6 tests)
# ===========================================================================


def test_BC_MOCK_01_repaired_mode(
    temp_git_repo: Path, run_dir: Path, mock_actor_path: Path
) -> None:
    """BC-MOCK-01: Mock actor REPAIRED mode produces valid result."""
    source_revision = _get_head_sha(temp_git_repo)

    # Create tracked file
    backend_dir = temp_git_repo / "backend"
    backend_dir.mkdir()
    test_file = backend_dir / "test.py"
    test_file.write_text("# Original\n")
    subprocess.run(
        ["git", "add", "backend/test.py"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add test"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )

    source_revision = _get_head_sha(temp_git_repo)
    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable="python3",
        actor_arguments=[
            str(mock_actor_path),
            "--mode",
            "REPAIRED",
            "--modify",
            "backend/test.py",
        ],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS
    assert result.repair_result_summary is not None
    assert result.repair_result_summary["status"] == "REPAIRED"
    assert "backend/test.py" in result.repair_result_summary["changed_files"]
    assert result.workspace_changes is not None
    assert "backend/test.py" in result.workspace_changes["modified"]
    assert result.reconciliation is not None
    assert result.reconciliation["exact_match"] is True


def test_BC_MOCK_02_no_change_mode(
    temp_git_repo: Path, run_dir: Path, mock_actor_path: Path
) -> None:
    """BC-MOCK-02: Mock actor NO_CHANGE mode produces valid result."""
    source_revision = _get_head_sha(temp_git_repo)
    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable="python3",
        actor_arguments=[str(mock_actor_path), "--mode", "NO_CHANGE"],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS
    assert result.repair_result_summary is not None
    assert result.repair_result_summary["status"] == "NO_CHANGE"
    assert result.repair_result_summary["changed_files"] == []
    assert result.workspace_changes is not None
    assert result.workspace_changes["modified"] == []
    assert result.workspace_changes["added"] == []
    assert result.reconciliation is not None
    assert result.reconciliation["exact_match"] is True


def test_BC_MOCK_03_error_mode(
    temp_git_repo: Path, run_dir: Path, mock_actor_path: Path
) -> None:
    """BC-MOCK-03: Mock actor ERROR mode produces valid result."""
    source_revision = _get_head_sha(temp_git_repo)
    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable="python3",
        actor_arguments=[str(mock_actor_path), "--mode", "ERROR"],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS
    assert result.repair_result_summary is not None
    assert result.repair_result_summary["status"] == "ERROR"


def test_BC_MOCK_04_undeclared_change_mode(
    temp_git_repo: Path, run_dir: Path, mock_actor_path: Path
) -> None:
    """BC-MOCK-04: Mock actor undeclared_change mode triggers ADAPTER_UNDECLARED_CHANGE."""
    # Create tracked file
    backend_dir = temp_git_repo / "backend"
    backend_dir.mkdir()
    test_file = backend_dir / "test.py"
    test_file.write_text("# Original\n")
    subprocess.run(
        ["git", "add", "backend/test.py"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add test"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )

    source_revision = _get_head_sha(temp_git_repo)
    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable="python3",
        actor_arguments=[
            str(mock_actor_path),
            "--mode",
            "undeclared_change",
            "--modify",
            "backend/test.py",
        ],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_UNDECLARED_CHANGE
    assert result.reconciliation is not None
    assert result.reconciliation["exact_match"] is False
    assert "undeclared_change.txt" in result.reconciliation["undeclared_changes"]


def test_BC_MOCK_05_deterministic_output(
    temp_git_repo: Path, run_dir: Path, mock_actor_path: Path
) -> None:
    """BC-MOCK-05: Mock actor produces deterministic output."""
    source_revision = _get_head_sha(temp_git_repo)
    repair_request = _make_valid_repair_request(source_revision=source_revision)

    # Run twice with same inputs
    result1 = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable="python3",
        actor_arguments=[str(mock_actor_path), "--mode", "NO_CHANGE"],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    result2 = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable="python3",
        actor_arguments=[str(mock_actor_path), "--mode", "NO_CHANGE"],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    # Same adapter status
    assert result1.adapter_status == result2.adapter_status
    # Same repair result summary
    assert result1.repair_result_summary == result2.repair_result_summary
    # Same workspace changes
    assert result1.workspace_changes == result2.workspace_changes


def test_BC_MOCK_06_schema_compliance(
    temp_git_repo: Path, run_dir: Path, mock_actor_path: Path
) -> None:
    """BC-MOCK-06: Mock actor result passes WP-AL-1C4 validation."""
    source_revision = _get_head_sha(temp_git_repo)

    # Create tracked file
    backend_dir = temp_git_repo / "backend"
    backend_dir.mkdir()
    test_file = backend_dir / "test.py"
    test_file.write_text("# Original\n")
    subprocess.run(
        ["git", "add", "backend/test.py"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add test"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )

    source_revision = _get_head_sha(temp_git_repo)
    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable="python3",
        actor_arguments=[
            str(mock_actor_path),
            "--mode",
            "REPAIRED",
            "--modify",
            "backend/test.py",
        ],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    # If adapter succeeded, actor result passed WP-AL-1C4 validation
    assert result.adapter_status == ADAPTER_SUCCESS
    # Verify repair result summary has all required fields
    assert result.repair_result_summary is not None
    assert "status" in result.repair_result_summary
    assert "changed" in result.repair_result_summary
    assert "changed_files" in result.repair_result_summary
    assert "recommended_action" in result.repair_result_summary
    assert "summary" in result.repair_result_summary


# ===========================================================================
# BC-CLI: Repair adapter CLI entry point (3 tests)
# ===========================================================================


def test_BC_CLI_01_help(
    mock_actor_path: Path,
) -> None:
    """BC-CLI-01: CLI --help exits 0."""
    adapter_script = Path(__file__).parent.parent / "lib" / "repair_adapter.py"

    result = subprocess.run(
        ["python3", str(adapter_script), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Repair adapter for WP-AL-1C5" in result.stdout


def test_BC_CLI_02_missing_required_arg(
    mock_actor_path: Path,
) -> None:
    """BC-CLI-02: CLI exits 2 on missing required argument."""
    adapter_script = Path(__file__).parent.parent / "lib" / "repair_adapter.py"

    result = subprocess.run(
        ["python3", str(adapter_script), "--repo-root", "/tmp"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "required" in result.stderr.lower()


def test_BC_CLI_03_invalid_repair_request(
    temp_git_repo: Path, run_dir: Path, mock_actor_path: Path
) -> None:
    """BC-CLI-03: CLI exits 2 on invalid repair request JSON."""
    adapter_script = Path(__file__).parent.parent / "lib" / "repair_adapter.py"

    # Write invalid JSON
    invalid_request = run_dir / "invalid-request.json"
    invalid_request.write_text("{ invalid json }")

    result = subprocess.run(
        [
            "python3",
            str(adapter_script),
            "--repo-root",
            str(temp_git_repo),
            "--run-dir",
            str(run_dir),
            "--repair-request",
            str(invalid_request),
            "--actor-command",
            "python3",
            "--completed-at",
            "2026-08-06T12:00:00Z",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "cannot read repair request" in result.stderr.lower()


# ===========================================================================
# BC-E2E: End-to-end scenarios Y/Z/AA (3 tests)
# ===========================================================================


def test_BC_E2E_Y_repair_success(
    temp_git_repo: Path, run_dir: Path, mock_actor_path: Path
) -> None:
    """BC-E2E-Y: Scenario Y — successful REPAIRED with matching diff."""
    # Create tracked file
    backend_dir = temp_git_repo / "backend"
    backend_dir.mkdir()
    test_file = backend_dir / "test.py"
    test_file.write_text("# Original\n")
    subprocess.run(
        ["git", "add", "backend/test.py"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add test"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )

    source_revision = _get_head_sha(temp_git_repo)
    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable="python3",
        actor_arguments=[
            str(mock_actor_path),
            "--mode",
            "REPAIRED",
            "--modify",
            "backend/test.py",
        ],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    # Scenario Y: ADAPTER_SUCCESS
    assert result.adapter_status == ADAPTER_SUCCESS
    assert result.repair_result_summary is not None
    assert result.repair_result_summary["status"] == "REPAIRED"
    assert result.workspace_changes is not None
    assert "backend/test.py" in result.workspace_changes["modified"]
    assert result.reconciliation is not None
    assert result.reconciliation["exact_match"] is True
    assert result.permission_enforcement is not None
    assert result.permission_enforcement["all_actual_changes_permitted"] is True


def test_BC_E2E_Z_repair_no_change(
    temp_git_repo: Path, run_dir: Path, mock_actor_path: Path
) -> None:
    """BC-E2E-Z: Scenario Z — NO_CHANGE with no actual diff."""
    source_revision = _get_head_sha(temp_git_repo)
    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable="python3",
        actor_arguments=[str(mock_actor_path), "--mode", "NO_CHANGE"],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    # Scenario Z: ADAPTER_SUCCESS
    assert result.adapter_status == ADAPTER_SUCCESS
    assert result.repair_result_summary is not None
    assert result.repair_result_summary["status"] == "NO_CHANGE"
    assert result.repair_result_summary["changed_files"] == []
    assert result.workspace_changes is not None
    assert result.workspace_changes["modified"] == []
    assert result.workspace_changes["added"] == []
    assert result.workspace_changes["deleted"] == []
    assert result.workspace_changes["untracked"] == []
    assert result.reconciliation is not None
    assert result.reconciliation["exact_match"] is True


def test_BC_E2E_AA_repair_safety_failure(
    temp_git_repo: Path, run_dir: Path, mock_actor_path: Path
) -> None:
    """BC-E2E-AA: Scenario AA — undeclared change triggers ADAPTER_UNDECLARED_CHANGE."""
    # Create tracked file
    backend_dir = temp_git_repo / "backend"
    backend_dir.mkdir()
    test_file = backend_dir / "test.py"
    test_file.write_text("# Original\n")
    subprocess.run(
        ["git", "add", "backend/test.py"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add test"],
        cwd=temp_git_repo,
        check=True,
        capture_output=True,
    )

    source_revision = _get_head_sha(temp_git_repo)
    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable="python3",
        actor_arguments=[
            str(mock_actor_path),
            "--mode",
            "undeclared_change",
            "--modify",
            "backend/test.py",
        ],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    # Scenario AA: ADAPTER_UNDECLARED_CHANGE
    assert result.adapter_status == ADAPTER_UNDECLARED_CHANGE
    assert result.workspace_changes is not None
    assert "backend/test.py" in result.workspace_changes["modified"]
    assert "undeclared_change.txt" in result.workspace_changes["untracked"]
    assert result.reconciliation is not None
    assert result.reconciliation["exact_match"] is False
    assert "undeclared_change.txt" in result.reconciliation["undeclared_changes"]
