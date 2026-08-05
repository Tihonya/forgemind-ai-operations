"""
WP-AL-1C2: Deterministic reviewer adapter.

Constructs schema-valid review-request.json, invokes reviewer subprocess,
validates output, and publishes canonical review-result.json with exact
identity binding.

Public API:
  run_review() -> ReviewAdapterResult

CLI entry point:
  python3 review_adapter.py --repo-root <path> --run-dir <path> ...

No orchestration wiring, no repair contract, no real LLM integration.
Fully typed, stdlib preferred, ruff/mypy --strict clean.
No internal time calls, no random values, no network, no shell=True.
Deterministic output, no secret leakage, no absolute-path leakage in diagnostics.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Narrow import contract from failure_context.py (approved public API)
sys.path.insert(0, str(Path(__file__).parent))
from failure_context import redact_text

# Narrow import contract from review_contract.py (approved public API)
from review_contract import (
    ReviewContractError,
    build_review_request,
    validate_review_result,
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ReviewAdapterResult:
    """
    Typed result from run_review.

    status: "OK" or "ERROR"
    error_code: empty string when OK; one of the error taxonomy codes when ERROR
    error_detail: human-readable sanitized detail (no secrets, no absolute paths)
    request_path: absolute path to review-request.json
    result_path: absolute path to review-result.json (None if not published)
    reviewer_stdout: bounded sanitized stdout (max 4096 bytes)
    reviewer_stderr: bounded sanitized stderr (max 4096 bytes)
    reviewer_exit_code: reviewer process exit code (None if not started)
    timeout_occurred: True if reviewer was terminated due to timeout
    """

    status: str
    error_code: str
    error_detail: str
    request_path: Path
    result_path: Path | None
    reviewer_stdout: str
    reviewer_stderr: str
    reviewer_exit_code: int | None
    timeout_occurred: bool


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PYTHON_INTERPRETER_RE = re.compile(r"^python3?(?:\.\d+)?$")
MAX_COMMAND_ELEMENTS = 10
MAX_COMMAND_ENCODED_LENGTH = 8192
MAX_OUTPUT_SIZE = 1_000_000  # 1 MB
MAX_DIAGNOSTIC_SIZE = 4096
MAX_ERROR_DETAIL_SIZE = 1024
MIN_TIMEOUT = 1
MAX_TIMEOUT = 600
DEFAULT_TIMEOUT = 30
TERMINATION_GRACE = 5


# ---------------------------------------------------------------------------
# Command validation
# ---------------------------------------------------------------------------
def _validate_command_sequence(
    reviewer_command: Sequence[str],
    repo_root: Path,
) -> tuple[Path, list[str]]:
    """
    Validate reviewer_command sequence and resolve executable.

    Returns (resolved_executable_path, full_command_list).

    Raises ValueError on validation failure.
    """
    # Sequence constraints
    if not reviewer_command:
        raise ValueError("reviewer_command is empty")

    if len(reviewer_command) > MAX_COMMAND_ELEMENTS:
        raise ValueError(f"reviewer_command exceeds {MAX_COMMAND_ELEMENTS} elements")

    # Check each element
    for i, elem in enumerate(reviewer_command):
        if not isinstance(elem, str):
            raise TypeError(f"reviewer_command[{i}] is not a string")
        if not elem:
            raise ValueError(f"reviewer_command[{i}] is empty")
        if "\x00" in elem:
            raise ValueError(f"reviewer_command[{i}] contains null byte")
        if "\r" in elem or "\n" in elem:
            raise ValueError(f"reviewer_command[{i}] contains CR/LF")

    # Total encoded length
    total_encoded = len("".join(reviewer_command).encode("utf-8"))
    if total_encoded > MAX_COMMAND_ENCODED_LENGTH:
        raise ValueError(f"reviewer_command total encoded length exceeds {MAX_COMMAND_ENCODED_LENGTH} bytes")

    # Reserved flag collision (before adapter-appended --request/--output)
    for i, elem in enumerate(reviewer_command):
        if elem in ("--request", "--output"):
            raise ValueError(f"reviewer_command[{i}] is reserved flag: {elem}")
        if elem.startswith(("--request=", "--output=")):
            raise ValueError(f"reviewer_command[{i}] is reserved flag prefix")

    # Credential-bearing fixed argument detection (simplified: check for common patterns)
    for i, elem in enumerate(reviewer_command):
        _redacted, count = redact_text(elem)
        if count > 0:
            raise ValueError(f"reviewer_command[{i}] contains credential-like pattern")

    # Resolve executable
    argv0 = reviewer_command[0]

    if "/" in argv0 or "\\" in argv0:
        # Absolute or relative path: reject symlinks per planning §13
        if os.path.islink(argv0):
            raise ValueError(f"executable is symlink: {Path(argv0).name}")
        exe_path = Path(argv0).resolve()
    else:
        # Simple executable name: use shutil.which with minimal PATH
        minimal_path = "/usr/local/bin:/usr/bin:/bin"
        resolved = shutil.which(argv0, path=minimal_path)
        if resolved is None:
            raise ValueError(f"executable not found in minimal PATH: {argv0}")
        exe_path = Path(resolved).resolve()

    # Executable validation
    if not exe_path.exists():
        raise ValueError(f"executable does not exist: {exe_path.name}")

    try:
        exe_stat = exe_path.stat()
    except OSError as e:
        raise ValueError(f"cannot stat executable: {e}")

    if not stat.S_ISREG(exe_stat.st_mode):
        raise ValueError(f"executable is not regular file: {exe_path.name}")

    if not os.access(exe_path, os.X_OK):
        raise ValueError(f"executable is not executable: {exe_path.name}")

    # Python interpreter script argument validation
    exe_basename = exe_path.name
    if PYTHON_INTERPRETER_RE.match(exe_basename):
        # First fixed non-option argument is reviewer script path
        script_arg = None
        for i, elem in enumerate(reviewer_command[1:], start=1):
            if not elem.startswith("-"):
                script_arg = elem
                break

        if script_arg is None:
            raise ValueError("Python interpreter requires script path argument")

        # Check if it's a symlink BEFORE resolving
        if os.path.islink(script_arg):
            raise ValueError(f"reviewer script is symlink: {Path(script_arg).name}")

        script_path = Path(script_arg).resolve()

        # Script path validation
        if not script_path.exists():
            raise ValueError(f"reviewer script does not exist: {script_path.name}")

        try:
            script_stat = script_path.stat()
        except OSError as e:
            raise ValueError(f"cannot stat reviewer script: {e}")

        if not stat.S_ISREG(script_stat.st_mode):
            raise ValueError(f"reviewer script is not regular file: {script_path.name}")

        # Containment check: must resolve beneath repo_root
        repo_root_resolved = repo_root.resolve()
        try:
            script_path.relative_to(repo_root_resolved)
        except ValueError:
            raise ValueError(f"reviewer script escapes repo_root: {script_path.name}")

    # Build full command list
    full_command = [str(exe_path)] + list(reviewer_command[1:])

    return exe_path, full_command


# ---------------------------------------------------------------------------
# Environment construction
# ---------------------------------------------------------------------------
def _build_minimal_env(run_dir: Path) -> dict[str, str]:
    """
    Build deterministic minimal environment for reviewer subprocess.

    No inherited values. Explicit allowlist only.
    """
    reviewer_home = run_dir / ".reviewer-home"
    reviewer_tmp = run_dir / "tmp"

    # Create directories with mode 0o700
    reviewer_home.mkdir(parents=True, exist_ok=True)
    reviewer_tmp.mkdir(parents=True, exist_ok=True)

    # Enforce mode 0o700
    os.chmod(reviewer_home, 0o700)
    os.chmod(reviewer_tmp, 0o700)

    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(reviewer_home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(reviewer_tmp),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


# ---------------------------------------------------------------------------
# Filesystem safety
# ---------------------------------------------------------------------------
def _validate_output_path_safety(path: Path, run_dir: Path) -> None:
    """
    Validate output path safety before reviewer invocation.

    Raises ValueError on unsafe path.
    """
    # Containment check
    run_dir_resolved = run_dir.resolve()
    try:
        path.resolve().relative_to(run_dir_resolved)
    except ValueError:
        raise ValueError(f"output path escapes run_dir: {path.name}")

    # Pre-existing path checks
    if path.exists() or path.is_symlink():
        try:
            # Use lstat to detect symlinks without following them
            path_stat = path.lstat()
        except OSError as e:
            raise ValueError(f"cannot stat output path: {e}")

        if stat.S_ISLNK(path_stat.st_mode):
            raise ValueError(f"output path is symlink: {path.name}")

        # Now check the resolved file
        if not path.exists():
            raise ValueError(f"output path symlink target does not exist: {path.name}")

        try:
            resolved_stat = path.stat()
        except OSError as e:
            raise ValueError(f"cannot stat output path target: {e}")

        if not stat.S_ISREG(resolved_stat.st_mode):
            if stat.S_ISFIFO(resolved_stat.st_mode):
                raise ValueError(f"output path is FIFO: {path.name}")
            if stat.S_ISSOCK(resolved_stat.st_mode):
                raise ValueError(f"output path is socket: {path.name}")
            if stat.S_ISBLK(resolved_stat.st_mode):
                raise ValueError(f"output path is block device: {path.name}")
            if stat.S_ISCHR(resolved_stat.st_mode):
                raise ValueError(f"output path is character device: {path.name}")
            if stat.S_ISDIR(resolved_stat.st_mode):
                raise ValueError(f"output path is directory: {path.name}")
            raise ValueError(f"output path is not regular file: {path.name}")

        # Hard-link count check
        if resolved_stat.st_nlink > 1:
            raise ValueError(f"output path hard-link count > 1: {path.name}")


# ---------------------------------------------------------------------------
# Lock management
# ---------------------------------------------------------------------------
def _acquire_lock(lock_path: Path, run_id: str) -> bool:
    """
    Acquire adapter lock atomically.

    Returns True if lock acquired, False if concurrent invocation.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    pid = os.getpid()
    lock_content = f"{pid}\n{run_id}\n"

    try:
        # Exclusive creation
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, lock_content.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        # Lock exists: check if stale
        try:
            with open(lock_path, "r", encoding="utf-8") as f:
                lines = f.read().strip().split("\n")
            if len(lines) != 2:
                return False  # Malformed lock

            stored_pid = int(lines[0])
            stored_run_id = lines[1]

            # Check if PID is running
            try:
                os.kill(stored_pid, 0)
                # PID exists and is running
                return False
            except OSError:
                # PID not running: stale lock
                # Check run_id match
                if stored_run_id != run_id:
                    return False  # Different run: concurrent invocation

                # Stale lock with matching run_id: remove and retry
                os.unlink(lock_path)
                return _acquire_lock(lock_path, run_id)
        except (OSError, ValueError):
            return False


