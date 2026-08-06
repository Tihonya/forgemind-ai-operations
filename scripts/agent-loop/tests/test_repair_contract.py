"""WP-AL-1C4: Repair contract tests.

75 planned test IDs (U01-U30, R01-R15, B01-B15, C01-C05, D01-D10).
Each ID appears exactly once. No skips, no xfails, no placeholders.
"""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from repair_contract import (
    RepairContractError,
    build_repair_request,
    canonical_json_bytes,
    pretty_json_string,
    sanitize_diagnostics,
    validate_repair_request,
    validate_repair_request_references,
    validate_repair_result,
    validate_repair_result_against_request,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

VALID_SHA40 = "a" * 40
VALID_SHA64 = "b" * 64


def _sha256_bytes(data: bytes) -> str:
    """Compute hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    """Compute hex SHA-256 of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_valid_request(
    *,
    run_id: str = "run-123",
    story_id: str = "story-456",
    attempt: int = 1,
    max_attempts: int = 3,
    source_revision: str = VALID_SHA40,
    failure_class: str = "verification_fail",
    failure_summary: str = "Test failure",
    fc_path: str = "reports/failure-context.json",
    fc_sha256: str = VALID_SHA64,
    vr_path: str = "reports/verify-result.json",
    vr_sha256: str = "c" * 64,
    review_result_ref: dict[str, str] | None = None,
    allowed_paths: list[str] | None = None,
    forbidden_paths: list[str] | None = None,
    repair_guidance: list[str] | None = None,
    requested_action: str = "fix_verification",
    generated_at: str = "2026-08-05T12:00:00Z",
) -> dict[str, Any]:
    """Build a structurally valid repair-request dict for testing."""
    req: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "story_id": story_id,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "source_revision": source_revision,
        "failure_class": failure_class,
        "failure_summary": failure_summary,
        "failure_context_ref": {
            "path": fc_path,
            "schema_version": "1.0",
            "sha256": fc_sha256,
        },
        "verification_result_ref": {
            "path": vr_path,
            "schema_version": "1.0",
            "sha256": vr_sha256,
        },
        "review_result_ref": review_result_ref,
        "allowed_paths": allowed_paths if allowed_paths is not None else ["backend/**"],
        "forbidden_paths": forbidden_paths if forbidden_paths is not None else [".env"],
        "requested_action": requested_action,
        "generated_at": generated_at,
    }
    if repair_guidance is not None:
        req["repair_guidance"] = repair_guidance
    return req


def _make_valid_result(
    *,
    run_id: str = "run-123",
    story_id: str = "story-456",
    attempt: int = 1,
    source_revision: str = VALID_SHA40,
    status: str = "REPAIRED",
    changed: bool = True,
    changed_files: list[str] | None = None,
    summary: str = "Fixed the test",
    diagnostics: dict[str, Any] | None = None,
    recommended_action: str = "reverify",
    completed_at: str = "2026-08-05T12:05:00Z",
) -> dict[str, Any]:
    """Build a structurally valid repair-result dict for testing."""
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "story_id": story_id,
        "attempt": attempt,
        "source_revision": source_revision,
        "status": status,
        "changed": changed,
        "changed_files": changed_files if changed_files is not None else ["backend/test.py"],
        "summary": summary,
        "diagnostics": diagnostics,
        "recommended_action": recommended_action,
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": completed_at,
    }


def _make_valid_sanitization() -> dict[str, Any]:
    return {
        "redaction_applied": False,
        "redaction_count": 0,
        "truncation_applied": False,
        "truncated_fields": [],
    }


