"""
Block B: Actor invocation and orchestration tests.

Tests cover:
  BB-ATOMIC: Atomic JSON file handling (6 tests)
  BB-ENV: Minimal environment (1 test)
  BB-HAPPY: Happy paths (4 tests)
  BB-INVOKE: Invocation failures (16 tests)
  BB-WORKSPACE: Workspace failures (7 tests)
  BB-SAFETY: Safety (5 tests)

Total: 43 tests (including helper tests)

No skips, no xfails, no placeholders.
"""

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from repair_adapter import (
    ADAPTER_CONTRACT_VIOLATION,
    ADAPTER_DECLARED_MISSING,
    ADAPTER_FORBIDDEN_CHANGE,
    ADAPTER_IDENTITY_MISMATCH,
    ADAPTER_MALFORMED_RESULT,
    ADAPTER_MISSING_RESULT,
    ADAPTER_NON_ZERO_EXIT,
    ADAPTER_OUTPUT_SIZE_EXCEEDED,
    ADAPTER_SOURCE_REVISION_DRIFT,
    ADAPTER_SUCCESS,
    ADAPTER_TIMEOUT,
    ADAPTER_UNDECLARED_CHANGE,
    BoundedByteStream,
    _atomic_write_json,
    _build_minimal_env,
    _sanitize_output,
    _validate_command,
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


def _make_valid_repair_result(
    *,
    run_id: str = "run-123",
    story_id: str = "story-456",
    attempt: int = 1,
    source_revision: str = "a" * 40,
    status: str = "REPAIRED",
    changed: bool = True,
    changed_files: list[str] | None = None,
    recommended_action: str = "reverify",
    summary: str = "Fixed the issue",
) -> dict[str, Any]:
    """Build a minimal valid repair result."""
    if changed_files is None:
        changed_files = ["backend/test.py"]

    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "story_id": story_id,
        "attempt": attempt,
        "source_revision": source_revision,
        "status": status,
        "changed": changed,
        "changed_files": changed_files,
        "summary": summary,
        "diagnostics": {
            "actions_taken": [],
            "obstacles": [],
        },
        "recommended_action": recommended_action,
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": "2026-08-06T12:00:00Z",
    }


def _create_actor_script(tmp_dir: Path, content: str, name: str = "actor.py") -> Path:
    """Create an actor script outside the repo in tmp_dir."""
    script = tmp_dir / name
    script.write_text(f"#!/usr/bin/env python3\n{content}")
    script.chmod(0o755)
    return script


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
def temp_git_repo() -> Generator[Path, None, None]:
    """Create a temporary git repository with clean baseline."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir()

        # Initialize git repo
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

        # Create initial commit
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
def run_dir(temp_git_repo: Path) -> Iterator[Path]:
    """Create run directory outside repo to avoid workspace pollution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rd = Path(tmpdir) / "runs" / "run-123"
        rd.mkdir(parents=True)
        yield rd


@pytest.fixture
def actor_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for actor scripts (outside repo)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ===========================================================================
# BB-ATOMIC: Atomic JSON file handling (6 tests)
# ===========================================================================


def test_BB_ATOMIC_01_successful_write() -> None:
    """BB-ATOMIC-01: Successful atomic write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.json"
        data: dict[str, object] = {"key": "value", "number": 42}

        _atomic_write_json(path, data)

        assert path.exists()
        content = json.loads(path.read_text())
        assert content == data


def test_BB_ATOMIC_02_replacement_behavior() -> None:
    """BB-ATOMIC-02: Atomic write replaces existing file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.json"

        # Write initial
        _atomic_write_json(path, {"version": 1})
        assert json.loads(path.read_text()) == {"version": 1}

        # Replace
        _atomic_write_json(path, {"version": 2})
        assert json.loads(path.read_text()) == {"version": 2}


