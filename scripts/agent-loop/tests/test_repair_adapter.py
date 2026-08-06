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
import subprocess
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
    BaselineVerificationError,
    ReconciliationResult,
    RepairAdapterContractError,
    RepairAdapterResult,
    WorkspaceBaseline,
    WorkspaceChange,
    _capture_post_run_workspace,
    _deduplicate_and_sort,
    _enforce_permissions,
    _parse_ls_files_others_z,
    _parse_porcelain_status_z,
    _reconcile_changes,
    _run_git_command,
    _run_git_subprocess,
    _validate_identity_binding,
    _validate_inventory_path,
    _validate_inventory_paths,
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


# ===========================================================================
# Slice 2: Baseline verification (Git repository tests)
# ===========================================================================

from repair_adapter import (
    _verify_clean_tracked_baseline,
)


def _git(repo: Path, *args: str) -> str:
    """Run git command in repo directory."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _create_temp_repo(tmp_path: Path) -> Path:
    """Create a temporary Git repository with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir()

    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

    # Create initial file and commit
    (repo / "initial.txt").write_text("initial content\n")
    _git(repo, "add", "initial.txt")
    _git(repo, "commit", "-m", "Initial commit")

    return repo


def _get_head_sha(repo: Path) -> str:
    """Get current HEAD SHA."""
    return _git(repo, "rev-parse", "HEAD")


# ---------------------------------------------------------------------------
# Test: Clean baseline acceptance
# ---------------------------------------------------------------------------


def test_BL01_clean_baseline_accepted(tmp_path: Path) -> None:
    """BL01: Clean repository with no changes should be accepted."""
    repo = _create_temp_repo(tmp_path)

    baseline = _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )

    assert isinstance(baseline, WorkspaceBaseline)
    assert baseline.source_revision == _get_head_sha(repo)
    assert baseline.baseline_exclusions == []
    assert baseline.captured_at == VALID_TIMESTAMP


def test_BL02_clean_baseline_with_untracked_files_accepted(tmp_path: Path) -> None:
    """BL02: Clean repository with untracked files (not in exclusions) should be accepted."""
    repo = _create_temp_repo(tmp_path)

    # Create untracked file
    (repo / "untracked.txt").write_text("untracked content\n")

    baseline = _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )

    assert isinstance(baseline, WorkspaceBaseline)
    assert baseline.source_revision == _get_head_sha(repo)


def test_BL03_clean_baseline_with_excluded_untracked_files(tmp_path: Path) -> None:
    """BL03: Clean repository with excluded untracked files should be accepted."""
    repo = _create_temp_repo(tmp_path)

    # Create untracked file
    (repo / "untracked.txt").write_text("untracked content\n")

    baseline = _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=["untracked.txt"],
        captured_at=VALID_TIMESTAMP,
    )

    assert isinstance(baseline, WorkspaceBaseline)
    assert baseline.baseline_exclusions == ["untracked.txt"]


# ---------------------------------------------------------------------------
# Test: Dirty baseline rejection
# ---------------------------------------------------------------------------


def test_BL04_modified_tracked_file_rejected(tmp_path: Path) -> None:
    """BL04: Modified tracked file should cause ADAPTER_DIRTY_BASELINE."""
    repo = _create_temp_repo(tmp_path)

    # Modify tracked file
    (repo / "initial.txt").write_text("modified content\n")

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_DIRTY_BASELINE
    assert "initial.txt" in str(exc_info.value)


def test_BL05_staged_tracked_file_rejected(tmp_path: Path) -> None:
    """BL05: Staged tracked file should cause ADAPTER_DIRTY_BASELINE."""
    repo = _create_temp_repo(tmp_path)

    # Modify and stage tracked file
    (repo / "initial.txt").write_text("modified content\n")
    _git(repo, "add", "initial.txt")

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_DIRTY_BASELINE
    assert "initial.txt" in str(exc_info.value)


def test_BL06_staged_new_file_rejected(tmp_path: Path) -> None:
    """BL06: Staged new file should cause ADAPTER_DIRTY_BASELINE."""
    repo = _create_temp_repo(tmp_path)

    # Create and stage new file
    (repo / "new.txt").write_text("new content\n")
    _git(repo, "add", "new.txt")

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_DIRTY_BASELINE
    assert "new.txt" in str(exc_info.value)


def test_BL07_deleted_tracked_file_rejected(tmp_path: Path) -> None:
    """BL07: Deleted tracked file should cause ADAPTER_DIRTY_BASELINE."""
    repo = _create_temp_repo(tmp_path)

    # Delete tracked file
    (repo / "initial.txt").unlink()

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_DIRTY_BASELINE
    assert "initial.txt" in str(exc_info.value)


def test_BL08_renamed_tracked_file_rejected(tmp_path: Path) -> None:
    """BL08: Renamed tracked file should cause ADAPTER_DIRTY_BASELINE."""
    repo = _create_temp_repo(tmp_path)

    # Rename tracked file
    _git(repo, "mv", "initial.txt", "renamed.txt")

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_DIRTY_BASELINE
    error_msg = str(exc_info.value)
    assert "initial.txt" in error_msg or "renamed.txt" in error_msg


# ---------------------------------------------------------------------------
# Test: Baseline exclusion validation
# ---------------------------------------------------------------------------


def test_BL09_exclusion_path_absolute_rejected(tmp_path: Path) -> None:
    """BL09: Absolute path in exclusion list should be rejected."""
    repo = _create_temp_repo(tmp_path)

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=["/absolute/path.txt"],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "absolute path" in str(exc_info.value)


def test_BL10_exclusion_path_traversal_rejected(tmp_path: Path) -> None:
    """BL10: Path with traversal (..) in exclusion list should be rejected."""
    repo = _create_temp_repo(tmp_path)

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=["../outside.txt"],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "traversal" in str(exc_info.value)


def test_BL11_exclusion_path_dot_segment_rejected(tmp_path: Path) -> None:
    """BL11: Path with '.' segment in exclusion list should be rejected."""
    repo = _create_temp_repo(tmp_path)

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=["./file.txt"],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "'.' segment" in str(exc_info.value)


def test_BL12_exclusion_path_empty_rejected(tmp_path: Path) -> None:
    """BL12: Empty path in exclusion list should be rejected."""
    repo = _create_temp_repo(tmp_path)

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=[""],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "empty path" in str(exc_info.value)


def test_BL13_exclusion_path_null_byte_rejected(tmp_path: Path) -> None:
    """BL13: Path with null byte in exclusion list should be rejected."""
    repo = _create_temp_repo(tmp_path)

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=["file\x00.txt"],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "null byte" in str(exc_info.value)


def test_BL14_exclusion_path_backslash_rejected(tmp_path: Path) -> None:
    """BL14: Path with backslash in exclusion list should be rejected."""
    repo = _create_temp_repo(tmp_path)

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=["path\\file.txt"],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "backslash" in str(exc_info.value)


def test_BL15_exclusion_path_duplicate_separator_rejected(tmp_path: Path) -> None:
    """BL15: Path with duplicate separator (//) in exclusion list should be rejected."""
    repo = _create_temp_repo(tmp_path)

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=["path//file.txt"],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "duplicate separator" in str(exc_info.value)


def test_BL16_exclusion_path_duplicate_entry_rejected(tmp_path: Path) -> None:
    """BL16: Duplicate entries in exclusion list should be rejected."""
    repo = _create_temp_repo(tmp_path)

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=["file.txt", "file.txt"],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "duplicate" in str(exc_info.value)


