"""
WP-AL-1C5 Repair Adapter.

Slice 1: Adapter-result contract v1.0 (structural validation, status-dependent
presence rules, nested-object validation, cross-field invariants, path lexical
safety, deterministic builder, canonical serialization).

Slice 2: Clean tracked baseline verification.
- Captures current source revision via ``git rev-parse HEAD``.
- Inspects workspace status via ``git status --porcelain=v1``.
- Rejects dirty tracked baseline (modified/staged/deleted/renamed tracked files).
- Applies orchestrator-provided baseline-exclusion list for approved untracked artifacts.
- Validates exclusion paths lexically.
- Does NOT invoke actor, does NOT write files, does NOT mutate repository.

Slice 3: Post-run workspace inventory.
- Captures post-run HEAD revision.
- Detects source revision drift.
- Collects actual workspace changes (added/modified/deleted/untracked).
- Normalizes renames to delete + add.
- Applies baseline exclusions to untracked files.
- Validates all paths.
- Ensures stable lexicographic ordering.
- No duplicates.
- Does NOT reconcile, does NOT enforce permissions, does NOT invoke actor.

Block A: Reconciliation and path policy.
- Flat exact reconciliation (declared vs actual).
- Permission enforcement (allowed_paths, forbidden_paths, gitwildmatch).
- Identity validation reuse from WP-AL-1C4.
- Does NOT invoke actor, does NOT write files, does NOT mutate repository.

Schema: .agent-loop/repair-adapter/SCHEMA.md
"""

from __future__ import annotations

import copy
import json
import os
import re
import selectors
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Narrow import contract from harness.py (approved public API for matching)
from harness import gitwildmatch

# Narrow import contract from repair_contract.py (WP-AL-1C4 identity validation)
from repair_contract import (
    RepairContractError,
    validate_repair_result_against_request,
)


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


# ---------------------------------------------------------------------------
# Slice 2: Baseline verification
# ---------------------------------------------------------------------------

# Maximum size for baseline-exclusion list (prevent abuse)
MAX_BASELINE_EXCLUSIONS = 128

# Git porcelain v1 status codes that indicate dirty tracked state.
# X column (index): anything other than ' ' means staged change.
# Y column (worktree): 'M', 'D', or 'T' means worktree modification of tracked file.
# 'U' in either column means unmerged (also dirty).


class BaselineVerificationError(Exception):
    """Raised when baseline verification fails with a specific adapter status."""

    def __init__(self, adapter_status: str, message: str) -> None:
        super().__init__(message)
        self.adapter_status = adapter_status


def _validate_exclusion_path(path_str: str) -> None:
    """
    Validate a single baseline-exclusion path lexically.

    Must be repo-relative, no traversal, no absolute, no null bytes,
    no backslashes, no empty segments, max 512 bytes.
    """
    if not isinstance(path_str, str):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"baseline_exclusion: path must be string, got {type(path_str).__name__}",
        )
    if not path_str:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            "baseline_exclusion: empty path",
        )
    if "\x00" in path_str:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            "baseline_exclusion: null byte in path",
        )
    if path_str.startswith("/"):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            "baseline_exclusion: absolute path not allowed",
        )
    if re.match(r"^[A-Za-z]:", path_str):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            "baseline_exclusion: Windows drive letter not allowed",
        )
    if path_str.startswith("\\\\"):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            "baseline_exclusion: UNC path not allowed",
        )
    if "\\" in path_str:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            "baseline_exclusion: backslash not allowed (use forward slash)",
        )
    if "//" in path_str:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            "baseline_exclusion: duplicate separator",
        )
    segments = path_str.split("/")
    for segment in segments:
        if segment == "":
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                "baseline_exclusion: empty segment",
            )
        if segment == ".":
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                "baseline_exclusion: '.' segment not allowed",
            )
        if segment == "..":
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                "baseline_exclusion: parent traversal not allowed",
            )
    if _byte_len(path_str) > MAX_PATH_BYTES:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"baseline_exclusion: exceeds {MAX_PATH_BYTES} bytes",
        )


