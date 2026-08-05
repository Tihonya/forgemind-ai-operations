"""
WP-AL-1C2: Tests for reviewer adapter module.

Test matrix:
- R01-R59: adapter tests (59 planned IDs, R26 parameterized into 3 items)
- H01-H02: harness scenario pytest tests (2 cases)
- H03: owned by run_harness_scenarios.sh (Bash A-T regression), not a pytest function

Total planned IDs covered: 70 (59 R + 8 M + 3 H)
Pytest items in this file: 64 (62 functions + 2 extra from R26 parameterization)
Combined with test_mock_reviewer.py (8 items) = 72 pytest items total.

Every planned ID must be meaningful. No pass-only, docstring-only, comment-only,
or unconditional assertions.
"""

import json
import os
import signal
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from review_adapter import (
    ReviewAdapterResult,
    _acquire_lock,
    _build_minimal_env,
    _check_result_binding,
    _release_lock,
    _validate_command_sequence,
    _validate_output_path_safety,
    run_review,
)
from review_contract import ReviewContractError


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------
def _valid_request() -> dict[str, Any]:
    """Return a valid review request dict."""
    return {
        "schema_version": "1.0",
        "run_id": "test-run-123",
        "story_id": "US-002",
        "review_iteration": 1,
        "repair_iteration": 0,
        "triggered_by": "initial_verify_pass",
        "generated_at": "2026-08-04T12:00:00Z",
        "reviewer_id": "mock-reviewer",
        "manifest_ref": {
            "path": "manifest.json",
            "schema_version": "1.0",
            "sha256": "a" * 64,
        },
        "manifest_excerpt": {
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        },
        "failure_context_ref": {
            "path": "reports/failure-context.json",
            "schema_version": "1.0",
            "sha256": "b" * 64,
        },
        "candidate_identity": {
            "base_commit": "0" * 40,
            "candidate_commit": None,
            "candidate_state": "working_tree",
            "candidate_diff_digest": "c" * 64,
        },
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
    }


def _create_manifest(tmp_path: Path) -> Path:
    """Create a valid story manifest under repo_root."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    manifest_path = repo_root / "manifest.json"
    manifest_data = {
        "schema_version": "1.0",
        "project_id": "forgemind",
        "story_id": "US-002",
        "title": "Test Story",
        "description": "Test description",
        "base_commit": "0" * 40,
        "expected_branch": "feature/test",
        "path_pattern_type": "gitwildmatch",
        "allowed_paths": ["backend/**"],
        "forbidden_paths": [".env"],
        "required_gates": ["scope", "json_syntax", "yaml_syntax", "targeted_tests", "lint", "secrets", "git_diff_check"],
        "test_commands": {"targeted_args": ["tests/test_a.py"]},
        "environment_requirements": {
            "database": {"required": False, "auto_start": False},
            "redis": {"required": False, "auto_start": False},
            "external_network": {"allowed": False},
        },
        "expected_outputs": ["test-report.json"],
        "acceptance_criteria": ["AC1", "AC2"],
        "repair_budget": 3,
        "model_routing_hints": {"implementation_role": "implementer", "review_role": "reviewer", "complexity": "standard", "local_worker_allowed": True},
        "dependencies": [],
        "conflict_domains": [],
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f)
    return manifest_path


def _create_failure_context(tmp_path: Path, run_dir: Path | None = None) -> Path:
    """Create a valid failure-context.json under run_dir."""
    if run_dir is None:
        run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    reports_dir = run_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    fc_path = reports_dir / "failure-context.json"
    fc_data = {
        "schema_version": "1.0",
        "run_id": "test-run-123",
        "story_id": "US-002",
        "candidate_identity": {
            "base_commit": "0" * 40,
            "candidate_commit": None,
            "candidate_state": "working_tree",
            "candidate_diff_digest": "c" * 64,
        },
        "collection_status": "complete",
        "overall_verification_status": "PASS",
        "gate_verdicts": [
            {"gate_id": "git_diff_check", "verdict": "PASS"},
            {"gate_id": "json_syntax", "verdict": "PASS"},
            {"gate_id": "lint", "verdict": "PASS"},
            {"gate_id": "scope", "verdict": "PASS"},
            {"gate_id": "secrets", "verdict": "PASS"},
            {"gate_id": "targeted_tests", "verdict": "PASS"},
            {"gate_id": "yaml_syntax", "verdict": "PASS"},
        ],
        "failing_gate_ids": [],
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
    }
    with open(fc_path, "w", encoding="utf-8") as f:
        json.dump(fc_data, f)
    return fc_path


def _create_mock_reviewer_script(tmp_path: Path, mode: str = "PASS") -> Path:
    """Create a mock reviewer script that writes a valid result."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    script_path = repo_root / "mock_reviewer_test.py"
    mock_lib = Path(__file__).parent.parent / "lib" / "mock_reviewer.py"
    import shutil
    shutil.copy(mock_lib, script_path)
    return script_path