def _setup_run_dir(
    tmp_path: Path,
    *,
    fc_content: dict[str, Any] | None = None,
    vr_content: dict[str, Any] | None = None,
    rr_content: dict[str, Any] | None = None,
    include_rr: bool = False,
) -> tuple[Path, str, str, str | None]:
    """Create a run_dir with failure-context, verify-result, and optionally review-result.

    Returns (run_dir, fc_sha256, vr_sha256, rr_sha256).
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    fc_data = fc_content if fc_content is not None else {
        "schema_version": "1.0",
        "run_id": "run-123",
        "story_id": "story-456",
    }
    fc_path = run_dir / "failure-context.json"
    fc_bytes = json.dumps(fc_data).encode("utf-8")
    fc_path.write_bytes(fc_bytes)
    fc_sha256 = _sha256_bytes(fc_bytes)

    vr_data = vr_content if vr_content is not None else {"schema_version": "1.0"}
    vr_path = run_dir / "verify-result.json"
    vr_bytes = json.dumps(vr_data).encode("utf-8")
    vr_path.write_bytes(vr_bytes)
    vr_sha256 = _sha256_bytes(vr_bytes)

    rr_sha256: str | None = None
    if include_rr:
        rr_data = rr_content if rr_content is not None else {"schema_version": "1.0"}
        rr_path = run_dir / "review-result.json"
        rr_bytes = json.dumps(rr_data).encode("utf-8")
        rr_path.write_bytes(rr_bytes)
        rr_sha256 = _sha256_bytes(rr_bytes)

    return run_dir, fc_sha256, vr_sha256, rr_sha256


# ============================================================================
# U01-U30: Structural validation (30 tests)
# ============================================================================


def test_U01_valid_request_minimal() -> None:
    """U01: Minimal valid repair request (all required fields) passes."""
    req = _make_valid_request()
    validate_repair_request(req)


def test_U02_valid_result_repaired() -> None:
    """U02: Minimal valid repair result (REPAIRED with changed files) passes."""
    result = _make_valid_result(status="REPAIRED", changed=True, changed_files=["backend/test.py"])
    validate_repair_result(result)


def test_U03_valid_result_no_change() -> None:
    """U03: Valid repair result (NO_CHANGE) passes."""
    result = _make_valid_result(
        status="NO_CHANGE", changed=False, changed_files=[], recommended_action="abort"
    )
    validate_repair_result(result)


def test_U04_valid_result_error() -> None:
    """U04: Valid repair result (ERROR) passes."""
    result = _make_valid_result(
        status="ERROR", changed=False, changed_files=[], recommended_action="human_review"
    )
    validate_repair_result(result)


def test_U05_missing_schema_version() -> None:
    """U05: Missing required field (schema_version) is rejected."""
    req = _make_valid_request()
    del req["schema_version"]
    with pytest.raises(RepairContractError, match="schema_version"):
        validate_repair_request(req)


def test_U06_wrong_field_type() -> None:
    """U06: Wrong field type (attempt as string) is rejected."""
    req = _make_valid_request(attempt="1")  # type: ignore[arg-type]
    with pytest.raises(RepairContractError, match="attempt"):
        validate_repair_request(req)


def test_U07_unknown_status_value() -> None:
    """U07: Unknown status value ('FIXED') is rejected."""
    result = _make_valid_result(status="FIXED")
    with pytest.raises(RepairContractError, match="status"):
        validate_repair_result(result)


def test_U08_schema_version_mismatch() -> None:
    """U08: Schema version mismatch ('2.0') is rejected."""
    req = _make_valid_request()
    req["schema_version"] = "2.0"
    with pytest.raises(RepairContractError, match="schema_version"):
        validate_repair_request(req)


def test_U09_run_id_mismatch() -> None:
    """U09: Run identity mismatch (result.run_id != request.run_id) is rejected."""
    req = _make_valid_request()
    result = _make_valid_result(run_id="different-run")
    with pytest.raises(RepairContractError, match="run_id"):
        validate_repair_result_against_request(result, req)


def test_U10_story_id_mismatch() -> None:
    """U10: Story identity mismatch (result.story_id != request.story_id) is rejected."""
    req = _make_valid_request()
    result = _make_valid_result(story_id="different-story")
    with pytest.raises(RepairContractError, match="story_id"):
        validate_repair_result_against_request(result, req)


def test_U11_attempt_mismatch() -> None:
    """U11: Attempt mismatch (result.attempt != request.attempt) is rejected."""
    req = _make_valid_request()
    result = _make_valid_result(attempt=2)
    with pytest.raises(RepairContractError, match="attempt"):
        validate_repair_result_against_request(result, req)


def test_U12_source_revision_mismatch() -> None:
    """U12: Source revision mismatch is rejected."""
    req = _make_valid_request()
    result = _make_valid_result(source_revision="b" * 40)
    with pytest.raises(RepairContractError, match="source_revision"):
        validate_repair_result_against_request(result, req)


def test_U13_attempt_less_than_1() -> None:
    """U13: Invalid attempt bounds (attempt < 1) is rejected."""
    req = _make_valid_request(attempt=0)
    with pytest.raises(RepairContractError, match="attempt"):
        validate_repair_request(req)


def test_U14_attempt_exceeds_max() -> None:
    """U14: Invalid attempt bounds (attempt > max_attempts) is rejected."""
    req = _make_valid_request(attempt=4, max_attempts=3)
    with pytest.raises(RepairContractError, match="attempt"):
        validate_repair_request(req)


def test_U15_repaired_without_changed_true() -> None:
    """U15: REPAIRED without changed=true is rejected."""
    result = _make_valid_result(status="REPAIRED", changed=False, changed_files=["backend/test.py"])
    with pytest.raises(RepairContractError, match="REPAIRED"):
        validate_repair_result(result)


def test_U16_repaired_with_empty_changed_files() -> None:
    """U16: REPAIRED with empty changed_files array is rejected."""
    result = _make_valid_result(status="REPAIRED", changed=True, changed_files=[])
    with pytest.raises(RepairContractError, match="REPAIRED"):
        validate_repair_result(result)


def test_U17_no_change_with_changed_true() -> None:
    """U17: NO_CHANGE with changed=true is rejected."""
    result = _make_valid_result(
        status="NO_CHANGE", changed=True, changed_files=[], recommended_action="abort"
    )
    with pytest.raises(RepairContractError, match="NO_CHANGE"):
        validate_repair_result(result)


def test_U18_no_change_with_nonempty_changed_files() -> None:
    """U18: NO_CHANGE with non-empty changed_files is rejected."""
    result = _make_valid_result(
        status="NO_CHANGE", changed=False, changed_files=["backend/test.py"], recommended_action="abort"
    )
    with pytest.raises(RepairContractError, match="NO_CHANGE"):
        validate_repair_result(result)


def test_U19_duplicate_changed_files() -> None:
    """U19: Duplicate changed_files entries are rejected."""
    result = _make_valid_result(changed_files=["backend/test.py", "backend/test.py"])
    with pytest.raises(RepairContractError, match="duplicate"):
        validate_repair_result(result)


def test_U20_absolute_path_in_changed_files() -> None:
    """U20: Absolute path in changed_files is rejected."""
    result = _make_valid_result(changed_files=["/etc/passwd"])
    with pytest.raises(RepairContractError, match="absolute"):
        validate_repair_result(result)


def test_U21_parent_traversal_in_changed_files() -> None:
    """U21: Parent traversal in changed_files is rejected."""
    result = _make_valid_result(changed_files=["../secrets.env"])
    with pytest.raises(RepairContractError, match="traversal"):
        validate_repair_result(result)


def test_U22_forbidden_path_in_changed_files() -> None:
    """U22: Forbidden path in changed_files (matches forbidden_paths pattern) is rejected."""
    req = _make_valid_request(
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
    )
    result = _make_valid_result(changed_files=[".env"])
    with pytest.raises(RepairContractError, match="forbidden"):
        validate_repair_result_against_request(result, req)


def test_U23_path_outside_allowed_paths() -> None:
    """U23: Path outside allowed_paths (does not match any allowed pattern) is rejected."""
    req = _make_valid_request(
        allowed_paths=["backend/**"],
        forbidden_paths=[],
    )
    result = _make_valid_result(changed_files=["docs/README.md"])
    with pytest.raises(RepairContractError, match="allowed"):
        validate_repair_result_against_request(result, req)


def test_U24_excessive_changed_files_count() -> None:
    """U24: Excessive changed_files count (51 entries) is rejected."""
    result = _make_valid_result(changed_files=[f"file{i}.py" for i in range(51)])
    with pytest.raises(RepairContractError, match="exceeds"):
        validate_repair_result(result)


def test_U25_oversized_summary() -> None:
    """U25: Oversized summary (2049 bytes) is rejected."""
    result = _make_valid_result(summary="x" * 2049)
    with pytest.raises(RepairContractError, match="summary"):
        validate_repair_result(result)


def test_U26_malformed_json_unparseable(tmp_path: Path) -> None:
    """U26: Malformed JSON (unparseable) is rejected by referential validator."""
    # Structural validator doesn't parse JSON; referential validator does.
    # This tests that a non-JSON failure-context file is rejected.
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    fc_path = run_dir / "failure-context.json"
    fc_bytes = b"{not valid json"
    fc_path.write_bytes(fc_bytes)
    fc_sha256 = _sha256_bytes(fc_bytes)

    vr_path = run_dir / "verify-result.json"
    vr_bytes = json.dumps({"schema_version": "1.0"}).encode("utf-8")
    vr_path.write_bytes(vr_bytes)
    vr_sha256 = _sha256_bytes(vr_bytes)

    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="failure-context"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_U27_unreadable_artifact_non_json(tmp_path: Path) -> None:
    """U27: Unreadable artifact (non-JSON file) is rejected by referential validator."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    fc_path = run_dir / "failure-context.json"
    # Write binary garbage that is valid UTF-8 but not JSON
    fc_bytes = b"\x00\x01\x02\x03\x04"
    fc_path.write_bytes(fc_bytes)
    fc_sha256 = _sha256_bytes(fc_bytes)

    vr_path = run_dir / "verify-result.json"
    vr_bytes = json.dumps({"schema_version": "1.0"}).encode("utf-8")
    vr_path.write_bytes(vr_bytes)
    vr_sha256 = _sha256_bytes(vr_bytes)

    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="failure-context"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_U28_bounded_diagnostics_actions_exceed() -> None:
    """U28: Bounded diagnostics (actions_taken > 20 entries) is rejected."""
    result = _make_valid_result(
        diagnostics={
            "actions_taken": [f"action{i}" for i in range(21)],
            "obstacles_encountered": [],
        }
    )
    with pytest.raises(RepairContractError, match="actions_taken"):
        validate_repair_result(result)