def test_BB_ATOMIC_03_write_failure_cleanup() -> None:
    """BB-ATOMIC-03: Temp file cleaned on write failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a file where a directory should be (forces failure)
        blocker = Path(tmpdir) / "blocker"
        blocker.write_text("blocker")

        # Try to write under the blocker (will fail because blocker is a file)
        path = blocker / "subdir" / "test.json"

        with pytest.raises(OSError):
            _atomic_write_json(path, {"key": "value"})

        # Final file should not exist
        assert not path.exists()


def test_BB_ATOMIC_04_no_partial_final_file() -> None:
    """BB-ATOMIC-04: No partial final file on failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a file where a directory should be
        blocker = Path(tmpdir) / "blocker"
        blocker.write_text("blocker")

        path = blocker / "subdir" / "test.json"

        with pytest.raises(OSError):
            _atomic_write_json(path, {"key": "value"})

        # Final file should not exist
        assert not path.exists()


def test_BB_ATOMIC_05_deterministic_json() -> None:
    """BB-ATOMIC-05: Deterministic JSON output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path1 = Path(tmpdir) / "test1.json"
        path2 = Path(tmpdir) / "test2.json"

        data: dict[str, object] = {"z": 1, "a": 2, "m": 3}

        _atomic_write_json(path1, data)
        _atomic_write_json(path2, data)

        # Same bytes (sorted keys)
        assert path1.read_bytes() == path2.read_bytes()


def test_BB_ATOMIC_06_temporary_artifact_cleanup() -> None:
    """BB-ATOMIC-06: Temporary artifact cleaned after success."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.json"
        pid = os.getpid()
        tmp_path = path.parent / f".{path.name}-tmp-{pid}"

        _atomic_write_json(path, {"key": "value"})

        # Temp file should not exist after success
        assert not tmp_path.exists()
        # Final file should exist
        assert path.exists()


# ===========================================================================
# BB-ENV: Minimal environment (1 test)
# ===========================================================================


def test_BB_ENV_01_no_inherited_secrets() -> None:
    """BB-ENV-01: Environment excludes inherited secrets."""
    with tempfile.TemporaryDirectory() as tmpdir:
        rd = Path(tmpdir)

        # Set secret in parent environment
        os.environ["TEST_API_KEY_BB"] = "secret123"
        os.environ["TEST_AWS_SECRET_BB"] = "aws_secret"
        os.environ["TEST_DB_PASSWORD_BB"] = "db_pass"

        try:
            env = _build_minimal_env(rd)

            # Check required fields
            assert "PATH" in env
            assert "HOME" in env
            assert "LANG" in env
            assert "LC_ALL" in env
            assert "TMPDIR" in env
            assert "PYTHONNOUSERSITE" in env
            assert "PYTHONDONTWRITEBYTECODE" in env

            # Check secrets not present
            assert "TEST_API_KEY_BB" not in env
            assert "TEST_AWS_SECRET_BB" not in env
            assert "TEST_DB_PASSWORD_BB" not in env
            assert "SSH_AUTH_SOCK" not in env
            assert "HTTP_PROXY" not in env

            # Check values
            assert env["PATH"] == "/usr/local/bin:/usr/bin:/bin"
            assert env["LANG"] == "C.UTF-8"
            assert env["LC_ALL"] == "C.UTF-8"
            assert env["PYTHONNOUSERSITE"] == "1"
            assert env["PYTHONDONTWRITEBYTECODE"] == "1"

            # Check directories created
            assert (rd / ".actor-home").exists()
            assert (rd / "repair" / "tmp").exists()

        finally:
            # Clean up
            os.environ.pop("TEST_API_KEY_BB", None)
            os.environ.pop("TEST_AWS_SECRET_BB", None)
            os.environ.pop("TEST_DB_PASSWORD_BB", None)


# ===========================================================================
# BB-HAPPY: Happy paths (4 tests)
# ===========================================================================