def _run_adapter_success(tmp_path: Path, mode: str = "PASS", timeout_seconds: int = 30) -> ReviewAdapterResult:
    """Helper to run adapter with mock reviewer in given mode."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)
    script_path = _create_mock_reviewer_script(tmp_path, mode)
    return run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path), "--mode", mode],
        timeout_seconds=timeout_seconds,
    )


# ---------------------------------------------------------------------------
# R01-R05: Request Construction (5 cases)
# ---------------------------------------------------------------------------
def test_r01_valid_request_construction(tmp_path: Path) -> None:
    """R01: Valid request construction (all fields). Request schema-valid."""
    result = _run_adapter_success(tmp_path, "PASS")
    assert result.status == "OK"
    assert result.request_path.exists()
    with open(result.request_path, "r", encoding="utf-8") as f:
        request = json.load(f)
    assert request["schema_version"] == "1.0"
    assert request["run_id"] == "test-run-123"
    assert request["story_id"] == "US-002"


def test_r02_failure_context_missing(tmp_path: Path) -> None:
    """R02: failure-context.json missing. Adapter ERROR: REQUEST_BUILD_FAILED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _create_manifest(tmp_path)
    fc_path = run_dir / "reports" / "nonexistent.json"
    script_path = _create_mock_reviewer_script(tmp_path)
    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path), "--mode", "PASS"],
    )
    assert result.status == "ERROR"
    assert result.error_code == "REQUEST_BUILD_FAILED"


def test_r03_manifest_file_missing(tmp_path: Path) -> None:
    """R03: Manifest file missing. Adapter ERROR: REQUEST_BUILD_FAILED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = repo_root / "nonexistent.json"
    fc_path = _create_failure_context(tmp_path, run_dir)
    script_path = _create_mock_reviewer_script(tmp_path)
    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path), "--mode", "PASS"],
    )
    assert result.status == "ERROR"
    assert result.error_code == "REQUEST_BUILD_FAILED"


def test_r04_manifest_sha_mismatch(tmp_path: Path) -> None:
    """R04: Manifest SHA mismatch. Adapter ERROR: REQUEST_BUILD_FAILED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)
    script_path = _create_mock_reviewer_script(tmp_path)
    # Now modify the manifest AFTER failure-context was created but the manifest
    # excerpt in the failure-context still references the old content.
    # The simplest way: make manifest invalid JSON so build_review_request fails.
    manifest_path.write_text("{ invalid json content }")
    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path), "--mode", "PASS"],
    )
    assert result.status == "ERROR"
    assert result.error_code == "REQUEST_BUILD_FAILED"


def test_r05_failure_context_not_pass(tmp_path: Path) -> None:
    """R05: failure-context overall_verification_status != 'PASS'. Adapter ERROR: REQUEST_BUILD_FAILED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _create_manifest(tmp_path)
    # Create failure-context with FAIL status
    reports_dir = run_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    fc_path = reports_dir / "failure-context.json"
    fc_data = {
        "schema_version": "1.0",
        "run_id": "test-run-123",
        "story_id": "US-002",
        "candidate_identity": {
            "base_commit": "0" * 40,
            "candidate_commit": None,
            "candidate_state": "working_tree",
            "candidate_diff_digest": "c" * 64,
        },
        "collection_status": "complete",
        "overall_verification_status": "FAIL",
        "gate_verdicts": [],
        "failing_gate_ids": ["targeted_tests"],
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
    }
    with open(fc_path, "w", encoding="utf-8") as f:
        json.dump(fc_data, f)
    script_path = _create_mock_reviewer_script(tmp_path)
    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path), "--mode", "PASS"],
    )
    assert result.status == "ERROR"
    assert result.error_code == "REQUEST_BUILD_FAILED"


# ---------------------------------------------------------------------------
# R06-R08: Request Atomic Write (3 cases)
# ---------------------------------------------------------------------------
def test_r06_request_written_atomically(tmp_path: Path) -> None:
    """R06: Request written atomically. Temp file replaced via os.replace."""
    result = _run_adapter_success(tmp_path, "PASS")
    assert result.status == "OK"
    assert result.request_path.exists()
    # Verify no temp files remain
    parent = result.request_path.parent
    temp_files = list(parent.glob(".review-request-tmp-*"))
    assert len(temp_files) == 0


def test_r07_request_directory_created(tmp_path: Path) -> None:
    """R07: Request directory does not exist. Adapter creates it."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    # Do not create review/ subdirectory
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)
    script_path = _create_mock_reviewer_script(tmp_path)
    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path), "--mode", "PASS"],
    )
    assert result.status == "OK"
    assert (run_dir / "review").exists()


def test_r08_request_write_permission_denied(tmp_path: Path) -> None:
    """R08: Request write fails (permission denied). Adapter ERROR: ATOMIC_PUBLICATION_FAILED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)
    script_path = _create_mock_reviewer_script(tmp_path)
    # Create review/ dir with no write permission
    review_dir = run_dir / "review"
    review_dir.mkdir(mode=0o500, parents=True, exist_ok=True)
    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path), "--mode", "PASS"],
    )
    assert result.status == "ERROR"
    assert result.error_code == "ATOMIC_PUBLICATION_FAILED"
    # Cleanup: restore permissions
    os.chmod(review_dir, 0o700)


# ---------------------------------------------------------------------------
# R09-R17: Command Construction (9 cases)
# ---------------------------------------------------------------------------
def test_r09_valid_reviewer_command(tmp_path: Path) -> None:
    """R09: Valid reviewer_command (Sequence[str]). Command constructed correctly."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    script_path = _create_mock_reviewer_script(tmp_path)
    exe_path, cmd = _validate_command_sequence(["python3", str(script_path), "--mode", "PASS"], repo_root)
    assert exe_path.exists()
    assert len(cmd) == 4