def test_BL17_exclusion_list_sorted_and_deduplicated(tmp_path: Path) -> None:
    """BL17: Exclusion list should be sorted and returned in baseline."""
    repo = _create_temp_repo(tmp_path)

    baseline = _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=["b.txt", "a.txt", "c.txt"],
        captured_at=VALID_TIMESTAMP,
    )

    assert baseline.baseline_exclusions == ["a.txt", "b.txt", "c.txt"]


# ---------------------------------------------------------------------------
# Test: Source revision capture
# ---------------------------------------------------------------------------


def test_BL18_source_revision_captured(tmp_path: Path) -> None:
    """BL18: Source revision should match current HEAD."""
    repo = _create_temp_repo(tmp_path)
    expected_sha = _get_head_sha(repo)

    baseline = _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )

    assert baseline.source_revision == expected_sha
    assert len(baseline.source_revision) == 40


def test_BL19_source_revision_format_validated(tmp_path: Path) -> None:
    """BL19: Source revision must be 40-char lowercase hex."""
    repo = _create_temp_repo(tmp_path)

    baseline = _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )

    # Verify it's a valid 40-char hex string
    assert len(baseline.source_revision) == 40
    assert all(c in "0123456789abcdef" for c in baseline.source_revision)


def test_BL20_detached_head_accepted(tmp_path: Path) -> None:
    """BL20: Detached HEAD state should be accepted (still valid SHA)."""
    repo = _create_temp_repo(tmp_path)

    # Get current HEAD and detach
    sha = _get_head_sha(repo)
    _git(repo, "checkout", sha)

    baseline = _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )

    assert baseline.source_revision == sha


# ---------------------------------------------------------------------------
# Test: Repository validation
# ---------------------------------------------------------------------------


def test_BL21_non_repository_path_rejected(tmp_path: Path) -> None:
    """BL21: Path that is not a Git repository should be rejected."""
    not_a_repo = tmp_path / "not_a_repo"
    not_a_repo.mkdir()

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=not_a_repo,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR


def test_BL22_missing_repo_root_rejected(tmp_path: Path) -> None:
    """BL22: Non-existent repo_root should be rejected."""
    missing = tmp_path / "missing"

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=missing,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "does not exist" in str(exc_info.value)


def test_BL23_file_as_repo_root_rejected(tmp_path: Path) -> None:
    """BL23: File (not directory) as repo_root should be rejected."""
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a directory\n")

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=file_path,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "not a directory" in str(exc_info.value)


def test_BL24_invalid_captured_at_format_rejected(tmp_path: Path) -> None:
    """BL24: Invalid captured_at format should be rejected."""
    repo = _create_temp_repo(tmp_path)

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=[],
            captured_at="not-a-timestamp",
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR
    assert "ISO-8601" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test: Non-mutation guarantee
# ---------------------------------------------------------------------------


def test_BL25_repository_state_unchanged_after_inspection(tmp_path: Path) -> None:
    """BL25: Baseline verification must not mutate repository state."""
    repo = _create_temp_repo(tmp_path)

    # Capture state before
    head_before = _get_head_sha(repo)
    status_before = _git(repo, "status", "--porcelain")
    branch_before = _git(repo, "branch", "--show-current")

    # Run baseline verification
    _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )

    # Verify state unchanged
    head_after = _get_head_sha(repo)
    status_after = _git(repo, "status", "--porcelain")
    branch_after = _git(repo, "branch", "--show-current")

    assert head_before == head_after
    assert status_before == status_after
    assert branch_before == branch_after


def test_BL26_no_stash_created_during_inspection(tmp_path: Path) -> None:
    """BL26: Baseline verification must not create stash entries."""
    repo = _create_temp_repo(tmp_path)

    # Verify no stash before
    stash_before = _git(repo, "stash", "list")
    assert stash_before == ""

    # Run baseline verification
    _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )

    # Verify no stash after
    stash_after = _git(repo, "stash", "list")
    assert stash_after == ""


def test_BL27_no_temp_files_created_during_inspection(tmp_path: Path) -> None:
    """BL27: Baseline verification must not create temporary files in repo."""
    repo = _create_temp_repo(tmp_path)

    # List files before
    files_before = set()
    for p in repo.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            files_before.add(p.relative_to(repo))

    # Run baseline verification
    _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )

    # List files after
    files_after = set()
    for p in repo.rglob("*"):
        if p.is_file() and ".git" not in p.parts:
            files_after.add(p.relative_to(repo))

    assert files_before == files_after


# ---------------------------------------------------------------------------
# Test: Hard-coded exception prevention
# ---------------------------------------------------------------------------


def test_BL28_no_hard_coded_exceptions_for_real_artifacts(tmp_path: Path) -> None:
    """BL28: Verification must not hard-code exceptions for specific review artifacts."""
    repo = _create_temp_repo(tmp_path)

    # Create a file that looks like a review artifact
    review_artifact = repo / "docs" / "reviews" / "test_review.md"
    review_artifact.parent.mkdir(parents=True, exist_ok=True)
    review_artifact.write_text("test review content\n")

    # Without exclusion, this untracked file should not cause baseline failure
    baseline = _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )

    assert isinstance(baseline, WorkspaceBaseline)

    # Now test that it CAN be excluded if needed
    baseline_with_exclusion = _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=["docs/reviews/test_review.md"],
        captured_at=VALID_TIMESTAMP,
    )

    assert "docs/reviews/test_review.md" in baseline_with_exclusion.baseline_exclusions


# ---------------------------------------------------------------------------
# Test: Multiple dirty files
# ---------------------------------------------------------------------------


def test_BL29_multiple_dirty_files_all_reported(tmp_path: Path) -> None:
    """BL29: When multiple tracked files are dirty, error should mention at least some."""
    repo = _create_temp_repo(tmp_path)

    # Create and commit multiple files
    for i in range(5):
        (repo / f"file{i}.txt").write_text(f"content {i}\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "Add multiple files")

    # Modify all of them
    for i in range(5):
        (repo / f"file{i}.txt").write_text(f"modified {i}\n")

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_DIRTY_BASELINE
    error_msg = str(exc_info.value)
    assert any(f"file{i}.txt" in error_msg for i in range(5))


# ---------------------------------------------------------------------------
# Test: Empty repository
# ---------------------------------------------------------------------------


def test_BL30_empty_repository_with_no_commits(tmp_path: Path) -> None:
    """BL30: Repository with no commits should fail (no HEAD to parse)."""
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    _git(repo, "init")

    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_INTERNAL_ERROR


# ---------------------------------------------------------------------------
# Test: Ignored files behavior
# ---------------------------------------------------------------------------


def test_BL31_ignored_files_outside_scope(tmp_path: Path) -> None:
    """BL31: Ignored files (via .gitignore) should not cause baseline failure."""
    repo = _create_temp_repo(tmp_path)

    # Create .gitignore
    (repo / ".gitignore").write_text("*.log\n")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "Add gitignore")

    # Create ignored file
    (repo / "test.log").write_text("log content\n")

    # Baseline should succeed (ignored file is outside scope)
    baseline = _verify_clean_tracked_baseline(
        repo_root=repo,
        baseline_exclusions=[],
        captured_at=VALID_TIMESTAMP,
    )

    assert isinstance(baseline, WorkspaceBaseline)