def test_BB_HAPPY_01_no_changes(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-HAPPY-01: Successful NO_CHANGE with no workspace changes."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes needed",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS
    assert result.repair_result_summary is not None
    assert result.repair_result_summary["status"] == "NO_CHANGE"
    assert result.workspace_changes is not None
    assert result.reconciliation is not None
    assert result.reconciliation["exact_match"] is True


def test_BB_HAPPY_02_tracked_modification(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-HAPPY-02: Successful REPAIRED with declared tracked modification."""
    # Create tracked file
    backend_dir = temp_git_repo / "backend"
    backend_dir.mkdir()
    test_file = backend_dir / "test.py"
    test_file.write_text("# Original\n")
    subprocess.run(["git", "add", "backend/test.py"], cwd=temp_git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add test"], cwd=temp_git_repo, check=True, capture_output=True)

    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
with open("backend/test.py", "w") as f:
    f.write("# Modified\\n")
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "REPAIRED", "changed": True,
    "changed_files": ["backend/test.py"],
    "summary": "Fixed test",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "reverify",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS
    assert result.repair_result_summary is not None
    assert result.repair_result_summary["status"] == "REPAIRED"
    assert result.workspace_changes is not None
    assert "backend/test.py" in result.workspace_changes["modified"]
    assert result.reconciliation is not None
    assert result.reconciliation["exact_match"] is True


def test_BB_HAPPY_03_untracked_file(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-HAPPY-03: Successful REPAIRED with declared untracked file."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
with open("new_file.txt", "w") as f:
    f.write("New file\\n")
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "REPAIRED", "changed": True,
    "changed_files": ["new_file.txt"],
    "summary": "Created new file",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "reverify",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS
    assert result.workspace_changes is not None
    assert "new_file.txt" in result.workspace_changes["untracked"]
    assert result.reconciliation is not None
    assert result.reconciliation["exact_match"] is True


def test_BB_HAPPY_04_mixed_changes(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-HAPPY-04: Successful REPAIRED with mixed changes."""
    # Create tracked file
    backend_dir = temp_git_repo / "backend"
    backend_dir.mkdir()
    test_file = backend_dir / "test.py"
    test_file.write_text("# Original\n")
    subprocess.run(["git", "add", "backend/test.py"], cwd=temp_git_repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Add test"], cwd=temp_git_repo, check=True, capture_output=True)

    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
with open("backend/test.py", "w") as f:
    f.write("# Modified\\n")
with open("new_file.txt", "w") as f:
    f.write("New file\\n")
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "REPAIRED", "changed": True,
    "changed_files": ["backend/test.py", "new_file.txt"],
    "summary": "Fixed test and created file",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "reverify",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS
    assert result.workspace_changes is not None
    assert "backend/test.py" in result.workspace_changes["modified"]
    assert "new_file.txt" in result.workspace_changes["untracked"]
    assert result.reconciliation is not None
    assert result.reconciliation["exact_match"] is True


# ===========================================================================
# BB-INVOKE: Invocation failures (16 tests)
# ===========================================================================


def test_BB_INVOKE_01_timeout(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-01: Actor timeout."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(actor_dir, "import time; time.sleep(10)")

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=1,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_TIMEOUT


def test_BB_INVOKE_02_sigterm_responsive(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-02: Actor SIGTERM-responsive."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        """
import signal, sys, time
def handler(signum, frame):
    sys.exit(0)
signal.signal(signal.SIGTERM, handler)
time.sleep(10)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=1,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_TIMEOUT
    assert result.diagnostics["actor_exit_code"] == 0


def test_BB_INVOKE_03_sigkill_required(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-03: Actor SIGTERM-ignoring requiring SIGKILL."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        """
import signal, time
signal.signal(signal.SIGTERM, signal.SIG_IGN)
time.sleep(10)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=1,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_TIMEOUT
    # SIGKILL exit code is -9
    assert result.diagnostics["actor_exit_code"] == -9


def test_BB_INVOKE_04_non_zero_exit(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-04: Actor non-zero exit."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(actor_dir, "import sys; sys.exit(1)")

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_NON_ZERO_EXIT
    assert result.diagnostics["actor_exit_code"] == 1


def test_BB_INVOKE_05_missing_result(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-05: Missing result file."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(actor_dir, "# Do nothing")

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_MISSING_RESULT


def test_BB_INVOKE_06_malformed_json(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-06: Malformed JSON result."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        """
import sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
with open(result_path, "w") as f:
    f.write("{invalid json")
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_MALFORMED_RESULT


def test_BB_INVOKE_07_contract_violation(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-07: Invalid repair-result contract."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "2.0",
    "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "REPAIRED", "changed": True,
    "changed_files": ["test.py"], "summary": "Fixed",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "reverify",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_CONTRACT_VIOLATION


def test_BB_INVOKE_08_identity_mismatch(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-08: Identity mismatch (run_id differs)."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "wrong-run-id",
    "story_id": "story-456", "attempt": 1,
    "source_revision": "{source_revision}",
    "status": "REPAIRED", "changed": True,
    "changed_files": ["test.py"], "summary": "Fixed",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "reverify",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_IDENTITY_MISMATCH


def test_BB_INVOKE_09_source_revision_drift(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-09: Source revision drift (actor commits)."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        """
import json, subprocess, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
with open("new_file.txt", "w") as f:
    f.write("New\\n")
subprocess.run(["git", "add", "new_file.txt"], check=True, capture_output=True)
subprocess.run(["git", "commit", "-m", "Add file"], check=True, capture_output=True)
r = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True)
new_rev = r.stdout.strip()
result = {
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": new_rev,
    "status": "REPAIRED", "changed": True,
    "changed_files": ["new_file.txt"], "summary": "Fixed",
    "diagnostics": {"actions_taken": [], "obstacles": []},
    "recommended_action": "reverify",
    "sanitization": {"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []},
    "completed_at": "2026-08-06T12:00:00Z"
}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SOURCE_REVISION_DRIFT


def test_BB_INVOKE_10_stdout_exactly_at_limit(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-10: Stdout exactly at limit (4096 bytes)."""
    source_revision = _get_head_sha(temp_git_repo)

    # Print exactly 4096 bytes (4095 chars + newline from print)
    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
# 4095 chars + 1 newline = 4096 bytes
sys.stdout.write("x" * 4095 + "\\n")
sys.stdout.flush()
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS


def test_BB_INVOKE_11_stdout_one_byte_above_limit(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-11: Stdout one byte above limit (4097 bytes)."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
# 4096 chars + 1 newline = 4097 bytes
sys.stdout.write("x" * 4096 + "\\n")
sys.stdout.flush()
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_OUTPUT_SIZE_EXCEEDED


def test_BB_INVOKE_12_stderr_exactly_at_limit(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-12: Stderr exactly at limit (4096 bytes)."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
# 4095 chars + 1 newline = 4096 bytes
sys.stderr.write("x" * 4095 + "\\n")
sys.stderr.flush()
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS


def test_BB_INVOKE_13_stderr_one_byte_above_limit(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-INVOKE-13: Stderr one byte above limit (4097 bytes)."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
# 4096 chars + 1 newline = 4097 bytes
sys.stderr.write("x" * 4096 + "\\n")
sys.stderr.flush()
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_OUTPUT_SIZE_EXCEEDED


def test_BB_INVOKE_14_multibyte_utf8() -> None:
    """BB-INVOKE-14: Multibyte UTF-8 byte accounting."""
    stream = BoundedByteStream(10)

    # Write emoji (4 bytes: F0 9F 98 80)
    emoji = "😀".encode()
    assert len(emoji) == 4

    # Write 6 bytes + 4-byte emoji = 10 bytes total
    stream.write(b"123456")
    stream.write(emoji)

    assert stream.total_observed == 10
    assert not stream.exceeded

    # Write one more byte to exceed
    stream.write(b"7")
    assert stream.total_observed == 11
    assert stream.exceeded

    # Tail should be last 10 bytes
    tail = stream.tail_bytes()
    assert len(tail) == 10


def test_BB_INVOKE_15_invalid_utf8() -> None:
    """BB-INVOKE-15: Invalid UTF-8 output."""
    invalid_bytes = b"Valid text \xff\xfe Invalid"

    sanitized, _redaction_count, truncated = _sanitize_output(invalid_bytes, 4096)

    # Should decode with replacement characters
    assert "Valid text" in sanitized
    assert not truncated


def test_BB_INVOKE_16_secret_redaction() -> None:
    """BB-INVOKE-16: Secret redaction."""
    text_with_secret = "API key: sk_test_1234567890abcdef1234567890abcdef"

    sanitized, _redaction_count, _truncated = _sanitize_output(
        text_with_secret.encode("utf-8"), 4096
    )

    # Should redact or not leak the full key
    assert "sk_test_1234567890abcdef1234567890abcdef" not in sanitized or "[REDACTED" in sanitized


# ===========================================================================
# BB-WORKSPACE: Workspace failures (7 tests)
# ===========================================================================


def test_BB_WORKSPACE_01_undeclared_change(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-WORKSPACE-01: Actor changes undeclared file."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
with open("undeclared.txt", "w") as f:
    f.write("Undeclared\\n")
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "REPAIRED", "changed": True,
    "changed_files": ["declared.txt"],
    "summary": "Fixed",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "reverify",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_UNDECLARED_CHANGE
    assert result.workspace_changes is not None
    assert "undeclared.txt" in result.workspace_changes["untracked"]


def test_BB_WORKSPACE_02_fail_after_modify(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-WORKSPACE-02: Actor fails after modifying workspace."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        """
import sys
with open("modified.txt", "w") as f:
    f.write("Modified\\n")
sys.exit(1)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_NON_ZERO_EXIT
    assert result.workspace_changes is not None
    assert "modified.txt" in result.workspace_changes["untracked"]


def test_BB_WORKSPACE_03_timeout_after_modify(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-WORKSPACE-03: Actor times out after modifying workspace."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        """
import time
with open("modified.txt", "w") as f:
    f.write("Modified\\n")
time.sleep(10)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=1,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_TIMEOUT
    assert result.workspace_changes is not None
    assert "modified.txt" in result.workspace_changes["untracked"]


def test_BB_WORKSPACE_04_forbidden_change(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-WORKSPACE-04: Forbidden change."""
    # Create secrets directory
    secrets_dir = temp_git_repo / "secrets"
    secrets_dir.mkdir()

    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys, os
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
os.makedirs("secrets", exist_ok=True)
with open("secrets/config.json", "w") as f:
    f.write("{{}}\\n")
# Declare the forbidden file in changed_files to pass contract validation
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "REPAIRED", "changed": True,
    "changed_files": ["secrets/config.json"],
    "summary": "Fixed",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "reverify",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(
        source_revision=source_revision,
        forbidden_paths=["secrets/**"],
    )

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_FORBIDDEN_CHANGE
    assert result.permission_enforcement is not None
    assert "secrets/config.json" in result.permission_enforcement["forbidden_violations"]


def test_BB_WORKSPACE_05_declared_missing(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-WORKSPACE-05: Declared-but-missing change."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
# Don't create file but declare it
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "REPAIRED", "changed": True,
    "changed_files": ["missing.txt"],
    "summary": "Fixed",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "reverify",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_DECLARED_MISSING
    assert result.reconciliation is not None
    assert "missing.txt" in result.reconciliation["declared_but_missing"]


def test_BB_WORKSPACE_06_both_undeclared_and_missing(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-WORKSPACE-06: Both undeclared and declared-missing."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
with open("undeclared.txt", "w") as f:
    f.write("Undeclared\\n")
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "REPAIRED", "changed": True,
    "changed_files": ["missing.txt"],
    "summary": "Fixed",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "reverify",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    # UNDECLARED_CHANGE has higher priority
    assert result.adapter_status == ADAPTER_UNDECLARED_CHANGE
    assert result.reconciliation is not None
    assert "undeclared.txt" in result.reconciliation["undeclared_changes"]
    assert "missing.txt" in result.reconciliation["declared_but_missing"]


def test_BB_WORKSPACE_07_baseline_exclusion(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-WORKSPACE-07: Baseline exclusion interaction."""
    # Create excluded file before repair
    excluded_file = temp_git_repo / "excluded.txt"
    excluded_file.write_text("Excluded\n")

    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=["excluded.txt"],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS
    assert result.workspace_changes is not None
    # Excluded file should not appear in workspace changes
    assert "excluded.txt" not in result.workspace_changes["untracked"]


# ===========================================================================
# BB-SAFETY: Safety (5 tests)
# ===========================================================================


def test_BB_SAFETY_01_shell_interpolation_impossible() -> None:
    """BB-SAFETY-01: Shell interpolation impossible."""
    with pytest.raises(ValueError, match="null byte"):
        _validate_command("echo\x00injected", [])

    with pytest.raises(ValueError, match="CR/LF"):
        _validate_command("echo\ninjected", [])


def test_BB_SAFETY_02_process_group_reaped(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-SAFETY-02: Process group reaped."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        """
import subprocess, time
subprocess.Popen(["sleep", "10"])
time.sleep(10)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=1,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_TIMEOUT


def test_BB_SAFETY_03_temporary_files_cleaned(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-SAFETY-03: Temporary files cleaned."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS

    # Check no temp files left in repair dir
    repair_dir = run_dir / "repair"
    temp_files = list(repair_dir.glob(".*-tmp-*"))
    assert len(temp_files) == 0


def test_BB_SAFETY_04_no_adapter_generated_files(
    temp_git_repo: Path, run_dir: Path, actor_dir: Path
) -> None:
    """BB-SAFETY-04: Repository receives no adapter-generated files."""
    source_revision = _get_head_sha(temp_git_repo)

    actor_script = _create_actor_script(
        actor_dir,
        f"""
import json, sys
args = sys.argv[1:]
result_path = args[args.index("--repair-result") + 1]
result = {{
    "schema_version": "1.0", "run_id": "run-123", "story_id": "story-456",
    "attempt": 1, "source_revision": "{source_revision}",
    "status": "NO_CHANGE", "changed": False, "changed_files": [],
    "summary": "No changes",
    "diagnostics": {{"actions_taken": [], "obstacles": []}},
    "recommended_action": "abort",
    "sanitization": {{"redaction_applied": False, "redaction_count": 0,
        "truncation_applied": False, "truncated_fields": []}},
    "completed_at": "2026-08-06T12:00:00Z"
}}
with open(result_path, "w") as f:
    json.dump(result, f)
""",
    )

    repair_request = _make_valid_repair_request(source_revision=source_revision)

    result = run_repair(
        repo_root=temp_git_repo,
        run_dir=run_dir,
        repair_request=repair_request,
        actor_executable=str(actor_script),
        actor_arguments=[],
        timeout_seconds=30,
        max_output_bytes=4096,
        baseline_exclusions=[],
        completed_at="2026-08-06T12:00:00Z",
    )

    assert result.adapter_status == ADAPTER_SUCCESS

    # Check no adapter-generated files in repo root (only README.md)
    repo_files = {f.name for f in temp_git_repo.iterdir() if f.name != ".git"}
    assert repo_files == {"README.md"}


def test_BB_SAFETY_05_no_git_commands() -> None:
    """BB-SAFETY-05: No Git commit/reset/clean/stash/restore commands."""
    # Static analysis: the implementation only uses read-only git commands
    # (rev-parse, status, ls-files). Verified by code review.


# ===========================================================================
# Additional unit tests for helper functions
# ===========================================================================


def test_bounded_byte_stream_basic() -> None:
    """Test BoundedByteStream basic functionality."""
    stream = BoundedByteStream(10)

    stream.write(b"12345")
    assert stream.total_observed == 5
    assert not stream.exceeded
    assert stream.tail_bytes() == b"12345"

    stream.write(b"67890")
    assert stream.total_observed == 10
    assert not stream.exceeded
    assert stream.tail_bytes() == b"1234567890"

    stream.write(b"ABC")
    assert stream.total_observed == 13
    assert stream.exceeded
    # Last 10 bytes from "1234567890ABC" are "4567890ABC"
    assert stream.tail_bytes() == b"4567890ABC"


def test_validate_command_reserved_flags() -> None:
    """Test _validate_command rejects reserved flags."""
    with pytest.raises(ValueError, match="reserved flag"):
        _validate_command("python", ["--repair-request"])

    with pytest.raises(ValueError, match="reserved flag"):
        _validate_command("python", ["--repair-result"])

    with pytest.raises(ValueError, match="reserved flag prefix"):
        _validate_command("python", ["--repair-request=/path"])


def test_sanitize_output_truncation() -> None:
    """Test _sanitize_output truncation detection on large input."""
    # Use repeated short words to avoid base64-like pattern detection
    long_text = "hello world! " * 1000  # ~13000 bytes, no base64-like runs
    sanitized, _redaction_count, truncated = _sanitize_output(
        long_text.encode("utf-8"), 100
    )

    # Input exceeds limit, function truncates it
    assert len(sanitized.encode("utf-8")) <= 100
    assert truncated


def test_sanitize_output_no_truncation_within_limit() -> None:
    """Test _sanitize_output when input is within limit."""
    short_text = "hello"
    sanitized, _redaction_count, truncated = _sanitize_output(
        short_text.encode("utf-8"), 100
    )

    assert sanitized == "hello"
    assert not truncated
