"""
WP-AL-1C5 Slice 1: Repair adapter contract and model tests.

Tests cover:
  A: Top-level structure (field count, required, unknown-field, type, bool-as-int)
  B: AdapterStatus enum (14 values, closed)
  C: Presence rules (SUCCESS, pre-invocation, post-invocation)
  D: repair_result_summary invariants (REPAIRED/NO_CHANGE/ERROR cross-field)
  E: workspace_changes invariants
  F: reconciliation invariants
  G: permission_enforcement invariants
  H: integrity_scope constants
  I: diagnostics bounds (1024-byte adapter_error_message)
  J: path lexical safety + duplicate rejection
  K: canonical/pretty serialization determinism
  L: builder determinism + immutability
  M: schema/code/test parity
  N: multibyte UTF-8 byte-boundary tests (byte counting, not character counting)
  O: missing-versus-explicit-null conditional-field behavior
  P: dedicated presence tests for all 14 AdapterStatus values

No skips, no xfails, no placeholders.
"""

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from repair_adapter import (
    ADAPTER_CONTRACT_VIOLATION,
    ADAPTER_DECLARED_MISSING,
    ADAPTER_DIRTY_BASELINE,
    ADAPTER_FORBIDDEN_CHANGE,
    ADAPTER_IDENTITY_MISMATCH,
    ADAPTER_INTERNAL_ERROR,
    ADAPTER_MALFORMED_RESULT,
    ADAPTER_MISSING_RESULT,
    ADAPTER_NON_ZERO_EXIT,
    ADAPTER_OUTPUT_SIZE_EXCEEDED,
    ADAPTER_SOURCE_REVISION_DRIFT,
    ADAPTER_SUCCESS,
    ADAPTER_TIMEOUT,
    ADAPTER_UNDECLARED_CHANGE,
    ALL_TOP_LEVEL_FIELDS,
    MAX_ADAPTER_ERROR_MESSAGE_BYTES,
    MAX_CHANGED_FILES,
    MAX_PATH_BYTES,
    MAX_STDERR_TAIL_BYTES,
    MAX_STDOUT_TAIL_BYTES,
    MAX_SUMMARY_BYTES,
    MAX_TRUNCATED_FIELDS,
    VALID_ADAPTER_STATUSES,
    ReconciliationResult,
    RepairAdapterContractError,
    RepairAdapterResult,
    WorkspaceBaseline,
    WorkspaceChange,
    build_adapter_result,
    canonical_json_bytes,
    pretty_json_string,
    validate_adapter_result,
)

# ---------------------------------------------------------------------------
# Shared constants and helpers
# ---------------------------------------------------------------------------
VALID_SHA40 = "a" * 40
VALID_TIMESTAMP = "2026-08-06T12:00:00Z"
VALID_RUN_ID = "run-001"
VALID_STORY_ID = "story-001"


def _make_diagnostics(**overrides: Any) -> dict[str, Any]:
    diag: dict[str, Any] = {
        "actor_exit_code": 0,
        "actor_stdout_tail": "stdout output",
        "actor_stderr_tail": "stderr output",
        "adapter_error_message": None,
    }
    diag.update(overrides)
    return diag


def _make_sanitization(**overrides: Any) -> dict[str, Any]:
    san: dict[str, Any] = {
        "redaction_applied": False,
        "redaction_count": 0,
        "truncation_applied": False,
        "truncated_fields": [],
    }
    san.update(overrides)
    return san


def _make_integrity_scope(**overrides: Any) -> dict[str, Any]:
    scope: dict[str, Any] = {
        "tracked_files_inspected": True,
        "untracked_non_ignored_inspected": True,
        "ignored_files_inspected": False,
        "advanced_symlink_inspected": False,
        "note": "WP-AL-1C5 scope limitations",
    }
    scope.update(overrides)
    return scope


def _make_repair_result_summary(
    *,
    status: str = "REPAIRED",
    changed: bool = True,
    changed_files: list[str] | None = None,
    recommended_action: str = "reverify",
    summary: str = "Fixed the issue",
) -> dict[str, Any]:
    return {
        "status": status,
        "changed": changed,
        "changed_files": changed_files if changed_files is not None else ["backend/test.py"],
        "recommended_action": recommended_action,
        "summary": summary,
    }


def _make_workspace_changes(**overrides: Any) -> dict[str, Any]:
    wc: dict[str, Any] = {
        "baseline_source_revision": VALID_SHA40,
        "post_source_revision": VALID_SHA40,
        "source_revision_stable": True,
        "added": [],
        "modified": ["backend/test.py"],
        "deleted": [],
        "untracked": [],
    }
    wc.update(overrides)
    return wc


def _make_reconciliation(**overrides: Any) -> dict[str, Any]:
    recon: dict[str, Any] = {
        "declared_files": ["backend/test.py"],
        "actual_files": ["backend/test.py"],
        "undeclared_changes": [],
        "declared_but_missing": [],
        "exact_match": True,
    }
    recon.update(overrides)
    return recon


def _make_permission_enforcement(**overrides: Any) -> dict[str, Any]:
    perm: dict[str, Any] = {
        "allowed_violations": [],
        "forbidden_violations": [],
        "all_actual_changes_permitted": True,
    }
    perm.update(overrides)
    return perm


def _make_success_result(**overrides: Any) -> dict[str, Any]:
    """Build a minimal valid ADAPTER_SUCCESS result."""
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": VALID_RUN_ID,
        "story_id": VALID_STORY_ID,
        "attempt": 1,
        "adapter_status": ADAPTER_SUCCESS,
        "repair_result_summary": _make_repair_result_summary(),
        "workspace_changes": _make_workspace_changes(),
        "reconciliation": _make_reconciliation(),
        "permission_enforcement": _make_permission_enforcement(),
        "diagnostics": _make_diagnostics(),
        "sanitization": _make_sanitization(),
        "integrity_scope": _make_integrity_scope(),
        "completed_at": VALID_TIMESTAMP,
    }
    result.update(overrides)
    return result