def _validate_baseline_exclusions(exclusions: list[str]) -> list[str]:
    """
    Validate baseline-exclusion paths.

    Returns sorted list.
    Raises BaselineVerificationError on invalid input or duplicates.
    """
    if not isinstance(exclusions, list):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"baseline_exclusions must be list, got {type(exclusions).__name__}",
        )
    if len(exclusions) > MAX_BASELINE_EXCLUSIONS:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"baseline_exclusions exceeds {MAX_BASELINE_EXCLUSIONS} entries",
        )

    # Validate each path
    for i, path in enumerate(exclusions):
        try:
            _validate_exclusion_path(path)
        except BaselineVerificationError:
            raise
        except Exception as e:
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"baseline_exclusions[{i}]: unexpected validation error: {e}",
            ) from e

    # Duplicate detection
    seen: set[str] = set()
    for path in exclusions:
        if path in seen:
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"baseline_exclusions: duplicate path: {path}",
            )
        seen.add(path)

    # Return sorted for determinism
    return sorted(exclusions)


def _run_git_subprocess(
    args: list[str],
    cwd: Path,
    timeout_seconds: float = 30.0,
    max_stdout_bytes: int = 10_485_760,  # 10 MB
    max_stderr_bytes: int = 1_048_576,   # 1 MB
) -> tuple[bytes, bytes, int]:
    """
    Run a git command with bounded output capture.

    Uses selectors to read stdout/stderr incrementally, preventing unbounded
    memory consumption. Terminates the process if either stream exceeds its limit.

    Returns: (stdout_bytes, stderr_bytes, return_code)
    Raises: BaselineVerificationError on timeout, size limit, or execution failure
    """
    # Minimal environment — no leakage beyond what Git requires
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        # Prevent Git from reading user/system config
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        # Deterministic output
        "GIT_PAGER": "cat",
        "GIT_TERMINAL_PROMPT": "0",
    }

    try:
        proc = subprocess.Popen(
            ["git"] + args,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
    except OSError as e:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"git command failed to execute: {e}",
        ) from e

    # Ensure stdout/stderr are available
    if proc.stdout is None or proc.stderr is None:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            "failed to create subprocess pipes",
        )

    # Incremental read using selectors on file descriptors
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_len = 0
    stderr_len = 0

    stdout_fd = proc.stdout.fileno()
    stderr_fd = proc.stderr.fileno()

    sel = selectors.DefaultSelector()
    sel.register(stdout_fd, selectors.EVENT_READ)
    sel.register(stderr_fd, selectors.EVENT_READ)

    start_time = os.times().elapsed
    open_streams = 2

    try:
        while open_streams > 0:
            # Check timeout
            elapsed = os.times().elapsed - start_time
            if elapsed >= timeout_seconds:
                proc.terminate()
                try:
                    proc.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise BaselineVerificationError(
                    ADAPTER_INTERNAL_ERROR,
                    f"git command timed out after {timeout_seconds}s: git {' '.join(args)}",
                )

            events = sel.select(timeout=0.1)
            for key, _ in events:
                fd = key.fileobj
                assert isinstance(fd, int), "selector key fileobj should be fd int"
                try:
                    data = os.read(fd, 65536)  # 64 KB chunks
                except OSError:
                    data = b""

                if not data:
                    # EOF
                    sel.unregister(fd)
                    open_streams -= 1
                    continue

                if fd == stdout_fd:
                    stdout_len += len(data)
                    if stdout_len > max_stdout_bytes:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5.0)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        raise BaselineVerificationError(
                            ADAPTER_INTERNAL_ERROR,
                            f"git command stdout exceeded {max_stdout_bytes} bytes: git {' '.join(args)}",
                        )
                    stdout_chunks.append(data)
                elif fd == stderr_fd:
                    stderr_len += len(data)
                    if stderr_len > max_stderr_bytes:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5.0)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait()
                        raise BaselineVerificationError(
                            ADAPTER_INTERNAL_ERROR,
                            f"git command stderr exceeded {max_stderr_bytes} bytes: git {' '.join(args)}",
                        )
                    stderr_chunks.append(data)

        # Final timeout check — command may have completed but exceeded the budget
        elapsed = os.times().elapsed - start_time
        if elapsed >= timeout_seconds:
            proc.terminate()
            try:
                proc.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"git command timed out after {timeout_seconds}s: git {' '.join(args)}",
            )

        returncode = proc.wait()
        return b"".join(stdout_chunks), b"".join(stderr_chunks), returncode

    finally:
        sel.close()
        # Ensure process is reaped
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def _run_git_command(
    args: list[str],
    cwd: Path,
) -> str:
    """
    Run a Git command with shell=False, explicit cwd, minimal environment.

    Returns stdout as string (stripped of trailing newline).
    Raises BaselineVerificationError(ADAPTER_INTERNAL_ERROR) on failure.
    """
    stdout_bytes, stderr_bytes, returncode = _run_git_subprocess(args, cwd)

    if returncode != 0:
        stderr_msg = stderr_bytes.decode("utf-8", errors="replace").strip()[:512]
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"git {' '.join(args)} failed (exit {returncode}): {stderr_msg}",
        )

    return stdout_bytes.decode("utf-8").rstrip("\n")