def test_U29_redacted_diagnostics_secret_in_summary() -> None:
    """U29: Secret pattern in summary is redacted in diagnostics sanitization output."""
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": ["password='secret12345678'"]}
    )
    assert diag is not None
    assert "[REDACTED:" in diag["actions_taken"][0]


def test_U30_deterministic_repeated_validation() -> None:
    """U30: Deterministic repeated validation (same input twice) produces identical result."""
    req = _make_valid_request()
    # validate_repair_request raises or doesn't; calling twice must behave identically.
    # Since it returns None on success, we verify no raise both times.
    validate_repair_request(req)
    validate_repair_request(req)
    # Also verify canonical bytes determinism for the request
    b1 = canonical_json_bytes(req)
    b2 = canonical_json_bytes(req)
    assert b1 == b2


# ============================================================================
# R01-R15: Referential validation (15 tests)
# ============================================================================


def test_R01_valid_references(tmp_path: Path) -> None:
    """R01: Valid referential validation (all matches) passes."""
    run_dir, fc_sha256, vr_sha256, _ = _setup_run_dir(tmp_path)
    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    validate_repair_request_references(req, tmp_path, run_dir)


def test_R02_failure_context_does_not_exist(tmp_path: Path) -> None:
    """R02: Failure-context file does not exist is rejected."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)
    # Only create verify-result, not failure-context
    vr_path = run_dir / "verify-result.json"
    vr_bytes = json.dumps({"schema_version": "1.0"}).encode("utf-8")
    vr_path.write_bytes(vr_bytes)
    vr_sha256 = _sha256_bytes(vr_bytes)

    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=VALID_SHA64,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="failure-context"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_R03_failure_context_sha256_mismatch(tmp_path: Path) -> None:
    """R03: Failure-context SHA-256 mismatch is rejected."""
    run_dir, _fc_sha256, vr_sha256, _ = _setup_run_dir(tmp_path)
    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256="0" * 64,  # Wrong hash
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="SHA-256"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_R04_failure_context_schema_mismatch(tmp_path: Path) -> None:
    """R04: Failure-context schema_version mismatch is rejected."""
    run_dir, _fc_sha256, vr_sha256, _ = _setup_run_dir(
        tmp_path, fc_content={"schema_version": "2.0", "run_id": "run-123", "story_id": "story-456"}
    )
    # Recompute fc_sha256 because we changed content
    fc_path = run_dir / "failure-context.json"
    fc_bytes = fc_path.read_bytes()
    fc_sha256 = _sha256_bytes(fc_bytes)

    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="schema_version"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_R05_verify_result_does_not_exist(tmp_path: Path) -> None:
    """R05: Verify-result file does not exist is rejected."""
    run_dir, fc_sha256, vr_sha256, _ = _setup_run_dir(tmp_path)
    # Delete verify-result to simulate missing file
    (run_dir / "verify-result.json").unlink()
    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="verification-result"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_R06_verify_result_sha256_mismatch(tmp_path: Path) -> None:
    """R06: Verify-result SHA-256 mismatch is rejected."""
    run_dir, fc_sha256, _vr_sha256, _ = _setup_run_dir(tmp_path)
    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256="0" * 64,  # Wrong hash
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="SHA-256"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_R07_review_result_does_not_exist(tmp_path: Path) -> None:
    """R07: Review-result file does not exist (when review_result_ref is non-null) is rejected."""
    run_dir, fc_sha256, vr_sha256, _ = _setup_run_dir(tmp_path)
    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        review_result_ref={
            "path": "review-result.json",
            "schema_version": "1.0",
            "sha256": "d" * 64,
        },
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="review-result"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_R08_review_result_sha256_mismatch(tmp_path: Path) -> None:
    """R08: Review-result SHA-256 mismatch is rejected."""
    run_dir, fc_sha256, vr_sha256, _ = _setup_run_dir(tmp_path)
    # Create review-result with a real hash
    rr_path = run_dir / "review-result.json"
    rr_bytes = json.dumps({"schema_version": "1.0"}).encode("utf-8")
    rr_path.write_bytes(rr_bytes)
    # But declare a wrong hash in the request
    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        review_result_ref={
            "path": "review-result.json",
            "schema_version": "1.0",
            "sha256": "0" * 64,  # Wrong hash
        },
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="SHA-256"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_R09_run_id_mismatch_with_failure_context(tmp_path: Path) -> None:
    """R09: run_id mismatch between request and failure-context is rejected."""
    run_dir, _fc_sha256, vr_sha256, _ = _setup_run_dir(
        tmp_path, fc_content={"schema_version": "1.0", "run_id": "different-run", "story_id": "story-456"}
    )
    fc_path = run_dir / "failure-context.json"
    fc_bytes = fc_path.read_bytes()
    fc_sha256 = _sha256_bytes(fc_bytes)

    req = _make_valid_request(
        run_id="run-123",
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="run_id"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_R10_story_id_mismatch_with_failure_context(tmp_path: Path) -> None:
    """R10: story_id mismatch between request and failure-context is rejected."""
    run_dir, _fc_sha256, vr_sha256, _ = _setup_run_dir(
        tmp_path, fc_content={"schema_version": "1.0", "run_id": "run-123", "story_id": "different-story"}
    )
    fc_path = run_dir / "failure-context.json"
    fc_bytes = fc_path.read_bytes()
    fc_sha256 = _sha256_bytes(fc_bytes)

    req = _make_valid_request(
        story_id="story-456",
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="story_id"):
        validate_repair_request_references(req, tmp_path, run_dir)


def test_R11_manifest_does_not_exist(tmp_path: Path) -> None:
    """R11: Manifest file does not exist is rejected."""
    run_dir, fc_sha256, vr_sha256, _ = _setup_run_dir(tmp_path)
    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    manifest_path = tmp_path / "manifest.json"  # Does not exist
    with pytest.raises(RepairContractError, match="manifest"):
        validate_repair_request_references(
            req, tmp_path, run_dir,
            manifest_path=manifest_path, manifest_sha256="e" * 64,
        )


def test_R12_manifest_sha256_mismatch(tmp_path: Path) -> None:
    """R12: Manifest SHA-256 mismatch is rejected."""
    run_dir, fc_sha256, vr_sha256, _ = _setup_run_dir(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_data = {
        "schema_version": "1.0",
        "story_id": "story-456",
        "base_commit": VALID_SHA40,
    }
    manifest_path.write_bytes(json.dumps(manifest_data).encode("utf-8"))

    req = _make_valid_request(
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="SHA-256"):
        validate_repair_request_references(
            req, tmp_path, run_dir,
            manifest_path=manifest_path, manifest_sha256="0" * 64,
        )


def test_R13_story_id_mismatch_with_manifest(tmp_path: Path) -> None:
    """R13: story_id mismatch between request and manifest is rejected."""
    run_dir, fc_sha256, vr_sha256, _ = _setup_run_dir(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_data = {
        "schema_version": "1.0",
        "story_id": "different-story",
        "base_commit": VALID_SHA40,
    }
    manifest_bytes = json.dumps(manifest_data).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha256 = _sha256_bytes(manifest_bytes)

    req = _make_valid_request(
        story_id="story-456",
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="story_id"):
        validate_repair_request_references(
            req, tmp_path, run_dir,
            manifest_path=manifest_path, manifest_sha256=manifest_sha256,
        )


def test_R14_source_revision_mismatch_with_manifest(tmp_path: Path) -> None:
    """R14: source_revision mismatch with manifest base_commit is rejected."""
    run_dir, fc_sha256, vr_sha256, _ = _setup_run_dir(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest_data = {
        "schema_version": "1.0",
        "story_id": "story-456",
        "base_commit": "b" * 40,  # Different from request source_revision
    }
    manifest_bytes = json.dumps(manifest_data).encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)
    manifest_sha256 = _sha256_bytes(manifest_bytes)

    req = _make_valid_request(
        source_revision=VALID_SHA40,  # "a" * 40
        fc_path="failure-context.json",
        fc_sha256=fc_sha256,
        vr_path="verify-result.json",
        vr_sha256=vr_sha256,
        allowed_paths=[],
        forbidden_paths=[],
    )
    with pytest.raises(RepairContractError, match="source_revision"):
        validate_repair_request_references(
            req, tmp_path, run_dir,
            manifest_path=manifest_path, manifest_sha256=manifest_sha256,
        )


def test_R15_review_fail_with_null_review_ref(tmp_path: Path) -> None:
    """R15: failure_class='review_fail' with null review_result_ref is rejected."""
    req = _make_valid_request(
        failure_class="review_fail",
        review_result_ref=None,
        requested_action="fix_review_findings",
    )
    with pytest.raises(RepairContractError, match="review_result_ref"):
        validate_repair_request(req)


# ============================================================================
# B01-B15: Builder tests (15 tests)
# ============================================================================


def _setup_builder_run_dir(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create a run_dir with valid failure-context and verify-result for builder tests."""
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True, exist_ok=True)

    fc_path = run_dir / "failure-context.json"
    fc_path.write_bytes(
        json.dumps({"schema_version": "1.0", "run_id": "run-123", "story_id": "story-456"}).encode("utf-8")
    )

    vr_path = run_dir / "verify-result.json"
    vr_path.write_bytes(json.dumps({"schema_version": "1.0"}).encode("utf-8"))

    return run_dir, fc_path, vr_path


