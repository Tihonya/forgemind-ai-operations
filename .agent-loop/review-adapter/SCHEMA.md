# Reviewer Adapter Protocol v1.0

## Purpose

Defines the deterministic reviewer adapter protocol for WP-AL-1C2. The adapter
constructs a schema-valid review-request.json, invokes a reviewer subprocess,
validates the output, and publishes a canonical review-result.json with exact
identity binding.

No orchestration wiring, no repair contract, no real LLM integration.

## Adapter API

### run_review()

```python
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
) -> ReviewAdapterResult
```

All arguments keyword-only. No internal time calls, no random values, no
network access, no shell=True, no command-string parsing.

### ReviewAdapterResult

```python
@dataclass(frozen=True)
class ReviewAdapterResult:
    status: str  # "OK" or "ERROR"
    error_code: str  # empty when OK; taxonomy code when ERROR
    error_detail: str  # sanitized, bounded, no secrets, no absolute paths
    request_path: Path  # absolute path to review-request.json
    result_path: Path | None  # absolute path to review-result.json (None if not published)
    reviewer_stdout: str  # bounded sanitized stdout (max 4096 bytes)
    reviewer_stderr: str  # bounded sanitized stderr (max 4096 bytes)
    reviewer_exit_code: int | None  # None if not started
    timeout_occurred: bool  # True if reviewer terminated due to timeout
```

## CLI Protocol

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

Exit codes:
- 0: adapter OK (reviewer produced valid PASS/FAIL/ERROR result)
- 2: adapter ERROR (infrastructure failure)

No traceback leakage, no secret leakage, no absolute-path leakage in diagnostics.

## Reviewer Subprocess Protocol

### Invocation

```bash
<reviewer_command> --request <request_path> --output <output_path>
```

- Adapter appends `--request` and `--output` after caller-supplied fixed arguments
- `request_path`: `$RUN_DIR/review/review-request.json` (adapter writes atomically)
- `output_path`: `$RUN_DIR/review/reviewer-output.json` (reviewer writes atomically)
- No other paths passed; no credentials; no tokens

### Environment

Deterministic minimal environment (no inherited values):

```python
{
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "HOME": str(run_dir / ".reviewer-home"),
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONNOUSERSITE": "1",
    "TMPDIR": str(run_dir / "tmp"),
    "PYTHONDONTWRITEBYTECODE": "1",
}
```

Excluded: inherited PATH, inherited HOME, PYTHONPATH, DATABASE_URL, REDIS_URL,
API_KEY, TOKEN, SECRET, credentials, provider variables, ambient environment dump.

Rationale:
- Fixed PATH ensures argv[0] resolution is deterministic
- Adapter-owned HOME prevents reviewer from reading user configuration
- No PYTHONPATH prevents arbitrary module injection
- PYTHONNOUSERSITE=1 prevents loading user-site packages
- Fixed LANG/LC_ALL ensures deterministic locale behavior
- TMPDIR under run_dir prevents reviewer from writing to shared /tmp
- PYTHONDONTWRITEBYTECODE=1 prevents .pyc file creation

HOME and TMPDIR directories created with mode 0o700.

### Working Directory

Reviewer process runs with `cwd=str(run_dir)`. Adapter does not depend on
caller's current working directory.

### Process Isolation

- `start_new_session=True`: creates new process group
- Allows clean termination via SIGTERM/SIGKILL to process group
- No orphan processes after adapter returns

## Artifact Lifecycle

### Three Artifact Classes

**1. Untrusted reviewer output** (`$RUN_DIR/review/reviewer-output.json`)

- Temporary; adapter-owned path
- Never canonical
- Checked for containment, file type, symlink status, and size before reading
- Removed after diagnostic extraction (on both success and failure)
- Never retained verbatim by default

**2. Sanitized diagnostic artifact** (`$RUN_DIR/review/.reviewer-output-diagnostic.log`)

