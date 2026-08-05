# WP-AL-1C2 — Deterministic Reviewer Adapter

**Status:** APPROVED FOR IMPLEMENTATION PLANNING, NOT STARTED

**Branch:** To be created: `feature/agent-loop-reviewer-adapter`
**Base:** `origin/main` @ `691bb9cc9610b03117bb79fbd7a9996ec8782106`

---

## 1. Objective and Boundary

Define and implement a standalone deterministic reviewer adapter that:

1. Constructs a schema-valid review-request.json using existing pipeline artifacts
   (failure-context.json + story manifest) via the WP-AL-1C1 builder;
2. Writes the request atomically to `$RUN_DIR/review/review-request.json`;
3. Invokes a configurable reviewer executable with named arguments;
4. Captures bounded stdout/stderr diagnostics;
5. Reads the reviewer's output from `$RUN_DIR/review/reviewer-output.json`;
6. Validates the output via `validate_review_result()` from WP-AL-1C1;
7. Checks exact request/result identity binding (run_id, story_id, iterations, reviewer_id);
8. Atomically publishes the canonical result to `$RUN_DIR/reports/review-result.json`;
9. Returns a typed `ReviewAdapterResult` indicating OK or ERROR with structured diagnostics.

**Boundary:**

- Standalone adapter module; no orchestration wiring;
- No modification to run-story.sh, report-story.sh, or verify-story.sh;
- No repair contract, repair adapter, or repair invocation;
- No real LLM or provider integration;
- No prompt design;
- No shared agent adapter protocol abstraction;
- No iteration orchestration or budget enforcement;
- No resumability or state machine.

**Depends on:**

- WP-AL-1C1 (review_contract.py: build_review_request, validate_review_result)
- WP-AL-1B3 (failure_context.json as input artifact)

**Precedes:**

- WP-AL-1C3 (Repair Contract)
- WP-AL-1D (Orchestration Wiring)

---

## 2. Exact Proposed Files

### New Files

| File | Purpose |
|---|---|
| `.agent-loop/review-adapter/SCHEMA.md` | Adapter protocol specification |
| `scripts/agent-loop/lib/review_adapter.py` | Adapter module (run_review function + CLI entry point) |
| `scripts/agent-loop/lib/mock_reviewer.py` | Configurable mock reviewer executable |
| `scripts/agent-loop/tests/test_review_adapter.py` | Adapter unit and integration tests |
| `scripts/agent-loop/tests/test_mock_reviewer.py` | Mock reviewer tests |
| `docs/planning/wp_al_1c2_reviewer_adapter.md` | This planning document |

### Modified Files

| File | Change |
|---|---|
| `scripts/agent-loop/tests/run_harness_scenarios.sh` | Add scenarios U and V |
| `scripts/agent-loop/README.md` | Status update: WP-AL-1C2 |
| `docs/next_steps.md` | Mark WP-AL-1C2 as IN PROGRESS or COMPLETE |

### Excluded Files

- `scripts/agent-loop/run-story.sh` (orchestration wiring is WP-AL-1D)
- `scripts/agent-loop/report-story.sh` (ERROR handling is WP-AL-1D)
- `scripts/agent-loop/verify-story.sh` (no changes needed)
- `scripts/agent-loop/lib/failure_context.py` (no changes needed)
- `scripts/agent-loop/lib/review_contract.py` (no changes unless genuine defect found)
- Any repair schema or adapter files

---

## 3. Adapter API

```python
from pathlib import Path
from typing import Sequence
from dataclasses import dataclass

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
    timeout_seconds: int = 30,
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
        timeout_seconds: integer 1–600 inclusive, default 30

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
```

### CLI Entry Point

The same file (`scripts/agent-loop/lib/review_adapter.py`) provides a CLI
entry point via a `__main__` block. No separate wrapper script is needed.

```bash
python3 scripts/agent-loop/lib/review_adapter.py \
  --repo-root <path> \
  --run-dir <path> \
  --manifest <path> \
  --failure-context <path> \
  --run-id <id> \
  --story-id <id> \
  --review-iteration <n> \
  --repair-iteration <n> \
  --triggered-by <value> \
  --generated-at <iso8601> \
  --reviewer-id <id> \
  --timeout-seconds <n> \
  --reviewer-command <executable> \
  [--reviewer-arg <arg>]...
```

**CLI requirements:**

- Thin wrapper around `run_review()`;
- `argparse` with explicit named arguments;
- No shell parsing; no command-string splitting;
- Repeated `--reviewer-arg` builds `Sequence[str]` of fixed arguments;
- `--reviewer-command` provides `argv[0]` (the executable);
- Adapter appends reserved `--request` and `--output` after fixed args;
- CLI exit 0 for valid PASS/FAIL/ERROR (adapter OK);
- CLI exit 2 for adapter infrastructure failure (adapter ERROR);
- Harness scenarios U and V invoke this exact CLI.

### API Design Decisions

**reviewer_command: Sequence[str] (not Path)**

Rationale:
- Allows passing the executable plus fixed safe arguments (e.g., `["python3", "/path/to/mock_reviewer.py"]`);
- Adapter appends only `--request` and `--output`;
- No shell string parsing;
- No shell=True;
- Security: caller controls the full command prefix; adapter does not interpolate.

**generated_at: required (no default)**

Rationale:
- No internal `datetime.now()` call;
- Deterministic: caller supplies timestamp;
- Matches WP-AL-1C1 builder contract.

**reviewer_id: required (no default)**

Rationale:
- Explicit identity for audit trail;
- No ambient configuration;
- Mock reviewer uses "mock-reviewer" by convention, but adapter does not assume.

**timeout_seconds: int = 30**

Rationale:
- PO-approved default (DEC-R3);
- Positive bounded integer;
- Caller may override for real reviewer WP.

---

## 4. Artifact Paths

### Three Artifact Classes

The adapter distinguishes three classes of output artifact:

**1. Untrusted reviewer output** (`$RUN_DIR/review/reviewer-output.json`)

- Temporary; adapter-owned path;
- Never canonical;
- Checked for containment, file type, symlink status and size before reading;
- Removed after diagnostic extraction (on both success and failure);
- Never retained verbatim by default.

**2. Sanitized diagnostic artifact** (`$RUN_DIR/review/.reviewer-output-diagnostic.log`)

- Bounded to 4096 bytes;
- UTF-8 decoded with `errors="replace"`;
- Control characters handled via `sanitize_control_characters()`;
- Base64 and secret redaction applied via `redact_text()`;
- URL query values stripped;
- File mode `0o600`;
- Deterministic filename under `$RUN_DIR/review/`;
- Contains no raw untrusted payload.

**3. Canonical validated review-result.json** (`$RUN_DIR/reports/review-result.json`)