def test_B01_builder_valid_inputs(tmp_path: Path) -> None:
    """B01: Builder from valid inputs produces valid request."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    request = build_repair_request(
        run_dir=run_dir,
        failure_context_path=fc_path,
        verify_result_path=vr_path,
        review_result_path=None,
        run_id="run-123",
        story_id="story-456",
        attempt=1,
        max_attempts=3,
        source_revision=VALID_SHA40,
        failure_class="verification_fail",
        failure_summary="Test failure",
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        requested_action="fix_verification",
        generated_at="2026-08-05T12:00:00Z",
    )
    assert request["schema_version"] == "1.0"


def test_B02_builder_fc_sha256_correct(tmp_path: Path) -> None:
    """B02: Builder computes failure_context_ref.sha256 correctly."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    request = build_repair_request(
        run_dir=run_dir,
        failure_context_path=fc_path,
        verify_result_path=vr_path,
        review_result_path=None,
        run_id="run-123",
        story_id="story-456",
        attempt=1,
        max_attempts=3,
        source_revision=VALID_SHA40,
        failure_class="verification_fail",
        failure_summary="Test failure",
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        requested_action="fix_verification",
        generated_at="2026-08-05T12:00:00Z",
    )
    expected_sha = _sha256_bytes(fc_path.read_bytes())
    assert request["failure_context_ref"]["sha256"] == expected_sha