def test_BL32_worktree_typechange_rejected(tmp_path: Path) -> None:
    """BL32: Worktree typechange (Y='T') should cause ADAPTER_DIRTY_BASELINE."""
    repo = _create_temp_repo(tmp_path)

    # Create and commit a regular file
    regular_file = repo / "regular.txt"
    regular_file.write_text("original content\n")
    _git(repo, "add", "regular.txt")
    _git(repo, "commit", "-m", "Add regular file")

    # Replace regular file with a symlink (typechange)
    regular_file.unlink()
    regular_file.symlink_to("/tmp/nonexistent_target")

    # Verify raw porcelain reports Y='T'
    result = subprocess.run(
        ["git", "status", "--porcelain=v1", "-uall"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )
    assert " T regular.txt" in result.stdout or "T regular.txt" in result.stdout

    # Baseline should reject the typechange
    with pytest.raises(BaselineVerificationError) as exc_info:
        _verify_clean_tracked_baseline(
            repo_root=repo,
            baseline_exclusions=[],
            captured_at=VALID_TIMESTAMP,
        )

    assert exc_info.value.adapter_status == ADAPTER_DIRTY_BASELINE
    assert "regular.txt" in str(exc_info.value)

    # Verify repository state is not mutated
    _git(repo, "status")  # Should succeed
    current_head = (repo / ".git" / "HEAD").read_text()
    assert "ref:" in current_head or len(current_head.strip()) == 40  # Valid HEAD


# ===========================================================================
# SLICE 3: Post-run workspace inventory tests (67 tests)
# ===========================================================================


def test_parse_porcelain_status_z_empty() -> None:
    """Parse empty porcelain status."""
    added, modified, deleted = _parse_porcelain_status_z(b"")
    assert added == []
    assert modified == []
    assert deleted == []


def test_parse_porcelain_status_z_added_tracked() -> None:
    """Parse added tracked file from porcelain status."""
    added, modified, deleted = _parse_porcelain_status_z(b"A  new.txt\0")
    assert added == ["new.txt"]
    assert modified == []
    assert deleted == []


def test_parse_porcelain_status_z_modified_tracked() -> None:
    """Parse modified tracked file from porcelain status."""
    added, modified, deleted = _parse_porcelain_status_z(b"M  mod.txt\0")
    assert added == []
    assert modified == ["mod.txt"]
    assert deleted == []


def test_parse_porcelain_status_z_deleted_tracked() -> None:
    """Parse deleted tracked file from porcelain status."""
    added, modified, deleted = _parse_porcelain_status_z(b"D  del.txt\0")
    assert added == []
    assert modified == []
    assert deleted == ["del.txt"]


def test_parse_porcelain_status_z_staged_modification() -> None:
    """Parse staged modification (M in index, M in working tree)."""
    added, modified, deleted = _parse_porcelain_status_z(b"MM staged.txt\0")
    assert added == []
    assert modified == ["staged.txt"]
    assert deleted == []


def test_parse_porcelain_status_z_rename_normalized() -> None:
    """Rename is normalized to delete + add."""
    added, modified, deleted = _parse_porcelain_status_z(b"R  new.txt\0old.txt\0")
    assert added == ["new.txt"]
    assert modified == []
    assert deleted == ["old.txt"]


def test_parse_porcelain_status_z_copy_normalized() -> None:
    """Copy is normalized to add only."""
    added, modified, deleted = _parse_porcelain_status_z(b"C  dst.txt\0src.txt\0")
    assert added == ["dst.txt"]
    assert modified == []
    assert deleted == []


def test_parse_porcelain_status_z_typechange_normalized() -> None:
    """Typechange is normalized to delete + add."""
    added, modified, deleted = _parse_porcelain_status_z(b"T  file.txt\0")
    assert added == ["file.txt"]
    assert modified == []
    assert deleted == ["file.txt"]


def test_parse_porcelain_status_z_multiple_changes() -> None:
    """Parse multiple changes from porcelain status."""
    data = b"A  new.txt\0M  mod.txt\0D  del.txt\0"
    added, modified, deleted = _parse_porcelain_status_z(data)
    assert added == ["new.txt"]
    assert modified == ["mod.txt"]
    assert deleted == ["del.txt"]


def test_parse_porcelain_status_z_unmerged_error() -> None:
    """Unmerged file raises error."""
    with pytest.raises(BaselineVerificationError, match="unmerged"):
        _parse_porcelain_status_z(b"UU conflict.txt\0")


def test_parse_porcelain_status_z_unmerged_aa() -> None:
    """AA (both added) raises error."""
    with pytest.raises(BaselineVerificationError, match="unmerged"):
        _parse_porcelain_status_z(b"AA new.txt\0")


def test_parse_porcelain_status_z_unmerged_dd() -> None:
    """DD (both deleted) raises error."""
    with pytest.raises(BaselineVerificationError, match="unmerged"):
        _parse_porcelain_status_z(b"DD file.txt\0")


def test_parse_porcelain_status_z_unmerged_au() -> None:
    """AU (added by us) raises error."""
    with pytest.raises(BaselineVerificationError, match="unmerged"):
        _parse_porcelain_status_z(b"AU file.txt\0")


def test_parse_porcelain_status_z_unmerged_ud() -> None:
    """UD (updated by them, deleted by us) raises error."""
    with pytest.raises(BaselineVerificationError, match="unmerged"):
        _parse_porcelain_status_z(b"UD file.txt\0")


def test_parse_porcelain_status_z_unmerged_ua() -> None:
    """UA (updated by us, added by them) raises error."""
    with pytest.raises(BaselineVerificationError, match="unmerged"):
        _parse_porcelain_status_z(b"UA file.txt\0")


def test_parse_porcelain_status_z_unmerged_du() -> None:
    """DU (deleted by us, updated by them) raises error."""
    with pytest.raises(BaselineVerificationError, match="unmerged"):
        _parse_porcelain_status_z(b"DU file.txt\0")


def test_parse_porcelain_status_z_unicode_filename() -> None:
    """Parse Unicode filename from porcelain status."""
    added, modified, deleted = _parse_porcelain_status_z("M  文件.txt\0".encode())
    assert added == []
    assert modified == ["文件.txt"]
    assert deleted == []


def test_parse_porcelain_status_z_invalid_utf8() -> None:
    """Invalid UTF-8 raises error."""
    with pytest.raises(BaselineVerificationError, match="UTF-8"):
        _parse_porcelain_status_z(b"M  \xff\xfe.txt\0")


def test_parse_porcelain_status_z_trailing_empty() -> None:
    """Trailing empty part is ignored."""
    _added, modified, _deleted = _parse_porcelain_status_z(b"M  file.txt\0")
    assert modified == ["file.txt"]


def test_parse_porcelain_status_z_malformed_entry() -> None:
    """Malformed entry raises error."""
    with pytest.raises(BaselineVerificationError, match="malformed"):
        _parse_porcelain_status_z(b"XY\0")


def test_parse_porcelain_status_z_rename_missing_second() -> None:
    """Rename with missing second path raises error."""
    with pytest.raises(BaselineVerificationError, match="rename/copy"):
        _parse_porcelain_status_z(b"R  old.txt\0")


def test_parse_ls_files_others_z_empty() -> None:
    """Parse empty ls-files output."""
    result = _parse_ls_files_others_z(b"")
    assert result == []


def test_parse_ls_files_others_z_single_file() -> None:
    """Parse single untracked file."""
    result = _parse_ls_files_others_z(b"untracked.txt\0")
    assert result == ["untracked.txt"]


def test_parse_ls_files_others_z_multiple_files() -> None:
    """Parse multiple untracked files."""
    result = _parse_ls_files_others_z(b"a.txt\0b.txt\0c.txt\0")
    assert result == ["a.txt", "b.txt", "c.txt"]


def test_parse_ls_files_others_z_unicode() -> None:
    """Parse Unicode filename from ls-files."""
    result = _parse_ls_files_others_z("文件.txt\0".encode())
    assert result == ["文件.txt"]


def test_parse_ls_files_others_z_invalid_utf8() -> None:
    """Invalid UTF-8 raises error."""
    with pytest.raises(BaselineVerificationError, match="UTF-8"):
        _parse_ls_files_others_z(b"\xff\xfe.txt\0")


def test_parse_ls_files_others_z_trailing_empty() -> None:
    """Trailing empty part is ignored."""
    result = _parse_ls_files_others_z(b"file.txt\0\0")
    assert result == ["file.txt"]


def test_validate_inventory_path_valid() -> None:
    """Valid path passes validation."""
    _validate_inventory_path("path/to/file.txt", "test")


def test_validate_inventory_path_empty() -> None:
    """Empty path is rejected."""
    with pytest.raises(BaselineVerificationError, match="empty"):
        _validate_inventory_path("", "test")


def test_validate_inventory_path_absolute() -> None:
    """Absolute path is rejected."""
    with pytest.raises(BaselineVerificationError, match="absolute"):
        _validate_inventory_path("/absolute/path.txt", "test")


def test_validate_inventory_path_parent_traversal() -> None:
    """Parent traversal is rejected."""
    with pytest.raises(BaselineVerificationError, match="traversal"):
        _validate_inventory_path("../escape.txt", "test")


def test_validate_inventory_path_null_byte() -> None:
    """Null byte is rejected."""
    with pytest.raises(BaselineVerificationError, match="null"):
        _validate_inventory_path("path\0escape.txt", "test")


def test_validate_inventory_path_windows_drive() -> None:
    """Windows drive letter is rejected."""
    with pytest.raises(BaselineVerificationError, match="drive"):
        _validate_inventory_path("C:/path.txt", "test")


def test_validate_inventory_path_unc() -> None:
    """UNC path is rejected."""
    with pytest.raises(BaselineVerificationError, match="UNC"):
        _validate_inventory_path("\\\\server\\share\\file.txt", "test")


def test_validate_inventory_path_backslash() -> None:
    """Backslash is rejected."""
    with pytest.raises(BaselineVerificationError, match="backslash"):
        _validate_inventory_path("path\\to\\file.txt", "test")


def test_validate_inventory_path_double_slash() -> None:
    """Double slash is rejected."""
    with pytest.raises(BaselineVerificationError, match="duplicate"):
        _validate_inventory_path("path//file.txt", "test")


def test_validate_inventory_path_dot_segment() -> None:
    """Dot segment is rejected."""
    with pytest.raises(BaselineVerificationError, match="segment"):
        _validate_inventory_path("./file.txt", "test")


def test_validate_inventory_path_empty_segment() -> None:
    """Empty segment is rejected."""
    with pytest.raises(BaselineVerificationError, match="duplicate separator"):
        _validate_inventory_path("path//file.txt", "test")


def test_validate_inventory_path_too_long() -> None:
    """Path exceeding 512 bytes is rejected."""
    long_path = "a" * 513
    with pytest.raises(BaselineVerificationError, match="exceeds 512"):
        _validate_inventory_path(long_path, "test")


def test_validate_inventory_path_exactly_512_bytes() -> None:
    """Path exactly 512 bytes is accepted."""
    path_512 = "a" * 512
    _validate_inventory_path(path_512, "test")


def test_validate_inventory_paths_all_valid() -> None:
    """All valid paths pass validation."""
    _validate_inventory_paths(
        added=["new.txt"],
        modified=["mod.txt"],
        deleted=["old.txt"],
        untracked=["untracked.txt"],
    )


def test_validate_inventory_paths_invalid_in_added() -> None:
    """Invalid path in added raises error."""
    with pytest.raises(BaselineVerificationError, match="added"):
        _validate_inventory_paths(
            added=["/absolute/path.txt"],
            modified=[],
            deleted=[],
            untracked=[],
        )


def test_validate_inventory_paths_invalid_in_modified() -> None:
    """Invalid path in modified raises error."""
    with pytest.raises(BaselineVerificationError, match="modified"):
        _validate_inventory_paths(
            added=[],
            modified=["/absolute/path.txt"],
            deleted=[],
            untracked=[],
        )


def test_validate_inventory_paths_invalid_in_deleted() -> None:
    """Invalid path in deleted raises error."""
    with pytest.raises(BaselineVerificationError, match="deleted"):
        _validate_inventory_paths(
            added=[],
            modified=[],
            deleted=["/absolute/path.txt"],
            untracked=[],
        )


def test_validate_inventory_paths_invalid_in_untracked() -> None:
    """Invalid path in untracked raises error."""
    with pytest.raises(BaselineVerificationError, match="untracked"):
        _validate_inventory_paths(
            added=[],
            modified=[],
            deleted=[],
            untracked=["/absolute/path.txt"],
        )


def test_deduplicate_and_sort_empty() -> None:
    """Empty list returns empty list."""
    result = _deduplicate_and_sort([])
    assert result == []


def test_deduplicate_and_sort_no_duplicates() -> None:
    """No duplicates, sorted."""
    result = _deduplicate_and_sort(["c", "a", "b"])
    assert result == ["a", "b", "c"]


def test_deduplicate_and_sort_with_duplicates() -> None:
    """Duplicates removed, sorted."""
    result = _deduplicate_and_sort(["b", "a", "b", "c", "a"])
    assert result == ["a", "b", "c"]


def test_deduplicate_and_sort_preserves_unicode() -> None:
    """Unicode paths preserved."""
    result = _deduplicate_and_sort(["文件.txt", "αβγ.txt", "文件.txt"])
    assert result == ["αβγ.txt", "文件.txt"]


def test_capture_post_run_workspace_clean(tmp_path: Path) -> None:
    """Clean workspace produces empty inventory."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert post_sha == baseline_sha
    assert stable is True
    assert change.added == []
    assert change.modified == []
    assert change.deleted == []
    assert change.untracked == []


def test_capture_post_run_workspace_modified_tracked(tmp_path: Path) -> None:
    """Modified tracked file detected."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "initial.txt").write_text("modified content")

    post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert post_sha == baseline_sha
    assert stable is True
    assert change.modified == ["initial.txt"]


def test_capture_post_run_workspace_added_tracked(tmp_path: Path) -> None:
    """Added (staged) tracked file detected."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "new.txt").write_text("new content")
    _git(repo, "add", "new.txt")

    post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert post_sha == baseline_sha
    assert stable is True
    assert change.added == ["new.txt"]


def test_capture_post_run_workspace_deleted_tracked(tmp_path: Path) -> None:
    """Deleted tracked file detected."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "initial.txt").unlink()

    post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert post_sha == baseline_sha
    assert stable is True
    assert change.deleted == ["initial.txt"]


def test_capture_post_run_workspace_rename_normalized(tmp_path: Path) -> None:
    """Rename normalized to delete old + add new."""
    repo = _create_temp_repo(tmp_path)

    (repo / "old.txt").write_text("content to rename")
    _git(repo, "add", "old.txt")
    _git(repo, "commit", "-m", "Add old.txt")

    baseline_sha = _get_head_sha(repo)

    (repo / "old.txt").rename(repo / "new.txt")
    _git(repo, "add", "-A")

    post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert post_sha == baseline_sha
    assert stable is True
    assert change.added == ["new.txt"]
    assert change.deleted == ["old.txt"]


def test_capture_post_run_workspace_untracked_file(tmp_path: Path) -> None:
    """Untracked file detected."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "untracked.txt").write_text("untracked content")

    post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert post_sha == baseline_sha
    assert stable is True
    assert change.untracked == ["untracked.txt"]


def test_capture_post_run_workspace_baseline_exclusion(tmp_path: Path) -> None:
    """Baseline exclusion removes untracked file from inventory."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "untracked.txt").write_text("untracked content")

    post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=["untracked.txt"],
    )

    assert post_sha == baseline_sha
    assert stable is True
    assert change.untracked == []


