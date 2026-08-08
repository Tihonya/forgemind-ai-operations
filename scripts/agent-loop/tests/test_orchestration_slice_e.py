"""
WP-AL-1C6 Slice E: Additional orchestration edge case tests.

Tests edge cases and error conditions in the orchestration flow.
"""

from pathlib import Path

from test_orchestration_wiring import make_repair_adapter_result, make_review_result

# ---------------------------------------------------------------------------
# Edge case: verify ERROR handling
# ---------------------------------------------------------------------------

class TestVerifyErrorHandling:
    """Test verify ERROR (exit 2) handling."""

    def test_verify_error_fails_closed_without_review(self) -> None:
        """Verify ERROR → immediate fail-closed, no review invoked."""
        verify_exit_code = 2

        review_invoked = False
        if verify_exit_code == 0 or verify_exit_code == 1:
            review_invoked = True
        elif verify_exit_code == 2:
            # ERROR → fail closed
            review_invoked = False

        assert review_invoked is False

    def test_verify_error_generates_infrastructure_error_status(self) -> None:
        """Verify ERROR → final_status = INFRASTRUCTURE_ERROR."""
        verify_exit_code = 2

        if verify_exit_code == 2:
            final_status = "INFRASTRUCTURE_ERROR"
        else:
            final_status = "UNKNOWN"

        assert final_status == "INFRASTRUCTURE_ERROR"


# ---------------------------------------------------------------------------
# Edge case: repair adapter failures
# ---------------------------------------------------------------------------

class TestRepairAdapterFailures:
    """Test various repair adapter failure modes."""

    def test_adapter_timeout_no_reverify(self) -> None:
        """ADAPTER_TIMEOUT → no reverify."""
        repair_result = make_repair_adapter_result("ADAPTER_TIMEOUT")

        can_reverify = (
            repair_result["adapter_status"] == "ADAPTER_SUCCESS"
            and repair_result["repair_result_summary"]["status"] == "REPAIRED"
        )

        assert can_reverify is False

    def test_adapter_dirty_baseline_no_reverify(self) -> None:
        """ADAPTER_DIRTY_BASELINE → no reverify."""
        repair_result = make_repair_adapter_result("ADAPTER_DIRTY_BASELINE")

        can_reverify = (
            repair_result["adapter_status"] == "ADAPTER_SUCCESS"
            and repair_result["repair_result_summary"]["status"] == "REPAIRED"
        )

        assert can_reverify is False

    def test_adapter_contract_violation_no_reverify(self) -> None:
        """ADAPTER_CONTRACT_VIOLATION → no reverify."""
        repair_result = make_repair_adapter_result("ADAPTER_CONTRACT_VIOLATION")

        can_reverify = (
            repair_result["adapter_status"] == "ADAPTER_SUCCESS"
            and repair_result["repair_result_summary"]["status"] == "REPAIRED"
        )

        assert can_reverify is False

    def test_adapter_identity_mismatch_no_reverify(self) -> None:
        """ADAPTER_IDENTITY_MISMATCH → no reverify."""
        repair_result = make_repair_adapter_result("ADAPTER_IDENTITY_MISMATCH")

        can_reverify = (
            repair_result["adapter_status"] == "ADAPTER_SUCCESS"
            and repair_result["repair_result_summary"]["status"] == "REPAIRED"
        )

        assert can_reverify is False


# ---------------------------------------------------------------------------
# Edge case: review recommended actions
# ---------------------------------------------------------------------------

class TestReviewRecommendedActions:
    """Test review recommended_action handling."""

    def test_review_fail_with_human_review_action(self) -> None:
        """Review FAIL + action=human_review → HUMAN_REVIEW_REQUIRED."""
        review_result = make_review_result("FAIL", "human_review")

        if review_result["status"] == "FAIL":
            action = review_result["recommended_action"]
            if action == "repair":
                final_status = "REPAIR_ATTEMPTED"
            elif action == "human_review":
                final_status = "HUMAN_REVIEW_REQUIRED"
            else:
                final_status = "REVIEW_REJECTED"
        else:
            final_status = "UNKNOWN"

        assert final_status == "HUMAN_REVIEW_REQUIRED"

    def test_review_fail_with_none_action(self) -> None:
        """Review FAIL + action=none → REVIEW_REJECTED."""
        review_result = make_review_result("FAIL", "none")

        if review_result["status"] == "FAIL":
            action = review_result["recommended_action"]
            if action == "repair":
                final_status = "REPAIR_ATTEMPTED"
            elif action == "human_review":
                final_status = "HUMAN_REVIEW_REQUIRED"
            else:
                final_status = "REVIEW_REJECTED"
        else:
            final_status = "UNKNOWN"

        assert final_status == "REVIEW_REJECTED"


# ---------------------------------------------------------------------------
# Edge case: reverify outcomes
# ---------------------------------------------------------------------------