def _capture_source_revision(repo_root: Path) -> str:
    """
    Capture current HEAD revision via git rev-parse HEAD.

    Returns 40-char lowercase hex SHA.
    Raises BaselineVerificationError on failure or invalid format.
    """
    sha = _run_git_command(["rev-parse", "HEAD"], repo_root)

    if not RE_SHA40.match(sha):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"source revision is not 40-char lowercase hex: {sha!r}",
        )

    return sha


def _parse_porcelain_status(
    status_output: str,
) -> tuple[list[str], list[str], list[str]]:
    """
    Parse git status --porcelain=v1 output.

    Returns (tracked_dirty_paths, untracked_paths, ignored_paths).
    Each list contains repo-relative paths, sorted.

    Porcelain v1 format: each line is "XY path" where:
    - X = index (staged) status
    - Y = worktree status
    - path = repo-relative path

    Dirty tracked: any line where X not in {' ', '?', '!'} or Y in {'M', 'D', 'U'}
    Untracked: lines starting with '??'
    Ignored: lines starting with '!!'
    """
    tracked_dirty: list[str] = []
    untracked: list[str] = []
    ignored: list[str] = []

    for line in status_output.split("\n"):
        if not line:
            continue

        # Lines must be at least 4 chars: "XY p"
        if len(line) < 4:
            # Malformed line — treat as internal error upstream
            # For now, skip empty/short lines
            continue

        x_code = line[0]
        y_code = line[1]
        # Path starts after "XY " (3 chars)
        path = line[3:]

        # Handle quoted paths (special characters)
        if path.startswith('"') and path.endswith('"'):
            # Porcelain quotes paths with special chars — strip quotes
            # Note: full unescaping is complex; for baseline purposes,
            # we accept the quoted form as-is since we're just comparing
            # against exclusion paths
            path = path[1:-1]

        if x_code == "?" and y_code == "?":
            # Untracked file
            untracked.append(path)
        elif x_code == "!" and y_code == "!":
            # Ignored file (only present with --ignored flag, which we don't use)
            ignored.append(path)
        elif x_code == "U" or y_code == "U":
            # Unmerged — dirty tracked
            tracked_dirty.append(path)
        elif x_code != " " and x_code not in ("?", "!"):
            # Staged change in index
            tracked_dirty.append(path)
        elif y_code in ("M", "D", "T"):
            # Worktree modification of tracked file (M=modified, D=deleted, T=typechange)
            tracked_dirty.append(path)
        # else: clean tracked file (X=' ', Y=' ') — no action needed

    # Sort for determinism
    tracked_dirty.sort()
    untracked.sort()
    ignored.sort()

    return tracked_dirty, untracked, ignored