- Created only after JSON parsing, structural validation and identity binding;
- Atomically published via tmp + os.replace;
- File mode `0o600`;
- Existing valid canonical result is preserved on all failure paths;
- Atomically replaced only after full validation of new result.

### Request Working Artifact

```
$RUN_DIR/review/review-request.json
```

- Written atomically by adapter (tmp + os.replace);
- Retained as audit artifact;
- Not removed after review completion.

### Reviewer Output (Temporary, Untrusted)

```
$RUN_DIR/review/reviewer-output.json
```

- Reviewer writes to this path;
- Adapter reads and validates;
- **On success (adapter OK):** removed after canonical publication;
- **On validation failure:** sanitized diagnostic artifact written, then raw
  output removed;
- **On timeout/non-zero exit:** raw output removed after diagnostic extraction;
- **Oversized (>1 MB) or special file type:** not read as JSON; adapter ERROR.

### Canonical Validated Publication

```
$RUN_DIR/reports/review-result.json
```

- Written atomically by adapter after validation;
- Only written when:
  - Reviewer exit 0;
  - Output is valid JSON;
  - Output passes `validate_review_result()`;
  - Output passes identity binding checks;
- Never overwritten by invalid output;
- Existing canonical result is preserved if new output is invalid.

### Pre-Existing Canonical Result

If a valid canonical `review-result.json` already exists before invocation:

- It is preserved until a new result is fully validated;
- Failed invocation does not delete or replace it;
- Successful publication atomically replaces it only after full validation;
- Concurrent or stale-run behavior is governed by the adapter lock (see section 14).

### Artifact Lifecycle

| State | reviewer-output.json | review-result.json | .reviewer-output-diagnostic.log |
|---|---|---|---|
| Before adapter runs | does not exist | may exist (prior run) | does not exist |
| Reviewer writes output | created | unchanged | not yet |
| Adapter validates OK | removed | atomically replaced | not created |
| Adapter validates FAIL | removed | unchanged (preserved) | created (sanitized) |
| Adapter timeout/exit | removed | unchanged (preserved) | created (sanitized) |
| Adapter oversized/type | not read | unchanged (preserved) | not created |

---

## 5. Atomicity

### Parent Directories

- Adapter creates `$RUN_DIR/review/` if it does not exist (`os.makedirs(exist_ok=True)`);
- Adapter creates `$RUN_DIR/reports/` if it does not exist.

### Temporary Sibling Files

- Request: `$RUN_DIR/review/.review-request-tmp-<PID>.json`
- Result: `$RUN_DIR/reports/.review-result-tmp-<PID>.json`
- Use PID to avoid collision in concurrent test scenarios.
- Temporary files created with exclusive creation (`O_CREAT | O_EXCL`).

### fsync Policy

- Write to temp file;
- `file.flush()`;
- `os.fsync(file.fileno())` if supported;
- `os.replace(temp_path, final_path)`.

### File Permissions

- All artifact files: mode `0o600` (owner read/write only);
- Adapter-created directories (`.reviewer-home`, `tmp`): mode `0o700`.

### Cleanup Behavior

- On successful publication: remove temp file if it still exists;
- On adapter ERROR: remove temp file (do not leave partial artifacts);
- On crash/interrupt: temp file may remain (manual cleanup acceptable);
- Never leave partially written canonical artifact;
- Raw reviewer-output.json removed after diagnostic extraction on all paths.

### No Partial Canonical Artifacts

- If `os.replace` fails, temp file remains but canonical path is untouched;
- Existing canonical result is never corrupted by failed write.

---

## 6. Result Binding Beyond Structural Validation

After `validate_review_result()` passes, the adapter enforces exact binding with the request:

| Result Field | Must Equal | Source |
|---|---|---|
| `schema_version` | `"1.0"` | (already checked by validate_review_result) |
| `run_id` | request.run_id | request |
| `story_id` | request.story_id | request |
| `review_iteration` | request.review_iteration | request |
| `repair_iteration` | request.repair_iteration | request |
| `reviewer_id` | request.reviewer_id | request |

**Note:** The review-result schema does not include `candidate_identity` or a digest field. Binding is limited to the identity fields above. This is sufficient for WP-AL-1C2; if future WPs require candidate identity binding in the result, that is a schema extension in WP-AL-1C3 or later.

**Binding check implementation:**

```python
def _check_result_binding(request: dict, result: dict) -> None:
    """
    Check exact binding between request and result.
    Raises ReviewContractError on mismatch.
    """
    for field in ("run_id", "story_id", "review_iteration", "repair_iteration", "reviewer_id"):
        if result.get(field) != request.get(field):
            raise ReviewContractError(
                f"result.{field} ({result.get(field)}) does not match request.{field} ({request.get(field)})"
            )
```

This check runs after `validate_review_result()` and before canonical publication.

---

## 7. Process Lifecycle

### Process Group Isolation

```python
import subprocess
import signal
import os

# Adapter-owned temporary streams (bounded, removed after use)
stdout_tmp = run_dir / "review" / ".reviewer-stdout-tmp"
stderr_tmp = run_dir / "review" / ".reviewer-stderr-tmp"
# Create with exclusive mode 0o600
stdout_fd = os.open(str(stdout_tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
stderr_fd = os.open(str(stderr_tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)

proc = subprocess.Popen(
    command,
    stdout=stdout_fd,
    stderr=stderr_fd,
    start_new_session=True,  # Creates new process group
    env=minimal_env,
    cwd=str(run_dir),  # Reviewer working directory is run_dir
    pass_fds=(stdout_fd, stderr_fd),
)
os.close(stdout_fd)
os.close(stderr_fd)
```

`start_new_session=True` ensures the reviewer and any children are in a separate process group, allowing clean termination.

**Working directory:** The reviewer process runs with `cwd=str(run_dir)`. The adapter does not depend on the caller's current working directory. The reviewer must not assume any other working directory.

**Why file-redirect instead of PIPE:** Using `subprocess.PIPE` with `communicate()` buffers all stdout/stderr in memory before any truncation can occur. A misbehaving reviewer could exhaust adapter memory before the timeout fires. File-redirect ensures output is bounded by the filesystem and the adapter reads at most 4096 bytes after process completion.

### Timeout Measurement

```python
try:
    proc.wait(timeout=timeout_seconds)
    timeout_occurred = False
except subprocess.TimeoutExpired:
    timeout_occurred = True
    # Terminate process group
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=5)  # 5-second grace
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait()  # reap
```

### Child Reaping

- `proc.wait()` reaps the child process;
- No orphan processes remain after adapter returns;
- Process group kill ensures grandchildren are also terminated.

### stdout/stderr Capture (Bounded)

- After process completion or termination:
  - Read at most 4096 bytes from each temporary stream file;
  - Decode as UTF-8 with `errors="replace"`;
  - Sanitize via `redact_text()` from failure_context.py;
  - Store bounded result in `ReviewAdapterResult.reviewer_stdout` and `reviewer_stderr`;
  - Remove temporary stream files;