def test_capture_post_run_workspace_source_revision_drift(tmp_path: Path) -> None:
    """Source revision drift detected."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "new.txt").write_text("new content")
    _git(repo, "add", "new.txt")
    _git(repo, "commit", "-m", "Add new file")

    post_sha, stable, _change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert post_sha != baseline_sha
    assert stable is False


def test_capture_post_run_workspace_multiple_changes(tmp_path: Path) -> None:
    """Multiple changes detected and sorted."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "initial.txt").write_text("modified")
    (repo / "new1.txt").write_text("new 1")
    (repo / "new2.txt").write_text("new 2")
    (repo / "untracked.txt").write_text("untracked")
    _git(repo, "add", "new1.txt", "new2.txt")

    post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert post_sha == baseline_sha
    assert stable is True
    assert change.added == ["new1.txt", "new2.txt"]
    assert change.modified == ["initial.txt"]
    assert change.untracked == ["untracked.txt"]


def test_capture_post_run_workspace_unicode_filename(tmp_path: Path) -> None:
    """Unicode filename handled correctly."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "文件.txt").write_text("unicode content")

    post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert post_sha == baseline_sha
    assert stable is True
    assert change.untracked == ["文件.txt"]


def test_capture_post_run_workspace_special_characters(tmp_path: Path) -> None:
    """Special characters in filename handled correctly."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "file with spaces.txt").write_text("spaces")
    (repo / "file-with-dashes.txt").write_text("dashes")
    (repo / "file_with_underscores.txt").write_text("underscores")

    post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert post_sha == baseline_sha
    assert stable is True
    assert "file with spaces.txt" in change.untracked
    assert "file-with-dashes.txt" in change.untracked
    assert "file_with_underscores.txt" in change.untracked