def _verify_clean_tracked_baseline(
    repo_root: Path,
    baseline_exclusions: list[str],
    captured_at: str,
) -> WorkspaceBaseline:
    """
    Verify clean tracked baseline and capture workspace baseline.

    Parameters:
        repo_root: repository root directory (must exist, must be a directory).
        baseline_exclusions: orchestrator-supplied list of approved pre-existing
            untracked artifact paths (repo-relative, lexically validated).
        captured_at: ISO-8601 UTC timestamp supplied by caller (no internal time call).

    Returns:
        WorkspaceBaseline with source_revision, baseline_exclusions (sorted), captured_at.

    Raises:
        BaselineVerificationError:
            - adapter_status=ADAPTER_INTERNAL_ERROR: repo_root invalid, git failure,
              format error, invalid exclusion path.
            - adapter_status=ADAPTER_DIRTY_BASELINE: tracked modifications or staged
              changes found.

    Semantics:
        - Untracked files in baseline_exclusions are excluded from baseline.
        - Untracked files NOT in baseline_exclusions are allowed at baseline time
          (they will be caught by post-run reconciliation if actor didn't declare them).
        - Ignored files are outside integrity scope (never inspected).
        - No filesystem mutation. No repository state change.
        - Deterministic: same inputs → same baseline.
    """
    # Validate captured_at format
    if not isinstance(captured_at, str):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"captured_at must be string, got {type(captured_at).__name__}",
        )
    if not RE_ISO8601_UTC.match(captured_at):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"captured_at must be ISO-8601 UTC format: {captured_at!r}",
        )

    # Validate repo_root
    if not isinstance(repo_root, Path):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"repo_root must be Path, got {type(repo_root).__name__}",
        )

    try:
        if not repo_root.exists():
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"repo_root does not exist: {repo_root}",
            )
        if not repo_root.is_dir():
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"repo_root is not a directory: {repo_root}",
            )
    except OSError as e:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"cannot access repo_root: {e}",
        ) from e

    # Validate baseline_exclusions
    validated_exclusions = _validate_baseline_exclusions(baseline_exclusions)

    # Capture source revision
    source_revision = _capture_source_revision(repo_root)

    # Inspect workspace status
    status_output = _run_git_command(
        ["status", "--porcelain=v1", "-uall"],
        repo_root,
    )

    # Parse status
    tracked_dirty, _untracked, _ignored = _parse_porcelain_status(status_output)

    # Reject dirty tracked baseline
    if tracked_dirty:
        dirty_summary = ", ".join(tracked_dirty[:5])
        if len(tracked_dirty) > 5:
            dirty_summary += f" ... (+{len(tracked_dirty) - 5} more)"
        raise BaselineVerificationError(
            ADAPTER_DIRTY_BASELINE,
            f"pre-existing tracked modifications found: {dirty_summary}",
        )

    # Untracked files not in exclusions are allowed at baseline time.
    # They will be caught during post-run reconciliation (later slices).

    # Build and return baseline
    return WorkspaceBaseline(
        source_revision=source_revision,
        baseline_exclusions=validated_exclusions,
        captured_at=captured_at,
    )


# ---------------------------------------------------------------------------
# Slice 3: Post-run workspace inventory
# ---------------------------------------------------------------------------

# Maximum size for workspace inventory lists (prevent abuse)
MAX_INVENTORY_ENTRIES_PER_CATEGORY = 512


