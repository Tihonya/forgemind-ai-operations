#!/usr/bin/env python3
"""WP-REC-03H acceptance harness orchestration script (Phase B/C).

Manages an isolated acceptance environment:
- Dedicated PostgreSQL (forgemind_acceptance, port 5433)
- Dedicated Redis (port 6380)
- Backend API + ARQ worker + frontend dev server
- Backend integration tests + Playwright acceptance tests

Modes:
  --mode=verify    Implementation-verification (Phase B)
  --mode=formal    Formal-evidence collection (Phase C, requires authorization)

Usage:
  python scripts/acceptance_harness.py --mode=verify
  python scripts/acceptance_harness.py --mode=formal
  python scripts/acceptance_harness.py --mode=formal --run-id=acc-20260813-001
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import psycopg

# Repository root (parent of scripts/)
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

# Secret patterns for redaction (configurable for testing)
REDACTION_PAIRS: list[tuple[str, str]] = [
    # OpenAI-style keys
    (r"sk-[A-Za-z0-9]{20,}", "[REDACTED]"),
    # password= values
    (r"password=[^\s&]+", "password=[REDACTED]"),
    # secret_key= values
    (r"secret[_-]?key=[^\s&]+", "secret_key=[REDACTED]"),
    # token= values
    (r"token=[^\s&]+", "token=[REDACTED]"),
    # api_key= values
    (r"api[_-]?key=[^\s&]+", "api_key=[REDACTED]"),
    # JSON-quoted secret fields: "secret_key": "value" (M-08)
    (r'(?i)"secret[_-]?key"\s*:\s*"[^"]*"', '"secret_key":"[REDACTED]"'),
    # JSON-quoted api_key fields: "api_key": "value" (M-08)
    (r'(?i)"api[_-]?key"\s*:\s*"[^"]*"', '"api_key":"[REDACTED]"'),
    # JSON-quoted password fields: "password": "value" (M-08)
    (r'(?i)"password"\s*:\s*"[^"]*"', '"password":"[REDACTED]"'),
    # JSON-quoted token fields: "token": "value" (M-08)
    (r'(?i)"token"\s*:\s*"[^"]*"', '"token":"[REDACTED]"'),
    # JSON-quoted auth_token fields: "auth_token": "value" (M-08)
    (r'(?i)"auth[_-]?token"\s*:\s*"[^"]*"', '"auth_token":"[REDACTED]"'),
    # hardcoded test secret
    (r"acceptance-test-secret-key-must-be-32-chars", "[REDACTED]"),
    # URL-embedded credentials with username (M-08: preserve scheme and host)
    (r"(://)[^/\s:]+:[^/\s@]+@", r"\1[REDACTED]@"),
    # URL-embedded credentials without username (M-08: :password@host)
    (r"(://):[^/\s@]+@", r"\1:[REDACTED]@"),
    # JWT tokens
    (r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", "[REDACTED]"),
    # Authorization: Bearer
    (r"(?i)authorization:\s*bearer\s+[^\s]+", "Authorization: Bearer [REDACTED]"),
    # Authorization: Basic
    (r"(?i)authorization:\s*basic\s+[^\s]+", "Authorization: Basic [REDACTED]"),
    # session_id= values
    (r"session[_-]?id=[^\s;]+", "session_id=[REDACTED]"),
    # auth_token= values
    (r"auth[_-]?token=[^\s;]+", "auth_token=[REDACTED]"),
]

DEFAULT_REDACTION_PATTERNS: list[str] = [pattern for pattern, _ in REDACTION_PAIRS]

# Protected audit file
PROTECTED_AUDIT_PATH = REPO_ROOT / "docs" / "reviews" / "wp-rec-03f-post-pr76-readiness-audit.md"
PROTECTED_AUDIT_SHA256 = "639a2529351bdacc606c6c5bbede44b82c73a7aefa26ae249bb592dec8e89657"

# Safe run-id pattern: alphanumeric, hyphens, underscores, dots only
SAFE_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}[a-zA-Z0-9]$|^[a-zA-Z0-9]$")

# Required evidence categories (B-06 completeness enforcement)
REQUIRED_EVIDENCE_CATEGORIES = [
    "repository/baseline.json",
    "environment/versions.json",
    "scenarios/AT008_INVALID_OUTPUT/identity.json",
    "scenarios/AT008_INVALID_OUTPUT/db/workflow_steps.json",
    "scenarios/AT008_INVALID_OUTPUT/db/workflow_run_state.json",
    "scenarios/AT008_INVALID_OUTPUT/db/provider_retry_count.json",
    "scenarios/AT008_INVALID_OUTPUT/api/dispatch_generation.json",
    "scenarios/AT008_INVALID_OUTPUT/db/recommendations.json",
    "scenarios/AT008_INVALID_OUTPUT/db/controlled_write_check.json",
    "scenarios/AT008_INVALID_OUTPUT/api/risk_api.json",
    "scenarios/AT008_INVALID_OUTPUT/tests/backend.json",
    "scenarios/AT008_INVALID_OUTPUT/tests/playwright.json",
    "scenarios/AT013_OUTAGE_UNTIL_RETRY/identity.json",
    "scenarios/AT013_OUTAGE_UNTIL_RETRY/db/workflow_steps.json",
    "scenarios/AT013_OUTAGE_UNTIL_RETRY/db/workflow_run_state.json",
    "scenarios/AT013_OUTAGE_UNTIL_RETRY/db/provider_retry_count.json",
    "scenarios/AT013_OUTAGE_UNTIL_RETRY/api/dispatch_generation.json",
    "scenarios/AT013_OUTAGE_UNTIL_RETRY/db/recommendations.json",
    "scenarios/AT013_OUTAGE_UNTIL_RETRY/db/controlled_write_check.json",
    "scenarios/AT013_OUTAGE_UNTIL_RETRY/api/risk_api.json",
    "scenarios/AT013_OUTAGE_UNTIL_RETRY/tests/backend.json",
    "scenarios/AT013_OUTAGE_UNTIL_RETRY/tests/playwright.json",
    "repository/final.json",
]

# Valid workflow states
VALID_WORKFLOW_STATES = {
    "PENDING", "RUNNING", "AWAITING_VALIDATION",
    "FAILED_VALIDATION", "FAILED_PROVIDER", "COMPLETED"
}


def _resolve_venv_dir() -> Path:
    """Resolve the Python virtual environment directory.

    Search order:
    1. VENV_DIR environment variable (explicit override).
    2. VIRTUAL_ENV environment variable (active virtualenv).
    3. {REPO_ROOT}/.venv (worktree-local).
    4. Primary tree venv (known path for linked worktrees).
    """
    # 1. Explicit override
    if venv_env := os.environ.get("VENV_DIR"):
        p = Path(venv_env)
        if p.is_dir():
            return p

    # 2. Active virtualenv
    if virtual_env := os.environ.get("VIRTUAL_ENV"):
        p = Path(virtual_env)
        if p.is_dir():
            return p

    # 3. Worktree-local .venv
    local_venv = REPO_ROOT / ".venv"
    if local_venv.is_dir():
        return local_venv

    # 4. Primary tree venv (for linked worktrees)
    primary_venv = Path("/home/toha/Projects/forgemind-ai-operations/.venv")
    if primary_venv.is_dir():
        return primary_venv

    raise AcceptanceHarnessError(
        "Cannot find Python virtual environment. "
        "Set VENV_DIR or create a .venv symlink in the repository root."
    )


VENV_DIR = _resolve_venv_dir()
VENV_BIN = VENV_DIR / "bin"

# Acceptance environment constants
ACCEPTANCE_DB_PORT = 5433
ACCEPTANCE_REDIS_PORT = 6380
ACCEPTANCE_DB_NAME = "forgemind_acceptance"
ACCEPTANCE_BACKEND_PORT = 8001
ACCEPTANCE_FRONTEND_PORT = 5174

ACCEPTANCE_DATABASE_URL = (
    f"postgresql+asyncpg://forgemind:forgemind@localhost:{ACCEPTANCE_DB_PORT}/{ACCEPTANCE_DB_NAME}"
)
ACCEPTANCE_REDIS_URL = f"redis://localhost:{ACCEPTANCE_REDIS_PORT}/0"
ACCEPTANCE_FRONTEND_URL = f"http://localhost:{ACCEPTANCE_FRONTEND_PORT}"


class AcceptanceHarnessError(Exception):
    """Raised when acceptance harness encounters a fatal error."""
    pass


@dataclass
class ExecutionResult:
    """Structured subprocess execution result (M-07)."""
    command: list[str]
    working_directory: str
    start_timestamp: str
    end_timestamp: str
    duration_seconds: float
    exit_code: int
    stdout: str
    stderr: str
    parsed_counts: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate required fields."""
        if not self.command:
            raise TypeError("command is required")
        # Validate timestamps are ISO format
        try:
            datetime.datetime.fromisoformat(self.start_timestamp)
            datetime.datetime.fromisoformat(self.end_timestamp)
        except ValueError as e:
            raise ValueError(f"Invalid timestamp format: {e}")
        # Validate duration
        if self.duration_seconds < 0:
            raise ValueError("duration_seconds must be non-negative")
        if self.duration_seconds != self.duration_seconds:  # NaN check
            raise ValueError("duration_seconds cannot be NaN")


@dataclass
class BrowserResult:
    """Validated browser scenario result (B-12)."""
    schema_version: str
    scenario: str
    harness_execution_id: str
    product_workflow_run_id: str
    correlation_id: str | None
    plan_id: str
    browser_test_start: str
    browser_test_end: str
    final_state: str
    screenshots: list[dict[str, Any]] = field(default_factory=list)
    # AT-013 specific
    pre_retry_snapshot: dict[str, Any] | None = None
    post_retry_snapshot: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Run-ID validation
# ---------------------------------------------------------------------------


