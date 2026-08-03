# Agent Loop Infrastructure

Autonomous agent-driven development cycle with deterministic verification gates.

## Quick Start

```bash
cd /path/to/forgemind-agent-loop

# Dry run (verify only, no agent invocation)
./scripts/agent-loop/run-story.sh --dry-run --manifest scripts/agent-loop/templates/story-prd.json

# Full run (implementation + verify + review + repair loop)
./scripts/agent-loop/run-story.sh --manifest scripts/agent-loop/templates/story-prd.json
```

## Architecture

### Components

1. **run-story.sh** - Main orchestrator
   - Implementation (Ralph) → Verification → Review → Repair → Report
   - Max iterations configurable (default: 3)
   - Dry-run mode for testing verification gates without agents

2. **verify-story.sh** - Deterministic verification (no agent)
   - Scope check (allowed/forbidden paths)
   - JSON syntax validation
   - Targeted tests with assertion gate
   - Lint (ruff + mypy)
   - Secrets scan (inline regex)
   - git diff --check
   - Generates machine-readable JSON report

3. **report-story.sh** - Final report generator
   - Aggregates verification/review/repair results
   - Atomic JSON writes via shared harness.py module

4. **lib/harness.py** - Shared Python utilities
   - atomic_json_write: tmp+os.replace for crash safety
   - parse_junit_xml: pytest JUnit parser
   - validate_manifest: manifest schema validation
   - load_gate_config: extract gate config from manifest
   - load_test_args: extract test args as JSON array

### Configuration

**config.sh** - Shared configuration loader:
- Derives FORGEMIND_AGENT_LOOP_ROOT from Git repository root
- Validates required environment: AGENTLAB_ROOT, FORGEMIND_MAIN_ROOT
- Loads .agent-loop/project.json and .agent-loop/gates.json via config_loader.py
- Parses NUL-delimited output to export resolved paths and policy
- Auto-detects Python/pytest/ruff/mypy binaries from .venv or PATH
- Agent binaries (override via RALPH_BIN, OPENCODE_BIN environment variables)
- State directories and loop limits

**scripts/agent-loop/lib/config_loader.py** - Configuration validator and emitter:
- CLI: `validate-project <path>`, `validate-gates <path>`, `emit-null-env <path>`
- Validates schema_version, project_id, required fields
- Resolves environment variable placeholders (${AGENTLAB_ROOT}, ${FORGEMIND_MAIN_ROOT}, ${FORGEMIND_AGENT_LOOP_ROOT})
- Validates path existence (existing roots) and distinctness (all roots pairwise distinct)
- Emits NUL-delimited key-value pairs (safe for paths with spaces)
- Exit codes: 0=success, 1=validation error, 2=configuration error
- No eval, no shell code generation, no secrets in error messages

**.agent-loop/project.json** - Project structure and runtime policy:
- schema_version, project_id, repository_name
- structure: main_control_plane_root, infrastructure_root, source_worktree_root, validation_worktree_root, runs_root
- roles: allowed agent roles
- workspaces: allowed workspace types
- runtime_policy: max_repair_iterations, auto_commit, auto_push, auto_merge, concurrency_limit
- secret_handling: never_log_secrets, never_commit_secrets, redact_in_reports
- path_policy: pattern_type (gitwildmatch), globally_forbidden_paths, approval_required_paths

**.agent-loop/gates.json** - Gate definitions:
- schema_version, project_id
- gates: dict of gate definitions
- Each gate: enabled, required, description, optional assertion_gate or scope_to_diff
- No command fields — gate logic is in verify-story.sh

### Story Manifest

Each story has a JSON manifest defining:
- `story_id` - Unique identifier
- `allowed_paths` - Regex patterns for files agent can modify
- `forbidden_paths` - Regex patterns for files agent cannot touch
- `gates` - Dict with per-gate {required, enabled, scope_to_diff} config
- `test_commands.targeted_args` - JSON array of pytest arguments (no shell interpolation)
- `acceptance_criteria` - Human-readable requirements
- `repair_hints` - Context for repair iterations

Example: `scripts/agent-loop/templates/story-prd.json`

## Verification Gates

### Assertion Gate (Critical)

The system distinguishes between:
- **PASSED** - Tests executed and assertions passed
- **SKIPPED** - Tests skipped (not counted as PASS)
- **XFAILED** - Expected failures (not counted as PASS)
- **FAILED** - Tests failed
- **ERROR** - Collection/setup errors
- **ZERO COLLECTED** - No tests found (FAIL)

Gate fails if:
- Zero tests collected
- All tests skipped/xfailed (zero passed)
- Any test failed or errored

This prevents false positives from all-skipped test suites.

### Scope Gate

Checks that changes are within allowed paths and don't touch forbidden files.

**Behavior on clean working tree**: SKIP (acceptable for required gates — nothing to verify).

Forbidden by default:
- `.env*` files
- Credentials/secrets
- Source of Truth documents
- Docker compose files
- Database migrations

### JSON Syntax Gate

