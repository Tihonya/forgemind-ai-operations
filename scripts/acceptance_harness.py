#!/usr/bin/env python3
"""WP-REC-03H acceptance harness orchestration script (Phase B/C).

Manages an isolated acceptance environment:
- Dedicated PostgreSQL (forgemind_acceptance, port 5433)
- Dedicated Redis (port 6380)
- Backend API + ARQ worker + frontend dev server
- Backend integration tests + Playwright acceptance tests
- Evidence collection (Phase C only)

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
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

# Repository root (parent of scripts/).
REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"

# Acceptance environment ports and database.
ACCEPTANCE_PG_PORT = 5433
ACCEPTANCE_REDIS_PORT = 6380
ACCEPTANCE_DB_NAME = "forgemind_acceptance"
ACCEPTANCE_DB_USER = "forgemind"
ACCEPTANCE_DB_PASSWORD = "forgemind"
ACCEPTANCE_BACKEND_PORT = 8001
ACCEPTANCE_FRONTEND_PORT = 5174

ACCEPTANCE_DATABASE_URL = (
    f"postgresql+asyncpg://{ACCEPTANCE_DB_USER}:{ACCEPTANCE_DB_PASSWORD}"
    f"@localhost:{ACCEPTANCE_PG_PORT}/{ACCEPTANCE_DB_NAME}"
)
ACCEPTANCE_REDIS_URL = f"redis://localhost:{ACCEPTANCE_REDIS_PORT}/0"


class AcceptanceHarnessError(Exception):
    """Base error for acceptance harness failures."""


def validate_acceptance_database_url(db_url: str) -> None:
    """Fail-closed validation of acceptance database URL."""
    parsed = urlparse(db_url)

    if parsed.hostname not in ("localhost", "127.0.0.1"):
        raise AcceptanceHarnessError(
            f"Acceptance DB host must be localhost, got {parsed.hostname}"
        )

    if parsed.port == 5432:
        raise AcceptanceHarnessError(
            "Acceptance DB must not use development port 5432"
        )

    db_name = parsed.path.lstrip("/")
    if db_name != ACCEPTANCE_DB_NAME:
        raise AcceptanceHarnessError(
            f"Acceptance DB name must be '{ACCEPTANCE_DB_NAME}', got '{db_name}'"
        )

    if "production" in db_url or "staging" in db_url:
        raise AcceptanceHarnessError(
            "Acceptance DB URL must not reference production or staging"
        )


def validate_acceptance_redis_url(redis_url: str) -> None:
    """Fail-closed validation of acceptance Redis URL."""
    parsed = urlparse(redis_url)

    if parsed.scheme not in ("redis", "rediss"):
        raise AcceptanceHarnessError(
            f"Acceptance Redis scheme must be redis:// or rediss://, got {parsed.scheme}"
        )

    if parsed.hostname not in ("localhost", "127.0.0.1"):
        raise AcceptanceHarnessError(
            f"Acceptance Redis host must be localhost, got {parsed.hostname}"
        )

    if parsed.port == 6379:
        raise AcceptanceHarnessError(
            "Acceptance Redis must not use development port 6379"
        )

    if parsed.port != ACCEPTANCE_REDIS_PORT:
        raise AcceptanceHarnessError(
            f"Acceptance Redis port must be {ACCEPTANCE_REDIS_PORT}, got {parsed.port}"
        )

    if "production" in redis_url or "staging" in redis_url:
        raise AcceptanceHarnessError(
            "Acceptance Redis URL must not reference production or staging"
        )


def check_port_available(port: int) -> bool:
    """Check if a port is available for binding."""
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
    raise AcceptanceHarnessError(
        f"PostgreSQL on port {port} did not become ready within {timeout}s"
    )


def wait_for_redis(port: int, timeout: int = 10) -> None:
    """Poll redis-cli ping until Redis is ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            ["redis-cli", "-p", str(port), "ping"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and "PONG" in result.stdout:
            return
        time.sleep(1)
    raise AcceptanceHarnessError(
        f"Redis on port {port} did not become ready within {timeout}s"
    )


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
    raise AcceptanceHarnessError(
        f"HTTP endpoint {url} did not become ready within {timeout}s"
    )


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

        # Validate URLs.
        validate_acceptance_database_url(ACCEPTANCE_DATABASE_URL)
        validate_acceptance_redis_url(ACCEPTANCE_REDIS_URL)

        # Check ports.
        if not check_port_available(ACCEPTANCE_PG_PORT):
            raise AcceptanceHarnessError(
                f"Port {ACCEPTANCE_PG_PORT} is already in use"
            )
        if not check_port_available(ACCEPTANCE_REDIS_PORT):
            raise AcceptanceHarnessError(
                f"Port {ACCEPTANCE_REDIS_PORT} is already in use"
            )

        # Create evidence directory.
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        (self.evidence_dir / "logs").mkdir(exist_ok=True)

        # Start PostgreSQL.
        pg_container = f"forgemind-{self.run_id}-pg"
        print(f"  Starting PostgreSQL container: {pg_container}")
        subprocess.run(
            [
                "docker", "run", "-d",
                "--name", pg_container,
                "--label", f"forgemind-run={self.run_id}",
                "-p", f"{ACCEPTANCE_PG_PORT}:5432",
                "-e", f"POSTGRES_DB={ACCEPTANCE_DB_NAME}",
                "-e", f"POSTGRES_USER={ACCEPTANCE_DB_USER}",
                "-e", f"POSTGRES_PASSWORD={ACCEPTANCE_DB_PASSWORD}",
                "postgres:16",
            ],
            check=True,
            capture_output=True,
        )
        self.containers.append(pg_container)
        wait_for_postgres(ACCEPTANCE_PG_PORT)

        # Start Redis.
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

        # Prepare database (migrations + seed).
        print("  Running Alembic migrations...")
        env = os.environ.copy()
        env["DATABASE_URL"] = ACCEPTANCE_DATABASE_URL
        subprocess.run(
            ["../.venv/bin/alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
            capture_output=True,
        )

        print("  Running seed generator...")
        subprocess.run(
            ["../.venv/bin/python", "-m", "app.seed.generator.main"],
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

        # Backend API.
        log_backend = self.evidence_dir / "logs" / "backend.log"
        backend_proc = subprocess.Popen(
            [
                "../.venv/bin/uvicorn",
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

        # ARQ worker.
        log_worker = self.evidence_dir / "logs" / "worker.log"
        worker_proc = subprocess.Popen(
            ["../.venv/bin/arq", "app.worker.WorkerSettings"],
            cwd=BACKEND_DIR,
            env=env,
            stdout=open(log_worker, "w"),
            stderr=subprocess.STDOUT,
        )
        self.processes.append(worker_proc)
        time.sleep(3)  # Allow worker to connect.
        print("  ARQ worker started")

        # Frontend dev server.
        log_frontend = self.evidence_dir / "logs" / "frontend.log"
        frontend_env = os.environ.copy()
        frontend_env["VITE_API_BASE_URL"] = f"http://localhost:{ACCEPTANCE_BACKEND_PORT}"
        frontend_proc = subprocess.Popen(
            ["npm", "run", "dev", "--", "--port", str(ACCEPTANCE_FRONTEND_PORT)],
            cwd=FRONTEND_DIR,
            env=frontend_env,
            stdout=open(log_frontend, "w"),
            stderr=subprocess.STDOUT,
        )
        self.processes.append(frontend_proc)
        wait_for_http(f"http://localhost:{ACCEPTANCE_FRONTEND_PORT}")
        print(f"  Frontend dev server started on port {ACCEPTANCE_FRONTEND_PORT}")

    def run_backend_tests(self) -> int:
        """Run backend integration tests for AT-008 and AT-013."""
        print(f"[{self.run_id}] Running backend acceptance tests...")
        env = os.environ.copy()
        env["DATABASE_URL"] = ACCEPTANCE_DATABASE_URL
        env["REDIS_URL"] = ACCEPTANCE_REDIS_URL

        result = subprocess.run(
            [
                "../.venv/bin/pytest",
                "tests/integration/test_at008_acceptance.py",
                "tests/integration/test_at013_acceptance.py",
                "-v",
            ],
            cwd=BACKEND_DIR,
            env=env,
        )
        return result.returncode

    def run_playwright_tests(self) -> int:
        """Run Playwright acceptance scenarios."""
        print(f"[{self.run_id}] Running Playwright acceptance tests...")
        env = os.environ.copy()
        env["PLAYWRIGHT_ACCEPTANCE_BASE_URL"] = (
            f"http://localhost:{ACCEPTANCE_FRONTEND_PORT}"
        )

        result = subprocess.run(
            [
                "npx", "playwright", "test",
                "--config=playwright.acceptance.config.ts",
            ],
            cwd=FRONTEND_DIR,
            env=env,
        )
        return result.returncode

    def teardown(self) -> None:
        """Stop processes and remove owned containers."""
        print(f"[{self.run_id}] Tearing down environment...")

        # Stop subprocesses.
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()

        # Remove owned containers.
        for container in self.containers:
            # Verify ownership via label.
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

        # For Phase B verification, run tests with AT008_INVALID_OUTPUT scenario.
        # AT-013 tests use OutageUntilRetryProvider directly in the test code.
        env.start_services(scenario="AT008_INVALID_OUTPUT")

        backend_rc = env.run_backend_tests()
        if backend_rc != 0:
            print(f"Backend tests failed (exit code {backend_rc})")
            return backend_rc

        # Playwright tests are optional for Phase B (require full UI flow).
        # Skip if the UI does not yet have the required data-testid attributes.
        print(
            "Note: Playwright acceptance tests are defined for Phase C. "
            "Skipping in Phase B verification mode."
        )

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