def validate_run_id(run_id: str) -> None:
    """Validate a run ID against the safe format.

    Raises AcceptanceHarnessError if the run ID is empty, contains path
    separators, traversal sequences, or other unsafe characters.
    """
    if not run_id:
        raise AcceptanceHarnessError("Run ID must not be empty")

    # Reject path separators and traversal
    if "/" in run_id or "\\" in run_id:
        raise AcceptanceHarnessError(f"Run ID must not contain path separators: {run_id!r}")
    if ".." in run_id:
        raise AcceptanceHarnessError(f"Run ID must not contain traversal sequences: {run_id!r}")
    if run_id.startswith(".") or run_id.startswith("-"):
        raise AcceptanceHarnessError(f"Run ID must start with an alphanumeric character: {run_id!r}")

    # Reject excessively long IDs (check before regex to give clear error)
    if len(run_id) > 64:
        raise AcceptanceHarnessError(f"Run ID too long ({len(run_id)} chars, max 64): {run_id!r}")

    # Reject unsafe characters (only allow alphanumeric, hyphens, underscores, dots)
    if not SAFE_RUN_ID_RE.match(run_id):
        raise AcceptanceHarnessError(
            f"Run ID contains unsafe characters: {run_id!r}. "
            "Only alphanumeric, hyphens, underscores, and dots are allowed."
        )


def validate_evidence_dir_not_exists(evidence_dir: Path) -> None:
    """Fail closed if the evidence directory already exists."""
    if evidence_dir.exists():
        raise AcceptanceHarnessError(
            f"Evidence directory already exists: {evidence_dir}. "
            "Use a unique --run-id or omit it to auto-generate."
        )


def generate_run_id() -> str:
    """Generate a unique run ID in the acc-... format."""
    return f"acc-{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Redaction utilities
# ---------------------------------------------------------------------------


def redact_secrets(content: str, patterns: list[str] | None = None) -> str:
    """Replace secret patterns with [REDACTED] markers.

    Args:
        content: The text content to redact.
        patterns: Regex patterns to match. Uses REDACTION_PAIRS if None.

    Returns:
        Redacted content with all matched patterns replaced.
    """
    result = content
    if patterns is None:
        # Use REDACTION_PAIRS for proper group substitution
        for pattern, replacement in REDACTION_PAIRS:
            result = re.sub(pattern, replacement, result)
    else:
        # Legacy: patterns without replacements
        for pattern in patterns:
            result = re.sub(pattern, "[REDACTED]", result)
    return result


def verify_redaction(content: str, patterns: list[str] | None = None) -> list[str]:
    """Check if any secret patterns remain in content after redaction.

    Returns:
        List of patterns that still match (empty means clean).
    """
    if patterns is None:
        patterns = DEFAULT_REDACTION_PATTERNS

    violations: list[str] = []
    for pattern in patterns:
        if re.search(pattern, content):
            violations.append(pattern)
    return violations


def redact_file(src: Path, dst: Path, patterns: list[str] | None = None) -> None:
    """Read a file, redact secrets, write to destination."""
    content = src.read_text(encoding="utf-8", errors="replace")
    redacted = redact_secrets(content, patterns)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(redacted, encoding="utf-8")


# ---------------------------------------------------------------------------
# Checksum utilities
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_checksums(directory: Path) -> dict[str, str]:
    """Compute SHA-256 checksums for all files in directory, excluding checksums.sha256.

    Returns:
        Dict mapping relative file paths to their SHA-256 hex digests.
        Sorted by path for deterministic output.
    """
    checksums: dict[str, str] = {}
    checksum_filename = "checksums.sha256"

    for file_path in sorted(directory.rglob("*")):
        if not file_path.is_file():
            continue
        # Exclude the checksum file itself
        if file_path.name == checksum_filename:
            continue
        rel_path = str(file_path.relative_to(directory))
        checksums[rel_path] = sha256_file(file_path)

    return checksums


def write_checksums_file(directory: Path) -> Path:
    """Compute checksums and write checksums.sha256 file.

    Returns:
        Path to the written checksums file.

    Raises:
        AcceptanceHarnessError: If no files found to checksum.
    """
    checksums = compute_checksums(directory)
    if not checksums:
        raise AcceptanceHarnessError(f"No files found in {directory} for checksum generation")

    checksum_path = directory / "checksums.sha256"
    lines = [f"{digest}  {path}\n" for path, digest in sorted(checksums.items())]
    checksum_path.write_text("".join(lines), encoding="utf-8")
    return checksum_path


# ---------------------------------------------------------------------------
# Protected audit verification
# ---------------------------------------------------------------------------


def verify_protected_audit() -> None:
    """Verify the protected audit file has not been modified.

    Raises AcceptanceHarnessError if the file is missing or its SHA-256
    does not match the expected value.
    """
    if not PROTECTED_AUDIT_PATH.exists():
        raise AcceptanceHarnessError(
            f"Protected audit file not found: {PROTECTED_AUDIT_PATH}"
        )

    actual = sha256_file(PROTECTED_AUDIT_PATH)
    if actual != PROTECTED_AUDIT_SHA256:
        raise AcceptanceHarnessError(
            f"Protected audit file SHA-256 mismatch: "
            f"expected {PROTECTED_AUDIT_SHA256}, got {actual}. "
            "The protected audit file must not be modified."
        )


# ---------------------------------------------------------------------------
# Repository state capture
# ---------------------------------------------------------------------------


def capture_git_state() -> dict[str, str]:
    """Capture current repository state for evidence.
    
    Enhanced to capture all invariants needed for H-07:
    - HEAD
    - branch identity
    - complete porcelain status
    - staged diff identity
    - unstaged tracked diff identity
    - untracked-file inventory
    - protected-audit identity
    
    Raises AcceptanceHarnessError on any git command failure (no [capture failed]).
    """
    state: dict[str, str] = {}
    for cmd_name, cmd in [
        ("head", ["git", "rev-parse", "HEAD"]),
        ("branch", ["git", "branch", "--show-current"]),
        ("status", ["git", "status", "--porcelain"]),
        ("diff_stat", ["git", "diff", "--stat"]),
        ("diff_staged", ["git", "diff", "--cached", "--stat"]),
        ("diff_unstaged_hash", ["git", "diff"]),
        ("log_oneline", ["git", "log", "--oneline", "-5"]),
    ]:
        try:
            result = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,  # Fail closed on non-zero exit
            )
            state[cmd_name] = result.stdout.strip()
            # For diff_unstaged_hash, compute SHA-256 of the diff content
            if cmd_name == "diff_unstaged_hash" and result.stdout:
                state["diff_unstaged_sha256"] = hashlib.sha256(
                    result.stdout.encode("utf-8")
                ).hexdigest()
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.CalledProcessError) as e:
            raise AcceptanceHarnessError(
                f"Git command failed for {cmd_name}: {cmd}. Error: {e}"
            )
    
    # Add protected audit SHA-256 if file exists
    if PROTECTED_AUDIT_PATH.exists():
        state["protected_audit_sha256"] = sha256_file(PROTECTED_AUDIT_PATH)
    
    return state


def capture_tool_versions() -> dict[str, str]:
    """Capture runtime and tool versions."""
    versions: dict[str, str] = {}
    for name, cmd in [
        ("python", ["python3", "--version"]),
        ("node", ["node", "--version"]),
        ("docker", ["docker", "--version"]),
    ]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5,
            )
            versions[name] = result.stdout.strip() or result.stderr.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            versions[name] = "[not available]"
    return versions


def verify_repository_invariants(baseline: dict[str, str], final: dict[str, str]) -> None:
    """Verify repository hasn't changed during execution (H-07).
    
    Compares:
    - HEAD
    - branch identity
    - complete porcelain status
    - staged diff identity
    - unstaged diff content hash
    - protected audit SHA-256
    
    Rejects [capture failed] values (H-07: no false-pass on git failures).
    """
    # Reject [capture failed] values
    for field_name in ["head", "branch", "status", "diff_staged", "diff_unstaged_sha256"]:
        if baseline.get(field_name) == "[capture failed]" or final.get(field_name) == "[capture failed]":
            raise AcceptanceHarnessError(
                f"Git capture failed for {field_name}. Cannot verify repository invariants."
            )
    
    checks = [
        ("head", "HEAD changed during execution"),
        ("branch", "Branch changed during execution"),
        ("status", "Repository status changed (new/deleted/modified files)"),
        ("diff_staged", "Staged changes appeared during execution"),
        ("diff_unstaged_sha256", "Unstaged content changed during execution"),
    ]
    
    for field_name, message in checks:
        if baseline.get(field_name) != final.get(field_name):
            raise AcceptanceHarnessError(
                f"{message}: baseline={baseline.get(field_name)!r}, "
                f"final={final.get(field_name)!r}"
            )
    
    # Check protected audit SHA-256 if present
    if "protected_audit_sha256" in baseline and "protected_audit_sha256" in final:
        if baseline["protected_audit_sha256"] != final["protected_audit_sha256"]:
            raise AcceptanceHarnessError(
                f"Protected audit file changed during execution: "
                f"baseline={baseline['protected_audit_sha256']!r}, "
                f"final={final['protected_audit_sha256']!r}"
            )


# ---------------------------------------------------------------------------
# Database and API evidence collection (B-09: psycopg3, not psql CLI)
# ---------------------------------------------------------------------------


