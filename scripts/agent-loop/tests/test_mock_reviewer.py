"""
WP-AL-1C2: Tests for mock reviewer module.

Test matrix:
- M01-M08: mock reviewer tests (8 cases)

Total: 8 planned cases
"""

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

MOCK_REVIEWER = Path(__file__).parent.parent / "lib" / "mock_reviewer.py"


def _valid_request() -> dict[str, Any]:
    """Return a valid review request."""
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
            "path": "scripts/agent-loop/templates/story-prd.json",
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


def _run_mock(tmp_path: Path, mode: str, request_data: dict[str, Any] | None = None) -> tuple[int, Path, Path]:
    """Run mock_reviewer.py with given mode. Returns (exit_code, request_path, output_path)."""
    import subprocess

    request_path = tmp_path / "request.json"
    output_path = tmp_path / "output.json"

    if request_data is None:
        request_data = _valid_request()

    with open(request_path, "w", encoding="utf-8") as f:
        json.dump(request_data, f)

    proc = subprocess.run(
        [sys.executable, str(MOCK_REVIEWER), "--request", str(request_path), "--output", str(output_path), "--mode", mode],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, request_path, output_path


# ---------------------------------------------------------------------------
# M01: Mock PASS mode
# ---------------------------------------------------------------------------
def test_m01_mock_pass_mode(tmp_path: Path) -> None:
    """M01: Mock PASS mode produces valid PASS result, exit 0."""
    exit_code, _, output_path = _run_mock(tmp_path, "PASS")
    assert exit_code == 0
    assert output_path.exists()
    with open(output_path, "r", encoding="utf-8") as f:
        result = json.load(f)
    assert result["status"] == "PASS"
    assert result["recommended_action"] == "none"
    assert result["findings"] == []
    assert result["decision_rationale"] == "Mock reviewer: PASS"


# ---------------------------------------------------------------------------
# M02: Mock FAIL mode
# ---------------------------------------------------------------------------
def test_m02_mock_fail_mode(tmp_path: Path) -> None:
    """M02: Mock FAIL mode produces valid FAIL result, exit 0."""
    exit_code, _, output_path = _run_mock(tmp_path, "FAIL")
    assert exit_code == 0
    assert output_path.exists()
    with open(output_path, "r", encoding="utf-8") as f:
        result = json.load(f)
    assert result["status"] == "FAIL"
    assert result["recommended_action"] == "repair"
    assert len(result["findings"]) >= 1
    assert result["findings"][0]["severity"] == "BLOCKER"


# ---------------------------------------------------------------------------
# M03: Mock ERROR mode
# ---------------------------------------------------------------------------
def test_m03_mock_error_mode(tmp_path: Path) -> None:
    """M03: Mock ERROR mode produces valid ERROR result (MAJOR finding, category infrastructure), exit 0."""
    exit_code, _, output_path = _run_mock(tmp_path, "ERROR")
    assert exit_code == 0
    assert output_path.exists()
    with open(output_path, "r", encoding="utf-8") as f:
        result = json.load(f)
    assert result["status"] == "ERROR"
    assert result["recommended_action"] == "human_review"
    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "MAJOR"
    assert result["findings"][0]["category"] == "infrastructure"


# ---------------------------------------------------------------------------
# M04: Mock determinism
# ---------------------------------------------------------------------------
def test_m04_mock_determinism(tmp_path: Path) -> None:
    """M04: Same request + mode produces same output."""
    import subprocess

    request_data = _valid_request()
    request_path = tmp_path / "request.json"
    with open(request_path, "w", encoding="utf-8") as f:
        json.dump(request_data, f)

    output1 = tmp_path / "output1.json"
    output2 = tmp_path / "output2.json"

    subprocess.run(
        [sys.executable, str(MOCK_REVIEWER), "--request", str(request_path), "--output", str(output1), "--mode", "PASS"],
        check=True,
    )
    subprocess.run(
        [sys.executable, str(MOCK_REVIEWER), "--request", str(request_path), "--output", str(output2), "--mode", "PASS"],
        check=True,
    )

    with open(output1, "r", encoding="utf-8") as f:
        content1 = f.read()
    with open(output2, "r", encoding="utf-8") as f:
        content2 = f.read()
    assert content1 == content2


# ---------------------------------------------------------------------------
# M05: Mock binds run_id from request
# ---------------------------------------------------------------------------
def test_m05_mock_binds_run_id(tmp_path: Path) -> None:
    """M05: Mock binds run_id from request."""
    exit_code, _, output_path = _run_mock(tmp_path, "PASS")
    assert exit_code == 0
    with open(output_path, "r", encoding="utf-8") as f:
        result = json.load(f)
    assert result["run_id"] == "test-run-123"


# ---------------------------------------------------------------------------
# M06: Mock uses request generated_at
# ---------------------------------------------------------------------------
def test_m06_mock_uses_request_generated_at(tmp_path: Path) -> None:
    """M06: Mock uses request generated_at as status_generated_at."""
    exit_code, _, output_path = _run_mock(tmp_path, "PASS")
    assert exit_code == 0
    with open(output_path, "r", encoding="utf-8") as f:
        result = json.load(f)
    assert result["status_generated_at"] == "2026-08-04T12:00:00Z"


# ---------------------------------------------------------------------------
# M07: Mock exit 2 on infrastructure failure
# ---------------------------------------------------------------------------
def test_m07_mock_exit_2_on_infrastructure_failure(tmp_path: Path) -> None:
    """M07: Cannot read request produces exit 2."""
    import subprocess

    output_path = tmp_path / "output.json"
    nonexistent_request = tmp_path / "nonexistent.json"

    proc = subprocess.run(
        [sys.executable, str(MOCK_REVIEWER), "--request", str(nonexistent_request), "--output", str(output_path), "--mode", "PASS"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2


# ---------------------------------------------------------------------------
# M08: Mock atomic write
# ---------------------------------------------------------------------------
def test_m08_mock_atomic_write(tmp_path: Path) -> None:
    """M08: Mock writes output atomically (temp file replaced via os.replace)."""
    exit_code, _, output_path = _run_mock(tmp_path, "PASS")
    assert exit_code == 0
    assert output_path.exists()
    # Verify no temp files remain
    parent = output_path.parent
    temp_files = list(parent.glob("*.tmp"))
    assert len(temp_files) == 0