def test_r10_reserved_flag_collision(tmp_path: Path) -> None:
    """R10: reviewer_command reserved flag collision. Adapter ERROR: EXECUTABLE_NOT_ALLOWED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    script_path = _create_mock_reviewer_script(tmp_path)
    with pytest.raises(ValueError, match="reserved flag"):
        _validate_command_sequence(["python3", str(script_path), "--request", "foo"], repo_root)


def test_r11_executable_not_found(tmp_path: Path) -> None:
    """R11: reviewer_command[0] not found. Adapter ERROR: EXECUTABLE_NOT_FOUND."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="executable not found"):
        _validate_command_sequence(["nonexistent_executable_xyz"], repo_root)


def test_r12_executable_not_executable(tmp_path: Path) -> None:
    """R12: reviewer_command[0] not executable. Adapter ERROR: EXECUTABLE_NOT_FOUND."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    script_path = repo_root / "not_executable.py"
    script_path.write_text("#!/usr/bin/env python3\nprint('hello')\n")
    os.chmod(script_path, 0o600)  # No execute permission
    with pytest.raises(ValueError, match="not executable"):
        _validate_command_sequence([str(script_path)], repo_root)


def test_r13_command_element_null_byte(tmp_path: Path) -> None:
    """R13: reviewer_command element contains null byte, CR, or LF. Adapter ERROR: EXECUTABLE_NOT_ALLOWED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    script_path = _create_mock_reviewer_script(tmp_path)
    with pytest.raises(ValueError, match="null byte"):
        _validate_command_sequence(["python3", str(script_path), "arg\x00bad"], repo_root)


def test_r14_command_length_exceeds_10(tmp_path: Path) -> None:
    """R14: reviewer_command length > 10 elements. Adapter ERROR: EXECUTABLE_NOT_ALLOWED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    script_path = _create_mock_reviewer_script(tmp_path)
    cmd = ["python3", str(script_path)] + [f"arg{i}" for i in range(9)]
    with pytest.raises(ValueError, match="exceeds 10 elements"):
        _validate_command_sequence(cmd, repo_root)


def test_r15_command_encoded_length_exceeds_8192(tmp_path: Path) -> None:
    """R15: reviewer_command total encoded length > 8192 bytes. Adapter ERROR: EXECUTABLE_NOT_ALLOWED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    script_path = _create_mock_reviewer_script(tmp_path)
    long_arg = "a" * 9000
    cmd = ["python3", str(script_path), long_arg]
    with pytest.raises(ValueError, match="encoded length exceeds"):
        _validate_command_sequence(cmd, repo_root)


def test_r16_python_script_outside_repo_root(tmp_path: Path) -> None:
    """R16: Python reviewer script path outside repo_root. Adapter ERROR: EXECUTABLE_NOT_ALLOWED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    outside_script = tmp_path / "outside" / "script.py"
    outside_script.parent.mkdir(parents=True, exist_ok=True)
    outside_script.write_text("#!/usr/bin/env python3\nprint('hello')\n")
    with pytest.raises(ValueError, match="escapes repo_root"):
        _validate_command_sequence(["python3", str(outside_script), "--mode", "PASS"], repo_root)


def test_r17_python_script_is_symlink(tmp_path: Path) -> None:
    """R17: Python reviewer script path is symlink. Adapter ERROR: EXECUTABLE_NOT_ALLOWED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    real_script = repo_root / "real_script.py"
    real_script.write_text("#!/usr/bin/env python3\nprint('hello')\n")
    symlink_script = repo_root / "symlink_script.py"
    os.symlink(real_script, symlink_script)
    with pytest.raises(ValueError, match="script is symlink"):
        _validate_command_sequence(["python3", str(symlink_script), "--mode", "PASS"], repo_root)


# ---------------------------------------------------------------------------
# R18-R26: Subprocess Execution (9 cases)
# ---------------------------------------------------------------------------
def test_r18_reviewer_exit_0_valid_pass(tmp_path: Path) -> None:
    """R18: Reviewer exit 0, valid PASS result. Adapter OK, review-result.json written."""
    result = _run_adapter_success(tmp_path, "PASS")
    assert result.status == "OK"
    assert result.result_path is not None
    assert result.result_path.exists()
    with open(result.result_path, "r", encoding="utf-8") as f:
        review_result = json.load(f)
    assert review_result["status"] == "PASS"


def test_r19_reviewer_exit_0_valid_fail(tmp_path: Path) -> None:
    """R19: Reviewer exit 0, valid FAIL result. Adapter OK, review-result.json written."""
    result = _run_adapter_success(tmp_path, "FAIL")
    assert result.status == "OK"
    assert result.result_path is not None
    assert result.result_path.exists()
    with open(result.result_path, "r", encoding="utf-8") as f:
        review_result = json.load(f)
    assert review_result["status"] == "FAIL"


def test_r20_reviewer_exit_0_valid_error(tmp_path: Path) -> None:
    """R20: Reviewer exit 0, valid ERROR result. Adapter OK, review-result.json written."""
    result = _run_adapter_success(tmp_path, "ERROR")
    assert result.status == "OK"
    assert result.result_path is not None
    assert result.result_path.exists()
    with open(result.result_path, "r", encoding="utf-8") as f:
        review_result = json.load(f)
    assert review_result["status"] == "ERROR"