def _make_pre_invocation_result(
    status: str = ADAPTER_DIRTY_BASELINE,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a minimal valid pre-invocation failure result."""
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": VALID_RUN_ID,
        "story_id": VALID_STORY_ID,
        "attempt": 1,
        "adapter_status": status,
        "diagnostics": _make_diagnostics(
            actor_exit_code=None,
            actor_stdout_tail="",
            actor_stderr_tail="",
            adapter_error_message="Dirty baseline",
        ),
        "sanitization": _make_sanitization(),
        "integrity_scope": _make_integrity_scope(),
        "completed_at": VALID_TIMESTAMP,
    }
    result.update(overrides)
    return result


def _make_post_invocation_result(
    status: str = ADAPTER_TIMEOUT,
    **overrides: Any,
) -> dict[str, Any]:
    """Build a minimal valid post-invocation failure result (no valid actor result)."""
    result: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": VALID_RUN_ID,
        "story_id": VALID_STORY_ID,
        "attempt": 1,
        "adapter_status": status,
        "diagnostics": _make_diagnostics(
            actor_exit_code=None,
            actor_stdout_tail="",
            actor_stderr_tail="",
            adapter_error_message="Timeout",
        ),
        "sanitization": _make_sanitization(),
        "integrity_scope": _make_integrity_scope(),
        "completed_at": VALID_TIMESTAMP,
    }
    result.update(overrides)
    return result


# ===========================================================================
# A: Top-level structure
# ===========================================================================

def test_A01_exactly_13_top_level_fields() -> None:
    """A01: Adapter result has exactly 13 top-level fields."""
    result = _make_success_result()
    assert len(result) == 13
    assert len(ALL_TOP_LEVEL_FIELDS) == 13


def test_A02_required_fields_present() -> None:
    """A02: All always-required fields are present in valid result."""
    result = _make_success_result()
    validate_adapter_result(result)  # must not raise


def test_A03_missing_required_field_rejected() -> None:
    """A03: Missing schema_version is rejected."""
    result = _make_success_result()
    del result["schema_version"]
    with pytest.raises(RepairAdapterContractError, match="missing required field"):
        validate_adapter_result(result)


def test_A04_missing_completed_at_rejected() -> None:
    """A04: Missing completed_at is rejected."""
    result = _make_success_result()
    del result["completed_at"]
    with pytest.raises(RepairAdapterContractError, match="missing required field"):
        validate_adapter_result(result)


def test_A05_unknown_field_rejected() -> None:
    """A05: Unknown top-level field is rejected (closed schema)."""
    result = _make_success_result()
    result["unexpected_field"] = "value"
    with pytest.raises(RepairAdapterContractError, match="unknown field"):
        validate_adapter_result(result)


def test_A06_wrong_schema_version_rejected() -> None:
    """A06: schema_version != '1.0' is rejected."""
    result = _make_success_result()
    result["schema_version"] = "2.0"
    with pytest.raises(RepairAdapterContractError, match="schema_version"):
        validate_adapter_result(result)


def test_A07_run_id_type_rejected() -> None:
    """A07: run_id as non-string is rejected."""
    result = _make_success_result()
    result["run_id"] = 123
    with pytest.raises(RepairAdapterContractError, match="run_id"):
        validate_adapter_result(result)


def test_A08_run_id_empty_rejected() -> None:
    """A08: Empty run_id is rejected."""
    result = _make_success_result()
    result["run_id"] = ""
    with pytest.raises(RepairAdapterContractError, match="run_id"):
        validate_adapter_result(result)


def test_A09_run_id_invalid_chars_rejected() -> None:
    """A09: run_id with invalid characters is rejected."""
    result = _make_success_result()
    result["run_id"] = "run@123"
    with pytest.raises(RepairAdapterContractError, match="run_id"):
        validate_adapter_result(result)


def test_A10_story_id_invalid_chars_rejected() -> None:
    """A10: story_id with invalid characters is rejected."""
    result = _make_success_result()
    result["story_id"] = "story:456"
    with pytest.raises(RepairAdapterContractError, match="story_id"):
        validate_adapter_result(result)


def test_A11_attempt_string_rejected() -> None:
    """A11: attempt as string is rejected."""
    result = _make_success_result()
    result["attempt"] = "1"
    with pytest.raises(RepairAdapterContractError, match="attempt"):
        validate_adapter_result(result)


def test_A12_attempt_bool_rejected() -> None:
    """A12: attempt as bool is rejected (bool is not int)."""
    result = _make_success_result()
    result["attempt"] = True
    with pytest.raises(RepairAdapterContractError, match="attempt"):
        validate_adapter_result(result)


def test_A13_attempt_zero_rejected() -> None:
    """A13: attempt < 1 is rejected."""
    result = _make_success_result()
    result["attempt"] = 0
    with pytest.raises(RepairAdapterContractError, match="attempt"):
        validate_adapter_result(result)


def test_A14_invalid_adapter_status_rejected() -> None:
    """A14: Invalid adapter_status is rejected."""
    result = _make_success_result()
    result["adapter_status"] = "ADAPTER_PARTIAL"
    with pytest.raises(RepairAdapterContractError, match="adapter_status"):
        validate_adapter_result(result)


def test_A15_invalid_timestamp_rejected() -> None:
    """A15: Invalid completed_at format is rejected."""
    result = _make_success_result()
    result["completed_at"] = "2026-08-06 12:00:00"
    with pytest.raises(RepairAdapterContractError, match="completed_at"):
        validate_adapter_result(result)


def test_A16_timestamp_with_fractional_seconds_accepted() -> None:
    """A16: ISO-8601 with fractional seconds is accepted."""
    result = _make_success_result()
    result["completed_at"] = "2026-08-06T12:00:00.123Z"
    validate_adapter_result(result)  # must not raise


def test_A17_result_not_dict_rejected() -> None:
    """A17: Non-dict result is rejected."""
    with pytest.raises(RepairAdapterContractError, match="must be object"):
        validate_adapter_result("not a dict")  # type: ignore[arg-type]


# ===========================================================================
# B: AdapterStatus enum
# ===========================================================================

def test_B01_exactly_14_adapter_statuses() -> None:
    """B01: VALID_ADAPTER_STATUSES has exactly 14 values."""
    assert len(VALID_ADAPTER_STATUSES) == 14


def test_B02_all_statuses_explicitly_listed() -> None:
    """B02: All 14 AdapterStatus values are present."""
    expected = {
        "ADAPTER_SUCCESS",
        "ADAPTER_DIRTY_BASELINE",
        "ADAPTER_TIMEOUT",
        "ADAPTER_NON_ZERO_EXIT",
        "ADAPTER_MISSING_RESULT",
        "ADAPTER_MALFORMED_RESULT",
        "ADAPTER_CONTRACT_VIOLATION",
        "ADAPTER_IDENTITY_MISMATCH",
        "ADAPTER_SOURCE_REVISION_DRIFT",
        "ADAPTER_FORBIDDEN_CHANGE",
        "ADAPTER_UNDECLARED_CHANGE",
        "ADAPTER_DECLARED_MISSING",
        "ADAPTER_OUTPUT_SIZE_EXCEEDED",
        "ADAPTER_INTERNAL_ERROR",
    }
    assert set(VALID_ADAPTER_STATUSES) == expected


def test_B03_success_status_accepted() -> None:
    """B03: ADAPTER_SUCCESS is accepted."""
    result = _make_success_result()
    validate_adapter_result(result)


def test_B04_dirty_baseline_accepted() -> None:
    """B04: ADAPTER_DIRTY_BASELINE is accepted."""
    result = _make_pre_invocation_result(ADAPTER_DIRTY_BASELINE)
    validate_adapter_result(result)


def test_B05_timeout_accepted() -> None:
    """B05: ADAPTER_TIMEOUT is accepted."""
    result = _make_post_invocation_result(ADAPTER_TIMEOUT)
    validate_adapter_result(result)


def test_B06_internal_error_accepted() -> None:
    """B06: ADAPTER_INTERNAL_ERROR is accepted."""
    result = _make_pre_invocation_result(ADAPTER_INTERNAL_ERROR)
    validate_adapter_result(result)


# ===========================================================================
# C: Presence rules
# ===========================================================================

def test_C01_success_requires_all_conditional_fields() -> None:
    """C01: ADAPTER_SUCCESS requires all 4 conditional fields."""
    result = _make_success_result()
    del result["repair_result_summary"]
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        validate_adapter_result(result)


def test_C02_success_requires_workspace_changes() -> None:
    """C02: ADAPTER_SUCCESS requires workspace_changes."""
    result = _make_success_result()
    del result["workspace_changes"]
    with pytest.raises(RepairAdapterContractError, match="workspace_changes"):
        validate_adapter_result(result)


def test_C03_success_requires_reconciliation() -> None:
    """C03: ADAPTER_SUCCESS requires reconciliation."""
    result = _make_success_result()
    del result["reconciliation"]
    with pytest.raises(RepairAdapterContractError, match="reconciliation"):
        validate_adapter_result(result)


def test_C04_success_requires_permission_enforcement() -> None:
    """C04: ADAPTER_SUCCESS requires permission_enforcement."""
    result = _make_success_result()
    del result["permission_enforcement"]
    with pytest.raises(RepairAdapterContractError, match="permission_enforcement"):
        validate_adapter_result(result)


def test_C05_pre_invocation_no_repair_summary() -> None:
    """C05: Pre-invocation failure must not have repair_result_summary."""
    result = _make_pre_invocation_result()
    result["repair_result_summary"] = _make_repair_result_summary()
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        validate_adapter_result(result)


def test_C06_pre_invocation_no_workspace_changes() -> None:
    """C06: Pre-invocation failure must not have workspace_changes."""
    result = _make_pre_invocation_result()
    result["workspace_changes"] = _make_workspace_changes()
    with pytest.raises(RepairAdapterContractError, match="workspace_changes"):
        validate_adapter_result(result)


def test_C07_pre_invocation_no_reconciliation() -> None:
    """C07: Pre-invocation failure must not have reconciliation."""
    result = _make_pre_invocation_result()
    result["reconciliation"] = _make_reconciliation()
    with pytest.raises(RepairAdapterContractError, match="reconciliation"):
        validate_adapter_result(result)


def test_C08_pre_invocation_no_permission_enforcement() -> None:
    """C08: Pre-invocation failure must not have permission_enforcement."""
    result = _make_pre_invocation_result()
    result["permission_enforcement"] = _make_permission_enforcement()
    with pytest.raises(RepairAdapterContractError, match="permission_enforcement"):
        validate_adapter_result(result)


def test_C09_post_invocation_no_valid_result() -> None:
    """C09: Post-invocation failure with no valid result must not have repair_result_summary."""
    result = _make_post_invocation_result(ADAPTER_TIMEOUT)
    result["repair_result_summary"] = _make_repair_result_summary()
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        validate_adapter_result(result)


def test_C10_post_invocation_missing_result_accepted() -> None:
    """C10: ADAPTER_MISSING_RESULT is a valid post-invocation failure."""
    result = _make_post_invocation_result(ADAPTER_MISSING_RESULT)
    validate_adapter_result(result)


def test_C11_enforcement_failure_requires_workspace_changes() -> None:
    """C11: ADAPTER_UNDECLARED_CHANGE requires workspace_changes."""
    result = _make_post_invocation_result(ADAPTER_UNDECLARED_CHANGE)
    result["workspace_changes"] = _make_workspace_changes()
    result["reconciliation"] = _make_reconciliation(
        undeclared_changes=["backend/extra.py"],
        exact_match=False,
    )
    validate_adapter_result(result)


def test_C12_forbidden_change_requires_permission_enforcement() -> None:
    """C12: ADAPTER_FORBIDDEN_CHANGE requires permission_enforcement."""
    result = _make_post_invocation_result(ADAPTER_FORBIDDEN_CHANGE)
    result["workspace_changes"] = _make_workspace_changes()
    result["permission_enforcement"] = _make_permission_enforcement(
        forbidden_violations=["backend/secret.py"],
        all_actual_changes_permitted=False,
    )
    validate_adapter_result(result)


def test_C13_forbidden_change_without_perm_enforcement_rejected() -> None:
    """C13: ADAPTER_FORBIDDEN_CHANGE without permission_enforcement is rejected."""
    result = _make_post_invocation_result(ADAPTER_FORBIDDEN_CHANGE)
    result["workspace_changes"] = _make_workspace_changes()
    with pytest.raises(RepairAdapterContractError, match="permission_enforcement"):
        validate_adapter_result(result)


# ===========================================================================
# D: repair_result_summary invariants
# ===========================================================================

def test_D01_repaired_requires_changed_true() -> None:
    """D01: REPAIRED with changed=false is rejected."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(changed=False)
    with pytest.raises(RepairAdapterContractError, match="REPAIRED requires changed"):
        validate_adapter_result(result)


def test_D02_repaired_requires_nonempty_changed_files() -> None:
    """D02: REPAIRED with empty changed_files is rejected."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(changed_files=[])
    with pytest.raises(RepairAdapterContractError, match="REPAIRED requires non-empty"):
        validate_adapter_result(result)


def test_D03_repaired_requires_reverify() -> None:
    """D03: REPAIRED with recommended_action != 'reverify' is rejected."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(recommended_action="abort")
    with pytest.raises(RepairAdapterContractError, match="REPAIRED requires recommended_action"):
        validate_adapter_result(result)


def test_D04_no_change_requires_changed_false() -> None:
    """D04: NO_CHANGE with changed=true is rejected."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(
        status="NO_CHANGE", changed=True, changed_files=[], recommended_action="abort",
    )
    with pytest.raises(RepairAdapterContractError, match="NO_CHANGE requires changed"):
        validate_adapter_result(result)


def test_D05_no_change_requires_empty_changed_files() -> None:
    """D05: NO_CHANGE with non-empty changed_files is rejected."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(
        status="NO_CHANGE", changed=False, changed_files=["backend/test.py"], recommended_action="abort",
    )
    with pytest.raises(RepairAdapterContractError, match="NO_CHANGE requires empty"):
        validate_adapter_result(result)


