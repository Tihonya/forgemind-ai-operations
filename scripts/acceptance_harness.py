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
"""

from __future__ import annotations

import argparse
import os
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
    args = parser.parse_args()

    if args.mode == "formal":
        print(
            "ERROR: --mode=formal requires separate Product Owner authorization. "
            "This script currently supports only --mode=verify (Phase B).",
            file=sys.stderr,
        )
        return 1

    run_id = f"acc-{uuid.uuid4().hex[:12]}"
    env = AcceptanceEnvironment(run_id=run_id, mode=args.mode)

    try:
        env.setup()

        # Phase B verification: run both scenarios sequentially
        scenarios = ["AT008_INVALID_OUTPUT", "AT013_OUTAGE_UNTIL_RETRY"]

        for scenario in scenarios:
            print(f"\n{'='*70}")
            print(f"Scenario: {scenario}")
            print('='*70)

            # Start services with this scenario
            env.start_services(scenario)

            # Run backend tests
            backend_rc = env.run_backend_tests(scenario)
            if backend_rc != 0:
                print(f"Backend tests failed for {scenario} (exit code {backend_rc})")
                return backend_rc

            # Run Playwright tests
            playwright_rc = env.run_playwright_tests(scenario)
            if playwright_rc != 0:
                print(f"Playwright tests failed for {scenario} (exit code {playwright_rc})")
                return playwright_rc

            # Stop services before next scenario
            env.stop_services()

        print(f"\n[{run_id}] Phase B verification complete.")
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


if __name__ == "__main__":
    sys.exit(main())