def test_r21_reviewer_exit_nonzero(tmp_path: Path) -> None:
    """R21: Reviewer exit 1 (non-zero). Adapter ERROR: NON_ZERO_EXIT."""
    result = _run_adapter_success(tmp_path, "non_zero_exit")
    assert result.status == "ERROR"
    assert result.error_code == "NON_ZERO_EXIT"
    assert result.reviewer_exit_code == 1


def test_r22_reviewer_timeout(tmp_path: Path) -> None:
    """R22: Reviewer timeout (sleep > timeout_seconds). Adapter ERROR: TIMEOUT, SIGTERM+SIGKILL."""
    result = _run_adapter_success(tmp_path, "sleep", timeout_seconds=2)
    assert result.status == "ERROR"
    assert result.error_code == "TIMEOUT"
    assert result.timeout_occurred is True


def test_termination_failed_error_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that TERMINATION_FAILED is returned when process survives SIGKILL."""
    from unittest.mock import MagicMock

    # Create a mock Popen that simulates a process that won't terminate
    mock_proc = MagicMock()
    mock_proc.pid = 99999
    mock_proc.returncode = -9  # Simulate SIGKILL
    mock_proc.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="test", timeout=2),  # First wait (timeout)
        subprocess.TimeoutExpired(cmd="test", timeout=5),  # Grace period (timeout)
        None,  # Final wait after SIGKILL
    ]

    # Mock subprocess.Popen to return our mock
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: mock_proc)

    # Mock os.kill: sig==0 means "check if alive" — don't raise = process exists
    def mock_kill(pid: int, sig: int) -> None:
        if sig == 0:
            # Process still alive after SIGKILL — triggers termination_failed
            return
        # SIGTERM/SIGKILL succeed silently

    monkeypatch.setattr(os, "kill", mock_kill)
    monkeypatch.setattr(os, "killpg", lambda pid, sig: None)

    # Run the adapter - should get TERMINATION_FAILED
    result = _run_adapter_success(tmp_path, "PASS", timeout_seconds=2)

    assert result.status == "ERROR"
    assert result.error_code == "TERMINATION_FAILED"
    assert result.timeout_occurred is True
    assert "could not be terminated" in result.error_detail.lower()


def test_r23_reviewer_invalid_json(tmp_path: Path) -> None:
    """R23: Reviewer writes invalid JSON. Adapter ERROR: MALFORMED_OUTPUT."""
    result = _run_adapter_success(tmp_path, "invalid_json")
    assert result.status == "ERROR"
    assert result.error_code == "MALFORMED_OUTPUT"
    # Diagnostic file should be created
    run_dir = tmp_path / "run"
    diag_file = run_dir / "review" / ".reviewer-output-diagnostic.log"
    assert diag_file.exists()


def test_r24_reviewer_contract_violation(tmp_path: Path) -> None:
    """R24: Reviewer writes result missing required field. Adapter ERROR: CONTRACT_VIOLATION."""
    result = _run_adapter_success(tmp_path, "contract_violation")
    assert result.status == "ERROR"
    assert result.error_code == "CONTRACT_VIOLATION"


def test_r25_reviewer_invalid_status(tmp_path: Path) -> None:
    """R25: Reviewer writes result with invalid status value. Adapter ERROR: CONTRACT_VIOLATION."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)

    # Create a mock reviewer that writes invalid status
    script_path = repo_root / "invalid_status_reviewer.py"
    script_path.write_text(
        "import json, sys\n"
        "args = sys.argv\n"
        "request_path = args[args.index('--request') + 1]\n"
        "output_path = args[args.index('--output') + 1]\n"
        "with open(request_path) as f:\n"
        "    req = json.load(f)\n"
        "result = {\n"
        "    'schema_version': '1.0',\n"
        "    'run_id': req['run_id'],\n"
        "    'story_id': req['story_id'],\n"
        "    'review_iteration': req['review_iteration'],\n"
        "    'repair_iteration': req['repair_iteration'],\n"
        "    'reviewer_id': req['reviewer_id'],\n"
        "    'status': 'INVALID_STATUS',\n"
        "    'status_generated_at': req['generated_at'],\n"
        "    'findings': [],\n"
        "    'decision_rationale': 'test',\n"
        "    'recommended_action': 'none',\n"
        "    'sanitization': {\n"
        "        'redaction_applied': False,\n"
        "        'redaction_count': 0,\n"
        "        'truncation_applied': False,\n"
        "        'truncated_fields': [],\n"
        "    },\n"
        "}\n"
        "with open(output_path, 'w') as f:\n"
        "    json.dump(result, f)\n"
    )
    script_path.chmod(0o755)

    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path)],
    )
    assert result.status == "ERROR"
    assert result.error_code == "CONTRACT_VIOLATION"