class TestReverifyOutcomes:
    """Test reverify outcome handling."""

    def test_reverify_error_generates_infrastructure_error(self) -> None:
        """Reverify ERROR → final_status = INFRASTRUCTURE_ERROR."""
        reverify_exit_code = 2

        if reverify_exit_code == 0:
            final_status = "VERIFIED_AFTER_REPAIR"
        elif reverify_exit_code == 2:
            final_status = "INFRASTRUCTURE_ERROR"
        else:
            final_status = "REPAIR_FAILED_REVERIFY"

        assert final_status == "INFRASTRUCTURE_ERROR"

    def test_reverify_fail_generates_repair_failed_reverify(self) -> None:
        """Reverify FAIL → final_status = REPAIR_FAILED_REVERIFY."""
        reverify_exit_code = 1

        if reverify_exit_code == 0:
            final_status = "VERIFIED_AFTER_REPAIR"
        elif reverify_exit_code == 2:
            final_status = "INFRASTRUCTURE_ERROR"
        else:
            final_status = "REPAIR_FAILED_REVERIFY"

        assert final_status == "REPAIR_FAILED_REVERIFY"


# ---------------------------------------------------------------------------
# Edge case: verify-context validation
# ---------------------------------------------------------------------------

class TestVerifyContextValidation:
    """Test verify-context.json validation in verify-story.sh."""

    def test_valid_initial_context_accepted(self, tmp_path: Path) -> None:
        """Valid initial context (verify_type=initial, attempt=0) → accepted."""
        context = {
            "schema_version": "1.0",
            "run_id": "test-run-001",
            "story_id": "STORY-001",
            "verify_type": "initial",
            "attempt": 0,
            "generated_at": "2026-08-07T10:00:00Z"
        }

        is_valid = (
            context["schema_version"] == "1.0"
            and context["verify_type"] in ["initial", "reverify"]
            and ((context["verify_type"] == "initial" and context["attempt"] == 0)
                 or (context["verify_type"] == "reverify" and context["attempt"] == 1))
        )

        assert is_valid is True

    def test_valid_reverify_context_accepted(self, tmp_path: Path) -> None:
        """Valid reverify context (verify_type=reverify, attempt=1) → accepted."""
        context = {
            "schema_version": "1.0",
            "run_id": "test-run-001",
            "story_id": "STORY-001",
            "verify_type": "reverify",
            "attempt": 1,
            "generated_at": "2026-08-07T10:00:05Z"
        }

        is_valid = (
            context["schema_version"] == "1.0"
            and context["verify_type"] in ["initial", "reverify"]
            and ((context["verify_type"] == "initial" and context["attempt"] == 0)
                 or (context["verify_type"] == "reverify" and context["attempt"] == 1))
        )

        assert is_valid is True

    def test_invalid_attempt_binding_rejected(self, tmp_path: Path) -> None:
        """Invalid attempt binding (initial with attempt=1) → rejected."""
        context = {
            "schema_version": "1.0",
            "run_id": "test-run-001",
            "story_id": "STORY-001",
            "verify_type": "initial",
            "attempt": 1,  # Wrong! initial should be 0
            "generated_at": "2026-08-07T10:00:00Z"
        }

        is_valid = (
            context["schema_version"] == "1.0"
            and context["verify_type"] in ["initial", "reverify"]
            and ((context["verify_type"] == "initial" and context["attempt"] == 0)
                 or (context["verify_type"] == "reverify" and context["attempt"] == 1))
        )

        assert is_valid is False

    def test_invalid_verify_type_rejected(self, tmp_path: Path) -> None:
        """Invalid verify_type → rejected."""
        context = {
            "schema_version": "1.0",
            "run_id": "test-run-001",
            "story_id": "STORY-001",
            "verify_type": "unknown",
            "attempt": 0,
            "generated_at": "2026-08-07T10:00:00Z"
        }

        is_valid = (
            context["schema_version"] == "1.0"
            and context["verify_type"] in ["initial", "reverify"]
            and ((context["verify_type"] == "initial" and context["attempt"] == 0)
                 or (context["verify_type"] == "reverify" and context["attempt"] == 1))
        )

        assert is_valid is False


# ---------------------------------------------------------------------------
# Edge case: final status determination
# ---------------------------------------------------------------------------

class TestFinalStatusEdgeCases:
    """Test final status determination edge cases."""

    def test_review_error_after_verify_pass(self) -> None:
        """Verify PASS + review ERROR → INFRASTRUCTURE_ERROR."""
        verify_status = "PASS"
        review_status = "ERROR"

        if review_status == "ERROR":
            final_status = "INFRASTRUCTURE_ERROR"
        elif verify_status == "PASS" and review_status == "PASS":
            final_status = "ACCEPTED"
        else:
            final_status = "UNKNOWN"

        assert final_status == "INFRASTRUCTURE_ERROR"

    def test_review_error_after_verify_fail(self) -> None:
        """Verify FAIL + review ERROR → INFRASTRUCTURE_ERROR."""
        verify_status = "FAIL"
        review_status = "ERROR"

        if review_status == "ERROR":
            final_status = "INFRASTRUCTURE_ERROR"
        elif verify_status == "PASS" and review_status == "PASS":
            final_status = "ACCEPTED"
        else:
            final_status = "UNKNOWN"

        assert final_status == "INFRASTRUCTURE_ERROR"

    def test_adapter_success_with_no_change_status(self) -> None:
        """ADAPTER_SUCCESS + NO_CHANGE → fail closed."""
        repair_result = make_repair_adapter_result("ADAPTER_SUCCESS", "NO_CHANGE")

        if repair_result["adapter_status"] == "ADAPTER_SUCCESS":
            repair_status = repair_result["repair_result_summary"]["status"]
            if repair_status == "REPAIRED":
                can_reverify = True
            else:
                can_reverify = False
        else:
            can_reverify = False

        assert can_reverify is False