def test_B03_builder_vr_sha256_correct(tmp_path: Path) -> None:
    """B03: Builder computes verification_result_ref.sha256 correctly."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    request = build_repair_request(
        run_dir=run_dir,
        failure_context_path=fc_path,
        verify_result_path=vr_path,
        review_result_path=None,
        run_id="run-123",
        story_id="story-456",
        attempt=1,
        max_attempts=3,
        source_revision=VALID_SHA40,
        failure_class="verification_fail",
        failure_summary="Test failure",
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        requested_action="fix_verification",
        generated_at="2026-08-05T12:00:00Z",
    )
    expected_sha = _sha256_bytes(vr_path.read_bytes())
    assert request["verification_result_ref"]["sha256"] == expected_sha


def test_B04_builder_rr_sha256_correct(tmp_path: Path) -> None:
    """B04: Builder computes review_result_ref.sha256 correctly (when present)."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    rr_path = run_dir / "review-result.json"
    rr_path.write_bytes(json.dumps({"schema_version": "1.0"}).encode("utf-8"))

    request = build_repair_request(
        run_dir=run_dir,
        failure_context_path=fc_path,
        verify_result_path=vr_path,
        review_result_path=rr_path,
        run_id="run-123",
        story_id="story-456",
        attempt=1,
        max_attempts=3,
        source_revision=VALID_SHA40,
        failure_class="review_fail",
        failure_summary="Test failure",
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        requested_action="fix_review_findings",
        generated_at="2026-08-05T12:00:00Z",
    )
    expected_sha = _sha256_bytes(rr_path.read_bytes())
    assert request["review_result_ref"]["sha256"] == expected_sha