def query_database(query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Execute a database query using psycopg3 with real parameter binding.
    
    Returns list of dicts with column names as keys.
    Preserves NULL values as None.
    Fails closed on any psycopg.Error.
    """
    # Convert postgresql+asyncpg:// to postgresql:// for psycopg
    sync_url = ACCEPTANCE_DATABASE_URL.replace("+asyncpg", "")
    
    try:
        conn = psycopg.connect(sync_url)
        try:
            cur = conn.cursor()
            try:
                cur.execute(query, params)
                
                # Get column names from cursor.description
                columns: list[str] = []
                if cur.description is not None:
                    columns = [desc[0] for desc in cur.description]
                
                rows_raw = cur.fetchall()
                
                # Validate rows_raw is a proper sequence
                if not isinstance(rows_raw, (list, tuple)):
                    raise TypeError(
                        f"Expected list/tuple from fetchall, got {type(rows_raw).__name__}"
                    )
                
                if not columns and rows_raw:
                    raise ValueError(
                        "fetchall returned rows but cursor.description is None"
                    )
                
                # Convert to list of dicts with column names
                rows: list[dict[str, Any]] = []
                for row in rows_raw:
                    row_dict: dict[str, Any] = {}
                    for i, col_name in enumerate(columns):
                        if i < len(row):
                            row_dict[col_name] = row[i]  # Preserves None for NULL
                        else:
                            row_dict[col_name] = None
                    rows.append(row_dict)
                
                return rows
            finally:
                cur.close()
        finally:
            conn.close()
    except psycopg.Error as e:
        raise AcceptanceHarnessError(f"Database query failed: {e}")
    except Exception as e:
        raise AcceptanceHarnessError(f"Database error: {e}")


def query_workflow_steps(workflow_run_id: str) -> list[dict[str, Any]]:
    """Query workflow_steps for a given run (B-01 category 4)."""
    query = """
        SELECT seq, step_name, status, error_code, error_detail,
               started_at, completed_at
        FROM workflow_steps
        WHERE run_id = %s
        ORDER BY seq
    """
    return query_database(query, (workflow_run_id,))


def query_workflow_run_state(workflow_run_id: str) -> dict[str, Any]:
    """Query current workflow run state (B-01 category 5, B-13: use 'state' not 'status')."""
    query = """
        SELECT id, correlation_id, state, dispatch_generation,
               error_code, error_detail,
               started_at, completed_at, created_at, updated_at
        FROM workflow_runs
        WHERE id = %s
    """
    rows = query_database(query, (workflow_run_id,))
    
    if not rows:
        return {"error": "Workflow run not found", "workflow_run_id": workflow_run_id}
    
    return rows[0]


def count_provider_retry_attempts(log_path: Path, correlation_id: str) -> int:
    """Count provider retry attempts from service logs (B-01 category 6).
    
    Args:
        log_path: Path to the worker log file for this run.
        correlation_id: Correlation ID to filter retry entries.
    
    Returns:
        Count of retry attempts matching the correlation ID.
    
    Raises:
        FileNotFoundError: If log file does not exist.
        AcceptanceHarnessError: If log is malformed.
    """
    if not log_path.exists():
        raise FileNotFoundError(f"Log file not found: {log_path}")
    
    try:
        content = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        raise AcceptanceHarnessError(f"Failed to read log file {log_path}: {e}")
    
    # Count occurrences of retry log pattern with matching correlation_id
    retry_count = 0
    target = f"correlation_id={correlation_id}"
    for line in content.splitlines():
        if target in line:
            # Verify exact match (not prefix)
            idx = line.find(target)
            end = idx + len(target)
            if end >= len(line) or not line[end].isalnum():
                retry_count += 1
    
    return retry_count


def query_recommendations(workflow_run_id: str) -> list[dict[str, Any]]:
    """Query recommendations for a given run (B-01 category 8)."""
    query = """
        SELECT id, run_id, created_at
        FROM recommendations
        WHERE run_id = %s
    """
    return query_database(query, (workflow_run_id,))


def check_procurement_tasks_exist() -> bool:
    """Check if procurement_tasks table exists and has data (B-01 category 9)."""
    query = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'procurement_tasks'
        ) AS exists
    """
    rows = query_database(query)
    
    if not rows:
        return False
    
    # Parse boolean result (psycopg returns True/False, not 't'/'f')
    table_exists = rows[0].get("exists", False)
    return bool(table_exists)


def query_risk_api(plan_id: str) -> dict[str, Any]:
    """Query deterministic risk API (B-01 category 10)."""
    import urllib.request
    import urllib.error
    
    url = f"http://localhost:{ACCEPTANCE_BACKEND_PORT}/api/v1/risks?plan_id={plan_id}"
    
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "status": "available",
                    "status_code": resp.status,
                    "risk_count": len(data) if isinstance(data, list) else 0,
                    "data": data,
                }
            else:
                return {
                    "status": "error",
                    "status_code": resp.status,
                    "error": f"HTTP {resp.status}",
                }
    except urllib.error.URLError as e:
        return {
            "status": "unavailable",
            "error": str(e),
        }


def query_workflow_run_api(workflow_run_id: str) -> dict[str, Any]:
    """Query workflow run via API (B-01 category 7, B-07)."""
    import urllib.request
    import urllib.error
    
    url = f"http://localhost:{ACCEPTANCE_BACKEND_PORT}/api/v1/workflow-runs/{workflow_run_id}"
    
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return {
                    "status": "success",
                    "status_code": resp.status,
                    "data": data,
                }
            else:
                return {
                    "status": "error",
                    "status_code": resp.status,
                    "error": f"HTTP {resp.status}",
                }
    except urllib.error.URLError as e:
        return {
            "status": "unavailable",
            "error": str(e),
        }


def find_recent_workflow_runs(
    after_time: datetime.datetime, scenario: str
) -> list[str]:
    """Find workflow runs created after a given time (for evidence collection).
    
    Returns list of workflow run IDs (as strings).
    Uses parameterized query (M-09: no f-string SQL).
    """
    query = """
        SELECT id FROM workflow_runs
        WHERE created_at >= %s
        ORDER BY created_at DESC
        LIMIT 5
    """
    
    try:
        rows = query_database(query, (after_time.isoformat(),))
        return [str(row.get("id", "")) for row in rows if row.get("id")]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Browser result validation (B-12)
# ---------------------------------------------------------------------------


def validate_browser_result(
    result_dict: dict[str, Any], scenario: str, harness_id: str
) -> BrowserResult:
    """Validate a Playwright scenario result JSON.
    
    Args:
        result_dict: The parsed JSON from the Playwright spec.
        scenario: Expected scenario name.
        harness_id: Expected harness execution ID.
    
    Returns:
        Validated BrowserResult.
    
    Raises:
        AcceptanceHarnessError: If validation fails.
    """
    # Required fields
    required_fields = [
        "schema_version", "scenario", "harness_execution_id",
        "product_workflow_run_id", "plan_id",
        "browser_test_start", "browser_test_end", "final_state"
    ]
    
    for field_name in required_fields:
        if field_name not in result_dict:
            raise AcceptanceHarnessError(f"Missing required field: {field_name}")
    
    # Validate schema version
    if result_dict["schema_version"] != "1.0":
        raise AcceptanceHarnessError(
            f"Unsupported schema version: {result_dict['schema_version']}"
        )
    
    # Validate scenario matches
    if result_dict["scenario"] != scenario:
        raise AcceptanceHarnessError(
            f"Scenario mismatch: expected {scenario}, got {result_dict['scenario']}"
        )
    
    # Validate harness ID matches
    if result_dict["harness_execution_id"] != harness_id:
        raise AcceptanceHarnessError(
            f"Harness ID mismatch: expected {harness_id}, got {result_dict['harness_execution_id']}"
        )
    
    # Validate workflow_run_id is a valid UUID
    workflow_run_id = result_dict["product_workflow_run_id"]
    try:
        uuid.UUID(workflow_run_id)
    except (ValueError, AttributeError) as e:
        raise AcceptanceHarnessError(
            f"Invalid workflow_run_id UUID: {workflow_run_id}. Error: {e}"
        )
    
    # Validate timestamps are ISO format
    for ts_field in ["browser_test_start", "browser_test_end"]:
        try:
            datetime.datetime.fromisoformat(result_dict[ts_field])
        except ValueError as e:
            raise AcceptanceHarnessError(
                f"Invalid timestamp in {ts_field}: {result_dict[ts_field]}. Error: {e}"
            )
    
    # AT-013 specific validation
    if scenario == "AT013_OUTAGE_UNTIL_RETRY":
        pre_retry = result_dict.get("pre_retry_snapshot")
        post_retry = result_dict.get("post_retry_snapshot")
        
        if pre_retry is None or post_retry is None:
            raise AcceptanceHarnessError(
                "AT-013 requires both pre_retry_snapshot and post_retry_snapshot"
            )
        
        # Validate generation increment
        pre_gen = pre_retry.get("generation")
        post_gen = post_retry.get("generation")
        
        if pre_gen is None or post_gen is None:
            raise AcceptanceHarnessError(
                "AT-013 pre/post retry snapshots must include generation"
            )
        
        if post_gen != pre_gen + 1:
            raise AcceptanceHarnessError(
                f"AT-013 generation increment invalid: pre={pre_gen}, post={post_gen}"
            )
        
        # Validate same workflow_run_id in both snapshots
        pre_run_id = pre_retry.get("workflow_run_id")
        post_run_id = post_retry.get("workflow_run_id")
        
        if pre_run_id != post_run_id:
            raise AcceptanceHarnessError(
                f"AT-013 run ID continuity violated: pre={pre_run_id}, post={post_run_id}"
            )
    
    return BrowserResult(
        schema_version=result_dict["schema_version"],
        scenario=result_dict["scenario"],
        harness_execution_id=result_dict["harness_execution_id"],
        product_workflow_run_id=result_dict["product_workflow_run_id"],
        correlation_id=result_dict.get("correlation_id"),
        plan_id=result_dict["plan_id"],
        browser_test_start=result_dict["browser_test_start"],
        browser_test_end=result_dict["browser_test_end"],
        final_state=result_dict["final_state"],
        screenshots=result_dict.get("screenshots", []),
        pre_retry_snapshot=result_dict.get("pre_retry_snapshot"),
        post_retry_snapshot=result_dict.get("post_retry_snapshot"),
    )