- Temporary streams are never retained verbatim;
- If a temporary stream exceeds 4096 bytes, only the first 4096 bytes are read and the remainder is discarded;
- No `subprocess.PIPE` is used — all output goes to adapter-owned files.

### No Secrets or Absolute-Path Leakage

- `error_detail` contains only sanitized, bounded text;
- No environment dump;
- No command line with credentials;
- No raw malformed JSON copied into error_detail;
- `error_detail` shows only the executable basename, never the full command or full absolute path.

---

## 8. Diagnostic Preservation

### Three-Class Output Policy

See section 4 for the full definition of untrusted output, sanitized diagnostic,
and canonical result.

**On adapter success (reviewer exit 0, valid output, binding matches):**

- Canonical review-result.json published atomically;
- Raw reviewer-output.json removed;
- No diagnostic files created.

**On adapter validation failure (reviewer exit 0, but output invalid):**

- Canonical review-result.json NOT created (existing one preserved);
- Sanitized diagnostic artifact written to `$RUN_DIR/review/.reviewer-output-diagnostic.log`;
- Raw reviewer-output.json removed after diagnostic extraction.

**On adapter infrastructure failure (timeout, non-zero exit, etc.):**

- Canonical review-result.json NOT created (existing one preserved);
- Sanitized diagnostic artifact written (if reviewer produced output);
- Raw reviewer-output.json removed after diagnostic extraction.

### Bounded Diagnostics in ReviewAdapterResult

| Field | Content | Limit |
|---|---|---|
| `reviewer_exit_code` | Process exit code | integer or None |
| `error_code` | Error taxonomy code | string (enum) |
| `error_detail` | Sanitized human-readable detail | max 1024 bytes |
| `reviewer_stdout` | Sanitized stdout | max 4096 bytes |
| `reviewer_stderr` | Sanitized stderr | max 4096 bytes |
| `timeout_occurred` | Boolean flag | boolean |

### Diagnostic Artifacts

For adapter ERROR cases, the following diagnostic files are written to `$RUN_DIR/review/`:

| File | When Written | Content |
|---|---|---|
| `.reviewer-output-diagnostic.log` | Reviewer wrote output but validation failed | Sanitized, bounded (4096 bytes), redacted excerpt |
| `.reviewer-stdout.log` | Adapter ERROR | Bounded sanitized stdout |
| `.reviewer-stderr.log` | Adapter ERROR | Bounded sanitized stderr |

These are retained for debugging but are not canonical artifacts.
File mode: `0o600`.

### Sanitization Pipeline for Diagnostics

- Use `redact_text()` from failure_context.py;
- Remove secrets, tokens, credentials;
- Truncate to byte limits;
- No environment dump;
- No absolute paths in error_detail (use relative paths or "reviewer output");
- No raw untrusted payload preserved on disk.

---

## 9. Error Taxonomy

| Error Code | Condition | Canonical Result Published? | Diagnostic Files? |
|---|---|---|---|
| `REQUEST_BUILD_FAILED` | build_review_request raised exception | No | No |
| `EXECUTABLE_NOT_FOUND` | reviewer_command[0] does not resolve to an existing executable regular file | No | No |
| `EXECUTABLE_NOT_ALLOWED` | reviewer_command sequence violates constraints (see section 13) | No | No |
| `UNSAFE_OUTPUT_PATH` | Pre-existing output path is symlink, FIFO, device, socket, hard-link count > 1, or escapes run_dir | No | No |
| `CONCURRENT_INVOCATION` | Adapter lock already held by another process | No | No |
| `TIMEOUT` | Reviewer exceeded timeout_seconds | No | Yes (stdout/stderr logs) |
| `TERMINATION_FAILED` | SIGKILL failed (should not happen) | No | Yes |
| `NON_ZERO_EXIT` | Reviewer exited non-zero | No | Yes (stdout/stderr logs, diagnostic if output exists) |
| `RESULT_NOT_CREATED` | Reviewer did not create reviewer-output.json | No | Yes (stdout/stderr logs) |
| `RESULT_TOO_LARGE` | reviewer-output.json exceeds 1 MB | No | No (do not read) |
| `MALFORMED_OUTPUT` | reviewer-output.json is not valid JSON | No | Yes (.reviewer-output-diagnostic.log) |
| `CONTRACT_VIOLATION` | validate_review_result raised ReviewContractError | No | Yes (.reviewer-output-diagnostic.log) |
| `IDENTITY_MISMATCH` | Result binding check failed | No | Yes (.reviewer-output-diagnostic.log) |
| `ATOMIC_PUBLICATION_FAILED` | tmp write, fsync, or os.replace failed | No | Yes (temp file may remain) |
| `INVALID_TIMEOUT` | timeout_seconds not integer or outside 1-600 | No | No |

### EXECUTABLE_NOT_ALLOWED Covers

- Invalid sequence (empty, non-string element, null bytes, embedded CR/LF);
- Reserved flag collision (`--request` or `--output` in fixed args);
- Excessive element count (>10) or total encoded length (>8192 bytes);
- Unsafe executable type (symlink, directory, device);
- Executable path escaping trusted root;
- Credential-bearing fixed argument detected;
- Python reviewer script path outside repo_root;
- Python reviewer script path is symlink or non-regular file.

### ATOMIC_PUBLICATION_FAILED Covers Only

- Temporary file write failure;
- `fsync` failure;
- `os.replace` failure.

It does NOT cover unsafe paths or symlinks (those use `UNSAFE_OUTPUT_PATH`).

### States That May Leave Diagnostic Files

- `TIMEOUT`, `TERMINATION_FAILED`, `NON_ZERO_EXIT`, `RESULT_NOT_CREATED`, `MALFORMED_OUTPUT`, `CONTRACT_VIOLATION`, `IDENTITY_MISMATCH`, `ATOMIC_PUBLICATION_FAILED`

Note: `INVALID_TIMEOUT` is validated before subprocess launch and does not leave diagnostic files.

### States That Must Not Produce Canonical review-result.json

- All error codes above.

### States That Produce Canonical review-result.json

- Only when adapter returns `status="OK"` (reviewer exit 0, valid output, binding matches).

---

## 10. Mock Reviewer Contract

### Production Protocol

```bash
mock_reviewer.py \
  --request <request_path> \
  --output <result_path> \
  --mode PASS|FAIL|ERROR
```

**Behavior:**

1. Parse named arguments via `argparse`;
2. Read and parse `request_path` as JSON;
3. Validate enough request fields to bind result (run_id, story_id, review_iteration, repair_iteration, reviewer_id);
4. Construct a deterministic review-result.json based on `--mode`:
   - **PASS:** empty findings, recommended_action="none", decision_rationale="Mock reviewer: PASS";
   - **FAIL:** one BLOCKER finding, recommended_action="repair", decision_rationale="Mock reviewer: FAIL";
   - **ERROR:** one finding with severity MAJOR, category "infrastructure", recommended_action="human_review", decision_rationale="Mock reviewer: ERROR";