def test_capture_post_run_workspace_invalid_baseline_sha(tmp_path: Path) -> None:
    """Invalid baseline SHA raises error."""
    repo = _create_temp_repo(tmp_path)

    with pytest.raises(BaselineVerificationError, match="baseline_source_revision"):
        _capture_post_run_workspace(
            repo_root=repo,
            baseline_source_revision="invalid_sha",
            baseline_exclusions=[],
        )


def test_capture_post_run_workspace_repo_not_directory(tmp_path: Path) -> None:
    """Non-directory repo_root raises error."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    file_path = repo / "initial.txt"

    with pytest.raises(BaselineVerificationError, match="directory"):
        _capture_post_run_workspace(
            repo_root=file_path,
            baseline_source_revision=baseline_sha,
            baseline_exclusions=[],
        )


def test_capture_post_run_workspace_repo_not_exists(tmp_path: Path) -> None:
    """Non-existent repo_root raises error."""
    fake_path = tmp_path / "nonexistent"

    with pytest.raises(BaselineVerificationError, match="exist"):
        _capture_post_run_workspace(
            repo_root=fake_path,
            baseline_source_revision="a" * 40,
            baseline_exclusions=[],
        )


def test_capture_post_run_workspace_deterministic_ordering(tmp_path: Path) -> None:
    """Results are deterministically ordered."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "zebra.txt").write_text("z")
    (repo / "alpha.txt").write_text("a")
    (repo / "middle.txt").write_text("m")

    _post_sha, _stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert change.untracked == ["alpha.txt", "middle.txt", "zebra.txt"]


def test_capture_post_run_workspace_no_duplicates(tmp_path: Path) -> None:
    """No duplicates in results."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "untracked.txt").write_text("content")

    _post_sha, _stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert change.untracked == ["untracked.txt"]
    assert len(change.untracked) == len(set(change.untracked))


def test_capture_post_run_workspace_tab_in_filename(tmp_path: Path) -> None:
    """Filename containing tab handled correctly."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "file\twith\ttabs.txt").write_text("tab content")

    _post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert stable is True
    assert change.untracked == ["file\twith\ttabs.txt"]


def test_capture_post_run_workspace_newline_in_filename(tmp_path: Path) -> None:
    """Filename containing newline handled correctly."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "file\nwith\nnewlines.txt").write_text("newline content")

    _post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert stable is True
    assert change.untracked == ["file\nwith\nnewlines.txt"]


def test_capture_post_run_workspace_quote_in_filename(tmp_path: Path) -> None:
    """Filename containing quotes handled correctly."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / 'file"with"quotes.txt').write_text("quote content")

    _post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert stable is True
    assert change.untracked == ['file"with"quotes.txt']


def test_capture_post_run_workspace_backslash_in_filename(tmp_path: Path) -> None:
    """Filename containing backslash raises error."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "file\\with\\backslashes.txt").write_text("backslash content")

    with pytest.raises(BaselineVerificationError, match="backslash"):
        _capture_post_run_workspace(
            repo_root=repo,
            baseline_source_revision=baseline_sha,
            baseline_exclusions=[],
        )


def test_capture_post_run_workspace_arrow_in_filename(tmp_path: Path) -> None:
    """Filename containing literal ' -> ' handled correctly."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "file -> renamed.txt").write_text("arrow content")

    _post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert stable is True
    assert change.untracked == ["file -> renamed.txt"]


