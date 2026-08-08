"""
WP-AL-1C6: Deterministic final-status computation for report-story.sh.

Single source of truth for the final_status state machine of
docs/planning/wp_al_1c6_orchestration_wiring.md (§5, §8.4, Appendices B/C).

Consumed by:
- report-story.sh (orchestrated runs and direct harness invocations)
- scripts/agent-loop/tests/test_orchestration_wiring.py (OW matrix)

Deterministic, stdlib-only, no network/LLM/shell. All inputs are plain dicts
or None; no filesystem access in compute_final_status().
"""

from __future__ import annotations

from typing import Any

# Final statuses authorized by the merged WP-AL-1C6 plan (§5.1, §11, §12).
FINAL_STATUS_ACCEPTED = "ACCEPTED"
FINAL_STATUS_VERIFIED_AFTER_REPAIR = "VERIFIED_AFTER_REPAIR"
FINAL_STATUS_VERIFICATION_FAILED = "VERIFICATION_FAILED"
FINAL_STATUS_REVIEW_REJECTED = "REVIEW_REJECTED"
FINAL_STATUS_HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"
FINAL_STATUS_INFRASTRUCTURE_ERROR = "INFRASTRUCTURE_ERROR"
FINAL_STATUS_REPAIR_FAILED_REVERIFY = "REPAIR_FAILED_REVERIFY"
FINAL_STATUS_DIRTY_BASELINE = "DIRTY_BASELINE"
FINAL_STATUS_REPAIR_ADAPTER_FAILURE = "REPAIR_ADAPTER_FAILURE"
FINAL_STATUS_REPAIR_NO_CHANGE = "REPAIR_NO_CHANGE"

# Legacy statuses preserved for backward compatibility (AC-46): produced only
# when no WP-AL-1C6 artifacts exist (pre-1C6 flows, review absent).
FINAL_STATUS_VERIFIED = "VERIFIED"
FINAL_STATUS_UNKNOWN = "UNKNOWN"

# Repair adapter status that permits success interpretation (Appendix C).
ADAPTER_SUCCESS = "ADAPTER_SUCCESS"


def _status_of(artifact: dict[str, Any] | None) -> str | None:
    """Extract overall_status from a verify-result artifact."""
    if not isinstance(artifact, dict):
        return None
    value = artifact.get("overall_status")
    return value if isinstance(value, str) else None


def _repair_summary_status(repair_result: dict[str, Any] | None) -> str | None:
    """Extract repair_result_summary.status from a repair-adapter-result."""
    if not isinstance(repair_result, dict):
        return None
    summary = repair_result.get("repair_result_summary")
    if not isinstance(summary, dict):
        return None
    value = summary.get("status")
    return value if isinstance(value, str) else None


def valid_repair_evidence(repair_result: dict[str, Any] | None) -> bool:
    """
    All adapter-success evidence required for VERIFIED_AFTER_REPAIR (§5.1).

    Requires ALL of:
    - adapter_status == ADAPTER_SUCCESS
    - repair_result_summary.status == REPAIRED
    - reconciliation.exact_match is True
    - permission_enforcement.all_actual_changes_permitted is True

    reconciliation / permission_enforcement are guaranteed by the adapter when
    adapter_status == ADAPTER_SUCCESS (§10.5); re-validated here so a bare or
    forged reverify can never produce VERIFIED_AFTER_REPAIR (OW-64..OW-66).
    """
    if not isinstance(repair_result, dict):
        return False
    if repair_result.get("adapter_status") != ADAPTER_SUCCESS:
        return False
    if _repair_summary_status(repair_result) != "REPAIRED":
        return False
    reconciliation = repair_result.get("reconciliation")
    if (
        not isinstance(reconciliation, dict)
        or reconciliation.get("exact_match") is not True
    ):
        return False
    permissions = repair_result.get("permission_enforcement")
    return isinstance(permissions, dict) and permissions.get("all_actual_changes_permitted") is True