5. Use `generated_at` from request as `status_generated_at` in result (no internal time call);
6. Write result atomically to `result_path` (tmp + os.replace);
7. Exit 0 on success;
8. Exit 2 on mock infrastructure failure (e.g., cannot read request, cannot write output).

**Mock ERROR mode detail:**

- `status`: `"ERROR"`
- `recommended_action`: `"human_review"`
- Finding: `finding_id="mock-finding-001"`, `severity="MAJOR"`, `category="infrastructure"`, `summary="Mock reviewer: infrastructure error"`, `evidence_refs=[]`, `recommended_fix="Human review required"`
- `decision_rationale`: `"Mock reviewer: ERROR"`
- Exit code: 0

This produces a schema-valid result. There is no "ERROR" severity in the
finding schema; valid severities are BLOCKER, MAJOR, MINOR, INFO.

**Determinism:**

- No `datetime.now()` or `time.time()` calls;
- Timestamps derived from request only;
- Finding IDs are deterministic (e.g., "mock-finding-001");
- Output is reproducible given the same request and mode.

**No Network, No Environment:**

- No network access;
- No environment variable configuration;
- No ambient state.

### Test-Only Modes (Hidden)

For testing edge cases, the mock supports additional `--mode` values:

| Mode | Behavior | Exit Code |
|---|---|---|
| `invalid_json` | Write `{ invalid json }` to output | 0 |
| `contract_violation` | Write result missing required field | 0 |
| `non_zero_exit` | Exit 1 without writing output | 1 |
| `sleep` | Sleep for 60 seconds (for timeout testing) | 0 |
| `missing_output` | Exit 0 without writing output | 0 |

These modes are for testing only and are not part of the production protocol. They may be documented in test comments or a separate test fixture section.

---

## 11. Harness Scenarios

### Reserved Scenarios

- **Scenario U:** Valid mock PASS
- **Scenario V:** Valid mock FAIL

### Scenario U — Mock PASS

1. Create isolated temp repository;
2. Create a story manifest with valid schema;
3. Run verify-story.sh (all gates pass);
4. Invoke adapter CLI:
   ```bash
   python3 scripts/agent-loop/lib/review_adapter.py \
     --repo-root <isolated_repo> \
     --run-dir <run_dir> \
     --manifest <manifest_path> \
     --failure-context <fc_path> \
     --run-id <run_id> \
     --story-id <story_id> \
     --review-iteration 1 \
     --repair-iteration 0 \
     --triggered-by initial_verify_pass \
     --generated-at "2026-01-01T00:00:00Z" \
     --reviewer-id mock-reviewer \
     --reviewer-command python3 \
     --reviewer-arg /path/to/mock_reviewer.py \
     --reviewer-arg --mode \
     --reviewer-arg PASS
   ```
5. Assert:
   - Adapter exit code 0;
   - `$RUN_DIR/review/review-request.json` exists and is schema-valid;
   - `$RUN_DIR/reports/review-result.json` exists and is schema-valid;
   - review-result.json has `status="PASS"`, `recommended_action="none"`;
   - Binding fields match request.

### Scenario V — Mock FAIL

1. Create isolated temp repository;
2. Create a story manifest with valid schema;
3. Run verify-story.sh (all gates pass);
4. Invoke adapter CLI with `--reviewer-arg FAIL`;
5. Assert:
   - Adapter exit code 0;
   - `$RUN_DIR/reports/review-result.json` exists and is schema-valid;
   - review-result.json has `status="FAIL"`, `recommended_action="repair"`;
   - At least one BLOCKER finding;
   - Binding fields match request.

### Expected Total

- Scenarios A-T: 20 (existing)
- Scenarios U-V: 2 (new)
- **Total: 22 scenarios, 22/22 PASS**

### Edge Cases in Unit Tests

Mock ERROR, timeout, malformed output, and identity mismatch are covered by unit tests in `test_review_adapter.py`, not harness scenarios, to keep the harness fast and focused on happy-path integration.

---

## 12. Test Matrix

### Planned Test Cases

**Note:** Planned case IDs are not guaranteed pytest-item counts. Some cases may be combined or split during implementation. The matrix defines coverage intent.

#### Request Construction (5 cases)

| ID | Case | Expected |
|---|---|---|
| R01 | Valid request construction (all fields) | Request schema-valid |
| R02 | failure-context.json missing | Adapter ERROR: REQUEST_BUILD_FAILED |
| R03 | Manifest file missing | Adapter ERROR: REQUEST_BUILD_FAILED |
| R04 | Manifest SHA mismatch | Adapter ERROR: REQUEST_BUILD_FAILED |
| R05 | failure-context overall_verification_status != "PASS" | Adapter ERROR: REQUEST_BUILD_FAILED |

#### Request Atomic Write (3 cases)

| ID | Case | Expected |
|---|---|---|
| R06 | Request written atomically | Temp file replaced via os.replace |
| R07 | Request directory does not exist | Adapter creates it |
| R08 | Request write fails (permission denied) | Adapter ERROR: ATOMIC_PUBLICATION_FAILED |

#### Command Construction (9 cases)

| ID | Case | Expected |
|---|---|---|
| R09 | Valid reviewer_command (Sequence[str]) | Command constructed correctly |
| R10 | reviewer_command reserved flag collision | Adapter ERROR: EXECUTABLE_NOT_ALLOWED |
| R11 | reviewer_command[0] not found | Adapter ERROR: EXECUTABLE_NOT_FOUND |
| R12 | reviewer_command[0] not executable | Adapter ERROR: EXECUTABLE_NOT_FOUND |
| R13 | reviewer_command element contains null byte, CR, or LF | Adapter ERROR: EXECUTABLE_NOT_ALLOWED |
| R14 | reviewer_command length > 10 elements | Adapter ERROR: EXECUTABLE_NOT_ALLOWED |
| R15 | reviewer_command total encoded length > 8192 bytes | Adapter ERROR: EXECUTABLE_NOT_ALLOWED |
| R16 | Python reviewer script path outside repo_root | Adapter ERROR: EXECUTABLE_NOT_ALLOWED |
| R17 | Python reviewer script path is symlink | Adapter ERROR: EXECUTABLE_NOT_ALLOWED |

#### Subprocess Execution (9 cases)