def _parse_porcelain_status_z(
    status_output_bytes: bytes,
) -> tuple[list[str], list[str], list[str]]:
    """
    Parse git status --porcelain=v1 -z output (NUL-delimited).

    Format: Each entry is "XY path\0" or for R/C: "XY path1\0path2\0"
    - X = index (staged) status
    - Y = worktree status
    - path = repo-relative path (no quoting, no escaping)

    Returns (added, modified, deleted) paths, each sorted.
    Raises BaselineVerificationError(ADAPTER_INTERNAL_ERROR) on unmerged state.

    Classification:
    - 'A' (staged add) → added
    - 'M' (modified in either column) → modified
    - 'D' (deleted in either column) → deleted
    - 'R' (rename) → delete old + add new (normalized)
    - 'C' (copy) → add new (destination)
    - 'T' (typechange) → delete + add (normalized)
    - 'U' (unmerged) → raise error (out of scope)
    """
    added: list[str] = []
    modified: list[str] = []
    deleted: list[str] = []

    # Split by NUL
    parts = status_output_bytes.split(b"\0")

    # Remove trailing empty part (if output ends with NUL)
    if parts and parts[-1] == b"":
        parts = parts[:-1]

    i = 0
    while i < len(parts):
        entry = parts[i]

        # Each entry must be at least 3 bytes: "XY "
        if len(entry) < 3:
            # Malformed entry
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"malformed porcelain entry (too short): {entry!r}",
            )

        # Extract XY codes and path
        x_code = chr(entry[0])
        y_code = chr(entry[1])
        # Path starts after "XY " (3 bytes)
        path1_bytes = entry[3:]

        # Decode path (UTF-8, no escaping with -z)
        try:
            path1 = path1_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"path is not valid UTF-8: {path1_bytes!r}",
            ) from e

        # Git porcelain v1 defines 7 unmerged XY states:
        # DD (both deleted), AU (added by us), UD (updated by them),
        # UA (added by them), DU (deleted by us), AA (both added), UU (both updated)
        xy_str = x_code + y_code
        if xy_str in ("DD", "AU", "UD", "UA", "DU", "AA", "UU"):
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"unmerged state detected (out of scope): {path1}",
            )

        # Classify based on XY codes
        # Handle rename (R) and copy (C) — two paths
        if x_code in ("R", "C"):
            # Second path follows
            if i + 1 >= len(parts):
                raise BaselineVerificationError(
                    ADAPTER_INTERNAL_ERROR,
                    f"rename/copy missing second path: {path1}",
                )
            path2_bytes = parts[i + 1]
            try:
                path2 = path2_bytes.decode("utf-8")
            except UnicodeDecodeError as e:
                raise BaselineVerificationError(
                    ADAPTER_INTERNAL_ERROR,
                    f"rename/copy path is not valid UTF-8: {path2_bytes!r}",
                ) from e
            i += 1  # Advance to skip path2

            if x_code == "R":
                # Rename: Git -z format is R  <new_path>\0<old_path>\0
                # path1 = new (destination), path2 = old (source)
                # Delete old + add new
                deleted.append(path2)
                added.append(path1)
            else:  # C (copy)
                # Copy: Git -z format is C  <dest_path>\0<src_path>\0
                # path1 = destination, path2 = source
                # Add destination only
                added.append(path1)
        elif x_code == "A":
            # Staged add
            added.append(path1)
        elif x_code == "M" or y_code == "M":
            # Modified (staged or worktree)
            modified.append(path1)
        elif x_code == "D" or y_code == "D":
            # Deleted (staged or worktree)
            deleted.append(path1)
        elif x_code == "T" or y_code == "T":
            # Typechange: treat as delete + add
            deleted.append(path1)
            added.append(path1)
        # else: clean tracked file or ignored — no action

        i += 1

    # Sort for determinism
    added.sort()
    modified.sort()
    deleted.sort()

    return added, modified, deleted


def _parse_ls_files_others_z(
    ls_files_output_bytes: bytes,
) -> list[str]:
    """
    Parse git ls-files -z --others --exclude-standard output (NUL-delimited).

    Returns sorted list of untracked non-ignored paths.
    """
    # Split by NUL
    parts = ls_files_output_bytes.split(b"\0")

    # Remove trailing empty part (if output ends with NUL)
    if parts and parts[-1] == b"":
        parts = parts[:-1]

    untracked: list[str] = []
    for path_bytes in parts:
        if not path_bytes:
            continue  # Skip empty parts

        # Decode path (UTF-8, no escaping with -z)
        try:
            path = path_bytes.decode("utf-8")
        except UnicodeDecodeError as e:
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"untracked path is not valid UTF-8: {path_bytes!r}",
            ) from e

        untracked.append(path)

    # Sort for determinism
    untracked.sort()

    return untracked


def _run_git_command_bytes(
    args: list[str],
    cwd: Path,
    max_stdout_bytes: int = 1_000_000,
) -> bytes:
    """
    Run a Git command with shell=False, explicit cwd, minimal environment.

    Returns stdout as bytes (no decoding).
    Raises BaselineVerificationError(ADAPTER_INTERNAL_ERROR) on failure.
    Bounded: rejects output exceeding max_stdout_bytes.
    """
    stdout_bytes, stderr_bytes, returncode = _run_git_subprocess(
        args, cwd, max_stdout_bytes=max_stdout_bytes
    )

    if returncode != 0:
        stderr_msg = stderr_bytes.decode("utf-8", errors="replace").strip()[:512]
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"git {' '.join(args)} failed (exit {returncode}): {stderr_msg}",
        )

    return stdout_bytes


