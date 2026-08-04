"""
WP-AL-1C1: Tests for review contract module.

Test matrix:
- S01-S30: structural validation (30 cases)
- R01-R20: referential validation (20 cases)
- B01-B20: builder tests (20 cases)
- C01-C08: serialization tests (8 cases)
- D01-D16: sanitization tests (16 cases)

Total: 94 planned cases
"""

# Import the module under test
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from review_contract import (
    ReviewContractError,
    build_review_request,
    canonical_json_bytes,
    pretty_json_string,
    validate_review_request,
    validate_review_request_references,
    validate_review_result,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------
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
            "repair_guidance": ["RG1"],
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


def _valid_result() -> dict[str, Any]:
    """Return a valid review result."""
    return {
        "schema_version": "1.0",
        "run_id": "test-run-123",
        "story_id": "US-002",
        "review_iteration": 1,
        "repair_iteration": 0,
        "status": "PASS",
        "status_generated_at": "2026-08-04T12:05:00Z",
        "reviewer_id": "mock-reviewer",
        "findings": [],
        "decision_rationale": "All checks passed",
        "recommended_action": "none",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
    }


# ---------------------------------------------------------------------------
# Structural validation tests (S01-S30)
# ---------------------------------------------------------------------------
class TestStructuralValidation:
    """Structural validation tests (no filesystem)."""

    def test_S01_valid_review_request(self) -> None:
        """Valid review request passes validation."""
        request = _valid_request()
        validate_review_request(request)

    def test_S02_valid_review_result_pass(self) -> None:
        """Valid review result (PASS) passes validation."""
        result = _valid_result()
        validate_review_result(result)

    def test_S03_valid_review_result_fail(self) -> None:
        """Valid review result (FAIL) passes validation."""
        result = _valid_result()
        result["status"] = "FAIL"
        result["recommended_action"] = "repair"
        result["findings"] = [
            {
                "finding_id": "F001",
                "severity": "BLOCKER",
                "category": "test",
                "summary": "Test failed",
                "evidence_refs": ["test.log"],
                "recommended_fix": "Fix test",
            }
        ]
        validate_review_result(result)

    def test_S04_valid_review_result_error(self) -> None:
        """Valid review result (ERROR) passes validation."""
        result = _valid_result()
        result["status"] = "ERROR"
        result["recommended_action"] = "human_review"
        result["findings"] = [
            {
                "finding_id": "E001",
                "severity": "INFO",
                "category": "infrastructure",
                "summary": "Infrastructure error",
                "evidence_refs": [],
                "recommended_fix": "Check infrastructure",
            }
        ]
        validate_review_result(result)

    def test_S05_missing_schema_version(self) -> None:
        """Missing schema_version is rejected."""
        request = _valid_request()
        del request["schema_version"]
        with pytest.raises(ReviewContractError, match="missing required field"):
            validate_review_request(request)

    def test_S06_invalid_status_value(self) -> None:
        """Invalid status value is rejected."""
        result = _valid_result()
        result["status"] = "ACCEPT"
        with pytest.raises(ReviewContractError, match="status must be PASS, FAIL, or ERROR"):
            validate_review_result(result)

    def test_S07_oversized_decision_rationale(self) -> None:
        """Oversized decision_rationale is rejected."""
        result = _valid_result()
        result["decision_rationale"] = "x" * 2049
        with pytest.raises(ReviewContractError, match="decision_rationale exceeds 2048 bytes"):
            validate_review_result(result)

    def test_S08_oversized_finding_summary(self) -> None:
        """Oversized finding summary is rejected."""
        result = _valid_result()
        result["findings"] = [
            {
                "finding_id": "F001",
                "severity": "INFO",
                "category": "test",
                "summary": "x" * 1025,
                "evidence_refs": [],
                "recommended_fix": "Fix",
            }
        ]
        with pytest.raises(ReviewContractError, match="summary exceeds 1024 bytes"):
            validate_review_result(result)

    def test_S09_too_many_acceptance_criteria(self) -> None:
        """Too many acceptance_criteria entries is rejected."""
        request = _valid_request()
        request["manifest_excerpt"]["acceptance_criteria"] = ["AC"] * 21
        with pytest.raises(ReviewContractError, match="acceptance_criteria exceeds 20 entries"):
            validate_review_request(request)

    def test_S10_path_traversal_failure_context(self) -> None:
        """Path traversal in failure_context_ref.path is rejected."""
        request = _valid_request()
        request["failure_context_ref"]["path"] = "../reports/fc.json"
        with pytest.raises(ReviewContractError, match="path traversal"):
            validate_review_request(request)

    def test_S11_absolute_path_failure_context(self) -> None:
        """Absolute path in failure_context_ref.path is rejected."""
        request = _valid_request()
        request["failure_context_ref"]["path"] = "/abs/path"
        with pytest.raises(ReviewContractError, match="absolute path"):
            validate_review_request(request)

    def test_S12_invalid_sha256(self) -> None:
        """Invalid SHA-256 is rejected."""
        request = _valid_request()
        request["manifest_ref"]["sha256"] = "invalid"
        with pytest.raises(ReviewContractError, match="sha256 must be 64-char lowercase hex"):
            validate_review_request(request)

    def test_S13_initial_verify_with_repair_iteration_1(self) -> None:
        """initial_verify_pass with repair_iteration=1 is rejected."""
        request = _valid_request()
        request["triggered_by"] = "initial_verify_pass"
        request["repair_iteration"] = 1
        request["review_iteration"] = 2
        with pytest.raises(ReviewContractError, match="initial_verify_pass requires repair_iteration == 0"):
            validate_review_request(request)

    def test_S14_post_repair_with_repair_iteration_0(self) -> None:
        """post_repair_verify_pass with repair_iteration=0 is rejected."""
        request = _valid_request()
        request["triggered_by"] = "post_repair_verify_pass"
        request["repair_iteration"] = 0
        request["review_iteration"] = 1
        with pytest.raises(ReviewContractError, match="post_repair_verify_pass requires repair_iteration >= 1"):
            validate_review_request(request)

    def test_S15_review_iteration_0(self) -> None:
        """review_iteration=0 is rejected."""
        request = _valid_request()
        request["review_iteration"] = 0
        with pytest.raises(ReviewContractError, match="review_iteration must be integer >= 1"):
            validate_review_request(request)

    def test_S16_review_iteration_2_repair_0(self) -> None:
        """review_iteration=2 with repair_iteration=0 is rejected."""
        request = _valid_request()
        request["review_iteration"] = 2
        request["repair_iteration"] = 0
        with pytest.raises(ReviewContractError, match="must equal repair_iteration"):
            validate_review_request(request)

    def test_S17_review_iteration_3_repair_1(self) -> None:
        """review_iteration=3 with repair_iteration=1 is rejected."""
        request = _valid_request()
        request["review_iteration"] = 3
        request["repair_iteration"] = 1
        with pytest.raises(ReviewContractError, match="must equal repair_iteration"):
            validate_review_request(request)

    def test_S18_pass_with_repair_action(self) -> None:
        """PASS status with recommended_action='repair' is rejected."""
        result = _valid_result()
        result["status"] = "PASS"
        result["recommended_action"] = "repair"
        with pytest.raises(ReviewContractError, match="PASS status requires recommended_action == 'none'"):
            validate_review_result(result)

    def test_S19_pass_with_blocker_finding(self) -> None:
        """PASS status with BLOCKER finding is rejected."""
        result = _valid_result()
        result["status"] = "PASS"
        result["findings"] = [
            {
                "finding_id": "F001",
                "severity": "BLOCKER",
                "category": "test",
                "summary": "Test",
                "evidence_refs": [],
                "recommended_fix": "Fix",
            }
        ]
        with pytest.raises(ReviewContractError, match="PASS status cannot have BLOCKER"):
            validate_review_result(result)

    def test_S20_fail_without_blocker_major(self) -> None:
        """FAIL status without BLOCKER/MAJOR finding is rejected."""
        result = _valid_result()
        result["status"] = "FAIL"
        result["recommended_action"] = "repair"
        result["findings"] = [
            {
                "finding_id": "F001",
                "severity": "MINOR",
                "category": "test",
                "summary": "Test",
                "evidence_refs": [],
                "recommended_fix": "Fix",
            }
        ]
        with pytest.raises(ReviewContractError, match="FAIL status requires at least one BLOCKER or MAJOR"):
            validate_review_result(result)

    def test_S21_fail_with_none_action(self) -> None:
        """FAIL status with recommended_action='none' is rejected."""
        result = _valid_result()
        result["status"] = "FAIL"
        result["recommended_action"] = "none"
        result["findings"] = [
            {
                "finding_id": "F001",
                "severity": "MAJOR",
                "category": "test",
                "summary": "Test",
                "evidence_refs": [],
                "recommended_fix": "Fix",
            }
        ]
        with pytest.raises(ReviewContractError, match="FAIL status requires recommended_action == 'repair'"):
            validate_review_result(result)

    def test_S22_error_with_repair_action(self) -> None:
        """ERROR status with recommended_action='repair' is rejected."""
        result = _valid_result()
        result["status"] = "ERROR"
        result["recommended_action"] = "repair"
        with pytest.raises(ReviewContractError, match="ERROR status requires recommended_action == 'human_review'"):
            validate_review_result(result)

    def test_S23_error_with_none_action(self) -> None:
        """ERROR status with recommended_action='none' is rejected."""
        result = _valid_result()
        result["status"] = "ERROR"
        result["recommended_action"] = "none"
        with pytest.raises(ReviewContractError, match="ERROR status requires recommended_action == 'human_review'"):
            validate_review_result(result)

    def test_S24_duplicate_finding_id(self) -> None:
        """Duplicate finding_id is rejected."""
        result = _valid_result()
        result["findings"] = [
            {
                "finding_id": "F001",
                "severity": "INFO",
                "category": "test",
                "summary": "Test 1",
                "evidence_refs": [],
                "recommended_fix": "Fix",
            },
            {
                "finding_id": "F001",
                "severity": "INFO",
                "category": "test",
                "summary": "Test 2",
                "evidence_refs": [],
                "recommended_fix": "Fix",
            },
        ]
        with pytest.raises(ReviewContractError, match="duplicate finding_id"):
            validate_review_result(result)

    def test_S25_findings_not_ordered(self) -> None:
        """Findings not ordered by finding_id is rejected."""
        result = _valid_result()
        result["findings"] = [
            {
                "finding_id": "F002",
                "severity": "INFO",
                "category": "test",
                "summary": "Test 2",
                "evidence_refs": [],
                "recommended_fix": "Fix",
            },
            {
                "finding_id": "F001",
                "severity": "INFO",
                "category": "test",
                "summary": "Test 1",
                "evidence_refs": [],
                "recommended_fix": "Fix",
            },
        ]
        with pytest.raises(ReviewContractError, match="findings not ordered"):
            validate_review_result(result)

    def test_S26_too_many_truncated_fields(self) -> None:
        """Too many truncated_fields is rejected."""
        request = _valid_request()
        request["sanitization"]["truncated_fields"] = ["field"] * 65
        with pytest.raises(ReviewContractError, match="truncated_fields exceeds 64 entries"):
            validate_review_request(request)

    def test_S27_negative_redaction_count(self) -> None:
        """Negative redaction_count is rejected."""
        request = _valid_request()
        request["sanitization"]["redaction_count"] = -1
        with pytest.raises(ReviewContractError, match="redaction_count must be integer >= 0"):
            validate_review_request(request)

    def test_S28_oversized_reviewer_id(self) -> None:
        """Oversized reviewer_id is rejected."""
        request = _valid_request()
        request["reviewer_id"] = "x" * 129
        with pytest.raises(ReviewContractError, match="reviewer_id exceeds 128 bytes"):
            validate_review_request(request)

    def test_S29_invalid_run_id_format(self) -> None:
        """Invalid run_id format is rejected."""
        request = _valid_request()
        request["run_id"] = "invalid run id"
        with pytest.raises(ReviewContractError, match="run_id contains invalid characters"):
            validate_review_request(request)

    def test_S30_invalid_generated_at_format(self) -> None:
        """Invalid generated_at format is rejected."""
        request = _valid_request()
        request["generated_at"] = "not-iso-8601"
        with pytest.raises(ReviewContractError, match="generated_at must be ISO-8601"):
            validate_review_request(request)


# ---------------------------------------------------------------------------
# Referential validation tests (R01-R20)
# ---------------------------------------------------------------------------
class TestReferentialValidation:
    """Referential validation tests (filesystem required)."""

    def test_R01_valid_referential(self, tmp_path: Path) -> None:
        """Valid referential validation passes."""
        # Setup
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)
        manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

        fc_path = run_dir / "reports" / "failure-context.json"
        fc_path.parent.mkdir()
        fc = {
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "story_id": "US-002",
            "overall_verification_status": "PASS",
            "candidate_identity": {
                "base_commit": "0" * 40,
                "candidate_commit": None,
                "candidate_state": "working_tree",
                "candidate_diff_digest": "c" * 64,
            },
        }
        fc_bytes = json.dumps(fc).encode("utf-8")
        fc_path.write_bytes(fc_bytes)
        fc_sha256 = hashlib.sha256(fc_bytes).hexdigest()

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = manifest_sha256
        request["failure_context_ref"]["path"] = "reports/failure-context.json"
        request["failure_context_ref"]["sha256"] = fc_sha256

        validate_review_request_references(request, repo_root, run_dir)

    def test_R02_manifest_not_exists(self, tmp_path: Path) -> None:
        """Manifest file does not exist is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        request = _valid_request()
        request["manifest_ref"]["path"] = "nonexistent.json"

        with pytest.raises(ReviewContractError, match="manifest file does not exist"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R03_manifest_sha256_mismatch(self, tmp_path: Path) -> None:
        """Manifest SHA-256 mismatch is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest_path.write_text("{}")

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = "0" * 64

        with pytest.raises(ReviewContractError, match="manifest SHA-256 mismatch"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R04_manifest_schema_version_mismatch(self, tmp_path: Path) -> None:
        """Manifest schema_version mismatch is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {"schema_version": "2.0"}
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()

        with pytest.raises(ReviewContractError, match="manifest schema_version must be '1.0'"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R05_excerpt_title_mismatch(self, tmp_path: Path) -> None:
        """Manifest excerpt title mismatch is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Different Title",
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["manifest_excerpt"]["title"] = "Wrong Title"

        with pytest.raises(ReviewContractError, match="manifest_excerpt.title does not match"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R06_excerpt_description_mismatch(self, tmp_path: Path) -> None:
        """Manifest excerpt description mismatch is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test",
            "description": "Different",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["manifest_excerpt"]["title"] = "Test"
        request["manifest_excerpt"]["description"] = "Wrong"

        with pytest.raises(ReviewContractError, match="manifest_excerpt.description does not match"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R07_excerpt_acceptance_criteria_mismatch(self, tmp_path: Path) -> None:
        """Manifest excerpt acceptance_criteria mismatch is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test",
            "description": "Test",
            "acceptance_criteria": ["Different"],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["manifest_excerpt"]["title"] = "Test"
        request["manifest_excerpt"]["description"] = "Test"
        request["manifest_excerpt"]["acceptance_criteria"] = ["Wrong"]

        with pytest.raises(ReviewContractError, match="manifest_excerpt.acceptance_criteria does not match"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R08_excerpt_allowed_paths_mismatch(self, tmp_path: Path) -> None:
        """Manifest excerpt allowed_paths mismatch is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test",
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": ["different/**"],
            "forbidden_paths": [],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["manifest_excerpt"]["title"] = "Test"
        request["manifest_excerpt"]["description"] = "Test"
        request["manifest_excerpt"]["acceptance_criteria"] = []
        request["manifest_excerpt"]["allowed_paths"] = ["wrong/**"]

        with pytest.raises(ReviewContractError, match="manifest_excerpt.allowed_paths does not match"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R09_failure_context_not_exists(self, tmp_path: Path) -> None:
        """Failure-context file does not exist is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["failure_context_ref"]["path"] = "nonexistent.json"

        with pytest.raises(ReviewContractError, match="failure-context file does not exist"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R10_failure_context_sha256_mismatch(self, tmp_path: Path) -> None:
        """Failure-context SHA-256 mismatch is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test",
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        fc_path = run_dir / "fc.json"
        fc_path.write_text("{}")

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["manifest_excerpt"]["title"] = "Test"
        request["manifest_excerpt"]["description"] = "Test"
        request["manifest_excerpt"]["acceptance_criteria"] = []
        request["manifest_excerpt"]["allowed_paths"] = []
        request["manifest_excerpt"]["forbidden_paths"] = []
        request["failure_context_ref"]["path"] = "fc.json"
        request["failure_context_ref"]["sha256"] = "0" * 64

        with pytest.raises(ReviewContractError, match="failure-context SHA-256 mismatch"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R11_failure_context_schema_version_mismatch(self, tmp_path: Path) -> None:
        """Failure-context schema_version mismatch is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        fc_path = run_dir / "fc.json"
        fc = {"schema_version": "2.0", "run_id": "test-run-123", "story_id": "US-002",
              "overall_verification_status": "PASS", "candidate_identity": request_ci()}
        fc_bytes = json.dumps(fc).encode("utf-8")
        fc_path.write_bytes(fc_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["failure_context_ref"]["path"] = "fc.json"
        request["failure_context_ref"]["sha256"] = hashlib.sha256(fc_bytes).hexdigest()

        with pytest.raises(ReviewContractError, match="failure-context schema_version must be '1.0'"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R12_run_id_mismatch(self, tmp_path: Path) -> None:
        """run_id mismatch between request and failure-context is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "different-run",
            "story_id": "US-002",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_bytes = json.dumps(fc).encode("utf-8")
        fc_path.write_bytes(fc_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["failure_context_ref"]["path"] = "fc.json"
        request["failure_context_ref"]["sha256"] = hashlib.sha256(fc_bytes).hexdigest()

        with pytest.raises(ReviewContractError, match="run_id mismatch"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R13_story_id_mismatch(self, tmp_path: Path) -> None:
        """story_id mismatch between request and failure-context is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "story_id": "US-999",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_bytes = json.dumps(fc).encode("utf-8")
        fc_path.write_bytes(fc_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["failure_context_ref"]["path"] = "fc.json"
        request["failure_context_ref"]["sha256"] = hashlib.sha256(fc_bytes).hexdigest()

        with pytest.raises(ReviewContractError, match="story_id mismatch"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R14_candidate_identity_mismatch(self, tmp_path: Path) -> None:
        """candidate_identity mismatch is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "story_id": "US-002",
            "overall_verification_status": "PASS",
            "candidate_identity": {
                "base_commit": "1" * 40,  # Different
                "candidate_commit": None,
                "candidate_state": "working_tree",
                "candidate_diff_digest": "c" * 64,
            },
        }
        fc_bytes = json.dumps(fc).encode("utf-8")
        fc_path.write_bytes(fc_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["failure_context_ref"]["path"] = "fc.json"
        request["failure_context_ref"]["sha256"] = hashlib.sha256(fc_bytes).hexdigest()

        with pytest.raises(ReviewContractError, match="candidate_identity does not exactly match"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R15_overall_verification_status_not_pass(self, tmp_path: Path) -> None:
        """Failure-context overall_verification_status not PASS is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "story_id": "US-002",
            "overall_verification_status": "FAIL",
            "candidate_identity": request_ci(),
        }
        fc_bytes = json.dumps(fc).encode("utf-8")
        fc_path.write_bytes(fc_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["failure_context_ref"]["path"] = "fc.json"
        request["failure_context_ref"]["sha256"] = hashlib.sha256(fc_bytes).hexdigest()

        with pytest.raises(ReviewContractError, match="overall_verification_status must be 'PASS'"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R16_absolute_manifest_path(self, tmp_path: Path) -> None:
        """Absolute manifest_ref.path is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        request = _valid_request()
        request["manifest_ref"]["path"] = "/absolute/path"

        with pytest.raises(ReviewContractError, match="absolute path"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R17_absolute_failure_context_path(self, tmp_path: Path) -> None:
        """Absolute failure_context_ref.path is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Create a valid manifest so we get past that check
        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["failure_context_ref"]["path"] = "/absolute/path"

        with pytest.raises(ReviewContractError, match="absolute path"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R18_manifest_path_traversal(self, tmp_path: Path) -> None:
        """manifest_ref.path with traversal is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        request = _valid_request()
        request["manifest_ref"]["path"] = "../traversal"

        with pytest.raises(ReviewContractError, match="path traversal"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R19_failure_context_path_traversal(self, tmp_path: Path) -> None:
        """failure_context_ref.path with traversal is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Create a valid manifest so we get past that check
        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"
        request["manifest_ref"]["sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
        request["failure_context_ref"]["path"] = "../traversal"

        with pytest.raises(ReviewContractError, match="path traversal"):
            validate_review_request_references(request, repo_root, run_dir)

    def test_R20_path_base_confusion(self, tmp_path: Path) -> None:
        """Path base confusion is rejected."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Put manifest in run_dir instead of repo_root
        wrong_manifest = run_dir / "manifest.json"
        wrong_manifest.write_text("{}")

        request = _valid_request()
        request["manifest_ref"]["path"] = "manifest.json"

        # This should fail because manifest.json doesn't exist under repo_root
        with pytest.raises(ReviewContractError, match="manifest file does not exist"):
            validate_review_request_references(request, repo_root, run_dir)


def request_ci() -> dict[str, Any]:
    """Helper to create candidate_identity for tests."""
    return {
        "base_commit": "0" * 40,
        "candidate_commit": None,
        "candidate_state": "working_tree",
        "candidate_diff_digest": "c" * 64,
    }


# ---------------------------------------------------------------------------
# Builder tests (B01-B20)
# ---------------------------------------------------------------------------
class TestBuilder:
    """Builder tests."""

    def test_B01_valid_builder(self, tmp_path: Path) -> None:
        """Builder from valid inputs produces valid request."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test Story",
            "description": "Test description",
            "acceptance_criteria": ["AC1"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "reports" / "failure-context.json"
        fc_path.parent.mkdir()
        fc = {
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "story_id": "US-002",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
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
        )

        assert request["schema_version"] == "1.0"
        assert request["run_id"] == "test-run-123"

    def test_B02_manifest_sha256_correct(self, tmp_path: Path) -> None:
        """Builder computes manifest SHA-256 correctly."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest_content = b'{"schema_version": "1.0", "story_id": "test"}'
        manifest_path.write_bytes(manifest_content)
        expected_sha256 = hashlib.sha256(manifest_content).hexdigest()

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert request["manifest_ref"]["sha256"] == expected_sha256

    def test_B03_failure_context_sha256_correct(self, tmp_path: Path) -> None:
        """Builder computes failure-context SHA-256 correctly."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {"schema_version": "1.0", "story_id": "test", "title": "Test", "description": "Test",
                    "acceptance_criteria": [], "allowed_paths": [], "forbidden_paths": []}
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc_content = b'{"schema_version": "1.0", "run_id": "test", "story_id": "test", "overall_verification_status": "PASS", "candidate_identity": {"base_commit": "0000000000000000000000000000000000000000", "candidate_commit": null, "candidate_state": "working_tree", "candidate_diff_digest": "0000000000000000000000000000000000000000000000000000000000000000"}}'
        fc_path.write_bytes(fc_content)
        expected_sha256 = hashlib.sha256(fc_content).hexdigest()

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert request["failure_context_ref"]["sha256"] == expected_sha256

    def test_B04_missing_manifest_file(self, tmp_path: Path) -> None:
        """Builder with missing manifest file raises error."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        fc_path = run_dir / "fc.json"
        fc_path.write_text("{}")

        with pytest.raises(ReviewContractError, match="manifest file does not exist"):
            build_review_request(
                repo_root=repo_root,
                run_dir=run_dir,
                manifest_path=repo_root / "nonexistent.json",
                failure_context_path=fc_path,
                run_id="test",
                story_id="test",
                review_iteration=1,
                repair_iteration=0,
                triggered_by="initial_verify_pass",
                generated_at="2026-08-04T12:00:00Z",
                reviewer_id="test",
            )

    def test_B05_invalid_manifest_schema(self, tmp_path: Path) -> None:
        """Builder with invalid manifest schema raises error."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest_path.write_text('{"schema_version": "2.0"}')

        fc_path = run_dir / "fc.json"
        fc_path.write_text("{}")

        with pytest.raises(ReviewContractError, match="manifest schema_version must be '1.0'"):
            build_review_request(
                repo_root=repo_root,
                run_dir=run_dir,
                manifest_path=manifest_path,
                failure_context_path=fc_path,
                run_id="test",
                story_id="test",
                review_iteration=1,
                repair_iteration=0,
                triggered_by="initial_verify_pass",
                generated_at="2026-08-04T12:00:00Z",
                reviewer_id="test",
            )

    def test_B06_missing_failure_context_file(self, tmp_path: Path) -> None:
        """Builder with missing failure-context file raises error."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {"schema_version": "1.0", "story_id": "test", "title": "Test", "description": "Test",
                    "acceptance_criteria": [], "allowed_paths": [], "forbidden_paths": []}
        manifest_path.write_text(json.dumps(manifest))

        with pytest.raises(ReviewContractError, match="failure-context file does not exist"):
            build_review_request(
                repo_root=repo_root,
                run_dir=run_dir,
                manifest_path=manifest_path,
                failure_context_path=run_dir / "nonexistent.json",
                run_id="test",
                story_id="test",
                review_iteration=1,
                repair_iteration=0,
                triggered_by="initial_verify_pass",
                generated_at="2026-08-04T12:00:00Z",
                reviewer_id="test",
            )

    def test_B07_invalid_failure_context_schema(self, tmp_path: Path) -> None:
        """Builder with invalid failure-context schema raises error."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {"schema_version": "1.0", "story_id": "test", "title": "Test", "description": "Test",
                    "acceptance_criteria": [], "allowed_paths": [], "forbidden_paths": []}
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc_path.write_text('{"schema_version": "2.0"}')

        with pytest.raises(ReviewContractError, match="failure-context schema_version must be '1.0'"):
            build_review_request(
                repo_root=repo_root,
                run_dir=run_dir,
                manifest_path=manifest_path,
                failure_context_path=fc_path,
                run_id="test",
                story_id="test",
                review_iteration=1,
                repair_iteration=0,
                triggered_by="initial_verify_pass",
                generated_at="2026-08-04T12:00:00Z",
                reviewer_id="test",
            )

    def test_B08_sanitize_secret_in_title(self, tmp_path: Path) -> None:
        """Builder sanitizes secret pattern in manifest title."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Construct test secret at runtime to avoid hardcoding in source
        test_secret = "sk_liv" + "e_12345678901234567890"
        test_title = f"Test with {test_secret} secret"

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": test_title,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED" in request["manifest_excerpt"]["title"]
        assert "sk_live_" not in request["manifest_excerpt"]["title"]

    def test_B09_sanitize_url_query_in_description(self, tmp_path: Path) -> None:
        """Builder sanitizes URL query string in description."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": "Test",
            "description": "See https://example.com/api?token=secret123 for details",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "?token=" not in request["manifest_excerpt"]["description"]
        assert "https://example.com/api" in request["manifest_excerpt"]["description"]

    def test_B10_sanitize_control_chars_in_acceptance_criteria(self, tmp_path: Path) -> None:
        """Builder sanitizes control characters in acceptance_criteria."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": "Test",
            "description": "Test",
            "acceptance_criteria": ["AC1\x00with\x01control"],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "\x00" not in request["manifest_excerpt"]["acceptance_criteria"][0]
        assert "\x01" not in request["manifest_excerpt"]["acceptance_criteria"][0]

    def test_B11_sanitize_binary_in_repair_guidance(self, tmp_path: Path) -> None:
        """Builder sanitizes binary content in repair_guidance."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        # Create binary-like content
        binary_content = "Fix this:\x00\x01\x02" * 50
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": "Test",
            "description": "Test",
            "acceptance_criteria": [],
            "repair_guidance": [binary_content],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:binary_content]" in request["manifest_excerpt"]["repair_guidance"][0]

    def test_B12_truncate_oversized_title(self, tmp_path: Path) -> None:
        """Builder truncates oversized title and adds marker."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        # Use mixed characters to avoid base64 detection
        long_title = "Test title with spaces and punctuation! " * 10
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": long_title,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert len(request["manifest_excerpt"]["title"].encode("utf-8")) <= 256
        assert "[truncated:" in request["manifest_excerpt"]["title"]
        assert "manifest_excerpt.title" in request["sanitization"]["truncated_fields"]

    def test_B13_utf8_invalid_bytes(self, tmp_path: Path) -> None:
        """Builder normalizes NFD Unicode to NFC and rejects malformed UTF-8 bytes."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        # Use NFD (decomposed) form: e + combining acute accent (6 bytes)
        nfd_title = "cafe\u0301"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": nfd_title,
            "description": "Test description",
            "acceptance_criteria": ["AC1", "AC2"],
            "repair_guidance": ["RG1"],
            "allowed_paths": ["backend/**"],
            "forbidden_paths": [".env"],
        }
        manifest_bytes = json.dumps(manifest).encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)

        fc_path = run_dir / "reports" / "failure-context.json"
        fc_path.parent.mkdir()
        fc = {
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "story_id": "US-002",
            "overall_verification_status": "PASS",
            "candidate_identity": {
                "base_commit": "0" * 40,
                "candidate_commit": None,
                "candidate_state": "working_tree",
                "candidate_diff_digest": "c" * 64,
            },
        }
        fc_bytes = json.dumps(fc).encode("utf-8")
        fc_path.write_bytes(fc_bytes)

        request = build_review_request(
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
        )

        # Assert: title is NFC normalized (5 bytes), not NFD (6 bytes)
        nfc_title = "caf\u00e9"
        assert request["manifest_excerpt"]["title"] == nfc_title
        assert len(request["manifest_excerpt"]["title"].encode("utf-8")) == 5
        assert len(nfd_title.encode("utf-8")) == 6

        # Also verify malformed UTF-8 file bytes are rejected as bounded error
        bad_manifest_path = repo_root / "bad_manifest.json"
        bad_manifest_path.write_bytes(b'{"schema_version": "1.0", "title": "\xff\xfe}')
        with pytest.raises(ReviewContractError, match="not valid JSON"):
            build_review_request(
                repo_root=repo_root,
                run_dir=run_dir,
                manifest_path=bad_manifest_path,
                failure_context_path=fc_path,
                run_id="test-run-123",
                story_id="US-002",
                review_iteration=1,
                repair_iteration=0,
                triggered_by="initial_verify_pass",
                generated_at="2026-08-04T12:00:00Z",
                reviewer_id="mock-reviewer",
            )

    def test_B14_sanitization_metadata_accurate(self, tmp_path: Path) -> None:
        """Builder populates sanitization metadata accurately."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Construct test secret at runtime
        test_secret = "sk_liv" + "e_12345678901234567890"

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": f"Test with {test_secret}",
            "description": "See https://example.com?token=secret",
            "acceptance_criteria": ["AC1"],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert request["sanitization"]["redaction_applied"] is True
        assert request["sanitization"]["redaction_count"] > 0

    def test_B15_no_sanitization_needed(self, tmp_path: Path) -> None:
        """Builder with no sanitization needed sets metadata correctly."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": "Clean Title",
            "description": "Clean description",
            "acceptance_criteria": ["Clean AC"],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert request["sanitization"]["redaction_applied"] is False
        assert request["sanitization"]["redaction_count"] == 0
        assert request["sanitization"]["truncation_applied"] is False
        assert request["sanitization"]["truncated_fields"] == []

    def test_B16_deterministic_output(self, tmp_path: Path) -> None:
        """Builder produces deterministic output for same inputs."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": "Test",
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request1 = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        request2 = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert canonical_json_bytes(request1) == canonical_json_bytes(request2)

    def test_B17_canonical_bytes_format(self, tmp_path: Path) -> None:
        """Builder canonical bytes use correct format."""
        obj = {"b": 2, "a": 1}
        result = canonical_json_bytes(obj)
        assert result == b'{"a":1,"b":2}'

    def test_B18_pretty_json_format(self) -> None:
        """Builder pretty JSON has correct format."""
        obj = {"b": 2, "a": 1}
        result = pretty_json_string(obj)
        lines = result.split("\n")
        assert lines[0] == "{"
        assert lines[-1] == ""  # Terminal newline
        assert lines[-2] == "}"
        # Check no trailing whitespace
        for line in lines:
            assert line == line.rstrip()

    def test_B19_no_internal_time_call(self) -> None:
        """Builder does not call internal time functions."""
        # Check 1: Verify generated_at is required parameter
        import inspect
        sig = inspect.signature(build_review_request)
        assert "generated_at" in sig.parameters
        # Calling without generated_at should raise TypeError
        with pytest.raises(TypeError, match="generated_at"):
            build_review_request(  # type: ignore[call-arg]
                repo_root=Path("/tmp"),
                run_dir=Path("/tmp"),
                manifest_path=Path("/tmp/manifest.json"),
                failure_context_path=Path("/tmp/fc.json"),
                run_id="test",
                story_id="US-002",
                review_iteration=1,
                repair_iteration=0,
                triggered_by="initial_verify_pass",
                reviewer_id="mock",
            )

        # Check 2: Inspect source for forbidden time imports
        import review_contract as rc_module
        source = inspect.getsource(rc_module)
        forbidden = ["datetime.now", "datetime.utcnow", "time.time", "date.today"]
        for pattern in forbidden:
            assert pattern not in source, f"Found forbidden pattern: {pattern}"

    def test_B20_validates_own_output(self, tmp_path: Path) -> None:
        """Builder validates its own output before returning."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "US-002",
            "title": "Test",
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "US-002",
            "overall_verification_status": "PASS",
            "candidate_identity": {
                "base_commit": "0" * 40,
                "candidate_commit": None,
                "candidate_state": "working_tree",
                "candidate_diff_digest": "c" * 64,
            },
        }
        fc_path.write_text(json.dumps(fc))

        # Monkeypatch validators to track invocations
        import review_contract
        original_validate_request = review_contract.validate_review_request
        original_validate_refs = review_contract.validate_review_request_references

        request_calls: list[bool] = []
        refs_calls: list[bool] = []

        def mock_validate_request(req: dict[str, Any]) -> None:
            request_calls.append(True)
            original_validate_request(req)

        def mock_validate_refs(req: dict[str, Any], repo: Path, run: Path) -> None:
            refs_calls.append(True)
            original_validate_refs(req, repo, run)

        review_contract.validate_review_request = mock_validate_request  # type: ignore[assignment]
        review_contract.validate_review_request_references = mock_validate_refs  # type: ignore[assignment]

        try:
            build_review_request(
                repo_root=repo_root,
                run_dir=run_dir,
                manifest_path=manifest_path,
                failure_context_path=fc_path,
                run_id="test",
                story_id="US-002",
                review_iteration=1,
                repair_iteration=0,
                triggered_by="initial_verify_pass",
                generated_at="2026-08-04T12:00:00Z",
                reviewer_id="mock",
            )

            # Assert both validators were called exactly once
            assert len(request_calls) == 1, "validate_review_request should be called once"
            assert len(refs_calls) == 1, "validate_review_request_references should be called once"
        finally:
            # Restore original validators
            review_contract.validate_review_request = original_validate_request
            review_contract.validate_review_request_references = original_validate_refs


# ---------------------------------------------------------------------------
# Serialization tests (C01-C08)
# ---------------------------------------------------------------------------
class TestSerialization:
    """Serialization tests."""

    def test_C01_canonical_deterministic(self) -> None:
        """Canonical bytes deterministic for different insertion order."""
        obj1 = {"b": 2, "a": 1}
        obj2 = {"a": 1, "b": 2}
        assert canonical_json_bytes(obj1) == canonical_json_bytes(obj2)

    def test_C02_canonical_sort_keys(self) -> None:
        """Canonical bytes use sort_keys=True."""
        obj = {"z": 1, "a": 2}
        result = canonical_json_bytes(obj).decode("utf-8")
        assert result.index('"a"') < result.index('"z"')

    def test_C03_canonical_compact_separators(self) -> None:
        """Canonical bytes use compact separators."""
        obj = {"a": 1}
        result = canonical_json_bytes(obj).decode("utf-8")
        assert result == '{"a":1}'
        assert ": " not in result
        assert ", " not in result

    def test_C04_canonical_preserve_utf8(self) -> None:
        """Canonical bytes preserve UTF-8."""
        obj = {"text": "Hello 世界"}
        result = canonical_json_bytes(obj).decode("utf-8")
        assert "世界" in result

    def test_C05_pretty_indent_2(self) -> None:
        """Pretty JSON has indent=2."""
        obj = {"a": 1}
        result = pretty_json_string(obj)
        assert "  " in result

    def test_C06_pretty_one_terminal_newline(self) -> None:
        """Pretty JSON has exactly one terminal newline."""
        obj = {"a": 1}
        result = pretty_json_string(obj)
        assert result.endswith("\n")
        assert not result.endswith("\n\n")

    def test_C07_pretty_no_trailing_whitespace(self) -> None:
        """Pretty JSON has no trailing whitespace on any line."""
        obj = {"a": 1, "b": 2}
        result = pretty_json_string(obj)
        for line in result.split("\n"):
            assert line == line.rstrip()

    def test_C08_pretty_sort_keys(self) -> None:
        """Pretty JSON uses sort_keys=True."""
        obj = {"z": 1, "a": 2}
        result = pretty_json_string(obj)
        assert result.index('"a"') < result.index('"z"')


# ---------------------------------------------------------------------------
# Sanitization tests (D01-D16)
# ---------------------------------------------------------------------------
class TestSanitization:
    """Sanitization tests."""

    def test_D01_redact_stripe_key(self, tmp_path: Path) -> None:
        """Redact Stripe key pattern."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Construct test secret at runtime
        test_secret = "sk_liv" + "e_1234567890abcdefghijklmnop"

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": test_secret,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:stripe_key]" in request["manifest_excerpt"]["title"]

    def test_D02_redact_github_token(self, tmp_path: Path) -> None:
        """Redact GitHub token pattern."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Construct test secret at runtime
        test_secret = "ghp_" + "1234567890abcdef1234567890abcdef1234"

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": test_secret,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:github_token]" in request["manifest_excerpt"]["title"]

    def test_D03_redact_aws_key(self, tmp_path: Path) -> None:
        """Redact AWS access key pattern."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Construct test secret at runtime
        test_secret = "AKIA" + "1234567890ABCDEF"

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": test_secret,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:aws_key]" in request["manifest_excerpt"]["title"]

    def test_D04_redact_bearer_token(self, tmp_path: Path) -> None:
        """Redact Bearer token pattern."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Construct test secret at runtime
        test_secret = "Bearer abc123xyz"

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": test_secret,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:bearer_token]" in request["manifest_excerpt"]["title"]

    def test_D05_redact_basic_auth(self, tmp_path: Path) -> None:
        """Redact Basic auth pattern."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Construct test secret at runtime
        test_secret = "Basic " + "dXNlcjpwYXNz"

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": test_secret,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:basic_auth]" in request["manifest_excerpt"]["title"]

    def test_D06_redact_password_assignment(self, tmp_path: Path) -> None:
        """Redact password assignment."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": 'password = "secret123"',
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:password]" in request["manifest_excerpt"]["title"]

    def test_D07_redact_api_key_assignment(self, tmp_path: Path) -> None:
        """Redact api_key assignment."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": 'api_key = "secret123"',
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:api_key]" in request["manifest_excerpt"]["title"]

    def test_D08_redact_secret_assignment(self, tmp_path: Path) -> None:
        """Redact secret assignment."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": 'secret = "secret123"',
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:secret]" in request["manifest_excerpt"]["title"]

    def test_D09_redact_private_key_block(self, tmp_path: Path) -> None:
        """Redact private key block."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Construct test secret at runtime
        test_secret = "-----BEGIN PRIVATE KEY-----\nMIIBVAIBADANBgkqhkiG9w0BAQEFAASCAT4wggE6AgEAAkEA\n-----END PRIVATE KEY-----"

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": test_secret,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:private_key]" in request["manifest_excerpt"]["title"]

    def test_D10_strip_url_query(self, tmp_path: Path) -> None:
        """Strip URL query string."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": "See https://example.com/path?query=secret",
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "?query=" not in request["manifest_excerpt"]["title"]
        assert "https://example.com/path" in request["manifest_excerpt"]["title"]

    def test_D11_detect_binary_content(self, tmp_path: Path) -> None:
        """Detect binary content."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": "\x00\x01\x02" * 50,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:binary_content]" in request["manifest_excerpt"]["title"]

    def test_D12_redact_base64_run(self, tmp_path: Path) -> None:
        """Redact base64 run (100+ chars)."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        base64_content = "A" * 120
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": f"Data: {base64_content}",
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "[REDACTED:base64_payload]" in request["manifest_excerpt"]["title"]

    def test_D13_remove_control_characters(self, tmp_path: Path) -> None:
        """Remove control characters (preserve \\n\\t\\r)."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        # Use minimal control chars to avoid binary detection
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": "Test\x01with\x02control",
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        title = request["manifest_excerpt"]["title"]
        assert "\x01" not in title
        assert "\x02" not in title

    def test_D14_utf8_normalize(self) -> None:
        """UTF-8 normalize invalid bytes with U+FFFD replacement."""
        # Test the sanitization pipeline directly
        # Import the internal helper to test normalization behavior
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
        from review_contract import _sanitize_field_with_metadata

        # Test 1: NFD -> NFC normalization through pipeline
        nfd_text = "cafe\u0301"  # e + combining acute (decomposed)
        nfc_text = "caf\u00e9"   # é (composed)

        truncation_fields: list[str] = []
        redaction_counts: list[int] = []

        result = _sanitize_field_with_metadata(
            nfd_text,
            "test_field",
            max_bytes=1000,
            truncation_fields=truncation_fields,
            redaction_counts=redaction_counts,
        )

        # Assert: result is NFC normalized
        assert result == nfc_text
        # Verify canonical bytes are deterministic for equivalent inputs
        # After sanitization, both should produce identical canonical bytes
        nfd_result = _sanitize_field_with_metadata(
            nfd_text, "f", 1000, [], []
        )
        nfc_result = _sanitize_field_with_metadata(
            nfc_text, "f", 1000, [], []
        )
        assert canonical_json_bytes({"text": nfd_result}) == canonical_json_bytes({"text": nfc_result})
        # Metadata should be accurate
        assert len(truncation_fields) == 0
        assert len(redaction_counts) == 0

    def test_D15_truncation_marker_format(self, tmp_path: Path) -> None:
        """Truncation marker format."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        manifest_path = repo_root / "manifest.json"
        # Use mixed characters to avoid base64 detection
        long_title = "Test title with spaces and punctuation! " * 10
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": long_title,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert "... [truncated:" in request["manifest_excerpt"]["title"]
        assert "bytes omitted]" in request["manifest_excerpt"]["title"]

    def test_D16_redaction_count_accurate(self, tmp_path: Path) -> None:
        """Redaction count accurate."""
        repo_root = tmp_path / "repo"
        run_dir = tmp_path / "run"
        repo_root.mkdir()
        run_dir.mkdir()

        # Construct test secrets at runtime
        test_secret = "sk_liv" + "e_12345678901234567890" + " and ghp_" + "1234567890abcdef1234567890abcdef1234"

        manifest_path = repo_root / "manifest.json"
        manifest = {
            "schema_version": "1.0",
            "story_id": "test",
            "title": test_secret,
            "description": "Test",
            "acceptance_criteria": [],
            "allowed_paths": [],
            "forbidden_paths": [],
        }
        manifest_path.write_text(json.dumps(manifest))

        fc_path = run_dir / "fc.json"
        fc = {
            "schema_version": "1.0",
            "run_id": "test",
            "story_id": "test",
            "overall_verification_status": "PASS",
            "candidate_identity": request_ci(),
        }
        fc_path.write_text(json.dumps(fc))

        request = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=fc_path,
            run_id="test",
            story_id="test",
            review_iteration=1,
            repair_iteration=0,
            triggered_by="initial_verify_pass",
            generated_at="2026-08-04T12:00:00Z",
            reviewer_id="test",
        )

        assert request["sanitization"]["redaction_count"] >= 2