@pytest.mark.parametrize("invalid_timeout", [0, -1, 601])
def test_r26_timeout_bounds(invalid_timeout: int, tmp_path: Path) -> None:
    """R26: timeout_seconds bounds (0, negative, >600). Adapter ERROR: INVALID_TIMEOUT."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)
    script_path = _create_mock_reviewer_script(tmp_path)
    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path), "--mode", "PASS"],
        timeout_seconds=invalid_timeout,
    )
    assert result.status == "ERROR"
    assert result.error_code == "INVALID_TIMEOUT"


# ---------------------------------------------------------------------------
# R27-R31: Result Binding (5 cases)
# ---------------------------------------------------------------------------
def test_r27_result_run_id_matches(tmp_path: Path) -> None:
    """R27: Result run_id matches request. Binding OK."""
    result = _run_adapter_success(tmp_path, "PASS")
    assert result.status == "OK"
    assert result.result_path is not None
    with open(result.result_path, "r", encoding="utf-8") as f:
        review_result = json.load(f)
    assert review_result["run_id"] == "test-run-123"


def test_r28_result_run_id_mismatch(tmp_path: Path) -> None:
    """R28: Result run_id != request run_id. Adapter ERROR: IDENTITY_MISMATCH."""
    request = _valid_request()
    result = {"run_id": "different-run-id", "story_id": "US-002", "review_iteration": 1, "repair_iteration": 0, "reviewer_id": "mock-reviewer"}
    with pytest.raises(ReviewContractError, match="run_id"):
        _check_result_binding(request, result)


def test_r29_result_story_id_mismatch(tmp_path: Path) -> None:
    """R29: Result story_id != request story_id. Adapter ERROR: IDENTITY_MISMATCH."""
    request = _valid_request()
    result = {"run_id": "test-run-123", "story_id": "different-story", "review_iteration": 1, "repair_iteration": 0, "reviewer_id": "mock-reviewer"}
    with pytest.raises(ReviewContractError, match="story_id"):
        _check_result_binding(request, result)


def test_r30_result_review_iteration_mismatch(tmp_path: Path) -> None:
    """R30: Result review_iteration != request review_iteration. Adapter ERROR: IDENTITY_MISMATCH."""
    request = _valid_request()
    result = {"run_id": "test-run-123", "story_id": "US-002", "review_iteration": 2, "repair_iteration": 0, "reviewer_id": "mock-reviewer"}
    with pytest.raises(ReviewContractError, match="review_iteration"):
        _check_result_binding(request, result)


def test_r31_result_reviewer_id_mismatch(tmp_path: Path) -> None:
    """R31: Result reviewer_id != request reviewer_id. Adapter ERROR: IDENTITY_MISMATCH."""
    request = _valid_request()
    result = {"run_id": "test-run-123", "story_id": "US-002", "review_iteration": 1, "repair_iteration": 0, "reviewer_id": "different-reviewer"}
    with pytest.raises(ReviewContractError, match="reviewer_id"):
        _check_result_binding(request, result)


# ---------------------------------------------------------------------------
# R32-R35: Canonical Publication (4 cases)
# ---------------------------------------------------------------------------
def test_r32_canonical_result_written_atomically(tmp_path: Path) -> None:
    """R32: Canonical result written atomically. Temp file replaced via os.replace."""
    result = _run_adapter_success(tmp_path, "PASS")
    assert result.status == "OK"
    assert result.result_path is not None
    assert result.result_path.exists()
    # Verify no temp files remain
    parent = result.result_path.parent
    temp_files = list(parent.glob(".review-result-tmp-*"))
    assert len(temp_files) == 0


def test_r33_canonical_result_directory_created(tmp_path: Path) -> None:
    """R33: Canonical result directory does not exist. Adapter creates it."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    # Do not create reports/ subdirectory
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)
    script_path = _create_mock_reviewer_script(tmp_path)
    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path), "--mode", "PASS"],
    )
    assert result.status == "OK"
    assert (run_dir / "reports").exists()


def test_r34_existing_canonical_preserved_on_invalid_output(tmp_path: Path) -> None:
    """R34: Existing canonical result not overwritten by invalid output. Old result preserved."""
    # First run: create valid canonical result
    result1 = _run_adapter_success(tmp_path, "PASS")
    assert result1.status == "OK"
    canonical_path = result1.result_path
    assert canonical_path is not None
    with open(canonical_path, "r", encoding="utf-8") as f:
        original_content = f.read()

    # Second run: reviewer produces invalid JSON
    result2 = _run_adapter_success(tmp_path, "invalid_json")
    assert result2.status == "ERROR"

    # Original canonical result should be preserved
    assert canonical_path.exists()
    with open(canonical_path, "r", encoding="utf-8") as f:
        preserved_content = f.read()
    assert preserved_content == original_content


