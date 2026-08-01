# Agent Loop Infrastructure

Autonomous agent-driven development cycle with deterministic verification gates.

## Quick Start

Single command to run a story through the agent loop:

```bash
cd /run/media/toha/Virtual Staff/AgentLab/worktrees/forgemind-agent-loop

# Dry run (verify only, no agent invocation)
./scripts/agent-loop/run-story.sh --dry-run --manifest scripts/agent-loop/templates/story-prd.json

# Full run (implementation + verify + review + repair loop)
./scripts/agent-loop/run-story.sh --manifest scripts/agent-loop/templates/story-prd.json

# With custom max iterations
./scripts/agent-loop/run-story.sh --max-iterations 5 --manifest scripts/agent-loop/templates/story-prd.json
```

## Architecture

### Components

1. **run-story.sh** - Main orchestrator, implements the loop:
   - Implementation (Ralph) → Verification → Review → Repair → Report
   - Max iterations configurable (default: 3)
   - Dry-run mode for testing verification gates without agents

2. **verify-story.sh** - Deterministic verification (no agent):
   - Scope check (allowed/forbidden paths)
   - JSON/YAML syntax validation
   - Targeted tests with assertion gate
   - Lint (ruff + mypy)
   - Secrets scan
   - git diff --check
   - Generates machine-readable JSON report

3. **review-story.sh** - Independent review (Phase 2):
   - Separate OpenCode session
   - Does not trust implementation agent's claims
   - Produces independent verdict

4. **repair-story.sh** - Automatic repair (Phase 2):
   - Receives structured failure report
   - Invokes agent with failure context
   - Iterates up to MAX_REPAIR_ITERATIONS

5. **report-story.sh** - Final report generator:
   - Aggregates all results
   - Machine-readable JSON
   - Human-readable summary

### Configuration

**config.sh** - Shared configuration:
- Agent binaries (Ralph, OpenCode)
- State directories
- Loop limits
- Forbidden/allowed path patterns
- Test/lint commands

**config.gates.json** - Gate definitions:
- Which gates to run
- Gate order
- Gate-specific options

### Story Manifest

Each story has a JSON manifest defining:
- `story_id` - Unique identifier
- `allowed_paths` - Regex patterns for files agent can modify
- `forbidden_paths` - Regex patterns for files agent cannot touch
- `gates_required` - Which verification gates to run
- `test_commands` - Explicit test commands (overrides diff-based selection)
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

Forbidden by default:
- `.env*` files
- Credentials/secrets
- Source of Truth documents
- Docker compose files
- Database migrations

### JSON/YAML Syntax Gate

Validates syntax of all modified/created JSON and YAML files.

### Targeted Tests Gate

Runs tests specified in story manifest or falls back to diff-based selection.

Uses `pytest-json-report` for structured output and assertion counting.

### Lint Gate

Runs `ruff` and `mypy` on backend code.

### Secrets Gate

Scans for accidentally committed secrets using `scripts/check-secrets.sh`.

### Git Diff Check Gate

Runs `git diff --check` for whitespace errors.

## Safety Rules

1. **No auto-commit** - All commits require explicit operator approval
2. **No push/merge** - Forbidden by design
3. **No branch switching** - Each worktree is isolated
4. **No destructive operations** - No `rm -rf`, `git reset --hard`, etc.
5. **No secrets in logs** - Environment loading masks credentials
6. **Worktree isolation** - Agent loop runs in separate worktree, not main repo

## Artifacts

All logs and reports are stored in:
```
.ralph-tui/artifacts/<story_id>_<timestamp>/
  verify/
    scope.log
    json_*.log
    tests.log
    pytest-report.json
    lint.log
    secrets.log
    diff_check.log
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
- [x] Configuration system
- [x] Artifact management
- [x] Environment loading (safe)
- [x] Scope verification
- [x] JSON/YAML syntax checks
- [x] Test execution with assertion gate
- [x] Lint checks
- [x] Secrets scanning
- [x] Main loop orchestrator
- [x] Dry-run mode
- [x] Machine-readable reports

### Phase 2 (Next)

- [ ] Review agent integration (OpenCode)
- [ ] Repair agent integration
- [ ] Failure context collection
- [ ] Story manifest parsing (full implementation)
- [ ] Diff-based test selection (fallback)

## Testing on US-002

Current story: `backend/tests/integration/test_at006_rag_retrieval.py`

Dry run:
```bash
cd /run/media/toha/Virtual Staff/AgentLab/worktrees/forgemind-agent-loop
./scripts/agent-loop/run-story.sh --dry-run --manifest scripts/agent-loop/templates/story-prd.json
```

This will:
1. Load story manifest
2. Run all verification gates
3. Generate reports
4. NOT invoke any agents

Check results in `.ralph-tui/artifacts/US-002_<timestamp>/`

## Troubleshooting

### pytest-json-report not installed

The system will auto-install if missing:
```bash
.venv/bin/pip install pytest-json-report
```

### Database connectivity issues

Check environment:
```bash
cd /run/media/toha/Virtual Staff/VScode/AIAutomation
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