def test_capture_post_run_workspace_ignored_file_excluded(tmp_path: Path) -> None:
    """Ignored files excluded from untracked."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / ".gitignore").write_text("*.ignored\n")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "Add gitignore")
    baseline_sha = _get_head_sha(repo)

    (repo / "normal.txt").write_text("normal")
    (repo / "secret.ignored").write_text("should be ignored")

    _post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert stable is True
    assert "normal.txt" in change.untracked
    assert "secret.ignored" not in change.untracked


def test_capture_post_run_workspace_typechange_classification(tmp_path: Path) -> None:
    """Typechange classified as delete + add."""
    repo = _create_temp_repo(tmp_path)

    (repo / "target.txt").write_text("content")
    _git(repo, "add", "target.txt")
    _git(repo, "commit", "-m", "Add target.txt")
    baseline_sha = _get_head_sha(repo)

    (repo / "target.txt").unlink()
    (repo / "target.txt").symlink_to("other.txt")
    _git(repo, "add", "target.txt")

    _post_sha, stable, change = _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    assert stable is True
    assert "target.txt" in change.deleted
    assert "target.txt" in change.added


def test_capture_post_run_workspace_repository_unchanged(tmp_path: Path) -> None:
    """Repository state unchanged after capture."""
    repo = _create_temp_repo(tmp_path)
    baseline_sha = _get_head_sha(repo)

    (repo / "tracked.txt").write_text("modified")
    (repo / "untracked.txt").write_text("new file")

    result_before = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    status_before = result_before.stdout

    _capture_post_run_workspace(
        repo_root=repo,
        baseline_source_revision=baseline_sha,
        baseline_exclusions=[],
    )

    result_after = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    status_after = result_after.stdout

    assert status_before == status_after
    assert _get_head_sha(repo) == baseline_sha


# --- Bounded Subprocess Capture Tests ---


def test_run_git_subprocess_normal_command() -> None:
    """_run_git_subprocess returns output for normal command."""
    stdout, stderr, returncode = _run_git_subprocess(
        ["--version"],
        cwd=Path("/tmp"),
        timeout_seconds=5.0,
        max_stdout_bytes=1_000_000,
    )
    assert returncode == 0
    assert b"git version" in stdout
    assert stderr == b""


def test_run_git_subprocess_timeout_enforcement(tmp_path: Path) -> None:
    """_run_git_subprocess terminates process on timeout."""
    # Create a fake 'git' executable that sleeps longer than the timeout.
    # This removes all dependency on real Git speed or repository size.
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text("#!/bin/sh\nsleep 5\n")
    fake_git.chmod(0o755)

    # Prepend fake bin to PATH so _run_git_subprocess finds our fake first.
    import os
    original_path = os.environ.get("PATH", "")

    # _run_git_subprocess builds its own env with PATH from os.environ.
    # We patch os.environ temporarily.
    patched_path = str(fake_bin) + os.pathsep + original_path
    old_env_path = os.environ.get("PATH")
    os.environ["PATH"] = patched_path

    try:
        with pytest.raises(BaselineVerificationError, match="timed out"):
            _run_git_subprocess(
                ["log", "--stat", "--all"],
                cwd=tmp_path,
                timeout_seconds=0.1,  # 100ms — fake sleeps 5s, guaranteed timeout
                max_stdout_bytes=100_000_000,
            )
    finally:
        if old_env_path is not None:
            os.environ["PATH"] = old_env_path
        else:
            os.environ.pop("PATH", None)


def test_run_git_subprocess_stdout_limit_enforcement() -> None:
    """_run_git_subprocess terminates when stdout exceeds limit."""
    # Create a real git repo with lots of output
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        repo = Path(tmpdir)
        # Initialize repo with some commits
        _run_git_command(["init"], cwd=repo)
        _run_git_command(["config", "user.email", "test@example.com"], cwd=repo)
        _run_git_command(["config", "user.name", "Test User"], cwd=repo)
        (repo / "file.txt").write_text("content")
        _run_git_command(["add", "file.txt"], cwd=repo)
        _run_git_command(["commit", "-m", "initial"], cwd=repo)

        # Generate output larger than the limit allows
        with pytest.raises(BaselineVerificationError, match="stdout exceeded"):
            _run_git_subprocess(
                ["log", "--all", "--oneline"],
                cwd=repo,
                timeout_seconds=5.0,
                max_stdout_bytes=10,  # Very small limit
            )


def test_run_git_subprocess_stderr_limit_enforcement() -> None:
    """_run_git_subprocess terminates when stderr exceeds limit."""
    # Generate error output
    with pytest.raises(BaselineVerificationError, match="stderr exceeded"):
        _run_git_subprocess(
            ["invalid-command-that-does-not-exist"],
            cwd=Path("/tmp"),
            timeout_seconds=5.0,
            max_stdout_bytes=1_000_000,
            max_stderr_bytes=10,  # Very small limit
        )


def test_run_git_subprocess_returns_bytes() -> None:
    """_run_git_subprocess returns bytes, not str."""
    stdout, stderr, returncode = _run_git_subprocess(
        ["--version"],
        cwd=Path("/tmp"),
        timeout_seconds=5.0,
        max_stdout_bytes=1_000_000,
    )
    assert isinstance(stdout, bytes)
    assert isinstance(stderr, bytes)
    assert isinstance(returncode, int)


def test_run_git_command_uses_bounded_subprocess(tmp_path: Path) -> None:
    """_run_git_command uses _run_git_subprocess internally."""
    # This is an integration test - verify it works with a real git repo
    repo = tmp_path / "test_repo"
    repo.mkdir()
    _run_git_command(["init"], cwd=repo)

    # Verify the repo was initialized
    result = _run_git_command(["status"], cwd=repo)
    assert "No commits yet" in result or "No branches" in result or "Initial commit" in result or result.strip() == ""


# ---------------------------------------------------------------------------
# Block A: Reconciliation tests
# ---------------------------------------------------------------------------


def test_block_a_reconcile_empty_declared_empty_actual() -> None:
    """Block A: empty declared and empty actual → exact_match=True."""
    workspace_change = WorkspaceChange(
        added=[], modified=[], deleted=[], untracked=[]
    )
    result = _reconcile_changes([], workspace_change)

    assert result.declared_files == []
    assert result.actual_files == []
    assert result.undeclared_changes == []
    assert result.declared_but_missing == []
    assert result.exact_match is True


def test_block_a_reconcile_exact_modified() -> None:
    """Block A: declared matches actual modified → exact_match=True."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/test.py"], deleted=[], untracked=[]
    )
    result = _reconcile_changes(["backend/test.py"], workspace_change)

    assert result.declared_files == ["backend/test.py"]
    assert result.actual_files == ["backend/test.py"]
    assert result.undeclared_changes == []
    assert result.declared_but_missing == []
    assert result.exact_match is True


def test_block_a_reconcile_exact_added() -> None:
    """Block A: declared matches actual added → exact_match=True."""
    workspace_change = WorkspaceChange(
        added=["backend/new.py"], modified=[], deleted=[], untracked=[]
    )
    result = _reconcile_changes(["backend/new.py"], workspace_change)

    assert result.declared_files == ["backend/new.py"]
    assert result.actual_files == ["backend/new.py"]
    assert result.exact_match is True


def test_block_a_reconcile_exact_deleted() -> None:
    """Block A: declared matches actual deleted → exact_match=True."""
    workspace_change = WorkspaceChange(
        added=[], modified=[], deleted=["backend/old.py"], untracked=[]
    )
    result = _reconcile_changes(["backend/old.py"], workspace_change)

    assert result.declared_files == ["backend/old.py"]
    assert result.actual_files == ["backend/old.py"]
    assert result.exact_match is True


def test_block_a_reconcile_exact_untracked() -> None:
    """Block A: declared matches actual untracked → exact_match=True."""
    workspace_change = WorkspaceChange(
        added=[], modified=[], deleted=[], untracked=["backend/untracked.py"]
    )
    result = _reconcile_changes(["backend/untracked.py"], workspace_change)

    assert result.declared_files == ["backend/untracked.py"]
    assert result.actual_files == ["backend/untracked.py"]
    assert result.exact_match is True


def test_block_a_reconcile_exact_mixed_categories() -> None:
    """Block A: declared matches mixed actual categories → exact_match=True."""
    workspace_change = WorkspaceChange(
        added=["backend/added.py"],
        modified=["backend/modified.py"],
        deleted=["backend/deleted.py"],
        untracked=["backend/untracked.py"],
    )
    declared = [
        "backend/added.py",
        "backend/modified.py",
        "backend/deleted.py",
        "backend/untracked.py",
    ]
    result = _reconcile_changes(declared, workspace_change)

    assert result.declared_files == sorted(declared)
    assert result.actual_files == sorted(declared)
    assert result.exact_match is True


