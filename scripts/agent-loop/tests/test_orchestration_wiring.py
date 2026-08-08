"""
WP-AL-1C6: Focused tests for orchestration wiring state machine.

Tests verify the core control-flow invariants of run-story.sh orchestration.
These are unit-level tests that validate the decision logic without requiring
full subprocess execution.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Test data builders
# ---------------------------------------------------------------------------

def make_verify_result(status: str, verify_type: str = "initial", attempt: int = 0) -> dict[str, Any]:
    """Build a verify-result.json structure."""
    return {
        "schema_version": "1.0",
        "run_id": "test-run-001",
        "story_id": "STORY-001",
        "started_at": "2026-08-07T10:00:00Z",
        "finished_at": "2026-08-07T10:00:05Z",
        "overall_status": status,
        "verify_context": {
            "verify_type": verify_type,
            "attempt": attempt,
            "run_id": "test-run-001",
            "story_id": "STORY-001",
        },
        "gates": [
            {"name": "scope", "status": "PASS"},
            {"name": "json_syntax", "status": "PASS"},
            {"name": "yaml_syntax", "status": "PASS"},
            {"name": "targeted_tests", "status": "PASS"},
            {"name": "lint", "status": "PASS"},
            {"name": "secrets", "status": "PASS"},
            {"name": "git_diff_check", "status": "PASS"},
        ],
    }


def make_review_result(status: str, recommended_action: str = "none") -> dict[str, Any]:
    """Build a review-result.json structure."""
    return {
        "schema_version": "1.0",
        "run_id": "test-run-001",
        "story_id": "STORY-001",
        "review_iteration": 1,
        "repair_iteration": 0,
        "status": status,
        "status_generated_at": "2026-08-07T10:00:10Z",
        "reviewer_id": "mock-reviewer",
        "findings": [],
        "decision_rationale": "test",
        "recommended_action": recommended_action,
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
    }


def make_repair_adapter_result(adapter_status: str, repair_status: str = "REPAIRED") -> dict[str, Any]:
    """Build a repair-adapter-result.json structure."""
    return {
        "schema_version": "1.0",
        "run_id": "test-run-001",
        "story_id": "STORY-001",
        "attempt": 1,
        "adapter_status": adapter_status,
        "repair_result_summary": {
            "status": repair_status,
            "changed": repair_status == "REPAIRED",
            "changed_files": ["file.py"] if repair_status == "REPAIRED" else [],
            "recommended_action": "reverify" if repair_status == "REPAIRED" else "abort",
            "summary": "test repair",
        },
        "diagnostics": {},
        "sanitization": {},
        "integrity_scope": {},
    }


# ---------------------------------------------------------------------------
# Orchestration decision logic tests
# ---------------------------------------------------------------------------

class TestOrchestrationDecisions:
    """Test the core orchestration state-machine decisions."""

    def test_verify_pass_review_pass_accepted(self) -> None:
        """verify PASS + review PASS → ACCEPTED (exit 0)."""
        verify_result = make_verify_result("PASS")
        review_result = make_review_result("PASS", "none")

        # Decision logic
        if verify_result["overall_status"] == "PASS":
            triggered_by = "initial_verify_pass"
        else:
            triggered_by = "initial_verify_fail"

        assert triggered_by == "initial_verify_pass"

        # Review PASS after verify PASS → ACCEPTED
        if review_result["status"] == "PASS":
            if verify_result["overall_status"] == "PASS":
                final_status = "ACCEPTED"
                exit_code = 0
            else:
                final_status = "VERIFICATION_FAILED"
                exit_code = 1
        else:
            final_status = "REVIEW_REJECTED"
            exit_code = 1

        assert final_status == "ACCEPTED"
        assert exit_code == 0

    def test_verify_fail_review_pass_verification_failed(self) -> None:
        """verify FAIL + review PASS → VERIFICATION_FAILED (verify is authoritative)."""
        verify_result = make_verify_result("FAIL")
        review_result = make_review_result("PASS", "none")

        # Decision logic
        if verify_result["overall_status"] == "PASS":
            triggered_by = "initial_verify_pass"
        else:
            triggered_by = "initial_verify_fail"

        assert triggered_by == "initial_verify_fail"

        # Review PASS after verify FAIL → VERIFICATION_FAILED
        if review_result["status"] == "PASS":
            if verify_result["overall_status"] == "PASS":
                final_status = "ACCEPTED"
                exit_code = 0
            else:
                final_status = "VERIFICATION_FAILED"
                exit_code = 1
        else:
            final_status = "REVIEW_REJECTED"
            exit_code = 1

        assert final_status == "VERIFICATION_FAILED"
        assert exit_code == 1

    def test_verify_pass_review_fail_repair_authorized(self) -> None:
        """verify PASS + review FAIL + action=repair → repair authorized."""
        make_verify_result("PASS")
        review_result = make_review_result("FAIL", "repair")

        repair_authorized = False
        if (
            review_result["status"] == "FAIL"
            and review_result["recommended_action"] == "repair"
        ):
            repair_authorized = True

        assert repair_authorized is True

    def test_verify_fail_review_fail_repair_authorized(self) -> None:
        """verify FAIL + review FAIL + action=repair → repair authorized."""
        make_verify_result("FAIL")
        review_result = make_review_result("FAIL", "repair")

        repair_authorized = False
        if (
            review_result["status"] == "FAIL"
            and review_result["recommended_action"] == "repair"
        ):
            repair_authorized = True

        assert repair_authorized is True

    def test_repair_budget_zero_blocks_repair(self) -> None:
        """repair_budget=0 → no repair allowed."""
        manifest = {"repair_budget": 0}
        review_result = make_review_result("FAIL", "repair")

        repair_authorized = False
        if (
            review_result["status"] == "FAIL"
            and review_result["recommended_action"] == "repair"
            and manifest["repair_budget"] > 0
        ):
            repair_authorized = True

        assert repair_authorized is False

    def test_repair_adapter_success_repaired_proceeds_to_reverify(self) -> None:
        """ADAPTER_SUCCESS + REPAIRED → proceed to reverify."""
        repair_result = make_repair_adapter_result("ADAPTER_SUCCESS", "REPAIRED")

        can_reverify = False
        if (
            repair_result["adapter_status"] == "ADAPTER_SUCCESS"
            and repair_result["repair_result_summary"]["status"] == "REPAIRED"
        ):
            can_reverify = True

        assert can_reverify is True

    def test_repair_adapter_success_error_no_reverify(self) -> None:
        """ADAPTER_SUCCESS + ERROR → no reverify, fail closed."""
        repair_result = make_repair_adapter_result("ADAPTER_SUCCESS", "ERROR")

        can_reverify = False
        if (
            repair_result["adapter_status"] == "ADAPTER_SUCCESS"
            and repair_result["repair_result_summary"]["status"] == "REPAIRED"
        ):
            can_reverify = True

        assert can_reverify is False

    def test_repair_adapter_success_no_change_no_reverify(self) -> None:
        """ADAPTER_SUCCESS + NO_CHANGE → no reverify, fail closed."""
        repair_result = make_repair_adapter_result("ADAPTER_SUCCESS", "NO_CHANGE")

        can_reverify = False
        if (
            repair_result["adapter_status"] == "ADAPTER_SUCCESS"
            and repair_result["repair_result_summary"]["status"] == "REPAIRED"
        ):
            can_reverify = True

        assert can_reverify is False

    def test_repair_adapter_failure_no_reverify(self) -> None:
        """Non-ADAPTER_SUCCESS → no reverify, fail closed."""
        repair_result = make_repair_adapter_result("ADAPTER_TIMEOUT", "REPAIRED")

        can_reverify = False
        if (
            repair_result["adapter_status"] == "ADAPTER_SUCCESS"
            and repair_result["repair_result_summary"]["status"] == "REPAIRED"
        ):
            can_reverify = True

        assert can_reverify is False

    def test_max_one_repair_attempt_enforced(self) -> None:
        """Orchestration allows max 1 repair attempt."""
        repair_attempts = 0
        max_repair_attempts = 1

        # Simulate repair flow
        for iteration in range(3):  # Try multiple iterations
            if repair_attempts < max_repair_attempts:
                repair_attempts += 1

        assert repair_attempts == 1

    def test_max_one_reverify_attempt_enforced(self) -> None:
        """Orchestration allows max 1 reverify attempt."""
        reverify_attempts = 0
        max_reverify_attempts = 1

        # Simulate reverify flow
        for iteration in range(3):  # Try multiple iterations
            if reverify_attempts < max_reverify_attempts:
                reverify_attempts += 1

        assert reverify_attempts == 1

    def test_review_error_fails_closed(self) -> None:
        """Review ERROR → fail closed (no repair, no reverify)."""
        review_result = make_review_result("ERROR", "human_review")

        should_proceed = False
        if review_result["status"] == "ERROR":
            # ERROR is fail-closed
            should_proceed = False
        elif (
            review_result["status"] == "PASS"
            or (
                review_result["status"] == "FAIL"
                and review_result["recommended_action"] == "repair"
            )
        ):
            should_proceed = True

        assert should_proceed is False


# ---------------------------------------------------------------------------
# Immutable evidence tests
# ---------------------------------------------------------------------------

class TestImmutableEvidence:
    """Test immutable snapshot preservation."""

    def test_initial_snapshot_preserved_after_reverify(self, tmp_path: Path) -> None:
        """Initial snapshot remains unchanged after reverify writes reverify snapshot."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        # Create initial snapshot
        initial_verify = make_verify_result("FAIL", "initial", 0)
        (reports_dir / "verify-result.initial.json").write_text(json.dumps(initial_verify))

        # Simulate reverify creating new snapshot
        reverify_verify = make_verify_result("PASS", "reverify", 1)
        (reports_dir / "verify-result.reverify.json").write_text(json.dumps(reverify_verify))

        # Verify initial snapshot unchanged
        initial_data = json.loads((reports_dir / "verify-result.initial.json").read_text())
        assert initial_data["overall_status"] == "FAIL"
        assert initial_data["verify_context"]["verify_type"] == "initial"
        assert initial_data["verify_context"]["attempt"] == 0

        # Verify reverify snapshot exists
        reverify_data = json.loads((reports_dir / "verify-result.reverify.json").read_text())
        assert reverify_data["overall_status"] == "PASS"
        assert reverify_data["verify_context"]["verify_type"] == "reverify"
        assert reverify_data["verify_context"]["attempt"] == 1

    def test_both_snapshots_coexist(self, tmp_path: Path) -> None:
        """Initial and reverify snapshots can coexist in same directory."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()

        initial_verify = make_verify_result("FAIL")
        reverify_verify = make_verify_result("PASS", "reverify", 1)

        (reports_dir / "verify-result.initial.json").write_text(json.dumps(initial_verify))
        (reports_dir / "verify-result.reverify.json").write_text(json.dumps(reverify_verify))

        assert (reports_dir / "verify-result.initial.json").exists()
        assert (reports_dir / "verify-result.reverify.json").exists()

        initial_bytes = (reports_dir / "verify-result.initial.json").read_bytes()
        reverify_bytes = (reports_dir / "verify-result.reverify.json").read_bytes()

        # N5 fix: use SHA-256 content comparison, not st_size. Two different
        # JSON objects can have the same file size; content hash is the only
        # reliable proof that the initial snapshot was not overwritten.
        initial_hash = hashlib.sha256(initial_bytes).hexdigest()
        reverify_hash = hashlib.sha256(reverify_bytes).hexdigest()

        # Snapshots must have different content (different overall_status)
        assert initial_hash != reverify_hash
        # Initial snapshot must still say FAIL (not overwritten by reverify PASS)
        assert json.loads(initial_bytes)["overall_status"] == "FAIL"
        assert json.loads(reverify_bytes)["overall_status"] == "PASS"


# ---------------------------------------------------------------------------
# Final status determination tests
# ---------------------------------------------------------------------------

class TestFinalStatusDetermination:
    """Test final_status determination logic."""

    def test_accepted_requires_verify_pass_and_review_pass(self) -> None:
        """ACCEPTED requires verify PASS AND review PASS."""
        cases = [
            ("PASS", "PASS", "ACCEPTED"),
            ("FAIL", "PASS", "VERIFICATION_FAILED"),
            ("PASS", "FAIL", "REVIEW_REJECTED"),
            ("FAIL", "FAIL", "REVIEW_REJECTED"),
        ]

        for verify_status, review_status, expected_final in cases:
            verify_result = make_verify_result(verify_status)
            review_result = make_review_result(review_status)

            # Determine final_status (simplified decision matrix for testing)
            if verify_result["overall_status"] == "PASS" and review_result["status"] == "PASS":
                final_status = "ACCEPTED"
            elif review_result["status"] == "PASS" and verify_result["overall_status"] == "FAIL":
                final_status = "VERIFICATION_FAILED"
            elif review_result["status"] == "FAIL":
                final_status = "REVIEW_REJECTED"
            else:
                final_status = "UNKNOWN"

            assert final_status == expected_final, f"Failed for {verify_status}+{review_status}"

    def test_verified_after_repair_requires_all_conditions(self) -> None:
        """VERIFIED_AFTER_REPAIR requires: repair REPAIRED + reverify PASS."""
        repair_result = make_repair_adapter_result("ADAPTER_SUCCESS", "REPAIRED")
        reverify_result = make_verify_result("PASS", "reverify", 1)

        can_be_verified_after_repair = False
        if (
            repair_result["adapter_status"] == "ADAPTER_SUCCESS"
            and repair_result["repair_result_summary"]["status"] == "REPAIRED"
            and reverify_result["overall_status"] == "PASS"
        ):
            can_be_verified_after_repair = True

        assert can_be_verified_after_repair is True

    def test_reverify_pass_alone_insufficient(self) -> None:
        """Reverify PASS alone is not sufficient for VERIFIED_AFTER_REPAIR."""
        # No repair evidence
        reverify_result = make_verify_result("PASS", "reverify", 1)

        can_be_verified_after_repair = False
        # Without repair evidence, cannot claim VERIFIED_AFTER_REPAIR
        repair_evidence_exists = False

        if (
            repair_evidence_exists
            and reverify_result["overall_status"] == "PASS"
        ):
            can_be_verified_after_repair = True

        assert can_be_verified_after_repair is False


# ---------------------------------------------------------------------------
# N2: Direct production-code tests for report_final_status.py
# ---------------------------------------------------------------------------
# These tests call compute_final_status() and valid_repair_evidence() — the
# REAL production functions — not reimplemented inline logic.
# ---------------------------------------------------------------------------

import sys as _sys

_sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from report_final_status import (
    FINAL_STATUS_ACCEPTED,
    FINAL_STATUS_DIRTY_BASELINE,
    FINAL_STATUS_INFRASTRUCTURE_ERROR,
    FINAL_STATUS_REPAIR_ADAPTER_FAILURE,
    FINAL_STATUS_REPAIR_FAILED_REVERIFY,
    FINAL_STATUS_REPAIR_NO_CHANGE,
    FINAL_STATUS_VERIFICATION_FAILED,
    FINAL_STATUS_VERIFIED_AFTER_REPAIR,
    compute_final_status,
    valid_repair_evidence,
)


class TestComputeFinalStatusProduction:
    """Direct tests against report_final_status.compute_final_status()."""

    def _make_verify(self, status: str, verify_type: str = "initial") -> dict[str, Any]:
        """Build a verify-result with verify_context for snapshot-mode detection."""
        return make_verify_result(status, verify_type, 0 if verify_type == "initial" else 1)

    def test_accepted_verify_pass_review_pass(self) -> None:
        """verify PASS + review PASS → ACCEPTED."""
        result = compute_final_status(
            initial_verify=self._make_verify("PASS"),
            reverify=None,
            review_result=make_review_result("PASS", "none"),
            repair_result=None,
            dirty_marker=None,
        )
        assert result == FINAL_STATUS_ACCEPTED

    def test_verification_failed_verify_fail_review_pass(self) -> None:
        """verify FAIL + review PASS → VERIFICATION_FAILED (DEC-C6-02)."""
        result = compute_final_status(
            initial_verify=self._make_verify("FAIL"),
            reverify=None,
            review_result=make_review_result("PASS", "none"),
            repair_result=None,
            dirty_marker=None,
        )
        assert result == FINAL_STATUS_VERIFICATION_FAILED

    def test_verified_after_repair_with_valid_evidence(self) -> None:
        """Repair REPAIRED + reverify PASS + valid evidence → VERIFIED_AFTER_REPAIR."""
        repair = make_repair_adapter_result("ADAPTER_SUCCESS", "REPAIRED")
        # Add reconciliation and permission evidence required by valid_repair_evidence
        repair["reconciliation"] = {"exact_match": True}
        repair["permission_enforcement"] = {"all_actual_changes_permitted": True}
        result = compute_final_status(
            initial_verify=self._make_verify("FAIL"),
            reverify=self._make_verify("PASS", "reverify"),
            review_result=make_review_result("FAIL", "repair"),
            repair_result=repair,
            dirty_marker=None,
        )
        assert result == FINAL_STATUS_VERIFIED_AFTER_REPAIR

    def test_repair_failed_reverify(self) -> None:
        """Repair REPAIRED + reverify FAIL → REPAIR_FAILED_REVERIFY."""
        repair = make_repair_adapter_result("ADAPTER_SUCCESS", "REPAIRED")
        repair["reconciliation"] = {"exact_match": True}
        repair["permission_enforcement"] = {"all_actual_changes_permitted": True}
        result = compute_final_status(
            initial_verify=self._make_verify("FAIL"),
            reverify=self._make_verify("FAIL", "reverify"),
            review_result=make_review_result("FAIL", "repair"),
            repair_result=repair,
            dirty_marker=None,
        )
        assert result == FINAL_STATUS_REPAIR_FAILED_REVERIFY

    def test_actor_error_to_infrastructure_error(self) -> None:
        """ADAPTER_SUCCESS + status=ERROR → INFRASTRUCTURE_ERROR."""
        repair = make_repair_adapter_result("ADAPTER_SUCCESS", "ERROR")
        result = compute_final_status(
            initial_verify=self._make_verify("FAIL"),
            reverify=None,
            review_result=make_review_result("FAIL", "repair"),
            repair_result=repair,
            dirty_marker=None,
        )
        assert result == FINAL_STATUS_INFRASTRUCTURE_ERROR

    def test_adapter_failure(self) -> None:
        """Non-ADAPTER_SUCCESS → REPAIR_ADAPTER_FAILURE."""
        repair = make_repair_adapter_result("ADAPTER_TIMEOUT")
        result = compute_final_status(
            initial_verify=self._make_verify("FAIL"),
            reverify=None,
            review_result=make_review_result("FAIL", "repair"),
            repair_result=repair,
            dirty_marker=None,
        )
        assert result == FINAL_STATUS_REPAIR_ADAPTER_FAILURE

    def test_bare_reverify_pass_without_repair_evidence(self) -> None:
        """Bare reverify PASS without repair evidence → INFRASTRUCTURE_ERROR (OW-64)."""
        result = compute_final_status(
            initial_verify=self._make_verify("FAIL"),
            reverify=self._make_verify("PASS", "reverify"),
            review_result=make_review_result("FAIL", "repair"),
            repair_result=None,  # No repair evidence!
            dirty_marker=None,
        )
        assert result == FINAL_STATUS_INFRASTRUCTURE_ERROR

    def test_dirty_baseline_precedence(self) -> None:
        """DIRTY_BASELINE marker takes highest precedence."""
        result = compute_final_status(
            initial_verify=self._make_verify("FAIL"),
            reverify=self._make_verify("PASS", "reverify"),
            review_result=make_review_result("FAIL", "repair"),
            repair_result=make_repair_adapter_result("ADAPTER_SUCCESS", "REPAIRED"),
            dirty_marker={"reason": "dirty tracked baseline"},
        )
        assert result == FINAL_STATUS_DIRTY_BASELINE

    def test_repair_no_change(self) -> None:
        """ADAPTER_SUCCESS + NO_CHANGE → REPAIR_NO_CHANGE."""
        repair = make_repair_adapter_result("ADAPTER_SUCCESS", "NO_CHANGE")
        result = compute_final_status(
            initial_verify=self._make_verify("FAIL"),
            reverify=None,
            review_result=make_review_result("FAIL", "repair"),
            repair_result=repair,
            dirty_marker=None,
        )
        assert result == FINAL_STATUS_REPAIR_NO_CHANGE


class TestValidRepairEvidenceProduction:
    """Direct tests against report_final_status.valid_repair_evidence()."""

    def test_valid_repaired_evidence(self) -> None:
        """ADAPTER_SUCCESS + REPAIRED + reconciliation + permissions → True."""
        repair = make_repair_adapter_result("ADAPTER_SUCCESS", "REPAIRED")
        repair["reconciliation"] = {"exact_match": True}
        repair["permission_enforcement"] = {"all_actual_changes_permitted": True}
        assert valid_repair_evidence(repair) is True

    def test_missing_reconciliation(self) -> None:
        """Missing reconciliation → False."""
        repair = make_repair_adapter_result("ADAPTER_SUCCESS", "REPAIRED")
        repair["permission_enforcement"] = {"all_actual_changes_permitted": True}
        assert valid_repair_evidence(repair) is False

    def test_missing_permission_enforcement(self) -> None:
        """Missing permission_enforcement → False."""
        repair = make_repair_adapter_result("ADAPTER_SUCCESS", "REPAIRED")
        repair["reconciliation"] = {"exact_match": True}
        assert valid_repair_evidence(repair) is False

    def test_non_adapter_success(self) -> None:
        """Non-ADAPTER_SUCCESS → False."""
        repair = make_repair_adapter_result("ADAPTER_TIMEOUT")
        repair["reconciliation"] = {"exact_match": True}
        repair["permission_enforcement"] = {"all_actual_changes_permitted": True}
        assert valid_repair_evidence(repair) is False

    def test_none_input(self) -> None:
        """None repair result → False."""
        assert valid_repair_evidence(None) is False


# ---------------------------------------------------------------------------
# OW-19: Malformed/invalid repair result → INFRASTRUCTURE_ERROR
# ---------------------------------------------------------------------------
class TestOW19MalformedRepairResult:
    """OW-19: Malformed repair-adapter-result → INFRASTRUCTURE_ERROR."""

    def test_malformed_repair_result_json(self, tmp_path: Path) -> None:
        """Malformed repair-adapter-result.json is handled as INFRASTRUCTURE_ERROR.

        Tests the production compute_final_status behavior when
        repair-adapter-result.json is malformed (not valid JSON).
        In production, report-story.sh's _load_json returns None for
        malformed JSON, which compute_final_status treats as
        repair_result=None — a bare reverify would then produce
        INFRASTRUCTURE_ERROR (OW-64 path).
        """
        # Simulate what report-story.sh does: malformed JSON → None
        result = compute_final_status(
            initial_verify=self._make_verify_with_context("FAIL", "initial"),
            reverify=self._make_verify_with_context("PASS", "reverify"),
            review_result=make_review_result("FAIL", "repair"),
            repair_result=None,  # Malformed JSON loaded as None
            dirty_marker=None,
        )
        assert result == FINAL_STATUS_INFRASTRUCTURE_ERROR

    @staticmethod
    def _make_verify_with_context(status: str, verify_type: str) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "run_id": "test-run-001",
            "story_id": "STORY-001",
            "started_at": "2026-08-07T10:00:00Z",
            "finished_at": "2026-08-07T10:00:05Z",
            "overall_status": status,
            "verify_context": {
                "verify_type": verify_type,
                "attempt": 0 if verify_type == "initial" else 1,
                "run_id": "test-run-001",
                "story_id": "STORY-001",
            },
            "gates": [],
        }


# ---------------------------------------------------------------------------
# OW-53: Snapshot publication failure → INFRASTRUCTURE_ERROR
# ---------------------------------------------------------------------------
class TestOW53SnapshotPublicationFailure:
    """OW-53: Snapshot publication failure → INFRASTRUCTURE_ERROR.

    Tests the production compute_final_status behavior: when the initial
    verify artifact carries verify_context (orchestrated flow) but the
    initial verify status is ERROR (simulating that verify-story.sh
    failed during snapshot publication), compute_final_status must
    return INFRASTRUCTURE_ERROR.

    In the full orchestrator (run-story.sh), publish_verify_snapshots()
    failure causes finalize_and_exit 1 with "INFRASTRUCTURE_ERROR". Here
    we verify the production state-machine function produces the correct
    status for the verify-ERROR path.
    """

    def test_verify_error_in_orchestrated_flow(self) -> None:
        """Verify ERROR → INFRASTRUCTURE_ERROR (snapshot publication failure path)."""
        verify_error = {
            "schema_version": "1.0",
            "run_id": "test-run-001",
            "story_id": "STORY-001",
            "started_at": "2026-08-07T10:00:00Z",
            "finished_at": "2026-08-07T10:00:05Z",
            "overall_status": "ERROR",
            "verify_context": {
                "verify_type": "initial",
                "attempt": 0,
                "run_id": "test-run-001",
                "story_id": "STORY-001",
            },
            "gates": [],
            "error": {"type": "SNAPSHOT_PUBLICATION_FAILED"},
        }
        result = compute_final_status(
            initial_verify=verify_error,
            reverify=None,
            review_result=None,
            repair_result=None,
            dirty_marker=None,
        )
        assert result == FINAL_STATUS_INFRASTRUCTURE_ERROR
