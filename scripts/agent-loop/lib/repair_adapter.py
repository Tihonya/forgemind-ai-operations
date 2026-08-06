"""
WP-AL-1C5 Slice 1: Repair adapter result data model and schema.

Defines the adapter-result contract v1.0 with structural validation,
status-dependent presence rules, nested-object validation, cross-field
invariants, path lexical safety, deterministic builder, and canonical
serialization.

No filesystem writes, no Git operations, no subprocess, no network,
no orchestration logic, no mock actor, no run_repair, no CLI.

Schema: .agent-loop/repair-adapter/SCHEMA.md
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------
class RepairAdapterContractError(Exception):
    """Raised when an adapter-result contract invariant is violated."""


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
RE_RUN_ID = re.compile(r"^[A-Za-z0-9_\-:]+$")
RE_STORY_ID = re.compile(r"^[A-Za-z0-9_\-]+$")
RE_SHA40 = re.compile(r"^[0-9a-f]{40}$")
RE_ISO8601_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
ADAPTER_SUCCESS = "ADAPTER_SUCCESS"
ADAPTER_DIRTY_BASELINE = "ADAPTER_DIRTY_BASELINE"
ADAPTER_TIMEOUT = "ADAPTER_TIMEOUT"
ADAPTER_NON_ZERO_EXIT = "ADAPTER_NON_ZERO_EXIT"
ADAPTER_MISSING_RESULT = "ADAPTER_MISSING_RESULT"
ADAPTER_MALFORMED_RESULT = "ADAPTER_MALFORMED_RESULT"
ADAPTER_CONTRACT_VIOLATION = "ADAPTER_CONTRACT_VIOLATION"
ADAPTER_IDENTITY_MISMATCH = "ADAPTER_IDENTITY_MISMATCH"
ADAPTER_SOURCE_REVISION_DRIFT = "ADAPTER_SOURCE_REVISION_DRIFT"
ADAPTER_FORBIDDEN_CHANGE = "ADAPTER_FORBIDDEN_CHANGE"
ADAPTER_UNDECLARED_CHANGE = "ADAPTER_UNDECLARED_CHANGE"
ADAPTER_DECLARED_MISSING = "ADAPTER_DECLARED_MISSING"
ADAPTER_OUTPUT_SIZE_EXCEEDED = "ADAPTER_OUTPUT_SIZE_EXCEEDED"
ADAPTER_INTERNAL_ERROR = "ADAPTER_INTERNAL_ERROR"

VALID_ADAPTER_STATUSES = (
    ADAPTER_SUCCESS,
    ADAPTER_DIRTY_BASELINE,
    ADAPTER_TIMEOUT,
    ADAPTER_NON_ZERO_EXIT,
    ADAPTER_MISSING_RESULT,
    ADAPTER_MALFORMED_RESULT,
    ADAPTER_CONTRACT_VIOLATION,
    ADAPTER_IDENTITY_MISMATCH,
    ADAPTER_SOURCE_REVISION_DRIFT,
    ADAPTER_FORBIDDEN_CHANGE,
    ADAPTER_UNDECLARED_CHANGE,
    ADAPTER_DECLARED_MISSING,
    ADAPTER_OUTPUT_SIZE_EXCEEDED,
    ADAPTER_INTERNAL_ERROR,
)

# Repair result summary status values (from WP-AL-1C4)
VALID_REPAIR_STATUSES = ("REPAIRED", "NO_CHANGE", "ERROR")
VALID_RECOMMENDED_ACTIONS = ("reverify", "abort", "human_review")

# Pre-invocation failure statuses (no actor was invoked)
_PRE_INVOCATION_FAILURES = frozenset({
    ADAPTER_DIRTY_BASELINE,
    ADAPTER_SOURCE_REVISION_DRIFT,
    ADAPTER_INTERNAL_ERROR,
})

# Post-invocation failure statuses that imply actor produced no valid result
_POST_INVOCATION_NO_RESULT = frozenset({
    ADAPTER_TIMEOUT,
    ADAPTER_NON_ZERO_EXIT,
    ADAPTER_MISSING_RESULT,
    ADAPTER_MALFORMED_RESULT,
    ADAPTER_CONTRACT_VIOLATION,
    ADAPTER_IDENTITY_MISMATCH,
    ADAPTER_OUTPUT_SIZE_EXCEEDED,
})

# ---------------------------------------------------------------------------
# Byte and array limits
# ---------------------------------------------------------------------------
MAX_RUN_ID_BYTES = 256
MAX_STORY_ID_BYTES = 128
MAX_PATH_BYTES = 512
MAX_SUMMARY_BYTES = 2048
MAX_STDOUT_TAIL_BYTES = 4096
MAX_STDERR_TAIL_BYTES = 4096
MAX_ADAPTER_ERROR_MESSAGE_BYTES = 1024
MAX_CHANGED_FILES = 50
MAX_TRUNCATED_FIELDS = 64
MAX_TRUNCATED_FIELD_BYTES = 256
MAX_INTEGRITY_SCOPE_NOTE_BYTES = 512

# Fields that are always required regardless of status
_ALWAYS_REQUIRED_TOP_LEVEL = (
    "schema_version",
    "run_id",
    "story_id",
    "attempt",
    "adapter_status",
    "diagnostics",
    "sanitization",
    "integrity_scope",
    "completed_at",
)

# Fields that are always optional (conditionally present)
_CONDITIONALLY_PRESENT = (
    "repair_result_summary",
    "workspace_changes",
    "reconciliation",
    "permission_enforcement",
)

# The complete set of 13 top-level fields
ALL_TOP_LEVEL_FIELDS: tuple[str, ...] = (
    "schema_version",
    "run_id",
    "story_id",
    "attempt",
    "adapter_status",
    "repair_result_summary",
    "workspace_changes",
    "reconciliation",
    "permission_enforcement",
    "diagnostics",
    "sanitization",
    "integrity_scope",
    "completed_at",
)

# Nested object field sets (for unknown-field rejection)
_REPAIR_RESULT_SUMMARY_FIELDS = frozenset({
    "status", "changed", "changed_files", "recommended_action", "summary",
})
_WORKSPACE_CHANGES_FIELDS = frozenset({
    "baseline_source_revision", "post_source_revision",
    "source_revision_stable", "added", "modified", "deleted", "untracked",
})
_RECONCILIATION_FIELDS = frozenset({
    "declared_files", "actual_files", "undeclared_changes",
    "declared_but_missing", "exact_match",
})
_PERMISSION_ENFORCEMENT_FIELDS = frozenset({
    "allowed_violations", "forbidden_violations",
    "all_actual_changes_permitted",
})
_DIAGNOSTICS_FIELDS = frozenset({
    "actor_exit_code", "actor_stdout_tail", "actor_stderr_tail",
    "adapter_error_message",
})
_SANITIZATION_FIELDS = frozenset({
    "redaction_applied", "redaction_count", "truncation_applied",
    "truncated_fields",
})
_INTEGRITY_SCOPE_FIELDS = frozenset({
    "tracked_files_inspected", "untracked_non_ignored_inspected",
    "ignored_files_inspected", "advanced_symlink_inspected", "note",
})


# ---------------------------------------------------------------------------
# Byte-size helper
# ---------------------------------------------------------------------------
def _byte_len(text: str) -> int:
    """Return UTF-8 byte length of a string."""
    return len(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class WorkspaceBaseline:
    """Internal model for workspace baseline capture (not serialized in adapter result)."""

    source_revision: str
    baseline_exclusions: list[str]
    captured_at: str


@dataclass(frozen=True)
class WorkspaceChange:
    """Actual workspace changes observed after actor invocation."""

    added: list[str]
    modified: list[str]
    deleted: list[str]
    untracked: list[str]


@dataclass(frozen=True)
class ReconciliationResult:
    """Result of comparing declared vs actual changes."""

    declared_files: list[str]
    actual_files: list[str]
    undeclared_changes: list[str]
    declared_but_missing: list[str]
    exact_match: bool


@dataclass(frozen=True)
class RepairAdapterResult:
    """
    Typed result dataclass mirroring the adapter-result JSON schema v1.0.

    Conditionally-present fields may be None depending on adapter_status.
    """

    schema_version: str
    run_id: str
    story_id: str
    attempt: int
    adapter_status: str
    completed_at: str
    repair_result_summary: dict[str, Any] | None = None
    workspace_changes: dict[str, Any] | None = None
    reconciliation: dict[str, Any] | None = None
    permission_enforcement: dict[str, Any] | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    sanitization: dict[str, Any] = field(default_factory=dict)
    integrity_scope: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Path lexical validation (no filesystem access)
# ---------------------------------------------------------------------------
def _validate_relative_path(path_str: str, field_name: str) -> None:
    """Validate a relative path for repo-root containment at the lexical level."""
    if not isinstance(path_str, str):
        raise RepairAdapterContractError(f"{field_name}: path must be string")
    if not path_str:
        raise RepairAdapterContractError(f"{field_name}: empty path")
    if "\x00" in path_str:
        raise RepairAdapterContractError(f"{field_name}: null byte in path")
    if path_str.startswith("/"):
        raise RepairAdapterContractError(f"{field_name}: absolute path not allowed")
    if re.match(r"^[A-Za-z]:", path_str):
        raise RepairAdapterContractError(f"{field_name}: Windows drive letter not allowed")
    if path_str.startswith("\\\\"):
        raise RepairAdapterContractError(f"{field_name}: UNC path not allowed")
    if "\\" in path_str:
        raise RepairAdapterContractError(f"{field_name}: backslash not allowed (use forward slash)")
    if "//" in path_str:
        raise RepairAdapterContractError(f"{field_name}: duplicate separator")
    segments = path_str.split("/")
    for segment in segments:
        if segment == "":
            raise RepairAdapterContractError(f"{field_name}: empty segment")
        if segment == ".":
            raise RepairAdapterContractError(f"{field_name}: '.' segment not allowed")
        if segment == "..":
            raise RepairAdapterContractError(f"{field_name}: parent traversal not allowed")
    if _byte_len(path_str) > MAX_PATH_BYTES:
        raise RepairAdapterContractError(
            f"{field_name}: exceeds {MAX_PATH_BYTES} bytes"
        )


def _validate_path_list(paths: Any, field_name: str) -> None:
    """Validate an array of repo-relative paths, including duplicate detection."""
    if not isinstance(paths, list):
        raise RepairAdapterContractError(f"{field_name}: must be array")
    seen: set[str] = set()
    for i, path in enumerate(paths):
        _validate_relative_path(path, f"{field_name}[{i}]")
        if path in seen:
            raise RepairAdapterContractError(f"{field_name}: duplicate path: {path}")
        seen.add(path)


def _validate_sorted_path_list(paths: Any, field_name: str) -> None:
    """Validate array of repo-relative sorted paths with duplicate detection."""
    _validate_path_list(paths, field_name)
    if paths != sorted(paths):
        raise RepairAdapterContractError(f"{field_name}: paths must be sorted lexicographically")


# ---------------------------------------------------------------------------
# Nested object validation
# ---------------------------------------------------------------------------
def _check_no_unknown_fields(obj: dict[str, Any], allowed: frozenset[str], field_name: str) -> None:
    """Reject unknown fields in a closed-schema object."""
    for key in obj:
        if key not in allowed:
            raise RepairAdapterContractError(
                f"{field_name}: unknown field '{key}'"
            )


def _validate_repair_result_summary(summary: Any) -> None:
    """Validate repair_result_summary nested object."""
    if not isinstance(summary, dict):
        raise RepairAdapterContractError("repair_result_summary: must be object")
    _check_no_unknown_fields(summary, _REPAIR_RESULT_SUMMARY_FIELDS, "repair_result_summary")

    # status
    status = summary.get("status")
    if status not in VALID_REPAIR_STATUSES:
        raise RepairAdapterContractError(
            f"repair_result_summary.status: must be one of {VALID_REPAIR_STATUSES}, got {status!r}"
        )

    # changed
    changed = summary.get("changed")
    if not isinstance(changed, bool):
        raise RepairAdapterContractError("repair_result_summary.changed: must be boolean")

    # changed_files
    changed_files = summary.get("changed_files")
    if not isinstance(changed_files, list):
        raise RepairAdapterContractError("repair_result_summary.changed_files: must be array")
    if len(changed_files) > MAX_CHANGED_FILES:
        raise RepairAdapterContractError(
            f"repair_result_summary.changed_files: exceeds {MAX_CHANGED_FILES} entries"
        )
    for i, path in enumerate(changed_files):
        _validate_relative_path(path, f"repair_result_summary.changed_files[{i}]")
    # duplicate detection
    seen_cf: set[str] = set()
    for path in changed_files:
        if path in seen_cf:
            raise RepairAdapterContractError(
                f"repair_result_summary.changed_files: duplicate path: {path}"
            )
        seen_cf.add(path)

    # recommended_action
    recommended_action = summary.get("recommended_action")
    if recommended_action not in VALID_RECOMMENDED_ACTIONS:
        raise RepairAdapterContractError(
            f"repair_result_summary.recommended_action: must be one of {VALID_RECOMMENDED_ACTIONS}, "
            f"got {recommended_action!r}"
        )

    # summary
    summary_text = summary.get("summary")
    if not isinstance(summary_text, str):
        raise RepairAdapterContractError("repair_result_summary.summary: must be string")
    if _byte_len(summary_text) > MAX_SUMMARY_BYTES:
        raise RepairAdapterContractError(
            f"repair_result_summary.summary: exceeds {MAX_SUMMARY_BYTES} bytes"
        )

    # Cross-field invariants (from WP-AL-1C4)
    if status == "REPAIRED":
        if changed is not True:
            raise RepairAdapterContractError(
                "repair_result_summary: REPAIRED requires changed == true"
            )
        if len(changed_files) < 1:
            raise RepairAdapterContractError(
                "repair_result_summary: REPAIRED requires non-empty changed_files"
            )
        if recommended_action != "reverify":
            raise RepairAdapterContractError(
                "repair_result_summary: REPAIRED requires recommended_action == 'reverify'"
            )
    elif status == "NO_CHANGE":
        if changed is not False:
            raise RepairAdapterContractError(
                "repair_result_summary: NO_CHANGE requires changed == false"
            )
        if len(changed_files) != 0:
            raise RepairAdapterContractError(
                "repair_result_summary: NO_CHANGE requires empty changed_files"
            )
        if recommended_action not in ("abort", "human_review"):
            raise RepairAdapterContractError(
                "repair_result_summary: NO_CHANGE requires recommended_action in ('abort', 'human_review')"
            )
    elif status == "ERROR":
        if recommended_action not in ("abort", "human_review"):
            raise RepairAdapterContractError(
                "repair_result_summary: ERROR requires recommended_action in ('abort', 'human_review')"
            )


def _validate_workspace_changes(changes: Any) -> None:
    """Validate workspace_changes nested object."""
    if not isinstance(changes, dict):
        raise RepairAdapterContractError("workspace_changes: must be object")
    _check_no_unknown_fields(changes, _WORKSPACE_CHANGES_FIELDS, "workspace_changes")

    # baseline_source_revision
    bsr = changes.get("baseline_source_revision")
    if not isinstance(bsr, str) or not RE_SHA40.match(bsr):
        raise RepairAdapterContractError(
            "workspace_changes.baseline_source_revision: must be 40-char lowercase hex"
        )

    # post_source_revision
    psr = changes.get("post_source_revision")
    if not isinstance(psr, str) or not RE_SHA40.match(psr):
        raise RepairAdapterContractError(
            "workspace_changes.post_source_revision: must be 40-char lowercase hex"
        )

    # source_revision_stable
    srs = changes.get("source_revision_stable")
    if not isinstance(srs, bool):
        raise RepairAdapterContractError(
            "workspace_changes.source_revision_stable: must be boolean"
        )

    # Cross-field: source_revision_stable == (baseline == post)
    if srs != (bsr == psr):
        raise RepairAdapterContractError(
            "workspace_changes.source_revision_stable must equal "
            "(baseline_source_revision == post_source_revision)"
        )

    # Path lists
    for field_name in ("added", "modified", "deleted", "untracked"):
        _validate_sorted_path_list(
            changes.get(field_name), f"workspace_changes.{field_name}"
        )


def _validate_reconciliation(recon: Any) -> None:
    """Validate reconciliation nested object."""
    if not isinstance(recon, dict):
        raise RepairAdapterContractError("reconciliation: must be object")
    _check_no_unknown_fields(recon, _RECONCILIATION_FIELDS, "reconciliation")

    for field_name in ("declared_files", "actual_files",
                       "undeclared_changes", "declared_but_missing"):
        _validate_sorted_path_list(recon.get(field_name), f"reconciliation.{field_name}")

    exact_match = recon.get("exact_match")
    if not isinstance(exact_match, bool):
        raise RepairAdapterContractError("reconciliation.exact_match: must be boolean")

    # Cross-field: exact_match == (no undeclared and no declared_missing)
    undeclared = recon.get("undeclared_changes", [])
    declared_missing = recon.get("declared_but_missing", [])
    if exact_match != (len(undeclared) == 0 and len(declared_missing) == 0):
        raise RepairAdapterContractError(
            "reconciliation.exact_match must be True iff "
            "undeclared_changes and declared_but_missing are both empty"
        )


def _validate_permission_enforcement(perm: Any) -> None:
    """Validate permission_enforcement nested object."""
    if not isinstance(perm, dict):
        raise RepairAdapterContractError("permission_enforcement: must be object")
    _check_no_unknown_fields(perm, _PERMISSION_ENFORCEMENT_FIELDS, "permission_enforcement")

    for field_name in ("allowed_violations", "forbidden_violations"):
        _validate_path_list(perm.get(field_name), f"permission_enforcement.{field_name}")

    all_permitted = perm.get("all_actual_changes_permitted")
    if not isinstance(all_permitted, bool):
        raise RepairAdapterContractError(
            "permission_enforcement.all_actual_changes_permitted: must be boolean"
        )

    # Cross-field
    allowed_v = perm.get("allowed_violations", [])
    forbidden_v = perm.get("forbidden_violations", [])
    if all_permitted != (len(allowed_v) == 0 and len(forbidden_v) == 0):
        raise RepairAdapterContractError(
            "permission_enforcement.all_actual_changes_permitted must be True iff "
            "allowed_violations and forbidden_violations are both empty"
        )


def _validate_diagnostics(diag: Any) -> None:
    """Validate diagnostics nested object."""
    if not isinstance(diag, dict):
        raise RepairAdapterContractError("diagnostics: must be object")
    _check_no_unknown_fields(diag, _DIAGNOSTICS_FIELDS, "diagnostics")

    # actor_exit_code: integer | null
    exit_code = diag.get("actor_exit_code")
    if exit_code is not None and (
        not isinstance(exit_code, int) or isinstance(exit_code, bool)
    ):
        raise RepairAdapterContractError(
            "diagnostics.actor_exit_code: must be integer or null"
        )

    # actor_stdout_tail: max 4096 bytes
    stdout_tail = diag.get("actor_stdout_tail")
    if not isinstance(stdout_tail, str):
        raise RepairAdapterContractError("diagnostics.actor_stdout_tail: must be string")
    if _byte_len(stdout_tail) > MAX_STDOUT_TAIL_BYTES:
        raise RepairAdapterContractError(
            f"diagnostics.actor_stdout_tail: exceeds {MAX_STDOUT_TAIL_BYTES} bytes"
        )

    # actor_stderr_tail: max 4096 bytes
    stderr_tail = diag.get("actor_stderr_tail")
    if not isinstance(stderr_tail, str):
        raise RepairAdapterContractError("diagnostics.actor_stderr_tail: must be string")
    if _byte_len(stderr_tail) > MAX_STDERR_TAIL_BYTES:
        raise RepairAdapterContractError(
            f"diagnostics.actor_stderr_tail: exceeds {MAX_STDERR_TAIL_BYTES} bytes"
        )

    # adapter_error_message: string | null, max 1024 bytes
    error_msg = diag.get("adapter_error_message")
    if error_msg is not None:
        if not isinstance(error_msg, str):
            raise RepairAdapterContractError(
                "diagnostics.adapter_error_message: must be string or null"
            )
        if _byte_len(error_msg) > MAX_ADAPTER_ERROR_MESSAGE_BYTES:
            raise RepairAdapterContractError(
                f"diagnostics.adapter_error_message: exceeds {MAX_ADAPTER_ERROR_MESSAGE_BYTES} bytes"
            )


def _validate_sanitization(san: Any) -> None:
    """Validate sanitization nested object."""
    if not isinstance(san, dict):
        raise RepairAdapterContractError("sanitization: must be object")
    _check_no_unknown_fields(san, _SANITIZATION_FIELDS, "sanitization")

    ra = san.get("redaction_applied")
    if not isinstance(ra, bool):
        raise RepairAdapterContractError("sanitization.redaction_applied: must be boolean")

    rc = san.get("redaction_count")
    if not isinstance(rc, int) or isinstance(rc, bool) or rc < 0:
        raise RepairAdapterContractError("sanitization.redaction_count: must be integer >= 0")

    ta = san.get("truncation_applied")
    if not isinstance(ta, bool):
        raise RepairAdapterContractError("sanitization.truncation_applied: must be boolean")

    tf = san.get("truncated_fields")
    if not isinstance(tf, list):
        raise RepairAdapterContractError("sanitization.truncated_fields: must be array")
    if len(tf) > MAX_TRUNCATED_FIELDS:
        raise RepairAdapterContractError(
            f"sanitization.truncated_fields: exceeds {MAX_TRUNCATED_FIELDS} entries"
        )
    for i, item in enumerate(tf):
        if not isinstance(item, str):
            raise RepairAdapterContractError(
                f"sanitization.truncated_fields[{i}]: must be string"
            )
        if _byte_len(item) > MAX_TRUNCATED_FIELD_BYTES:
            raise RepairAdapterContractError(
                f"sanitization.truncated_fields[{i}]: exceeds {MAX_TRUNCATED_FIELD_BYTES} bytes"
            )

    # truncated_fields sorted lexicographically
    if tf != sorted(tf):
        raise RepairAdapterContractError(
            "sanitization.truncated_fields: must be sorted lexicographically"
        )

    # Cross-field: redaction_applied == False implies redaction_count == 0
    if ra is False and rc != 0:
        raise RepairAdapterContractError(
            "sanitization: redaction_applied == False requires redaction_count == 0"
        )

    # Cross-field: truncation_applied == False implies empty truncated_fields
    if ta is False and len(tf) != 0:
        raise RepairAdapterContractError(
            "sanitization: truncation_applied == False requires empty truncated_fields"
        )


def _validate_integrity_scope(scope: Any) -> None:
    """Validate integrity_scope nested object with constant checks."""
    if not isinstance(scope, dict):
        raise RepairAdapterContractError("integrity_scope: must be object")
    _check_no_unknown_fields(scope, _INTEGRITY_SCOPE_FIELDS, "integrity_scope")

    tfi = scope.get("tracked_files_inspected")
    if not isinstance(tfi, bool):
        raise RepairAdapterContractError("integrity_scope.tracked_files_inspected: must be boolean")
    if tfi is not True:
        raise RepairAdapterContractError(
            "integrity_scope.tracked_files_inspected: must be True in WP-AL-1C5"
        )

    uni = scope.get("untracked_non_ignored_inspected")
    if not isinstance(uni, bool):
        raise RepairAdapterContractError(
            "integrity_scope.untracked_non_ignored_inspected: must be boolean"
        )
    if uni is not True:
        raise RepairAdapterContractError(
            "integrity_scope.untracked_non_ignored_inspected: must be True in WP-AL-1C5"
        )

    ifi = scope.get("ignored_files_inspected")
    if not isinstance(ifi, bool):
        raise RepairAdapterContractError("integrity_scope.ignored_files_inspected: must be boolean")
    if ifi is not False:
        raise RepairAdapterContractError(
            "integrity_scope.ignored_files_inspected: must be False in WP-AL-1C5"
        )

    asi = scope.get("advanced_symlink_inspected")
    if not isinstance(asi, bool):
        raise RepairAdapterContractError(
            "integrity_scope.advanced_symlink_inspected: must be boolean"
        )
    if asi is not False:
        raise RepairAdapterContractError(
            "integrity_scope.advanced_symlink_inspected: must be False in WP-AL-1C5"
        )

    note = scope.get("note")
    if not isinstance(note, str):
        raise RepairAdapterContractError("integrity_scope.note: must be string")
    if _byte_len(note) > MAX_INTEGRITY_SCOPE_NOTE_BYTES:
        raise RepairAdapterContractError(
            f"integrity_scope.note: exceeds {MAX_INTEGRITY_SCOPE_NOTE_BYTES} bytes"
        )


# ---------------------------------------------------------------------------
# Status-dependent presence validation
# ---------------------------------------------------------------------------
def _validate_presence_rules(result: dict[str, Any]) -> None:
    """Validate status-dependent field presence rules."""
    status = result["adapter_status"]

    # ADAPTER_SUCCESS: all conditionally-present fields must be present
    if status == ADAPTER_SUCCESS:
        for field_name in _CONDITIONALLY_PRESENT:
            if field_name not in result or result[field_name] is None:
                raise RepairAdapterContractError(
                    f"{field_name}: must be present when adapter_status is ADAPTER_SUCCESS"
                )

    # Pre-invocation failures: actor was never invoked
    elif status in _PRE_INVOCATION_FAILURES:
        # repair_result_summary, workspace_changes, reconciliation,
        # permission_enforcement must NOT be present
        for field_name in _CONDITIONALLY_PRESENT:
            if field_name in result and result[field_name] is not None:
                raise RepairAdapterContractError(
                    f"{field_name}: must not be present for pre-invocation failure {status}"
                )

    # Post-invocation failures where actor produced no valid result
    elif status in _POST_INVOCATION_NO_RESULT:
        # repair_result_summary must NOT be present (no valid result)
        if "repair_result_summary" in result and result["repair_result_summary"] is not None:
            raise RepairAdapterContractError(
                f"repair_result_summary: must not be present for {status}"
            )

    # Post-invocation enforcement failures
    elif status in (ADAPTER_FORBIDDEN_CHANGE, ADAPTER_UNDECLARED_CHANGE, ADAPTER_DECLARED_MISSING):
        # repair_result_summary may be present (actor produced valid result)
        # workspace_changes must be present (we inspected the workspace)
        if "workspace_changes" not in result or result["workspace_changes"] is None:
            raise RepairAdapterContractError(
                f"workspace_changes: must be present for {status}"
            )
        # permission_enforcement must be present for FORBIDDEN_CHANGE
        if status == ADAPTER_FORBIDDEN_CHANGE and (
            "permission_enforcement" not in result
            or result["permission_enforcement"] is None
        ):
            raise RepairAdapterContractError(
                "permission_enforcement: must be present for ADAPTER_FORBIDDEN_CHANGE"
            )


# ---------------------------------------------------------------------------
# Structural validation: adapter result
# ---------------------------------------------------------------------------
def validate_adapter_result(result: dict[str, Any]) -> None:
    """
    Validate adapter-result structural invariants.

    Raises RepairAdapterContractError on any violation.
    No filesystem access, no Git operations, no subprocess.

    Enforces:
    - Exactly 13 top-level fields (closed schema, no unknown fields)
    - Status-dependent presence rules
    - All nested-object field sets and invariants
    - Path lexical safety
    - Byte bounds on all bounded strings
    """
    if not isinstance(result, dict):
        raise RepairAdapterContractError("result: must be object")

    # Unknown-field rejection (closed schema)
    for key in result:
        if key not in ALL_TOP_LEVEL_FIELDS:
            raise RepairAdapterContractError(f"unknown field: {key}")

    # Always-required fields
    for field_name in _ALWAYS_REQUIRED_TOP_LEVEL:
        if field_name not in result:
            raise RepairAdapterContractError(f"missing required field: {field_name}")

    # schema_version
    if result["schema_version"] != "1.0":
        raise RepairAdapterContractError(
            f"schema_version: must be '1.0', got {result['schema_version']!r}"
        )

    # run_id
    run_id = result["run_id"]
    if not isinstance(run_id, str) or not run_id:
        raise RepairAdapterContractError("run_id: must be non-empty string")
    if _byte_len(run_id) > MAX_RUN_ID_BYTES:
        raise RepairAdapterContractError(f"run_id: exceeds {MAX_RUN_ID_BYTES} bytes")
    if not RE_RUN_ID.match(run_id):
        raise RepairAdapterContractError("run_id: contains invalid characters")

    # story_id
    story_id = result["story_id"]
    if not isinstance(story_id, str) or not story_id:
        raise RepairAdapterContractError("story_id: must be non-empty string")
    if _byte_len(story_id) > MAX_STORY_ID_BYTES:
        raise RepairAdapterContractError(f"story_id: exceeds {MAX_STORY_ID_BYTES} bytes")
    if not RE_STORY_ID.match(story_id):
        raise RepairAdapterContractError("story_id: contains invalid characters")

    # attempt
    attempt = result["attempt"]
    if not isinstance(attempt, int) or isinstance(attempt, bool):
        raise RepairAdapterContractError("attempt: must be integer")
    if attempt < 1:
        raise RepairAdapterContractError("attempt: must be >= 1")

    # adapter_status
    status = result["adapter_status"]
    if status not in VALID_ADAPTER_STATUSES:
        raise RepairAdapterContractError(
            f"adapter_status: must be one of {VALID_ADAPTER_STATUSES}, got {status!r}"
        )

    # completed_at
    completed_at = result["completed_at"]
    if not isinstance(completed_at, str) or not RE_ISO8601_UTC.match(completed_at):
        raise RepairAdapterContractError("completed_at: must be ISO-8601 UTC format")

    # Status-dependent presence rules
    _validate_presence_rules(result)

    # Conditionally-present nested objects
    rrs = result.get("repair_result_summary")
    if rrs is not None:
        _validate_repair_result_summary(rrs)

    wc = result.get("workspace_changes")
    if wc is not None:
        _validate_workspace_changes(wc)

    recon = result.get("reconciliation")
    if recon is not None:
        _validate_reconciliation(recon)

    perm = result.get("permission_enforcement")
    if perm is not None:
        _validate_permission_enforcement(perm)

    # Always-present nested objects
    _validate_diagnostics(result["diagnostics"])
    _validate_sanitization(result["sanitization"])
    _validate_integrity_scope(result["integrity_scope"])


# ---------------------------------------------------------------------------
# Deterministic builder
# ---------------------------------------------------------------------------
def build_adapter_result(
    *,
    schema_version: str = "1.0",
    run_id: str,
    story_id: str,
    attempt: int,
    adapter_status: str,
    completed_at: str,
    repair_result_summary: dict[str, Any] | None = None,
    workspace_changes: dict[str, Any] | None = None,
    reconciliation: dict[str, Any] | None = None,
    permission_enforcement: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
    sanitization: dict[str, Any] | None = None,
    integrity_scope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a deterministic adapter-result dict with deep validation.

    - All caller-provided dicts and lists are deep-copied (no mutation).
    - No internal timestamp generation (caller supplies completed_at).
    - Returns a validated dict that passes validate_adapter_result.
    - Raises RepairAdapterContractError on any validation failure.
    """
    # Deep-copy all caller-provided mutable inputs to prevent mutation
    rrs_copy = copy.deepcopy(repair_result_summary) if repair_result_summary is not None else None
    wc_copy = copy.deepcopy(workspace_changes) if workspace_changes is not None else None
    recon_copy = copy.deepcopy(reconciliation) if reconciliation is not None else None
    perm_copy = copy.deepcopy(permission_enforcement) if permission_enforcement is not None else None

    if diagnostics is not None:
        diag_copy = copy.deepcopy(diagnostics)
    else:
        diag_copy = {
            "actor_exit_code": None,
            "actor_stdout_tail": "",
            "actor_stderr_tail": "",
            "adapter_error_message": None,
        }

    if sanitization is not None:
        san_copy = copy.deepcopy(sanitization)
    else:
        san_copy = {
            "redaction_applied": False,
            "redaction_count": 0,
            "truncation_applied": False,
            "truncated_fields": [],
        }

    if integrity_scope is not None:
        scope_copy = copy.deepcopy(integrity_scope)
    else:
        scope_copy = {
            "tracked_files_inspected": True,
            "untracked_non_ignored_inspected": True,
            "ignored_files_inspected": False,
            "advanced_symlink_inspected": False,
            "note": "WP-AL-1C5: ignored files and advanced symlink targets not inspected",
        }

    result: dict[str, Any] = {
        "schema_version": schema_version,
        "run_id": run_id,
        "story_id": story_id,
        "attempt": attempt,
        "adapter_status": adapter_status,
        "completed_at": completed_at,
        "diagnostics": diag_copy,
        "sanitization": san_copy,
        "integrity_scope": scope_copy,
    }

    if rrs_copy is not None:
        result["repair_result_summary"] = rrs_copy
    if wc_copy is not None:
        result["workspace_changes"] = wc_copy
    if recon_copy is not None:
        result["reconciliation"] = recon_copy
    if perm_copy is not None:
        result["permission_enforcement"] = perm_copy

    # Validate the built result
    validate_adapter_result(result)

    return result


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------
def canonical_json_bytes(obj: dict[str, Any]) -> bytes:
    """
    Produce deterministic canonical bytes for digest comparisons.

    sort_keys=True, separators=(",", ":"), ensure_ascii=False.
    """
    return json.dumps(
        obj,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def pretty_json_string(obj: dict[str, Any]) -> str:
    """
    Produce deterministic pretty JSON with indent=2 and trailing newline.

    No trailing whitespace on any line.
    """
    text = json.dumps(
        obj,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines) + "\n"