def test_block_a_reconcile_undeclared_modified() -> None:
    """Block A: actual has extra modified file → undeclared_changes non-empty."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/test.py", "backend/extra.py"], deleted=[], untracked=[]
    )
    result = _reconcile_changes(["backend/test.py"], workspace_change)

    assert result.undeclared_changes == ["backend/extra.py"]
    assert result.declared_but_missing == []
    assert result.exact_match is False


def test_block_a_reconcile_undeclared_untracked() -> None:
    """Block A: actual has extra untracked file → undeclared_changes non-empty."""
    workspace_change = WorkspaceChange(
        added=[], modified=[], deleted=[], untracked=["backend/test.py", "backend/extra.py"]
    )
    result = _reconcile_changes(["backend/test.py"], workspace_change)

    assert result.undeclared_changes == ["backend/extra.py"]
    assert result.declared_but_missing == []
    assert result.exact_match is False


def test_block_a_reconcile_declared_missing() -> None:
    """Block A: declared has extra file not in actual → declared_but_missing non-empty."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/test.py"], deleted=[], untracked=[]
    )
    result = _reconcile_changes(["backend/test.py", "backend/missing.py"], workspace_change)

    assert result.undeclared_changes == []
    assert result.declared_but_missing == ["backend/missing.py"]
    assert result.exact_match is False


def test_block_a_reconcile_both_undeclared_and_missing() -> None:
    """Block A: both undeclared and declared_missing → both lists non-empty."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/test.py", "backend/extra.py"], deleted=[], untracked=[]
    )
    result = _reconcile_changes(
        ["backend/test.py", "backend/missing.py"], workspace_change
    )

    assert result.undeclared_changes == ["backend/extra.py"]
    assert result.declared_but_missing == ["backend/missing.py"]
    assert result.exact_match is False


def test_block_a_reconcile_rename_requires_both_paths() -> None:
    """Block A: rename normalization means both old and new paths in actual."""
    # Rename: old.py → new.py (deleted + added)
    workspace_change = WorkspaceChange(
        added=["backend/new.py"], modified=[], deleted=["backend/old.py"], untracked=[]
    )
    # Actor must declare both paths
    result = _reconcile_changes(
        ["backend/old.py", "backend/new.py"], workspace_change
    )

    assert result.exact_match is True

    # If actor declares only new path → old is undeclared
    result2 = _reconcile_changes(["backend/new.py"], workspace_change)
    assert result2.undeclared_changes == ["backend/old.py"]
    assert result2.declared_but_missing == []
    assert result2.exact_match is False


def test_block_a_reconcile_stable_sorted_output() -> None:
    """Block A: output is deterministically sorted."""
    workspace_change = WorkspaceChange(
        added=["z.py", "a.py"], modified=["m.py"], deleted=[], untracked=[]
    )
    result = _reconcile_changes(["z.py", "a.py", "m.py"], workspace_change)

    assert result.declared_files == ["a.py", "m.py", "z.py"]
    assert result.actual_files == ["a.py", "m.py", "z.py"]
    assert result.exact_match is True


def test_block_a_reconcile_duplicate_rejection() -> None:
    """Block A: duplicate paths in declared are rejected by WP-AL-1C4 validation."""
    # This test verifies that duplicates would be caught upstream
    # The reconcile function itself deduplicates via set operations
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/test.py"], deleted=[], untracked=[]
    )
    # Even if caller passes duplicates, set() deduplicates
    result = _reconcile_changes(
        ["backend/test.py", "backend/test.py"], workspace_change
    )

    assert result.declared_files == ["backend/test.py"]
    assert result.actual_files == ["backend/test.py"]
    assert result.exact_match is True


# ---------------------------------------------------------------------------
# Block A: Permission enforcement tests
# ---------------------------------------------------------------------------


def test_block_a_permissions_exact_allowed_match() -> None:
    """Block A: exact path matches allowed pattern → permitted."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/test.py"], deleted=[], untracked=[]
    )
    allowed, forbidden = _enforce_permissions(
        workspace_change,
        allowed_paths=["backend/test.py"],
        forbidden_paths=[],
    )

    assert allowed == []
    assert forbidden == []


def test_block_a_permissions_gitwildmatch_allowed_match() -> None:
    """Block A: gitwildmatch pattern matches → permitted."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/test.py", "backend/utils.py"], deleted=[], untracked=[]
    )
    allowed, forbidden = _enforce_permissions(
        workspace_change,
        allowed_paths=["backend/*.py"],
        forbidden_paths=[],
    )

    assert allowed == []
    assert forbidden == []


def test_block_a_permissions_outside_allowed_paths() -> None:
    """Block A: path outside allowed patterns → allowed_violation."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/test.py", "frontend/app.py"], deleted=[], untracked=[]
    )
    allowed, forbidden = _enforce_permissions(
        workspace_change,
        allowed_paths=["backend/*.py"],
        forbidden_paths=[],
    )

    assert allowed == ["frontend/app.py"]
    assert forbidden == []


def test_block_a_permissions_exact_forbidden_match() -> None:
    """Block A: exact path matches forbidden pattern → forbidden_violation."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/secret.py"], deleted=[], untracked=[]
    )
    allowed, forbidden = _enforce_permissions(
        workspace_change,
        allowed_paths=["backend/*.py"],
        forbidden_paths=["backend/secret.py"],
    )

    assert allowed == []
    assert forbidden == ["backend/secret.py"]


def test_block_a_permissions_forbidden_wildcard() -> None:
    """Block A: forbidden wildcard pattern matches → forbidden_violation."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/test.py", "backend/secret.py"], deleted=[], untracked=[]
    )
    allowed, forbidden = _enforce_permissions(
        workspace_change,
        allowed_paths=["backend/*.py"],
        forbidden_paths=["**/secret.py"],
    )

    assert allowed == []
    assert forbidden == ["backend/secret.py"]