def compute_final_status(
    initial_verify: dict[str, Any] | None,
    reverify: dict[str, Any] | None,
    review_result: dict[str, Any] | None,
    repair_result: dict[str, Any] | None,
    dirty_marker: dict[str, Any] | None,
    review_category: str | None = None,
    review_category_final_status: str | None = None,
    legacy_repair_iterations: int = 0,
) -> str:
    """
    Compute final_status from loaded artifacts.

    Precedence (highest first), per the merged plan:

    1. DIRTY_BASELINE marker present → DIRTY_BASELINE (orchestrator wrote it
       when the pre-repair baseline check failed; repair never invoked).
    2. Reverify snapshot present → repair path outcome; VERIFIED_AFTER_REPAIR
       additionally requires valid repair adapter evidence (OW-64).
    3. Repair adapter result present without reverify → fail-closed repair
       outcome (REPAIR_ADAPTER_FAILURE / REPAIR_NO_CHANGE /
       INFRASTRUCTURE_ERROR).
    4. Initial-verify-only paths:
       a. WP-AL-1C6 immutable initial snapshot present → DEC-C6-02 matrix
          (verify FAIL is authoritative over review PASS).
       b. No snapshot (legacy direct report-story.sh invocation) → preserve
          pre-1C6 behavior via the WP-AL-1C3 review classification.
    """
    # --- 1. Dirty baseline (DEC-C6-04) ---
    if isinstance(dirty_marker, dict):
        return FINAL_STATUS_DIRTY_BASELINE

    # --- 2. Reverify present → repair path ---
    if isinstance(reverify, dict):
        if not valid_repair_evidence(repair_result):
            # Bare reverify (or invalid/forged repair evidence) must never
            # produce VERIFIED_AFTER_REPAIR (OW-64/65/66, scenario AN).
            return FINAL_STATUS_INFRASTRUCTURE_ERROR
        reverify_status = _status_of(reverify)
        if reverify_status == "PASS":
            return FINAL_STATUS_VERIFIED_AFTER_REPAIR
        if reverify_status == "ERROR":
            return FINAL_STATUS_INFRASTRUCTURE_ERROR
        # FAIL or any unexpected value → fail closed
        return FINAL_STATUS_REPAIR_FAILED_REVERIFY

    # --- 3. Repair attempted, no reverify ---
    if isinstance(repair_result, dict):
        adapter_status = repair_result.get("adapter_status")
        if adapter_status != ADAPTER_SUCCESS:
            return FINAL_STATUS_REPAIR_ADAPTER_FAILURE
        summary_status = _repair_summary_status(repair_result)
        if summary_status == "NO_CHANGE":
            return FINAL_STATUS_REPAIR_NO_CHANGE
        if summary_status == "ERROR":
            # Actor returned valid status=ERROR; adapter published it
            # (scenario AD). Fail closed, no reverify.
            return FINAL_STATUS_INFRASTRUCTURE_ERROR
        # ADAPTER_SUCCESS + REPAIRED without a reverify snapshot is an
        # orchestration invariant violation → fail closed.
        return FINAL_STATUS_INFRASTRUCTURE_ERROR

    # --- 4. Initial-verify-only paths ---
    initial_status = _status_of(initial_verify)

    if isinstance(initial_verify, dict) and initial_status == "ERROR":
        return FINAL_STATUS_INFRASTRUCTURE_ERROR

    # 4a. WP-AL-1C6 orchestrated flow (immutable snapshot present):
    # DEC-C6-02 authoritative matrix.
    snapshot_present = initial_verify is not None and _snapshot_mode_enabled(
        initial_verify
    )
    if snapshot_present:
        return _dec_c6_02_matrix(initial_status, review_result)

    # 4b. Legacy path (no snapshot): preserve pre-WP-AL-1C6 report-story.sh
    # behavior exactly (AC-46), driven by the WP-AL-1C3 classification.
    return _legacy_final_status(
        initial_verify,
        review_result,
        review_category,
        review_category_final_status,
        legacy_repair_iterations,
    )


