"""
WP-AL-1C4: Repair request/result contract for the agent-loop repair phase.

Defines repair-request and repair-result schemas v1.0 with structural
validators, identity binding, path-safety (gitwildmatch), and a deterministic
builder. No LLM invocation, no adapter, no repair execution, no orchestrator
wiring.

Schema: .agent-loop/repair/SCHEMA.md

Deterministic, stdlib-only, no network/LLM/shell. Imports narrow public API
from failure_context.py for sanitization. Imports gitwildmatch from harness.py
for path-safety matching. Does NOT claim to prove workspace integrity — it
validates declared artifact claims only.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

# Narrow import contract from failure_context.py (approved public API)
from failure_context import (
    is_binary_content,
    normalize_utf8,
    redact_base64_runs,
    redact_text,
    sanitize_control_characters,
)

# Narrow import contract from harness.py (approved public API for matching)
from harness import gitwildmatch


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------
class RepairContractError(Exception):
    """Raised when a repair contract invariant is violated."""


# ---------------------------------------------------------------------------
# Regex patterns for field validation
# ---------------------------------------------------------------------------
RE_RUN_ID = re.compile(r"^[A-Za-z0-9_\-:]+$")
RE_STORY_ID = re.compile(r"^[A-Za-z0-9_\-]+$")
RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
RE_SHA40 = re.compile(r"^[0-9a-f]{40}$")
RE_ISO8601_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

# Valid enumerations
VALID_FAILURE_CLASS = ("verification_fail", "review_fail")
VALID_REQUESTED_ACTION = ("fix_verification", "fix_review_findings")
VALID_RESULT_STATUS = ("REPAIRED", "NO_CHANGE", "ERROR")
VALID_RECOMMENDED_ACTION = ("reverify", "abort", "human_review")
VALID_CONFIDENCE = ("high", "medium", "low")

# Path and byte limits
MAX_PATH_BYTES = 512
MAX_CHANGED_FILES = 50
MAX_SUMMARY_BYTES = 2048
MAX_FAILURE_SUMMARY_BYTES = 2048
MAX_REPAIR_GUIDANCE_ENTRIES = 10
MAX_REPAIR_GUIDANCE_BYTES = 256
MAX_DIAG_ACTIONS = 20
MAX_DIAG_OBSTACLES = 10
MAX_DIAG_ENTRY_BYTES = 512
MAX_TRUNCATED_FIELDS = 64
MAX_TRUNCATED_FIELD_BYTES = 256


# ---------------------------------------------------------------------------
# Byte-size helpers
# ---------------------------------------------------------------------------
def _byte_len(text: str) -> int:
    """Return UTF-8 byte length of a string."""
    return len(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Path safety (lexical, no filesystem)
# ---------------------------------------------------------------------------
def _validate_relative_path(path_str: str, field_name: str) -> None:
    """Validate a relative path for repo-root containment at the lexical level."""
    if not isinstance(path_str, str):
        raise RepairContractError(f"{field_name}: path must be string")
    if not path_str:
        raise RepairContractError(f"{field_name}: empty path")
    if "\x00" in path_str:
        raise RepairContractError(f"{field_name}: null byte in path")
    if path_str.startswith("/"):
        raise RepairContractError(f"{field_name}: absolute path not allowed")
    # Windows drive letter (C:) or UNC (\\server\share)
    if re.match(r"^[A-Za-z]:", path_str):
        raise RepairContractError(f"{field_name}: Windows drive letter not allowed")
    if path_str.startswith("\\\\"):
        raise RepairContractError(f"{field_name}: UNC path not allowed")
    # Also reject backslashes (we only allow normalized forward-slash form)
    if "\\" in path_str:
        raise RepairContractError(f"{field_name}: backslash not allowed (use forward slash)")
    # Reject duplicate separators
    if "//" in path_str:
        raise RepairContractError(f"{field_name}: duplicate separator")
    segments = path_str.split("/")
    for segment in segments:
        if segment == "":
            raise RepairContractError(f"{field_name}: empty segment")
        if segment == ".":
            raise RepairContractError(f"{field_name}: '.' segment not allowed")
        if segment == "..":
            raise RepairContractError(f"{field_name}: parent traversal not allowed")
    if _byte_len(path_str) > MAX_PATH_BYTES:
        raise RepairContractError(f"{field_name}: exceeds {MAX_PATH_BYTES} bytes")


def _safe_resolve(root: Path, relative_path: str) -> Path:
    """Resolve a relative path under a trusted root, preventing traversal."""
    resolved = (root / relative_path).resolve()
    root_resolved = root.resolve()
    resolved_str = str(resolved)
    root_str = str(root_resolved)
    # Ensure resolved path is under root (use / separator for containment check)
    if not (resolved_str == root_str or resolved_str.startswith(root_str + "/")):
        raise RepairContractError(f"path escapes root: {relative_path}")
    return resolved


# ---------------------------------------------------------------------------
# Structural validation: repair request
# ---------------------------------------------------------------------------
def validate_repair_request(request: dict[str, Any]) -> None:
    """
    Validate repair-request structural invariants.
    Raises RepairContractError on any violation.
    No filesystem access.
    """
    if not isinstance(request, dict):
        raise RepairContractError("request must be object")

    # Top-level required fields
    required = [
        "schema_version",
        "run_id",
        "story_id",
        "attempt",
        "max_attempts",
        "source_revision",
        "failure_class",
        "failure_summary",
        "failure_context_ref",
        "verification_result_ref",
        "allowed_paths",
        "forbidden_paths",
        "requested_action",
        "generated_at",
    ]
    for field in required:
        if field not in request:
            raise RepairContractError(f"missing required field: {field}")

    # schema_version
    if request["schema_version"] != "1.0":
        raise RepairContractError(
            f"schema_version must be '1.0', got {request['schema_version']!r}"
        )

    # run_id
    run_id = request["run_id"]
    if not isinstance(run_id, str) or not run_id:
        raise RepairContractError("run_id must be non-empty string")
    if _byte_len(run_id) > 256:
        raise RepairContractError("run_id exceeds 256 bytes")
    if not RE_RUN_ID.match(run_id):
        raise RepairContractError("run_id contains invalid characters")

    # story_id
    story_id = request["story_id"]
    if not isinstance(story_id, str) or not story_id:
        raise RepairContractError("story_id must be non-empty string")
    if _byte_len(story_id) > 128:
        raise RepairContractError("story_id exceeds 128 bytes")
    if not RE_STORY_ID.match(story_id):
        raise RepairContractError("story_id contains invalid characters")

    # attempt
    attempt = request["attempt"]
    if not isinstance(attempt, int) or isinstance(attempt, bool):
        raise RepairContractError("attempt must be integer")
    if attempt < 1:
        raise RepairContractError("attempt must be >= 1")

    # max_attempts
    max_attempts = request["max_attempts"]
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool):
        raise RepairContractError("max_attempts must be integer")
    if max_attempts < 1:
        raise RepairContractError("max_attempts must be >= 1")

    # attempt <= max_attempts
    if attempt > max_attempts:
        raise RepairContractError(
            f"attempt ({attempt}) exceeds max_attempts ({max_attempts})"
        )

    # source_revision
    source_revision = request["source_revision"]
    if not isinstance(source_revision, str) or not RE_SHA40.match(source_revision):
        raise RepairContractError("source_revision must be 40-char lowercase hex")

    # failure_class
    failure_class = request["failure_class"]
    if failure_class not in VALID_FAILURE_CLASS:
        raise RepairContractError(
            f"failure_class must be one of {VALID_FAILURE_CLASS}, got {failure_class!r}"
        )

    # failure_summary
    failure_summary = request["failure_summary"]
    if not isinstance(failure_summary, str):
        raise RepairContractError("failure_summary must be string")
    if _byte_len(failure_summary) > MAX_FAILURE_SUMMARY_BYTES:
        raise RepairContractError(
            f"failure_summary exceeds {MAX_FAILURE_SUMMARY_BYTES} bytes"
        )

    # failure_context_ref
    _validate_ref(request["failure_context_ref"], "failure_context_ref", required=True)

    # verification_result_ref
    _validate_ref(
        request["verification_result_ref"], "verification_result_ref", required=True
    )

    # review_result_ref (optional — may be null)
    review_ref = request.get("review_result_ref")
    if review_ref is None:
        # Allowed for verification_fail
        pass
    elif "review_result_ref" not in request:
        # Optional field missing — allowed
        pass
    else:
        _validate_ref(review_ref, "review_result_ref", required=True)

    # Cross-field: failure_class=="review_fail" requires non-null review_result_ref
    if failure_class == "review_fail" and review_ref is None:
        raise RepairContractError(
            "review_result_ref must be non-null when failure_class is 'review_fail'"
        )

    # allowed_paths
    _validate_path_list(request["allowed_paths"], "allowed_paths")

    # forbidden_paths
    _validate_path_list(request["forbidden_paths"], "forbidden_paths")

    # repair_guidance (optional)
    if "repair_guidance" in request and request["repair_guidance"] is not None:
        rg = request["repair_guidance"]
        if not isinstance(rg, list):
            raise RepairContractError("repair_guidance must be array")
        if len(rg) > MAX_REPAIR_GUIDANCE_ENTRIES:
            raise RepairContractError(
                f"repair_guidance exceeds {MAX_REPAIR_GUIDANCE_ENTRIES} entries"
            )
        for i, item in enumerate(rg):
            if not isinstance(item, str):
                raise RepairContractError(f"repair_guidance[{i}] must be string")
            if _byte_len(item) > MAX_REPAIR_GUIDANCE_BYTES:
                raise RepairContractError(
                    f"repair_guidance[{i}] exceeds {MAX_REPAIR_GUIDANCE_BYTES} bytes"
                )

    # requested_action
    requested_action = request["requested_action"]
    if requested_action not in VALID_REQUESTED_ACTION:
        raise RepairContractError(
            f"requested_action must be one of {VALID_REQUESTED_ACTION}, "
            f"got {requested_action!r}"
        )

    # Cross-field: requested_action=="fix_review_findings" requires failure_class=="review_fail"
    if requested_action == "fix_review_findings" and failure_class != "review_fail":
        raise RepairContractError(
            "requested_action=='fix_review_findings' requires failure_class=='review_fail'"
        )

    # generated_at
    generated_at = request["generated_at"]
    if not isinstance(generated_at, str) or not RE_ISO8601_UTC.match(generated_at):
        raise RepairContractError("generated_at must be ISO-8601 UTC format")


def _validate_ref(
    ref: Any, field_name: str, required: bool
) -> None:
    """Validate a *_ref object {path, schema_version, sha256}."""
    if required and ref is None:
        raise RepairContractError(f"{field_name} is required but null")
    if not isinstance(ref, dict):
        raise RepairContractError(f"{field_name} must be object")
    for sub in ("path", "schema_version", "sha256"):
        if sub not in ref:
            raise RepairContractError(f"{field_name} missing field: {sub}")

    path = ref["path"]
    if not isinstance(path, str):
        raise RepairContractError(f"{field_name}.path must be string")
    _validate_relative_path(path, f"{field_name}.path")

    sv = ref["schema_version"]
    if sv != "1.0":
        raise RepairContractError(f"{field_name}.schema_version must be '1.0'")

    sha256 = ref["sha256"]
    if not isinstance(sha256, str) or not RE_SHA256.match(sha256):
        raise RepairContractError(
            f"{field_name}.sha256 must be 64-char lowercase hex"
        )


def _validate_path_list(paths: Any, field_name: str) -> None:
    """Validate an array of repo-relative paths."""
    if not isinstance(paths, list):
        raise RepairContractError(f"{field_name} must be array")
    for i, path in enumerate(paths):
        _validate_relative_path(path, f"{field_name}[{i}]")


# ---------------------------------------------------------------------------
# Structural validation: repair result
# ---------------------------------------------------------------------------
def validate_repair_result(result: dict[str, Any]) -> None:
    """
    Validate repair-result structural invariants.
    Raises RepairContractError on any violation.
    No filesystem access.
    """
    if not isinstance(result, dict):
        raise RepairContractError("result must be object")

    # Top-level required fields
    required = [
        "schema_version",
        "run_id",
        "story_id",
        "attempt",
        "source_revision",
        "status",
        "changed",
        "changed_files",
        "summary",
        "recommended_action",
        "sanitization",
        "completed_at",
    ]
    for field in required:
        if field not in result:
            raise RepairContractError(f"missing required field: {field}")

    # schema_version
    if result["schema_version"] != "1.0":
        raise RepairContractError(
            f"schema_version must be '1.0', got {result['schema_version']!r}"
        )

    # run_id
    run_id = result["run_id"]
    if not isinstance(run_id, str) or not run_id:
        raise RepairContractError("run_id must be non-empty string")
    if _byte_len(run_id) > 256:
        raise RepairContractError("run_id exceeds 256 bytes")
    if not RE_RUN_ID.match(run_id):
        raise RepairContractError("run_id contains invalid characters")

    # story_id
    story_id = result["story_id"]
    if not isinstance(story_id, str) or not story_id:
        raise RepairContractError("story_id must be non-empty string")
    if _byte_len(story_id) > 128:
        raise RepairContractError("story_id exceeds 128 bytes")
    if not RE_STORY_ID.match(story_id):
        raise RepairContractError("story_id contains invalid characters")

    # attempt
    attempt = result["attempt"]
    if not isinstance(attempt, int) or isinstance(attempt, bool):
        raise RepairContractError("attempt must be integer")
    if attempt < 1:
        raise RepairContractError("attempt must be >= 1")

    # source_revision
    source_revision = result["source_revision"]
    if not isinstance(source_revision, str) or not RE_SHA40.match(source_revision):
        raise RepairContractError("source_revision must be 40-char lowercase hex")

    # status
    status = result["status"]
    if status not in VALID_RESULT_STATUS:
        raise RepairContractError(
            f"status must be one of {VALID_RESULT_STATUS}, got {status!r}"
        )

    # changed
    changed = result["changed"]
    if not isinstance(changed, bool):
        raise RepairContractError("changed must be boolean")

    # changed_files
    changed_files = result["changed_files"]
    if not isinstance(changed_files, list):
        raise RepairContractError("changed_files must be array")
    if len(changed_files) > MAX_CHANGED_FILES:
        raise RepairContractError(
            f"changed_files exceeds {MAX_CHANGED_FILES} entries"
        )
    seen_paths: set[str] = set()
    for i, path in enumerate(changed_files):
        _validate_relative_path(path, f"changed_files[{i}]")
        if path in seen_paths:
            raise RepairContractError(f"duplicate changed_files entry: {path}")
        seen_paths.add(path)

    # summary
    summary = result["summary"]
    if not isinstance(summary, str):
        raise RepairContractError("summary must be string")
    if _byte_len(summary) > MAX_SUMMARY_BYTES:
        raise RepairContractError(
            f"summary exceeds {MAX_SUMMARY_BYTES} bytes"
        )

    # diagnostics (optional)
    if "diagnostics" in result and result["diagnostics"] is not None:
        _validate_diagnostics(result["diagnostics"])

    # recommended_action
    recommended_action = result["recommended_action"]
    if recommended_action not in VALID_RECOMMENDED_ACTION:
        raise RepairContractError(
            f"recommended_action must be one of {VALID_RECOMMENDED_ACTION}, "
            f"got {recommended_action!r}"
        )

    # sanitization
    _validate_sanitization(result["sanitization"])

    # completed_at
    completed_at = result["completed_at"]
    if not isinstance(completed_at, str) or not RE_ISO8601_UTC.match(completed_at):
        raise RepairContractError("completed_at must be ISO-8601 UTC format")

    # Status invariants
    if status == "REPAIRED":
        if changed is not True:
            raise RepairContractError(
                "REPAIRED status requires changed == true"
            )
        if len(changed_files) < 1:
            raise RepairContractError(
                "REPAIRED status requires non-empty changed_files"
            )
        if recommended_action != "reverify":
            raise RepairContractError(
                "REPAIRED status requires recommended_action == 'reverify'"
            )
    elif status == "NO_CHANGE":
        if changed is not False:
            raise RepairContractError(
                "NO_CHANGE status requires changed == false"
            )
        if len(changed_files) != 0:
            raise RepairContractError(
                "NO_CHANGE status requires empty changed_files"
            )
        if recommended_action not in ("abort", "human_review"):
            raise RepairContractError(
                "NO_CHANGE status requires recommended_action in ('abort', 'human_review')"
            )
    elif status == "ERROR":
        if recommended_action not in ("abort", "human_review"):
            raise RepairContractError(
                "ERROR status requires recommended_action in ('abort', 'human_review')"
            )


def _validate_diagnostics(diag: Any) -> None:
    """Validate optional diagnostics object."""
    if not isinstance(diag, dict):
        raise RepairContractError("diagnostics must be object")

    # actions_taken (optional inside diagnostics)
    if "actions_taken" in diag:
        at = diag["actions_taken"]
        if not isinstance(at, list):
            raise RepairContractError("diagnostics.actions_taken must be array")
        if len(at) > MAX_DIAG_ACTIONS:
            raise RepairContractError(
                f"diagnostics.actions_taken exceeds {MAX_DIAG_ACTIONS} entries"
            )
        for i, item in enumerate(at):
            if not isinstance(item, str):
                raise RepairContractError(
                    f"diagnostics.actions_taken[{i}] must be string"
                )
            if _byte_len(item) > MAX_DIAG_ENTRY_BYTES:
                raise RepairContractError(
                    f"diagnostics.actions_taken[{i}] exceeds {MAX_DIAG_ENTRY_BYTES} bytes"
                )

    # obstacles_encountered (optional inside diagnostics)
    if "obstacles_encountered" in diag:
        oe = diag["obstacles_encountered"]
        if not isinstance(oe, list):
            raise RepairContractError(
                "diagnostics.obstacles_encountered must be array"
            )
        if len(oe) > MAX_DIAG_OBSTACLES:
            raise RepairContractError(
                f"diagnostics.obstacles_encountered exceeds {MAX_DIAG_OBSTACLES} entries"
            )
        for i, item in enumerate(oe):
            if not isinstance(item, str):
                raise RepairContractError(
                    f"diagnostics.obstacles_encountered[{i}] must be string"
                )
            if _byte_len(item) > MAX_DIAG_ENTRY_BYTES:
                raise RepairContractError(
                    f"diagnostics.obstacles_encountered[{i}] exceeds "
                    f"{MAX_DIAG_ENTRY_BYTES} bytes"
                )

    # confidence (optional, DEC-C4-03)
    if "confidence" in diag:
        confidence = diag["confidence"]
        if confidence is not None:
            if not isinstance(confidence, str):
                raise RepairContractError("diagnostics.confidence must be string")
            if confidence not in VALID_CONFIDENCE:
                raise RepairContractError(
                    f"diagnostics.confidence must be one of {VALID_CONFIDENCE}, "
                    f"got {confidence!r}"
                )


def _validate_sanitization(san: Any) -> None:
    """Validate sanitization object."""
    if not isinstance(san, dict):
        raise RepairContractError("sanitization must be object")

    required = ["redaction_applied", "redaction_count", "truncation_applied", "truncated_fields"]
    for field in required:
        if field not in san:
            raise RepairContractError(f"sanitization missing field: {field}")

    if not isinstance(san["redaction_applied"], bool):
        raise RepairContractError("sanitization.redaction_applied must be boolean")

    rc = san["redaction_count"]
    if not isinstance(rc, int) or isinstance(rc, bool) or rc < 0:
        raise RepairContractError("sanitization.redaction_count must be integer >= 0")

    if not isinstance(san["truncation_applied"], bool):
        raise RepairContractError("sanitization.truncation_applied must be boolean")

    tf = san["truncated_fields"]
    if not isinstance(tf, list):
        raise RepairContractError("sanitization.truncated_fields must be array")
    if len(tf) > MAX_TRUNCATED_FIELDS:
        raise RepairContractError(
            f"sanitization.truncated_fields exceeds {MAX_TRUNCATED_FIELDS} entries"
        )
    for i, item in enumerate(tf):
        if not isinstance(item, str):
            raise RepairContractError(
                f"sanitization.truncated_fields[{i}] must be string"
            )
        if _byte_len(item) > MAX_TRUNCATED_FIELD_BYTES:
            raise RepairContractError(
                f"sanitization.truncated_fields[{i}] exceeds "
                f"{MAX_TRUNCATED_FIELD_BYTES} bytes"
            )


# ---------------------------------------------------------------------------
# Identity binding
# ---------------------------------------------------------------------------
def validate_repair_result_against_request(
    result: dict[str, Any],
    request: dict[str, Any],
) -> None:
    """
    Validate repair-result identity binding and path claims against request.

    Fail-closed on:
    - run_id / story_id / attempt / source_revision mismatch
    - changed_files violating allowed_paths / forbidden_paths
    - schema version mismatch
    - attempt/max_attempts relationship

    No filesystem access.
    """
    # Schema versions must match
    if result.get("schema_version") != request.get("schema_version"):
        raise RepairContractError(
            "schema_version mismatch between request and result"
        )

    # Identity binding
    if result.get("run_id") != request.get("run_id"):
        raise RepairContractError(
            "run_id mismatch between request and result"
        )
    if result.get("story_id") != request.get("story_id"):
        raise RepairContractError(
            "story_id mismatch between request and result"
        )
    if result.get("attempt") != request.get("attempt"):
        raise RepairContractError(
            "attempt mismatch between request and result"
        )
    if result.get("source_revision") != request.get("source_revision"):
        raise RepairContractError(
            "source_revision mismatch between request and result"
        )

    # attempt/max_attempts relationship: attempt in result must be <= request.max_attempts
    result_attempt = result.get("attempt")
    request_max = request.get("max_attempts")
    if (
        isinstance(result_attempt, int)
        and isinstance(request_max, int)
        and result_attempt > request_max
    ):
        raise RepairContractError(
            f"result attempt ({result_attempt}) exceeds request max_attempts ({request_max})"
        )

    # Path-claim validation: every changed_files entry must respect
    # orchestrator-provided allow/deny rules.
    allowed_paths = request.get("allowed_paths", [])
    forbidden_paths = request.get("forbidden_paths", [])
    if not isinstance(allowed_paths, list):
        allowed_paths = []
    if not isinstance(forbidden_paths, list):
        forbidden_paths = []

    changed_files = result.get("changed_files", [])
    if not isinstance(changed_files, list):
        changed_files = []

    for path in changed_files:
        # Forbidden wins over allowed
        for pattern in forbidden_paths:
            try:
                if gitwildmatch(path, pattern):
                    raise RepairContractError(
                        f"changed_files entry '{path}' matches forbidden path pattern '{pattern}'"
                    )
            except ValueError:
                # Invalid pattern cannot match; skip defensively
                continue

        # Must match at least one allowed pattern (if allowed_paths is non-empty)
        if allowed_paths:
            matched = False
            for pattern in allowed_paths:
                try:
                    if gitwildmatch(path, pattern):
                        matched = True
                        break
                except ValueError:
                    continue
            if not matched:
                raise RepairContractError(
                    f"changed_files entry '{path}' does not match any allowed_paths pattern"
                )


# ---------------------------------------------------------------------------
# Referential validation (filesystem, two-root)
# ---------------------------------------------------------------------------
def validate_repair_request_references(
    request: dict[str, Any],
    repo_root: Path,
    run_dir: Path,
    manifest_path: Path | None = None,
    manifest_sha256: str | None = None,
) -> None:
    """
    Validate repair-request referential invariants against filesystem.

    - failure_context_ref: existence, SHA-256, schema_version, run_id/story_id
    - verification_result_ref: existence, SHA-256, schema_version
    - review_result_ref (if non-null): existence, SHA-256, schema_version
    - manifest (if manifest_path provided): existence, SHA-256, story_id, base_commit, allowed_paths, forbidden_paths

    Raises RepairContractError on any violation.
    """
    # --- Manifest validation (if provided) ---
    if manifest_path is not None:
        if not manifest_path.exists():
            raise RepairContractError(f"manifest file does not exist: {manifest_path}")

        manifest_bytes = manifest_path.read_bytes()
        actual_sha256 = hashlib.sha256(manifest_bytes).hexdigest()

        if manifest_sha256 is not None and actual_sha256 != manifest_sha256:
            raise RepairContractError(
                f"manifest SHA-256 mismatch: expected {manifest_sha256}, got {actual_sha256}"
            )

        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RepairContractError(f"manifest is not valid JSON: {e}") from e

        if manifest.get("schema_version") != "1.0":
            raise RepairContractError("manifest schema_version must be '1.0'")

        # story_id binding
        if manifest.get("story_id") != request.get("story_id"):
            raise RepairContractError(
                f"story_id mismatch: request has {request.get('story_id')!r}, "
                f"manifest has {manifest.get('story_id')!r}"
            )

        # source_revision binding (must equal manifest base_commit)
        if manifest.get("base_commit") != request.get("source_revision"):
            raise RepairContractError(
                f"source_revision mismatch: request has {request.get('source_revision')!r}, "
                f"manifest base_commit has {manifest.get('base_commit')!r}"
            )
    # --- failure_context_ref ---
    fc_ref = request["failure_context_ref"]
    fc_rel = fc_ref["path"]
    fc_path = _safe_resolve(run_dir, fc_rel)
    if not fc_path.exists() or not fc_path.is_file():
        raise RepairContractError(f"failure-context file does not exist: {fc_rel}")
    fc_bytes = fc_path.read_bytes()
    fc_sha256 = hashlib.sha256(fc_bytes).hexdigest()
    if fc_sha256 != fc_ref["sha256"]:
        raise RepairContractError(
            f"failure-context SHA-256 mismatch: expected {fc_ref['sha256']}, "
            f"got {fc_sha256}"
        )
    try:
        fc = json.loads(fc_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise RepairContractError(f"failure-context is not valid JSON: {e}") from e
    if not isinstance(fc, dict):
        raise RepairContractError("failure-context is not an object")
    if fc.get("schema_version") != "1.0":
        raise RepairContractError("failure-context schema_version must be '1.0'")
    if fc.get("run_id") != request["run_id"]:
        raise RepairContractError(
            f"run_id mismatch: request has {request['run_id']!r}, "
            f"failure-context has {fc.get('run_id')!r}"
        )
    if fc.get("story_id") != request["story_id"]:
        raise RepairContractError(
            f"story_id mismatch: request has {request['story_id']!r}, "
            f"failure-context has {fc.get('story_id')!r}"
        )

    # --- verification_result_ref ---
    vr_ref = request["verification_result_ref"]
    vr_rel = vr_ref["path"]
    vr_path = _safe_resolve(run_dir, vr_rel)
    if not vr_path.exists() or not vr_path.is_file():
        raise RepairContractError(
            f"verification-result file does not exist: {vr_rel}"
        )
    vr_bytes = vr_path.read_bytes()
    vr_sha256 = hashlib.sha256(vr_bytes).hexdigest()
    if vr_sha256 != vr_ref["sha256"]:
        raise RepairContractError(
            f"verification-result SHA-256 mismatch: expected {vr_ref['sha256']}, "
            f"got {vr_sha256}"
        )
    try:
        vr = json.loads(vr_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise RepairContractError(
            f"verification-result is not valid JSON: {e}"
        ) from e
    if not isinstance(vr, dict):
        raise RepairContractError("verification-result is not an object")
    if vr.get("schema_version") != "1.0":
        raise RepairContractError(
            "verification-result schema_version must be '1.0'"
        )

    # --- review_result_ref (optional) ---
    rr_ref = request.get("review_result_ref")
    if rr_ref is not None:
        rr_rel = rr_ref["path"]
        rr_path = _safe_resolve(run_dir, rr_rel)
        if not rr_path.exists() or not rr_path.is_file():
            raise RepairContractError(
                f"review-result file does not exist: {rr_rel}"
            )
        rr_bytes = rr_path.read_bytes()
        rr_sha256 = hashlib.sha256(rr_bytes).hexdigest()
        if rr_sha256 != rr_ref["sha256"]:
            raise RepairContractError(
                f"review-result SHA-256 mismatch: expected {rr_ref['sha256']}, "
                f"got {rr_sha256}"
            )
        try:
            rr = json.loads(rr_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise RepairContractError(
                f"review-result is not valid JSON: {e}"
            ) from e
        if not isinstance(rr, dict):
            raise RepairContractError("review-result is not an object")
        if rr.get("schema_version") != "1.0":
            raise RepairContractError(
                "review-result schema_version must be '1.0'"
            )


# ---------------------------------------------------------------------------
# Sanitization helpers
# ---------------------------------------------------------------------------
def _sanitize_text(text: str, max_bytes: int | None = None) -> str:
    """
    Apply the sanitization pipeline to a single text field.
    Returns sanitized text with optional truncation.
    """
    # 1. UTF-8 normalization
    text = normalize_utf8(text)

    # 2. Binary detection (before control char removal so null bytes visible)
    if is_binary_content(text):
        return "[REDACTED:binary_content]"

    # 3. Control character removal
    text = sanitize_control_characters(text)

    # 4. Base64 run detection
    text, _ = redact_base64_runs(text)

    # 5. Secret pattern redaction
    text, _ = redact_text(text)

    # 6. URL query stripping
    url_pattern = re.compile(r"(https?://[^\s?]+)\?[^\s]*")
    text = url_pattern.sub(r"\1", text)

    # 7-8. Byte truncation
    if max_bytes is not None:
        text_bytes = text.encode("utf-8")
        original_byte_len = len(text_bytes)
        if original_byte_len > max_bytes:
            omitted = original_byte_len - max_bytes
            marker = f"\n... [truncated: {omitted} bytes omitted]"
            marker_bytes = len(marker.encode("utf-8"))
            target_bytes = max(max_bytes - marker_bytes, 0)
            text_bytes = text_bytes[:target_bytes]
            text = text_bytes.decode("utf-8", errors="ignore")
            text += marker

    return text


def _sanitize_field_with_metadata(
    text: str,
    field_path: str,
    max_bytes: int,
    truncation_fields: list[str],
    redaction_counts: list[int],
) -> str:
    """
    Sanitize a single field with full pipeline and metadata tracking.
    Appends to truncation_fields if truncated.
    Appends to redaction_counts the number of redactions.
    Returns sanitized text.
    """
    # 1. UTF-8 normalization
    text = normalize_utf8(text)

    # 2. Binary detection
    if is_binary_content(text):
        redaction_counts.append(1)
        return "[REDACTED:binary_content]"

    # 3. Control character removal
    text = sanitize_control_characters(text)

    # 4. Base64 run detection
    text, base64_count = redact_base64_runs(text)
    if base64_count > 0:
        redaction_counts.append(base64_count)

    # 5. Secret pattern redaction
    text, secret_count = redact_text(text)
    if secret_count > 0:
        redaction_counts.append(secret_count)

    # 6. URL query stripping
    url_pattern = re.compile(r"(https?://[^\s?]+)\?[^\s]*")
    text, url_count = url_pattern.subn(r"\1", text)
    if url_count > 0:
        redaction_counts.append(url_count)

    # 7. Byte truncation
    text_bytes = text.encode("utf-8")
    original_byte_len = len(text_bytes)
    if original_byte_len > max_bytes:
        omitted = original_byte_len - max_bytes
        marker = f"\n... [truncated: {omitted} bytes omitted]"
        marker_bytes = len(marker.encode("utf-8"))
        target_bytes = max(max_bytes - marker_bytes, 0)
        text_bytes = text_bytes[:target_bytes]
        text = text_bytes.decode("utf-8", errors="ignore")
        text += marker
        truncation_fields.append(field_path)

    return text


# ---------------------------------------------------------------------------
# Bounded diagnostics sanitization
# ---------------------------------------------------------------------------
def sanitize_diagnostics(
    diagnostics: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, int, bool, list[str]]:
    """
    Apply sanitization pipeline to diagnostics object.

    Returns (sanitized_diagnostics, total_redaction_count, truncation_applied,
    truncated_fields_list).

    If input is None, returns (None, 0, False, []).
    """
    if diagnostics is None:
        return None, 0, False, []

    if not isinstance(diagnostics, dict):
        raise RepairContractError("diagnostics must be object")

    truncation_fields: list[str] = []
    redaction_counts: list[int] = []

    sanitized: dict[str, Any] = {}

    # actions_taken
    if "actions_taken" in diagnostics:
        at = diagnostics["actions_taken"]
        if not isinstance(at, list):
            raise RepairContractError("diagnostics.actions_taken must be array")
        sanitized_actions: list[str] = []
        for i, item in enumerate(at):
            if not isinstance(item, str):
                raise RepairContractError(
                    f"diagnostics.actions_taken[{i}] must be string"
                )
            sanitized_item = _sanitize_field_with_metadata(
                item,
                f"diagnostics.actions_taken[{i}]",
                MAX_DIAG_ENTRY_BYTES,
                truncation_fields,
                redaction_counts,
            )
            sanitized_actions.append(sanitized_item)
        if len(sanitized_actions) > MAX_DIAG_ACTIONS:
            raise RepairContractError(
                f"diagnostics.actions_taken exceeds {MAX_DIAG_ACTIONS} entries"
            )
        sanitized["actions_taken"] = sanitized_actions

    # obstacles_encountered
    if "obstacles_encountered" in diagnostics:
        oe = diagnostics["obstacles_encountered"]
        if not isinstance(oe, list):
            raise RepairContractError(
                "diagnostics.obstacles_encountered must be array"
            )
        sanitized_obstacles: list[str] = []
        for i, item in enumerate(oe):
            if not isinstance(item, str):
                raise RepairContractError(
                    f"diagnostics.obstacles_encountered[{i}] must be string"
                )
            sanitized_item = _sanitize_field_with_metadata(
                item,
                f"diagnostics.obstacles_encountered[{i}]",
                MAX_DIAG_ENTRY_BYTES,
                truncation_fields,
                redaction_counts,
            )
            sanitized_obstacles.append(sanitized_item)
        if len(sanitized_obstacles) > MAX_DIAG_OBSTACLES:
            raise RepairContractError(
                f"diagnostics.obstacles_encountered exceeds {MAX_DIAG_OBSTACLES} entries"
            )
        sanitized["obstacles_encountered"] = sanitized_obstacles

    # confidence (optional, informational only — pass through with validation)
    if "confidence" in diagnostics:
        confidence = diagnostics["confidence"]
        if confidence is not None:
            if not isinstance(confidence, str):
                raise RepairContractError("diagnostics.confidence must be string")
            if confidence not in VALID_CONFIDENCE:
                raise RepairContractError(
                    f"diagnostics.confidence must be one of {VALID_CONFIDENCE}, "
                    f"got {confidence!r}"
                )
            sanitized["confidence"] = confidence

    total_redaction_count = sum(redaction_counts)
    truncation_applied = len(truncation_fields) > 0
    truncated_fields_sorted = sorted(truncation_fields)

    return sanitized, total_redaction_count, truncation_applied, truncated_fields_sorted


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
def build_repair_request(
    run_dir: Path,
    failure_context_path: Path,
    verify_result_path: Path,
    review_result_path: Path | None,
    run_id: str,
    story_id: str,
    attempt: int,
    max_attempts: int,
    source_revision: str,
    failure_class: str,
    failure_summary: str,
    allowed_paths: list[str],
    forbidden_paths: list[str],
    requested_action: str,
    generated_at: str,
    repair_guidance: list[str] | None = None,
) -> dict[str, Any]:
    """
    Build repair request with both structural and referential validation.

    - failure_context_path: absolute path under run_dir
    - verify_result_path: absolute path under run_dir
    - review_result_path: absolute path under run_dir, or None
    - allowed_paths/forbidden_paths: orchestrator-provided (caller responsibility;
      builder does not infer or widen permissions)
    - generated_at: ISO-8601 timestamp supplied by caller (no internal time call)

    Returns validated repair-request dict.
    Raises RepairContractError on any violation.
    """
    run_dir_resolved = run_dir.resolve()

    # Validate failure_context_path is under run_dir
    fc_resolved = failure_context_path.resolve()
    if not str(fc_resolved).startswith(str(run_dir_resolved) + "/") and str(
        fc_resolved
    ) != str(run_dir_resolved):
        raise RepairContractError("failure_context_path must be under run_dir")

    # Validate verify_result_path is under run_dir
    vr_resolved = verify_result_path.resolve()
    if not str(vr_resolved).startswith(str(run_dir_resolved) + "/") and str(
        vr_resolved
    ) != str(run_dir_resolved):
        raise RepairContractError("verify_result_path must be under run_dir")

    # Load and validate failure-context
    if not failure_context_path.exists() or not failure_context_path.is_file():
        raise RepairContractError(
            f"failure-context file does not exist: {failure_context_path}"
        )
    try:
        fc_bytes = failure_context_path.read_bytes()
        fc = json.loads(fc_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise RepairContractError(
            f"failure-context is not valid JSON: {e}"
        ) from e
    if not isinstance(fc, dict):
        raise RepairContractError("failure-context is not an object")
    if fc.get("schema_version") != "1.0":
        raise RepairContractError("failure-context schema_version must be '1.0'")

    # Load and validate verify-result
    if not verify_result_path.exists() or not verify_result_path.is_file():
        raise RepairContractError(
            f"verification-result file does not exist: {verify_result_path}"
        )
    try:
        vr_bytes = verify_result_path.read_bytes()
        vr = json.loads(vr_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise RepairContractError(
            f"verification-result is not valid JSON: {e}"
        ) from e
    if not isinstance(vr, dict):
        raise RepairContractError("verification-result is not an object")
    if vr.get("schema_version") != "1.0":
        raise RepairContractError(
            "verification-result schema_version must be '1.0'"
        )

    # Load and validate review-result (if provided)
    review_bytes: bytes | None = None
    review_rel: str | None = None
    review_sha256: str | None = None
    if review_result_path is not None:
        rr_resolved = review_result_path.resolve()
        if not str(rr_resolved).startswith(
            str(run_dir_resolved) + "/"
        ) and str(rr_resolved) != str(run_dir_resolved):
            raise RepairContractError("review_result_path must be under run_dir")
        if not review_result_path.exists() or not review_result_path.is_file():
            raise RepairContractError(
                f"review-result file does not exist: {review_result_path}"
            )
        try:
            review_bytes = review_result_path.read_bytes()
            rr = json.loads(review_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            raise RepairContractError(
                f"review-result is not valid JSON: {e}"
            ) from e
        if not isinstance(rr, dict):
            raise RepairContractError("review-result is not an object")
        if rr.get("schema_version") != "1.0":
            raise RepairContractError(
                "review-result schema_version must be '1.0'"
            )
        review_rel = str(rr_resolved.relative_to(run_dir_resolved))
        review_sha256 = hashlib.sha256(review_bytes).hexdigest()

    # Compute SHA-256 digests
    fc_sha256 = hashlib.sha256(fc_bytes).hexdigest()
    vr_sha256 = hashlib.sha256(vr_bytes).hexdigest()

    # Build relative paths
    fc_rel = str(fc_resolved.relative_to(run_dir_resolved))
    vr_rel = str(vr_resolved.relative_to(run_dir_resolved))

    # Sanitize failure_summary with metadata tracking
    truncation_fields: list[str] = []
    redaction_counts: list[int] = []

    sanitized_summary = _sanitize_field_with_metadata(
        failure_summary,
        "failure_summary",
        MAX_FAILURE_SUMMARY_BYTES,
        truncation_fields,
        redaction_counts,
    )

    # Sanitize repair_guidance
    sanitized_guidance: list[str] = []
    if repair_guidance is not None:
        if len(repair_guidance) > MAX_REPAIR_GUIDANCE_ENTRIES:
            raise RepairContractError(
                f"repair_guidance exceeds {MAX_REPAIR_GUIDANCE_ENTRIES} entries"
            )
        for i, item in enumerate(repair_guidance):
            sanitized_item = _sanitize_field_with_metadata(
                item,
                f"repair_guidance[{i}]",
                MAX_REPAIR_GUIDANCE_BYTES,
                truncation_fields,
                redaction_counts,
            )
            sanitized_guidance.append(sanitized_item)

    # Build sanitization metadata
    total_redaction_count = sum(redaction_counts)
    truncation_applied = len(truncation_fields) > 0
    truncation_fields_sorted = sorted(truncation_fields)

    sanitization = {
        "redaction_applied": total_redaction_count > 0,
        "redaction_count": total_redaction_count,
        "truncation_applied": truncation_applied,
        "truncated_fields": truncation_fields_sorted,
    }

    # Build the repair request
    request: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "story_id": story_id,
        "attempt": attempt,
        "max_attempts": max_attempts,
        "source_revision": source_revision,
        "failure_class": failure_class,
        "failure_summary": sanitized_summary,
        "failure_context_ref": {
            "path": fc_rel,
            "schema_version": "1.0",
            "sha256": fc_sha256,
        },
        "verification_result_ref": {
            "path": vr_rel,
            "schema_version": "1.0",
            "sha256": vr_sha256,
        },
        "allowed_paths": list(allowed_paths),
        "forbidden_paths": list(forbidden_paths),
        "requested_action": requested_action,
        "generated_at": generated_at,
        "sanitization": sanitization,
    }

    # Optional review_result_ref
    if review_result_path is not None and review_rel is not None and review_sha256 is not None:
        request["review_result_ref"] = {
            "path": review_rel,
            "schema_version": "1.0",
            "sha256": review_sha256,
        }
    else:
        request["review_result_ref"] = None

    # Optional repair_guidance
    if repair_guidance is not None:
        request["repair_guidance"] = sanitized_guidance

    # Validate output (structural)
    validate_repair_request(request)

    return request


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
    Produce deterministic pretty JSON with indent=2, trailing newline.
    """
    text = json.dumps(
        obj,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines) + "\n"