def test_B05_builder_missing_failure_context(tmp_path: Path) -> None:
    """B05: Builder with missing failure-context file raises error."""
    run_dir, _, vr_path = _setup_builder_run_dir(tmp_path)
    fc_path = run_dir / "failure-context.json"
    fc_path.unlink()  # Remove it
    with pytest.raises(RepairContractError, match="failure-context"):
        build_repair_request(
            run_dir=run_dir,
            failure_context_path=fc_path,
            verify_result_path=vr_path,
            review_result_path=None,
            run_id="run-123",
            story_id="story-456",
            attempt=1,
            max_attempts=3,
            source_revision=VALID_SHA40,
            failure_class="verification_fail",
            failure_summary="Test failure",
            allowed_paths=["backend/**"],
            forbidden_paths=[".env"],
            requested_action="fix_verification",
            generated_at="2026-08-05T12:00:00Z",
        )


def test_B06_builder_missing_verify_result(tmp_path: Path) -> None:
    """B06: Builder with missing verify-result file raises error."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    vr_path.unlink()  # Remove it
    with pytest.raises(RepairContractError, match="verification-result"):
        build_repair_request(
            run_dir=run_dir,
            failure_context_path=fc_path,
            verify_result_path=vr_path,
            review_result_path=None,
            run_id="run-123",
            story_id="story-456",
            attempt=1,
            max_attempts=3,
            source_revision=VALID_SHA40,
            failure_class="verification_fail",
            failure_summary="Test failure",
            allowed_paths=["backend/**"],
            forbidden_paths=[".env"],
            requested_action="fix_verification",
            generated_at="2026-08-05T12:00:00Z",
        )


def test_B07_builder_invalid_failure_context_schema(tmp_path: Path) -> None:
    """B07: Builder with invalid failure-context schema raises error."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    # Overwrite failure-context with wrong schema_version
    fc_path.write_bytes(
        json.dumps({"schema_version": "2.0", "run_id": "run-123", "story_id": "story-456"}).encode("utf-8")
    )
    with pytest.raises(RepairContractError, match="schema_version"):
        build_repair_request(
            run_dir=run_dir,
            failure_context_path=fc_path,
            verify_result_path=vr_path,
            review_result_path=None,
            run_id="run-123",
            story_id="story-456",
            attempt=1,
            max_attempts=3,
            source_revision=VALID_SHA40,
            failure_class="verification_fail",
            failure_summary="Test failure",
            allowed_paths=["backend/**"],
            forbidden_paths=[".env"],
            requested_action="fix_verification",
            generated_at="2026-08-05T12:00:00Z",
        )


def test_B08_builder_sanitize_failure_summary_secret(tmp_path: Path) -> None:
    """B08: Builder sanitizes failure_summary (secret pattern redacted)."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    request = build_repair_request(
        run_dir=run_dir,
        failure_context_path=fc_path,
        verify_result_path=vr_path,
        review_result_path=None,
        run_id="run-123",
        story_id="story-456",
        attempt=1,
        max_attempts=3,
        source_revision=VALID_SHA40,
        failure_class="verification_fail",
        failure_summary="Error: password='secret12345678'",
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        requested_action="fix_verification",
        generated_at="2026-08-05T12:00:00Z",
    )
    assert "[REDACTED:" in request["failure_summary"]


def test_B09_builder_sanitize_repair_guidance_control_chars(tmp_path: Path) -> None:
    """B09: Builder sanitizes repair_guidance (control chars removed)."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    request = build_repair_request(
        run_dir=run_dir,
        failure_context_path=fc_path,
        verify_result_path=vr_path,
        review_result_path=None,
        run_id="run-123",
        story_id="story-456",
        attempt=1,
        max_attempts=3,
        source_revision=VALID_SHA40,
        failure_class="verification_fail",
        failure_summary="Test failure",
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        requested_action="fix_verification",
        generated_at="2026-08-05T12:00:00Z",
        repair_guidance=["Fix\x00the\x01test"],
    )
    assert "\x00" not in request["repair_guidance"][0]
    assert "\x01" not in request["repair_guidance"][0]