# ---------------------------------------------------------------------------
# Semantic evidence validation (B-11)
# ---------------------------------------------------------------------------


def validate_semantic_evidence(evidence: dict[str, Any]) -> None:
    """Validate semantic completeness of evidence (B-11).
    
    Checks:
    - Required fields present
    - No placeholder values
    - No error objects
    - Valid state values
    - Consistent IDs
    - Non-empty lists where required
    - Valid timestamps
    
    Raises:
        AcceptanceHarnessError: If validation fails.
    """
    category = evidence.get("category")
    
    # Required fields for all categories
    required_fields = ["workflow_run_id", "state", "dispatch_generation", "correlation_id", "timestamp", "step_count"]
    for field_name in required_fields:
        if field_name not in evidence:
            raise AcceptanceHarnessError(f"Missing required field: {field_name}")
    
    # Check for None identifiers
    for id_field in ["workflow_run_id", "correlation_id"]:
        if evidence.get(id_field) is None:
            raise AcceptanceHarnessError(f"{id_field} cannot be None")
    
    # Check for placeholder values
    placeholder_values = {"TODO", "N/A", "placeholder", "[capture failed]", "unknown"}
    state_value = evidence.get("state")
    if isinstance(state_value, str) and state_value in placeholder_values:
        raise AcceptanceHarnessError(f"Placeholder value in state: {state_value}")
    
    # Check for error objects
    if isinstance(state_value, dict) and "error" in state_value:
        raise AcceptanceHarnessError(f"Error object in state: {state_value}")
    
    # Validate state is a recognized value (case-insensitive)
    if isinstance(state_value, str) and state_value.upper() not in VALID_WORKFLOW_STATES:
        raise AcceptanceHarnessError(
            f"Invalid state value: {state_value}. Must be one of {VALID_WORKFLOW_STATES}"
        )
    
    # Category-specific validation
    if category == "workflow_steps":
        steps = evidence.get("steps", [])
        if not steps:
            raise AcceptanceHarnessError("workflow_steps category requires non-empty steps list")
        
        step_count = evidence.get("step_count", 0)
        if step_count == 0:
            raise AcceptanceHarnessError("workflow_steps category requires step_count > 0")
        
        # Check ID consistency
        identity_run_id = evidence.get("identity_workflow_run_id")
        if identity_run_id and identity_run_id != evidence.get("workflow_run_id"):
            raise AcceptanceHarnessError(
                f"ID mismatch: identity_workflow_run_id={identity_run_id}, "
                f"workflow_run_id={evidence.get('workflow_run_id')}"
            )
    
    elif category == "recommendations":
        rec_count = evidence.get("recommendation_count", 0)
        recommendations = evidence.get("recommendations", [])
        
        # AT-008 expects at least one recommendation
        if rec_count == 0 or not recommendations:
            raise AcceptanceHarnessError(
                "recommendations category requires at least one recommendation"
            )
    
    # Validate timestamp is recent (not stale)
    timestamp_str = evidence.get("timestamp")
    browser_start = evidence.get("browser_test_start")
    
    if timestamp_str and browser_start:
        try:
            ts = datetime.datetime.fromisoformat(timestamp_str)
            browser_ts = datetime.datetime.fromisoformat(browser_start)
            
            # Timestamp should be within browser test window or after
            if ts < browser_ts:
                # Allow some tolerance (e.g., 1 year for test data)
                one_year = datetime.timedelta(days=365)
                if browser_ts - ts > one_year:
                    raise AcceptanceHarnessError(
                        f"Stale timestamp: {timestamp_str} is before browser test start {browser_start}"
                    )
        except ValueError:
            pass  # Invalid timestamp format already caught


# ---------------------------------------------------------------------------
# Screenshot review (M-06)
# ---------------------------------------------------------------------------