def test_D06_no_change_requires_abort_or_human_review() -> None:
    """D06: NO_CHANGE with recommended_action='reverify' is rejected."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(
        status="NO_CHANGE", changed=False, changed_files=[], recommended_action="reverify",
    )
    with pytest.raises(RepairAdapterContractError, match="NO_CHANGE requires"):
        validate_adapter_result(result)


def test_D07_error_requires_abort_or_human_review() -> None:
    """D07: ERROR with recommended_action='reverify' is rejected."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(
        status="ERROR", changed=True, changed_files=["x.py"], recommended_action="reverify",
    )
    with pytest.raises(RepairAdapterContractError, match="ERROR requires"):
        validate_adapter_result(result)


def test_D08_error_unconstrained_changed() -> None:
    """D08: ERROR with changed=true and non-empty changed_files is accepted."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(
        status="ERROR", changed=True, changed_files=["x.py"], recommended_action="abort",
    )
    validate_adapter_result(result)


def test_D09_summary_unknown_field_rejected() -> None:
    """D09: Unknown field in repair_result_summary is rejected."""
    result = _make_success_result()
    rrs = result["repair_result_summary"]
    rrs["extra_field"] = "value"
    with pytest.raises(RepairAdapterContractError, match="unknown field"):
        validate_adapter_result(result)


def test_D10_oversized_summary_rejected() -> None:
    """D10: Summary exceeding 2048 bytes is rejected."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(
        summary="x" * (MAX_SUMMARY_BYTES + 1),
    )
    with pytest.raises(RepairAdapterContractError, match="exceeds"):
        validate_adapter_result(result)