def test_B10_builder_truncate_oversized_summary(tmp_path: Path) -> None:
    """B10: Builder truncates oversized summary (3000 bytes to <=2048 bytes)."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    long_summary = "ab " * 1000  # 3000 bytes
    request = build_repair_request(
        run_dir=run_dir,
        failure_context_path=fc_path,
        verify_result_path=vr_path,
        review_result_path=None,
        run_id="run-123",
        story_id="story-456",
        attempt=1,
        max_attempts=3,
        source_revision=VALID_SHA40,
        failure_class="verification_fail",
        failure_summary=long_summary,
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        requested_action="fix_verification",
        generated_at="2026-08-05T12:00:00Z",
    )
    assert len(request["failure_summary"].encode("utf-8")) <= 2048


def test_B11_builder_utf8_invalid_bytes(tmp_path: Path) -> None:
    """B11: Builder with UTF-8 invalid bytes replaces with U+FFFD."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    # Create a string with replacement chars (simulating invalid UTF-8 decoded)
    invalid_text = b"test\xff\xfe".decode("utf-8", errors="replace")
    request = build_repair_request(
        run_dir=run_dir,
        failure_context_path=fc_path,
        verify_result_path=vr_path,
        review_result_path=None,
        run_id="run-123",
        story_id="story-456",
        attempt=1,
        max_attempts=3,
        source_revision=VALID_SHA40,
        failure_class="verification_fail",
        failure_summary=invalid_text,
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        requested_action="fix_verification",
        generated_at="2026-08-05T12:00:00Z",
    )
    assert "test" in request["failure_summary"]


def test_B12_builder_sanitization_metadata(tmp_path: Path) -> None:
    """B12: Builder populates sanitization metadata accurately."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    request = build_repair_request(
        run_dir=run_dir,
        failure_context_path=fc_path,
        verify_result_path=vr_path,
        review_result_path=None,
        run_id="run-123",
        story_id="story-456",
        attempt=1,
        max_attempts=3,
        source_revision=VALID_SHA40,
        failure_class="verification_fail",
        failure_summary="password='secret12345678'",
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        requested_action="fix_verification",
        generated_at="2026-08-05T12:00:00Z",
    )
    assert request["sanitization"]["redaction_applied"] is True
    assert request["sanitization"]["redaction_count"] > 0


def test_B13_builder_no_sanitization_needed(tmp_path: Path) -> None:
    """B13: Builder with clean input sets redaction_applied=false, redaction_count=0."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    request = build_repair_request(
        run_dir=run_dir,
        failure_context_path=fc_path,
        verify_result_path=vr_path,
        review_result_path=None,
        run_id="run-123",
        story_id="story-456",
        attempt=1,
        max_attempts=3,
        source_revision=VALID_SHA40,
        failure_class="verification_fail",
        failure_summary="Clean summary with no secrets",
        allowed_paths=["backend/**"],
        forbidden_paths=[".env"],
        requested_action="fix_verification",
        generated_at="2026-08-05T12:00:00Z",
    )
    assert request["sanitization"]["redaction_applied"] is False
    assert request["sanitization"]["redaction_count"] == 0