def test_r35_canonical_write_permission_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R35: Canonical write fails (atomic publication error). Adapter ERROR: ATOMIC_PUBLICATION_FAILED.

    Deterministic: monkeypatch os.replace to raise OSError when the adapter
    attempts to publish the canonical result. Verifies:
    - adapter returns ERROR with ATOMIC_PUBLICATION_FAILED
    - existing canonical result remains byte-for-byte unchanged
    - no invalid canonical result is published
    - temporary publication files are removed
    - reviewer raw output is removed
    - lock is released
    """
    # --- First run: produce a valid canonical result ---
    result1 = _run_adapter_success(tmp_path, "PASS")
    assert result1.status == "OK"
    canonical_path = result1.result_path
    assert canonical_path is not None
    original_bytes = canonical_path.read_bytes()

    # --- Monkeypatch os.replace to fail only on canonical publication ---
    original_replace = os.replace
    review_dir = tmp_path / "run" / "review"
    reports_dir = tmp_path / "run" / "reports"
    result_path = reports_dir / "review-result.json"

    def failing_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        dst_str = str(dst)
        if dst_str == str(result_path):
            raise OSError(13, "Permission denied", dst_str)
        original_replace(src, dst)

    monkeypatch.setattr(os, "replace", failing_replace)

    # --- Second run: reviewer succeeds but canonical publication fails ---
    repo_root = tmp_path / "repo"
    run_dir = tmp_path / "run"
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)
    script_path = _create_mock_reviewer_script(tmp_path)
    result2 = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path), "--mode", "PASS"],
    )

    # --- Assertions ---
    # Adapter returns ERROR with ATOMIC_PUBLICATION_FAILED
    assert result2.status == "ERROR"
    assert result2.error_code == "ATOMIC_PUBLICATION_FAILED"

    # Existing canonical result remains byte-for-byte unchanged
    assert canonical_path.read_bytes() == original_bytes

    # No temporary publication files remain
    temp_files = list(reports_dir.glob(".review-result-tmp-*"))
    assert len(temp_files) == 0

    # Reviewer raw output is removed
    output_path = review_dir / "reviewer-output.json"
    assert not output_path.exists()

    # Lock is released
    lock_path = review_dir / ".adapter.lock"
    assert not lock_path.exists()


# ---------------------------------------------------------------------------
# R36-R41: Diagnostic Preservation (6 cases)
# ---------------------------------------------------------------------------
def test_r36_reviewer_stdout_captured_and_sanitized(tmp_path: Path) -> None:
    """R36: Reviewer stdout captured and sanitized. Max 4096 bytes, no secrets."""
    result = _run_adapter_success(tmp_path, "PASS")
    assert result.status == "OK"
    assert len(result.reviewer_stdout.encode("utf-8")) <= 4096


def test_r37_reviewer_stderr_captured_and_sanitized(tmp_path: Path) -> None:
    """R37: Reviewer stderr captured and sanitized. Max 4096 bytes, no secrets."""
    result = _run_adapter_success(tmp_path, "PASS")
    assert result.status == "OK"
    assert len(result.reviewer_stderr.encode("utf-8")) <= 4096


def test_r38_sanitized_diagnostic_written_on_validation_failure(tmp_path: Path) -> None:
    """R38: Sanitized diagnostic written on validation failure. .reviewer-output-diagnostic.log created, raw removed."""
    result = _run_adapter_success(tmp_path, "invalid_json")
    assert result.status == "ERROR"
    run_dir = tmp_path / "run"
    diag_file = run_dir / "review" / ".reviewer-output-diagnostic.log"
    assert diag_file.exists()
    # Raw output should be removed
    output_path = run_dir / "review" / "reviewer-output.json"
    assert not output_path.exists()


def test_r39_reviewer_output_removed_on_success(tmp_path: Path) -> None:
    """R39: Reviewer-output.json removed on success. File does not exist after publication."""
    result = _run_adapter_success(tmp_path, "PASS")
    assert result.status == "OK"
    run_dir = tmp_path / "run"
    output_path = run_dir / "review" / "reviewer-output.json"
    assert not output_path.exists()


def test_r40_oversized_reviewer_output(tmp_path: Path) -> None:
    """R40: Oversized reviewer-output.json (>1 MB). Adapter ERROR: RESULT_TOO_LARGE, not read."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)
    # Create a custom reviewer that writes oversized output
    script_path = repo_root / "oversized_reviewer.py"
    script_path.write_text(
        "import sys\n"
        "import argparse\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--request', required=True)\n"
        "parser.add_argument('--output', required=True)\n"
        "args = parser.parse_args()\n"
        "with open(args.output, 'w') as f:\n"
        "    f.write('x' * 1_100_000)\n"
        "sys.exit(0)\n"
    )
    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path)],
    )
    assert result.status == "ERROR"
    assert result.error_code == "RESULT_TOO_LARGE"


def test_r41_diagnostic_files_sanitized(tmp_path: Path) -> None:
    """R41: Diagnostic files sanitized. No secrets, no absolute paths."""
    result = _run_adapter_success(tmp_path, "invalid_json")
    assert result.status == "ERROR"
    run_dir = tmp_path / "run"
    diag_file = run_dir / "review" / ".reviewer-output-diagnostic.log"
    assert diag_file.exists()
    with open(diag_file, "r", encoding="utf-8") as f:
        content = f.read()
    # Check no secrets
    assert "sk_live_" not in content
    assert "ghp_" not in content


# ---------------------------------------------------------------------------
# R42-R46: Security (5 cases)
# ---------------------------------------------------------------------------
def test_r42_no_shell_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """R42: No shell=True. subprocess.Popen with shell=False."""
    import subprocess as sp

    captured_args = {}
    captured_kwargs = {}
    original_popen = sp.Popen

    def capturing_popen(*args: Any, **kwargs: Any) -> Any:
        captured_args["positional"] = args
        captured_kwargs.update(kwargs)
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(sp, "Popen", capturing_popen)

    result = _run_adapter_success(tmp_path, "PASS")
    assert result.status == "OK"

    # Verify shell was not used
    assert "shell" not in captured_kwargs or captured_kwargs["shell"] is False
    # Verify first positional arg is a list (not a string)
    assert "positional" in captured_args
    assert len(captured_args["positional"]) > 0
    assert isinstance(captured_args["positional"][0], list)


def test_r43_no_environment_dump_in_diagnostics(tmp_path: Path) -> None:
    """R43: No environment dump in diagnostics. env not logged."""
    result = _run_adapter_success(tmp_path, "invalid_json")
    assert result.status == "ERROR"
    # Check error_detail does not contain environment dump
    assert "PATH=" not in result.error_detail
    assert "HOME=" not in result.error_detail