def _validate_inventory_path(path: str, category: str) -> None:
    """
    Validate a workspace inventory path lexically.

    Must be repo-relative, no traversal, no absolute, no null bytes,
    no backslashes, no empty segments, max 512 bytes.
    """
    if not isinstance(path, str):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"{category}: path must be string, got {type(path).__name__}",
        )
    if not path:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"{category}: empty path",
        )
    if "\x00" in path:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"{category}: null byte in path",
        )
    if path.startswith("/"):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"{category}: absolute path not allowed",
        )
    if re.match(r"^[A-Za-z]:", path):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"{category}: Windows drive letter not allowed",
        )
    if path.startswith("\\\\"):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"{category}: UNC path not allowed",
        )
    if "\\" in path:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"{category}: backslash not allowed (use forward slash)",
        )
    if "//" in path:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"{category}: duplicate separator",
        )
    segments = path.split("/")
    for segment in segments:
        if segment == "":
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"{category}: empty segment",
            )
        if segment == ".":
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"{category}: '.' segment not allowed",
            )
        if segment == "..":
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"{category}: parent traversal not allowed",
            )
    if _byte_len(path) > MAX_PATH_BYTES:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"{category}: exceeds {MAX_PATH_BYTES} bytes",
        )


def _validate_inventory_paths(
    added: list[str],
    modified: list[str],
    deleted: list[str],
    untracked: list[str],
) -> None:
    """
    Validate all workspace inventory paths lexically.

    Raises BaselineVerificationError on any invalid path.
    """
    for path in added:
        _validate_inventory_path(path, "workspace_changes.added")
    for path in modified:
        _validate_inventory_path(path, "workspace_changes.modified")
    for path in deleted:
        _validate_inventory_path(path, "workspace_changes.deleted")
    for path in untracked:
        _validate_inventory_path(path, "workspace_changes.untracked")


def _deduplicate_and_sort(paths: list[str]) -> list[str]:
    """
    Remove duplicates and sort paths lexicographically.

    Returns new sorted list with no duplicates.
    """
    # Use dict to preserve order while deduplicating (Python 3.7+)
    seen: dict[str, None] = {}
    for p in paths:
        if p not in seen:
            seen[p] = None
    return sorted(seen.keys())