def test_block_a_permissions_allowed_and_forbidden_overlap() -> None:
    """Block A: path matches both allowed and forbidden → forbidden wins."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/test.py"], deleted=[], untracked=[]
    )
    allowed, forbidden = _enforce_permissions(
        workspace_change,
        allowed_paths=["backend/*.py"],
        forbidden_paths=["backend/test.py"],
    )

    assert allowed == []
    assert forbidden == ["backend/test.py"]


def test_block_a_permissions_forbidden_wins() -> None:
    """Block A: forbidden takes precedence over allowed."""
    workspace_change = WorkspaceChange(
        added=[], modified=["backend/secret.py"], deleted=[], untracked=[]
    )
    allowed, forbidden = _enforce_permissions(
        workspace_change,
        allowed_paths=["backend/*"],
        forbidden_paths=["backend/*"],
    )

    assert allowed == []
    assert forbidden == ["backend/secret.py"]


def test_block_a_permissions_deleted_path_enforcement() -> None:
    """Block A: deleted paths are enforced."""
    workspace_change = WorkspaceChange(
        added=[], modified=[], deleted=["backend/old.py"], untracked=[]
    )
    allowed, forbidden = _enforce_permissions(
        workspace_change,
        allowed_paths=["backend/*.py"],
        forbidden_paths=[],
    )

    assert allowed == []
    assert forbidden == []


def test_block_a_permissions_untracked_path_enforcement() -> None:
    """Block A: untracked paths are enforced."""
    workspace_change = WorkspaceChange(
        added=[], modified=[], deleted=[], untracked=["backend/untracked.py"]
    )
    allowed, forbidden = _enforce_permissions(
        workspace_change,
        allowed_paths=["backend/*.py"],
        forbidden_paths=[],
    )

    assert allowed == []
    assert forbidden == []


def test_block_a_permissions_deterministic_ordering() -> None:
    """Block A: violations are sorted deterministically."""
    workspace_change = WorkspaceChange(
        added=[],
        modified=["z.py", "a.py", "m.py"],
        deleted=[],
        untracked=[],
    )
    allowed, forbidden = _enforce_permissions(
        workspace_change,
        allowed_paths=["other/*.py"],  # No matches → all are violations
        forbidden_paths=[],
    )

    # No allowed pattern matches → all are allowed_violations
    assert allowed == ["a.py", "m.py", "z.py"]
    assert forbidden == []


# ---------------------------------------------------------------------------
# Block A: Identity validation tests
# ---------------------------------------------------------------------------


def test_block_a_identity_all_fields_match() -> None:
    """Block A: all identity fields match → no exception."""
    request = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "story_id": "story-001",
        "attempt": 1,
        "max_attempts": 3,
        "source_revision": "a" * 40,
        "failure_class": "verification_fail",
        "failure_summary": "test failure",
        "failure_context_ref": {
            "path": "ctx.json",
            "schema_version": "1.0",
            "sha256": "b" * 64,
        },
        "verification_result_ref": {
            "path": "verify.json",
            "schema_version": "1.0",
            "sha256": "c" * 64,
        },
        "allowed_paths": ["backend/*.py"],
        "forbidden_paths": [],
        "requested_action": "fix_verification",
        "generated_at": "2026-08-06T12:00:00Z",
    }
    result = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "story_id": "story-001",
        "attempt": 1,
        "source_revision": "a" * 40,
        "status": "REPAIRED",
        "changed": True,
        "changed_files": ["backend/test.py"],
        "summary": "Fixed",
        "recommended_action": "reverify",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": "2026-08-06T12:01:00Z",
    }

    # Should not raise
    _validate_identity_binding(result, request)


def test_block_a_identity_run_id_mismatch() -> None:
    """Block A: run_id mismatch → ADAPTER_IDENTITY_MISMATCH."""
    request = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "story_id": "story-001",
        "attempt": 1,
        "max_attempts": 3,
        "source_revision": "a" * 40,
        "failure_class": "verification_fail",
        "failure_summary": "test",
        "failure_context_ref": {
            "path": "ctx.json",
            "schema_version": "1.0",
            "sha256": "b" * 64,
        },
        "verification_result_ref": {
            "path": "verify.json",
            "schema_version": "1.0",
            "sha256": "c" * 64,
        },
        "allowed_paths": [],
        "forbidden_paths": [],
        "requested_action": "fix_verification",
        "generated_at": "2026-08-06T12:00:00Z",
    }
    result = {
        "schema_version": "1.0",
        "run_id": "run-999",  # mismatch
        "story_id": "story-001",
        "attempt": 1,
        "source_revision": "a" * 40,
        "status": "REPAIRED",
        "changed": True,
        "changed_files": ["test.py"],
        "summary": "Fixed",
        "recommended_action": "reverify",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": "2026-08-06T12:01:00Z",
    }

    with pytest.raises(BaselineVerificationError) as exc_info:
        _validate_identity_binding(result, request)

    assert exc_info.value.adapter_status == ADAPTER_IDENTITY_MISMATCH
    assert "identity binding" in str(exc_info.value)


def test_block_a_identity_story_id_mismatch() -> None:
    """Block A: story_id mismatch → ADAPTER_IDENTITY_MISMATCH."""
    request = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "story_id": "story-001",
        "attempt": 1,
        "max_attempts": 3,
        "source_revision": "a" * 40,
        "failure_class": "verification_fail",
        "failure_summary": "test",
        "failure_context_ref": {
            "path": "ctx.json",
            "schema_version": "1.0",
            "sha256": "b" * 64,
        },
        "verification_result_ref": {
            "path": "verify.json",
            "schema_version": "1.0",
            "sha256": "c" * 64,
        },
        "allowed_paths": [],
        "forbidden_paths": [],
        "requested_action": "fix_verification",
        "generated_at": "2026-08-06T12:00:00Z",
    }
    result = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "story_id": "story-999",  # mismatch
        "attempt": 1,
        "source_revision": "a" * 40,
        "status": "REPAIRED",
        "changed": True,
        "changed_files": ["test.py"],
        "summary": "Fixed",
        "recommended_action": "reverify",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": "2026-08-06T12:01:00Z",
    }

    with pytest.raises(BaselineVerificationError) as exc_info:
        _validate_identity_binding(result, request)

    assert exc_info.value.adapter_status == ADAPTER_IDENTITY_MISMATCH


def test_block_a_identity_attempt_mismatch() -> None:
    """Block A: attempt mismatch → ADAPTER_IDENTITY_MISMATCH."""
    request = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "story_id": "story-001",
        "attempt": 1,
        "max_attempts": 3,
        "source_revision": "a" * 40,
        "failure_class": "verification_fail",
        "failure_summary": "test",
        "failure_context_ref": {
            "path": "ctx.json",
            "schema_version": "1.0",
            "sha256": "b" * 64,
        },
        "verification_result_ref": {
            "path": "verify.json",
            "schema_version": "1.0",
            "sha256": "c" * 64,
        },
        "allowed_paths": [],
        "forbidden_paths": [],
        "requested_action": "fix_verification",
        "generated_at": "2026-08-06T12:00:00Z",
    }
    result = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "story_id": "story-001",
        "attempt": 2,  # mismatch
        "source_revision": "a" * 40,
        "status": "REPAIRED",
        "changed": True,
        "changed_files": ["test.py"],
        "summary": "Fixed",
        "recommended_action": "reverify",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": "2026-08-06T12:01:00Z",
    }

    with pytest.raises(BaselineVerificationError) as exc_info:
        _validate_identity_binding(result, request)

    assert exc_info.value.adapter_status == ADAPTER_IDENTITY_MISMATCH


def test_block_a_identity_source_revision_mismatch() -> None:
    """Block A: source_revision mismatch → ADAPTER_IDENTITY_MISMATCH."""
    request = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "story_id": "story-001",
        "attempt": 1,
        "max_attempts": 3,
        "source_revision": "a" * 40,
        "failure_class": "verification_fail",
        "failure_summary": "test",
        "failure_context_ref": {
            "path": "ctx.json",
            "schema_version": "1.0",
            "sha256": "b" * 64,
        },
        "verification_result_ref": {
            "path": "verify.json",
            "schema_version": "1.0",
            "sha256": "c" * 64,
        },
        "allowed_paths": [],
        "forbidden_paths": [],
        "requested_action": "fix_verification",
        "generated_at": "2026-08-06T12:00:00Z",
    }
    result = {
        "schema_version": "1.0",
        "run_id": "run-001",
        "story_id": "story-001",
        "attempt": 1,
        "source_revision": "b" * 40,  # mismatch
        "status": "REPAIRED",
        "changed": True,
        "changed_files": ["test.py"],
        "summary": "Fixed",
        "recommended_action": "reverify",
        "sanitization": {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        },
        "completed_at": "2026-08-06T12:01:00Z",
    }

    with pytest.raises(BaselineVerificationError) as exc_info:
        _validate_identity_binding(result, request)

    assert exc_info.value.adapter_status == ADAPTER_IDENTITY_MISMATCH


def test_block_a_identity_contract_error_mapping() -> None:
    """Block A: RepairContractError maps to ADAPTER_IDENTITY_MISMATCH."""
    # Provide valid-looking dicts with a deliberate schema_version mismatch
    request: dict[str, Any] = {"schema_version": "1.0"}
    result: dict[str, Any] = {"schema_version": "2.0"}

    with pytest.raises(BaselineVerificationError) as exc_info:
        _validate_identity_binding(result, request)

    assert exc_info.value.adapter_status == ADAPTER_IDENTITY_MISMATCH
    assert "identity binding" in str(exc_info.value)