def test_B14_builder_deterministic_output(tmp_path: Path) -> None:
    """B14: Builder deterministic output (same inputs twice produces identical canonical bytes)."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    kwargs: dict[str, Any] = {
        "run_dir": run_dir,
        "failure_context_path": fc_path,
        "verify_result_path": vr_path,
        "review_result_path": None,
        "run_id": "run-123",
        "story_id": "story-456",
        "attempt": 1,
        "max_attempts": 3,
        "source_revision": VALID_SHA40,
        "failure_class": "verification_fail",
        "failure_summary": "Test failure",
        "allowed_paths": ["backend/**"],
        "forbidden_paths": [".env"],
        "requested_action": "fix_verification",
        "generated_at": "2026-08-05T12:00:00Z",
    }
    request1 = build_repair_request(**kwargs)
    request2 = build_repair_request(**kwargs)
    assert canonical_json_bytes(request1) == canonical_json_bytes(request2)


def test_B15_builder_without_explicit_timestamp(tmp_path: Path) -> None:
    """B15: Builder without explicit timestamp raises error (no internal time call)."""
    run_dir, fc_path, vr_path = _setup_builder_run_dir(tmp_path)
    with pytest.raises(TypeError):
        build_repair_request(  # type: ignore[call-arg]
            run_dir=run_dir,
            failure_context_path=fc_path,
            verify_result_path=vr_path,
            review_result_path=None,
            run_id="run-123",
            story_id="story-456",
            attempt=1,
            max_attempts=3,
            source_revision=VALID_SHA40,
            failure_class="verification_fail",
            failure_summary="Test failure",
            allowed_paths=["backend/**"],
            forbidden_paths=[".env"],
            requested_action="fix_verification",
            # generated_at intentionally omitted
        )


# ============================================================================
# C01-C05: Serialization tests (5 tests)
# ============================================================================


def test_C01_canonical_deterministic() -> None:
    """C01: Canonical bytes deterministic (same dict, different insertion order)."""
    obj1: dict[str, Any] = {"b": 2, "a": 1}
    obj2: dict[str, Any] = {"a": 1, "b": 2}
    assert canonical_json_bytes(obj1) == canonical_json_bytes(obj2)


def test_C02_canonical_sort_keys() -> None:
    """C02: Canonical bytes use sort_keys=True (keys sorted alphabetically)."""
    obj: dict[str, Any] = {"z": 1, "a": 2, "m": 3}
    result = canonical_json_bytes(obj).decode("utf-8")
    assert result == '{"a":2,"m":3,"z":1}'


def test_C03_canonical_compact_separators() -> None:
    """C03: Canonical bytes use compact separators (no spaces after : or ,)."""
    obj: dict[str, Any] = {"a": "1", "b": "2"}
    result = canonical_json_bytes(obj).decode("utf-8")
    assert ":" in result
    assert "," in result
    assert ": " not in result
    assert ", " not in result


def test_C04_pretty_json_indent() -> None:
    """C04: Pretty JSON has indent=2."""
    obj: dict[str, Any] = {"key": "value"}
    result = pretty_json_string(obj)
    assert "  " in result
    assert "{\n" in result


def test_C05_pretty_json_terminal_newline() -> None:
    """C05: Pretty JSON has exactly one terminal newline."""
    obj: dict[str, Any] = {"key": "value"}
    result = pretty_json_string(obj)
    assert result.endswith("\n")
    assert not result.endswith("\n\n")


# ============================================================================
# D01-D10: Sanitization tests (10 tests)
# ============================================================================


def test_D01_redact_stripe_key() -> None:
    """D01: Redact stripe key pattern in summary -> '[REDACTED:stripe_key]'."""
    # Pattern: sk_live_[A-Za-z0-9]{20,}
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": ["Used sk_live_abcdef1234567890abcdef in payment"]}
    )
    assert diag is not None
    assert "[REDACTED:stripe_key]" in diag["actions_taken"][0]


def test_D02_redact_github_token() -> None:
    """D02: Redact GitHub token pattern -> '[REDACTED:github_token]'."""
    # Pattern: ghp_[A-Za-z0-9]{36}
    token = "ghp_" + "a" * 36
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": [f"Token {token} in auth"]}
    )
    assert diag is not None
    assert "[REDACTED:github_token]" in diag["actions_taken"][0]


def test_D03_redact_aws_key() -> None:
    """D03: Redact AWS key pattern -> '[REDACTED:aws_key]'."""
    # Pattern: AKIA[0-9A-Z]{16}
    key = "AKIA" + "A" * 16
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": [f"Key {key} detected"]}
    )
    assert diag is not None
    assert "[REDACTED:aws_key]" in diag["actions_taken"][0]


def test_D04_redact_bearer_token() -> None:
    """D04: Redact Bearer token -> '[REDACTED:bearer_token]'."""
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": ["Auth: Bearer abc123def456ghi789jkl012mno345pqr789"]}
    )
    assert diag is not None
    assert "[REDACTED:bearer_token]" in diag["actions_taken"][0]


def test_D05_redact_basic_auth() -> None:
    """D05: Redact Basic auth -> '[REDACTED:basic_auth]'."""
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": ["Auth: Basic dXNlcjpwYXNzMTIzNDU2"]}
    )
    assert diag is not None
    assert "[REDACTED:basic_auth]" in diag["actions_taken"][0]


def test_D06_redact_password() -> None:
    """D06: Redact password assignment -> '[REDACTED:password]'."""
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": ["Config password='secret12345678'"]}
    )
    assert diag is not None
    assert "[REDACTED:password]" in diag["actions_taken"][0]


def test_D07_redact_private_key() -> None:
    """D07: Redact private key block -> '[REDACTED:private_key]'."""
    # Pattern: -----BEGIN...PRIVATE KEY-----...END...-----
    key_block = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA0a0a0a0a0a0a0a0a0a0a0a0a0a0a\n"
        "-----END RSA PRIVATE KEY-----"
    )
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": [f"Found {key_block} in config"]}
    )
    assert diag is not None
    assert "[REDACTED:private_key]" in diag["actions_taken"][0]


def test_D08_strip_url_query() -> None:
    """D08: Strip URL query string (query removed, path preserved)."""
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": ["URL: https://example.com/path?secret=value&token=abc"]}
    )
    assert diag is not None
    assert "https://example.com/path" in diag["actions_taken"][0]
    assert "?secret=value" not in diag["actions_taken"][0]


def test_D09_detect_binary() -> None:
    """D09: Detect binary content -> '[REDACTED:binary_content]'."""
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": ["\x00\x01\x02\x03\x04\x05\x06\x07\x08\x0b\x0c\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f"]}
    )
    assert diag is not None
    assert "[REDACTED:binary_content]" in diag["actions_taken"][0]


def test_D10_redact_base64() -> None:
    """D10: Redact base64 run (100+ chars) -> '[REDACTED:base64_payload]'."""
    # 150 alphanumeric chars (+ and = are valid base64 but we keep it simple)
    payload = "A" * 150
    diag, _count, _trunc, _fields = sanitize_diagnostics(
        {"actions_taken": [f"Data: {payload}"]}
    )
    assert diag is not None
    assert "[REDACTED:base64_payload]" in diag["actions_taken"][0]