def _snapshot_mode_enabled(initial_verify: dict[str, Any]) -> bool:
    """
    True when the initial verify artifact carries the WP-AL-1C6 verify_context
    (written by run-story.sh before each verify invocation). Direct legacy
    verify runs have no verify-context file and therefore no verify_context
    field, which keeps their report behavior unchanged.
    """
    return isinstance(initial_verify.get("verify_context"), dict)


def _dec_c6_02_matrix(
    initial_status: str | None, review_result: dict[str, Any] | None
) -> str:
    """DEC-C6-02 / Appendix B outcome matrix for orchestrated flows."""
    review_status = None
    recommended_action = None
    if isinstance(review_result, dict):
        raw_status = review_result.get("status")
        if isinstance(raw_status, str):
            review_status = raw_status
        raw_action = review_result.get("recommended_action")
        if isinstance(raw_action, str):
            recommended_action = raw_action

    if initial_status == "PASS":
        if review_status == "PASS":
            return FINAL_STATUS_ACCEPTED
        if review_status == "FAIL":
            if recommended_action == "human_review":
                return FINAL_STATUS_HUMAN_REVIEW_REQUIRED
            # action=repair without repair artifacts is an orchestration
            # invariant violation; action=none rejects. Both fail closed.
            if recommended_action == "repair":
                return FINAL_STATUS_INFRASTRUCTURE_ERROR
            return FINAL_STATUS_REVIEW_REJECTED
        if review_status == "ERROR":
            if recommended_action == "human_review":
                return FINAL_STATUS_HUMAN_REVIEW_REQUIRED
            return FINAL_STATUS_INFRASTRUCTURE_ERROR
        # Missing or malformed review result in an orchestrated flow
        return FINAL_STATUS_INFRASTRUCTURE_ERROR

    if initial_status == "FAIL":
        if review_status == "PASS":
            # Reviewer cannot override failed verification (DEC-C6-02)
            return FINAL_STATUS_VERIFICATION_FAILED
        if review_status == "FAIL":
            if recommended_action == "human_review":
                return FINAL_STATUS_HUMAN_REVIEW_REQUIRED
            if recommended_action == "repair":
                return FINAL_STATUS_INFRASTRUCTURE_ERROR
            return FINAL_STATUS_VERIFICATION_FAILED
        if review_status == "ERROR":
            if recommended_action == "human_review":
                return FINAL_STATUS_HUMAN_REVIEW_REQUIRED
            return FINAL_STATUS_INFRASTRUCTURE_ERROR
        return FINAL_STATUS_INFRASTRUCTURE_ERROR

    # Unparseable/absent initial verify in an orchestrated flow
    return FINAL_STATUS_INFRASTRUCTURE_ERROR


def _legacy_final_status(
    initial_verify: dict[str, Any] | None,
    review_result: dict[str, Any] | None,
    review_category: str | None,
    review_category_final_status: str | None,
    legacy_repair_iterations: int,
) -> str:
    """
    Pre-WP-AL-1C6 report-story.sh behavior (AC-46 regression guard).

    Mirrors the original aggregation:
    - verify PASS → WP-AL-1C3 classification final_status
    - verify FAIL → REPAIR_EXHAUSTED if repair iterations exist, else
      VERIFICATION_FAILED
    - verify ERROR → INFRASTRUCTURE_ERROR
    - no verify result → UNKNOWN
    """
    if initial_verify is None:
        return FINAL_STATUS_UNKNOWN
    status = _status_of(initial_verify)
    if status == "PASS":
        if review_category == "ABSENT" or review_category is None:
            return review_category_final_status or FINAL_STATUS_VERIFIED
        return review_category_final_status or FINAL_STATUS_UNKNOWN
    if status == "FAIL":
        if legacy_repair_iterations > 0:
            return "REPAIR_EXHAUSTED"
        return FINAL_STATUS_VERIFICATION_FAILED
    if status == "ERROR":
        return FINAL_STATUS_INFRASTRUCTURE_ERROR
    return FINAL_STATUS_UNKNOWN