| ID | Case | Expected |
|---|---|---|
| R18 | Reviewer exit 0, valid PASS result | Adapter OK, review-result.json written |
| R19 | Reviewer exit 0, valid FAIL result | Adapter OK, review-result.json written |
| R20 | Reviewer exit 0, valid ERROR result | Adapter OK, review-result.json written |
| R21 | Reviewer exit 1 (non-zero) | Adapter ERROR: NON_ZERO_EXIT |
| R22 | Reviewer timeout (sleep > timeout_seconds) | Adapter ERROR: TIMEOUT, SIGTERM+SIGKILL |
| R23 | Reviewer writes invalid JSON | Adapter ERROR: MALFORMED_OUTPUT |
| R24 | Reviewer writes result missing required field | Adapter ERROR: CONTRACT_VIOLATION |
| R25 | Reviewer writes result with invalid status | Adapter ERROR: CONTRACT_VIOLATION |
| R26 | timeout_seconds bounds (0, negative, >600) | Adapter ERROR: INVALID_TIMEOUT (parameterized: 3 sub-cases) |

#### Result Binding (5 cases)

| ID | Case | Expected |
|---|---|---|
| R27 | Result run_id matches request | Binding OK |
| R28 | Result run_id != request run_id | Adapter ERROR: IDENTITY_MISMATCH |
| R29 | Result story_id != request story_id | Adapter ERROR: IDENTITY_MISMATCH |
| R30 | Result review_iteration != request review_iteration | Adapter ERROR: IDENTITY_MISMATCH |
| R31 | Result reviewer_id != request reviewer_id | Adapter ERROR: IDENTITY_MISMATCH |

#### Canonical Publication (4 cases)

| ID | Case | Expected |
|---|---|---|
| R32 | Canonical result written atomically | Temp file replaced via os.replace |
| R33 | Canonical result directory does not exist | Adapter creates it |
| R34 | Existing canonical result not overwritten by invalid output | Old result preserved |
| R35 | Canonical write fails (permission denied) | Adapter ERROR: ATOMIC_PUBLICATION_FAILED |

#### Diagnostic Preservation (6 cases)

| ID | Case | Expected |
|---|---|---|
| R36 | Reviewer stdout captured and sanitized | Max 4096 bytes, no secrets |
| R37 | Reviewer stderr captured and sanitized | Max 4096 bytes, no secrets |
| R38 | Sanitized diagnostic written on validation failure | .reviewer-output-diagnostic.log created, raw removed |
| R39 | Reviewer-output.json removed on success | File does not exist after publication |
| R40 | Oversized reviewer-output.json (>1 MB) | Adapter ERROR: RESULT_TOO_LARGE, not read |
| R41 | Diagnostic files sanitized | No secrets, no absolute paths |

#### Security (5 cases)

| ID | Case | Expected |
|---|---|---|
| R42 | No shell=True | subprocess.Popen with shell=False |
| R43 | No environment dump in diagnostics | env not logged |
| R44 | Deterministic environment passed to reviewer | No inherited PATH/HOME/PYTHONPATH; explicit allowlist only |
| R45 | No secrets in error_detail | Sanitized, basename only |
| R46 | No orphan processes after timeout | Process group killed |

#### Filesystem Safety and Concurrency (13 cases)

| ID | Case | Expected |
|---|---|---|
| R47 | Empty reviewer_command sequence | Adapter ERROR: EXECUTABLE_NOT_ALLOWED |
| R48 | Reserved flag collision in fixed args | Adapter ERROR: EXECUTABLE_NOT_ALLOWED |
| R49 | Executable is symlink | Adapter ERROR: EXECUTABLE_NOT_FOUND |
| R50 | Pre-existing output path is symlink | Adapter ERROR: UNSAFE_OUTPUT_PATH |
| R51 | Output path is FIFO/device/socket | Adapter ERROR: UNSAFE_OUTPUT_PATH |
| R52 | PYTHONPATH not inherited by reviewer | PYTHONPATH absent from subprocess env |
| R53 | Concurrent invocation rejected | Adapter ERROR: CONCURRENT_INVOCATION |
| R54 | Pre-existing output path hard-link count > 1 | Adapter ERROR: UNSAFE_OUTPUT_PATH |
| R55 | Stale adapter lock (run_id matches, PID dead) | Lock removed and reacquired |
| R56 | Stale adapter lock (run_id differs) | Adapter ERROR: CONCURRENT_INVOCATION |
| R57 | HOME directory mode exactly 0o700 | stat mode == 0o700 |
| R58 | TMPDIR directory mode exactly 0o700 | stat mode == 0o700 |
| R59 | Lock file mode exactly 0o600 | stat mode == 0o600 |

#### Mock Reviewer (8 cases)

| ID | Case | Expected |
|---|---|---|
| M01 | Mock PASS mode | Valid PASS result, exit 0 |
| M02 | Mock FAIL mode | Valid FAIL result, exit 0 |
| M03 | Mock ERROR mode | Valid ERROR result (MAJOR finding, category infrastructure), exit 0 |
| M04 | Mock determinism | Same request + mode produces same output |
| M05 | Mock binds run_id from request | Result run_id == request run_id |
| M06 | Mock uses request generated_at | Result status_generated_at == request generated_at |
| M07 | Mock exit 2 on infrastructure failure | Cannot read request produces exit 2 |
| M08 | Mock atomic write | Temp file replaced via os.replace |

#### Harness Scenarios (2 cases)

| ID | Case | Expected |
|---|---|---|
| H01 | Scenario U: mock PASS | 22/22 harness scenarios pass |
| H02 | Scenario V: mock FAIL | 22/22 harness scenarios pass |

#### Regression (1 case)

| ID | Case | Expected |
|---|---|---|
| H03 | Scenarios A-T unchanged | 20/20 existing scenarios still pass |

### Planned Counts

- Request construction: 5 cases
- Request atomic write: 3 cases
- Command construction: 9 cases
- Subprocess execution: 9 cases
- Result binding: 5 cases
- Canonical publication: 4 cases
- Diagnostic preservation: 6 cases
- Security: 5 cases
- Filesystem safety and concurrency: 13 cases
- Mock reviewer: 8 cases
- Harness scenarios: 2 cases
- Regression: 1 case

**Total planned: 70 cases**

Actual pytest-item count may vary due to parameterization or test structure.

---

## 13. Security Model

### No shell=True

```python
subprocess.Popen(
    command,
    shell=False,  # Explicit
    ...
)
```

### No Arbitrary Shell Strings

- `reviewer_command` is `Sequence[str]`;
- Adapter appends only `--request` and `--output` with validated paths;
- No string interpolation;
- Shell metacharacters are not interpreted because `shell=False`.

### reviewer_command Constraints

**Sequence validation (before invocation):**

- Length: 1 to 10 elements inclusive;
- Every element must be `str` and non-empty;
- No element may contain null bytes (`\x00`);
- No element may contain CR (`\r`) or LF (`\n`);
- Total UTF-8 encoded command length (all elements joined) bounded at 8192 bytes;
- No fixed argument (elements before adapter-appended `--request`/`--output`) may equal or start with `--request` or `--output`;
- Duplicate reserved flags forbidden;
- No fixed argument may match known secret patterns (apply `redact_text()` check).