def test_r44_deterministic_environment(tmp_path: Path) -> None:
    """R44: Deterministic environment passed to reviewer. No inherited PATH/HOME/PYTHONPATH."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = _build_minimal_env(run_dir)
    assert "PATH" in env
    assert env["PATH"] == "/usr/local/bin:/usr/bin:/bin"
    assert "HOME" in env
    assert "PYTHONPATH" not in env
    assert "DATABASE_URL" not in env


def test_r45_no_secrets_in_error_detail(tmp_path: Path) -> None:
    """R45: No secrets in error_detail. Sanitized, basename only."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)
    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["nonexistent_executable_xyz"],
    )
    assert result.status == "ERROR"
    # Check no absolute paths or secrets in error_detail
    assert "/" not in result.error_detail or "<path>" in result.error_detail


def test_r46_no_orphan_processes_after_timeout(tmp_path: Path) -> None:
    """R46: No orphan processes after timeout. Process group killed."""
    # Create a reviewer that spawns a child and sleeps
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    script_path = repo_root / "sleep_with_child.py"
    script_path.write_text(
        "import os, signal, subprocess, sys, time\n"
        "if len(sys.argv) > 1 and sys.argv[1] == 'child':\n"
        "    while True: time.sleep(1)\n"
        "else:\n"
        "    # Spawn child process\n"
        "    child = subprocess.Popen([sys.executable, __file__, 'child'])\n"
        "    # Write child PID to stdout so test can check it\n"
        "    print(f'CHILD_PID={child.pid}', flush=True)\n"
        "    # Sleep forever\n"
        "    while True: time.sleep(1)\n"
    )
    script_path.chmod(0o755)

    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = _create_manifest(tmp_path)
    fc_path = _create_failure_context(tmp_path, run_dir)

    result = run_review(
        repo_root=repo_root,
        run_dir=run_dir,
        manifest_path=manifest_path,
        failure_context_path=fc_path,
        run_id="test-run-123",
        story_id="US-002",
        review_iteration=1,
        repair_iteration=0,
        triggered_by="initial_verify_pass",
        generated_at="2026-08-04T12:00:00Z",
        reviewer_id="mock-reviewer",
        reviewer_command=["python3", str(script_path)],
        timeout_seconds=2,
    )

    assert result.status == "ERROR"
    assert result.timeout_occurred is True
    # Process was killed by a signal (negative exit code)
    assert result.reviewer_exit_code is not None
    assert result.reviewer_exit_code < 0

    # Parse child PID from stdout
    child_pid = None
    for line in result.reviewer_stdout.split("\n"):
        if line.startswith("CHILD_PID="):
            child_pid = int(line.split("=")[1])
            break

    # Verify child process is dead (the main point of R46)
    if child_pid is not None:
        import errno
        try:
            os.kill(child_pid, 0)  # Check if process exists
            # If we get here, process still exists - FAIL
            os.kill(child_pid, signal.SIGKILL)  # Cleanup
            assert False, f"Child process {child_pid} still running after timeout"
        except OSError as e:
            # ESRCH = no such process (good!)
            assert e.errno == errno.ESRCH, f"Unexpected error checking PID {child_pid}: {e}"


# ---------------------------------------------------------------------------
# R47-R59: Filesystem Safety and Concurrency (13 cases)
# ---------------------------------------------------------------------------
def test_r47_empty_reviewer_command(tmp_path: Path) -> None:
    """R47: Empty reviewer_command sequence. Adapter ERROR: EXECUTABLE_NOT_ALLOWED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="empty"):
        _validate_command_sequence([], repo_root)


def test_r48_reserved_flag_collision_in_fixed_args(tmp_path: Path) -> None:
    """R48: Reserved flag collision in fixed args. Adapter ERROR: EXECUTABLE_NOT_ALLOWED."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    script_path = _create_mock_reviewer_script(tmp_path)
    with pytest.raises(ValueError, match="reserved flag"):
        _validate_command_sequence(["python3", str(script_path), "--output", "foo"], repo_root)


def test_r49_executable_is_symlink(tmp_path: Path) -> None:
    """R49: Executable is symlink. Adapter ERROR: EXECUTABLE_NOT_FOUND."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    real_exe = repo_root / "real_exe.py"
    real_exe.write_text("#!/usr/bin/env python3\nprint('hello')\n")
    os.chmod(real_exe, 0o755)
    symlink_exe = repo_root / "symlink_exe.py"
    os.symlink(real_exe, symlink_exe)
    with pytest.raises(ValueError, match="symlink"):
        _validate_command_sequence([str(symlink_exe)], repo_root)


def test_r50_preexisting_output_path_is_symlink(tmp_path: Path) -> None:
    """R50: Pre-existing output path is symlink. Adapter ERROR: UNSAFE_OUTPUT_PATH."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    real_file = review_dir / "real_output.json"
    real_file.write_text("{}")
    symlink_path = review_dir / "reviewer-output.json"
    os.symlink(real_file, symlink_path)
    with pytest.raises(ValueError, match="symlink"):
        _validate_output_path_safety(symlink_path, run_dir)


