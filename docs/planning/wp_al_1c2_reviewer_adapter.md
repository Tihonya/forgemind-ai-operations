# WP-AL-1C2: Reviewer Adapter — Implementation Plan

**Status:** IMPLEMENTATION COMPLETE — AWAITING REVIEW
**Work Package:** WP-AL-1C2
**Priority:** High
**Estimated Effort:** 2-3 days

## Overview

The reviewer adapter provides a secure, deterministic interface for invoking external reviewer subprocesses within the agent-loop infrastructure. It handles process lifecycle management, filesystem safety, security validation, and structured result parsing.

## Acceptance Criteria

### AC-1: Adapter Interface
- [x] `run_review()` function accepts all required parameters
- [x] Returns `ReviewAdapterResult` with all fields
- [x] Supports both function call and CLI entry points

### AC-2: Security Validation
- [x] `shell=False` in all subprocess calls
- [x] Command argument validation (max 10 elements, max 8192 bytes)
- [x] Reserved flag collision detection
- [x] Null byte and control character rejection
- [x] Credential pattern redaction check
- [x] Executable path resolution via `shutil.which()` or absolute path

### AC-3: Filesystem Safety
- [x] Symlink detection and rejection
- [x] Hard link count validation (>1 rejected)
- [x] Path containment checks (output under run_dir)
- [x] Atomic file writes with `os.replace()`
- [x] Permission validation (0o600 for files, 0o700 for directories)

### AC-4: Process Lifecycle
- [x] `start_new_session=True` for process group isolation
- [x] File descriptor redirection (stdout/stderr to temp files)
- [x] Timeout validation (1-600 seconds)
- [x] SIGTERM → 5s grace → SIGKILL escalation
- [x] Process group termination via `os.killpg()`
- [x] Orphan process cleanup verification

### AC-5: Result Validation
- [x] JSON schema validation via `validate_review_result()`
- [x] Status field validation (PASS/FAIL/ERROR)
- [x] Identity field binding verification
- [x] Bounded output reading (4096 bytes max)
- [x] Diagnostic file sanitization

### AC-6: Error Handling
- [x] Comprehensive error code taxonomy
- [x] TERMINATION_FAILED for SIGKILL survival
- [x] Sanitized error messages (no secrets, no absolute paths)
- [x] Proper exception type usage (TypeError vs ValueError)

### AC-7: Test Coverage
- [x] 59 adapter tests (R01-R59)
- [x] 8 mock reviewer tests (M01-M08)
- [x] 3 harness scenario tests (H01-H03)
- [x] All tests pass with ruff/mypy compliance

## Architecture

### Component Structure
```
scripts/agent-loop/lib/review_adapter.py
├── ReviewAdapterResult (dataclass)
├── run_review() (main API)
├── _validate_command_sequence() (security)
├── _validate_output_path_safety() (filesystem)
├── _build_minimal_env() (environment)
├── _atomic_write_json() (I/O)
├── _acquire_lock() / _release_lock() (concurrency)
└── main() (CLI entry point)

scripts/agent-loop/lib/mock_reviewer.py
├── Mock reviewer with PASS/FAIL/ERROR modes
├── Deterministic output generation
└── Schema-compliant result format
```

### Security Model
1. **Command Validation**: Reject shell metacharacters, reserved flags, credential patterns
2. **Path Safety**: Symlink detection, hard link limits, containment checks
3. **Process Isolation**: New session, file descriptor redirection, group termination
4. **Environment Control**: Minimal environment, no inheritance, explicit allowlist
5. **Output Bounding**: 4096 byte limit, sanitization, redaction

### Error Code Taxonomy
| Code | Meaning |
|------|---------|
| `REQUEST_BUILD_FAILED` | Request construction failed |
| `EXECUTABLE_NOT_FOUND` | Executable not in PATH or invalid |
| `EXECUTABLE_NOT_ALLOWED` | Security validation failed |
| `UNSAFE_OUTPUT_PATH` | Output path safety check failed |
| `CONCURRENT_INVOCATION` | Lock acquisition failed |
| `TIMEOUT` | Process exceeded timeout |
| `TERMINATION_FAILED` | Process survived SIGKILL |
| `NON_ZERO_EXIT` | Process exited with error |
| `RESULT_NOT_CREATED` | Output file missing |
| `RESULT_TOO_LARGE` | Output exceeds 1MB |
| `MALFORMED_OUTPUT` | Invalid JSON |
| `CONTRACT_VIOLATION` | Schema validation failed |
| `IDENTITY_MISMATCH` | Result doesn't match request |
| `ATOMIC_PUBLICATION_FAILED` | Atomic write failed |

## Implementation Details

### Subprocess Invocation
```python
proc = subprocess.Popen(
    cmd,
    stdout=stdout_fd,
    stderr=stderr_fd,
    cwd=str(run_dir),
    env=minimal_env,
    start_new_session=True,
    close_fds=True,
    shell=False,  # Explicit, required by R42
)
```

### Timeout Escalation
```python
try:
    proc.wait(timeout=timeout_seconds)
except subprocess.TimeoutExpired:
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=5)  # Grace period
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()
        # Check if process still exists
        try:
            os.kill(proc.pid, 0)
            error_code = "TERMINATION_FAILED"
        except ProcessLookupError:
            error_code = "TIMEOUT"
```

### Atomic Write Pattern
```python
fd, tmp_path = tempfile.mkstemp(dir=output_dir, suffix=".tmp")
try:
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, final_path)
except Exception:
    os.unlink(tmp_path)
    raise
```

## Test Matrix

### R01-R59: Adapter Tests
- **R01-R05**: Request construction
- **R06-R08**: Atomic write safety
- **R09-R17**: Command validation
- **R18-R26**: Subprocess execution (including timeout/termination)
- **R27-R31**: Result binding verification
- **R32-R35**: Canonical result publication
- **R36-R41**: Diagnostic output handling
- **R42-R46**: Security enforcement
- **R47-R59**: Filesystem safety & concurrency

### M01-M08: Mock Reviewer Tests
- **M01-M03**: Status mode tests (PASS/FAIL/ERROR)
- **M04-M06**: Determinism verification
- **M07**: Atomic write verification
- **M08**: Schema compliance

### H01-H03: Harness Integration
- **H01**: Scenario U (mock PASS integration)
- **H02**: Scenario V (mock FAIL integration)
- **H03**: Regression test ownership (run_harness_scenarios.sh)

## Quality Metrics

- **Test Count**: 70 planned IDs, 73 pytest items collected
- **Pass Rate**: 73/73 (100%)
- **Ruff Violations**: 0
- **Mypy Violations**: 0
- **Harness Scenarios**: 22/22 PASS (A-V)

## Dependencies

- Python 3.11+
- pytest 9.0+
- ruff 0.8+
- mypy 1.14+

## Notes

- R35 uses `pytest.mark.skipif(os.geteuid() == 0)` for root user detection
- H03 is owned by bash harness, not pytest (documentation-only test)
- R26 uses `@pytest.mark.parametrize` for timeout boundary testing
- All subprocess calls explicitly set `shell=False` per R42 requirement
- SIGKILL survival detection added for TERMINATION_FAILED error code

## Next Steps

1. Product Owner review of implementation
2. Address any feedback or concerns
3. Merge to main branch upon approval
4. Update project documentation
5. Plan WP-AL-1C3 (Repair Adapter)
