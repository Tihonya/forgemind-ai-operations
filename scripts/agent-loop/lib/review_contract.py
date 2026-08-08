"""
WP-AL-1C1: Review request/result contract for the agent-loop review phase.

Defines review-request and review-result schemas v1.0 with structural validators,
a two-root referential validator, and a deterministic builder. No LLM invocation,
no adapter, no repair, no orchestration.

Schema: .agent-loop/review/SCHEMA.md

Deterministic, stdlib-only, no network/LLM/shell. Imports narrow public API
from failure_context.py for sanitization. Validates output before publish.
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


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------
class ReviewContractError(Exception):
    """Raised when a review contract invariant is violated."""


# ---------------------------------------------------------------------------
# Regex patterns for field validation
# ---------------------------------------------------------------------------
RE_RUN_ID = re.compile(r"^[A-Za-z0-9_\-:]+$")
RE_STORY_ID = re.compile(r"^[A-Za-z0-9_\-]+$")
RE_REVIEWER_ID = re.compile(r"^[A-Za-z0-9_\-]+$")
RE_SHA256 = re.compile(r"^[0-9a-f]{64}$")
RE_SHA40 = re.compile(r"^[0-9a-f]{40}$")
RE_ISO8601_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
RE_RELATIVE_PATH = re.compile(r"^[^/].*$")  # no leading slash


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------
def _validate_relative_path(path_str: str, field_name: str) -> None:
    """Validate a relative path has no traversal or absolute prefix."""
    if not path_str:
        raise ReviewContractError(f"{field_name}: empty path")
    if path_str.startswith("/"):
        raise ReviewContractError(f"{field_name}: absolute path not allowed")
    if ".." in path_str.split("/"):
        raise ReviewContractError(f"{field_name}: path traversal not allowed")
    if re.match(r"^[A-Za-z]:", path_str):
        raise ReviewContractError(f"{field_name}: Windows drive letter not allowed")
    if path_str.startswith("\\\\"):
        raise ReviewContractError(f"{field_name}: UNC path not allowed")


def _safe_resolve(root: Path, relative_path: str) -> Path:
    """Resolve a relative path under a trusted root, preventing traversal."""
    resolved = (root / relative_path).resolve()
    root_resolved = root.resolve()
    if not str(resolved).startswith(str(root_resolved)):
        raise ReviewContractError(f"path escapes root: {relative_path}")
    return resolved


# ---------------------------------------------------------------------------
# Byte-size helpers
# ---------------------------------------------------------------------------
def _byte_len(text: str) -> int:
    """Return UTF-8 byte length of a string."""
    return len(text.encode("utf-8"))


# ---------------------------------------------------------------------------
# Structural validation: review request
# ---------------------------------------------------------------------------
def validate_review_request(request: dict[str, Any]) -> None:
    """
    Validate review-request structural invariants.
    Raises ReviewContractError on any violation.
    No filesystem access.
    """
    # Top-level required fields
    required = [
        "schema_version",
        "run_id",
        "story_id",
        "review_iteration",
        "repair_iteration",
        "triggered_by",
        "generated_at",
        "reviewer_id",
        "manifest_ref",
        "manifest_excerpt",
        "failure_context_ref",
        "candidate_identity",
        "sanitization",
    ]
    for field in required:
        if field not in request:
            raise ReviewContractError(f"missing required field: {field}")

    # schema_version
    if request["schema_version"] != "1.0":
        raise ReviewContractError(f"schema_version must be '1.0', got {request['schema_version']}")

    # run_id
    run_id = request["run_id"]
    if not isinstance(run_id, str) or not run_id:
        raise ReviewContractError("run_id must be non-empty string")
    if _byte_len(run_id) > 256:
        raise ReviewContractError("run_id exceeds 256 bytes")
    if not RE_RUN_ID.match(run_id):
        raise ReviewContractError("run_id contains invalid characters")

    # story_id
    story_id = request["story_id"]
    if not isinstance(story_id, str) or not story_id:
        raise ReviewContractError("story_id must be non-empty string")
    if _byte_len(story_id) > 128:
        raise ReviewContractError("story_id exceeds 128 bytes")
    if not RE_STORY_ID.match(story_id):
        raise ReviewContractError("story_id contains invalid characters")

    # review_iteration
    review_iteration = request["review_iteration"]
    if not isinstance(review_iteration, int) or review_iteration < 1:
        raise ReviewContractError("review_iteration must be integer >= 1")

    # repair_iteration
    repair_iteration = request["repair_iteration"]
    if not isinstance(repair_iteration, int) or repair_iteration < 0:
        raise ReviewContractError("repair_iteration must be integer >= 0")

    # Cross-field: review_iteration == repair_iteration + 1
    if review_iteration != repair_iteration + 1:
        raise ReviewContractError(
            f"review_iteration ({review_iteration}) must equal repair_iteration ({repair_iteration}) + 1"
        )

    # triggered_by
    triggered_by = request["triggered_by"]
    if triggered_by not in ("initial_verify_pass", "initial_verify_fail", "post_repair_verify_pass"):
        raise ReviewContractError(f"invalid triggered_by: {triggered_by}")

    # Cross-field: triggered_by + repair_iteration
    if triggered_by == "initial_verify_pass" and repair_iteration != 0:
        raise ReviewContractError("initial_verify_pass requires repair_iteration == 0")
    if triggered_by == "initial_verify_fail" and repair_iteration != 0:
        raise ReviewContractError("initial_verify_fail requires repair_iteration == 0")
    if triggered_by == "post_repair_verify_pass" and repair_iteration < 1:
        raise ReviewContractError("post_repair_verify_pass requires repair_iteration >= 1")

    # generated_at
    generated_at = request["generated_at"]
    if not isinstance(generated_at, str) or not RE_ISO8601_UTC.match(generated_at):
        raise ReviewContractError("generated_at must be ISO-8601 UTC format")

    # reviewer_id
    reviewer_id = request["reviewer_id"]
    if not isinstance(reviewer_id, str) or not reviewer_id:
        raise ReviewContractError("reviewer_id must be non-empty string")
    if _byte_len(reviewer_id) > 128:
        raise ReviewContractError("reviewer_id exceeds 128 bytes")
    if not RE_REVIEWER_ID.match(reviewer_id):
        raise ReviewContractError("reviewer_id contains invalid characters")

    # manifest_ref
    _validate_manifest_ref(request["manifest_ref"])

    # manifest_excerpt
    _validate_manifest_excerpt(request["manifest_excerpt"])

    # failure_context_ref
    _validate_failure_context_ref(request["failure_context_ref"])

    # candidate_identity
    _validate_candidate_identity(request["candidate_identity"])

    # sanitization
    _validate_sanitization(request["sanitization"])


def _validate_manifest_ref(ref: dict[str, Any]) -> None:
    """Validate manifest_ref object."""
    if not isinstance(ref, dict):
        raise ReviewContractError("manifest_ref must be object")
    for field in ["path", "schema_version", "sha256"]:
        if field not in ref:
            raise ReviewContractError(f"manifest_ref missing field: {field}")

    path = ref["path"]
    if not isinstance(path, str):
        raise ReviewContractError("manifest_ref.path must be string")
    if _byte_len(path) > 512:
        raise ReviewContractError("manifest_ref.path exceeds 512 bytes")
    _validate_relative_path(path, "manifest_ref.path")

    if ref["schema_version"] != "1.0":
        raise ReviewContractError("manifest_ref.schema_version must be '1.0'")

    sha256 = ref["sha256"]
    if not isinstance(sha256, str) or not RE_SHA256.match(sha256):
        raise ReviewContractError("manifest_ref.sha256 must be 64-char lowercase hex")


def _validate_manifest_excerpt(excerpt: dict[str, Any]) -> None:
    """Validate manifest_excerpt object."""
    if not isinstance(excerpt, dict):
        raise ReviewContractError("manifest_excerpt must be object")

    required = ["title", "description", "acceptance_criteria", "allowed_paths", "forbidden_paths"]
    for field in required:
        if field not in excerpt:
            raise ReviewContractError(f"manifest_excerpt missing field: {field}")

    # title
    title = excerpt["title"]
    if not isinstance(title, str):
        raise ReviewContractError("manifest_excerpt.title must be string")
    if _byte_len(title) > 256:
        raise ReviewContractError("manifest_excerpt.title exceeds 256 bytes")

    # description
    description = excerpt["description"]
    if not isinstance(description, str):
        raise ReviewContractError("manifest_excerpt.description must be string")
    if _byte_len(description) > 2048:
        raise ReviewContractError("manifest_excerpt.description exceeds 2048 bytes")

    # acceptance_criteria
    ac = excerpt["acceptance_criteria"]
    if not isinstance(ac, list):
        raise ReviewContractError("manifest_excerpt.acceptance_criteria must be array")
    if len(ac) > 20:
        raise ReviewContractError("manifest_excerpt.acceptance_criteria exceeds 20 entries")
    for i, item in enumerate(ac):
        if not isinstance(item, str):
            raise ReviewContractError(f"manifest_excerpt.acceptance_criteria[{i}] must be string")
        if _byte_len(item) > 512:
            raise ReviewContractError(f"manifest_excerpt.acceptance_criteria[{i}] exceeds 512 bytes")

    # repair_guidance (optional)
    if "repair_guidance" in excerpt:
        rg = excerpt["repair_guidance"]
        if not isinstance(rg, list):
            raise ReviewContractError("manifest_excerpt.repair_guidance must be array")
        if len(rg) > 10:
            raise ReviewContractError("manifest_excerpt.repair_guidance exceeds 10 entries")
        for i, item in enumerate(rg):
            if not isinstance(item, str):
                raise ReviewContractError(f"manifest_excerpt.repair_guidance[{i}] must be string")
            if _byte_len(item) > 256:
                raise ReviewContractError(f"manifest_excerpt.repair_guidance[{i}] exceeds 256 bytes")

    # allowed_paths
    allowed = excerpt["allowed_paths"]
    if not isinstance(allowed, list):
        raise ReviewContractError("manifest_excerpt.allowed_paths must be array")
    for i, path in enumerate(allowed):
        if not isinstance(path, str):
            raise ReviewContractError(f"manifest_excerpt.allowed_paths[{i}] must be string")
        _validate_relative_path(path, f"manifest_excerpt.allowed_paths[{i}]")

    # forbidden_paths
    forbidden = excerpt["forbidden_paths"]
    if not isinstance(forbidden, list):
        raise ReviewContractError("manifest_excerpt.forbidden_paths must be array")
    for i, path in enumerate(forbidden):
        if not isinstance(path, str):
            raise ReviewContractError(f"manifest_excerpt.forbidden_paths[{i}] must be string")
        _validate_relative_path(path, f"manifest_excerpt.forbidden_paths[{i}]")


def _validate_failure_context_ref(ref: dict[str, Any]) -> None:
    """Validate failure_context_ref object."""
    if not isinstance(ref, dict):
        raise ReviewContractError("failure_context_ref must be object")
    for field in ["path", "schema_version", "sha256"]:
        if field not in ref:
            raise ReviewContractError(f"failure_context_ref missing field: {field}")

    path = ref["path"]
    if not isinstance(path, str):
        raise ReviewContractError("failure_context_ref.path must be string")
    if _byte_len(path) > 512:
        raise ReviewContractError("failure_context_ref.path exceeds 512 bytes")
    _validate_relative_path(path, "failure_context_ref.path")

    if ref["schema_version"] != "1.0":
        raise ReviewContractError("failure_context_ref.schema_version must be '1.0'")

    sha256 = ref["sha256"]
    if not isinstance(sha256, str) or not RE_SHA256.match(sha256):
        raise ReviewContractError("failure_context_ref.sha256 must be 64-char lowercase hex")


def _validate_candidate_identity(ci: dict[str, Any]) -> None:
    """Validate candidate_identity object."""
    if not isinstance(ci, dict):
        raise ReviewContractError("candidate_identity must be object")
    for field in ["base_commit", "candidate_commit", "candidate_state", "candidate_diff_digest"]:
        if field not in ci:
            raise ReviewContractError(f"candidate_identity missing field: {field}")

    base_commit = ci["base_commit"]
    if not isinstance(base_commit, str) or not RE_SHA40.match(base_commit):
        raise ReviewContractError("candidate_identity.base_commit must be 40-char lowercase hex")

    candidate_commit = ci["candidate_commit"]
    candidate_state = ci["candidate_state"]

    if candidate_state not in ("committed", "working_tree"):
        raise ReviewContractError("candidate_identity.candidate_state must be 'committed' or 'working_tree'")

    if candidate_state == "committed":
        if candidate_commit is None or not isinstance(candidate_commit, str) or not RE_SHA40.match(candidate_commit):
            raise ReviewContractError(
                "candidate_identity.candidate_commit must be 40-char hex when state is 'committed'"
            )
    elif candidate_state == "working_tree" and candidate_commit is not None:
        raise ReviewContractError("candidate_identity.candidate_commit must be null when state is 'working_tree'")

    diff_digest = ci["candidate_diff_digest"]
    if not isinstance(diff_digest, str) or not RE_SHA256.match(diff_digest):
        raise ReviewContractError("candidate_identity.candidate_diff_digest must be 64-char lowercase hex")


def _validate_sanitization(san: dict[str, Any]) -> None:
    """Validate sanitization object."""
    if not isinstance(san, dict):
        raise ReviewContractError("sanitization must be object")

    required = ["redaction_applied", "redaction_count", "truncation_applied", "truncated_fields"]
    for field in required:
        if field not in san:
            raise ReviewContractError(f"sanitization missing field: {field}")

    if not isinstance(san["redaction_applied"], bool):
        raise ReviewContractError("sanitization.redaction_applied must be boolean")

    rc = san["redaction_count"]
    if not isinstance(rc, int) or rc < 0:
        raise ReviewContractError("sanitization.redaction_count must be integer >= 0")

    if not isinstance(san["truncation_applied"], bool):
        raise ReviewContractError("sanitization.truncation_applied must be boolean")

    tf = san["truncated_fields"]
    if not isinstance(tf, list):
        raise ReviewContractError("sanitization.truncated_fields must be array")
    if len(tf) > 64:
        raise ReviewContractError("sanitization.truncated_fields exceeds 64 entries")
    for i, item in enumerate(tf):
        if not isinstance(item, str):
            raise ReviewContractError(f"sanitization.truncated_fields[{i}] must be string")
        if _byte_len(item) > 256:
            raise ReviewContractError(f"sanitization.truncated_fields[{i}] exceeds 256 bytes")


# ---------------------------------------------------------------------------
# Structural validation: review result
# ---------------------------------------------------------------------------
def validate_review_result(result: dict[str, Any]) -> None:
    """
    Validate review-result structural invariants.
    Raises ReviewContractError on any violation.
    No filesystem access.
    """
    # Top-level required fields
    required = [
        "schema_version",
        "run_id",
        "story_id",
        "review_iteration",
        "repair_iteration",
        "status",
        "status_generated_at",
        "reviewer_id",
        "findings",
        "decision_rationale",
        "recommended_action",
        "sanitization",
    ]
    for field in required:
        if field not in result:
            raise ReviewContractError(f"missing required field: {field}")

    # schema_version
    if result["schema_version"] != "1.0":
        raise ReviewContractError(f"schema_version must be '1.0', got {result['schema_version']}")

    # run_id
    run_id = result["run_id"]
    if not isinstance(run_id, str) or not run_id:
        raise ReviewContractError("run_id must be non-empty string")
    if _byte_len(run_id) > 256:
        raise ReviewContractError("run_id exceeds 256 bytes")

    # story_id
    story_id = result["story_id"]
    if not isinstance(story_id, str) or not story_id:
        raise ReviewContractError("story_id must be non-empty string")
    if _byte_len(story_id) > 128:
        raise ReviewContractError("story_id exceeds 128 bytes")

    # review_iteration
    review_iteration = result["review_iteration"]
    if not isinstance(review_iteration, int) or review_iteration < 1:
        raise ReviewContractError("review_iteration must be integer >= 1")

    # repair_iteration
    repair_iteration = result["repair_iteration"]
    if not isinstance(repair_iteration, int) or repair_iteration < 0:
        raise ReviewContractError("repair_iteration must be integer >= 0")

    # Cross-field: review_iteration == repair_iteration + 1
    if review_iteration != repair_iteration + 1:
        raise ReviewContractError(
            f"review_iteration ({review_iteration}) must equal repair_iteration ({repair_iteration}) + 1"
        )

    # status
    status = result["status"]
    if status not in ("PASS", "FAIL", "ERROR"):
        raise ReviewContractError(f"status must be PASS, FAIL, or ERROR, got {status}")

    # status_generated_at
    status_generated_at = result["status_generated_at"]
    if not isinstance(status_generated_at, str) or not RE_ISO8601_UTC.match(status_generated_at):
        raise ReviewContractError("status_generated_at must be ISO-8601 UTC format")

    # reviewer_id
    reviewer_id = result["reviewer_id"]
    if not isinstance(reviewer_id, str) or not reviewer_id:
        raise ReviewContractError("reviewer_id must be non-empty string")
    if _byte_len(reviewer_id) > 128:
        raise ReviewContractError("reviewer_id exceeds 128 bytes")

    # findings
    findings = result["findings"]
    if not isinstance(findings, list):
        raise ReviewContractError("findings must be array")

    # Validate each finding
    finding_ids = set()
    prev_id = ""
    for i, finding in enumerate(findings):
        _validate_finding(finding, i)

        fid = finding["finding_id"]
        if fid in finding_ids:
            raise ReviewContractError(f"duplicate finding_id: {fid}")
        finding_ids.add(fid)

        # Check lexicographic order
        if fid < prev_id:
            raise ReviewContractError(f"findings not ordered by finding_id: {prev_id} > {fid}")
        prev_id = fid

    # decision_rationale
    dr = result["decision_rationale"]
    if not isinstance(dr, str):
        raise ReviewContractError("decision_rationale must be string")
    if _byte_len(dr) > 2048:
        raise ReviewContractError("decision_rationale exceeds 2048 bytes")

    # recommended_action
    ra = result["recommended_action"]
    if ra not in ("none", "repair", "human_review"):
        raise ReviewContractError(f"recommended_action must be none, repair, or human_review, got {ra}")

    # Cross-field: status + recommended_action + findings
    if status == "PASS":
        if ra != "none":
            raise ReviewContractError("PASS status requires recommended_action == 'none'")
        for finding in findings:
            if finding["severity"] not in ("MINOR", "INFO"):
                raise ReviewContractError(
                    f"PASS status cannot have {finding['severity']} finding: {finding['finding_id']}"
                )

    elif status == "FAIL":
        if ra not in ("repair", "human_review"):
            raise ReviewContractError("FAIL status requires recommended_action == 'repair' or 'human_review'")
        has_blocker_major = any(f["severity"] in ("BLOCKER", "MAJOR") for f in findings)
        if not has_blocker_major:
            raise ReviewContractError("FAIL status requires at least one BLOCKER or MAJOR finding")

    elif status == "ERROR":
        if ra != "human_review":
            raise ReviewContractError("ERROR status requires recommended_action == 'human_review'")

    # sanitization
    _validate_sanitization(result["sanitization"])


def _validate_finding(finding: dict[str, Any], index: int) -> None:
    """Validate a single finding object."""
    if not isinstance(finding, dict):
        raise ReviewContractError(f"findings[{index}] must be object")

    required = ["finding_id", "severity", "category", "summary", "evidence_refs", "recommended_fix"]
    for field in required:
        if field not in finding:
            raise ReviewContractError(f"findings[{index}] missing field: {field}")

    # finding_id
    fid = finding["finding_id"]
    if not isinstance(fid, str) or not fid:
        raise ReviewContractError(f"findings[{index}].finding_id must be non-empty string")
    if _byte_len(fid) > 128:
        raise ReviewContractError(f"findings[{index}].finding_id exceeds 128 bytes")

    # severity
    severity = finding["severity"]
    if severity not in ("BLOCKER", "MAJOR", "MINOR", "INFO"):
        raise ReviewContractError(f"findings[{index}].severity must be BLOCKER, MAJOR, MINOR, or INFO")

    # category
    category = finding["category"]
    if not isinstance(category, str) or not category:
        raise ReviewContractError(f"findings[{index}].category must be non-empty string")
    if _byte_len(category) > 64:
        raise ReviewContractError(f"findings[{index}].category exceeds 64 bytes")

    # summary
    summary = finding["summary"]
    if not isinstance(summary, str) or not summary:
        raise ReviewContractError(f"findings[{index}].summary must be non-empty string")
    if _byte_len(summary) > 1024:
        raise ReviewContractError(f"findings[{index}].summary exceeds 1024 bytes")

    # evidence_refs
    evidence_refs = finding["evidence_refs"]
    if not isinstance(evidence_refs, list):
        raise ReviewContractError(f"findings[{index}].evidence_refs must be array")
    if len(evidence_refs) > 20:
        raise ReviewContractError(f"findings[{index}].evidence_refs exceeds 20 entries")
    for j, ref in enumerate(evidence_refs):
        if not isinstance(ref, str):
            raise ReviewContractError(f"findings[{index}].evidence_refs[{j}] must be string")
        _validate_relative_path(ref, f"findings[{index}].evidence_refs[{j}]")

    # recommended_fix
    rfix = finding["recommended_fix"]
    if not isinstance(rfix, str):
        raise ReviewContractError(f"findings[{index}].recommended_fix must be string")
    if _byte_len(rfix) > 512:
        raise ReviewContractError(f"findings[{index}].recommended_fix exceeds 512 bytes")


# ---------------------------------------------------------------------------
# Referential validation
# ---------------------------------------------------------------------------
def validate_review_request_references(
    request: dict[str, Any],
    repo_root: Path,
    run_dir: Path,
) -> None:
    """
    Validate review-request referential invariants against filesystem.

    repo_root: repository root (manifest_ref.path resolved relative to this)
    run_dir:   current run's artifact directory (failure_context_ref.path resolved relative to this)

    Raises ReviewContractError on any violation.
    """
    # Resolve manifest path
    manifest_rel = request["manifest_ref"]["path"]
    _validate_relative_path(manifest_rel, "manifest_ref.path")
    manifest_path = _safe_resolve(repo_root, manifest_rel)

    # Manifest must exist
    if not manifest_path.exists() or not manifest_path.is_file():
        raise ReviewContractError(f"manifest file does not exist: {manifest_rel}")

    # Manifest SHA-256 must match
    manifest_bytes = manifest_path.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != request["manifest_ref"]["sha256"]:
        raise ReviewContractError(
            f"manifest SHA-256 mismatch: expected {request['manifest_ref']['sha256']}, got {manifest_sha256}"
        )

    # Manifest must be valid JSON
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ReviewContractError(f"manifest is not valid JSON: {e}") from e

    # Manifest schema_version
    if manifest.get("schema_version") != "1.0":
        raise ReviewContractError("manifest schema_version must be '1.0'")

    # story_id match
    if manifest.get("story_id") != request["story_id"]:
        raise ReviewContractError(
            f"story_id mismatch: request has {request['story_id']}, manifest has {manifest.get('story_id')}"
        )

    # manifest_excerpt fields match manifest after sanitization
    excerpt = request["manifest_excerpt"]

    # title (256 bytes max)
    manifest_title = manifest.get("title", "")
    sanitized_title = _sanitize_text(manifest_title, max_bytes=256)
    if excerpt["title"] != sanitized_title:
        raise ReviewContractError("manifest_excerpt.title does not match manifest after sanitization")

    # description (2048 bytes max)
    manifest_desc = manifest.get("description", "")
    sanitized_desc = _sanitize_text(manifest_desc, max_bytes=2048)
    if excerpt["description"] != sanitized_desc:
        raise ReviewContractError("manifest_excerpt.description does not match manifest after sanitization")

    # acceptance_criteria (512 bytes max per item)
    manifest_ac = manifest.get("acceptance_criteria", [])
    sanitized_ac = [_sanitize_text(item, max_bytes=512) for item in manifest_ac]
    if excerpt["acceptance_criteria"] != sanitized_ac:
        raise ReviewContractError("manifest_excerpt.acceptance_criteria does not match manifest after sanitization")

    # repair_guidance (if present in manifest, 256 bytes max per item)
    if "repair_guidance" in manifest:
        manifest_rg = manifest.get("repair_guidance", [])
        sanitized_rg = [_sanitize_text(item, max_bytes=256) for item in manifest_rg]
        if excerpt.get("repair_guidance", []) != sanitized_rg:
            raise ReviewContractError("manifest_excerpt.repair_guidance does not match manifest after sanitization")

    # allowed_paths (no sanitization, direct match)
    manifest_allowed = manifest.get("allowed_paths", [])
    if excerpt["allowed_paths"] != manifest_allowed:
        raise ReviewContractError("manifest_excerpt.allowed_paths does not match manifest")

    # forbidden_paths (no sanitization, direct match)
    manifest_forbidden = manifest.get("forbidden_paths", [])
    if excerpt["forbidden_paths"] != manifest_forbidden:
        raise ReviewContractError("manifest_excerpt.forbidden_paths does not match manifest")

    # Resolve failure-context path
    fc_rel = request["failure_context_ref"]["path"]
    _validate_relative_path(fc_rel, "failure_context_ref.path")
    fc_path = _safe_resolve(run_dir, fc_rel)

    # Failure-context must exist
    if not fc_path.exists() or not fc_path.is_file():
        raise ReviewContractError(f"failure-context file does not exist: {fc_rel}")

    # Failure-context SHA-256 must match
    fc_bytes = fc_path.read_bytes()
    fc_sha256 = hashlib.sha256(fc_bytes).hexdigest()
    if fc_sha256 != request["failure_context_ref"]["sha256"]:
        raise ReviewContractError(
            f"failure-context SHA-256 mismatch: expected {request['failure_context_ref']['sha256']}, got {fc_sha256}"
        )

    # Failure-context must be valid JSON
    try:
        fc = json.loads(fc_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ReviewContractError(f"failure-context is not valid JSON: {e}") from e

    # Failure-context schema_version
    if fc.get("schema_version") != "1.0":
        raise ReviewContractError("failure-context schema_version must be '1.0'")

    # run_id match
    if fc.get("run_id") != request["run_id"]:
        raise ReviewContractError(
            f"run_id mismatch: request has {request['run_id']}, failure-context has {fc.get('run_id')}"
        )

    # story_id match
    if fc.get("story_id") != request["story_id"]:
        raise ReviewContractError(
            f"story_id mismatch: request has {request['story_id']}, failure-context has {fc.get('story_id')}"
        )

    # candidate_identity exact match
    fc_ci = fc.get("candidate_identity")
    if fc_ci != request["candidate_identity"]:
        raise ReviewContractError("candidate_identity does not exactly match failure-context")

    # overall_verification_status must match triggered_by
    # DEC-C6-01: conditional binding
    triggered_by = request["triggered_by"]
    actual_ovs = fc.get("overall_verification_status")
    if triggered_by in ("initial_verify_pass", "post_repair_verify_pass"):
        if actual_ovs != "PASS":
            raise ReviewContractError(
                f"failure-context overall_verification_status must be 'PASS' "
                f"for triggered_by={triggered_by!r}, got {actual_ovs!r}"
            )
    elif triggered_by == "initial_verify_fail":
        if actual_ovs != "FAIL":
            raise ReviewContractError(
                f"failure-context overall_verification_status must be 'FAIL' "
                f"for triggered_by='initial_verify_fail', got {actual_ovs!r}"
            )
    else:
        # Unknown triggered_by should have been caught by structural validator,
        # but fail closed here too.
        raise ReviewContractError(
            f"unexpected triggered_by in referential validation: {triggered_by!r}"
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

    # 3. Binary detection (before control char removal so null bytes are visible)
    if is_binary_content(text):
        return "[REDACTED:binary_content]"

    # 2. Control character removal
    text = sanitize_control_characters(text)

    # 4. Base64 run detection
    text, _ = redact_base64_runs(text)

    # 5. Secret pattern redaction
    text, _ = redact_text(text)

    # 6. URL query stripping
    import re
    url_pattern = re.compile(r"(https?://[^\s?]+)\?[^\s]*")
    text = url_pattern.sub(r"\1", text)

    # 7-8. Byte truncation (if max_bytes specified)
    if max_bytes is not None:
        text_bytes = text.encode("utf-8")
        original_byte_len = len(text_bytes)
        if original_byte_len > max_bytes:
            # Calculate marker size to ensure final output fits within max_bytes
            omitted = original_byte_len - max_bytes
            marker = f"\n... [truncated: {omitted} bytes omitted]"
            marker_bytes = len(marker.encode("utf-8"))
            # Truncate to leave room for the marker
            target_bytes = max_bytes - marker_bytes
            target_bytes = max(target_bytes, 0)
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

    # 3. Binary detection (before control char removal so null bytes are visible)
    if is_binary_content(text):
        redaction_counts.append(1)
        return "[REDACTED:binary_content]"

    # 2. Control character removal
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
        # Calculate marker size to ensure final output fits within max_bytes
        omitted = original_byte_len - max_bytes
        marker = f"\n... [truncated: {omitted} bytes omitted]"
        marker_bytes = len(marker.encode("utf-8"))
        # Truncate to leave room for the marker
        target_bytes = max_bytes - marker_bytes
        target_bytes = max(target_bytes, 0)
        text_bytes = text_bytes[:target_bytes]
        text = text_bytes.decode("utf-8", errors="ignore")
        text += marker
        truncation_fields.append(field_path)

    return text


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
def build_review_request(
    repo_root: Path,
    run_dir: Path,
    manifest_path: Path,
    failure_context_path: Path,
    run_id: str,
    story_id: str,
    review_iteration: int,
    repair_iteration: int,
    triggered_by: str,
    generated_at: str,
    reviewer_id: str,
) -> dict[str, Any]:
    """
    Build review request with both structural and referential validation.

    manifest_path: absolute path to manifest (must be under repo_root)
    failure_context_path: absolute path to failure-context (must be under run_dir)
    generated_at: ISO-8601 timestamp supplied by caller (no internal time call)

    Returns validated review-request dict.
    Raises ReviewContractError on any violation.
    """
    # Validate manifest_path is under repo_root
    manifest_resolved = manifest_path.resolve()
    repo_root_resolved = repo_root.resolve()
    if not str(manifest_resolved).startswith(str(repo_root_resolved)):
        raise ReviewContractError("manifest_path must be under repo_root")

    # Validate failure_context_path is under run_dir
    fc_resolved = failure_context_path.resolve()
    run_dir_resolved = run_dir.resolve()
    if not str(fc_resolved).startswith(str(run_dir_resolved)):
        raise ReviewContractError("failure_context_path must be under run_dir")

    # Load and validate manifest
    if not manifest_path.exists() or not manifest_path.is_file():
        raise ReviewContractError(f"manifest file does not exist: {manifest_path}")

    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise ReviewContractError(f"manifest is not valid JSON: {e}") from e

    if manifest.get("schema_version") != "1.0":
        raise ReviewContractError("manifest schema_version must be '1.0'")

    # Load and validate failure-context
    if not failure_context_path.exists() or not failure_context_path.is_file():
        raise ReviewContractError(f"failure-context file does not exist: {failure_context_path}")

    try:
        fc_bytes = failure_context_path.read_bytes()
        fc = json.loads(fc_bytes.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        raise ReviewContractError(f"failure-context is not valid JSON: {e}") from e

    if fc.get("schema_version") != "1.0":
        raise ReviewContractError("failure-context schema_version must be '1.0'")

    # Compute SHA-256 digests
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    fc_sha256 = hashlib.sha256(fc_bytes).hexdigest()

    # Build relative paths
    manifest_rel = str(manifest_resolved.relative_to(repo_root_resolved))
    fc_rel = str(fc_resolved.relative_to(run_dir_resolved))

    # Sanitize manifest excerpt with metadata tracking
    truncation_fields: list[str] = []
    redaction_counts: list[int] = []

    # title
    manifest_title = manifest.get("title", "")
    sanitized_title = _sanitize_field_with_metadata(
        manifest_title,
        "manifest_excerpt.title",
        256,
        truncation_fields,
        redaction_counts,
    )

    # description
    manifest_desc = manifest.get("description", "")
    sanitized_desc = _sanitize_field_with_metadata(
        manifest_desc,
        "manifest_excerpt.description",
        2048,
        truncation_fields,
        redaction_counts,
    )

    # acceptance_criteria
    manifest_ac = manifest.get("acceptance_criteria", [])
    sanitized_ac = []
    for i, item in enumerate(manifest_ac):
        sanitized_item = _sanitize_field_with_metadata(
            item,
            f"manifest_excerpt.acceptance_criteria[{i}]",
            512,
            truncation_fields,
            redaction_counts,
        )
        sanitized_ac.append(sanitized_item)

    # repair_guidance (optional)
    repair_guidance: list[str] = []
    if "repair_guidance" in manifest:
        manifest_rg = manifest.get("repair_guidance", [])
        for i, item in enumerate(manifest_rg):
            sanitized_item = _sanitize_field_with_metadata(
                item,
                f"manifest_excerpt.repair_guidance[{i}]",
                256,
                truncation_fields,
                redaction_counts,
            )
            repair_guidance.append(sanitized_item)

    # allowed_paths (no sanitization, direct copy)
    allowed_paths = manifest.get("allowed_paths", [])

    # forbidden_paths (no sanitization, direct copy)
    forbidden_paths = manifest.get("forbidden_paths", [])

    # Build candidate_identity from failure-context
    candidate_identity = fc.get("candidate_identity")

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

    # Build the review request
    request: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "story_id": story_id,
        "review_iteration": review_iteration,
        "repair_iteration": repair_iteration,
        "triggered_by": triggered_by,
        "generated_at": generated_at,
        "reviewer_id": reviewer_id,
        "manifest_ref": {
            "path": manifest_rel,
            "schema_version": "1.0",
            "sha256": manifest_sha256,
        },
        "manifest_excerpt": {
            "title": sanitized_title,
            "description": sanitized_desc,
            "acceptance_criteria": sanitized_ac,
            "repair_guidance": repair_guidance,
            "allowed_paths": allowed_paths,
            "forbidden_paths": forbidden_paths,
        },
        "failure_context_ref": {
            "path": fc_rel,
            "schema_version": "1.0",
            "sha256": fc_sha256,
        },
        "candidate_identity": candidate_identity,
        "sanitization": sanitization,
    }

    # Validate output (structural + referential)
    validate_review_request(request)
    validate_review_request_references(request, repo_root, run_dir)

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
    Produce human-readable pretty JSON with exactly one terminal newline.
    indent=2, sort_keys=True, ensure_ascii=False, no trailing whitespace per line.
    """
    text = json.dumps(
        obj,
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines) + "\n"