def _release_lock(lock_path: Path, owned: bool) -> None:
    """Release adapter lock if owned."""
    if owned and lock_path.exists():
        try:
            os.unlink(lock_path)
        except OSError:
            pass  # Best-effort cleanup


# ---------------------------------------------------------------------------
# Diagnostic helpers
# ---------------------------------------------------------------------------
def _sanitize_text(text: str, max_bytes: int = MAX_DIAGNOSTIC_SIZE) -> str:
    """Sanitize and bound text for diagnostics."""
    redacted, _ = redact_text(text)
    # Truncate to max_bytes
    encoded = redacted.encode("utf-8")
    if len(encoded) > max_bytes:
        encoded = encoded[:max_bytes]
        redacted = encoded.decode("utf-8", errors="ignore")
    return redacted


def _sanitize_error_detail(text: str) -> str:
    """Sanitize error_detail: no absolute paths, bounded."""
    # Remove absolute paths (simplified: replace common prefixes)
    text = re.sub(r"/[^\s]+", "<path>", text)
    return _sanitize_text(text, MAX_ERROR_DETAIL_SIZE)


def _read_bounded_stream(path: Path, max_bytes: int = MAX_DIAGNOSTIC_SIZE) -> str:
    """Read bounded bytes from stream file, decode UTF-8, sanitize."""
    if not path.exists():
        return ""
    try:
        with open(path, "rb") as f:
            data = f.read(max_bytes)
        return _sanitize_text(data.decode("utf-8", errors="replace"), max_bytes)
    except (OSError, UnicodeDecodeError):
        return ""