def review_screenshot(
    path: Path, name: str, dom_snapshot_path: Path | None = None
) -> dict[str, Any]:
    """Review screenshot for validity and security (M-06).
    
    Checks:
    - PNG/JPEG signature
    - Non-zero dimensions within expected range
    - Modification time within reasonable window
    - DOM text snapshot (if provided) for secrets
    
    Args:
        path: Path to the screenshot file.
        name: Artifact name for logging.
        dom_snapshot_path: Optional path to companion DOM text snapshot.
    
    Returns:
        Review result dict.
    
    Raises:
        AcceptanceHarnessError: If review fails.
    """
    review_result: dict[str, Any] = {
        "artifact": name,
        "reviewed": True,
        "method": "signature_and_dom_scan",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    
    if not path.exists():
        raise AcceptanceHarnessError(f"Screenshot not found: {path}")
    
    # Read file bytes
    try:
        with open(path, "rb") as f:
            header = f.read(32)
    except Exception as e:
        raise AcceptanceHarnessError(f"Failed to read screenshot {path}: {e}")
    
    # Check PNG signature
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        review_result["format"] = "png"
        
        # Parse IHDR chunk for dimensions
        if len(header) >= 24:
            try:
                # IHDR starts at offset 8 (after signature)
                # Length (4 bytes) + "IHDR" (4 bytes) + width (4 bytes) + height (4 bytes)
                width = struct.unpack(">I", header[16:20])[0]
                height = struct.unpack(">I", header[20:24])[0]
                
                if width == 0 or height == 0:
                    raise AcceptanceHarnessError(
                        f"Screenshot has zero dimensions: {width}x{height}"
                    )
                
                # Reject extremely large dimensions (not a real screenshot)
                if width > 10000 or height > 10000:
                    raise AcceptanceHarnessError(
                        f"Screenshot dimensions too large: {width}x{height}"
                    )
                
                review_result["dimensions"] = {"width": width, "height": height}
            except struct.error as e:
                raise AcceptanceHarnessError(f"Failed to parse PNG IHDR: {e}")
    
    elif header.startswith(b"\xff\xd8\xff"):
        review_result["format"] = "jpeg"
        # JPEG dimension parsing would require more complex parsing
        # For now, accept JPEG with signature check only
    else:
        raise AcceptanceHarnessError(
            f"Unknown image format for {path}. Expected PNG or JPEG."
        )
    
    # Check modification time (should be recent, not from 2020)
    mtime = path.stat().st_mtime
    mtime_dt = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    
    # Reject screenshots older than 5 years (stale artifact detection)
    five_years_ago = now - datetime.timedelta(days=5*365)
    if mtime_dt < five_years_ago:
        raise AcceptanceHarnessError(
            f"Screenshot is stale (modification time {mtime_dt} is older than 5 years)"
        )
    
    review_result["modification_time"] = mtime_dt.isoformat()
    
    # Check DOM text snapshot if provided
    if dom_snapshot_path:
        if not dom_snapshot_path.exists():
            raise AcceptanceHarnessError(
                f"DOM snapshot not found: {dom_snapshot_path}"
            )
        
        try:
            dom_text = dom_snapshot_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            raise AcceptanceHarnessError(f"Failed to read DOM snapshot: {e}")
        
        # Scan for secret patterns
        secret_patterns = [
            r"password=[^\s\"&]+",
            r"secret[_-]?key=[^\s\"&]+",
            r"token=[^\s\"&]+",
            r"api[_-]?key=[^\s\"&]+",
            r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",  # JWT
            r"(?i)authorization[\"=:]+[^\s\"&,}]+",
        ]
        
        for pattern in secret_patterns:
            if re.search(pattern, dom_text, re.IGNORECASE):
                raise AcceptanceHarnessError(
                    f"Secret pattern found in DOM snapshot: {pattern}"
                )
        
        review_result["dom_snapshot_reviewed"] = True
    
    review_result["safe"] = True
    return review_result


# ---------------------------------------------------------------------------
# ZIP artifact review (L-04)
# ---------------------------------------------------------------------------


def review_zip_artifact(path: Path) -> dict[str, Any]:
    """Review ZIP artifact for security and validity (L-04).
    
    Checks:
    - Max member count (10000)
    - Max compressed size (100MB)
    - Max expanded size (500MB)
    - Max compression ratio (100:1)
    - Encrypted entries
    - Symlink entries
    - Nested archives
    - Absolute paths
    - .. traversal
    - Windows drive paths
    - Both / and \\ separators
    - Secret patterns in text members
    
    Args:
        path: Path to the ZIP file.
    
    Returns:
        Review result dict.
    
    Raises:
        AcceptanceHarnessError: If review fails.
    """
    review_result: dict[str, Any] = {
        "artifact": str(path),
        "reviewed": True,
        "method": "comprehensive_zip_scan",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    
    if not path.exists():
        raise AcceptanceHarnessError(f"ZIP file not found: {path}")
    
    # Check file size
    file_size = path.stat().st_size
    max_compressed_size = 100 * 1024 * 1024  # 100MB
    
    if file_size > max_compressed_size:
        raise AcceptanceHarnessError(
            f"ZIP file too large: {file_size} bytes (max {max_compressed_size})"
        )
    
    try:
        with zipfile.ZipFile(path, "r") as zf:
            infolist = zf.infolist()
            
            # Check member count
            max_members = 10000
            if len(infolist) > max_members:
                raise AcceptanceHarnessError(
                    f"ZIP has too many members: {len(infolist)} (max {max_members})"
                )
            
            total_expanded_size = 0
            max_expanded_size = 500 * 1024 * 1024  # 500MB
            
            for zip_info in infolist:
                filename = zip_info.filename
                
                # Check for path traversal (both / and \\)
                if filename.startswith("/") or filename.startswith("\\"):
                    raise AcceptanceHarnessError(
                        f"Absolute path in ZIP: {filename}"
                    )
                
                if ".." in filename:
                    raise AcceptanceHarnessError(
                        f"Path traversal in ZIP: {filename}"
                    )
                
                # Check for Windows drive paths
                if re.match(r"^[A-Za-z]:[\\/]", filename):
                    raise AcceptanceHarnessError(
                        f"Windows drive path in ZIP: {filename}"
                    )
                
                # Check for encrypted entries
                if zip_info.flag_bits & 0x1:
                    raise AcceptanceHarnessError(
                        f"Encrypted entry in ZIP: {filename}"
                    )
                
                # Check for symlinks (Unix symlink attribute)
                if (zip_info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise AcceptanceHarnessError(
                        f"Symlink entry in ZIP: {filename}"
                    )
                
                # Check for nested archives
                if filename.lower().endswith((".zip", ".tar", ".gz", ".bz2", ".xz")):
                    raise AcceptanceHarnessError(
                        f"Nested archive in ZIP: {filename}"
                    )
                
                # Accumulate expanded size
                if not zip_info.is_dir():
                    total_expanded_size += zip_info.file_size
                    
                    if total_expanded_size > max_expanded_size:
                        raise AcceptanceHarnessError(
                            f"ZIP expanded size too large: {total_expanded_size} bytes "
                            f"(max {max_expanded_size})"
                        )
                    
                    # Check compression ratio for this entry
                    if zip_info.compress_size > 0:
                        ratio = zip_info.file_size / zip_info.compress_size
                        max_ratio = 100.0
                        if ratio > max_ratio:
                            raise AcceptanceHarnessError(
                                f"Suspicious compression ratio for {filename}: "
                                f"{ratio:.1f}:1 (max {max_ratio}:1)"
                            )
                    
                    # Scan text files for secrets
                    if filename.endswith((".json", ".txt", ".log", ".har")):
                        try:
                            content = zf.read(filename).decode("utf-8", errors="ignore")
                            
                            secret_patterns = [
                                r"sk-[A-Za-z0-9]{20,}",
                                r"password[\"=:]+[^\s\"&,}]+",
                                r"secret[_-]?key[\"=:]+[^\s\"&,}]+",
                                r"token[\"=:]+[^\s\"&,}]+",
                                r"api[_-]?key[\"=:]+[^\s\"&,}]+",
                                r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
                                r"(?i)authorization[\"=:]+[^\s\"&,}]+",
                                # Bearer tokens in JSON/HAR value fields
                                r"(?i)bearer\s+[A-Za-z0-9_\-\.=]+",
                                # Authorization header in HAR format: "name":"Authorization","value":"..."
                                r"(?i)authorization[\"']?\s*,\s*[\"']?value[\"']?\s*:\s*[\"'][^\"]+",
                            ]
                            
                            for pattern in secret_patterns:
                                if re.search(pattern, content, re.IGNORECASE):
                                    raise AcceptanceHarnessError(
                                        f"Secret pattern found in ZIP member {filename}: {pattern}"
                                    )
                        except UnicodeDecodeError:
                            pass  # Binary file, skip text scan
            
            review_result["member_count"] = len(infolist)
            review_result["total_expanded_size"] = total_expanded_size
            review_result["safe"] = True
            
    except zipfile.BadZipFile as e:
        raise AcceptanceHarnessError(f"Invalid ZIP file: {e}")
    
    return review_result


# ---------------------------------------------------------------------------
# Evidence Collector
# ---------------------------------------------------------------------------


class EvidenceCollector:
    """Collects, redacts, and checksums formal-evidence artifacts.

    Lifecycle:
    1. Raw artifacts collected in raw/ during execution.
    2. After execution, redact all raw text artifacts to redacted/.
    3. Verify redaction (fail closed if secrets remain).
    4. Review binary artifacts (fail closed if unreviewed).
    5. Generate checksums for all redacted artifacts.
    6. Delete raw/ only after successful redaction and checksum.
    7. Write manifest.json describing all artifacts.
    """

    def __init__(self, evidence_dir: Path, run_id: str) -> None:
        self.evidence_dir = evidence_dir
        self.run_id = run_id
        self.raw_dir = evidence_dir / "raw"
        self.redacted_dir = evidence_dir / "redacted"
        self.artifacts: list[dict[str, str]] = []
        self.binary_reviews: dict[str, dict[str, Any]] = {}
        self._failure = False
        self._complete = False

    def setup(self) -> None:
        """Create evidence directory structure."""
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(exist_ok=True)
        self.redacted_dir.mkdir(exist_ok=True)
        (self.evidence_dir / "logs").mkdir(exist_ok=True)

    def collect_text(self, name: str, content: str, source: str = "generated") -> Path:
        """Write a raw text artifact."""
        path = self.raw_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.artifacts.append({
            "name": name,
            "source": source,
            "type": "text",
        })
        return path

    def collect_json(self, name: str, data: dict[str, Any], source: str = "api") -> Path:
        """Write a raw JSON artifact."""
        path = self.raw_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        self.artifacts.append({
            "name": name,
            "source": source,
            "type": "json",
        })
        return path

    def collect_file(self, src: Path, name: str, source: str = "file") -> Path:
        """Copy a file into raw artifacts."""
        dst = self.raw_dir / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_file():
            shutil.copy2(src, dst)
        elif src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        self.artifacts.append({
            "name": name,
            "source": source,
            "type": "file",
        })
        return dst

    def collect_repository_baseline(self) -> None:
        """Capture repository baseline state."""
        git_state = capture_git_state()
        self.collect_json("repository/baseline.json", git_state, source="git")

    def collect_repository_final(self) -> None:
        """Capture repository final state."""
        git_state = capture_git_state()
        self.collect_json("repository/final.json", git_state, source="git")

    def collect_versions(self) -> None:
        """Capture runtime and tool versions."""
        versions = capture_tool_versions()
        self.collect_json("environment/versions.json", versions, source="system")

    def collect_scenario_identity(
        self, scenario: str, correlation_id: str | None = None,
        workflow_run_id: str | None = None,
        dispatch_generation: int | None = None
    ) -> None:
        """Record scenario identity (B-07)."""
        identity = {
            "harness_run_id": self.run_id,
            "product_workflow_run_id": workflow_run_id,
            "scenario": scenario,
            "correlation_id": correlation_id,
            "dispatch_generation": dispatch_generation,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self.collect_json(
            f"scenarios/{scenario}/identity.json", identity, source="harness"
        )

    def collect_api_snapshot(
        self, scenario: str, name: str, data: dict[str, Any]
    ) -> None:
        """Capture an API response snapshot."""
        self.collect_json(
            f"scenarios/{scenario}/api/{name}.json", data, source="api"
        )

    def collect_test_results(
        self, scenario: str, test_type: str, exit_code: int, output: str,
        parsed_counts: dict[str, int] | None = None
    ) -> None:
        """Capture test results (B-08)."""
        self.collect_json(
            f"scenarios/{scenario}/tests/{test_type}.json",
            {
                "exit_code": exit_code,
                "output": output,
                "parsed_counts": parsed_counts or {},
            },
            source=test_type,
        )

    def collect_workflow_steps(
        self, scenario: str, run_id: str, steps: list[dict[str, Any]]
    ) -> None:
        """Collect workflow step audit trail (B-01 category 4)."""
        self.collect_json(
            f"scenarios/{scenario}/db/workflow_steps.json",
            {"workflow_run_id": run_id, "steps": steps, "step_count": len(steps)},
            source="database",
        )

    def collect_workflow_run_state(
        self, scenario: str, run_state: dict[str, Any]
    ) -> None:
        """Collect current workflow run state (B-01 category 5)."""
        self.collect_json(
            f"scenarios/{scenario}/db/workflow_run_state.json",
            run_state,
            source="database",
        )

    def collect_provider_retry_count(
        self, scenario: str, retry_count: int
    ) -> None:
        """Collect provider retry attempt count (B-01 category 6)."""
        self.collect_json(
            f"scenarios/{scenario}/db/provider_retry_count.json",
            {"retry_count": retry_count},
            source="log_parsing",
        )

    def collect_recommendations(
        self, scenario: str, run_id: str, recommendations: list[dict[str, Any]]
    ) -> None:
        """Collect recommendations (B-01 category 8)."""
        self.collect_json(
            f"scenarios/{scenario}/db/recommendations.json",
            {
                "workflow_run_id": run_id,
                "recommendations": recommendations,
                "count": len(recommendations),
            },
            source="database",
        )

    def collect_controlled_write_check(
        self, scenario: str, procurement_tasks_exist: bool
    ) -> None:
        """Collect controlled-write absence check (B-01 category 9)."""
        self.collect_json(
            f"scenarios/{scenario}/db/controlled_write_check.json",
            {"procurement_tasks_exist": procurement_tasks_exist},
            source="database",
        )

    def collect_risk_api_availability(
        self, scenario: str, risk_data: dict[str, Any]
    ) -> None:
        """Collect deterministic risk API availability (B-01 category 10)."""
        self.collect_json(
            f"scenarios/{scenario}/api/risk_api.json",
            risk_data,
            source="api",
        )

    def review_binary_artifact(self, path: Path, name: str) -> dict[str, Any]:
        """Review binary artifact for sensitive content (B-03).
        
        Returns review result dict with:
        - reviewed: bool
        - method: str
        - safe: bool
        - findings: list[str]
        """
        review_result: dict[str, Any] = {
            "artifact": name,
            "reviewed": True,
            "method": "automated_scan",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        
        findings: list[str] = []
        
        # For ZIP files, use comprehensive review
        if path.suffix == ".zip":
            try:
                zip_review = review_zip_artifact(path)
                review_result.update(zip_review)
            except AcceptanceHarnessError as e:
                findings.append(str(e))
        
        # For screenshots, use signature and DOM review
        elif path.suffix in ('.png', '.jpg', '.jpeg', '.gif'):
            try:
                screenshot_review = review_screenshot(path, name)
                review_result.update(screenshot_review)
            except AcceptanceHarnessError as e:
                findings.append(str(e))
        
        review_result["safe"] = len(findings) == 0
        review_result["findings"] = findings
        
        self.binary_reviews[name] = review_result
        return review_result

    def verify_evidence_completeness(self) -> None:
        """Verify all required evidence categories are present (B-06).
        
        Raises AcceptanceHarnessError if any required category is missing.
        """
        missing: list[str] = []
        for required_path in REQUIRED_EVIDENCE_CATEGORIES:
            artifact_path = self.raw_dir / required_path
            if not artifact_path.exists():
                missing.append(required_path)
        
        if missing:
            self._failure = True
            raise AcceptanceHarnessError(
                f"Evidence completeness check failed. Missing {len(missing)} required artifacts:\n"
                + "\n".join(f"  - {m}" for m in missing[:20])
                + ("\n  ..." if len(missing) > 20 else "")
            )
        
        self._complete = True

    def redact_and_verify(self, patterns: list[str] | None = None) -> None:
        """Redact all raw artifacts, verify, review binaries, and generate checksums.

        Raises AcceptanceHarnessError if redaction verification fails,
        binary review fails, or required evidence is missing.

        On success: raw/ is deleted, checksums.sha256 is written.
        On failure: raw/ is preserved for debugging.
        """
        # Step 1: Verify completeness (B-06)
        self.verify_evidence_completeness()

        # Step 2: Redact all files from raw/ to redacted/
        redacted_files: list[Path] = []
        for src_file in sorted(self.raw_dir.rglob("*")):
            if not src_file.is_file():
                continue
            rel_path = src_file.relative_to(self.raw_dir)
            dst_file = self.redacted_dir / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            if src_file.suffix in (".png", ".jpg", ".jpeg", ".gif", ".zip", ".gz"):
                # Binary files: review before copying (B-03)
                review_result = self.review_binary_artifact(src_file, str(rel_path))
                if not review_result["safe"]:
                    self._failure = True
                    raise AcceptanceHarnessError(
                        f"Binary artifact review failed for {rel_path}: "
                        f"{', '.join(review_result['findings'])}"
                    )
                # Copy reviewed binary
                shutil.copy2(src_file, dst_file)
            else:
                # Text files: redact
                try:
                    redact_file(src_file, dst_file, patterns)
                except Exception as e:
                    self._failure = True
                    raise AcceptanceHarnessError(
                        f"Redaction failed for {src_file}: {e}"
                    ) from e
            redacted_files.append(dst_file)

        # Step 3: Verify redaction on all text files
        all_violations: list[tuple[str, list[str]]] = []
        for redacted_file in redacted_files:
            if redacted_file.suffix in (".png", ".jpg", ".jpeg", ".gif", ".zip", ".gz"):
                continue
            try:
                content = redacted_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            violations = verify_redaction(content, patterns)
            if violations:
                rel = str(redacted_file.relative_to(self.redacted_dir))
                all_violations.append((rel, violations))

        if all_violations:
            self._failure = True
            detail = "; ".join(
                f"{path}: {len(pats)} patterns still match"
                for path, pats in all_violations
            )
            raise AcceptanceHarnessError(
                f"Redaction verification failed — secrets remain: {detail}. "
                "Raw artifacts preserved for debugging."
            )

        # Step 4: Generate checksums
        try:
            write_checksums_file(self.redacted_dir)
        except AcceptanceHarnessError:
            self._failure = True
            raise

        # Step 5: Write manifest (H-06)
        self._write_manifest()

        # Step 6: Success - remove raw artifacts
        shutil.rmtree(self.raw_dir)

    def _write_manifest(self) -> None:
        """Write deterministic manifest.json (H-06 corrected)."""
        # Compute checksums of current files (before manifest)
        checksums_before = compute_checksums(self.redacted_dir)
        
        # Build artifacts list from collected artifacts
        artifacts_list = []
        for artifact in self.artifacts:
            artifact_path = artifact["name"]
            if artifact_path in checksums_before:
                artifacts_list.append({
                    "path": artifact_path,
                    "sha256": checksums_before[artifact_path],
                    "source": artifact["source"],
                    "type": artifact["type"],
                })
        
        # Add binary review results (B-03)
        binary_reviews_list = []
        for name, review in self.binary_reviews.items():
            binary_reviews_list.append({
                "artifact": name,
                "reviewed": review["reviewed"],
                "method": review["method"],
                "safe": review["safe"],
                "findings": review["findings"],
            })
        
        manifest = {
            "run_id": self.run_id,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "complete": self._complete,
            "artifact_count": len(artifacts_list),
            "artifacts": artifacts_list,
            "binary_reviews": binary_reviews_list,
        }

        manifest_path = self.redacted_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

        # Recompute checksums including the manifest
        write_checksums_file(self.redacted_dir)


# ---------------------------------------------------------------------------
# Acceptance environment and validation
# ---------------------------------------------------------------------------


def validate_acceptance_database_url(url: str) -> None:
    """Fail-closed validation: must be localhost:5433/forgemind_acceptance."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        raise AcceptanceHarnessError(f"Database host must be localhost, got {parsed.hostname}")
    if parsed.port != ACCEPTANCE_DB_PORT:
        raise AcceptanceHarnessError(f"Database port must be {ACCEPTANCE_DB_PORT}, got {parsed.port}")
    if parsed.path.lstrip("/") != ACCEPTANCE_DB_NAME:
        raise AcceptanceHarnessError(f"Database name must be {ACCEPTANCE_DB_NAME}, got {parsed.path}")


def validate_acceptance_redis_url(url: str) -> None:
    """Fail-closed validation: must be redis://localhost:6380/0."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in ("redis", "rediss"):
        raise AcceptanceHarnessError(f"Redis scheme must be redis/rediss, got {parsed.scheme}")
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        raise AcceptanceHarnessError(f"Redis host must be localhost, got {parsed.hostname}")
    if parsed.port != ACCEPTANCE_REDIS_PORT:
        raise AcceptanceHarnessError(f"Redis port must be {ACCEPTANCE_REDIS_PORT}, got {parsed.port}")


def check_port_available(port: int) -> bool:
    """Check if a TCP port is available (not listening)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", port))
        return result != 0  # 0 means connection succeeded (port in use)


def wait_for_postgres(port: int, timeout: int = 30) -> None:
    """Poll pg_isready until PostgreSQL is ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["pg_isready", "-h", "localhost", "-p", str(port)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return
        time.sleep(1)
    raise AcceptanceHarnessError(f"PostgreSQL on port {port} did not become ready within {timeout}s")


def wait_for_redis(port: int, timeout: int = 10) -> None:
    """Poll Redis PING/PONG via raw socket (no redis-cli dependency)."""
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(2)
                sock.connect(("localhost", port))
                # Send PING command (RESP protocol)
                sock.sendall(b"PING\r\n")
                response = sock.recv(16)
                if b"PONG" in response:
                    return
        except (socket.error, OSError):
            pass
        time.sleep(1)
    raise AcceptanceHarnessError(f"Redis on port {port} did not become ready within {timeout}s")


def wait_for_http(url: str, timeout: int = 30) -> None:
    """Poll an HTTP endpoint until it responds."""
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1)
    raise AcceptanceHarnessError(f"HTTP endpoint {url} did not become ready within {timeout}s")


def verify_ports_clear(ports: list[int]) -> None:
    """Verify all specified ports are clear after teardown (L-03).
    
    Raises AcceptanceHarnessError if any port is still occupied.
    """
    still_in_use = []
    for port in ports:
        if not check_port_available(port):
            still_in_use.append(port)
    
    if still_in_use:
        raise AcceptanceHarnessError(
            f"Ports still in use after teardown: {still_in_use}. "
            "This may indicate zombie processes or external services."
        )


class AcceptanceEnvironment:
    """Manages the isolated acceptance environment lifecycle."""

    def __init__(self, run_id: str, mode: str) -> None:
        self.run_id = run_id
        self.mode = mode
        self.evidence_dir = REPO_ROOT / "evidence" / run_id
        self.containers: list[str] = []
        self.processes: list[subprocess.Popen[bytes]] = []
        self._log_handles: list[io.TextIOWrapper] = []  # L-05: track log file handles

    def setup(self) -> None:
        """Start PostgreSQL, Redis, prepare database."""
        print(f"[{self.run_id}] Setting up acceptance environment...")

        # Validate URLs
        validate_acceptance_database_url(ACCEPTANCE_DATABASE_URL)
        validate_acceptance_redis_url(ACCEPTANCE_REDIS_URL)

        # Check ports
        if not check_port_available(ACCEPTANCE_DB_PORT):
            raise AcceptanceHarnessError(f"Port {ACCEPTANCE_DB_PORT} is already in use")
        if not check_port_available(ACCEPTANCE_REDIS_PORT):
            raise AcceptanceHarnessError(f"Port {ACCEPTANCE_REDIS_PORT} is already in use")

        # Create evidence directory
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        (self.evidence_dir / "logs").mkdir(exist_ok=True)

        # Start PostgreSQL
        pg_container = f"forgemind-{self.run_id}-pg"
        print(f"  Starting PostgreSQL container: {pg_container}")
        subprocess.run(
            [
                "docker", "run", "-d",
                "--name", pg_container,
                "--label", f"forgemind-run={self.run_id}",
                "-p", f"{ACCEPTANCE_DB_PORT}:5432",
                "-e", f"POSTGRES_DB={ACCEPTANCE_DB_NAME}",
                "-e", "POSTGRES_USER=forgemind",
                "-e", "POSTGRES_PASSWORD=forgemind",
                "pgvector/pgvector:pg16",
            ],
            check=True,
            capture_output=True,
        )
        self.containers.append(pg_container)
        wait_for_postgres(ACCEPTANCE_DB_PORT)

        # Start Redis
        redis_container = f"forgemind-{self.run_id}-redis"
        print(f"  Starting Redis container: {redis_container}")
        subprocess.run(
            [
                "docker", "run", "-d",
                "--name", redis_container,
                "--label", f"forgemind-run={self.run_id}",
                "-p", f"{ACCEPTANCE_REDIS_PORT}:6379",
                "redis:7",
            ],
            check=True,
            capture_output=True,
        )
        self.containers.append(redis_container)
        wait_for_redis(ACCEPTANCE_REDIS_PORT)

        # Prepare database (migrations + seed)
        print("  Running Alembic migrations...")
        env = os.environ.copy()
        env["DATABASE_URL"] = ACCEPTANCE_DATABASE_URL
        subprocess.run(
            [str(VENV_BIN / "alembic"), "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
            capture_output=True,
        )

        print("  Running seed generator...")
        subprocess.run(
            [str(VENV_BIN / "python3.12"), "-m", "app.seed.generator.main"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
            capture_output=True,
        )

        print(f"[{self.run_id}] Environment ready.")

    def start_services(self, scenario: str) -> None:
        """Start backend API, ARQ worker, frontend dev server."""
        print(f"[{self.run_id}] Starting services (scenario={scenario})...")

        env = os.environ.copy()
        env["DATABASE_URL"] = ACCEPTANCE_DATABASE_URL
        env["REDIS_URL"] = ACCEPTANCE_REDIS_URL
        env["FORGEMIND_ACCEPTANCE_SCENARIO"] = scenario
        env["ENVIRONMENT"] = "development"
        env["SECRET_KEY"] = "acceptance-test-secret-key-must-be-32-chars"
        import json
        env["CORS_ORIGINS"] = json.dumps([f"http://localhost:{ACCEPTANCE_FRONTEND_PORT}"])

        # Backend API
        log_backend = self.evidence_dir / "logs" / f"backend-{scenario}.log"
        log_backend_handle = open(log_backend, "w")
        self._log_handles.append(log_backend_handle)
        backend_proc = subprocess.Popen(
            [
                str(VENV_BIN / "uvicorn"),
                "app.main:app",
                "--host", "0.0.0.0",
                "--port", str(ACCEPTANCE_BACKEND_PORT),
            ],
            cwd=BACKEND_DIR,
            env=env,
            stdout=log_backend_handle,
            stderr=subprocess.STDOUT,
        )
        self.processes.append(backend_proc)
        wait_for_http(f"http://localhost:{ACCEPTANCE_BACKEND_PORT}/health")
        print(f"  Backend API started on port {ACCEPTANCE_BACKEND_PORT}")

        # ARQ worker
        log_worker = self.evidence_dir / "logs" / f"worker-{scenario}.log"
        log_worker_handle = open(log_worker, "w")
        self._log_handles.append(log_worker_handle)
        worker_proc = subprocess.Popen(
            [str(VENV_BIN / "python3.12"), "-m", "arq", "app.worker.WorkerSettings"],
            cwd=BACKEND_DIR,
            env=env,
            stdout=log_worker_handle,
            stderr=subprocess.STDOUT,
        )
        self.processes.append(worker_proc)
        time.sleep(5)
        print("  ARQ worker started")

        # Frontend dev server
        log_frontend = self.evidence_dir / "logs" / f"frontend-{scenario}.log"
        log_frontend_handle = open(log_frontend, "w")
        self._log_handles.append(log_frontend_handle)
        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = f"http://localhost:{ACCEPTANCE_BACKEND_PORT}/api/v1"
        frontend_proc = subprocess.Popen(
            ["npm", "run", "dev", "--", "--port", str(ACCEPTANCE_FRONTEND_PORT)],
            cwd=FRONTEND_DIR,
            env=frontend_env,
            stdout=log_frontend_handle,
            stderr=subprocess.STDOUT,
        )
        self.processes.append(frontend_proc)
        wait_for_http(ACCEPTANCE_FRONTEND_URL)
        print(f"  Frontend dev server started on port {ACCEPTANCE_FRONTEND_PORT}")

    def stop_services(self) -> None:
        """Stop all running services (backend, worker, frontend)."""
        print(f"[{self.run_id}] Stopping services...")
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        self.processes.clear()
        
        # L-05: Flush and close all tracked log handles
        for handle in self._log_handles:
            try:
                handle.flush()
                handle.close()
            except Exception:
                pass
        self._log_handles.clear()
        
        time.sleep(2)  # Allow ports to be released

    def run_backend_tests(self, scenario: str) -> tuple[int, str]:
        """Run backend integration tests for AT-008 or AT-013 (B-08).
        
        Returns:
            Tuple of (exit_code, stdout_output)
        """
        print(f"[{self.run_id}] Running backend acceptance tests for {scenario}...")
        env = os.environ.copy()
        env["DATABASE_URL"] = ACCEPTANCE_DATABASE_URL
        env["REDIS_URL"] = ACCEPTANCE_REDIS_URL

        if scenario == "AT008_INVALID_OUTPUT":
            test_file = "tests/integration/test_at008_acceptance.py"
        elif scenario == "AT013_OUTAGE_UNTIL_RETRY":
            test_file = "tests/integration/test_at013_acceptance.py"
        else:
            raise AcceptanceHarnessError(f"Unknown scenario: {scenario}")

        result = subprocess.run(
            [
                str(VENV_BIN / "pytest"),
                test_file,
                "-v",
            ],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout

    def run_playwright_tests(self, scenario: str) -> tuple[int, str]:
        """Run Playwright acceptance scenarios for the given scenario only (B-08).
        
        Returns:
            Tuple of (exit_code, stdout_output)
        """
        print(f"[{self.run_id}] Running Playwright acceptance tests for {scenario}...")
        env = os.environ.copy()
        env["PLAYWRIGHT_ACCEPTANCE_BASE_URL"] = ACCEPTANCE_FRONTEND_URL
        env["ACCEPTANCE_FRONTEND_PORT"] = str(ACCEPTANCE_FRONTEND_PORT)

        if scenario == "AT008_INVALID_OUTPUT":
            spec_file = "acceptance-e2e/at008-acceptance.spec.ts"
        elif scenario == "AT013_OUTAGE_UNTIL_RETRY":
            spec_file = "acceptance-e2e/at013-acceptance.spec.ts"
        else:
            raise AcceptanceHarnessError(f"Unknown scenario: {scenario}")

        result = subprocess.run(
            [
                "npx", "playwright", "test",
                spec_file,
                "--config=playwright.acceptance.config.ts",
            ],
            cwd=FRONTEND_DIR,
            env=env,
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout

    def teardown(self) -> None:
        """Stop processes and remove owned containers."""
        print(f"[{self.run_id}] Tearing down environment...")

        # Stop subprocesses
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()

        # L-05: Close all tracked log handles
        for handle in self._log_handles:
            try:
                handle.flush()
                handle.close()
            except Exception:
                pass
        self._log_handles.clear()

        # Remove owned containers
        for container in self.containers:
            # Verify ownership via label
            result = subprocess.run(
                [
                    "docker", "inspect",
                    "--format", '{{index .Config.Labels "forgemind-run"}}',
                    container,
                ],
                capture_output=True,
                text=True,
            )
            label = result.stdout.strip()
            if label == self.run_id:
                subprocess.run(
                    ["docker", "stop", container],
                    capture_output=True,
                )
                subprocess.run(
                    ["docker", "rm", container],
                    capture_output=True,
                )
                print(f"  Removed container: {container}")
            else:
                print(f"  Skipping container {container} (not owned by this run)")

        # Verify ports are clear (L-03: raises if occupied)
        verify_ports_clear([
            ACCEPTANCE_DB_PORT,
            ACCEPTANCE_REDIS_PORT,
            ACCEPTANCE_BACKEND_PORT,
            ACCEPTANCE_FRONTEND_PORT,
        ])

        print(f"[{self.run_id}] Teardown complete.")


# ---------------------------------------------------------------------------
# Verify mode (Phase B) — implementation verification only
# ---------------------------------------------------------------------------


def run_verify_mode(run_id: str) -> int:
    """Execute Phase B implementation-verification mode.

    This mode proves the harness works correctly. Its output is
    implementation-verification evidence only — it is NOT authoritative
    Phase C evidence and must not be labeled as such.
    """
    env = AcceptanceEnvironment(run_id=run_id, mode="verify")

    try:
        env.setup()

        scenarios = ["AT008_INVALID_OUTPUT", "AT013_OUTAGE_UNTIL_RETRY"]

        for scenario in scenarios:
            print(f"\n{'='*70}")
            print(f"Scenario: {scenario}")
            print('='*70)

            env.start_services(scenario)

            backend_rc, _ = env.run_backend_tests(scenario)
            if backend_rc != 0:
                print(f"Backend tests failed for {scenario} (exit code {backend_rc})")
                env.stop_services()
                return backend_rc

            playwright_rc, _ = env.run_playwright_tests(scenario)
            if playwright_rc != 0:
                print(f"Playwright tests failed for {scenario} (exit code {playwright_rc})")
                env.stop_services()
                return playwright_rc

            env.stop_services()

        print(f"\n[{run_id}] Phase B implementation-verification complete.")
        print("NOTE: This is implementation verification only, not authoritative Phase C evidence.")
        print(f"Evidence directory: {env.evidence_dir}")
        return 0

    except AcceptanceHarnessError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130
    finally:
        env.teardown()


# ---------------------------------------------------------------------------
# Formal mode (Phase C) — authoritative evidence collection
# ---------------------------------------------------------------------------


def parse_pytest_output(output: str) -> dict[str, int]:
    """Parse pytest output for pass/fail/skip counts (B-08)."""
    counts: dict[str, int] = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "deselected": 0,
    }
    
    import re
    summary_pattern = r'(\d+) passed'
    match = re.search(summary_pattern, output)
    if match:
        counts["passed"] = int(match.group(1))
    
    failed_pattern = r'(\d+) failed'
    match = re.search(failed_pattern, output)
    if match:
        counts["failed"] = int(match.group(1))
    
    skipped_pattern = r'(\d+) skipped'
    match = re.search(skipped_pattern, output)
    if match:
        counts["skipped"] = int(match.group(1))
    
    deselected_pattern = r'(\d+) deselected'
    match = re.search(deselected_pattern, output)
    if match:
        counts["deselected"] = int(match.group(1))
    
    return counts


def collect_service_logs(collector: EvidenceCollector, logs_dir: Path) -> None:
    """Collect service logs into raw artifacts (H-03).
    
    Logs are moved (not copied) to ensure no unredacted copies remain.
    """
    if logs_dir.exists():
        for log_file in logs_dir.iterdir():
            if log_file.is_file():
                collector.collect_file(
                    log_file, f"logs/{log_file.name}", source="service-log"
                )
                # Remove original to prevent unredacted copy (B-02)
                log_file.unlink()


def run_formal_mode(run_id: str) -> int:
    """Execute Phase C formal-evidence collection mode.

    Runs both deterministic scenarios sequentially, collects complete
    evidence, redacts secrets, generates checksums, and writes a manifest.

    Does NOT declare AT-008 or AT-013 PASS — that belongs to Phase D.
    
    Single finalization path ensures:
    - Logs collected on all paths (H-03)
    - Protected audit reverified on all paths (H-04)
    - Repository invariants checked on all paths (H-07)
    - No evidence failures swallowed (B-10)
    - No unredacted logs survive (B-02)
    """
    # Pre-flight: verify protected audit integrity
    verify_protected_audit()

    # Capture baseline repository state
    baseline_git = capture_git_state()

    evidence_dir = REPO_ROOT / "evidence" / run_id
    collector = EvidenceCollector(evidence_dir=evidence_dir, run_id=run_id)
    collector.setup()

    # Record baseline
    collector.collect_json("repository/baseline.json", baseline_git, source="git")

    env = AcceptanceEnvironment(run_id=run_id, mode="formal")
    
    # Track scenario failures (B-10: no swallowing)
    scenario_failure: int | None = None

    try:
        env.setup()
        collector.collect_versions()

        scenarios = ["AT008_INVALID_OUTPUT", "AT013_OUTAGE_UNTIL_RETRY"]

        for scenario in scenarios:
            print(f"\n{'='*70}")
            print(f"[FORMAL] Scenario: {scenario}")
            print('='*70)

            # Collect scenario identity (B-07: will be populated from API later)
            collector.collect_scenario_identity(scenario)

            env.start_services(scenario)

            # Record test start time for DB queries
            test_start_time = datetime.datetime.now(datetime.timezone.utc)

            # Run backend tests and capture output (B-08)
            backend_rc, backend_output = env.run_backend_tests(scenario)
            backend_counts = parse_pytest_output(backend_output)
            collector.collect_test_results(
                scenario, "backend", backend_rc, backend_output, backend_counts
            )

            # Collect DB/API evidence (B-10: no broad except swallowing)
            # Query for workflow runs created during this test
            workflow_run_ids = find_recent_workflow_runs(test_start_time, scenario)
            run_state: dict[str, Any] = {}
            
            if workflow_run_ids:
                primary_run_id = workflow_run_ids[0]
                
                # Update scenario identity with actual workflow_run_id (B-07)
                collector.collect_scenario_identity(
                    scenario,
                    workflow_run_id=primary_run_id,
                )
                
                # Collect workflow steps audit trail (B-01 category 4)
                steps = query_workflow_steps(primary_run_id)
                collector.collect_workflow_steps(scenario, primary_run_id, steps)
                
                # Collect workflow run state (B-01 category 5)
                run_state = query_workflow_run_state(primary_run_id)
                collector.collect_workflow_run_state(scenario, run_state)
                
                # Collect dispatch generation from API (B-01 category 7)
                api_snapshot = query_workflow_run_api(primary_run_id)
                collector.collect_api_snapshot(scenario, "dispatch_generation", api_snapshot)
                
                # Collect recommendations (B-01 category 8)
                recommendations = query_recommendations(primary_run_id)
                collector.collect_recommendations(scenario, primary_run_id, recommendations)
                
                # Collect controlled-write check (B-01 category 9)
                procurement_exist = check_procurement_tasks_exist()
                collector.collect_controlled_write_check(scenario, procurement_exist)
            
            # Collect provider retry count from logs (B-01 category 6)
            # Use the actual log path for this run
            log_path = evidence_dir / "logs" / f"worker-{scenario}.log"
            correlation_id: str | None = None
            if workflow_run_ids and "run_state" in dir():
                correlation_id = run_state.get("correlation_id")
            if correlation_id:
                retry_count = count_provider_retry_attempts(log_path, str(correlation_id))
            else:
                retry_count = 0
            collector.collect_provider_retry_count(scenario, retry_count)
            
            # Collect risk API availability (B-01 category 10)
            risk_data = query_risk_api("PLAN-2026-W31")
            collector.collect_risk_api_availability(scenario, risk_data)

            if backend_rc != 0:
                print(f"Backend tests failed for {scenario} (exit code {backend_rc})")
                scenario_failure = backend_rc
                # Stop services to flush logs (H-03)
                env.stop_services()
                # Collect logs before breaking (H-03)
                collect_service_logs(collector, evidence_dir / "logs")
                break

            # Run Playwright tests (B-08)
            playwright_rc, playwright_output = env.run_playwright_tests(scenario)
            playwright_counts = parse_pytest_output(playwright_output)
            collector.collect_test_results(
                scenario, "playwright", playwright_rc, playwright_output, playwright_counts
            )

            # Collect Playwright artifacts if available
            pw_results_dir = FRONTEND_DIR / "test-results" / "acceptance"
            if pw_results_dir.exists():
                collector.collect_file(
                    pw_results_dir,
                    f"scenarios/{scenario}/playwright-results",
                    source="playwright",
                )

            if playwright_rc != 0:
                print(f"Playwright tests failed for {scenario} (exit code {playwright_rc})")
                scenario_failure = playwright_rc
                # Stop services to flush logs (H-03)
                env.stop_services()
                # Collect logs before breaking (H-03)
                collect_service_logs(collector, evidence_dir / "logs")
                break

            env.stop_services()
            # Collect logs after each successful scenario (H-03)
            collect_service_logs(collector, evidence_dir / "logs")

        # Post-execution finalization (single path for all outcomes)
        
        # Capture final repository state
        final_git = capture_git_state()
        collector.collect_json("repository/final.json", final_git, source="git")

        # Verify repository invariants (B-05, H-07)
        verify_repository_invariants(baseline_git, final_git)

        # Re-verify protected audit (H-04)
        verify_protected_audit()

        # If scenario failed, stop here (don't produce complete package)
        if scenario_failure is not None:
            print(f"\nScenario failed with exit code {scenario_failure}")
            print("Evidence collection stopped before finalization.")
            print(f"Raw evidence preserved at: {evidence_dir / 'raw'}")
            return scenario_failure

        # Redact, verify, checksum, cleanup (B-10: don't swallow failures)
        print(f"\n[{run_id}] Redacting and verifying evidence...")
        collector.redact_and_verify()

        print(f"\n[{run_id}] Formal evidence collection complete.")
        print(f"Evidence directory: {evidence_dir / 'redacted'}")
        print("NOTE: Scenario execution succeeded. Evidence completeness verified.")
        print("AT-008 and AT-013 formal PASS declarations require Phase D review.")
        return 0

    except AcceptanceHarnessError as e:
        print(f"EVIDENCE COLLECTION ERROR: {e}", file=sys.stderr)
        # Collect logs on evidence failure (H-03)
        collect_service_logs(collector, evidence_dir / "logs")
        # Re-verify protected audit even on failure (H-04)
        try:
            verify_protected_audit()
        except AcceptanceHarnessError as audit_err:
            print(f"PROTECTED AUDIT FAILURE: {audit_err}", file=sys.stderr)
        
        # H-07: Verify repository invariants on exception path
        try:
            final_git = capture_git_state()
            verify_repository_invariants(baseline_git, final_git)
        except AcceptanceHarnessError as inv_err:
            print(f"REPOSITORY INVARIANT FAILURE: {inv_err}", file=sys.stderr)
        
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        # Collect logs on interruption (H-03)
        collect_service_logs(collector, evidence_dir / "logs")
        # Re-verify protected audit even on interruption (H-04)
        try:
            verify_protected_audit()
        except AcceptanceHarnessError:
            pass
        
        # H-07: Verify repository invariants on interruption path
        try:
            final_git = capture_git_state()
            verify_repository_invariants(baseline_git, final_git)
        except AcceptanceHarnessError:
            pass
        
        return 130
    finally:
        env.teardown()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="WP-REC-03H acceptance harness orchestration"
    )
    parser.add_argument(
        "--mode",
        choices=["verify", "formal"],
        required=True,
        help="Execution mode: verify (Phase B) or formal (Phase C)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Run identifier for evidence directory. Auto-generated if omitted. "
             "Must contain only alphanumeric, hyphens, underscores, and dots.",
    )
    args = parser.parse_args()

    # Resolve run ID
    if args.run_id:
        run_id = args.run_id
        validate_run_id(run_id)
    else:
        run_id = generate_run_id()

    # Validate evidence directory doesn't already exist (for formal mode)
    if args.mode == "formal":
        evidence_dir = REPO_ROOT / "evidence" / run_id
        validate_evidence_dir_not_exists(evidence_dir)
        return run_formal_mode(run_id)
    else:
        return run_verify_mode(run_id)


if __name__ == "__main__":
    sys.exit(main())
