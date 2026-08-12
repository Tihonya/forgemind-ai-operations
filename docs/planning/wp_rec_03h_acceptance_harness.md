# WP-REC-03H — Phase 5 AT-008 / AT-013 Acceptance Harness

**Status:** PLANNING PACKAGE — implementation-ready specification  
**Date:** 2026-08-12  
**Baseline:** `origin/main` @ `8392ba8fccdafd1ba966019d4301676344b9e3cb` (PR #81 merge commit)  
**Authorizes:** This document authorizes harness implementation only.  
**Does NOT authorize:** Formal AT-008 or AT-013 execution, Phase 5 acceptance declaration, Source of Truth changes, production code changes beyond the minimal acceptance-only injection point.

---

## 1. Objective

Design and specify an implementation-ready acceptance harness that provides formal end-to-end evidence for:

- **AT-008 (Structured output validation):** Deterministic invalid provider output → `FAILED_VALIDATION` transition → failed workflow-step persistence → workflow detail API → frontend trace rendering → absence of persisted `Recommendation` → absence of approval/procurement write actions → continued deterministic risk availability.

- **AT-013 (Model outage):** Deterministic provider unavailability → production error classification → automatic retry attempts and exhaustion → `FAILED_PROVIDER` transition → failed-step persistence → workflow detail API → continued risk availability → frontend usability while polling → polling termination → authorized Retry → dispatch-generation increment → ARQ retry execution → post-Retry success or terminal result → resumed polling → stale Start/Retry and plan-change protections.

The harness must exercise the **real production workflow path** through ARQ worker, PostgreSQL persistence, Redis queue, backend API, frontend polling, and browser rendering. It must not mock backend responses or bypass production state-machine behavior.

---

## 2. Scope

### Included

- Deterministic scenario-control mechanism for AT-008 and AT-013 provider behavior.
- Backend integration tests exercising the real workflow vertical through ARQ worker.
- Playwright end-to-end scenarios for AT-008 and AT-013 with real backend, worker, database, and frontend.
- Process orchestration script for isolated acceptance environment (PostgreSQL, Redis, backend, worker, frontend, Playwright).
- Evidence collection and redaction utilities.
- CI strategy for harness execution.
- Validation command sequence.

### Excluded

- Production code changes beyond the minimal acceptance-only provider injection point.
- Formal AT-008 or AT-013 PASS declaration (requires Product Owner acceptance of evidence).
- Phase 5 acceptance declaration.
- WP-REC-05 (Phase 4 completion), AT-006/AT-007 verification, Phase 6, SP-0B, or any unrelated package.
- Source of Truth or Decision Log changes.
- Documentation lifecycle reconciliation (deferred).

---

## 3. Repository Analysis

### 3.1 Provider Configuration Path

**Current production path:**

1. `backend/app/config.py` line 75: `embedding_provider: Literal["openai", "fake"] = "openai"`
2. `backend/app/ai/provider/factory.py` line 140: `name = provider_name if provider_name is not None else effective_config.embedding_provider`
3. Line 142-148: When `name == "fake"`, creates `FakeChatProvider` wrapped in `RetryingChatProvider`.
4. `backend/app/ai/workflow/worker.py` line 146: `provider = create_chat_provider()` — uses global settings.

**Critical finding:** The setting is named `embedding_provider` but controls the **chat provider** selection. This is a naming quirk from WP-REC-03A but functionally correct.

**FakeChatProvider behavior:**
- Returns deterministic JSON: `{"prompt_hash": "...", "model": "fake-chat-model", "schema_requested": true}`
- **Does NOT return valid `RecommendationData` schema** — will fail validation at `validate_structured_output()`.
- Perfect for AT-008 invalid-output path.

### 3.2 Workflow Execution Path

**Vertical execution sequence** (`backend/app/ai/workflow/vertical.py`):

1. Load `WorkflowRun` (lines 117-128).
2. Generation-guarded `PENDING → RUNNING` transition (lines 131-143).
3. Load `ProductionPlan` (lines 146-164).
4. Deterministic risk calculation via `analyze_plan()` (lines 169-211) — persisted independently of provider.
5. Build prompt and call provider (lines 219-257).
6. **On provider success:**
   - Transition `RUNNING → AWAITING_VALIDATION` (line 270).
   - Validate structured output (lines 282-284).
   - **On validation success:** Persist `Recommendation` (lines 315-323), transition `AWAITING_VALIDATION → COMPLETED` (line 339).
   - **On validation failure:** Record validation step (lines 287-299), transition to `FAILED_VALIDATION` (lines 301-305).
7. **On provider failure:**
   - Record failed step (lines 352-356).
   - Transition to `FAILED_PROVIDER` or `FAILED_INTERNAL` (lines 363-368).

**Retry path** (`backend/app/api/workflow.py` lines 379-500):

1. Authorization check: run creator OR `PRODUCTION_MANAGER` (lines 431-453).
2. State eligibility check: `FAILED_PROVIDER`, `FAILED_VALIDATION`, `FAILED_INTERNAL` (lines 456-469).
3. Atomic conditional `FAILED_* → PENDING` transition with dispatch-generation increment (lines 472-498).
4. Enqueue ARQ retry job with deterministic job ID `workflow:{run_id}:{dispatch_generation}` (lines 501-545).

### 3.3 Database and Session Management

**Application database singleton** (`backend/app/database.py`):

- Module-level `engine` and `async_session_factory` read `settings.database_url` at import time (lines 21-36).
- `get_async_session()` FastAPI dependency yields sessions from the factory (lines 39-52).

**Worker database usage** (`backend/app/ai/workflow/worker.py`):

- Line 143: `async with async_session_factory() as session:` — uses the same module-level factory.

**Integration test pattern** (`backend/tests/integration/conftest.py`):

- `reset_app_db_pool` fixture disposes the app engine before/after each test (lines 13-26).
- Integration tests create their own engines via `TEST_DATABASE_URL` or `DATABASE_URL`.

### 3.4 Existing Test Coverage

**AT-008 partial coverage:**

- ✅ Unit tests: `backend/tests/unit/test_schema_validator.py` — validator logic.
- ✅ Integration tests: `backend/tests/integration/test_workflow_start_retry.py` — `FAILED_VALIDATION` path via `_SuccessProvider` (but no invalid-output fixture).
- ❌ No end-to-end test through ARQ worker + API + browser.
- ❌ No deterministic fixture exercising real workflow path with invalid output.
- ❌ No browser-level evidence showing trace rendering.

**AT-013 partial coverage:**

- ✅ Unit tests: `backend/tests/unit/test_retry_policy.py`, `test_outage_handler.py` — retry wrapper logic.
- ✅ Integration tests: `backend/tests/integration/test_provider_outage.py` — `FAILED_PROVIDER` + retry via `_ScriptedProvider`.
- ✅ Integration tests: `backend/tests/integration/test_workflow_start_retry.py` — retry from `FAILED_PROVIDER`.
- ❌ No end-to-end test through ARQ worker + API + browser.
- ❌ No browser-level evidence showing outage, retry exhaustion, user Retry, dispatch-generation increment, post-retry success, polling termination/resumption.

### 3.5 Frontend Workflow Interaction

**Workflow polling and retry** (`frontend/src/hooks/useWorkflowRun.tsx`):

- Polls `GET /api/v1/workflow-runs/{run_id}` every 2 seconds when state is `PENDING` or `RUNNING`.
- Stops polling when state reaches terminal state (`COMPLETED`, `FAILED_*`).
- Retry button visible only to run creator or `PRODUCTION_MANAGER`.
- Plan-change guard: suppresses stale Start/Retry completions.

**Workflow detail rendering** (`frontend/src/routes/supply-risk-detail.tsx`):

- Displays workflow trace with steps, states, timestamps, error codes.
- Shows recommendation when present.
- Shows retry button when eligible.

---

## 4. Harness Architecture

### 4.1 Deterministic Scenario Control

**Decision:** Add a test-only scenario registry in `backend/app/ai/provider/factory.py` guarded by environment check.

**Rationale:**

- Minimal production code change (one conditional block).
- Clearly guarded: `if settings.environment not in ("production", "staging")`.
- Test-only path: inaccessible in production/staging.
- Concurrency-safe: scenario state is per-process, not global mutable state.
- Observable in evidence: scenario name logged in worker startup.

**Implementation:**

```python
# backend/app/ai/provider/factory.py (proposed addition after line 156)

# Acceptance-test scenario registry (test-only, guarded by environment check).
# Maps scenario names to provider factory callables.
_ACCEPTANCE_SCENARIOS: dict[str, Callable[[Settings], ChatProvider]] = {}

def register_acceptance_scenario(
    name: str,
    factory: Callable[[Settings], ChatProvider],
) -> None:
    """Register a test-only provider scenario for acceptance harness."""
    if settings.environment in ("production", "staging"):
        raise ChatProviderConfigurationError(
            f"Acceptance scenarios not allowed in {settings.environment}"
        )
    _ACCEPTANCE_SCENARIOS[name] = factory

def create_chat_provider(
    config: Settings | None = None,
    *,
    provider_name: str | None = None,
) -> ChatProvider:
    effective_config = config if config is not None else application_settings
    
    # Check for acceptance scenario override (test-only).
    scenario_name = os.environ.get("FORGEMIND_ACCEPTANCE_SCENARIO")
    if scenario_name and scenario_name in _ACCEPTANCE_SCENARIOS:
        if effective_config.environment in ("production", "staging"):
            raise ChatProviderConfigurationError(
                f"Acceptance scenarios not allowed in {effective_config.environment}"
            )
        delegate = _ACCEPTANCE_SCENARIOS[scenario_name](effective_config)
        return _wrap_with_retry(delegate, effective_config)
    
    # ... existing provider selection logic ...
```

**Scenarios to register:**

1. **`AT008_INVALID_OUTPUT`:** Provider returns invalid JSON or schema-invalid output.
   - Use existing `FakeChatProvider` (already returns invalid schema).
   - Or create `_InvalidOutputProvider` that returns `{"invalid": "data"}`.

2. **`AT013_OUTAGE_UNTIL_RETRY`:** Provider fails transiently on first dispatch generation (0), succeeds on retry generation (1+).
   - Create `_OutageUntilRetryProvider` that tracks dispatch generation from context.
   - Raises `TransientChatProviderError` when `dispatch_generation == 0`.
   - Returns valid `RecommendationData` when `dispatch_generation >= 1`.

3. **`NORMAL_SUCCESS`:** Control scenario — provider returns valid output immediately.
   - Create `_ValidOutputProvider` that returns valid `RecommendationData` JSON.

**Dispatch generation tracking:**

The provider receives `context["run_id"]` but not `dispatch_generation`. The harness must:

- Parse dispatch generation from ARQ job ID in worker logs.
- Or add `dispatch_generation` to the provider context in `worker.py` (minimal change).

**Proposed minimal change to `backend/app/ai/workflow/worker.py` line 242:**

```python
context: dict[str, Any] = {
    "correlation_id": str(run.correlation_id),
    "run_id": str(run.id),
    "dispatch_generation": run.dispatch_generation,  # Added for acceptance harness
}
```

This change is safe: the context dict is provider-specific metadata, not part of the public API contract.

### 4.2 Database Isolation

**Decision:** Use a dedicated `forgemind_acceptance` database with explicit environment variable propagation.

**Isolation strategy:**

1. **Database creation:** Orchestration script creates `forgemind_acceptance` database via `createdb` or Docker exec.
2. **Environment variable:** Set `TEST_DATABASE_URL=postgresql+asyncpg://forgemind:forgemind@localhost:5433/forgemind_acceptance`.
3. **Propagation:** All processes (backend, worker, tests, Playwright) read `TEST_DATABASE_URL`.
4. **Migrations:** Run `alembic upgrade head` on `forgemind_acceptance` before tests.
5. **Seed:** Run seed generator on `forgemind_acceptance` to populate golden dataset.

**Idempotent preparation:**

```python
# Orchestration script (proposed)
def prepare_acceptance_database(db_url: str) -> None:
    """Create database if not exists, run migrations, seed."""
    # 1. Check if database exists via pg_database query.
    # 2. If not, create via CREATE DATABASE.
    # 3. Run alembic upgrade head.
    # 4. Run seed generator.
```

**Precondition:** PostgreSQL must be running on port 5433 (or configured port). The orchestration script starts a dedicated PostgreSQL container.

### 4.3 Redis Isolation

**Decision:** Use Redis database 1 (or dedicated port 6380) with explicit environment variable propagation.

**Isolation strategy:**

1. **Redis URL:** Set `REDIS_URL=redis://localhost:6380/0` (dedicated port).
2. **Propagation:** All processes read `REDIS_URL`.
3. **ARQ worker:** Reads `settings.redis_url` which is set from `REDIS_URL`.

**Rationale:** Separate port avoids accidental collision with development Redis on 6379.

### 4.4 Process Orchestration

**Decision:** Python orchestration script with subprocess management and health checks.

**Orchestration sequence:**

1. **Start PostgreSQL:**
   - Docker container: `docker run -d --name forgemind-acceptance-pg -p 5433:5432 -e POSTGRES_DB=forgemind_acceptance -e POSTGRES_USER=forgemind -e POSTGRES_PASSWORD=forgemind postgres:16`.
   - Health check: `pg_isready -h localhost -p 5433` (poll up to 30 seconds).

2. **Start Redis:**
   - Docker container: `docker run -d --name forgemind-acceptance-redis -p 6380:6379 redis:7`.
   - Health check: `redis-cli -p 6380 ping` (poll up to 10 seconds).

3. **Prepare database:**
   - Run Alembic migrations: `alembic upgrade head`.
   - Run seed generator: `python -m app.seed.generator.main`.

4. **Start backend API:**
   - Command: `uvicorn app.main:app --host 0.0.0.0 --port 8001`.
   - Environment: `TEST_DATABASE_URL`, `REDIS_URL`, `FORGEMIND_ACCEPTANCE_SCENARIO`, `ENVIRONMENT=development`.
   - Health check: `curl http://localhost:8001/health` (poll up to 30 seconds).

5. **Start ARQ worker:**
   - Command: `arq app.worker.WorkerSettings`.
   - Environment: Same as backend.
   - Health check: Monitor logs for "worker started" message (poll up to 30 seconds).

6. **Start frontend:**
   - Command: `npm run dev -- --port 5174`.
   - Environment: `VITE_API_BASE_URL=http://localhost:8001`.
   - Health check: `curl http://localhost:5174` (poll up to 30 seconds).

7. **Run Playwright tests:**
   - Command: `npm run test:e2e -- --project=acceptance`.
   - Environment: `PLAYWRIGHT_BASE_URL=http://localhost:5174`.

8. **Collect evidence:**
   - API responses, database queries, worker logs, browser screenshots, Playwright traces.

9. **Teardown:**
   - Stop processes in reverse order.
   - Remove Docker containers.

**Failure propagation:**

- If any process fails to start, abort and teardown.
- If Playwright tests fail, collect evidence before teardown.
- Log all process stdout/stderr to files.

**Safe teardown:**

- Use `docker stop` and `docker rm` (not `docker compose down -v`).
- Kill subprocesses via `process.terminate()` with timeout.

### 4.5 Backend Integration Tests

**Decision:** Add dedicated AT-008 and AT-013 integration tests exercising the real workflow vertical through ARQ worker.

**AT-008 backend test** (`backend/tests/integration/test_at008_acceptance.py`):

```python
async def test_at008_invalid_output_via_worker(
    db_session: AsyncSession,
    arq_pool: ArqRedis,
) -> None:
    """AT-008: Invalid provider output → FAILED_VALIDATION via real worker."""
    # 1. Set FORGEMIND_ACCEPTANCE_SCENARIO=AT008_INVALID_OUTPUT.
    # 2. Create WorkflowRun via API or direct ORM.
    # 3. Enqueue ARQ job.
    # 4. Wait for worker to process (poll database state).
    # 5. Assert final state is FAILED_VALIDATION.
    # 6. Assert workflow_steps contain validation failure.
    # 7. Assert no Recommendation row exists.
    # 8. Assert risk API still returns deterministic risks.
```

**AT-013 backend test** (`backend/tests/integration/test_at013_acceptance.py`):

```python
async def test_at013_outage_retry_via_worker(
    db_session: AsyncSession,
    arq_pool: ArqRedis,
) -> None:
    """AT-013: Provider outage → FAILED_PROVIDER → user Retry → success."""
    # 1. Set FORGEMIND_ACCEPTANCE_SCENARIO=AT013_OUTAGE_UNTIL_RETRY.
    # 2. Create WorkflowRun.
    # 3. Enqueue ARQ start job (generation 0).
    # 4. Wait for worker to process → FAILED_PROVIDER.
    # 5. Assert workflow_steps contain provider failure with retry exhaustion.
    # 6. Assert risk API still returns deterministic risks.
    # 7. Perform user Retry via API (POST /workflow-runs/{run_id}/retry).
    # 8. Assert dispatch_generation incremented to 1.
    # 9. Wait for worker to process retry job (generation 1) → COMPLETED.
    # 10. Assert Recommendation row exists.
    # 11. Assert workflow_steps are append-only (prior steps preserved).
```

**Test fixtures:**

- `arq_pool` fixture: Creates ARQ Redis pool for job enqueue.
- `worker_process` fixture: Starts ARQ worker subprocess with scenario environment.
- `wait_for_terminal_state` helper: Polls database until workflow reaches terminal state (with timeout).

### 4.6 Playwright Scenarios

**Decision:** Two independently reviewable Playwright scenarios with real backend, worker, database, and frontend.

**AT-008 Playwright scenario** (`frontend/e2e/at008-acceptance.spec.ts`):

```typescript
test("AT-008: validation failure visible in trace", async ({ page }) => {
  // 1. Authenticate as production_manager.demo.
  // 2. Navigate to supply risk detail page for PLAN-2026-W31.
  // 3. Verify deterministic risks are visible (RISK-001, RISK-002, RISK-003).
  // 4. Click "Start AI Analysis" button.
  // 5. Wait for workflow state to reach FAILED_VALIDATION (poll API or observe UI).
  // 6. Verify workflow trace shows:
  //    - provider_call step with status "completed" or "failed".
  //    - validation step with status "failed" and error_code "VALIDATION_FAILED".
  // 7. Verify no recommendation section is rendered.
  // 8. Verify "Retry" button is visible (user is run creator).
  // 9. Verify deterministic risks remain visible (not blocked by workflow failure).
  // 10. Take screenshot of trace.
  // 11. Assert API response for GET /workflow-runs/{run_id} matches UI state.
});
```

**AT-013 Playwright scenario** (`frontend/e2e/at013-acceptance.spec.ts`):

```typescript
test("AT-013: provider outage and user retry", async ({ page }) => {
  // 1. Authenticate as production_manager.demo.
  // 2. Navigate to supply risk detail page for PLAN-2026-W31.
  // 3. Verify deterministic risks are visible.
  // 4. Click "Start AI Analysis" button.
  // 5. Wait for workflow state to reach FAILED_PROVIDER (poll API or observe UI).
  // 6. Verify workflow trace shows:
  //    - provider_call step with status "failed" and error_code "PROVIDER_TRANSIENT".
  //    - error_detail "ProviderError" (safe value, no secrets).
  // 7. Verify no recommendation section is rendered.
  // 8. Verify "Retry" button is visible.
  // 9. Verify deterministic risks remain visible.
  // 10. Take screenshot of failed state.
  // 11. Click "Retry" button.
  // 12. Wait for workflow state to reach COMPLETED (poll API or observe UI).
  // 13. Verify workflow trace shows:
  //     - Prior failed steps preserved (append-only).
  //     - New provider_call step with status "completed".
  //     - New validation step with status "completed".
  // 14. Verify recommendation section is rendered with valid data.
  // 15. Take screenshot of success state.
  // 16. Assert API response for GET /workflow-runs/{run_id} matches UI state.
  // 17. Verify dispatch_generation in API response is 1 (incremented by retry).
});
```

**Real end-to-end boundary:**

- ✅ Real browser (Playwright).
- ✅ Real frontend (React app).
- ✅ Real backend API (FastAPI + uvicorn).
- ✅ Real PostgreSQL persistence.
- ✅ Real Redis queue.
- ✅ Real ARQ worker.
- ✅ Real provider adapter and retry wrapper (via scenario registry).
- ✅ Real workflow state machine and trace persistence.
- ❌ External provider API (replaced by deterministic scenario provider).

**Justification for provider simulation:**

The acceptance test proves the **workflow behavior** (state transitions, error handling, retry logic, trace persistence, UI rendering) — not the external provider's actual API. The scenario provider exercises the same code paths as a real provider (same exceptions, same result structure) without network dependency or secret exposure.

### 4.7 Evidence Collection

**Decision:** Python evidence collector with deterministic failure handling, redaction, run identity, and artifact integrity.

**Evidence categories:**

1. **Repository baseline:**
   - Git SHA, dirty-state check, branch name.
   - Command: `git rev-parse HEAD`, `git status --porcelain`.

2. **Environment versions:**
   - Python version, Node version, Docker version, PostgreSQL version, Redis version.
   - Command: `python --version`, `node --version`, `docker --version`, `psql --version`, `redis-server --version`.

3. **Scenario identity:**
   - Scenario name, run ID, correlation ID, dispatch generation.
   - Source: Test metadata and API responses.

4. **State transitions:**
   - Workflow run state history from database.
   - Command: `SELECT state, updated_at FROM workflow_runs WHERE id = :run_id`.

5. **Workflow steps:**
   - All workflow steps with seq, step_name, status, error_code, error_detail.
   - Command: `SELECT * FROM workflow_steps WHERE run_id = :run_id ORDER BY seq`.

6. **Provider attempt count:**
   - From worker logs: count of `chat_provider.retry.attempt` log entries.
   - Source: Worker stdout log file.

7. **Dispatch generation:**
   - From API response: `GET /workflow-runs/{run_id}` → `dispatch_generation` field.

8. **Recommendation absence/presence:**
   - From database: `SELECT COUNT(*) FROM recommendations WHERE run_id = :run_id`.

9. **Controlled-write absence:**
   - From database: `SELECT COUNT(*) FROM procurement_tasks WHERE run_id = :run_id` (should be 0 for Phase 5).

10. **Risk API availability:**
    - From API response: `GET /api/v1/risks?plan_id=PLAN-2026-W31` → verify 3 risks returned.

11. **Browser screenshots:**
    - Playwright screenshots at key moments (failed state, success state).

12. **Playwright traces:**
    - Playwright trace.zip files for failed tests.

13. **Final database checks:**
    - Workflow run final state, step count, recommendation count.

14. **Test counts:**
    - pytest pass/fail/skip counts, Playwright pass/fail counts.

15. **Redaction result:**
    - Verify no secrets, tokens, or API keys in evidence files.
    - Command: `grep -E "(sk-[a-zA-Z0-9]{20,}|Bearer|password)" evidence/*` (should be empty).

16. **Final repository status:**
    - Git status after evidence collection (should show only evidence files).

**Evidence lifecycle:**

1. **Raw artifacts:** Written to `evidence/raw/{run_id}/` (temporary, not committed).
2. **Redacted artifacts:** Written to `evidence/redacted/{run_id}/` (reviewable, may be committed later).
3. **Cleanup:** Raw artifacts deleted after redaction; redacted artifacts retained for review.
4. **Integrity:** SHA-256 checksums for all redacted artifacts written to `evidence/redacted/{run_id}/checksums.sha256`.

**Evidence collector implementation:**

```python
# backend/tests/acceptance/evidence_collector.py (proposed)

class EvidenceCollector:
    def __init__(self, run_id: str, scenario: str, output_dir: Path):
        self.run_id = run_id
        self.scenario = scenario
        self.raw_dir = output_dir / "raw" / run_id
        self.redacted_dir = output_dir / "redacted" / run_id
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.redacted_dir.mkdir(parents=True, exist_ok=True)
    
    def collect_api_response(self, name: str, response: dict) -> None:
        """Save API response to raw and redacted directories."""
        raw_path = self.raw_dir / f"{name}.json"
        redacted_path = self.redacted_dir / f"{name}.json"
        raw_path.write_text(json.dumps(response, indent=2))
        redacted = self._redact_secrets(response)
        redacted_path.write_text(json.dumps(redacted, indent=2))
    
    def collect_database_query(self, name: str, query: str, results: list) -> None:
        """Save database query results."""
        # Similar to API response.
    
    def collect_screenshot(self, name: str, screenshot_path: Path) -> None:
        """Copy Playwright screenshot to evidence directories."""
        # Copy to raw and redacted (screenshots don't need redaction).
    
    def compute_checksums(self) -> None:
        """Compute SHA-256 checksums for all redacted artifacts."""
        checksums = []
        for path in self.redacted_dir.glob("*"):
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            checksums.append(f"{checksum}  {path.name}")
        (self.redacted_dir / "checksums.sha256").write_text("\n".join(checksums))
    
    def _redact_secrets(self, data: Any) -> Any:
        """Recursively redact secrets from JSON-like data."""
        # Replace values matching secret patterns with "[REDACTED]".
```

**Repository cleanliness:**

- Evidence files are written to `evidence/` directory (gitignored).
- `.gitignore` must include `evidence/raw/` and `evidence/redacted/`.
- Protected audit file `docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md` remains the sole pre-existing untracked entry.
- After evidence collection, `git status --porcelain` should show only the protected audit file.

---

## 5. File-Level Implementation Plan

### 5.1 Production Code Changes (Minimal)

**File:** `backend/app/ai/provider/factory.py`  
**Change:** Add acceptance scenario registry and environment-variable check.  
**Lines:** ~20 lines added after line 156.  
**Scope:** Test-only, guarded by environment check.  
**Risk:** Low — no production behavior change, clearly isolated.

**File:** `backend/app/ai/workflow/worker.py`  
**Change:** Add `dispatch_generation` to provider context (line 242).  
**Lines:** 1 line added.  
**Scope:** Metadata propagation, not part of public API contract.  
**Risk:** Low — context dict is provider-specific.

### 5.2 Backend Test Files

**File:** `backend/tests/integration/test_at008_acceptance.py`  
**Purpose:** AT-008 backend integration test via real ARQ worker.  
**Key symbols:** `test_at008_invalid_output_via_worker`.  
**AT clauses:** AT-008 (all clauses).  
**Scope:** Integration test.  
**Expected coverage:** 1 test, ~100 lines.

**File:** `backend/tests/integration/test_at013_acceptance.py`  
**Purpose:** AT-013 backend integration test via real ARQ worker.  
**Key symbols:** `test_at013_outage_retry_via_worker`.  
**AT clauses:** AT-013 (all clauses).  
**Scope:** Integration test.  
**Expected coverage:** 1 test, ~150 lines.

**File:** `backend/tests/integration/conftest.py`  
**Change:** Add `arq_pool`, `worker_process`, `wait_for_terminal_state` fixtures.  
**Lines:** ~100 lines added.  
**Scope:** Test infrastructure.

**File:** `backend/tests/acceptance/evidence_collector.py`  
**Purpose:** Evidence collection and redaction utilities.  
**Key symbols:** `EvidenceCollector` class.  
**Scope:** Test infrastructure.  
**Expected coverage:** ~200 lines.

**File:** `backend/tests/acceptance/scenarios.py`  
**Purpose:** Scenario provider implementations (`_InvalidOutputProvider`, `_OutageUntilRetryProvider`, `_ValidOutputProvider`).  
**Key symbols:** Provider classes and registration function.  
**Scope:** Test infrastructure.  
**Expected coverage:** ~150 lines.

### 5.3 Playwright Test Files

**File:** `frontend/e2e/at008-acceptance.spec.ts`  
**Purpose:** AT-008 browser scenario.  
**Key symbols:** `test("AT-008: validation failure visible in trace")`.  
**AT clauses:** AT-008 (UI clauses).  
**Scope:** End-to-end test.  
**Expected coverage:** 1 test, ~80 lines.

**File:** `frontend/e2e/at013-acceptance.spec.ts`  
**Purpose:** AT-013 browser scenario.  
**Key symbols:** `test("AT-013: provider outage and user retry")`.  
**AT clauses:** AT-013 (UI clauses).  
**Scope:** End-to-end test.  
**Expected coverage:** 1 test, ~120 lines.

**File:** `frontend/playwright.config.ts`  
**Change:** Add `acceptance` project with dedicated base URL and timeout.  
**Lines:** ~10 lines added.  
**Scope:** Test configuration.

### 5.4 Orchestration Script

**File:** `scripts/acceptance_harness.py`  
**Purpose:** Process orchestration for isolated acceptance environment.  
**Key symbols:** `run_acceptance_harness()` main function.  
**Scope:** Orchestration.  
**Expected coverage:** ~400 lines.

**Responsibilities:**

- Start PostgreSQL and Redis containers.
- Prepare database (migrations, seed).
- Start backend, worker, frontend.
- Run backend integration tests.
- Run Playwright tests.
- Collect evidence.
- Teardown.

### 5.5 Configuration Files

**File:** `.gitignore`  
**Change:** Add `evidence/raw/` and `evidence/redacted/`.  
**Lines:** 2 lines added.  
**Scope:** Repository configuration.

**File:** `Makefile`  
**Change:** Add `acceptance-test` target.  
**Lines:** ~10 lines added.  
**Scope:** Build automation.

**Target definition:**

```makefile
acceptance-test: ## Run acceptance harness for AT-008 and AT-013
	@echo "Running acceptance harness..."
	python scripts/acceptance_harness.py
	@echo "Acceptance harness complete. Evidence in evidence/redacted/"
```

### 5.6 Documentation Files

**File:** `docs/planning/wp_rec_03h_acceptance_harness.md`  
**Purpose:** This planning document.  
**Scope:** Planning.

**File:** `docs/ACCEPTANCE_HARNESS.md` (proposed, optional)  
**Purpose:** User guide for running the acceptance harness.  
**Scope:** Documentation.  
**Expected coverage:** ~100 lines.

---

## 6. CI Strategy

**Decision:** Acceptance harness runs manually or via dedicated workflow, not on every PR.

**Rationale:**

- **Runtime cost:** ~5-10 minutes (container startup, migrations, seed, tests, teardown).
- **Service availability:** Requires Docker, PostgreSQL, Redis — not all CI runners have these.
- **Determinism:** Scenario providers are deterministic, but container startup timing may vary.
- **Artifact retention:** Evidence files are large (screenshots, traces) — not suitable for every PR.
- **Secret-free execution:** No real API keys, but environment setup is complex.
- **Flaky-test risk:** Low (deterministic scenarios), but container startup failures possible.

**CI workflow** (proposed, optional):

```yaml
# .github/workflows/acceptance-harness.yml (proposed)
name: Acceptance Harness

on:
  workflow_dispatch:  # Manual trigger only
  # Or: push to specific branch like "acceptance/wp-rec-03h"

jobs:
  acceptance:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: forgemind_acceptance
          POSTGRES_USER: forgemind
          POSTGRES_PASSWORD: forgemind
        ports:
          - 5433:5432
      redis:
        image: redis:7
        ports:
          - 6380:6379
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - uses: actions/setup-node@v4
        with:
          node-version: "22"
      - run: python scripts/acceptance_harness.py
      - uses: actions/upload-artifact@v4
        with:
          name: acceptance-evidence
          path: evidence/redacted/
```

**Integration with existing CI:**

- Existing backend unit/integration tests run on every PR (no change).
- Existing frontend unit tests run on every PR (no change).
- Existing Playwright E2E tests run on every PR (no change — they use mocked backend).
- Acceptance harness tests are **separate** and run only via dedicated workflow.

---

## 7. Test Matrix

| Test Type | Scope | Runs On | Command |
|-----------|-------|---------|---------|
| Backend unit tests | All backend unit tests | Every PR | `cd backend && ../.venv/bin/pytest tests/unit/` |
| Backend integration tests | All backend integration tests | Every PR | `cd backend && ../.venv/bin/pytest tests/integration/` |
| AT-008 backend acceptance | AT-008 via real worker | Manual/dedicated workflow | `cd backend && ../.venv/bin/pytest tests/integration/test_at008_acceptance.py` |
| AT-013 backend acceptance | AT-013 via real worker | Manual/dedicated workflow | `cd backend && ../.venv/bin/pytest tests/integration/test_at013_acceptance.py` |
| Frontend unit tests | All frontend unit tests | Every PR | `cd frontend && npm test` |
| Playwright E2E tests | Existing E2E tests (mocked backend) | Every PR | `cd frontend && npm run test:e2e` |
| AT-008 Playwright acceptance | AT-008 browser scenario | Manual/dedicated workflow | `cd frontend && npm run test:e2e -- --project=acceptance at008-acceptance.spec.ts` |
| AT-013 Playwright acceptance | AT-013 browser scenario | Manual/dedicated workflow | `cd frontend && npm run test:e2e -- --project=acceptance at013-acceptance.spec.ts` |
| Full acceptance harness | All acceptance tests + evidence | Manual/dedicated workflow | `make acceptance-test` |

---

## 8. Validation Commands

**Pre-implementation validation (this planning package):**

```bash
# Verify repository identity
git remote -v | grep Tihonya/forgemind-ai-operations

# Verify starting branch and HEAD
git branch --show-current
git rev-parse HEAD

# Verify protected audit identity
sha256sum docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md
wc -l docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md
wc -c docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md

# Verify no unrelated changes
git status --porcelain

# Verify planning document exists
ls -la docs/planning/wp_rec_03h_acceptance_harness.md

# Verify no syntax errors in planning document
python -m markdown docs/planning/wp_rec_03h_acceptance_harness.md > /dev/null

# Verify diff contains only planning document
git diff --cached --name-only
```

**Post-implementation validation (harness implementation package):**

```bash
# Run backend unit tests (should still pass)
cd backend && ../.venv/bin/pytest tests/unit/ -v

# Run backend integration tests (should still pass)
cd backend && ../.venv/bin/pytest tests/integration/ -v

# Run frontend unit tests (should still pass)
cd frontend && npm test

# Run existing Playwright E2E tests (should still pass)
cd frontend && npm run test:e2e

# Run AT-008 backend acceptance test (new)
cd backend && ../.venv/bin/pytest tests/integration/test_at008_acceptance.py -v

# Run AT-013 backend acceptance test (new)
cd backend && ../.venv/bin/pytest tests/integration/test_at013_acceptance.py -v

# Run full acceptance harness (new)
make acceptance-test

# Verify evidence collected
ls -la evidence/redacted/
cat evidence/redacted/*/checksums.sha256

# Verify repository cleanliness (only protected audit + evidence files)
git status --porcelain
```

---

## 9. Stop Conditions

The harness implementation must stop and report if:

1. **Production code change exceeds minimal injection point:** More than 2 files changed in `backend/app/` (excluding tests).
2. **Test isolation failure:** Acceptance tests modify production database or Redis.
3. **Evidence redaction failure:** Secrets, tokens, or API keys found in evidence files.
4. **Determinism failure:** Scenario providers produce non-deterministic output across runs.
5. **Container startup failure:** PostgreSQL or Redis containers fail to start within timeout.
6. **Migration failure:** Alembic migrations fail on `forgemind_acceptance` database.
7. **Seed failure:** Seed generator fails to populate golden dataset.
8. **Worker startup failure:** ARQ worker fails to start or connect to Redis.
9. **Test timeout:** Backend acceptance tests or Playwright scenarios exceed timeout (5 minutes each).
10. **Evidence collection failure:** Evidence collector fails to write artifacts or compute checksums.

---

## 10. Rollback Approach

**If harness implementation fails:**

1. Revert all changes via `git reset --hard HEAD`.
2. Remove Docker containers: `docker rm -f forgemind-acceptance-pg forgemind-acceptance-redis`.
3. Delete evidence directory: `rm -rf evidence/`.
4. Report failure with exact error message and stop condition triggered.

**If harness execution fails:**

1. Stop all processes (orchestration script handles this).
2. Remove Docker containers.
3. Retain evidence for debugging (in `evidence/raw/`).
4. Report failure with test output and error logs.

---

## 11. Security Constraints

The harness implementation and execution must ensure:

1. **Synthetic data only:** No real corporate, military, or confidential data.
2. **No real provider API calls:** Scenario providers do not make network requests.
3. **No real API keys:** Environment variables use sentinel values or empty strings.
4. **No secret values in artifacts:** Evidence collector redacts all secrets before saving.
5. **No uncontrolled external outage dependency:** Scenario providers simulate outages deterministically.
6. **No normal development or production database mutation:** Isolated `forgemind_acceptance` database.
7. **No deletion of Docker volumes:** Use `docker stop` and `docker rm`, not `docker compose down -v`.
8. **No database recreation:** Orchestration script creates database if not exists, does not drop.
9. **No installation into running containers:** All dependencies installed via `pip` or `npm` before container start.
10. **No privilege or authorization bypass:** Tests use demo accounts with appropriate roles.
11. **No weakening of backend role enforcement:** Production RBAC unchanged.
12. **No acceptance-only route exposed in production:** Scenario registry guarded by environment check.
13. **Safe user-facing errors only:** Error messages do not expose secrets or stack traces.
14. **Deterministic teardown limited to harness-owned resources:** Only stop containers and processes started by harness.

---

## 12. Definition of Done

The harness implementation is complete when:

1. ✅ All files in Section 5 are created or modified as specified.
2. ✅ Backend unit tests pass (no regressions).
3. ✅ Backend integration tests pass (no regressions).
4. ✅ Frontend unit tests pass (no regressions).
5. ✅ Existing Playwright E2E tests pass (no regressions).
6. ✅ AT-008 backend acceptance test passes.
7. ✅ AT-013 backend acceptance test passes.
8. ✅ AT-008 Playwright acceptance scenario passes.
9. ✅ AT-013 Playwright acceptance scenario passes.
10. ✅ Full acceptance harness runs successfully via `make acceptance-test`.
11. ✅ Evidence collected in `evidence/redacted/` with checksums.
12. ✅ No secrets, tokens, or API keys in evidence files.
13. ✅ Repository cleanliness: only protected audit file and evidence files untracked.
14. ✅ Lint passes: `make lint`.
15. ✅ No production code changes beyond minimal injection point (2 files, ~21 lines).

**The harness implementation does NOT:**

- Declare AT-008 or AT-013 PASS.
- Declare Phase 5 acceptance.
- Modify Source of Truth or Decision Log.
- Authorize formal acceptance execution.

---

## 13. Authorization Boundary

**This planning package authorizes:**

- Harness implementation (files listed in Section 5).
- Harness execution via `make acceptance-test`.
- Evidence collection and redaction.

**This planning package does NOT authorize:**

- Formal AT-008 or AT-013 PASS declaration (requires Product Owner acceptance of evidence).
- Phase 5 acceptance declaration.
- Source of Truth or Decision Log changes.
- Documentation lifecycle reconciliation (deferred).
- WP-REC-05, AT-006/AT-007 verification, Phase 6, SP-0B, or any unrelated package.

**Formal acceptance execution requires:**

1. Harness implementation reviewed and merged.
2. Product Owner authorizes formal execution.
3. Formal execution package runs harness and collects evidence.
4. Product Owner reviews evidence and declares AT-008/AT-013 PASS.
5. Phase 5 acceptance declared.
6. Documentation lifecycle reconciliation performed.

---

## 14. Implementation Package Contract

### 14.1 Objective

Implement the acceptance harness specified in this document.

### 14.2 Included Scope

- All files listed in Section 5.
- All validation commands in Section 8.
- All stop conditions in Section 9.

### 14.3 Excluded Scope

- Formal AT-008 or AT-013 execution.
- Phase 5 acceptance declaration.
- Source of Truth or Decision Log changes.
- Documentation lifecycle reconciliation.

### 14.4 Prerequisites

- Docker installed and running.
- Python 3.12+ with venv at `/home/toha/Projects/forgemind-ai-operations/.venv/`.
- Node 22+ with npm.
- PostgreSQL 16 client tools (`psql`, `pg_isready`).
- Redis client tools (`redis-cli`).

### 14.5 Exact File Scope

See Section 5.

### 14.6 Deterministic Scenario-Control Design

See Section 4.1.

### 14.7 Database and Redis Isolation Design

See Sections 4.2 and 4.3.

### 14.8 Process-Orchestration Design

See Section 4.4.

### 14.9 Backend Integration-Test Design

See Section 4.5.

### 14.10 Playwright Scenario Design

See Section 4.6.

### 14.11 Evidence Collector Design

See Section 4.7.

### 14.12 CI Strategy

See Section 6.

### 14.13 Test Matrix

See Section 7.

### 14.14 Validation Commands

See Section 8.

### 14.15 Stop Conditions

See Section 9.

### 14.16 Rollback Approach

See Section 10.

### 14.17 Security Constraints

See Section 11.

### 14.18 Definition of Done

See Section 12.

### 14.19 Explicit Authorization Boundary

See Section 13.

### 14.20 Exact Next Action After Implementation Review

After harness implementation is reviewed and merged:

1. Product Owner authorizes formal acceptance execution package.
2. Formal execution package runs harness and collects evidence.
3. Product Owner reviews evidence and declares AT-008/AT-013 PASS.
4. Phase 5 acceptance declared.
5. Documentation lifecycle reconciliation performed (separate package).

---

## 15. Required Plan Conclusions

### 15.1 Is WP-REC-03H the correct bounded package name and scope?

**Yes.** WP-REC-03H is the correct name and scope. It follows the WP-REC-03 series (Phase 5 AI Workflow) and is bounded to AT-008 and AT-013 acceptance harness only. It does not expand into WP-REC-05 (Phase 4 completion), AT-006/AT-007 verification, Phase 6, or any unrelated package.

### 15.2 Can the harness be implemented without production-code changes?

**No, but with minimal changes.** Two production files require changes:

1. `backend/app/ai/provider/factory.py`: Add acceptance scenario registry (~20 lines).
2. `backend/app/ai/workflow/worker.py`: Add `dispatch_generation` to provider context (1 line).

Both changes are test-only, guarded by environment checks, and do not affect production behavior.

### 15.3 What exact mechanism selects deterministic chat-provider behavior?

**Environment variable `FORGEMIND_ACCEPTANCE_SCENARIO`** checked in `create_chat_provider()` after line 140. When set to `AT008_INVALID_OUTPUT`, `AT013_OUTAGE_UNTIL_RETRY`, or `NORMAL_SUCCESS`, the factory returns a scenario-specific provider from the registry. The registry is guarded by `if settings.environment not in ("production", "staging")`.

### 15.4 How are the backend API and ARQ worker guaranteed to share the same provider scenario?

Both processes read the same `FORGEMIND_ACCEPTANCE_SCENARIO` environment variable. The orchestration script sets this variable before starting both processes. The worker calls `create_chat_provider()` which checks the environment variable and returns the scenario provider.

### 15.5 How is the acceptance database isolated from the development database?

**Dedicated database `forgemind_acceptance`** on port 5433 (or configured port). All processes read `TEST_DATABASE_URL=postgresql+asyncpg://forgemind:forgemind@localhost:5433/forgemind_acceptance`. The orchestration script creates the database, runs migrations, and seeds the golden dataset before starting tests.

### 15.6 How is Redis state isolated?

**Dedicated Redis on port 6380** (or configured port). All processes read `REDIS_URL=redis://localhost:6380/0`. The orchestration script starts a dedicated Redis container.

### 15.7 How does AT-013 fail before Retry and succeed after Retry without race-prone global state?

**Dispatch-generation-aware scenario provider.** The `_OutageUntilRetryProvider` receives `dispatch_generation` in the provider context (added in Section 4.1). When `dispatch_generation == 0`, it raises `TransientChatProviderError`. When `dispatch_generation >= 1`, it returns valid `RecommendationData`. This is per-process state (the provider instance), not global mutable state. Each ARQ job creates a fresh provider instance, so there is no shared state across jobs.

### 15.8 Which Playwright interactions are real end-to-end rather than mocked?

**All interactions are real** except the external provider API:

- ✅ Real browser (Playwright).
- ✅ Real frontend (React app).
- ✅ Real backend API (FastAPI + uvicorn).
- ✅ Real PostgreSQL persistence.
- ✅ Real Redis queue.
- ✅ Real ARQ worker.
- ✅ Real provider adapter and retry wrapper (via scenario registry).
- ✅ Real workflow state machine and trace persistence.
- ❌ External provider API (replaced by deterministic scenario provider).

### 15.9 Where are raw evidence artifacts written?

**`evidence/raw/{run_id}/`** (temporary, gitignored, deleted after redaction).

### 15.10 Which evidence artifacts, if any, are later committed?

**None are committed automatically.** The `evidence/redacted/{run_id}/` directory contains reviewable artifacts that **may** be committed later by a separate documentation lifecycle package, but this is not authorized by WP-REC-03H.

### 15.11 How is repository cleanliness evaluated while evidence exists?

**Git status check:** `git status --porcelain` should show only:

1. The protected audit file: `docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md`.
2. The evidence directories: `evidence/raw/` and `evidence/redacted/` (gitignored).

No other untracked or modified files are permitted.

### 15.12 What is the exact implementation file list?

See Section 5. Summary:

**Production code (2 files):**

1. `backend/app/ai/provider/factory.py` (modify).
2. `backend/app/ai/workflow/worker.py` (modify).

**Backend tests (5 files):**

3. `backend/tests/integration/test_at008_acceptance.py` (create).
4. `backend/tests/integration/test_at013_acceptance.py` (create).
5. `backend/tests/integration/conftest.py` (modify).
6. `backend/tests/acceptance/evidence_collector.py` (create).
7. `backend/tests/acceptance/scenarios.py` (create).

**Playwright tests (3 files):**

8. `frontend/e2e/at008-acceptance.spec.ts` (create).
9. `frontend/e2e/at013-acceptance.spec.ts` (create).
10. `frontend/playwright.config.ts` (modify).

**Orchestration and configuration (3 files):**

11. `scripts/acceptance_harness.py` (create).
12. `.gitignore` (modify).
13. `Makefile` (modify).

**Documentation (1 file, optional):**

14. `docs/ACCEPTANCE_HARNESS.md` (create, optional).

### 15.13 What is the exact validation command sequence?

See Section 8. Summary:

```bash
# Pre-implementation (this planning package)
git remote -v | grep Tihonya/forgemind-ai-operations
git branch --show-current
git rev-parse HEAD
sha256sum docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md
wc -l docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md
wc -c docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md
git status --porcelain
ls -la docs/planning/wp_rec_03h_acceptance_harness.md
git diff --cached --name-only

# Post-implementation (harness implementation package)
cd backend && ../.venv/bin/pytest tests/unit/ -v
cd backend && ../.venv/bin/pytest tests/integration/ -v
cd frontend && npm test
cd frontend && npm run test:e2e
cd backend && ../.venv/bin/pytest tests/integration/test_at008_acceptance.py -v
cd backend && ../.venv/bin/pytest tests/integration/test_at013_acceptance.py -v
make acceptance-test
ls -la evidence/redacted/
cat evidence/redacted/*/checksums.sha256
git status --porcelain
```

### 15.14 Does harness implementation require CI changes?

**No, but optional.** The harness can run manually via `make acceptance-test`. An optional CI workflow (`.github/workflows/acceptance-harness.yml`) can be added later for automated execution, but this is not required for harness implementation.

### 15.15 What later package will execute formal acceptance?

**WP-REC-03H-EXEC** (proposed name) or a similar formal execution package. This package will:

1. Run the harness via `make acceptance-test`.
2. Collect evidence.
3. Submit evidence to Product Owner for review.
4. Product Owner declares AT-008/AT-013 PASS.
5. Phase 5 acceptance declared.

### 15.16 What conditions block formal acceptance execution?

Formal acceptance execution is blocked if:

1. Harness implementation is not reviewed and merged.
2. Harness execution fails (test failures, evidence collection failures).
3. Evidence contains secrets, tokens, or API keys.
4. Evidence does not demonstrate all AT-008 and AT-013 clauses.
5. Product Owner does not authorize formal execution.

---

## 16. Unresolved Questions

**None.** All design decisions are resolved and specified in this document.

---

## 17. Lifecycle and Authorization Boundary Confirmation

**This planning package:**

- ✅ Authorizes harness implementation.
- ✅ Authorizes harness execution via `make acceptance-test`.
- ✅ Authorizes evidence collection and redaction.
- ❌ Does NOT authorize formal AT-008 or AT-013 PASS declaration.
- ❌ Does NOT authorize Phase 5 acceptance declaration.
- ❌ Does NOT authorize Source of Truth or Decision Log changes.
- ❌ Does NOT authorize documentation lifecycle reconciliation.
- ❌ Does NOT authorize WP-REC-05, AT-006/AT-007 verification, Phase 6, SP-0B, or any unrelated package.

**Harness implementation completion:**

- Merging the harness implementation PR does NOT declare AT-008 or AT-013 PASS.
- It only provides the tooling to collect evidence.

**Harness execution:**

- Running `make acceptance-test` collects evidence but does NOT declare PASS.
- Evidence must be reviewed by Product Owner.

**Product Owner acceptance:**

- Product Owner reviews evidence and explicitly declares AT-008/AT-013 PASS.
- Phase 5 acceptance is declared separately.

**Documentation lifecycle reconciliation:**

- Deferred to a separate package after Phase 5 acceptance.

---

## 18. Recommended Next Action

**After this planning package is reviewed and approved:**

Authorize harness implementation package with the following scope:

- Implement all files listed in Section 5.
- Run all validation commands in Section 8.
- Collect evidence via `make acceptance-test`.
- Submit implementation PR for review.

**Do NOT authorize:**

- Formal AT-008 or AT-013 execution.
- Phase 5 acceptance declaration.
- Source of Truth or Decision Log changes.
- Documentation lifecycle reconciliation.

---

**End of WP-REC-03H Planning Document**