def test_D11_changed_files_over_max_rejected() -> None:
    """D11: changed_files exceeding 50 entries is rejected."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(
        changed_files=[f"file{i}.py" for i in range(MAX_CHANGED_FILES + 1)],
    )
    with pytest.raises(RepairAdapterContractError, match="exceeds"):
        validate_adapter_result(result)


def test_D12_duplicate_changed_files_rejected() -> None:
    """D12: Duplicate paths in changed_files are rejected."""
    result = _make_success_result()
    result["repair_result_summary"] = _make_repair_result_summary(
        changed_files=["backend/test.py", "backend/test.py"],
    )
    with pytest.raises(RepairAdapterContractError, match="duplicate"):
        validate_adapter_result(result)


# ===========================================================================
# E: workspace_changes invariants
# ===========================================================================

def test_E01_unknown_field_rejected() -> None:
    """E01: Unknown field in workspace_changes is rejected."""
    result = _make_success_result()
    result["workspace_changes"]["extra"] = "value"
    with pytest.raises(RepairAdapterContractError, match="unknown field"):
        validate_adapter_result(result)


def test_E02_invalid_baseline_revision_rejected() -> None:
    """E02: Invalid baseline_source_revision is rejected."""
    result = _make_success_result()
    result["workspace_changes"]["baseline_source_revision"] = "not-a-sha"
    with pytest.raises(RepairAdapterContractError, match="baseline_source_revision"):
        validate_adapter_result(result)


def test_E03_source_revision_stable_false_when_drift() -> None:
    """E03: source_revision_stable must be False when revisions differ."""
    result = _make_success_result()
    result["workspace_changes"]["post_source_revision"] = "b" * 40
    result["workspace_changes"]["source_revision_stable"] = True
    with pytest.raises(RepairAdapterContractError, match="source_revision_stable"):
        validate_adapter_result(result)


def test_E04_unsorted_paths_rejected() -> None:
    """E04: Unsorted path lists in workspace_changes are rejected."""
    result = _make_success_result()
    result["workspace_changes"]["modified"] = ["z.py", "a.py"]
    with pytest.raises(RepairAdapterContractError, match="sorted"):
        validate_adapter_result(result)


def test_E05_duplicate_paths_in_workspace_rejected() -> None:
    """E05: Duplicate paths within a workspace_changes list are rejected."""
    result = _make_success_result()
    result["workspace_changes"]["modified"] = ["a.py", "a.py"]
    with pytest.raises(RepairAdapterContractError, match="duplicate"):
        validate_adapter_result(result)


def test_E06_absolute_path_rejected() -> None:
    """E06: Absolute path in workspace_changes is rejected."""
    result = _make_success_result()
    result["workspace_changes"]["modified"] = ["/etc/passwd"]
    with pytest.raises(RepairAdapterContractError, match="absolute"):
        validate_adapter_result(result)


def test_E07_traversal_path_rejected() -> None:
    """E07: Parent traversal path in workspace_changes is rejected."""
    result = _make_success_result()
    result["workspace_changes"]["modified"] = ["../secrets.env"]
    with pytest.raises(RepairAdapterContractError, match="traversal"):
        validate_adapter_result(result)


# ===========================================================================
# F: reconciliation invariants
# ===========================================================================

def test_F01_unknown_field_rejected() -> None:
    """F01: Unknown field in reconciliation is rejected."""
    result = _make_success_result()
    result["reconciliation"]["extra"] = "value"
    with pytest.raises(RepairAdapterContractError, match="unknown field"):
        validate_adapter_result(result)


def test_F02_exact_match_false_with_mismatches() -> None:
    """F02: exact_match must be False when undeclared_changes is non-empty."""
    result = _make_success_result()
    result["reconciliation"] = _make_reconciliation(
        undeclared_changes=["extra.py"], exact_match=True,
    )
    with pytest.raises(RepairAdapterContractError, match="exact_match"):
        validate_adapter_result(result)


def test_F03_exact_match_false_with_declared_missing() -> None:
    """F03: exact_match must be False when declared_but_missing is non-empty."""
    result = _make_success_result()
    result["reconciliation"] = _make_reconciliation(
        declared_but_missing=["missing.py"], exact_match=True,
    )
    with pytest.raises(RepairAdapterContractError, match="exact_match"):
        validate_adapter_result(result)


def test_F04_exact_match_true_when_both_empty() -> None:
    """F04: exact_match must be True when both undeclared and declared_missing are empty."""
    result = _make_success_result()
    result["reconciliation"] = _make_reconciliation(exact_match=True)
    validate_adapter_result(result)


def test_F05_exact_match_true_with_nonempty_lists_rejected() -> None:
    """F05: exact_match True with non-empty mismatch lists is rejected."""
    result = _make_success_result()
    result["reconciliation"] = _make_reconciliation(
        undeclared_changes=["a.py"],
        declared_but_missing=["b.py"],
        exact_match=True,
    )
    with pytest.raises(RepairAdapterContractError, match="exact_match"):
        validate_adapter_result(result)


def test_F06_unsorted_reconciliation_paths_rejected() -> None:
    """F06: Unsorted declared_files in reconciliation are rejected."""
    result = _make_success_result()
    result["reconciliation"]["declared_files"] = ["z.py", "a.py"]
    with pytest.raises(RepairAdapterContractError, match="sorted"):
        validate_adapter_result(result)


# ===========================================================================
# G: permission_enforcement invariants
# ===========================================================================

def test_G01_unknown_field_rejected() -> None:
    """G01: Unknown field in permission_enforcement is rejected."""
    result = _make_success_result()
    result["permission_enforcement"]["extra"] = "value"
    with pytest.raises(RepairAdapterContractError, match="unknown field"):
        validate_adapter_result(result)


def test_G02_all_permitted_true_with_empty_violations() -> None:
    """G02: all_actual_changes_permitted True with empty violations is accepted."""
    result = _make_success_result()
    validate_adapter_result(result)


def test_G03_all_permitted_false_with_allowed_violation() -> None:
    """G03: all_actual_changes_permitted must be False when allowed_violations non-empty."""
    result = _make_success_result()
    result["permission_enforcement"] = _make_permission_enforcement(
        allowed_violations=["bad.py"], all_actual_changes_permitted=True,
    )
    with pytest.raises(RepairAdapterContractError, match="all_actual_changes_permitted"):
        validate_adapter_result(result)


def test_G04_all_permitted_false_with_forbidden_violation() -> None:
    """G04: all_actual_changes_permitted must be False when forbidden_violations non-empty."""
    result = _make_success_result()
    result["permission_enforcement"] = _make_permission_enforcement(
        forbidden_violations=["secret.py"], all_actual_changes_permitted=True,
    )
    with pytest.raises(RepairAdapterContractError, match="all_actual_changes_permitted"):
        validate_adapter_result(result)


def test_G05_all_permitted_false_with_both_violations() -> None:
    """G05: all_actual_changes_permitted False with both violations is accepted."""
    result = _make_success_result()
    result["permission_enforcement"] = _make_permission_enforcement(
        allowed_violations=["bad.py"],
        forbidden_violations=["secret.py"],
        all_actual_changes_permitted=False,
    )
    validate_adapter_result(result)


# ===========================================================================
# H: integrity_scope constants
# ===========================================================================

def test_H01_tracked_files_inspected_must_be_true() -> None:
    """H01: tracked_files_inspected must be True."""
    result = _make_success_result()
    result["integrity_scope"]["tracked_files_inspected"] = False
    with pytest.raises(RepairAdapterContractError, match="tracked_files_inspected"):
        validate_adapter_result(result)


def test_H02_untracked_non_ignored_must_be_true() -> None:
    """H02: untracked_non_ignored_inspected must be True."""
    result = _make_success_result()
    result["integrity_scope"]["untracked_non_ignored_inspected"] = False
    with pytest.raises(RepairAdapterContractError, match="untracked_non_ignored_inspected"):
        validate_adapter_result(result)


def test_H03_ignored_files_must_be_false() -> None:
    """H03: ignored_files_inspected must be False."""
    result = _make_success_result()
    result["integrity_scope"]["ignored_files_inspected"] = True
    with pytest.raises(RepairAdapterContractError, match="ignored_files_inspected"):
        validate_adapter_result(result)


def test_H04_advanced_symlink_must_be_false() -> None:
    """H04: advanced_symlink_inspected must be False."""
    result = _make_success_result()
    result["integrity_scope"]["advanced_symlink_inspected"] = True
    with pytest.raises(RepairAdapterContractError, match="advanced_symlink_inspected"):
        validate_adapter_result(result)


def test_H05_note_must_be_string() -> None:
    """H05: integrity_scope.note must be a string."""
    result = _make_success_result()
    result["integrity_scope"]["note"] = 123
    with pytest.raises(RepairAdapterContractError, match="note"):
        validate_adapter_result(result)


def test_H06_unknown_field_rejected() -> None:
    """H06: Unknown field in integrity_scope is rejected."""
    result = _make_success_result()
    result["integrity_scope"]["extra"] = "value"
    with pytest.raises(RepairAdapterContractError, match="unknown field"):
        validate_adapter_result(result)


# ===========================================================================
# I: diagnostics bounds
# ===========================================================================

def test_I01_unknown_field_rejected() -> None:
    """I01: Unknown field in diagnostics is rejected."""
    result = _make_success_result()
    result["diagnostics"]["extra"] = "value"
    with pytest.raises(RepairAdapterContractError, match="unknown field"):
        validate_adapter_result(result)


def test_I02_exit_code_none_accepted() -> None:
    """I02: actor_exit_code null is accepted."""
    result = _make_success_result()
    result["diagnostics"]["actor_exit_code"] = None
    validate_adapter_result(result)


def test_I03_exit_code_bool_rejected() -> None:
    """I03: actor_exit_code as bool is rejected."""
    result = _make_success_result()
    result["diagnostics"]["actor_exit_code"] = True
    with pytest.raises(RepairAdapterContractError, match="actor_exit_code"):
        validate_adapter_result(result)


def test_I04_oversized_stdout_rejected() -> None:
    """I04: actor_stdout_tail exceeding 4096 bytes is rejected."""
    result = _make_success_result()
    result["diagnostics"]["actor_stdout_tail"] = "x" * (MAX_STDOUT_TAIL_BYTES + 1)
    with pytest.raises(RepairAdapterContractError, match="actor_stdout_tail"):
        validate_adapter_result(result)


def test_I05_oversized_stderr_rejected() -> None:
    """I05: actor_stderr_tail exceeding 4096 bytes is rejected."""
    result = _make_success_result()
    result["diagnostics"]["actor_stderr_tail"] = "x" * (MAX_STDERR_TAIL_BYTES + 1)
    with pytest.raises(RepairAdapterContractError, match="actor_stderr_tail"):
        validate_adapter_result(result)


def test_I06_adapter_error_message_1024_byte_bound() -> None:
    """I06: adapter_error_message exceeding 1024 bytes is rejected."""
    result = _make_success_result()
    result["diagnostics"]["adapter_error_message"] = "x" * (MAX_ADAPTER_ERROR_MESSAGE_BYTES + 1)
    with pytest.raises(RepairAdapterContractError, match="adapter_error_message"):
        validate_adapter_result(result)


def test_I07_adapter_error_message_at_limit_accepted() -> None:
    """I07: adapter_error_message at exactly 1024 bytes is accepted."""
    result = _make_success_result()
    result["diagnostics"]["adapter_error_message"] = "x" * MAX_ADAPTER_ERROR_MESSAGE_BYTES
    validate_adapter_result(result)


def test_I08_adapter_error_message_none_accepted() -> None:
    """I08: adapter_error_message null is accepted."""
    result = _make_success_result()
    result["diagnostics"]["adapter_error_message"] = None
    validate_adapter_result(result)


# ===========================================================================
# J: path lexical safety + duplicate rejection
# ===========================================================================

def test_J01_absolute_path_in_changed_files_rejected() -> None:
    """J01: Absolute path in changed_files is rejected."""
    result = _make_success_result()
    result["repair_result_summary"]["changed_files"] = ["/etc/passwd"]
    with pytest.raises(RepairAdapterContractError, match="absolute"):
        validate_adapter_result(result)


def test_J02_traversal_path_in_changed_files_rejected() -> None:
    """J02: Parent traversal in changed_files is rejected."""
    result = _make_success_result()
    result["repair_result_summary"]["changed_files"] = ["../secrets.env"]
    with pytest.raises(RepairAdapterContractError, match="traversal"):
        validate_adapter_result(result)


def test_J03_backslash_path_rejected() -> None:
    """J03: Backslash in path is rejected."""
    result = _make_success_result()
    result["repair_result_summary"]["changed_files"] = ["backend\\test.py"]
    with pytest.raises(RepairAdapterContractError, match="backslash"):
        validate_adapter_result(result)


def test_J04_null_byte_in_path_rejected() -> None:
    """J04: Null byte in path is rejected."""
    result = _make_success_result()
    result["repair_result_summary"]["changed_files"] = ["backend\x00test.py"]
    with pytest.raises(RepairAdapterContractError, match="null byte"):
        validate_adapter_result(result)


def test_J05_windows_drive_letter_rejected() -> None:
    """J05: Windows drive letter in path is rejected."""
    result = _make_success_result()
    result["repair_result_summary"]["changed_files"] = ["C:backend/test.py"]
    with pytest.raises(RepairAdapterContractError, match="Windows drive"):
        validate_adapter_result(result)


def test_J06_unc_path_rejected() -> None:
    """J06: UNC path is rejected."""
    result = _make_success_result()
    result["repair_result_summary"]["changed_files"] = ["\\\\server\\share"]
    with pytest.raises(RepairAdapterContractError, match="UNC"):
        validate_adapter_result(result)


def test_J07_dot_segment_rejected() -> None:
    """J07: Single-dot segment in path is rejected."""
    result = _make_success_result()
    result["repair_result_summary"]["changed_files"] = ["./backend/test.py"]
    with pytest.raises(RepairAdapterContractError, match=r"'\.'"):
        validate_adapter_result(result)


def test_J08_duplicate_separator_rejected() -> None:
    """J08: Duplicate separator in path is rejected."""
    result = _make_success_result()
    result["repair_result_summary"]["changed_files"] = ["backend//test.py"]
    with pytest.raises(RepairAdapterContractError, match="duplicate separator"):
        validate_adapter_result(result)


def test_J09_oversized_path_rejected() -> None:
    """J09: Path exceeding 512 bytes is rejected."""
    result = _make_success_result()
    result["repair_result_summary"]["changed_files"] = ["a" * (MAX_PATH_BYTES + 1)]
    with pytest.raises(RepairAdapterContractError, match="exceeds"):
        validate_adapter_result(result)


def test_J10_duplicate_path_in_permission_violations_rejected() -> None:
    """J10: Duplicate path in permission_enforcement.violations is rejected."""
    result = _make_success_result()
    result["permission_enforcement"]["allowed_violations"] = ["a.py", "a.py"]
    result["permission_enforcement"]["all_actual_changes_permitted"] = False
    with pytest.raises(RepairAdapterContractError, match="duplicate"):
        validate_adapter_result(result)


# ===========================================================================
# K: canonical/pretty serialization determinism
# ===========================================================================

def test_K01_canonical_bytes_deterministic() -> None:
    """K01: Same dict with different insertion order produces identical canonical bytes."""
    result = _make_success_result()
    result2 = dict(reversed(list(result.items())))
    b1 = canonical_json_bytes(result)
    b2 = canonical_json_bytes(result2)
    assert b1 == b2


def test_K02_canonical_bytes_sorted_keys() -> None:
    """K02: Canonical JSON keys are sorted alphabetically."""
    result = _make_success_result()
    parsed = json.loads(canonical_json_bytes(result).decode("utf-8"))
    assert list(parsed.keys()) == sorted(parsed.keys())


def test_K03_canonical_bytes_compact_separators() -> None:
    """K03: Canonical JSON uses compact separators (no spaces after : or ,)."""
    result = _make_success_result()
    text = canonical_json_bytes(result).decode("utf-8")
    assert ", " not in text
    assert ": " not in text


def test_K04_pretty_json_indent_2() -> None:
    """K04: Pretty JSON has 2-space indent."""
    result = _make_success_result()
    text = pretty_json_string(result)
    assert '  "schema_version"' in text


def test_K05_pretty_json_trailing_newline() -> None:
    """K05: Pretty JSON ends with exactly one newline."""
    result = _make_success_result()
    text = pretty_json_string(result)
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_K06_pretty_json_no_trailing_whitespace() -> None:
    """K06: Pretty JSON has no trailing whitespace on any line."""
    result = _make_success_result()
    text = pretty_json_string(result)
    for line in text.split("\n"):
        assert line == line.rstrip()


# ===========================================================================
# L: builder determinism + immutability
# ===========================================================================

def test_L01_builder_produces_valid_result() -> None:
    """L01: build_adapter_result produces a result that passes validation."""
    result = build_adapter_result(
        run_id=VALID_RUN_ID,
        story_id=VALID_STORY_ID,
        attempt=1,
        adapter_status=ADAPTER_SUCCESS,
        completed_at=VALID_TIMESTAMP,
        repair_result_summary=_make_repair_result_summary(),
        workspace_changes=_make_workspace_changes(),
        reconciliation=_make_reconciliation(),
        permission_enforcement=_make_permission_enforcement(),
    )
    validate_adapter_result(result)


def test_L02_builder_deterministic_output() -> None:
    """L02: Same inputs produce identical canonical bytes."""
    kwargs: dict[str, Any] = {
        "run_id": VALID_RUN_ID,
        "story_id": VALID_STORY_ID,
        "attempt": 1,
        "adapter_status": ADAPTER_SUCCESS,
        "completed_at": VALID_TIMESTAMP,
        "repair_result_summary": _make_repair_result_summary(),
        "workspace_changes": _make_workspace_changes(),
        "reconciliation": _make_reconciliation(),
        "permission_enforcement": _make_permission_enforcement(),
    }
    r1 = build_adapter_result(**kwargs)
    r2 = build_adapter_result(**kwargs)
    assert canonical_json_bytes(r1) == canonical_json_bytes(r2)


def test_L03_builder_does_not_mutate_caller_dict() -> None:
    """L03: Builder does not mutate caller-provided repair_result_summary."""
    rrs = _make_repair_result_summary()
    rrs_copy = json.loads(json.dumps(rrs))
    build_adapter_result(
        run_id=VALID_RUN_ID,
        story_id=VALID_STORY_ID,
        attempt=1,
        adapter_status=ADAPTER_SUCCESS,
        completed_at=VALID_TIMESTAMP,
        repair_result_summary=rrs,
        workspace_changes=_make_workspace_changes(),
        reconciliation=_make_reconciliation(),
        permission_enforcement=_make_permission_enforcement(),
    )
    assert rrs == rrs_copy


def test_L04_builder_does_not_mutate_caller_list() -> None:
    """L04: Builder does not mutate caller-provided changed_files list."""
    changed_files = ["backend/test.py"]
    changed_files_copy = list(changed_files)
    rrs = _make_repair_result_summary(changed_files=changed_files)
    build_adapter_result(
        run_id=VALID_RUN_ID,
        story_id=VALID_STORY_ID,
        attempt=1,
        adapter_status=ADAPTER_SUCCESS,
        completed_at=VALID_TIMESTAMP,
        repair_result_summary=rrs,
        workspace_changes=_make_workspace_changes(),
        reconciliation=_make_reconciliation(),
        permission_enforcement=_make_permission_enforcement(),
    )
    assert changed_files == changed_files_copy


def test_L05_builder_does_not_mutate_nested_list_in_summary() -> None:
    """L05: Builder does not mutate nested changed_files inside summary dict."""
    rrs = _make_repair_result_summary(changed_files=["a.py", "b.py"])
    rrs_serialized_before = json.dumps(rrs, sort_keys=True)
    build_adapter_result(
        run_id=VALID_RUN_ID,
        story_id=VALID_STORY_ID,
        attempt=1,
        adapter_status=ADAPTER_SUCCESS,
        completed_at=VALID_TIMESTAMP,
        repair_result_summary=rrs,
        workspace_changes=_make_workspace_changes(),
        reconciliation=_make_reconciliation(),
        permission_enforcement=_make_permission_enforcement(),
    )
    assert json.dumps(rrs, sort_keys=True) == rrs_serialized_before


def test_L06_builder_defaults_diagnostics_and_sanitization() -> None:
    """L06: Builder provides default diagnostics and sanitization."""
    result = build_adapter_result(
        run_id=VALID_RUN_ID,
        story_id=VALID_STORY_ID,
        attempt=1,
        adapter_status=ADAPTER_DIRTY_BASELINE,
        completed_at=VALID_TIMESTAMP,
    )
    assert result["diagnostics"]["actor_exit_code"] is None
    assert result["diagnostics"]["adapter_error_message"] is None
    assert result["sanitization"]["redaction_applied"] is False
    assert result["sanitization"]["redaction_count"] == 0
    assert result["sanitization"]["truncated_fields"] == []
    validate_adapter_result(result)


def test_L07_builder_defaults_integrity_scope() -> None:
    """L07: Builder provides default integrity_scope with correct constants."""
    result = build_adapter_result(
        run_id=VALID_RUN_ID,
        story_id=VALID_STORY_ID,
        attempt=1,
        adapter_status=ADAPTER_DIRTY_BASELINE,
        completed_at=VALID_TIMESTAMP,
    )
    assert result["integrity_scope"]["tracked_files_inspected"] is True
    assert result["integrity_scope"]["untracked_non_ignored_inspected"] is True
    assert result["integrity_scope"]["ignored_files_inspected"] is False
    assert result["integrity_scope"]["advanced_symlink_inspected"] is False
    validate_adapter_result(result)


def test_L08_builder_rejects_invalid_status() -> None:
    """L08: Builder rejects invalid adapter_status."""
    with pytest.raises(RepairAdapterContractError, match="adapter_status"):
        build_adapter_result(
            run_id=VALID_RUN_ID,
            story_id=VALID_STORY_ID,
            attempt=1,
            adapter_status="INVALID",
            completed_at=VALID_TIMESTAMP,
        )


def test_L09_builder_rejects_missing_conditional_for_success() -> None:
    """L09: Builder rejects ADAPTER_SUCCESS without conditional fields."""
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        build_adapter_result(
            run_id=VALID_RUN_ID,
            story_id=VALID_STORY_ID,
            attempt=1,
            adapter_status=ADAPTER_SUCCESS,
            completed_at=VALID_TIMESTAMP,
        )


def test_L10_validation_does_not_alter_supplied_object() -> None:
    """L10: validate_adapter_result does not mutate the supplied dict."""
    result = _make_success_result()
    serialized_before = json.dumps(result, sort_keys=True)
    validate_adapter_result(result)
    assert json.dumps(result, sort_keys=True) == serialized_before


# ===========================================================================
# M: schema/code/test parity
# ===========================================================================

def test_M01_top_level_field_set_matches_code_constant() -> None:
    """M01: ALL_TOP_LEVEL_FIELDS has exactly 13 entries matching schema."""
    expected = {
        "schema_version", "run_id", "story_id", "attempt", "adapter_status",
        "repair_result_summary", "workspace_changes", "reconciliation",
        "permission_enforcement", "diagnostics", "sanitization",
        "integrity_scope", "completed_at",
    }
    assert set(ALL_TOP_LEVEL_FIELDS) == expected
    assert len(ALL_TOP_LEVEL_FIELDS) == 13


def test_M02_adapter_status_count_matches_schema() -> None:
    """M02: VALID_ADAPTER_STATUSES has exactly 14 values matching schema."""
    assert len(VALID_ADAPTER_STATUSES) == 14


def test_M03_dataclasses_are_frozen() -> None:
    """M03: WorkspaceBaseline, WorkspaceChange, ReconciliationResult, RepairAdapterResult are frozen."""
    import dataclasses
    assert dataclasses.is_dataclass(WorkspaceBaseline)
    assert dataclasses.is_dataclass(WorkspaceChange)
    assert dataclasses.is_dataclass(ReconciliationResult)
    assert dataclasses.is_dataclass(RepairAdapterResult)
    # Verify frozen by attempting assignment
    baseline = WorkspaceBaseline(
        source_revision=VALID_SHA40,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        baseline.source_revision = "b" * 40  # type: ignore[misc]


def test_M04_repair_adapter_result_dataclass_fields() -> None:
    """M04: RepairAdapterResult has 13 fields matching top-level schema."""
    import dataclasses
    fields_list = dataclasses.fields(RepairAdapterResult)
    assert len(fields_list) == 13
    field_names = {f.name for f in fields_list}
    assert field_names == set(ALL_TOP_LEVEL_FIELDS)


def test_M05_sanitization_cross_field_redaction() -> None:
    """M05: redaction_applied False requires redaction_count 0."""
    result = _make_success_result()
    result["sanitization"]["redaction_applied"] = False
    result["sanitization"]["redaction_count"] = 5
    with pytest.raises(RepairAdapterContractError, match="redaction"):
        validate_adapter_result(result)


def test_M06_sanitization_cross_field_truncation() -> None:
    """M06: truncation_applied False requires empty truncated_fields."""
    result = _make_success_result()
    result["sanitization"]["truncation_applied"] = False
    result["sanitization"]["truncated_fields"] = ["some_field"]
    with pytest.raises(RepairAdapterContractError, match="truncation"):
        validate_adapter_result(result)


def test_M07_sanitization_truncated_fields_sorted() -> None:
    """M07: truncated_fields must be sorted lexicographically."""
    result = _make_success_result()
    result["sanitization"]["truncation_applied"] = True
    result["sanitization"]["truncated_fields"] = ["z_field", "a_field"]
    with pytest.raises(RepairAdapterContractError, match="sorted"):
        validate_adapter_result(result)


def test_M08_sanitization_truncated_fields_at_limit() -> None:
    """M08: truncated_fields at exactly 64 entries is accepted."""
    result = _make_success_result()
    result["sanitization"]["truncation_applied"] = True
    result["sanitization"]["truncated_fields"] = sorted([f"field_{i}" for i in range(MAX_TRUNCATED_FIELDS)])
    validate_adapter_result(result)


def test_M09_sanitization_truncated_fields_over_limit() -> None:
    """M09: truncated_fields exceeding 64 entries is rejected."""
    result = _make_success_result()
    result["sanitization"]["truncation_applied"] = True
    result["sanitization"]["truncated_fields"] = sorted([f"field_{i}" for i in range(MAX_TRUNCATED_FIELDS + 1)])
    with pytest.raises(RepairAdapterContractError, match="exceeds"):
        validate_adapter_result(result)


def test_M10_redaction_count_bool_rejected() -> None:
    """M10: redaction_count as bool is rejected."""
    result = _make_success_result()
    result["sanitization"]["redaction_count"] = True
    with pytest.raises(RepairAdapterContractError, match="redaction_count"):
        validate_adapter_result(result)


def test_M11_redaction_count_negative_rejected() -> None:
    """M11: negative redaction_count is rejected."""
    result = _make_success_result()
    result["sanitization"]["redaction_count"] = -1
    with pytest.raises(RepairAdapterContractError, match="redaction_count"):
        validate_adapter_result(result)


def test_M12_sanitization_unknown_field_rejected() -> None:
    """M12: Unknown field in sanitization is rejected."""
    result = _make_success_result()
    result["sanitization"]["extra"] = "value"
    with pytest.raises(RepairAdapterContractError, match="unknown field"):
        validate_adapter_result(result)


# ===========================================================================
# N: Multibyte UTF-8 byte-boundary tests
# ===========================================================================
# These tests prove byte counting, not character counting. 'é' is U+00E9,
# 2 UTF-8 bytes per character. A character-counting implementation would
# accept the one-byte-over cases below, so those rejections are
# defect-sensitive.

def test_N01_multibyte_stdout_at_exact_byte_limit_accepted() -> None:
    """N01: actor_stdout_tail of 2048 two-byte chars = exactly 4096 bytes accepted."""
    result = _make_success_result()
    payload = "é" * (MAX_STDOUT_TAIL_BYTES // 2)
    assert len(payload) == 2048  # characters
    assert len(payload.encode("utf-8")) == MAX_STDOUT_TAIL_BYTES
    result["diagnostics"]["actor_stdout_tail"] = payload
    validate_adapter_result(result)  # must not raise


def test_N02_multibyte_stdout_one_byte_over_rejected() -> None:
    """N02: actor_stdout_tail at 4097 UTF-8 bytes (2049 chars) is rejected."""
    result = _make_success_result()
    payload = "é" * (MAX_STDOUT_TAIL_BYTES // 2) + "a"
    assert len(payload.encode("utf-8")) == MAX_STDOUT_TAIL_BYTES + 1
    result["diagnostics"]["actor_stdout_tail"] = payload
    with pytest.raises(RepairAdapterContractError, match="actor_stdout_tail"):
        validate_adapter_result(result)


def test_N03_multibyte_summary_at_exact_byte_limit_accepted() -> None:
    """N03: summary of 1024 two-byte chars = exactly 2048 bytes accepted."""
    result = _make_success_result()
    payload = "é" * (MAX_SUMMARY_BYTES // 2)
    assert len(payload.encode("utf-8")) == MAX_SUMMARY_BYTES
    result["repair_result_summary"]["summary"] = payload
    validate_adapter_result(result)  # must not raise


def test_N04_multibyte_summary_one_byte_over_rejected() -> None:
    """N04: summary at 2049 UTF-8 bytes is rejected."""
    result = _make_success_result()
    payload = "é" * (MAX_SUMMARY_BYTES // 2) + "a"
    assert len(payload.encode("utf-8")) == MAX_SUMMARY_BYTES + 1
    result["repair_result_summary"]["summary"] = payload
    with pytest.raises(RepairAdapterContractError, match="summary"):
        validate_adapter_result(result)


def test_N05_multibyte_path_at_exact_byte_limit_accepted() -> None:
    """N05: path of 256 two-byte chars = exactly 512 bytes accepted."""
    result = _make_success_result()
    payload = "é" * (MAX_PATH_BYTES // 2)
    assert len(payload.encode("utf-8")) == MAX_PATH_BYTES
    result["repair_result_summary"]["changed_files"] = [payload]
    validate_adapter_result(result)  # must not raise


def test_N06_multibyte_path_one_byte_over_rejected() -> None:
    """N06: path at 513 UTF-8 bytes is rejected."""
    result = _make_success_result()
    payload = "é" * (MAX_PATH_BYTES // 2) + "a"
    assert len(payload.encode("utf-8")) == MAX_PATH_BYTES + 1
    result["repair_result_summary"]["changed_files"] = [payload]
    with pytest.raises(RepairAdapterContractError, match="exceeds"):
        validate_adapter_result(result)


# ===========================================================================
# O: Missing-versus-explicit-null conditional-field behavior
# ===========================================================================

def test_O01_success_missing_repair_result_summary_rejected() -> None:
    """O01: ADAPTER_SUCCESS with repair_result_summary key missing fails."""
    result = _make_success_result()
    del result["repair_result_summary"]
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        validate_adapter_result(result)


def test_O02_success_explicit_null_repair_result_summary_rejected() -> None:
    """O02: ADAPTER_SUCCESS with repair_result_summary=None fails."""
    result = _make_success_result()
    result["repair_result_summary"] = None
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        validate_adapter_result(result)


def test_O03_dirty_baseline_omitted_conditional_fields_accepted() -> None:
    """O03: ADAPTER_DIRTY_BASELINE with all conditional fields omitted succeeds."""
    result = _make_pre_invocation_result(ADAPTER_DIRTY_BASELINE)
    assert "repair_result_summary" not in result
    assert "workspace_changes" not in result
    assert "reconciliation" not in result
    assert "permission_enforcement" not in result
    validate_adapter_result(result)  # must not raise


def test_O04_dirty_baseline_explicit_null_conditional_fields_accepted() -> None:
    """O04: ADAPTER_DIRTY_BASELINE with conditional fields explicitly None succeeds.

    Explicit null is treated as absence for conditional fields.
    """
    result = _make_pre_invocation_result(ADAPTER_DIRTY_BASELINE)
    result["repair_result_summary"] = None
    result["workspace_changes"] = None
    result["reconciliation"] = None
    result["permission_enforcement"] = None
    validate_adapter_result(result)  # must not raise


def test_O05_timeout_missing_repair_result_summary_accepted() -> None:
    """O05: ADAPTER_TIMEOUT with repair_result_summary omitted succeeds."""
    result = _make_post_invocation_result(ADAPTER_TIMEOUT)
    assert "repair_result_summary" not in result
    validate_adapter_result(result)  # must not raise


def test_O06_timeout_explicit_null_repair_result_summary_accepted() -> None:
    """O06: ADAPTER_TIMEOUT with repair_result_summary=None succeeds (null = absent)."""
    result = _make_post_invocation_result(ADAPTER_TIMEOUT)
    result["repair_result_summary"] = None
    validate_adapter_result(result)  # must not raise


# ===========================================================================
# P: Dedicated presence tests for statuses relying on shared branches
# ===========================================================================

def test_P01_non_zero_exit_presence() -> None:
    """P01: ADAPTER_NON_ZERO_EXIT minimal payload accepted; summary forbidden."""
    result = _make_post_invocation_result(ADAPTER_NON_ZERO_EXIT)
    validate_adapter_result(result)  # must not raise
    result["repair_result_summary"] = _make_repair_result_summary()
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        validate_adapter_result(result)


def test_P02_malformed_result_presence() -> None:
    """P02: ADAPTER_MALFORMED_RESULT minimal payload accepted; summary forbidden."""
    result = _make_post_invocation_result(ADAPTER_MALFORMED_RESULT)
    validate_adapter_result(result)  # must not raise
    result["repair_result_summary"] = _make_repair_result_summary()
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        validate_adapter_result(result)


def test_P03_contract_violation_presence() -> None:
    """P03: ADAPTER_CONTRACT_VIOLATION minimal payload accepted; summary forbidden."""
    result = _make_post_invocation_result(ADAPTER_CONTRACT_VIOLATION)
    validate_adapter_result(result)  # must not raise
    result["repair_result_summary"] = _make_repair_result_summary()
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        validate_adapter_result(result)


def test_P04_identity_mismatch_presence() -> None:
    """P04: ADAPTER_IDENTITY_MISMATCH minimal payload accepted; summary forbidden."""
    result = _make_post_invocation_result(ADAPTER_IDENTITY_MISMATCH)
    validate_adapter_result(result)  # must not raise
    result["repair_result_summary"] = _make_repair_result_summary()
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        validate_adapter_result(result)


def test_P05_source_revision_drift_presence() -> None:
    """P05: ADAPTER_SOURCE_REVISION_DRIFT pre-invocation shape accepted; workspace forbidden."""
    result = _make_pre_invocation_result(ADAPTER_SOURCE_REVISION_DRIFT)
    validate_adapter_result(result)  # must not raise
    result["workspace_changes"] = _make_workspace_changes()
    with pytest.raises(RepairAdapterContractError, match="workspace_changes"):
        validate_adapter_result(result)


def test_P06_declared_missing_presence() -> None:
    """P06: ADAPTER_DECLARED_MISSING requires workspace_changes."""
    result = _make_post_invocation_result(ADAPTER_DECLARED_MISSING)
    result["workspace_changes"] = _make_workspace_changes()
    result["reconciliation"] = _make_reconciliation(
        declared_but_missing=["backend/test.py"],
        exact_match=False,
    )
    validate_adapter_result(result)  # must not raise
    del result["workspace_changes"]
    with pytest.raises(RepairAdapterContractError, match="workspace_changes"):
        validate_adapter_result(result)


def test_P07_output_size_exceeded_presence() -> None:
    """P07: ADAPTER_OUTPUT_SIZE_EXCEEDED minimal payload accepted; summary forbidden."""
    result = _make_post_invocation_result(ADAPTER_OUTPUT_SIZE_EXCEEDED)
    validate_adapter_result(result)  # must not raise
    result["repair_result_summary"] = _make_repair_result_summary()
    with pytest.raises(RepairAdapterContractError, match="repair_result_summary"):
        validate_adapter_result(result)