def _write_diagnostic_file(path: Path, content: str) -> None:
    """Write diagnostic file with mode 0o600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(path, 0o600)
    except OSError:
        pass  # Best-effort


# ---------------------------------------------------------------------------
# Atomic write helpers
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomically write JSON to path via tmp + os.replace."""
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    # Create temp file with PID to avoid collision
    pid = os.getpid()
    tmp_path = parent / f".{path.name}-tmp-{pid}"

    try:
        # Exclusive creation
        fd = os.open(str(tmp_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except (OSError, AttributeError):
                pass

        # Re-check destination safety before replace
        if path.exists():
            _validate_output_path_safety(path, path.parent)

        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


# ---------------------------------------------------------------------------
# Result binding check
# ---------------------------------------------------------------------------
def _check_result_binding(request: dict[str, Any], result: dict[str, Any]) -> None:
    """
    Check exact binding between request and result.

    Raises ReviewContractError on mismatch.
    """
    for field in ("run_id", "story_id", "review_iteration", "repair_iteration", "reviewer_id"):
        if result.get(field) != request.get(field):
            raise ReviewContractError(
                f"result.{field} ({result.get(field)}) does not match request.{field} ({request.get(field)})"
            )


# ---------------------------------------------------------------------------
# Main adapter function
# ---------------------------------------------------------------------------
def run_review(
    *,
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
    reviewer_command: Sequence[str],
    timeout_seconds: int = DEFAULT_TIMEOUT,
) -> ReviewAdapterResult:
    """
    Run the reviewer adapter.

    Keyword-only arguments:
        repo_root: repository root directory
        run_dir: current run's artifact directory
        manifest_path: absolute path to story manifest (under repo_root)
        failure_context_path: absolute path to failure-context.json (under run_dir)
        run_id: run identifier (supplied by caller)
        story_id: story identifier (supplied by caller)
        review_iteration: integer >= 1 (supplied by caller)
        repair_iteration: integer >= 0 (supplied by caller)
        triggered_by: "initial_verify_pass" or "post_repair_verify_pass"
        generated_at: ISO-8601 UTC timestamp (required, no internal time call)
        reviewer_id: reviewer identifier (required, no default)
        reviewer_command: executable + fixed safe arguments (Sequence[str])
        timeout_seconds: integer 1-600 inclusive, default 30

    Adapter appends to reviewer_command:
        --request <request_path>
        --output <output_path>

    Returns:
        ReviewAdapterResult with status, diagnostics, and paths

    Side effects:
        - Writes $run_dir/review/review-request.json atomically
        - Invokes reviewer subprocess (no shell=True)
        - Reads $run_dir/review/reviewer-output.json
        - Writes $run_dir/reports/review-result.json atomically (on success)
        - Preserves bounded diagnostics in result
    """
    # Paths
    review_dir = run_dir / "review"
    reports_dir = run_dir / "reports"
    request_path = review_dir / "review-request.json"
    output_path = review_dir / "reviewer-output.json"
    result_path = reports_dir / "review-result.json"
    lock_path = review_dir / ".adapter.lock"

    # Initialize result fields
    status = "ERROR"
    error_code = ""
    error_detail = ""
    result_path_final: Path | None = None
    reviewer_stdout = ""
    reviewer_stderr = ""
    reviewer_exit_code: int | None = None
    timeout_occurred = False

    # Timeout validation
    if not isinstance(timeout_seconds, int) or timeout_seconds < MIN_TIMEOUT or timeout_seconds > MAX_TIMEOUT:
        error_code = "INVALID_TIMEOUT"
        error_detail = f"timeout_seconds must be integer {MIN_TIMEOUT}-{MAX_TIMEOUT}, got {timeout_seconds}"
        return ReviewAdapterResult(
            status=status,
            error_code=error_code,
            error_detail=_sanitize_error_detail(error_detail),
            request_path=request_path,
            result_path=result_path_final,
            reviewer_stdout=reviewer_stdout,
            reviewer_stderr=reviewer_stderr,
            reviewer_exit_code=reviewer_exit_code,
            timeout_occurred=timeout_occurred,
        )

    # Build review request
    try:
        request_data = build_review_request(
            repo_root=repo_root,
            run_dir=run_dir,
            manifest_path=manifest_path,
            failure_context_path=failure_context_path,
            run_id=run_id,
            story_id=story_id,
            review_iteration=review_iteration,
            repair_iteration=repair_iteration,
            triggered_by=triggered_by,
            generated_at=generated_at,
            reviewer_id=reviewer_id,
        )
    except (ReviewContractError, FileNotFoundError, json.JSONDecodeError, OSError) as e:
        error_code = "REQUEST_BUILD_FAILED"
        error_detail = f"build_review_request failed: {e}"
        return ReviewAdapterResult(
            status=status,
            error_code=error_code,
            error_detail=_sanitize_error_detail(error_detail),
            request_path=request_path,
            result_path=result_path_final,
            reviewer_stdout=reviewer_stdout,
            reviewer_stderr=reviewer_stderr,
            reviewer_exit_code=reviewer_exit_code,
            timeout_occurred=timeout_occurred,
        )

    # Write request atomically
    try:
        review_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(request_path, request_data)
    except OSError as e:
        error_code = "ATOMIC_PUBLICATION_FAILED"
        error_detail = f"cannot write request: {e}"
        return ReviewAdapterResult(
            status=status,
            error_code=error_code,
            error_detail=_sanitize_error_detail(error_detail),
            request_path=request_path,
            result_path=result_path_final,
            reviewer_stdout=reviewer_stdout,
            reviewer_stderr=reviewer_stderr,
            reviewer_exit_code=reviewer_exit_code,
            timeout_occurred=timeout_occurred,
        )

    # Validate command
    try:
        _exe_path, command_prefix = _validate_command_sequence(reviewer_command, repo_root)
    except (ValueError, TypeError) as e:
        # Distinguish EXECUTABLE_NOT_FOUND vs EXECUTABLE_NOT_ALLOWED
        err_msg = str(e)
        if "executable not found" in err_msg:
            error_code = "EXECUTABLE_NOT_FOUND"
        else:
            error_code = "EXECUTABLE_NOT_ALLOWED"
        error_detail = err_msg
        return ReviewAdapterResult(
            status=status,
            error_code=error_code,
            error_detail=_sanitize_error_detail(error_detail),
            request_path=request_path,
            result_path=result_path_final,
            reviewer_stdout=reviewer_stdout,
            reviewer_stderr=reviewer_stderr,
            reviewer_exit_code=reviewer_exit_code,
            timeout_occurred=timeout_occurred,
        )

    # Validate output path safety
    try:
        _validate_output_path_safety(output_path, run_dir)
    except ValueError as e:
        error_code = "UNSAFE_OUTPUT_PATH"
        error_detail = str(e)
        return ReviewAdapterResult(
            status=status,
            error_code=error_code,
            error_detail=_sanitize_error_detail(error_detail),
            request_path=request_path,
            result_path=result_path_final,
            reviewer_stdout=reviewer_stdout,
            reviewer_stderr=reviewer_stderr,
            reviewer_exit_code=reviewer_exit_code,
            timeout_occurred=timeout_occurred,
        )

    # Acquire lock
    lock_owned = _acquire_lock(lock_path, run_id)
    if not lock_owned:
        error_code = "CONCURRENT_INVOCATION"
        error_detail = "adapter lock already held"
        return ReviewAdapterResult(
            status=status,
            error_code=error_code,
            error_detail=_sanitize_error_detail(error_detail),
            request_path=request_path,
            result_path=result_path_final,
            reviewer_stdout=reviewer_stdout,
            reviewer_stderr=reviewer_stderr,
            reviewer_exit_code=reviewer_exit_code,
            timeout_occurred=timeout_occurred,
        )

    try:
        # Build full command with --request and --output
        full_command = command_prefix + ["--request", str(request_path), "--output", str(output_path)]

        # Build minimal environment
        minimal_env = _build_minimal_env(run_dir)

        # Temporary stream files
        stdout_tmp = review_dir / ".reviewer-stdout-tmp"
        stderr_tmp = review_dir / ".reviewer-stderr-tmp"

        # Create stream files with exclusive mode 0o600
        try:
            stdout_fd = os.open(str(stdout_tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            stderr_fd = os.open(str(stderr_tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            # Clean up existing temp files
            if stdout_tmp.exists():
                os.unlink(stdout_tmp)
            if stderr_tmp.exists():
                os.unlink(stderr_tmp)
            stdout_fd = os.open(str(stdout_tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            stderr_fd = os.open(str(stderr_tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

        # Spawn subprocess
        try:
            proc = subprocess.Popen(
                full_command,
                stdout=stdout_fd,
                stderr=stderr_fd,
                start_new_session=True,
                env=minimal_env,
                cwd=str(run_dir),
                pass_fds=(stdout_fd, stderr_fd),
            )
        finally:
            os.close(stdout_fd)
            os.close(stderr_fd)

        # Wait for completion or timeout
        termination_failed = False
        try:
            proc.wait(timeout=timeout_seconds)
            timeout_occurred = False
        except subprocess.TimeoutExpired:
            timeout_occurred = True
            # Terminate process group
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
            try:
                proc.wait(timeout=TERMINATION_GRACE)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
                proc.wait()
                # Check if process is still alive after SIGKILL
                try:
                    os.kill(proc.pid, 0)
                    # Process still exists - termination failed
                    termination_failed = True
                except (OSError, ProcessLookupError):
                    # Process is gone - normal
                    pass

        reviewer_exit_code = proc.returncode

        # Read bounded streams
        reviewer_stdout = _read_bounded_stream(stdout_tmp)
        reviewer_stderr = _read_bounded_stream(stderr_tmp)

        # Clean up temp stream files
        if stdout_tmp.exists():
            try:
                os.unlink(stdout_tmp)
            except OSError:
                pass
        if stderr_tmp.exists():
            try:
                os.unlink(stderr_tmp)
            except OSError:
                pass

        # Check timeout
        if timeout_occurred:
            if termination_failed:
                error_code = "TERMINATION_FAILED"
                error_detail = "reviewer process could not be terminated after SIGKILL"
            else:
                error_code = "TIMEOUT"
                error_detail = f"reviewer exceeded {timeout_seconds}s timeout"
            # Write diagnostic files
            _write_diagnostic_file(review_dir / ".reviewer-stdout.log", reviewer_stdout)
            _write_diagnostic_file(review_dir / ".reviewer-stderr.log", reviewer_stderr)
            # Clean up output if exists
            if output_path.exists():
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
            return ReviewAdapterResult(
                status=status,
                error_code=error_code,
                error_detail=_sanitize_error_detail(error_detail),
                request_path=request_path,
                result_path=result_path_final,
                reviewer_stdout=reviewer_stdout,
                reviewer_stderr=reviewer_stderr,
                reviewer_exit_code=reviewer_exit_code,
                timeout_occurred=timeout_occurred,
            )

        # Check non-zero exit
        if reviewer_exit_code != 0:
            error_code = "NON_ZERO_EXIT"
            error_detail = f"reviewer exited with code {reviewer_exit_code}"
            # Write diagnostic files
            _write_diagnostic_file(review_dir / ".reviewer-stdout.log", reviewer_stdout)
            _write_diagnostic_file(review_dir / ".reviewer-stderr.log", reviewer_stderr)
            # Write diagnostic log if output exists
            if output_path.exists():
                output_content = _read_bounded_stream(output_path)
                _write_diagnostic_file(review_dir / ".reviewer-output-diagnostic.log", output_content)
                try:
                    os.unlink(output_path)
                except OSError:
                    pass
            return ReviewAdapterResult(
                status=status,
                error_code=error_code,
                error_detail=_sanitize_error_detail(error_detail),
                request_path=request_path,
                result_path=result_path_final,
                reviewer_stdout=reviewer_stdout,
                reviewer_stderr=reviewer_stderr,
                reviewer_exit_code=reviewer_exit_code,
                timeout_occurred=timeout_occurred,
            )

        # Check output exists
        if not output_path.exists():
            error_code = "RESULT_NOT_CREATED"
            error_detail = "reviewer did not create output file"
            _write_diagnostic_file(review_dir / ".reviewer-stdout.log", reviewer_stdout)
            _write_diagnostic_file(review_dir / ".reviewer-stderr.log", reviewer_stderr)
            return ReviewAdapterResult(
                status=status,
                error_code=error_code,
                error_detail=_sanitize_error_detail(error_detail),
                request_path=request_path,
                result_path=result_path_final,
                reviewer_stdout=reviewer_stdout,
                reviewer_stderr=reviewer_stderr,
                reviewer_exit_code=reviewer_exit_code,
                timeout_occurred=timeout_occurred,
            )

        # Check output size
        try:
            output_size = output_path.stat().st_size
        except OSError as e:
            error_code = "RESULT_NOT_CREATED"
            error_detail = f"cannot stat output: {e}"
            return ReviewAdapterResult(
                status=status,
                error_code=error_code,
                error_detail=_sanitize_error_detail(error_detail),
                request_path=request_path,
                result_path=result_path_final,
                reviewer_stdout=reviewer_stdout,
                reviewer_stderr=reviewer_stderr,
                reviewer_exit_code=reviewer_exit_code,
                timeout_occurred=timeout_occurred,
            )

        if output_size > MAX_OUTPUT_SIZE:
            error_code = "RESULT_TOO_LARGE"
            error_detail = f"reviewer output exceeds {MAX_OUTPUT_SIZE} bytes"
            try:
                os.unlink(output_path)
            except OSError:
                pass
            return ReviewAdapterResult(
                status=status,
                error_code=error_code,
                error_detail=_sanitize_error_detail(error_detail),
                request_path=request_path,
                result_path=result_path_final,
                reviewer_stdout=reviewer_stdout,
                reviewer_stderr=reviewer_stderr,
                reviewer_exit_code=reviewer_exit_code,
                timeout_occurred=timeout_occurred,
            )

        # Read and parse output
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                result_data = json.load(f)
        except json.JSONDecodeError as e:
            error_code = "MALFORMED_OUTPUT"
            error_detail = f"output is not valid JSON: {e}"
            output_content = _read_bounded_stream(output_path)
            _write_diagnostic_file(review_dir / ".reviewer-output-diagnostic.log", output_content)
            try:
                os.unlink(output_path)
            except OSError:
                pass
            return ReviewAdapterResult(
                status=status,
                error_code=error_code,
                error_detail=_sanitize_error_detail(error_detail),
                request_path=request_path,
                result_path=result_path_final,
                reviewer_stdout=reviewer_stdout,
                reviewer_stderr=reviewer_stderr,
                reviewer_exit_code=reviewer_exit_code,
                timeout_occurred=timeout_occurred,
            )
        except OSError as e:
            error_code = "RESULT_NOT_CREATED"
            error_detail = f"cannot read output: {e}"
            return ReviewAdapterResult(
                status=status,
                error_code=error_code,
                error_detail=_sanitize_error_detail(error_detail),
                request_path=request_path,
                result_path=result_path_final,
                reviewer_stdout=reviewer_stdout,
                reviewer_stderr=reviewer_stderr,
                reviewer_exit_code=reviewer_exit_code,
                timeout_occurred=timeout_occurred,
            )

        # Validate result structure
        try:
            validate_review_result(result_data)
        except ReviewContractError as e:
            error_code = "CONTRACT_VIOLATION"
            error_detail = f"result validation failed: {e}"
            output_content = _read_bounded_stream(output_path)
            _write_diagnostic_file(review_dir / ".reviewer-output-diagnostic.log", output_content)
            try:
                os.unlink(output_path)
            except OSError:
                pass
            return ReviewAdapterResult(
                status=status,
                error_code=error_code,
                error_detail=_sanitize_error_detail(error_detail),
                request_path=request_path,
                result_path=result_path_final,
                reviewer_stdout=reviewer_stdout,
                reviewer_stderr=reviewer_stderr,
                reviewer_exit_code=reviewer_exit_code,
                timeout_occurred=timeout_occurred,
            )

        # Check identity binding
        try:
            _check_result_binding(request_data, result_data)
        except ReviewContractError as e:
            error_code = "IDENTITY_MISMATCH"
            error_detail = f"identity binding failed: {e}"
            output_content = _read_bounded_stream(output_path)
            _write_diagnostic_file(review_dir / ".reviewer-output-diagnostic.log", output_content)
            try:
                os.unlink(output_path)
            except OSError:
                pass
            return ReviewAdapterResult(
                status=status,
                error_code=error_code,
                error_detail=_sanitize_error_detail(error_detail),
                request_path=request_path,
                result_path=result_path_final,
                reviewer_stdout=reviewer_stdout,
                reviewer_stderr=reviewer_stderr,
                reviewer_exit_code=reviewer_exit_code,
                timeout_occurred=timeout_occurred,
            )

        # Publish canonical result
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
            _atomic_write_json(result_path, result_data)
            result_path_final = result_path
        except OSError as e:
            error_code = "ATOMIC_PUBLICATION_FAILED"
            error_detail = f"cannot write canonical result: {e}"
            try:
                os.unlink(output_path)
            except OSError:
                pass
            return ReviewAdapterResult(
                status=status,
                error_code=error_code,
                error_detail=_sanitize_error_detail(error_detail),
                request_path=request_path,
                result_path=result_path_final,
                reviewer_stdout=reviewer_stdout,
                reviewer_stderr=reviewer_stderr,
                reviewer_exit_code=reviewer_exit_code,
                timeout_occurred=timeout_occurred,
            )

        # Success
        try:
            os.unlink(output_path)
        except OSError:
            pass

        status = "OK"
        error_code = ""
        error_detail = ""

        return ReviewAdapterResult(
            status=status,
            error_code=error_code,
            error_detail=error_detail,
            request_path=request_path,
            result_path=result_path_final,
            reviewer_stdout=reviewer_stdout,
            reviewer_stderr=reviewer_stderr,
            reviewer_exit_code=reviewer_exit_code,
            timeout_occurred=timeout_occurred,
        )

    finally:
        _release_lock(lock_path, lock_owned)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main() -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Reviewer adapter for WP-AL-1C2")
    parser.add_argument("--repo-root", required=True, type=Path, help="Repository root directory")
    parser.add_argument("--run-dir", required=True, type=Path, help="Run artifact directory")
    parser.add_argument("--manifest", required=True, type=Path, help="Story manifest path")
    parser.add_argument("--failure-context", required=True, type=Path, help="Failure context path")
    parser.add_argument("--run-id", required=True, help="Run identifier")
    parser.add_argument("--story-id", required=True, help="Story identifier")
    parser.add_argument("--review-iteration", required=True, type=int, help="Review iteration (>=1)")
    parser.add_argument("--repair-iteration", required=True, type=int, help="Repair iteration (>=0)")
    parser.add_argument("--triggered-by", required=True, choices=["initial_verify_pass", "post_repair_verify_pass"])
    parser.add_argument("--generated-at", required=True, help="ISO-8601 UTC timestamp")
    parser.add_argument("--reviewer-id", required=True, help="Reviewer identifier")
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT, help=f"Timeout seconds ({MIN_TIMEOUT}-{MAX_TIMEOUT})")
    parser.add_argument("--reviewer-command", required=True, help="Reviewer executable")
    parser.add_argument("--reviewer-arg", action="append", default=[], help="Reviewer fixed arguments (repeatable)")

    args = parser.parse_args()

    # Build reviewer_command sequence
    reviewer_command = [args.reviewer_command] + args.reviewer_arg

    try:
        result = run_review(
            repo_root=args.repo_root,
            run_dir=args.run_dir,
            manifest_path=args.manifest,
            failure_context_path=args.failure_context,
            run_id=args.run_id,
            story_id=args.story_id,
            review_iteration=args.review_iteration,
            repair_iteration=args.repair_iteration,
            triggered_by=args.triggered_by,
            generated_at=args.generated_at,
            reviewer_id=args.reviewer_id,
            reviewer_command=reviewer_command,
            timeout_seconds=args.timeout_seconds,
        )
    except (ReviewContractError, FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"Adapter exception: {e}", file=sys.stderr)
        return 2

    if result.status == "OK":
        return 0
    else:
        # Print error detail to stderr (sanitized, no traceback)
        if result.error_detail:
            print(f"Adapter error: {result.error_detail}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