**Executable validation:**

- `argv[0]` may be absolute or a simple executable name (no path separators);
- If `argv[0]` is absolute:
  - Resolve it directly via `Path(argv[0]).resolve()`;
  - Reject if symlink (`os.path.islink()`);
  - Require regular file (`stat.S_ISREG`);
  - Require executable (`os.access(path, os.X_OK)`);
- If `argv[0]` is not absolute:
  - It must contain no path separators (no `/` or `\`);
  - Resolve it using `shutil.which(argv[0], path=minimal_env["PATH"])`;
  - If `shutil.which` returns `None`, return `EXECUTABLE_NOT_FOUND`;
  - Apply the same symlink/regular/executable checks to the resolved path;
- After resolution, use the absolute resolved executable path in `subprocess` argv;
- Never rely on the parent process PATH;
- Never use `Path("python3").resolve()` as executable lookup (it does not perform PATH search).

**Diagnostic safety:**

- `error_detail` never includes the full command or full absolute path;
- Diagnostics show only the sanitized executable basename (`Path(argv[0]).name`);
- No credentials echoed.

### Python Interpreter Script Argument Validation

When the resolved `argv[0]` basename is `python`, `python3`, `python3.12`, or similar (regex `^python3?(?:\.\d+)?$`), the first fixed non-option argument in `reviewer_command[1:]` is treated as the **reviewer script path**.

**Script path validation:**

- Must be absolute after resolution;
- Must exist;
- Must be a regular file (`stat.S_ISREG`);
- Must not be a symlink (`os.path.islink()`);
- Must resolve beneath `repo_root` (containment check via `_safe_resolve`);
- Must contain no null bytes, CR, or LF;
- Failure maps to `EXECUTABLE_NOT_ALLOWED`;
- Script content is not executed through shell;
- Arbitrary script paths outside `repo_root` are rejected.

**Scope:** This rule applies only to the Python mock/reviewer boundary of WP-AL-1C2. It is not a generic interpreter framework.

### EXECUTABLE_NOT_ALLOWED Definition

This error code covers:

- Invalid sequence (empty, length > 10, non-string element);
- Null bytes or CR/LF in any element;
- Excessive total encoded length (> 8192 bytes);
- Reserved flag collision (`--request` or `--output` in fixed args);
- Unsafe executable type (symlink, directory, FIFO, device);
- Executable path escaping trusted root;
- Credential-bearing fixed argument detected.

### EXECUTABLE_NOT_FOUND Definition

This error code covers:

- `argv[0]` does not resolve to an existing file;
- Resolved file is not executable by current process;
- Resolved file is a regular file but lacks execute permission.

### Reviewer Receives Only Two Paths

- `--request <request_path>` (under `$RUN_DIR/review/`)
- `--output <output_path>` (under `$RUN_DIR/review/`)
- No other filesystem paths passed;
- No credentials or tokens.

### Path Containment

- `request_path` and `output_path` are under `$RUN_DIR/review/`;
- Adapter validates paths are under `run_dir` (no traversal);
- Reviewer cannot escape `run_dir` via path arguments.

### Subprocess Environment Policy

**Deterministic explicit environment (no inherited values):**

```python
reviewer_home = run_dir / ".reviewer-home"
reviewer_tmp = run_dir / "tmp"
os.makedirs(reviewer_home, mode=0o700, exist_ok=True)
os.makedirs(reviewer_tmp, mode=0o700, exist_ok=True)

minimal_env = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": str(reviewer_home),
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONNOUSERSITE": "1",
    "TMPDIR": str(reviewer_tmp),
    "PYTHONDONTWRITEBYTECODE": "1",
}
```

**Explicitly excluded:**

- No inherited `PATH` (fixed value);
- No inherited `HOME` (adapter-owned directory under run_dir);
- No `PYTHONPATH` (not set at all — prevents arbitrary module injection);
- No `DATABASE_URL`, `REDIS_URL`, or connection strings;
- No `API_KEY`, `TOKEN`, `SECRET`, or credentials;
- No `.env` sourcing;
- No full ambient environment;
- No provider or runtime configuration variables.

**Rationale:**

- Fixed PATH ensures `argv[0]` resolution is deterministic;
- Adapter-owned HOME prevents reviewer from reading user configuration;
- No PYTHONPATH prevents arbitrary module injection;
- PYTHONNOUSERSITE=1 prevents loading user-site packages;
- Fixed LANG/LC_ALL ensures deterministic locale behavior;
- TMPDIR under run_dir prevents reviewer from writing to shared /tmp;
- PYTHONDONTWRITEBYTECODE=1 prevents .pyc file creation.

**Future expansion:** If a real reviewer needs additional variables, they must be
explicit, allowlisted and approved in a later WP.

### Result-Size Limit

```python
output_path = run_dir / "review" / "reviewer-output.json"
if output_path.exists() and output_path.stat().st_size > 1_000_000:
    return ReviewAdapterResult(
        status="ERROR",
        error_code="RESULT_TOO_LARGE",
        error_detail="reviewer output exceeds 1 MB",
        ...
    )
```

### Timeout Bounds

**Policy:**

- `timeout_seconds` must be an integer;
- Minimum: 1;
- Maximum: 600;
- Default: 30;
- Invalid values (0, negative, >600, non-integer) rejected before subprocess launch;
- Termination grace remains fixed at 5 seconds.

**Validation:**

```python
if not isinstance(timeout_seconds, int) or timeout_seconds < 1 or timeout_seconds > 600:
    return ReviewAdapterResult(
        status="ERROR",
        error_code="INVALID_TIMEOUT",
        error_detail=f"timeout_seconds must be integer 1-600, got {timeout_seconds}",
        ...
    )