Validates syntax of all modified/created JSON files.

### Targeted Tests Gate

Runs tests specified in story manifest (`test_commands.targeted_args` as JSON array).

Uses built-in pytest `--junitxml` for structured output (no pytest-json-report plugin required).

### Lint Gate

Runs `ruff` and `mypy` on backend code.

Can be scoped to diff via `scope_to_diff: true` in gate config.

### Secrets Gate

Scans for accidentally committed secrets using inline regex patterns:
- Stripe keys (sk_live_, sk_test_)
- GitHub tokens (ghp_)
- Private keys (BEGIN PRIVATE KEY)
- Password/API key/secret assignments

Can be scoped to diff via `scope_to_diff: true` in gate config.

### Git Diff Check Gate

Runs `git diff --check` for whitespace errors.

## Safety Rules

1. **No auto-commit** - All commits require explicit operator approval
2. **No push/merge** - Forbidden by design
3. **No branch switching** - Each worktree is isolated
4. **No destructive operations** - No `rm -rf`, `git reset --hard`, etc.
5. **No secrets in logs** - Environment loading masks credentials
6. **Worktree isolation** - Agent loop runs in separate worktree, not main repo
7. **Atomic JSON writes** - All reports use tmp+os.replace for crash safety
8. **Cleanup traps** - EXIT/INT/TERM handlers remove temp files

## Artifacts

All logs and reports are stored in:
```
.ralph-tui/artifacts/<story_id>_<timestamp>_<PID>/
  verify/
    scope.log
    json_*.log
    tests.log
    pytest-report.xml
    pytest-stdout.log
    lint.log
    ruff.log
    mypy.log
    diff_check.log
    .gates-tmp.json
    .gate-config-tmp.json
  review/
    (Phase 2)
  repair/
    (Phase 2)
  reports/
    verify-result.json
    review-result.json
    repair-*.json
    final-report.json
```

## Environment

The system loads `.env` safely using Python (no `source .env`):
- Resolves `${VAR}` placeholders
- URL-encodes special characters in passwords
- Exports variables without printing secrets
- Checks database connectivity without exposing credentials

## Current Implementation Status

### Phase 1 (Implemented)

- [x] Worktree isolation
- [x] Configuration system (env overrides, command -v fallback)
- [x] Artifact management (collision-resistant RUN_ID with nanoseconds+PID)
- [x] Environment loading (safe Python parser)
- [x] Scope verification (SKIP on clean tree = PASS)
- [x] JSON syntax checks
- [x] Test execution with assertion gate (JSON array args, no shell splitting)
- [x] Lint checks (ruff + mypy, optional if not installed)
- [x] Secrets scanning (inline regex, portable [[:space:]])
- [x] Main loop orchestrator
- [x] Dry-run mode
- [x] Machine-readable reports (atomic JSON writes)
- [x] Cleanup traps (EXIT/INT/TERM)
- [x] Shared Python harness module (lib/harness.py)
- [x] Comprehensive test scenarios A-O (15 scenarios)

### Phase 2 (Next)

- [ ] Review agent integration (OpenCode)
- [ ] Repair agent integration
- [ ] Failure context collection
- [ ] Story manifest parsing (full implementation)
- [ ] Diff-based test selection (fallback)

## Testing

Run the harness validation suite:

```bash
cd /path/to/forgemind-agent-loop
./scripts/agent-loop/tests/run_harness_scenarios.sh
```

Scenarios A-O test:
- A: required test passes
- B: required test missing
- C: all tests skipped
- D: real tests pass
- E: malformed manifest (ERROR)
- F: zero tests collected
- G: pytest collection error
- H: pytest failure
- I: mixed passed + skipped
- J: optional gate skipped (does not block)
- K: malformed JUnit XML
- L: missing manifest file
- M: test path with spaces
- N: concurrent runs (collision-resistant RUN_ID)
- O: interruption cleanup

## Troubleshooting

### Python/pytest not found

The system auto-detects via `command -v` or uses `MAIN_REPO/.venv/bin/python`.

Override via environment:
```bash
export PYTHON_BIN=/path/to/python
export PYTEST_BIN=/path/to/pytest
```

### Database connectivity issues

Check environment:
```bash
cd /main/repo/path
docker compose ps
```

Ensure Postgres is running and `.env` has correct credentials.

### Scope violations

If agent touches forbidden files:
1. Check story manifest `allowed_paths` and `forbidden_paths`
2. Update manifest if story scope changed
3. Re-run verification

### All tests skipped

If verification fails with "all tests skipped":
1. Check test file exists and is not commented out
2. Verify database connectivity
3. Check test markers (integration tests need DB)
4. Review test conftest.py for skip conditions

### Stale temp files

If verify-story.sh is interrupted, the cleanup trap removes temp files automatically.

Manual cleanup:
```bash
rm -f /tmp/agent-loop-report-*
rm -f .ralph-tui/artifacts/*/verify/.gates-tmp.json
rm -f .ralph-tui/artifacts/*/verify/.gate-config-tmp.json
```