def _capture_post_run_workspace(
    repo_root: Path,
    baseline_source_revision: str,
    baseline_exclusions: list[str],
) -> tuple[str, bool, WorkspaceChange]:
    """
    Capture post-run workspace inventory and detect source revision drift.

    Parameters:
        repo_root: repository root directory (must exist, must be a directory).
        baseline_source_revision: 40-char hex SHA from baseline capture.
        baseline_exclusions: orchestrator-supplied list of approved pre-existing
            untracked artifact paths (repo-relative, lexically validated).

    Returns:
        Tuple of (post_source_revision, source_revision_stable, workspace_change).
        - post_source_revision: 40-char hex SHA of current HEAD.
        - source_revision_stable: True if post matches baseline, False if drifted.
        - workspace_change: WorkspaceChange with added/modified/deleted/untracked lists.

    Raises:
        BaselineVerificationError:
            - adapter_status=ADAPTER_INTERNAL_ERROR: repo_root invalid, git failure,
              unmerged state, path validation failure, output size exceeded.
            - adapter_status=ADAPTER_SOURCE_REVISION_DRIFT: source revision changed.

    Semantics:
        - Captures current HEAD revision (post-run).
        - Detects source revision drift (compares to baseline).
        - Collects actual workspace changes (added/modified/deleted/untracked).
        - Normalizes renames to delete + add.
        - Applies baseline exclusions to untracked files (excludes from inventory).
        - Validates all paths lexically.
        - Ensures stable lexicographic ordering.
        - No duplicates.
        - Does NOT reconcile, does NOT enforce permissions, does NOT invoke actor.
    """
    # Validate repo_root
    if not isinstance(repo_root, Path):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"repo_root must be Path, got {type(repo_root).__name__}",
        )

    try:
        if not repo_root.exists():
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"repo_root does not exist: {repo_root}",
            )
        if not repo_root.is_dir():
            raise BaselineVerificationError(
                ADAPTER_INTERNAL_ERROR,
                f"repo_root is not a directory: {repo_root}",
            )
    except OSError as e:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"cannot access repo_root: {e}",
        ) from e

    # Validate baseline_source_revision
    if not isinstance(baseline_source_revision, str):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"baseline_source_revision must be string, got {type(baseline_source_revision).__name__}",
        )
    if not RE_SHA40.match(baseline_source_revision):
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"baseline_source_revision is not 40-char lowercase hex: {baseline_source_revision!r}",
        )

    # Validate baseline_exclusions
    validated_exclusions = _validate_baseline_exclusions(baseline_exclusions)

    # Capture post-run source revision
    post_source_revision = _capture_source_revision(repo_root)

    # Detect source revision drift
    source_revision_stable = post_source_revision == baseline_source_revision

    # Collect tracked changes via git status --porcelain=v1 -z -uno
    # -uno: only show tracked files (untracked come from ls-files separately)
    status_output_bytes = _run_git_command_bytes(
        ["-c", "core.quotePath=false", "status", "--porcelain=v1", "-z", "-uno"],
        repo_root,
        max_stdout_bytes=1_000_000,  # 1 MB bound
    )

    # Parse tracked changes (added, modified, deleted)
    added_tracked, modified_tracked, deleted_tracked = _parse_porcelain_status_z(
        status_output_bytes
    )

    # Collect untracked non-ignored files via git ls-files -z --others --exclude-standard
    ls_files_output_bytes = _run_git_command_bytes(
        ["ls-files", "-z", "--others", "--exclude-standard"],
        repo_root,
        max_stdout_bytes=1_000_000,  # 1 MB bound
    )

    # Parse untracked files
    untracked_all = _parse_ls_files_others_z(ls_files_output_bytes)

    # Apply baseline exclusions to untracked files
    exclusion_set = set(validated_exclusions)
    untracked_filtered = [p for p in untracked_all if p not in exclusion_set]

    # Validate all paths lexically
    _validate_inventory_paths(
        added_tracked, modified_tracked, deleted_tracked, untracked_filtered
    )

    # Deduplicate and sort (should already be sorted, but ensure determinism)
    added_final = _deduplicate_and_sort(added_tracked)
    modified_final = _deduplicate_and_sort(modified_tracked)
    deleted_final = _deduplicate_and_sort(deleted_tracked)
    untracked_final = _deduplicate_and_sort(untracked_filtered)

    # Check inventory size bounds
    if len(added_final) > MAX_INVENTORY_ENTRIES_PER_CATEGORY:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"workspace_changes.added exceeds {MAX_INVENTORY_ENTRIES_PER_CATEGORY} entries",
        )
    if len(modified_final) > MAX_INVENTORY_ENTRIES_PER_CATEGORY:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"workspace_changes.modified exceeds {MAX_INVENTORY_ENTRIES_PER_CATEGORY} entries",
        )
    if len(deleted_final) > MAX_INVENTORY_ENTRIES_PER_CATEGORY:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"workspace_changes.deleted exceeds {MAX_INVENTORY_ENTRIES_PER_CATEGORY} entries",
        )
    if len(untracked_final) > MAX_INVENTORY_ENTRIES_PER_CATEGORY:
        raise BaselineVerificationError(
            ADAPTER_INTERNAL_ERROR,
            f"workspace_changes.untracked exceeds {MAX_INVENTORY_ENTRIES_PER_CATEGORY} entries",
        )

    # Build workspace change
    workspace_change = WorkspaceChange(
        added=added_final,
        modified=modified_final,
        deleted=deleted_final,
        untracked=untracked_final,
    )

    return post_source_revision, source_revision_stable, workspace_change


# ---------------------------------------------------------------------------
# Block A: Reconciliation and path policy
# ---------------------------------------------------------------------------