- Bounded to 4096 bytes
- UTF-8 decoded with `errors="replace"`
- Control characters handled via `sanitize_control_characters()`
- Base64 and secret redaction applied via `redact_text()`
- URL query values stripped
- File mode 0o600
- Deterministic filename under `$RUN_DIR/review/`
- Contains no raw untrusted payload

**3. Canonical validated review-result.json** (`$RUN_DIR/reports/review-result.json`)

- Created only after JSON parsing, structural validation, and identity binding
- Atomically published via tmp + os.replace
- File mode 0o600
- Existing valid canonical result preserved on all failure paths
- Atomically replaced only after full validation of new result

### Request Working Artifact

```
$RUN_DIR/review/review-request.json
```

- Written atomically by adapter (tmp + os.replace)
- Retained as audit artifact
- Not removed after review completion

### Reviewer Output (Temporary, Untrusted)

```
$RUN_DIR/review/reviewer-output.json
```

- Reviewer writes to this path
- Adapter reads and validates
- On success (adapter OK): removed after canonical publication
- On validation failure: sanitized diagnostic artifact written, then raw output removed
- On timeout/non-zero exit: raw output removed after diagnostic extraction
- Oversized (>1 MB) or special file type: not read as JSON; adapter ERROR

### Canonical Validated Publication

```
$RUN_DIR/reports/review-result.json
```

- Written atomically by adapter after validation
- Only written when:
  - Reviewer exit 0
  - Output is valid JSON
  - Output passes `validate_review_result()`
  - Output passes identity binding checks
- Never overwritten by invalid output
- Existing canonical result preserved if new output is invalid

### Pre-Existing Canonical Result

If a valid canonical `review-result.json` already exists before invocation:

- Preserved until a new result is fully validated
- Failed invocation does not delete or replace it
- Successful publication atomically replaces it only after full validation
- Concurrent or stale-run behavior governed by adapter lock (see below)

### Artifact Lifecycle Table

| State | reviewer-output.json | review-result.json | .reviewer-output-diagnostic.log |
|---|---|---|---|
| Before adapter runs | does not exist | may exist (prior run) | does not exist |
| Reviewer writes output | created | unchanged | not yet |
| Adapter validates OK | removed | atomically replaced | not created |
| Adapter validates FAIL | removed | unchanged (preserved) | created (sanitized) |
| Adapter timeout/exit | removed | unchanged (preserved) | created (sanitized) |
| Adapter oversized/type | not read | unchanged (preserved) | not created |

## Atomic Publication

### Parent Directories

- Adapter creates `$RUN_DIR/review/` if it does not exist (`os.makedirs(exist_ok=True)`)
- Adapter creates `$RUN_DIR/reports/` if it does not exist

### Temporary Sibling Files

- Request: `$RUN_DIR/review/.review-request-tmp-<PID>.json`
- Result: `$RUN_DIR/reports/.review-result-tmp-<PID>.json`
- Use PID to avoid collision in concurrent test scenarios
- Temporary files created with exclusive creation (`O_CREAT | O_EXCL`)

### fsync Policy

- Write to temp file
- `file.flush()`
- `os.fsync(file.fileno())` if supported
- `os.replace(temp_path, final_path)`

### File Permissions

- All artifact files: mode 0o600 (owner read/write only)
- Adapter-created directories (`.reviewer-home`, `tmp`): mode 0o700

### Cleanup Behavior

- On successful publication: remove temp file if it still exists
- On adapter ERROR: remove temp file (do not leave partial artifacts)
- On crash/interrupt: temp file may remain (manual cleanup acceptable)
- Never leave partially written canonical artifact
- Raw reviewer-output.json removed after diagnostic extraction on all paths

### No Partial Canonical Artifacts

- If `os.replace` fails, temp file remains but canonical path is untouched
- Existing canonical result is never corrupted by failed write

## Identity Binding

After `validate_review_result()` passes, the adapter enforces exact binding with the request:

