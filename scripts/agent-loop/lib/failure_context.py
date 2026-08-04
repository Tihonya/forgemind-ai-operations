"""
WP-AL-1B3: Failure context collector for the agent-loop verification harness.

This module reads verification artifacts produced by verify-story.sh and emits
a structured failure-context.json that downstream agents (reviewer, repair,
reporter) consume.

Schema: .agent-loop/failure-context/SCHEMA.md

Deterministic, stdlib-only, no network/LLM/shell. Writes atomically via
tmp+os.replace. Validates its own output before publish.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Canonical gate IDs (lexicographic order for deterministic output)
# ---------------------------------------------------------------------------
CANONICAL_GATE_IDS = [
    "git_diff_check",
    "json_syntax",
    "lint",
    "scope",
    "secrets",
    "targeted_tests",
    "yaml_syntax",
]


# ---------------------------------------------------------------------------
# Redaction patterns (order matters: apply in sequence)
# ---------------------------------------------------------------------------
REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Stripe keys
    (re.compile(r"sk_(live|test)_[A-Za-z0-9]{20,}"), "[REDACTED:stripe_key]"),
    # GitHub tokens
    (re.compile(r"ghp_[A-Za-z0-9]{36}"), "[REDACTED:github_token]"),
    # AWS access keys
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED:aws_key]"),
    # Bearer tokens
    (re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE), "[REDACTED:bearer_token]"),
    # Basic auth
    (re.compile(r"Basic\s+[A-Za-z0-9+/=]+", re.IGNORECASE), "[REDACTED:basic_auth]"),
    # Password assignments
    (re.compile(r"password\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE), "[REDACTED:password]"),
    # API key assignments
    (re.compile(r"api[_-]?key\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE), "[REDACTED:api_key]"),
    # Secret assignments
    (re.compile(r"secret\s*=\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE), "[REDACTED:secret]"),
    # Private key blocks
    (re.compile(r"-----BEGIN[A-Z\s]*PRIVATE\s+KEY-----[\s\S]*?-----END[A-Z\s]*PRIVATE\s+KEY-----"), "[REDACTED:private_key]"),
    # URL query strings (preserve scheme+host+path, strip query)
    (re.compile(r"(https?://[^\s?]+)\?[^\s]*"), r"\1"),
]


# ---------------------------------------------------------------------------
# Limits (defaults; may be overridden by caller)
# ---------------------------------------------------------------------------
DEFAULT_LIMITS: dict[str, int] = {
    "max_excerpt_lines": 50,
    "max_excerpt_bytes": 4096,
    "max_diagnostics_per_gate": 10,
    "max_total_diagnostics": 50,
    "max_collection_errors": 20,
}


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------
def normalize_utf8(text: str) -> str:
    """Normalize to NFC, replace invalid bytes with U+FFFD."""
    return unicodedata.normalize("NFC", text.encode("utf-8", errors="replace").decode("utf-8"))


def sanitize_control_characters(text: str) -> str:
    """Remove or replace non-printable control characters, preserve \\n\\t\\r."""
    result = []
    for char in text:
        # Preserve allowed whitespace
        if char in ("\n", "\t", "\r"):
            result.append(char)
        # Replace other control characters (C0 and C1 except DEL)
        elif unicodedata.category(char).startswith("C"):
            result.append("")  # U+FFFD replacement
        else:
            result.append(char)
    return "".join(result)


def is_binary_content(text: str, threshold: float = 0.3) -> bool:
    """Detect if content appears to be binary (high ratio of non-printable chars)."""
    if not text:
        return False

    # Strong indicator: null bytes
    if "\x00" in text:
        return True

    sample = text[:1024]  # Check first 1KB
    non_printable = 0
    for char in sample:
        # Count characters outside printable ASCII range (32-126)
        # Exclude common whitespace: \n (10), \r (13), \t (9)
        code = ord(char)
        if code < 32 and code not in (9, 10, 13):
            non_printable += 1
        elif code > 126 and code < 160:
            # C1 control characters and DEL
            non_printable += 1

    return (non_printable / len(sample)) > threshold


def redact_base64_runs(text: str, min_length: int = 100) -> tuple[str, int]:
    """Detect and redact long base64-like strings (alphanumeric + /+=)."""
    # Match runs of base64 characters that are suspiciously long
    pattern = re.compile(f"[A-Za-z0-9+/]{{{min_length},}}" + "={0,2}")

    count = 0
    def replacer(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return "[REDACTED:base64_payload]"

    result = pattern.sub(replacer, text)
    return result, count


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------
def redact_text(text: str) -> tuple[str, int]:
    """Apply redaction patterns and safety sanitization. Returns (sanitized_text, redaction_count)."""
    count = 0

    # Check for binary content first
    if is_binary_content(text):
        return "[REDACTED:binary_content]", 1

    # Remove control characters
    text = sanitize_control_characters(text)

    # Redact base64-like runs
    text, base64_count = redact_base64_runs(text)
    count += base64_count

    # Apply pattern-based redaction
    for pattern, replacement in REDACTION_PATTERNS:
        text, n = pattern.subn(replacement, text)
        count += n
    return text, count


# ---------------------------------------------------------------------------
# Truncation
# ---------------------------------------------------------------------------
def truncate_text(text: str, max_lines: int, max_bytes: int, source_artifact: str) -> dict[str, Any]:
    """Truncate text to line/byte limits. Returns metadata dict."""
    original_bytes = len(text.encode("utf-8"))
    lines = text.split("\n")

    truncated = False
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True

    result = "\n".join(lines)
    result_bytes = result.encode("utf-8")

    if len(result_bytes) > max_bytes:
        result_bytes = result_bytes[:max_bytes]
        result = result_bytes.decode("utf-8", errors="ignore")
        truncated = True

    included_bytes = len(result.encode("utf-8"))

    metadata = {
        "truncated": truncated,
        "original_size_bytes": original_bytes,
        "included_size_bytes": included_bytes,
        "source_artifact": source_artifact,
    }

    if truncated:
        result += f"\n... [truncated: {original_bytes - included_bytes} bytes omitted, source: {source_artifact}]"

    return {"content": result, "metadata": metadata}


# ---------------------------------------------------------------------------
# Safe file reading
# ---------------------------------------------------------------------------
def safe_read_text(path: Path, max_bytes: int = 1_000_000) -> str | None:
    """Read file with size limit. Returns None on error."""
    try:
        if not path.exists() or not path.is_file():
            return None
        size = path.stat().st_size
        if size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return None


def safe_read_json(path: Path) -> dict[str, Any] | None:
    """Read and parse JSON file. Returns None on error."""
    text = safe_read_text(path)
    if text is None:
        return None
    try:
        return json.loads(text)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# XML parsing (pytest JUnit XML)
# ---------------------------------------------------------------------------
def parse_pytest_xml(path: Path) -> dict[str, Any] | None:
    """Parse pytest JUnit XML for structured diagnostics. Returns None on error."""
    import xml.etree.ElementTree as ET

    text = safe_read_text(path)
    if text is None:
        return None

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None

    testcases = []
    for testcase in root.iter("testcase"):
        tc = {
            "classname": testcase.get("classname", ""),
            "name": testcase.get("name", ""),
            "time": testcase.get("time", "0"),
        }
        failure = testcase.find("failure")
        if failure is not None:
            tc["status"] = "failed"
            tc["message"] = failure.get("message", "")
            tc["text"] = failure.text or ""
        error = testcase.find("error")
        if error is not None:
            tc["status"] = "error"
            tc["message"] = error.get("message", "")
            tc["text"] = error.text or ""
        if "status" not in tc:
            tc["status"] = "passed"
        testcases.append(tc)

    return {
        "tests": root.get("tests", "0"),
        "failures": root.get("failures", "0"),
        "errors": root.get("errors", "0"),
        "testcases": testcases,
    }


# ---------------------------------------------------------------------------
# Candidate identity
# ---------------------------------------------------------------------------
def compute_candidate_identity(
    repo_root: Path,
    base_commit: str,
    manifest_path: Path,
) -> dict[str, Any]:
    """
    Compute deterministic candidate identity.

    Returns dict with:
      base_commit: concrete 40-char hex SHA (from manifest)
      candidate_commit: 40-char hex SHA if committed, else null
      candidate_state: "committed" | "working_tree"
      candidate_diff_digest: 64-char hex SHA-256 of normalized diff inventory
    """
    # Validate base_commit is concrete (40-char hex)
    if not re.match(r"^[0-9a-f]{40}$", base_commit):
        raise ValueError(f"base_commit is not a concrete SHA: {base_commit}")

    # Determine candidate state
    # Check if there are uncommitted changes
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    has_changes = bool(proc.stdout.strip())

    if has_changes:
        candidate_commit = None
        candidate_state = "working_tree"
    else:
        # Get HEAD SHA
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError("git rev-parse HEAD failed")
        candidate_commit = proc.stdout.strip()
        if not re.match(r"^[0-9a-f]{40}$", candidate_commit):
            raise ValueError(f"HEAD is not a concrete SHA: {candidate_commit}")
        candidate_state = "committed"

    # Compute candidate_diff_digest
    # Enumerate files changed between base_commit and HEAD (or working tree)
    if candidate_state == "committed":
        target = "HEAD"
    else:
        target = None  # working tree

    if target:
        proc = subprocess.run(
            ["git", "diff", "--name-only", base_commit, target],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    else:
        # For working tree: diff base_commit against working tree
        proc = subprocess.run(
            ["git", "diff", "--name-only", base_commit],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    if proc.returncode != 0:
        raise RuntimeError(f"git diff failed: {proc.stderr}")

    changed_files = sorted(proc.stdout.strip().split("\n")) if proc.stdout.strip() else []

    # Build inventory: (path, size_bytes, sha256_of_content)
    inventory = []
    for rel_path in changed_files:
        full_path = repo_root / rel_path
        if not full_path.exists():
            continue
        try:
            content = full_path.read_bytes()
            size = len(content)
            sha256 = hashlib.sha256(content).hexdigest()
            inventory.append((rel_path, size, sha256))
        except (OSError, PermissionError):
            continue

    # Also include untracked files for working_tree state
    if candidate_state == "working_tree":
        proc = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            untracked = sorted(proc.stdout.strip().split("\n"))
            for rel_path in untracked:
                full_path = repo_root / rel_path
                if not full_path.exists():
                    continue
                try:
                    content = full_path.read_bytes()
                    size = len(content)
                    sha256 = hashlib.sha256(content).hexdigest()
                    inventory.append((rel_path, size, sha256))
                except (OSError, PermissionError):
                    continue

    # Sort by path
    inventory.sort(key=lambda x: x[0])

    # Serialize as newline-delimited lines: path\tsize\tsha256
    serialized = "\n".join(f"{path}\t{size}\t{sha}" for path, size, sha in inventory)

    # Compute SHA-256
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    return {
        "base_commit": base_commit,
        "candidate_commit": candidate_commit,
        "candidate_state": candidate_state,
        "candidate_diff_digest": digest,
    }


# ---------------------------------------------------------------------------
# Diagnostic extraction
# ---------------------------------------------------------------------------
def extract_gate_diagnostics(
    gate_id: str,
    run_dir: Path,
    verify_result: dict[str, Any],
    limits: dict[str, int],
) -> list[dict[str, Any]]:
    """
    Extract structured diagnostics for a single gate.

    Returns list of diagnostic dicts (bounded by limits).
    """
    diagnostics: list[dict[str, Any]] = []
    verify_dir = run_dir / "verify"

    # Gate log file
    log_file = verify_dir / f"{gate_id}.log"
    log_text = safe_read_text(log_file)

    if log_text is None:
        return diagnostics

    # Apply redaction
    sanitized, redaction_count = redact_text(log_text)

    # Truncate
    truncation = truncate_text(
        sanitized,
        max_lines=limits["max_excerpt_lines"],
        max_bytes=limits["max_excerpt_bytes"],
        source_artifact=f"verify/{gate_id}.log",
    )

    # Build diagnostic
    diagnostic = {
        "category": "gate_log",
        "severity": "error",  # Only include diagnostics for failing gates
        "source_artifact": f"verify/{gate_id}.log",
        "content": truncation["content"],
        "redaction_applied": redaction_count > 0,
        "redaction_count": redaction_count,
    }
    diagnostic.update(truncation["metadata"])

    diagnostics.append(diagnostic)

    # Special handling for secrets gate: extract structured findings
    if gate_id == "secrets" and log_text:
        # Look for rule_id, file, line in log
        secrets_pattern = re.compile(
            r"^(?P<file>[^:]+):(?P<line>\d+)\s+rule=(?P<rule>\S+)\s+classification=(?P<class>\S+)",
            re.MULTILINE,
        )
        for match in secrets_pattern.finditer(log_text):
            finding = {
                "category": "secrets_finding",
                "severity": "error",
                "source_artifact": f"verify/{gate_id}.log",
                "content": f"rule={match.group('rule')} file={match.group('file')} line={match.group('line')}",
                "redaction_applied": False,
                "redaction_count": 0,
                "truncated": False,
                "original_size_bytes": 0,
                "included_size_bytes": 0,
            }
            diagnostics.append(finding)
            if len(diagnostics) >= limits["max_diagnostics_per_gate"]:
                break

    # Special handling for targeted_tests: extract pytest failures
    if gate_id == "targeted_tests":
        xml_path = verify_dir / "pytest-report.xml"
        pytest_data = parse_pytest_xml(xml_path)
        if pytest_data:
            for tc in pytest_data["testcases"]:
                if tc["status"] in ("failed", "error"):
                    # Redact test output
                    test_text = tc.get("text", "")
                    sanitized, redaction_count = redact_text(test_text)
                    truncation = truncate_text(
                        sanitized,
                        max_lines=20,  # Smaller limit for test output
                        max_bytes=2048,
                        source_artifact="verify/pytest-report.xml",
                    )
                    diagnostic = {
                        "category": "test_failure",
                        "severity": "error",
                        "source_artifact": "verify/pytest-report.xml",
                        "content": f"{tc['classname']}::{tc['name']}\n{truncation['content']}",
                        "redaction_applied": redaction_count > 0,
                        "redaction_count": redaction_count,
                    }
                    diagnostic.update(truncation["metadata"])
                    diagnostics.append(diagnostic)
                    if len(diagnostics) >= limits["max_diagnostics_per_gate"]:
                        break

    return diagnostics[: limits["max_diagnostics_per_gate"]]


# ---------------------------------------------------------------------------
# Main collector
# ---------------------------------------------------------------------------
def collect_failure_context(
    run_dir: Path,
    repo_root: Path,
    manifest_path: Path,
    output_path: Path,
    limits: dict[str, int] | None = None,
) -> None:
    """
    Collect failure context from run artifacts and write failure-context.json.

    Args:
        run_dir: Path to the run directory (contains verify/, reports/, etc.)
        repo_root: Path to the repository root (where git commands run)
        manifest_path: Path to the story manifest JSON
        output_path: Path where failure-context.json will be written
        limits: Optional limits override (defaults to DEFAULT_LIMITS)

    Raises:
        RuntimeError: On infrastructure failure (caller must handle)
    """
    if limits is None:
        limits = DEFAULT_LIMITS.copy()

    collection_errors = []
    total_redaction_count = 0

    # Load manifest
    manifest = safe_read_json(manifest_path)
    if manifest is None:
        collection_errors.append(
            {
                "artifact_id": str(manifest_path),
                "error_code": "MALFORMED",
                "safe_summary": "manifest is not valid JSON",
            }
        )
        raise RuntimeError("manifest malformed")

    base_commit = manifest.get("base_commit", "")
    story_id = manifest.get("story_id", "unknown")
    project_id = manifest.get("project_id", "forgemind")

    # Load verify-result.json
    verify_result_path = run_dir / "reports" / "verify-result.json"
    verify_result = safe_read_json(verify_result_path)
    if verify_result is None:
        collection_errors.append(
            {
                "artifact_id": "reports/verify-result.json",
                "error_code": "MISSING",
                "safe_summary": "verify-result.json not found",
            }
        )
        raise RuntimeError("verify-result.json missing")

    run_id = verify_result.get("run_id", "unknown")
    overall_status = verify_result.get("overall_status", "UNKNOWN")

    # Compute candidate identity
    try:
        candidate_identity = compute_candidate_identity(
            repo_root=repo_root,
            base_commit=base_commit,
            manifest_path=manifest_path,
        )
    except (RuntimeError, ValueError) as e:
        collection_errors.append(
            {
                "artifact_id": "candidate_identity",
                "error_code": "COMPUTE_ERROR",
                "safe_summary": f"failed to compute candidate identity: {type(e).__name__}",
            }
        )
        candidate_identity = {
            "base_commit": base_commit,
            "candidate_commit": None,
            "candidate_state": "working_tree",
            "candidate_diff_digest": "0" * 64,
        }

    # Build gate verdicts
    gate_verdicts: dict[str, dict[str, Any]] = {}
    failing_gate_ids: list[str] = []

    gates = verify_result.get("gates", [])
    for gate in gates:
        gate_id = gate.get("name", "")
        gate_status = gate.get("status", "UNKNOWN")
        gate_details = gate.get("details", "")

        # Sanitize summary
        sanitized_summary, summary_redactions = redact_text(gate_details)
        total_redaction_count += summary_redactions

        # Build source_artifacts list
        source_artifacts: list[str] = []
        log_file = run_dir / "verify" / f"{gate_id}.log"
        if log_file.exists():
            source_artifacts.append(f"verify/{gate_id}.log")

        # Extract diagnostics only for failing/error gates
        diagnostics: list[dict[str, Any]] = []
        if gate_status in ("FAIL", "ERROR"):
            diagnostics = extract_gate_diagnostics(gate_id, run_dir, verify_result, limits)
            for d in diagnostics:
                total_redaction_count += d.get("redaction_count", 0)

        # Build verdict
        verdict = {
            "status": gate_status,
            "summary": sanitized_summary[:200],  # Bound summary
            "source_artifacts": source_artifacts,
            "diagnostics": diagnostics,
        }

        gate_verdicts[gate_id] = verdict

        if gate_status == "FAIL":
            failing_gate_ids.append(gate_id)

    # Sort failing_gate_ids lexicographically
    failing_gate_ids.sort()

    # Build artifact_refs
    artifact_refs: dict[str, Any] = {
        "verify_result": "reports/verify-result.json",
        "gate_logs": [],
    }
    verify_dir = run_dir / "verify"
    if verify_dir.exists():
        for log_file in sorted(verify_dir.glob("*.log")):
            artifact_refs["gate_logs"].append(f"verify/{log_file.name}")

    # Build repair_guidance (pass-through from manifest)
    repair_guidance = manifest.get("repair_guidance", [])

    # Determine collection_status
    if collection_errors:
        collection_status = "partial"
    else:
        collection_status = "complete"

    # Build final output
    generated_at = datetime.now(timezone.utc).isoformat()

    output = {
        "schema_version": "1.0",
        "project_id": project_id,
        "run_id": run_id,
        "story_id": story_id,
        "generated_at": generated_at,
        "candidate_identity": candidate_identity,
        "collection_status": collection_status,
        "collection_errors": collection_errors[: limits["max_collection_errors"]],
        "overall_verification_status": overall_status,
        "gate_verdicts": gate_verdicts,
        "failing_gate_ids": failing_gate_ids,
        "repair_guidance": repair_guidance,
        "artifact_refs": artifact_refs,
        "limits": limits,
        "redaction_applied": total_redaction_count > 0,
        "redaction_count": total_redaction_count,
    }

    # Validate output
    validate_output(output)

    # Write atomically
    atomic_json_write(output_path, output)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_output(data: dict[str, Any]) -> None:
    """
    Validate failure-context output against schema requirements.

    Raises ValueError on validation failure.
    """
    required_fields = [
        "schema_version",
        "run_id",
        "story_id",
        "generated_at",
        "candidate_identity",
        "collection_status",
        "collection_errors",
        "overall_verification_status",
        "gate_verdicts",
        "failing_gate_ids",
        "repair_guidance",
        "artifact_refs",
        "limits",
        "redaction_applied",
        "redaction_count",
    ]

    for field in required_fields:
        if field not in data:
            raise ValueError(f"missing required field: {field}")

    # Validate candidate_identity
    ci = data["candidate_identity"]
    for field in ["base_commit", "candidate_commit", "candidate_state", "candidate_diff_digest"]:
        if field not in ci:
            raise ValueError(f"candidate_identity missing field: {field}")

    if not re.match(r"^[0-9a-f]{40}$", ci["base_commit"]):
        raise ValueError(f"base_commit is not a concrete SHA: {ci['base_commit']}")

    if ci["candidate_state"] not in ("committed", "working_tree"):
        raise ValueError(f"invalid candidate_state: {ci['candidate_state']}")

    if ci["candidate_state"] == "committed" and ci["candidate_commit"] is None:
        raise ValueError("candidate_state is 'committed' but candidate_commit is null")

    if ci["candidate_state"] == "working_tree" and ci["candidate_commit"] is not None:
        raise ValueError("candidate_state is 'working_tree' but candidate_commit is not null")

    if not re.match(r"^[0-9a-f]{64}$", ci["candidate_diff_digest"]):
        raise ValueError(f"candidate_diff_digest is not a valid SHA-256: {ci['candidate_diff_digest']}")

    # Validate collection_status
    if data["collection_status"] not in ("complete", "partial", "failed"):
        raise ValueError(f"invalid collection_status: {data['collection_status']}")

    # Validate overall_verification_status
    if data["overall_verification_status"] not in ("PASS", "FAIL", "ERROR", "SKIP"):
        raise ValueError(f"invalid overall_verification_status: {data['overall_verification_status']}")

    # Validate gate_verdicts
    for gate_id, verdict in data["gate_verdicts"].items():
        for field in ["status", "summary", "source_artifacts", "diagnostics"]:
            if field not in verdict:
                raise ValueError(f"gate_verdicts[{gate_id}] missing field: {field}")
        if verdict["status"] not in ("PASS", "FAIL", "SKIP", "ERROR", "DISABLED"):
            raise ValueError(f"gate_verdicts[{gate_id}] invalid status: {verdict['status']}")


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------
def atomic_json_write(path: Path, data: dict[str, Any]) -> None:
    """Write JSON data atomically via tmp+os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        suffix=".tmp",
        prefix=path.name + ".",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Collect failure context from verification artifacts")
    parser.add_argument("command", choices=["collect"], help="Command to execute")
    parser.add_argument("--run-dir", required=True, help="Path to run directory")
    parser.add_argument("--repo-root", required=True, help="Path to repository root")
    parser.add_argument("--manifest", required=True, help="Path to story manifest")
    parser.add_argument("--output", required=True, help="Path to output file")

    args = parser.parse_args()

    if args.command == "collect":
        try:
            collect_failure_context(
                run_dir=Path(args.run_dir),
                repo_root=Path(args.repo_root),
                manifest_path=Path(args.manifest),
                output_path=Path(args.output),
            )
            print(f"failure-context.json written: {args.output}")
            sys.exit(0)
        except (RuntimeError, ValueError, OSError) as e:
            print(f"COLLECTION_FAILED: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