def _validate_identity_binding(
    result: dict[str, Any],
    request: dict[str, Any],
) -> None:
    """
    Validate identity binding between repair request and repair result.

    Reuses WP-AL-1C4 validate_repair_result_against_request().
    Catches RepairContractError and re-raises as BaselineVerificationError
    with ADAPTER_IDENTITY_MISMATCH.

    Parameters:
        result: repair result dict (WP-AL-1C4 validated)
        request: repair request dict (WP-AL-1C4 validated)

    Raises:
        BaselineVerificationError(ADAPTER_IDENTITY_MISMATCH) on mismatch.
    """
    try:
        validate_repair_result_against_request(result, request)
    except RepairContractError as e:
        raise BaselineVerificationError(
            ADAPTER_IDENTITY_MISMATCH,
            f"identity binding validation failed: {e}",
        ) from e


def _reconcile_changes(
    declared_files: list[str],
    workspace_change: WorkspaceChange,
) -> ReconciliationResult:
    """
    Flat exact reconciliation: compare declared changed_files vs actual workspace.

    Computes:
    - actual_files: sorted unique union of (added + modified + deleted + untracked)
    - undeclared_changes: sorted(actual - declared)
    - declared_but_missing: sorted(declared - actual)
    - exact_match: True iff both sets are empty

    Parameters:
        declared_files: list of paths from repair_result.changed_files
        workspace_change: WorkspaceChange from _capture_post_run_workspace

    Returns:
        ReconciliationResult with sorted, unique, deterministic fields.

    Semantics:
    - Untracked paths participate in actual_files after baseline exclusions.
    - Rename normalization (old→deleted, new→added) means both paths are in actual.
    - No category-mismatch concept: actor declares paths, not Git categories.
    - Both undeclared and declared_missing can be non-empty; caller decides status.
    """
    # Build actual_files: sorted unique union of all workspace categories
    actual_files = sorted(
        set(
            workspace_change.added
            + workspace_change.modified
            + workspace_change.deleted
            + workspace_change.untracked
        )
    )

    # Build declared set (validated by WP-AL-1C4, but deduplicate defensively)
    declared_set = set(declared_files)
    actual_set = set(actual_files)

    # Compute set differences
    undeclared_changes = sorted(actual_set - declared_set)
    declared_but_missing = sorted(declared_set - actual_set)

    # exact_match: both differences empty
    exact_match = len(undeclared_changes) == 0 and len(declared_but_missing) == 0

    return ReconciliationResult(
        declared_files=sorted(declared_set),
        actual_files=actual_files,
        undeclared_changes=undeclared_changes,
        declared_but_missing=declared_but_missing,
        exact_match=exact_match,
    )


def _enforce_permissions(
    workspace_change: WorkspaceChange,
    allowed_paths: list[str],
    forbidden_paths: list[str],
) -> tuple[list[str], list[str]]:
    """
    Enforce allowed_paths and forbidden_paths on actual workspace changes.

    For each actual path (sorted, unique):
    1. If any forbidden pattern matches → forbidden_violation
    2. Else if allowed_paths is non-empty and no allowed pattern matches → allowed_violation
    3. Else → permitted

    Forbidden wins over allowed.

    Parameters:
        workspace_change: WorkspaceChange from _capture_post_run_workspace
        allowed_paths: list of gitwildmatch patterns (from repair request)
        forbidden_paths: list of gitwildmatch patterns (from repair request)

    Returns:
        Tuple of (allowed_violations, forbidden_violations), each sorted and unique.

    Both violation forms map to ADAPTER_FORBIDDEN_CHANGE at the caller level.
    """
    # Build actual_paths: sorted unique union of all workspace categories
    actual_paths = sorted(
        set(
            workspace_change.added
            + workspace_change.modified
            + workspace_change.deleted
            + workspace_change.untracked
        )
    )

    allowed_violations: list[str] = []
    forbidden_violations: list[str] = []

    for path in actual_paths:
        # Check forbidden first (forbidden wins)
        if any(gitwildmatch(path, pattern) for pattern in forbidden_paths):
            forbidden_violations.append(path)
        # Check allowed (if allowed_paths is non-empty)
        elif allowed_paths and not any(
            gitwildmatch(path, pattern) for pattern in allowed_paths
        ):
            allowed_violations.append(path)

    return allowed_violations, forbidden_violations