| Result Field | Must Equal | Source |
|---|---|---|
| `schema_version` | `"1.0"` | (already checked by validate_review_result) |
| `run_id` | request.run_id | request |
| `story_id` | request.story_id | request |
| `review_iteration` | request.review_iteration | request |
| `repair_iteration` | request.repair_iteration | request |
| `reviewer_id` | request.reviewer_id | request |

Note: The review-result schema does not include `candidate_identity` or a digest
field. Binding is limited to the identity fields above. This is sufficient for
WP-AL-1C2; if future WPs require candidate identity binding in the result, that
is a schema extension in WP-AL-1C3 or later.

Binding check implementation:

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

## Command Validation

### Sequence Constraints

- Length: 1 to 10 elements inclusive
- Every element must be `str` and non-empty
- No element may contain null bytes (`\x00`)
- No element may contain CR (`\r`) or LF (`\n`)
- Total UTF-8 encoded command length (all elements joined) bounded at 8192 bytes
- No fixed argument (elements before adapter-appended `--request`/`--output`) may equal or start with `--request` or `--output`
- Duplicate reserved flags forbidden
- No fixed argument may match known secret patterns (apply `redact_text()` check)

### Executable Validation

`argv[0]` may be absolute or a simple executable name (no path separators):

**If `argv[0]` is absolute:**
- Resolve it directly via `Path(argv[0]).resolve()`
- Reject if symlink (`os.path.islink()`)
- Require regular file (`stat.S_ISREG`)
- Require executable (`os.access(path, os.X_OK)`)

