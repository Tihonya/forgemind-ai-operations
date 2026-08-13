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
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

# Repository root (parent of scripts/)
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

# Secret patterns for redaction (configurable for testing)
DEFAULT_REDACTION_PATTERNS: list[str] = [
    r"sk-[A-Za-z0-9]{20,}",
    r"password=[^\s&]+",
    r"secret[_-]?key=[^\s&]+",
    r"token=[^\s&]+",
    r"api[_-]?key=[^\s&]+",
    r"[A-Za-z0-9+/]{40,}={0,2}",  # base64-ish long strings
    r"acceptance-test-secret-key-must-be-32-chars",
]

# Protected audit file
PROTECTED_AUDIT_PATH = REPO_ROOT / "docs" / "reviews" / "wp-rec-03f-post-pr76-readiness-audit.md"
PROTECTED_AUDIT_SHA256 = "639a2529351bdacc606c6c5bbede44b82c73a7aefa26ae249bb592dec8e89657"

# Safe run-id pattern: alphanumeric, hyphens, underscores, dots only
SAFE_RUN_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,62}[a-zA-Z0-9]$|^[a-zA-Z0-9]$")


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
        patterns: Regex patterns to match. Uses DEFAULT_REDACTION_PATTERNS if None.

    Returns:
        Redacted content with all matched patterns replaced.
    """
    if patterns is None:
        patterns = DEFAULT_REDACTION_PATTERNS

    result = content
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
    """Capture current repository state for evidence."""
    state: dict[str, str] = {}
    for cmd_name, cmd in [
        ("head", ["git", "rev-parse", "HEAD"]),
        ("branch", ["git", "branch", "--show-current"]),
        ("status", ["git", "status", "--porcelain"]),
        ("diff_stat", ["git", "diff", "--stat"]),
        ("log_oneline", ["git", "log", "--oneline", "-5"]),
    ]:
        try:
            result = subprocess.run(
                cmd,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=10,
            )
            state[cmd_name] = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            state[cmd_name] = "[capture failed]"
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


# ---------------------------------------------------------------------------
# Evidence Collector
# ---------------------------------------------------------------------------


class EvidenceCollector:
    """Collects, redacts, and checksums formal-evidence artifacts.

    Lifecycle:
    1. Raw artifacts collected in raw/ during execution.
    2. After execution, redact all raw text artifacts to redacted/.
    3. Verify redaction (fail closed if secrets remain).
    4. Generate checksums for all redacted artifacts.
    5. Delete raw/ only after successful redaction and checksum.
    6. Write manifest.json describing all artifacts.
    """

    def __init__(self, evidence_dir: Path, run_id: str) -> None:
        self.evidence_dir = evidence_dir
        self.run_id = run_id
        self.raw_dir = evidence_dir / "raw"
        self.redacted_dir = evidence_dir / "redacted"
        self.artifacts: list[dict[str, str]] = []
        self._failure = False

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

    def collect_json(self, name: str, data: dict, source: str = "api") -> Path:
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
        self, scenario: str, correlation_id: str | None = None
    ) -> None:
        """Record scenario identity."""
        identity = {
            "run_id": self.run_id,
            "scenario": scenario,
            "correlation_id": correlation_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self.collect_json(
            f"scenarios/{scenario}/identity.json", identity, source="harness"
        )

    def collect_api_snapshot(
        self, scenario: str, name: str, data: dict
    ) -> None:
        """Capture an API response snapshot."""
        self.collect_json(
            f"scenarios/{scenario}/api/{name}.json", data, source="api"
        )

    def collect_test_results(
        self, scenario: str, test_type: str, exit_code: int, output: str
    ) -> None:
        """Capture test results."""
        self.collect_json(
            f"scenarios/{scenario}/tests/{test_type}.json",
            {"exit_code": exit_code, "output": output},
            source=test_type,
        )

    def redact_and_verify(self, patterns: list[str] | None = None) -> None:
        """Redact all raw artifacts, verify, and generate checksums.

        Raises AcceptanceHarnessError if redaction verification fails
        or if required evidence is missing.

        On success: raw/ is deleted, checksums.sha256 is written.
        On failure: raw/ is preserved for debugging.
        """
        if not list(self.raw_dir.rglob("*")):
            raise AcceptanceHarnessError(
                "No raw artifacts found — required evidence is missing"
            )

        # Redact all files from raw/ to redacted/
        redacted_files: list[Path] = []
        for src_file in sorted(self.raw_dir.rglob("*")):
            if not src_file.is_file():
                continue
            rel_path = src_file.relative_to(self.raw_dir)
            dst_file = self.redacted_dir / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            if src_file.suffix in (".png", ".jpg", ".jpeg", ".gif", ".zip", ".gz"):
                # Binary files: copy as-is (screenshots reviewed separately)
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

        # Verify redaction on all text files
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

        # Generate checksums
        try:
            write_checksums_file(self.redacted_dir)
        except AcceptanceHarnessError:
            self._failure = True
            raise

        # Write manifest
        self._write_manifest()

        # Success: remove raw artifacts
        shutil.rmtree(self.raw_dir)

    def _write_manifest(self) -> None:
        """Write deterministic manifest.json."""
        checksums = compute_checksums(self.redacted_dir)

        manifest = {
            "run_id": self.run_id,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "artifact_count": len(checksums),
            "artifacts": [
                {
                    "path": path,
                    "sha256": digest,
                    "source": next(
                        (a["source"] for a in self.artifacts if a["name"] == path),
                        "unknown",
                    ),
                }
                for path, digest in sorted(checksums.items())
            ],
        }

        manifest_path = self.redacted_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

        # Recompute checksums including the manifest
        # (checksums.sha256 is regenerated to include manifest.json)
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


class AcceptanceEnvironment:
    """Manages the isolated acceptance environment lifecycle."""

    def __init__(self, run_id: str, mode: str) -> None:
        self.run_id = run_id
        self.mode = mode
        self.evidence_dir = REPO_ROOT / "evidence" / run_id
        self.containers: list[str] = []
        self.processes: list[subprocess.Popen] = []

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
        backend_proc = subprocess.Popen(
            [
                str(VENV_BIN / "uvicorn"),
                "app.main:app",
                "--host", "0.0.0.0",
                "--port", str(ACCEPTANCE_BACKEND_PORT),
            ],
            cwd=BACKEND_DIR,
            env=env,
            stdout=open(log_backend, "w"),
            stderr=subprocess.STDOUT,
        )
        self.processes.append(backend_proc)
        wait_for_http(f"http://localhost:{ACCEPTANCE_BACKEND_PORT}/health")
        print(f"  Backend API started on port {ACCEPTANCE_BACKEND_PORT}")

        # ARQ worker — use python3.12 -m arq to avoid shebang picking up
        # system python3.14 which lacks the installed packages.
        log_worker = self.evidence_dir / "logs" / f"worker-{scenario}.log"
        worker_proc = subprocess.Popen(
            [str(VENV_BIN / "python3.12"), "-m", "arq", "app.worker.WorkerSettings"],
            cwd=BACKEND_DIR,
            env=env,
            stdout=open(log_worker, "w"),
            stderr=subprocess.STDOUT,
        )
        self.processes.append(worker_proc)
        # Wait for worker to connect and start polling
        time.sleep(5)  # Increased from 3 to 5 seconds
        print("  ARQ worker started")

        # Frontend dev server
        log_frontend = self.evidence_dir / "logs" / f"frontend-{scenario}.log"
        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = f"http://localhost:{ACCEPTANCE_BACKEND_PORT}/api/v1"
        frontend_proc = subprocess.Popen(
            ["npm", "run", "dev", "--", "--port", str(ACCEPTANCE_FRONTEND_PORT)],
            cwd=FRONTEND_DIR,
            env=frontend_env,
            stdout=open(log_frontend, "w"),
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
        time.sleep(2)  # Allow ports to be released

    def run_backend_tests(self, scenario: str) -> int:
        """Run backend integration tests for AT-008 or AT-013."""
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
        )
        return result.returncode

    def run_playwright_tests(self, scenario: str) -> int:
        """Run Playwright acceptance scenarios for the given scenario only."""
        print(f"[{self.run_id}] Running Playwright acceptance tests for {scenario}...")
        env = os.environ.copy()
        env["PLAYWRIGHT_ACCEPTANCE_BASE_URL"] = ACCEPTANCE_FRONTEND_URL
        env["ACCEPTANCE_FRONTEND_PORT"] = str(ACCEPTANCE_FRONTEND_PORT)

        # Map scenario to its specific spec file so only the matching
        # acceptance test runs for each scenario's service configuration.
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
        )
        return result.returncode

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

            backend_rc = env.run_backend_tests(scenario)
            if backend_rc != 0:
                print(f"Backend tests failed for {scenario} (exit code {backend_rc})")
                return backend_rc

            playwright_rc = env.run_playwright_tests(scenario)
            if playwright_rc != 0:
                print(f"Playwright tests failed for {scenario} (exit code {playwright_rc})")
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


def run_formal_mode(run_id: str) -> int:
    """Execute Phase C formal-evidence collection mode.

    Runs both deterministic scenarios sequentially, collects complete
    evidence, redacts secrets, generates checksums, and writes a manifest.

    Does NOT declare AT-008 or AT-013 PASS — that belongs to Phase D.
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

    try:
        env.setup()
        collector.collect_versions()

        scenarios = ["AT008_INVALID_OUTPUT", "AT013_OUTAGE_UNTIL_RETRY"]

        for scenario in scenarios:
            print(f"\n{'='*70}")
            print(f"[FORMAL] Scenario: {scenario}")
            print('='*70)

            collector.collect_scenario_identity(scenario)

            env.start_services(scenario)

            # Run backend tests and capture output
            backend_rc = env.run_backend_tests(scenario)
            collector.collect_test_results(
                scenario, "backend", backend_rc,
                f"pytest exit code: {backend_rc}"
            )

            if backend_rc != 0:
                print(f"Backend tests failed for {scenario} (exit code {backend_rc})")
                # Still collect remaining evidence before failing
                collector.collect_repository_final()
                try:
                    collector.redact_and_verify()
                except AcceptanceHarnessError:
                    pass  # Raw preserved on failure
                return backend_rc

            # Run Playwright tests
            playwright_rc = env.run_playwright_tests(scenario)
            collector.collect_test_results(
                scenario, "playwright", playwright_rc,
                f"playwright exit code: {playwright_rc}"
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
                collector.collect_repository_final()
                try:
                    collector.redact_and_verify()
                except AcceptanceHarnessError:
                    pass
                return playwright_rc

            env.stop_services()

        # Post-execution: verify repository hasn't changed (tracked files)
        final_git = capture_git_state()
        collector.collect_json("repository/final.json", final_git, source="git")

        # Verify tracked files haven't changed during execution
        if baseline_git.get("diff_stat") != final_git.get("diff_stat"):
            raise AcceptanceHarnessError(
                "Tracked repository files changed during formal execution"
            )

        # Re-verify protected audit
        verify_protected_audit()

        # Copy service logs to raw artifacts
        logs_dir = evidence_dir / "logs"
        if logs_dir.exists():
            for log_file in logs_dir.iterdir():
                if log_file.is_file():
                    collector.collect_file(
                        log_file, f"logs/{log_file.name}", source="service-log"
                    )

        # Redact, verify, checksum, cleanup
        print(f"\n[{run_id}] Redacting and verifying evidence...")
        collector.redact_and_verify()

        print(f"\n[{run_id}] Formal evidence collection complete.")
        print(f"Evidence directory: {evidence_dir / 'redacted'}")
        print("NOTE: Scenario execution succeeded. Evidence completeness verified.")
        print("AT-008 and AT-013 formal PASS declarations require Phase D review.")
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