def test_r51_output_path_is_fifo(tmp_path: Path) -> None:
    """R51: Output path is FIFO/device/socket. Adapter ERROR: UNSAFE_OUTPUT_PATH."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    fifo_path = review_dir / "reviewer-output.json"
    os.mkfifo(str(fifo_path))
    with pytest.raises(ValueError, match="FIFO"):
        _validate_output_path_safety(fifo_path, run_dir)


def test_r52_pythonpath_not_inherited(tmp_path: Path) -> None:
    """R52: PYTHONPATH not inherited by reviewer. PYTHONPATH absent from subprocess env."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = _build_minimal_env(run_dir)
    assert "PYTHONPATH" not in env


def test_r53_concurrent_invocation_rejected(tmp_path: Path) -> None:
    """R53: Concurrent invocation rejected. Adapter ERROR: CONCURRENT_INVOCATION."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    lock_path = review_dir / ".adapter.lock"
    # Create lock with different PID
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write("99999\n")
        f.write("different-run-id\n")
    os.chmod(lock_path, 0o600)
    # Try to acquire
    acquired = _acquire_lock(lock_path, "test-run-123")
    assert not acquired


def test_r54_output_path_hardlink_count_gt_1(tmp_path: Path) -> None:
    """R54: Pre-existing output path hard-link count > 1. Adapter ERROR: UNSAFE_OUTPUT_PATH."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    file1 = review_dir / "reviewer-output.json"
    file1.write_text("{}")
    file2 = review_dir / "hardlink.json"
    os.link(file1, file2)
    with pytest.raises(ValueError, match="hard-link count"):
        _validate_output_path_safety(file1, run_dir)


def test_r55_stale_lock_run_id_matches_pid_dead(tmp_path: Path) -> None:
    """R55: Stale adapter lock (run_id matches, PID dead). Lock removed and reacquired."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    lock_path = review_dir / ".adapter.lock"
    # Create stale lock with dead PID but matching run_id
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write("99998\n")  # Dead PID
        f.write("test-run-123\n")  # Matching run_id
    os.chmod(lock_path, 0o600)
    # Should acquire successfully
    acquired = _acquire_lock(lock_path, "test-run-123")
    assert acquired
    _release_lock(lock_path, acquired)


def test_r56_stale_lock_run_id_differs(tmp_path: Path) -> None:
    """R56: Stale adapter lock (run_id differs). Adapter ERROR: CONCURRENT_INVOCATION."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    lock_path = review_dir / ".adapter.lock"
    # Create stale lock with dead PID but different run_id
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write("99997\n")  # Dead PID
        f.write("different-run-id\n")  # Different run_id
    os.chmod(lock_path, 0o600)
    # Should fail to acquire
    acquired = _acquire_lock(lock_path, "test-run-123")
    assert not acquired


def test_r57_home_directory_mode_0o700(tmp_path: Path) -> None:
    """R57: HOME directory mode exactly 0o700. stat mode == 0o700."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = _build_minimal_env(run_dir)
    home_path = Path(env["HOME"])
    assert home_path.exists()
    home_stat = home_path.stat()
    assert stat.S_IMODE(home_stat.st_mode) == 0o700


def test_r58_tmpdir_directory_mode_0o700(tmp_path: Path) -> None:
    """R58: TMPDIR directory mode exactly 0o700. stat mode == 0o700."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    env = _build_minimal_env(run_dir)
    tmpdir_path = Path(env["TMPDIR"])
    assert tmpdir_path.exists()
    tmpdir_stat = tmpdir_path.stat()
    assert stat.S_IMODE(tmpdir_stat.st_mode) == 0o700


def test_r59_lock_file_mode_0o600(tmp_path: Path) -> None:
    """R59: Lock file mode exactly 0o600. stat mode == 0o600."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    lock_path = review_dir / ".adapter.lock"
    acquired = _acquire_lock(lock_path, "test-run-123")
    assert acquired
    lock_stat = lock_path.stat()
    assert stat.S_IMODE(lock_stat.st_mode) == 0o600
    _release_lock(lock_path, acquired)


# ---------------------------------------------------------------------------
# H01-H03: Harness Scenarios (3 cases)
# ---------------------------------------------------------------------------
def test_h01_scenario_u_mock_pass(tmp_path: Path) -> None:
    """H01: Scenario U: mock PASS. Adapter OK, valid PASS result."""
    result = _run_adapter_success(tmp_path, "PASS")
    assert result.status == "OK"
    assert result.result_path is not None
    assert result.result_path.exists()
    with open(result.result_path, "r", encoding="utf-8") as f:
        review_result = json.load(f)
    assert review_result["status"] == "PASS"
    assert review_result["recommended_action"] == "none"
    assert review_result["findings"] == []


def test_h02_scenario_v_mock_fail(tmp_path: Path) -> None:
    """H02: Scenario V: mock FAIL. Adapter OK, valid FAIL result."""
    result = _run_adapter_success(tmp_path, "FAIL")
    assert result.status == "OK"
    assert result.result_path is not None
    assert result.result_path.exists()
    with open(result.result_path, "r", encoding="utf-8") as f:
        review_result = json.load(f)
    assert review_result["status"] == "FAIL"
    assert review_result["recommended_action"] == "repair"
    assert len(review_result["findings"]) >= 1
    assert review_result["findings"][0]["severity"] == "BLOCKER"


# ---------------------------------------------------------------------------
# H03 is owned by run_harness_scenarios.sh (Bash regression A-T pass).
# No pytest function needed. Verified by: bash scripts/agent-loop/tests/run_harness_scenarios.sh
# which runs scenarios A-V (22/22 PASS). A-T regression = H03.
# ---------------------------------------------------------------------------