**If `argv[0]` is not absolute:**
- It must contain no path separators (no `/` or `\`)
- Resolve it using `shutil.which(argv[0], path=minimal_env["PATH"])`
- If `shutil.which` returns `None`, return `EXECUTABLE_NOT_FOUND`
- Apply the same symlink/regular/executable checks to the resolved path

After resolution, use the absolute resolved executable path in `subprocess` argv.
Never rely on the parent process PATH.
Never use `Path("python3").resolve()` as executable lookup (it does not perform PATH search).

### Python Interpreter Script Argument Validation

When the resolved `argv[0]` basename is `python`, `python3`, `python3.12`, or
similar (regex `^python3?(?:\.\d+)?$`), the first fixed non-option argument in
`reviewer_command[1:]` is treated as the **reviewer script path**.

Script path validation:
- Must be absolute after resolution
- Must exist
- Must be a regular file (`stat.S_ISREG`)
- Must not be a symlink (`os.path.islink()`)
- Must resolve beneath `repo_root` (containment check via `_safe_resolve`)
- Must contain no null bytes, CR, or LF
- Failure maps to `EXECUTABLE_NOT_ALLOWED`
- Script content is not executed through shell
- Arbitrary script paths outside `repo_root` are rejected

Scope: This rule applies only to the Python mock/reviewer boundary of WP-AL-1C2.
It is not a generic interpreter framework.

### Diagnostic Safety

- `error_detail` never includes the full command or full absolute path
- Diagnostics show only the sanitized executable basename (`Path(argv[0]).name`)
- No credentials echoed

## Environment Isolation

See "Environment" section above. No inherited environment. Explicit allowlist only.

## Filesystem Safety

### Pre-Invocation Checks

Before reviewer invocation, the adapter validates:

- `request_path` resolves beneath `run_dir`
- `output_path` resolves beneath `run_dir`
- Canonical destination resolves beneath `run_dir / "reports"`
- No symlink following outside trusted root (`_safe_resolve` from review_contract.py)
- Pre-existing output path rejected if symlink (`os.path.islink()`)
- Pre-existing output path rejected if non-regular file type:
  - FIFO (`stat.S_ISFIFO`)
  - Socket (`stat.S_ISSOCK`)
  - Block device (`stat.S_ISBLK`)
  - Character device (`stat.S_ISCHR`)
  - Directory (`stat.S_ISDIR`)
- Canonical destination rejected if symlink or unsafe type
- Hard-link count greater than 1 rejected for pre-existing output path (if supported by OS)

### Temporary File Safety

- Temporary siblings created with exclusive creation (`O_CREAT | O_EXCL`)
- `os.replace` only after destination safety re-check
- Invalid output never replaces existing canonical result

### File Permissions

- All artifact files: mode 0o600
- Adapter-created directories (`.reviewer-home`, `tmp`): mode 0o700

### Cleanup After Timeout

- After timeout and process group kill:
  - Raw reviewer-output.json removed after diagnostic extraction
  - Temporary files removed
  - Canonical result untouched

## Lock Semantics

WP-AL-1C2 uses an explicit single-writer lock:

```
$RUN_DIR/review/.adapter.lock
```

- Acquired atomically via exclusive file creation (`O_CREAT | O_EXCL`)
- Lock file mode: 0o600
- Lock file contains:
  - PID of the acquiring adapter process
  - `run_id` of the current adapter invocation
- Concurrent invocation returns adapter ERROR: `CONCURRENT_INVOCATION`
- Lock released on every exit path (success, error, exception, signal) in `finally` block when owned by current adapter invocation
- Stale-lock policy:
  - If lock file exists but PID is not a running process:
    - If stored `run_id` matches the current `run_id` (same run directory identity), the lock is considered stale and may be removed and reacquired
    - Otherwise, return `CONCURRENT_INVOCATION` and require manual inspection
  - Stale-lock removal and lock reacquisition must use race-aware exclusive operations (check-then-acquire in one atomic step where possible)
- PID reuse is a known limitation; the `run_id` check mitigates the most dangerous case (different runs sharing a recycled PID)
- The adapter does NOT rely solely on `project.json` `concurrency_limit: 1` — it enforces its own lock

## Timeout and Termination

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

### Timeout Bounds

- `timeout_seconds` must be an integer
- Minimum: 1
- Maximum: 600
- Default: 30
- Invalid values (0, negative, >600, non-integer) rejected before subprocess launch
- Termination grace remains fixed at 5 seconds

### Child Reaping

- `proc.wait()` reaps the child process
- No orphan processes remain after adapter returns
- Process group kill ensures grandchildren are also terminated

## Diagnostic Sanitization

### stdout/stderr Capture (Bounded)

- After process completion or termination:
  - Read at most 4096 bytes from each temporary stream file
  - Decode as UTF-8 with `errors="replace"`
  - Sanitize via `redact_text()` from failure_context.py
  - Store bounded result in `ReviewAdapterResult.reviewer_stdout` and `reviewer_stderr`
  - Remove temporary stream files
- Temporary streams are never retained verbatim
- If a temporary stream exceeds 4096 bytes, only the first 4096 bytes are read and the remainder is discarded
- No `subprocess.PIPE` is used — all output goes to adapter-owned files

### Why File-Redirect Instead of PIPE

Using `subprocess.PIPE` with `communicate()` buffers all stdout/stderr in memory
before any truncation can occur. A misbehaving reviewer could exhaust adapter
memory before the timeout fires. File-redirect ensures output is bounded by the
filesystem and the adapter reads at most 4096 bytes after process completion.

### No Secrets or Absolute-Path Leakage

- `error_detail` contains only sanitized, bounded text
- No environment dump
- No command line with credentials
- No raw malformed JSON copied into error_detail
- `error_detail` shows only the executable basename, never the full command or full absolute path

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
File mode: 0o600.

### Sanitization Pipeline for Diagnostics

- Use `redact_text()` from failure_context.py
- Remove secrets, tokens, credentials
- Truncate to byte limits
- No environment dump
- No absolute paths in error_detail (use relative paths or "reviewer output")
- No raw untrusted payload preserved on disk

## Error Taxonomy

| Error Code | Condition | Canonical Result Published? | Diagnostic Files? |
|---|---|---|---|
| `REQUEST_BUILD_FAILED` | build_review_request raised exception | No | No |
| `EXECUTABLE_NOT_FOUND` | reviewer_command[0] does not resolve to an existing executable regular file | No | No |
| `EXECUTABLE_NOT_ALLOWED` | reviewer_command sequence violates constraints (see Command Validation) | No | No |
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

- Invalid sequence (empty, non-string element, null bytes, embedded CR/LF)
- Reserved flag collision (`--request` or `--output` in fixed args)
- Excessive element count (>10) or total encoded length (>8192 bytes)
- Unsafe executable type (symlink, directory, device)
- Executable path escaping trusted root
- Credential-bearing fixed argument detected
- Python reviewer script path outside repo_root
- Python reviewer script path is symlink or non-regular file

### ATOMIC_PUBLICATION_FAILED Covers Only

- Temporary file write failure
- `fsync` failure
- `os.replace` failure

It does NOT cover unsafe paths or symlinks (those use `UNSAFE_OUTPUT_PATH`).

### States That May Leave Diagnostic Files

- `TIMEOUT`, `TERMINATION_FAILED`, `NON_ZERO_EXIT`, `RESULT_NOT_CREATED`, `MALFORMED_OUTPUT`, `CONTRACT_VIOLATION`, `IDENTITY_MISMATCH`, `ATOMIC_PUBLICATION_FAILED`

Note: `INVALID_TIMEOUT` is validated before subprocess launch and does not leave diagnostic files.

### States That Must Not Produce Canonical review-result.json

- All error codes above.

### States That Produce Canonical review-result.json

- Only when adapter returns `status="OK"` (reviewer exit 0, valid output, binding matches).

## Exit Semantics

### Reviewer Exit 0 + Valid Result (PASS, FAIL, or ERROR)

- Adapter validates result
- Adapter publishes canonical review-result.json
- Adapter returns `ReviewAdapterResult(status="OK")`
- Adapter process exit 0
- Reviewer ERROR status is preserved in review-result.json and must never be interpreted as PASS or VERIFIED

### Reviewer Exit Non-Zero

- Adapter classifies as infrastructure failure
- Adapter does NOT publish canonical review-result.json
- Adapter returns `ReviewAdapterResult(status="ERROR", error_code="NON_ZERO_EXIT")`
- Adapter process exit 2

### Adapter Infrastructure ERROR (timeout, missing executable, invalid JSON, schema violation, identity mismatch, unsafe path, concurrent invocation)

- Adapter does NOT publish canonical review-result.json
- Adapter returns `ReviewAdapterResult(status="ERROR", error_code=<specific code>)`
- Adapter process exit 2

### Distinction

| State | Reviewer Exit | Reviewer Result Status | Adapter Result | Adapter Exit |
|---|---|---|---|---|
| Valid PASS | 0 | PASS | OK | 0 |
| Valid FAIL | 0 | FAIL | OK | 0 |
| Valid ERROR | 0 | ERROR | OK | 0 |
| Reviewer infrastructure failure | non-zero | (none) | ERROR | 2 |
| Adapter infrastructure failure | (varies) | (varies) | ERROR | 2 |

Reviewer ERROR (status in result) and adapter ERROR (exit 2) are distinct and
must never share ambiguous semantics.

WARNING for orchestration WP: A valid review-result.json with `status="ERROR"`
must NOT be passed into the current report-story.sh. The current report-story.sh
(lines 97-102) falls through to `VERIFIED` for any review status that is not
PASS or FAIL, which means ERROR would silently become VERIFIED. This bug must be
fixed in the orchestration-wiring WP (WP-AL-1D) before review-result.json with
ERROR enters the reporting flow.

## Mock Reviewer Behavior

### Production Protocol

```bash
mock_reviewer.py \
  --request <request_path> \
  --output <result_path> \
  --mode PASS|FAIL|ERROR
```

Behavior:

1. Parse named arguments via `argparse`
2. Read and parse `request_path` as JSON
3. Validate enough request fields to bind result (run_id, story_id, review_iteration, repair_iteration, reviewer_id)
4. Construct a deterministic review-result.json based on `--mode`:
   - **PASS:** empty findings, recommended_action="none", decision_rationale="Mock reviewer: PASS"
   - **FAIL:** one BLOCKER finding, recommended_action="repair", decision_rationale="Mock reviewer: FAIL"
   - **ERROR:** one finding with severity MAJOR, category "infrastructure", recommended_action="human_review", decision_rationale="Mock reviewer: ERROR"
5. Use `generated_at` from request as `status_generated_at` in result (no internal time call)
6. Write result atomically to `result_path` (tmp + os.replace)
7. Exit 0 on success
8. Exit 2 on mock infrastructure failure (e.g., cannot read request, cannot write output)

### Mock ERROR Mode Detail

- `status`: `"ERROR"`
- `recommended_action`: `"human_review"`
- Finding: `finding_id="mock-finding-001"`, `severity="MAJOR"`, `category="infrastructure"`, `summary="Mock reviewer: infrastructure error"`, `evidence_refs=[]`, `recommended_fix="Human review required"`
- `decision_rationale`: `"Mock reviewer: ERROR"`
- Exit code: 0

This produces a schema-valid result. There is no "ERROR" severity in the
finding schema; valid severities are BLOCKER, MAJOR, MINOR, INFO.

### Determinism

- No `datetime.now()` or `time.time()` calls
- Timestamps derived from request only
- Finding IDs are deterministic (e.g., "mock-finding-001")
- Output is reproducible given the same request and mode

### No Network, No Environment

- No network access
- No environment variable configuration
- No ambient state

### Test-Only Modes (Hidden)

For testing edge cases, the mock supports additional `--mode` values:

| Mode | Behavior | Exit Code |
|---|---|---|
| `invalid_json` | Write `{ invalid json }` to output | 0 |
| `contract_violation` | Write result missing required field | 0 |
| `non_zero_exit` | Exit 1 without writing output | 1 |
| `sleep` | Sleep for 60 seconds (for timeout testing) | 0 |
| `missing_output` | Exit 0 without writing output | 0 |

These modes are for testing only and are not part of the production protocol.
They may be documented in test comments or a separate test fixture section.

## Exclusions

The following are explicitly out of scope for WP-AL-1C2:

- **Orchestration wiring:** run-story.sh remains unchanged; review phase handler remains empty
- **Report integration:** report-story.sh remains unchanged; ERROR handling deferred to WP-AL-1D
- **Verification changes:** verify-story.sh and failure_context.py remain unchanged
- **Review contract changes:** review_contract.py remains unchanged unless a genuine prerequisite defect is discovered (in which case STOP and report)
- **Repair schema or adapter:** WP-AL-1C3 and WP-AL-1C4 are separate WPs
- **Iteration orchestration:** No loop counting or budget enforcement
- **Real reviewer or LLM:** Only mock reviewer; no provider integration
- **Provider credentials:** No API keys, tokens, or secrets
- **Prompt design:** No prompt engineering
- **Shared agent protocol:** No generic adapter abstraction
- **Resumability:** No run state machine or checkpoint

## Relationship to Other Schemas

- Manifest schema: `.agent-loop/manifests/SCHEMA.md` (unchanged)
- Failure-context schema: `.agent-loop/failure-context/SCHEMA.md` (unchanged)
- Review schema: `.agent-loop/review/SCHEMA.md` (unchanged)
- Reviewer adapter protocol: this document (`.agent-loop/review-adapter/SCHEMA.md`)

## Non-Goals

- No LLM invocation
- No reviewer/repair agent logic (beyond mock)
- No run lifecycle / state machine
- No concurrency support (beyond lock)
- No prompt design
- No orchestrator wiring
- No modification to report-story.sh
- No repair contract
- No shared adapter framework