```

---

## 14. Filesystem Safety and Concurrency

### Pre-Invocation Checks

Before reviewer invocation, the adapter validates:

- `request_path` resolves beneath `run_dir`;
- `output_path` resolves beneath `run_dir`;
- Canonical destination resolves beneath `run_dir / "reports"`;
- No symlink following outside trusted root (`_safe_resolve` from review_contract.py);
- Pre-existing output path rejected if symlink (`os.path.islink()`);
- Pre-existing output path rejected if non-regular file type:
  - FIFO (`stat.S_ISFIFO`)
  - Socket (`stat.S_ISSOCK`)
  - Block device (`stat.S_ISBLK`)
  - Character device (`stat.S_ISCHR`)
  - Directory (`stat.S_ISDIR`)
- Canonical destination rejected if symlink or unsafe type;
- Hard-link count greater than 1 rejected for pre-existing output path (if supported by OS).

### Temporary File Safety

- Temporary siblings created with exclusive creation (`O_CREAT | O_EXCL`);
- `os.replace` only after destination safety re-check;
- Invalid output never replaces existing canonical result.

### File Permissions

- All artifact files: mode `0o600`;
- Adapter-created directories (`.reviewer-home`, `tmp`): mode `0o700`.

### Cleanup After Timeout

- After timeout and process group kill:
  - Raw reviewer-output.json removed after diagnostic extraction;
  - Temporary files removed;
  - Canonical result untouched.

### Concurrency Policy

WP-AL-1C2 uses an explicit single-writer lock:

```
$RUN_DIR/review/.adapter.lock
```

- Acquired atomically via exclusive file creation (`O_CREAT | O_EXCL`);
- Lock file mode: `0o600`;
- Lock file contains:
  - PID of the acquiring adapter process;
  - `run_id` of the current adapter invocation;
- Concurrent invocation returns adapter ERROR: `CONCURRENT_INVOCATION`;
- Lock released on every exit path (success, error, exception, signal) in `finally` block when owned by current adapter invocation;
- Stale-lock policy:
  - If lock file exists but PID is not a running process:
    - If stored `run_id` matches the current `run_id` (same run directory identity), the lock is considered stale and may be removed and reacquired;
    - Otherwise, return `CONCURRENT_INVOCATION` and require manual inspection;
  - Stale-lock removal and lock reacquisition must use race-aware exclusive operations (check-then-acquire in one atomic step where possible);
- PID reuse is a known limitation; the `run_id` check mitigates the most dangerous case (different runs sharing a recycled PID);
- The adapter does NOT rely solely on `project.json` `concurrency_limit: 1` — it enforces its own lock.

---

## 15. Scope Exclusions

The following are explicitly out of scope for WP-AL-1C2:

- **Orchestration wiring:** run-story.sh remains unchanged; review phase handler remains empty;
- **Report integration:** report-story.sh remains unchanged; ERROR handling deferred to WP-AL-1D;
- **Verification changes:** verify-story.sh and failure_context.py remain unchanged;
- **Review contract changes:** review_contract.py remains unchanged unless a genuine prerequisite defect is discovered (in which case STOP and report);
- **Repair schema or adapter:** WP-AL-1C3 and WP-AL-1C4 are separate WPs;
- **Iteration orchestration:** No loop counting or budget enforcement;
- **Real reviewer or LLM:** Only mock reviewer; no provider integration;
- **Provider credentials:** No API keys, tokens, or secrets;
- **Prompt design:** No prompt engineering;
- **Shared agent protocol:** No generic adapter abstraction;
- **Resumability:** No run state machine or checkpoint.

---

## 16. Exit Semantics (Critical Distinction)

### Reviewer Exit 0 + Valid Result (PASS, FAIL, or ERROR)

- Adapter validates result;
- Adapter publishes canonical review-result.json;
- Adapter returns `ReviewAdapterResult(status="OK")`;
- Adapter process exit 0;
- **Reviewer ERROR status is preserved in review-result.json and must never be interpreted as PASS or VERIFIED.**

### Reviewer Exit Non-Zero

- Adapter classifies as infrastructure failure;
- Adapter does NOT publish canonical review-result.json;
- Adapter returns `ReviewAdapterResult(status="ERROR", error_code="NON_ZERO_EXIT")`;
- Adapter process exit 2.

### Adapter Infrastructure ERROR (timeout, missing executable, invalid JSON, schema violation, identity mismatch, unsafe path, concurrent invocation)

- Adapter does NOT publish canonical review-result.json;
- Adapter returns `ReviewAdapterResult(status="ERROR", error_code=<specific code>)`;
- Adapter process exit 2.

### Distinction

| State | Reviewer Exit | Reviewer Result Status | Adapter Result | Adapter Exit |
|---|---|---|---|---|
| Valid PASS | 0 | PASS | OK | 0 |
| Valid FAIL | 0 | FAIL | OK | 0 |
| Valid ERROR | 0 | ERROR | OK | 0 |
| Reviewer infrastructure failure | non-zero | (none) | ERROR | 2 |
| Adapter infrastructure failure | (varies) | (varies) | ERROR | 2 |

**Reviewer ERROR (status in result) and adapter ERROR (exit 2) are distinct and must never share ambiguous semantics.**

**WARNING for orchestration WP:** A valid review-result.json with `status="ERROR"` must NOT be passed into the current report-story.sh. The current report-story.sh (lines 97-102) falls through to `VERIFIED` for any review status that is not PASS or FAIL, which means ERROR would silently become VERIFIED. This bug must be fixed in the orchestration-wiring WP (WP-AL-1D) before review-result.json with ERROR enters the reporting flow.

---

## 17. Acceptance Criteria

- **AC-1:** Adapter protocol documented at `.agent-loop/review-adapter/SCHEMA.md`;
- **AC-2:** `run_review()` constructs schema-valid review-request.json using `build_review_request()` from WP-AL-1C1;
- **AC-3:** Request written atomically to `$RUN_DIR/review/review-request.json`;
- **AC-4:** Mock reviewer executable produces schema-valid PASS/FAIL/ERROR results;
- **AC-5:** Adapter invokes reviewer with named arguments (`--request`, `--output`);
- **AC-6:** Adapter validates result via `validate_review_result()` from WP-AL-1C1;
- **AC-7:** Adapter checks exact identity binding (run_id, story_id, iterations, reviewer_id);
- **AC-8:** Canonical result written atomically to `$RUN_DIR/reports/review-result.json`;
- **AC-9:** Timeout handling: SIGTERM after N seconds, SIGKILL after 5-second grace;
- **AC-10:** Malformed reviewer output produces adapter ERROR with sanitized diagnostic artifact; raw output removed;
- **AC-11:** No modification to run-story.sh or report-story.sh;
- **AC-12:** Harness scenarios U and V pass;
- **AC-13:** All existing scenarios A-T continue to pass (22/22 total);
- **AC-14:** ruff clean, mypy --strict clean;
- **AC-15:** No secrets in adapter output, error messages, or diagnostics;
- **AC-16:** No shell=True, no arbitrary shell strings;
- **AC-17:** Deterministic explicit environment passed to reviewer (no inherited PATH/HOME/PYTHONPATH);
- **AC-18:** Reviewer ERROR (status in result) distinct from adapter ERROR (exit 2);
- **AC-19:** Existing canonical result never overwritten by invalid output;
- **AC-20:** No orphan processes after timeout or interrupt;
- **AC-21:** reviewer_command constraints enforced (sequence length, null bytes, reserved flags, executable type);
- **AC-22:** Filesystem safety: pre-existing symlinks, FIFO/device/socket rejection, containment checks;
- **AC-23:** Concurrency: adapter lock prevents concurrent invocation;
- **AC-24:** CLI entry point functional: harness U/V invoke `review_adapter.py` directly;
- **AC-25:** All artifact files mode 0o600, adapter directories mode 0o700;
- **AC-26:** Raw reviewer-output.json never retained verbatim; sanitized diagnostic artifact produced instead;
- **AC-27:** Deterministic executable lookup: argv[0] resolved via shutil.which() for relative names, direct path resolution for absolute names;
- **AC-28:** Python reviewer script containment: script path validated to exist under repo_root, reject symlinks;
- **AC-29:** Timeout bounds enforced: timeout_seconds must be integer 1-600, invalid values rejected before subprocess launch;
- **AC-30:** Bounded stdout/stderr capture: file-redirect with 4096-byte read limit, no unbounded PIPE accumulation;
- **AC-31:** Lock permissions and stale-lock behavior: lock file mode 0o600, contains PID and run_id, stale detection requires run_id match;
- **AC-32:** Every security policy has explicit test coverage (command constraints, script containment, timeout bounds, lock policy, environment isolation).

---

## 18. Documentation Status

**APPROVED FOR IMPLEMENTATION PLANNING, NOT STARTED**

This document defines the plan. Implementation begins only after Product Owner reviews and approves this planning document.

---

## 19. Commit / PR Strategy

Conventional commits, one logical change per commit:

1. `docs(agent-loop): add WP-AL-1C2 reviewer adapter planning document`
   (this file)
2. `docs(agent-loop): add review-adapter protocol schema`
   (`.agent-loop/review-adapter/SCHEMA.md`)
3. `feat(agent-loop): add mock reviewer executable`
   (`scripts/agent-loop/lib/mock_reviewer.py`, `tests/test_mock_reviewer.py`)
4. `feat(agent-loop): add reviewer adapter`
   (`scripts/agent-loop/lib/review_adapter.py`, `tests/test_review_adapter.py`)
5. `test(agent-loop): add harness scenarios U and V`
   (`scripts/agent-loop/tests/run_harness_scenarios.sh`)
6. `docs(agent-loop): update README and next_steps for WP-AL-1C2`

PR description references this planning document and lists AC-1 through AC-32.

---

## 20. Branch Strategy

- Base: `origin/main` @ `691bb9cc9610b03117bb79fbd7a9996ec8782106`;
- Branch name: `feature/agent-loop-reviewer-adapter`;
- One PR against `main`;
- Merge commit strategy (not squash) to preserve WP structure.

---

## 21. Dependencies and Follow-On WPs

**Depends on:**

- WP-AL-1C1 (review contract, builder, validators)
- WP-AL-1B3 (failure-context collector)

**Precedes / unblocks:**

- WP-AL-1C3 (Repair Contract)
- WP-AL-1C4 (Repair Adapter)
- WP-AL-1D (Orchestration Wiring)

---

## 22. Stop Conditions

Stop and report without further action if:

- Any regression in scenarios A-T;
- Any secret value appearing in test fixtures, diagnostics, or error messages;
- Any scope violation on a forbidden path (run-story.sh, report-story.sh, etc.);
- Any modification to review_contract.py unless a genuine prerequisite defect is discovered (in which case STOP and report the defect);
- Any attempt to implement orchestration wiring or repair contract;
- Reviewer ERROR status cannot be cleanly distinguished from adapter ERROR.

---

## 23. Product Owner Decisions Incorporated

| ID | Decision | Resolution |
|---|---|---|
| DEC-R1 | Reviewer result transport | Output file (not stdout); stdout/stderr diagnostic only |
| DEC-R2 | Reviewer invocation protocol | Named arguments: `--request <path> --output <path>` |
| DEC-R3 | Adapter timeout default | 30 seconds, caller may override |
| DEC-R4 | Timeout kill strategy | SIGTERM then 5s grace then SIGKILL |
| DEC-R5 | run-story.sh integration | No modification; standalone adapter |
| DEC-R6 | report-story.sh integration | No modification; ERROR handling deferred |
| DEC-R7 | Mock reviewer configuration | `--mode PASS\|FAIL\|ERROR` |
| DEC-R8 | Request artifact | Write to `$RUN_DIR/review/review-request.json`, retain as audit |

---

## 24. Temporary Report Disposition

The file `docs/planning/next_wp_al_1c2_planning_report.md` was created on explicit Product Owner request and is approved as a temporary planning artifact.

**Disposition:**

- Retain during planning review;
- Do not stage automatically;
- The unique rationale has been migrated to section 25 of this document;
- After this canonical planning document is approved, the temporary report is FULLY SUPERSEDED and may be deleted before the planning commit.

---

## 25. Architecture Rationale

### Why Reviewer Adapter Now

Three candidates were evaluated for the next work package after WP-AL-1C1:

**Option A: Repair Contract (schemas, validators, builder)**
- Depends on review-result being producible;
- Repair consumes review findings as input;
- Without a reviewer adapter, no review-result exists for repair to consume;
- Verdict: **Premature.** No upstream consumer to validate against.

**Option B: Deterministic Reviewer Adapter**
- First working consumer of WP-AL-1C1 review contract + WP-AL-1B3 failure-context artifacts;
- Closes the gap between "schema exists" and "artifact is producible";
- Independently testable without modifying run-story.sh;
- Mock-based testing keeps it deterministic and LLM-free;
- Verdict: **Selected.** Highest immediate value.

**Option C: Shared Agent Adapter Protocol**
- Only one adapter type exists (reviewer);
- Repair adapter is 2+ WPs away;
- Abstracting over one instance is premature;
- Risk: over-engineering, locking in protocol before repair requirements are known;
- Verdict: **Deferred.** Extract commonality after repair adapter exists.

### Current report-story.sh ERROR Fallthrough Bug

The current `report-story.sh` (lines 97-102) determines final status as:

```python
if report["review"]["status"] == "PASS":
    final_status = "ACCEPTED"
elif report["review"]["status"] == "FAIL":
    final_status = "REVIEW_REJECTED"
else:
    final_status = "VERIFIED"  # BUG: ERROR falls through here
```

A valid review-result.json with `status="ERROR"` would produce `final_status="VERIFIED"`,
silently converting an infrastructure failure into a successful outcome.

**WP-AL-1C2 does NOT fix this bug.** The adapter correctly produces ERROR results,
but they must not enter the current reporting flow. WP-AL-1D (Orchestration Wiring)
must add explicit ERROR detection: if review-result.json has `status="ERROR"`,
the orchestrator must NOT call report-story.sh with current logic, and must instead
exit 2 or write an `INFRASTRUCTURE_ERROR` final report directly.

### Remaining Architectural Gaps After WP-AL-1C2

After WP-AL-1C2, the following capabilities remain missing:

1. Repair contract (WP-AL-1C3)
2. Repair adapter (WP-AL-1C4)
3. Orchestration wiring: run-story.sh phase handlers remain stubs (WP-AL-1D)
4. ERROR propagation: report-story.sh has no ERROR handling (WP-AL-1D)
5. Iteration budget: no loop counting or max-repair enforcement in adapter layer
6. Resumability: no run state machine

---

End of planning document.
