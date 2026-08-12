# WP-REC-03H — Phase 5 AT-008 / AT-013 Acceptance Harness

**Status:** PLANNING PACKAGE — implementation-ready specification (corrected)
**Date:** 2026-08-12
**Corrected:** 2026-08-12 (remediation of independent review findings 1–8, then remediation of final re-review findings 1–5)
**Baseline:** `origin/main` @ `8392ba8fccdafd1ba966019d4301676344b9e3cb` (PR #81 merge commit)
**Authorizes:** This document is an implementation-ready **specification only**. It does not authorize harness implementation, harness execution, evidence collection, or any code changes.
**Does NOT authorize:** Harness implementation, harness execution, formal AT-008 or AT-013 execution, Phase 5 acceptance declaration, Source of Truth changes, or any other action.

---

## 0. Lifecycle Phases

This plan defines five strictly separated lifecycle phases. No earlier phase authorizes a later phase.

### Phase A — Planning (this document)

- Produce an implementation-ready specification.
- No code, no tests, no containers, no evidence.
- Ends when this planning PR is reviewed and merged.

### Phase B — Harness Implementation (requires separate authorization after Phase A merge)

- Implement the harness code, tests, orchestration, and configuration.
- Run ordinary unit, integration, lint, type, and implementation-verification tests.
- Prove that orchestration, deterministic controls, and evidence utilities are correctly implemented.
- Create a draft implementation PR.
- **Must NOT:** collect formal acceptance evidence, declare AT-008/AT-013 PASS, declare Phase 5 accepted, or run the harness in formal-evidence mode.
- Ends when the implementation PR is reviewed and merged.

### Phase C — Formal Acceptance Execution (requires separate authorization after Phase B merge)

- Run the reviewed and merged harness against the approved isolated environment in formal-evidence mode.
- Collect the authoritative evidence package.
- **Must NOT:** itself declare AT-008 or AT-013 PASS.
- Ends when evidence is submitted for Product Owner review.

### Phase D — Product Owner Evidence Review and Acceptance Declaration

- Product Owner reviews the evidence package.
- Product Owner explicitly declares AT-008 and/or AT-013 PASS.
- Product Owner declares Phase 5 acceptance.
- **Must NOT:** be automated or assumed from test results.

### Phase E — Documentation Lifecycle Reconciliation (requires separate authorization after Phase D)

- Update ACTIVE_WORK, next_steps, requirements_traceability_matrix, wp_rec_03_decomposition, and other lifecycle documents.
- Separate package.

---

## 1. Objective

Design and specify an implementation-ready acceptance harness that can later provide formal end-to-end evidence for:

- **AT-008 (Structured output validation):** Deterministic invalid provider output → `FAILED_VALIDATION` transition → failed workflow-step persistence → workflow detail API → frontend trace rendering → absence of persisted `Recommendation` → absence of controlled write actions → continued deterministic risk availability.

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

- Formal AT-008 or AT-013 PASS declaration (requires Phase D).
- Phase 5 acceptance declaration.
- WP-REC-05 (Phase 4 completion), AT-006/AT-007 verification, Phase 6, SP-0B, or any unrelated package.
- Source of Truth or Decision Log changes.
- Documentation lifecycle reconciliation (Phase E).

---

## 3. Repository Analysis

### 3.1 Provider Configuration Path

**Current production path:**

1. `backend/app/config.py` line 75: `embedding_provider: Literal["openai", "fake"] = "openai"` — the setting named `embedding_provider` controls the chat provider selection (WP-REC-03A naming convention, functionally correct).
2. `backend/app/ai/provider/factory.py` line 140: `name = provider_name if provider_name is not None else effective_config.embedding_provider`.
3. Lines 142–148: When `name == "fake"`, creates `FakeChatProvider` wrapped in `RetryingChatProvider`.
4. `backend/app/ai/workflow/worker.py` line 146: `provider = create_chat_provider()` — uses global settings singleton.

**FakeChatProvider behavior** (`backend/app/ai/provider/fake_chat_provider.py`):

- Returns deterministic JSON: `{"prompt_hash": "...", "model": "fake-chat-model", "schema_requested": true}`.
- **Does NOT return valid `RecommendationData` schema** — will fail validation at `validate_structured_output()`.
- Suitable for AT-008 invalid-output path.

### 3.2 Workflow Execution Path

**Vertical execution sequence** (`backend/app/ai/workflow/vertical.py`):

1. Load `WorkflowRun` (lines 117–128).
2. Generation-guarded `PENDING → RUNNING` transition (lines 131–143).
3. Load `ProductionPlan` (lines 146–164).
4. Deterministic risk calculation via `analyze_plan()` (lines 169–211) — persisted independently of provider.
5. Build prompt and call provider (lines 219–257).
   - **Provider context is constructed at `vertical.py` lines 242–245**, not in `worker.py`.
   - Context dict: `{"correlation_id": str(run.correlation_id), "run_id": str(run.id)}`.
   - `dispatch_generation` is **not** currently included in the context.
6. **On provider success:**
   - Transition `RUNNING → AWAITING_VALIDATION` (line 270).
   - Validate structured output (lines 282–284).
   - **On validation success:** Persist `Recommendation` (lines 315–323), transition `AWAITING_VALIDATION → COMPLETED` (line 339).
   - **On validation failure:** Record validation step (lines 287–299), transition to `FAILED_VALIDATION` (lines 301–305).
7. **On provider failure:**
   - Record failed step (lines 352–356).
   - Transition to `FAILED_PROVIDER` or `FAILED_INTERNAL` (lines 363–368).

**Retry path** (`backend/app/api/workflow.py` lines 379–545):

1. Authorization check: run creator OR `PRODUCTION_MANAGER` (lines 431–453).
2. State eligibility check: `FAILED_PROVIDER`, `FAILED_VALIDATION`, `FAILED_INTERNAL` (lines 456–469).
3. Atomic conditional `FAILED_* → PENDING` transition with dispatch-generation increment (lines 472–498).
4. Enqueue ARQ retry job with deterministic job ID `workflow:{run_id}:{dispatch_generation}` (lines 501–545).

### 3.3 Database and Session Management

**Application database singleton** (`backend/app/database.py`):

- Module-level `engine` and `async_session_factory` read `settings.database_url` at import time (lines 21–36).
- `settings.database_url` is populated from the `DATABASE_URL` environment variable (Pydantic BaseSettings).
- `get_async_session()` FastAPI dependency yields sessions from the factory (lines 39–52).

**Worker database usage** (`backend/app/ai/workflow/worker.py`):

- Line 143: `async with async_session_factory() as session:` — uses the same module-level factory from `database.py`.
- The factory is initialized at module import from `settings.database_url`, which reads `DATABASE_URL`.

**Alembic environment** (`backend/alembic/env.py`):

- Line 46: `config.set_main_option("sqlalchemy.url", _to_sync_url(settings.database_url))`.
- Alembic reads `settings.database_url`, which reads `DATABASE_URL`.

**Seed loader** (`backend/app/seed/generator/loader.py`):

- Line 56: `sync_url = settings.database_url`.
- The loader reads `settings.database_url`, which reads `DATABASE_URL`.
- Module-level `_sync_engine` is created at import time (line 64).

**Critical finding:** All production processes (backend API, ARQ worker, Alembic, seed loader) consume `DATABASE_URL` through `settings.database_url`. The environment variable `TEST_DATABASE_URL` is **not** automatically consumed by any of these production processes. Integration tests read `TEST_DATABASE_URL` directly via `os.environ.get("TEST_DATABASE_URL")` and create their own engines — they do not use the application's module-level engine.

**Integration test pattern** (`backend/tests/integration/conftest.py`):

- `reset_app_db_pool` fixture disposes the app engine before/after each test (lines 13–26).
- Integration tests create their own engines via `os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")`.

### 3.4 ARQ Worker Configuration

**Entry point** (`backend/app/worker.py`):

- `WorkerSettings` class (line 72) registers functions via `arq.func(...)`.
- Redis connection from `settings.redis_url` (populated from `REDIS_URL` env var).
- Worker started via: `arq app.worker.WorkerSettings`.

**Worker execution path** (`backend/app/ai/workflow/worker.py`):

- `_do_execute()` (line 115) creates a fresh session and provider per job.
- Line 146: `provider = create_chat_provider()` — creates provider through the production factory using the global settings singleton.
- Line 149: `result = await execute_workflow(session=session, provider=provider, run_id=run_uuid, queued_generation=queued_generation)`.

### 3.5 Existing Test Coverage

**AT-008 partial coverage:**

- ✅ Unit tests: `backend/tests/unit/test_schema_validator.py` — validator logic.
- ✅ Integration tests: `backend/tests/integration/test_workflow_start_retry.py` — `FAILED_VALIDATION` path via `_SuccessProvider` (but no invalid-output fixture exercising the real factory path).
- ❌ No end-to-end test through ARQ worker + API + browser.
- ❌ No deterministic fixture exercising real workflow path with invalid output through the production factory.
- ❌ No browser-level evidence showing trace rendering.

**AT-013 partial coverage:**

- ✅ Unit tests: `backend/tests/unit/test_retry_policy.py`, `test_outage_handler.py` — retry wrapper logic.
- ✅ Integration tests: `backend/tests/integration/test_provider_outage.py` — `FAILED_PROVIDER` + retry via `_ScriptedProvider`.
- ✅ Integration tests: `backend/tests/integration/test_workflow_start_retry.py` — retry from `FAILED_PROVIDER`.
- ❌ No end-to-end test through ARQ worker + API + browser.
- ❌ No browser-level evidence showing outage, retry exhaustion, user Retry, dispatch-generation increment, post-retry success, polling termination/resumption.

### 3.6 Frontend Workflow Interaction

**Workflow hooks** (`frontend/src/hooks/`):

- `use-workflow-run.ts`: Polls `GET /api/v1/workflow-runs/{run_id}` every 2 seconds when state is `PENDING` or `RUNNING`. Stops polling when state reaches terminal state (`COMPLETED`, `FAILED_*`).
- `use-workflow-start.ts`: POST `/api/v1/workflow-runs` to start a workflow.
- `use-workflow-retry.ts`: POST `/api/v1/workflow-runs/{run_id}/retry` to retry a failed workflow.

**Workflow detail rendering** (`frontend/src/routes/supply-risk-detail.tsx`):

- Displays workflow trace with steps, states, timestamps, error codes.
- Shows recommendation when present.
- Shows retry button when eligible (run creator or `PRODUCTION_MANAGER`).

**Playwright configuration** (`frontend/playwright.config.ts`):

- `baseURL`: `process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:4173'`.
- `webServer`: `npm run preview` on port 4173 (uses Vite preview, not dev server).
- Existing E2E tests (`golden-scenario.spec.ts`) run against the preview server.

### 3.7 API Response Verification

**`dispatch_generation` in API responses:** Confirmed. `WorkflowRunSchema` (`backend/app/schemas/workflow.py` line 130) includes `dispatch_generation: int`. `WorkflowRunDetailResponse` extends `WorkflowRunSchema` and inherits this field. `WorkflowRunSummarySchema` also includes it (line 248).

**Workflow steps as audit trail:** Confirmed. `WorkflowStep` model (`backend/app/models/workflow.py` line 223) provides persistent append-only step records with `seq`, `step_name`, `status`, `error_code`, `error_detail`, `started_at`, `completed_at`.

**Log event for retry attempts:** `chat_provider.retry.attempt` (verified at `backend/app/ai/workflow/outage_handler.py` line 289).

---

## 4. Harness Architecture

### 4.1 Deterministic Scenario Control

**Decision:** Create a dedicated acceptance-scenarios module inside the application package, guarded by environment check, loaded by the production factory.

**Rationale:** The independently started ARQ worker process imports `backend/app/ai/provider/factory.py` through the normal import chain. It does **not** import test packages (`backend/tests/`). Therefore, scenario provider implementations must reside in a module the worker actually loads. A test-only bootstrap cannot safely provide the seam because the worker process has no mechanism to import from `backend/tests/acceptance/`.

**Design: Guarded acceptance-only provider module**

Create a new production module (guarded, not test-only):

**Proposed file:** `backend/app/ai/provider/acceptance_scenarios.py`

This module:

- Defines scenario provider classes (`InvalidOutputProvider`, `OutageUntilRetryProvider`, `ValidOutputProvider`).
- Exports a `get_acceptance_provider(scenario_name: str, settings: Settings) -> ChatProvider` function.
- Is imported by `factory.py` only when `FORGEMIND_ACCEPTANCE_SCENARIO` is set.
- Raises `ChatProviderConfigurationError` for unknown scenario names (fail closed).
- Is guarded by an environment check: the import and usage only occur when `settings.environment` is `"development"`.

**Proposed change to `backend/app/ai/provider/factory.py`:**

**Insertion point:** After the `name` and `effective_config` variables are resolved (after line 140: `name = provider_name if provider_name is not None else effective_config.embedding_provider`) and **before** the first normal-provider branch (`if name == "fake":` at line 142). This ensures the acceptance override is evaluated before any supported-provider return path.

The current control flow is:

```
line 138: effective_config = config if config is not None else application_settings
line 140: name = provider_name if provider_name is not None else effective_config.embedding_provider
line 142: if name == "fake":        ← returns from here
line 150: if name == "openai":      ← returns from here
line 154: raise ChatProviderConfigurationError(...)
```

The override must be inserted **between line 140 and line 142**, so that when `FORGEMIND_ACCEPTANCE_SCENARIO` is set, the factory returns the acceptance provider before reaching any normal provider branch:

```python
# --- Acceptance scenario override (development-only, fail-closed). ---
# Inserted after line 140 (name resolution), before line 142 (first branch).
import os as _os
_acceptance_scenario = _os.environ.get("FORGEMIND_ACCEPTANCE_SCENARIO")
if _acceptance_scenario:
    if effective_config.environment in ("production", "staging"):
        raise ChatProviderConfigurationError(
            "Acceptance scenarios are not available in "
            f"{effective_config.environment}"
        )
    # Import only when the env var is set — no import cost in production.
    from app.ai.provider.acceptance_scenarios import get_acceptance_provider
    delegate = get_acceptance_provider(_acceptance_scenario, effective_config)
    return _wrap_with_retry(delegate, effective_config)
# --- End acceptance override. Normal provider selection continues below. ---
```

**Fail-closed guarantees:**

1. **Unknown scenario name:** `get_acceptance_provider()` raises `ChatProviderConfigurationError` if the name is not recognized. No fallback to normal provider.
2. **Environment guard:** If `FORGEMIND_ACCEPTANCE_SCENARIO` is set but `environment` is `production` or `staging`, the factory raises before importing the module.
3. **No real provider call possible:** When the env var is set and environment is `development`, the factory returns the acceptance provider before reaching the `if name == "fake"` or `if name == "openai"` branches. No external provider client is constructed.
4. **Import guard:** The `acceptance_scenarios` module is imported lazily (only when env var is set), so production deployments without the env var never load it.
5. **Deterministic:** Scenario selection is determined entirely by the env var value. No mutable global registry.
6. **Normal behavior unchanged:** When `FORGEMIND_ACCEPTANCE_SCENARIO` is not set, the override block is skipped entirely and the existing `fake`/`openai` selection logic runs unchanged.

**Concurrency safety:**

- Each ARQ job creates a fresh provider instance via `create_chat_provider()` (worker.py line 146).
- The scenario name is read from the environment variable, which is process-wide and immutable during the job.
- No shared mutable state between jobs — the scenario classes are stateless (except `OutageUntilRetryProvider` which reads `dispatch_generation` from the per-call context).

**Scenarios:**

1. **`AT008_INVALID_OUTPUT`:** Returns invalid JSON or schema-invalid output.
   - Uses `FakeChatProvider` (already returns invalid schema) or a dedicated `InvalidOutputProvider` returning `{"invalid": "data"}`.

2. **`AT013_OUTAGE_UNTIL_RETRY`:** Fails transiently on dispatch generation 0, succeeds on generation ≥ 1.
   - `OutageUntilRetryProvider` reads `context["dispatch_generation"]` (see §4.1.1).
   - Raises `TransientChatProviderError` when `dispatch_generation == 0`.
   - Returns valid `RecommendationData` JSON when `dispatch_generation >= 1`.

3. **`NORMAL_SUCCESS`:** Control scenario — returns valid `RecommendationData` immediately.
   - `ValidOutputProvider` returns valid JSON matching the recommendation wire schema.

#### 4.1.1 Dispatch Generation Propagation

**Verified production behavior:** The provider context dict is constructed in `backend/app/ai/workflow/vertical.py` at lines 242–245:

```python
context: dict[str, Any] = {
    "correlation_id": str(run.correlation_id),
    "run_id": str(run.id),
}
```

The `execute_workflow()` function already receives `queued_generation` as a parameter (line 91). The `dispatch_generation` value is available as `queued_generation` at the point where the context is constructed.

**Proposed change to `backend/app/ai/workflow/vertical.py` line 242–245:**

```python
context: dict[str, Any] = {
    "correlation_id": str(run.correlation_id),
    "run_id": str(run.id),
    "dispatch_generation": queued_generation,  # Added for acceptance harness
}
```

This is a 1-line addition at the correct location. The `queued_generation` parameter is already available in scope. The context dict is provider-specific metadata, not part of any public API contract.

**Why not `worker.py`:** The previous plan incorrectly targeted `worker.py` line 242. That file does not construct the provider context — it delegates to `execute_workflow()` in `vertical.py`. The context dict shown in the previous plan's code sketch does not exist in `worker.py`.

### 4.2 Database Isolation

**Decision:** Use a dedicated `forgemind_acceptance` database. Set `DATABASE_URL` (not `TEST_DATABASE_URL`) for all application subprocesses.

**Verified consumption paths:**

| Consumer | Reads | Source |
|----------|-------|--------|
| Backend API (`database.py`) | `settings.database_url` | `DATABASE_URL` |
| ARQ worker (`database.py` via `worker.py`) | `settings.database_url` | `DATABASE_URL` |
| Alembic (`alembic/env.py` line 46) | `settings.database_url` | `DATABASE_URL` |
| Seed loader (`loader.py` line 56) | `settings.database_url` | `DATABASE_URL` |
| Integration tests (own engine) | `os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")` | Either |

**Isolation strategy:**

1. **Harness-internal variable:** The orchestration script defines `ACCEPTANCE_DATABASE_URL` internally.
2. **Mandatory mapping:** Before starting any subprocess, the orchestration script sets `DATABASE_URL=$ACCEPTANCE_DATABASE_URL` in that subprocess's environment.
3. **Module-level initialization:** The orchestration script must ensure `DATABASE_URL` is set **before** any Python process imports `app.database` or `app.config`, because these modules create engines at import time from `settings.database_url`.
4. **All processes receive the same URL:** Backend API, ARQ worker, Alembic, seed loader, and evidence queries all receive the identical `DATABASE_URL`.

**Mandatory fail-closed checks (before migration, seed, API startup, worker startup, or evidence queries):**

```python
# Proposed: orchestration script fail-closed checks
def validate_acceptance_database_url(db_url: str) -> None:
    """Fail-closed validation of acceptance database URL."""
    from urllib.parse import urlparse
    parsed = urlparse(db_url)

    # 1. Host must be localhost or 127.0.0.1
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        raise RuntimeError(f"Acceptance DB host must be localhost, got {parsed.hostname}")

    # 2. Port must be the acceptance port (5433), not the development port (5432)
    if parsed.port == 5432:
        raise RuntimeError("Acceptance DB must not use development port 5432")

    # 3. Database name must be exactly 'forgemind_acceptance'
    db_name = parsed.path.lstrip("/")
    if db_name != "forgemind_acceptance":
        raise RuntimeError(f"Acceptance DB name must be 'forgemind_acceptance', got '{db_name}'")

    # 4. Must not be a production or staging endpoint
    if "production" in db_url or "staging" in db_url:
        raise RuntimeError("Acceptance DB URL must not reference production or staging")

    # 5. Confirm the URL is propagated to all consumers
    #    (verified by querying the database from each subprocess)
```

**Idempotent preparation:**

```python
# Proposed: orchestration script
def prepare_acceptance_database(db_url: str) -> None:
    """Create database if not exists, run migrations, seed."""
    validate_acceptance_database_url(db_url)
    # 1. Check if database exists via pg_database query on the server.
    # 2. If not, create via CREATE DATABASE.
    # 3. Set DATABASE_URL for Alembic subprocess.
    # 4. Run: alembic upgrade head (subprocess with DATABASE_URL set).
    # 5. Set DATABASE_URL for seed subprocess.
    # 6. Run: python -m app.seed.generator.main (subprocess with DATABASE_URL set).
```

**Precondition:** PostgreSQL must be running on port 5433 (or configured acceptance port). The orchestration script starts a dedicated PostgreSQL container.

### 4.3 Redis Isolation

**Decision:** Use a dedicated Redis on port 6380. Set `REDIS_URL` for all application subprocesses.

**Verified consumption paths:**

| Consumer | Reads | Source |
|----------|-------|--------|
| ARQ worker (`worker.py` line 69) | `settings.redis_url` | `REDIS_URL` |
| Backend API workflow endpoints (`api/workflow.py` line 218) | `settings.redis_url` | `REDIS_URL` |

**Isolation strategy:**

1. **Redis URL:** Set `REDIS_URL=redis://localhost:6380/0` (dedicated port).
2. **Propagation:** All processes receive `REDIS_URL` in their environment.
3. **Separate port:** Avoids accidental collision with development Redis on 6379.

**Mandatory fail-closed checks (before backend API startup, ARQ worker startup, or any enqueue operation):**

```python
# Proposed: orchestration script fail-closed checks
def validate_acceptance_redis_url(redis_url: str) -> None:
    """Fail-closed validation of acceptance Redis URL."""
    from urllib.parse import urlparse
    parsed = urlparse(redis_url)

    # 1. Scheme must be redis:// or rediss://
    if parsed.scheme not in ("redis", "rediss"):
        raise RuntimeError(f"Acceptance Redis scheme must be redis:// or rediss://, got {parsed.scheme}")

    # 2. Host must be localhost or 127.0.0.1
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        raise RuntimeError(f"Acceptance Redis host must be localhost, got {parsed.hostname}")

    # 3. Port must be exactly 6380 (acceptance port), not 6379 (development port)
    if parsed.port == 6379:
        raise RuntimeError("Acceptance Redis must not use development port 6379")
    if parsed.port != 6380:
        raise RuntimeError(f"Acceptance Redis port must be 6380, got {parsed.port}")

    # 4. Must not reference production or staging
    if "production" in redis_url or "staging" in redis_url:
        raise RuntimeError("Acceptance Redis URL must not reference production or staging")

    # 5. Confirm the URL is propagated to all consumers
    #    (verified by querying Redis INFO from each subprocess)
```

### 4.4 Process Orchestration

**Decision:** Python orchestration script with subprocess management, run-scoped resource identity, and health checks.

#### 4.4.1 Run Identity and Resource Ownership

Every harness invocation generates a unique run identifier:

```python
# Proposed: run identity
import uuid
run_id = f"acc-{uuid.uuid4().hex[:12]}"
```

All resources created by the harness are tagged with this run ID:

- Docker container names: `forgemind-{run_id}-pg`, `forgemind-{run_id}-redis`.
- Log files: `evidence/{run_id}/logs/`.
- Evidence artifacts: `evidence/{run_id}/`.

**Ownership verification before teardown:**

Before stopping or removing any resource, the orchestration script must verify that the resource was created by the current run using **exact label matching**, not substring or name matching:

```python
# Proposed: ownership check (exact label match)
def owns_container(container_name: str, run_id: str) -> bool:
    """Verify the container was created by this run via exact label match."""
    result = subprocess.run(
        [
            "docker", "inspect",
            "--format", "{{index .Config.Labels \"forgemind-run\"}}",
            container_name,
        ],
        capture_output=True, text=True,
    )
    label_value = result.stdout.strip()
    # Exact equality — no substring, prefix, or fuzzy matching.
    return label_value == run_id
```

The `forgemind-run` label is set at container creation time (see §4.4.2). If the label is absent, empty, or does not exactly equal the current `run_id`, the container is **not owned** by this run and must not be stopped or removed.

**Port conflict handling:** If the preferred port (5433 or 6380) is already occupied, the orchestration script must:

1. Check if the occupying process is owned by a previous harness run (via container name pattern).
2. If owned by a previous run: refuse to proceed and report the conflict.
3. If not owned by a harness run: refuse to proceed and report the external conflict.
4. Do **not** silently kill or replace pre-existing resources.

#### 4.4.2 Orchestration Sequence

1. **Generate run ID** and create evidence directory `evidence/{run_id}/`.

2. **Start PostgreSQL:**
   - Container: `docker run -d --name forgemind-{run_id}-pg --label forgemind-run={run_id} -p 5433:5432 -e POSTGRES_DB=forgemind_acceptance -e POSTGRES_USER=forgemind -e POSTGRES_PASSWORD=forgemind postgres:16`.
   - Health check: `pg_isready -h localhost -p 5433` (poll up to 30 seconds).

3. **Start Redis:**
   - Container: `docker run -d --name forgemind-{run_id}-redis --label forgemind-run={run_id} -p 6380:6379 redis:7`.
   - Health check: `redis-cli -p 6380 ping` (poll up to 10 seconds).

4. **Prepare database (with `DATABASE_URL` set to acceptance URL):**
   - Validate URL via `validate_acceptance_database_url()`.
   - Run Alembic migrations: `alembic upgrade head` (subprocess with `DATABASE_URL` set).
   - Run seed generator: `python -m app.seed.generator.main` (subprocess with `DATABASE_URL` set).

5. **Start backend API:**
   - Command: `uvicorn app.main:app --host 0.0.0.0 --port 8001`.
   - Environment: `DATABASE_URL=<acceptance_url>`, `REDIS_URL=redis://localhost:6380/0`, `FORGEMIND_ACCEPTANCE_SCENARIO=<scenario>`, `ENVIRONMENT=development`.
   - Health check: `curl http://localhost:8001/health` (poll up to 30 seconds).

6. **Start ARQ worker:**
   - Command: `arq app.worker.WorkerSettings`.
   - Environment: Same as backend (identical `DATABASE_URL`, `REDIS_URL`, `FORGEMIND_ACCEPTANCE_SCENARIO`).
   - Health check: Monitor logs for `on_startup` hook completion (poll up to 30 seconds).

7. **Start frontend:**
   - Command: `npm run dev -- --port 5174`.
   - Environment: `VITE_API_BASE_URL=http://localhost:8001`.
   - Health check: `curl http://localhost:5174` (poll up to 30 seconds).

8. **Run tests** (see §4.5 and §4.6).

9. **Collect evidence** (see §4.7).

10. **Teardown:**
    - Stop subprocesses via `process.terminate()` with timeout.
    - Stop and remove only containers owned by this run (verified via ownership check).
    - Do **not** delete volumes.
    - Do **not** run `docker compose down -v`.
    - Do **not** run broad Docker cleanup.

**Failure propagation:**

- If any process fails to start, abort and teardown owned resources only.
- If tests fail, collect evidence before teardown.
- Log all process stdout/stderr to `evidence/{run_id}/logs/`.

### 4.5 Backend Integration Tests

**Decision:** Add dedicated AT-008 and AT-013 integration tests exercising the real workflow vertical.

**Implementation-verification mode (Phase B):**

The implementation package runs these tests to prove the harness works correctly. The test results are implementation-verification evidence, **not** formal acceptance evidence.

**AT-008 backend test** (proposed: `backend/tests/integration/test_at008_acceptance.py`):

```python
async def test_at008_invalid_output_via_worker(
    db_session: AsyncSession,
    arq_pool: ArqRedis,
) -> None:
    """AT-008: Invalid provider output → FAILED_VALIDATION via real worker."""
    # 1. Set FORGEMIND_ACCEPTANCE_SCENARIO=AT008_INVALID_OUTPUT in worker env.
    # 2. Create WorkflowRun via API or direct ORM.
    # 3. Enqueue ARQ job.
    # 4. Wait for worker to process (poll database state).
    # 5. Assert final state is FAILED_VALIDATION.
    # 6. Assert workflow_steps contain validation failure.
    # 7. Assert no Recommendation row exists.
    # 8. Assert risk API still returns deterministic risks.
```

**AT-013 backend test** (proposed: `backend/tests/integration/test_at013_acceptance.py`):

```python
async def test_at013_outage_retry_via_worker(
    db_session: AsyncSession,
    arq_pool: ArqRedis,
) -> None:
    """AT-013: Provider outage → FAILED_PROVIDER → user Retry → success."""
    # 1. Set FORGEMIND_ACCEPTANCE_SCENARIO=AT013_OUTAGE_UNTIL_RETRY in worker env.
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

**Test fixtures** (proposed additions to `backend/tests/integration/conftest.py`):

- `arq_pool` fixture: Creates ARQ Redis pool for job enqueue.
- `worker_process` fixture: Starts ARQ worker subprocess with scenario environment and `DATABASE_URL` set to acceptance URL.
- `wait_for_terminal_state` helper: Polls database until workflow reaches terminal state (with timeout).

### 4.6 Playwright Scenarios

**Decision:** Two independently reviewable Playwright scenarios with real backend, worker, database, and frontend.

**AT-008 Playwright scenario** (proposed: `frontend/acceptance-e2e/at008-acceptance.spec.ts`):

```typescript
test("AT-008: validation failure visible in trace", async ({ page }) => {
  // 1. Authenticate as production_manager.demo.
  // 2. Navigate to supply risk detail page for PLAN-2026-W31.
  // 3. Verify deterministic risks are visible (RISK-001, RISK-002, RISK-003).
  // 4. Click "Start AI Analysis" button (if present in UI).
  // 5. Wait for workflow state to reach FAILED_VALIDATION (poll API).
  // 6. Verify workflow trace shows:
  //    - provider_call step with status "completed".
  //    - validation step with status "failed" and error_code "VALIDATION_FAILED".
  // 7. Verify no recommendation section is rendered.
  // 8. Verify "Retry" button is visible (user is PRODUCTION_MANAGER / run creator).
  // 9. Verify deterministic risks remain visible (not blocked by workflow failure).
  // 10. Take screenshot of trace.
  // 11. Assert API response for GET /workflow-runs/{run_id} matches UI state.
});
```

**AT-013 Playwright scenario** (proposed: `frontend/acceptance-e2e/at013-acceptance.spec.ts`):

```typescript
test("AT-013: provider outage and user retry", async ({ page }) => {
  // 1. Authenticate as production_manager.demo.
  // 2. Navigate to supply risk detail page for PLAN-2026-W31.
  // 3. Verify deterministic risks are visible.
  // 4. Click "Start AI Analysis" button (if present in UI).
  // 5. Wait for workflow state to reach FAILED_PROVIDER (poll API).
  // 6. Verify workflow trace shows:
  //    - provider_call step with status "failed" and error_code "PROVIDER_TRANSIENT".
  //    - error_detail "ProviderError" (safe value, no secrets).
  // 7. Verify no recommendation section is rendered.
  // 8. Verify "Retry" button is visible.
  // 9. Verify deterministic risks remain visible.
  // 10. Take screenshot of failed state.
  // 11. Click "Retry" button.
  // 12. Wait for workflow state to reach COMPLETED (poll API).
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
- ✅ Real provider adapter and retry wrapper (via acceptance scenario module).
- ✅ Real workflow state machine and trace persistence.
- ❌ External provider API (replaced by deterministic scenario provider).

**Justification for provider simulation:**

The acceptance test proves the **workflow behavior** (state transitions, error handling, retry logic, trace persistence, UI rendering) — not the external provider's actual API. The scenario provider exercises the same code paths as a real provider (same exceptions, same result structure, same factory wrapping) without network dependency or secret exposure.

**Playwright configuration** (proposed new file `frontend/playwright.acceptance.config.ts`):

The existing `frontend/playwright.config.ts` is **not modified**. It remains responsible for ordinary E2E tests and its top-level `webServer` configuration (which starts `npm run preview` on port 4173) is preserved unchanged.

Instead, a dedicated acceptance configuration is created. This configuration:

- Sets `testDir` to `./acceptance-e2e` (outside the ordinary `./e2e` discovery tree).
- Does **not** define a `webServer` — the orchestration script owns frontend startup.
- Reads the frontend URL from `PLAYWRIGHT_ACCEPTANCE_BASE_URL` (fail-closed: aborts if unset or invalid).
- Preserves trace, screenshot, and timeout settings from the ordinary configuration.

```typescript
// Proposed new file: frontend/playwright.acceptance.config.ts
import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.PLAYWRIGHT_ACCEPTANCE_BASE_URL;
if (!baseURL) {
  throw new Error('PLAYWRIGHT_ACCEPTANCE_BASE_URL must be set for acceptance tests');
}

export default defineConfig({
  testDir: './acceptance-e2e',
  fullyParallel: false,
  forbidOnly: true,
  retries: 0,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL,
    trace: 'on-first-retry',
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'acceptance',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  // No webServer — orchestration script manages frontend startup.
});
```

**Ordinary E2E isolation:**

The existing `frontend/playwright.config.ts` has `testDir: './e2e'` (line 4). The proposed acceptance specs are placed in `frontend/acceptance-e2e/`, which is **outside** the ordinary discovery tree. Therefore:

- `npm run test:e2e` (which runs `playwright test` with the default config) discovers only `frontend/e2e/*.spec.ts`.
- Acceptance specs in `frontend/acceptance-e2e/` are not discovered by the ordinary config.
- Acceptance specs are executed only via the dedicated config: `npx playwright test --config=playwright.acceptance.config.ts`.
- The dedicated config does not start a webServer — the orchestration script starts the frontend dev server on a dynamic port and sets `PLAYWRIGHT_ACCEPTANCE_BASE_URL` before invoking Playwright.

**Acceptance invocation** (proposed):

```bash
cd frontend && npx playwright test --config=playwright.acceptance.config.ts
```

This command is invoked by the orchestration script after the frontend dev server is started and ready.

### 4.7 Evidence Collection

**Decision:** Python evidence collector with deterministic failure handling, redaction, run identity, and artifact integrity.

#### 4.7.1 Evidence Categories and Authoritative Sources

| # | Evidence | Authoritative Source | Query / Command |
|---|----------|---------------------|-----------------|
| 1 | Repository baseline | Git | `git rev-parse HEAD`, `git status --porcelain`, `git diff --stat` |
| 2 | Environment versions | System | `python --version`, `node --version`, `docker --version` |
| 3 | Scenario identity | Test metadata | Scenario name, run ID, correlation ID from API responses |
| 4 | Workflow steps (audit trail) | `workflow_steps` table | `SELECT id, run_id, seq, step_name, status, error_code, error_detail, started_at, completed_at FROM workflow_steps WHERE run_id = :run_id ORDER BY seq` |
| 5 | Current run state | `workflow_runs` table | `SELECT id, state, dispatch_generation, error_code, error_detail, started_at, completed_at, updated_at FROM workflow_runs WHERE id = :run_id` |
| 6 | Provider attempt count | Worker log file | Count of `chat_provider.retry.attempt` log entries for the run's correlation_id |
| 7 | Dispatch generation | API response | `GET /api/v1/workflow-runs/{run_id}` → `dispatch_generation` field |
| 8 | Recommendation absence/presence | `recommendations` table | `SELECT COUNT(*) FROM recommendations WHERE run_id = :run_id` |
| 9 | Controlled-write absence | Schema verification | `procurement_tasks` table does not exist in Phase 5 schema (Phase 6). Verify via: `SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'procurement_tasks')` — must be `false`. |
| 10 | Risk API availability | API response | `GET /api/v1/risks?plan_id=PLAN-2026-W31` → verify 3 risks returned |
| 11 | Browser screenshots | Playwright | Screenshots at key moments (failed state, success state) |
| 12 | Playwright traces | Playwright | trace.zip files for failed tests |
| 13 | Final database checks | Database queries | Workflow run final state, step count, recommendation count |
| 14 | Test counts | pytest / Playwright | pass/fail/skip counts |
| 15 | Redaction result | Evidence collector | Verify no secrets in evidence files |
| 16 | Final repository status | Git | `git status --porcelain`, `ls evidence/{run_id}/` |

**State transition evidence — design limitation:**

The `workflow_runs` table stores only the **current** state and timestamps, not a history of transitions. There is no persisted state-transition history table.

State transitions are reconstructed from:

1. **Workflow steps** (`workflow_steps` table): The append-only step records provide a persistent audit trail of provider calls, validation attempts, and their outcomes. Each step has `seq`, `step_name`, `status`, `error_code`, `error_detail`, `started_at`, `completed_at`.
2. **Structured worker logs**: The `workflow.vertical.*` and `chat_provider.retry.attempt` log events capture state transitions with timestamps. The orchestration script captures worker stdout to a log file.
3. **API snapshots**: The orchestration script captures `GET /api/v1/workflow-runs/{run_id}` at defined points (after start, after terminal state, after retry) to record the state at those moments.

**Explicit limitation:** If a future requirement demands a persisted state-transition history table, that would be a product change outside the harness scope. The current evidence model uses steps + logs + API snapshots as the authoritative transition record.

#### 4.7.2 Evidence Lifecycle

1. **Raw artifacts:** Written to `evidence/{run_id}/raw/` during harness execution.
2. **Redaction:** After all raw artifacts are collected, the evidence collector redacts secrets and writes to `evidence/{run_id}/redacted/`.
3. **Redaction verification:** The collector verifies redaction by scanning redacted files for secret patterns. If any secret is found, redaction is marked as **failed** and raw artifacts are **preserved** (not deleted) for debugging.
4. **Checksum generation:** SHA-256 checksums computed for all redacted artifacts **excluding** the checksum file itself. Written to `evidence/{run_id}/redacted/checksums.sha256`.
5. **Raw cleanup:** Raw artifacts deleted **only after** redaction verification succeeds and checksums are generated. If redaction fails, raw artifacts are retained in `evidence/{run_id}/raw/` and the run is marked as failed.
6. **Screenshots:** Binary artifacts are reviewed for sensitive content (auth tokens, API keys visible in browser). Screenshots are included in redacted evidence only after manual or automated review confirms no sensitive content is visible.

#### 4.7.3 Repository Cleanliness Model

The evidence lifecycle must not contradict the repository cleanliness invariant. The following are distinct concepts:

**Tracked worktree cleanliness** (measured by `git status --porcelain`):

- After harness execution, `git status --porcelain` must show **only** the protected audit file (`docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md`).
- Evidence directories are gitignored and do **not** appear in `git status --porcelain`.

**Ignored artifact inventory** (measured by explicit directory listing):

- `ls evidence/{run_id}/raw/` — should be empty after successful redaction.
- `ls evidence/{run_id}/redacted/` — should contain the redacted evidence files.
- `cat evidence/{run_id}/redacted/checksums.sha256` — should list all redacted artifacts.

**Evidence existence verification:**

- `find evidence/ -type f | wc -l` — should match expected artifact count.
- `find evidence/ -name "*.json" -exec grep -l "sk-" {} \;` — should be empty (no secrets).

**Protected-audit status:**

- `sha256sum docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md` — must match expected hash.
- The protected audit file is the sole pre-existing untracked worktree entry.

**Cleanliness invariant:**

- `git status --porcelain` shows only: `?? docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md`.
- No other tracked or untracked files appear.
- Evidence directories exist but are gitignored.

---

## 5. File-Level Implementation Plan

### 5.1 Production Code Changes (Minimal, Guarded)

**File:** `backend/app/ai/provider/factory.py`
**Change:** Add conditional import and usage of acceptance scenario module when `FORGEMIND_ACCEPTANCE_SCENARIO` is set.
**Lines:** ~8 lines added (conditional block with lazy import).
**Scope:** Guarded acceptance-only path. Environment check prevents execution in production/staging.
**Risk:** Low — lazy import, environment guard, fail-closed for unknown scenarios.

**File:** `backend/app/ai/provider/acceptance_scenarios.py` (proposed, new)
**Purpose:** Acceptance scenario provider implementations and lookup function.
**Key symbols:** `get_acceptance_provider()`, `InvalidOutputProvider`, `OutageUntilRetryProvider`, `ValidOutputProvider`.
**Scope:** Guarded acceptance-only module. Only imported when `FORGEMIND_ACCEPTANCE_SCENARIO` is set.
**Expected coverage:** ~150 lines.

**File:** `backend/app/ai/workflow/vertical.py`
**Change:** Add `dispatch_generation` to provider context dict at line 242–245.
**Lines:** 1 line added.
**Scope:** Metadata propagation to provider context. `queued_generation` is already available as a function parameter.
**Risk:** Low — context dict is provider-specific metadata, not part of any public API contract.

**Total production code changes:** 3 files, ~9 lines of logic + ~150 lines in the new acceptance module.

### 5.2 Backend Test Files

**File:** `backend/tests/integration/test_at008_acceptance.py` (proposed, new)
**Purpose:** AT-008 backend integration test via real ARQ worker.
**Key symbols:** `test_at008_invalid_output_via_worker`.
**AT clauses:** AT-008 (all clauses).
**Scope:** Integration test.
**Expected coverage:** 1 test, ~100 lines.

**File:** `backend/tests/integration/test_at013_acceptance.py` (proposed, new)
**Purpose:** AT-013 backend integration test via real ARQ worker.
**Key symbols:** `test_at013_outage_retry_via_worker`.
**AT clauses:** AT-013 (all clauses).
**Scope:** Integration test.
**Expected coverage:** 1 test, ~150 lines.

**File:** `backend/tests/integration/conftest.py`
**Change:** Add `arq_pool`, `worker_process`, `wait_for_terminal_state` fixtures.
**Lines:** ~100 lines added.
**Scope:** Test infrastructure.

### 5.3 Playwright Test Files

**File:** `frontend/acceptance-e2e/at008-acceptance.spec.ts` (proposed, new)
**Purpose:** AT-008 browser scenario.
**Key symbols:** `test("AT-008: validation failure visible in trace")`.
**AT clauses:** AT-008 (UI clauses).
**Scope:** End-to-end test.
**Expected coverage:** 1 test, ~80 lines.

**File:** `frontend/acceptance-e2e/at013-acceptance.spec.ts` (proposed, new)
**Purpose:** AT-013 browser scenario.
**Key symbols:** `test("AT-013: provider outage and user retry")`.
**AT clauses:** AT-013 (UI clauses).
**Scope:** End-to-end test.
**Expected coverage:** 1 test, ~120 lines.

**File:** `frontend/playwright.acceptance.config.ts` (proposed, new)
**Purpose:** Dedicated Playwright configuration for acceptance tests. No webServer, reads `PLAYWRIGHT_ACCEPTANCE_BASE_URL`, testDir set to `./acceptance-e2e`.
**Key symbols:** `defineConfig`, `testDir: './acceptance-e2e'`, `baseURL` from environment.
**Scope:** Test configuration.
**Expected coverage:** ~30 lines.

**File:** `frontend/playwright.config.ts`
**Change:** None. This file is **not modified**. It remains responsible for ordinary E2E tests only.

### 5.4 Orchestration Script

**File:** `scripts/acceptance_harness.py` (proposed, new)
**Purpose:** Process orchestration for isolated acceptance environment.
**Key symbols:** `run_acceptance_harness()` main function, `validate_acceptance_database_url()`, `prepare_acceptance_database()`.
**Scope:** Orchestration.
**Expected coverage:** ~400 lines.

**Responsibilities:**

- Generate run ID.
- Start PostgreSQL and Redis containers with run-scoped names and labels.
- Validate database URL (fail-closed checks).
- Prepare database (migrations, seed) with `DATABASE_URL` set.
- Start backend, worker, frontend with correct environment.
- Run backend integration tests.
- Run Playwright tests.
- Collect evidence.
- Teardown owned resources only.

**Command modes** (proposed):

```python
# Implementation-verification mode (Phase B):
python scripts/acceptance_harness.py --mode=verify

# Formal-evidence mode (Phase C):
python scripts/acceptance_harness.py --mode=formal --run-id=<run_id>
```

- `--mode=verify`: Runs tests to prove the harness works. Output is implementation-verification evidence. Does not produce the authoritative evidence package.
- `--mode=formal`: Runs the full harness and collects the authoritative evidence package for Product Owner review.

### 5.5 Configuration Files

**File:** `.gitignore`
**Change:** Add `evidence/` (covers all subdirectories).
**Lines:** 1 line added.
**Scope:** Repository configuration.

**File:** `Makefile`
**Change:** Add `acceptance-verify` and `acceptance-formal` targets.
**Lines:** ~15 lines added.
**Scope:** Build automation.

**Proposed target definitions:**

```makefile
acceptance-verify: ## Run acceptance harness in implementation-verification mode
	@echo "Running acceptance harness (verification mode)..."
	python scripts/acceptance_harness.py --mode=verify
	@echo "Verification complete."

acceptance-formal: ## Run acceptance harness in formal-evidence mode
	@echo "Running acceptance harness (formal-evidence mode)..."
	python scripts/acceptance_harness.py --mode=formal
	@echo "Formal evidence collected. See evidence/ directory."
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

- **Runtime cost:** ~5–10 minutes (container startup, migrations, seed, tests, teardown).
- **Service availability:** Requires Docker, PostgreSQL, Redis — not all CI runners have these.
- **Determinism:** Scenario providers are deterministic, but container startup timing may vary.
- **Artifact retention:** Evidence files are large (screenshots, traces) — not suitable for every PR.
- **Secret-free execution:** No real API keys, but environment setup is complex.
- **Flaky-test risk:** Low (deterministic scenarios), but container startup failures possible.

**CI workflow** (proposed, optional, for Phase C formal execution):

```yaml
# .github/workflows/acceptance-harness.yml (proposed)
name: Acceptance Harness

on:
  workflow_dispatch:  # Manual trigger only

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
      - run: python scripts/acceptance_harness.py --mode=formal
        env:
          DATABASE_URL: postgresql+asyncpg://forgemind:forgemind@localhost:5433/forgemind_acceptance
          REDIS_URL: redis://localhost:6380/0
      - uses: actions/upload-artifact@v4
        with:
          name: acceptance-evidence
          path: evidence/
```

**Integration with existing CI:**

- Existing backend unit/integration tests run on every PR (no change).
- Existing frontend unit tests run on every PR (no change).
- Existing Playwright E2E tests run on every PR (no change).
- Acceptance harness tests are **separate** and run only via dedicated workflow or manual invocation.

---

## 7. Test Matrix

| Test Type | Scope | Runs On | Command |
|-----------|-------|---------|---------|
| Backend unit tests | All backend unit tests | Every PR | `cd backend && ../.venv/bin/pytest tests/unit/` |
| Backend integration tests | All backend integration tests | Every PR | `cd backend && ../.venv/bin/pytest tests/integration/` |
| AT-008 backend acceptance | AT-008 via real worker | Phase B verification | `cd backend && ../.venv/bin/pytest tests/integration/test_at008_acceptance.py` |
| AT-013 backend acceptance | AT-013 via real worker | Phase B verification | `cd backend && ../.venv/bin/pytest tests/integration/test_at013_acceptance.py` |
| Frontend unit tests | All frontend unit tests | Every PR | `cd frontend && npm test` |
| Playwright E2E tests | Existing E2E tests | Every PR | `cd frontend && npm run test:e2e` |
| AT-008 Playwright acceptance | AT-008 browser scenario | Phase C formal | Via orchestration script |
| AT-013 Playwright acceptance | AT-013 browser scenario | Phase C formal | Via orchestration script |
| Full acceptance harness | All acceptance tests + evidence | Phase C formal | `make acceptance-formal` |

---

## 8. Validation Commands

**Pre-implementation validation (this planning package — Phase A):**

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

# Verify diff contains only planning document
git diff --cached --name-only
```

**Implementation-verification validation (Phase B — harness implementation package):**

```bash
# Run backend unit tests (no regressions)
cd backend && ../.venv/bin/pytest tests/unit/ -v

# Run backend integration tests (no regressions)
cd backend && ../.venv/bin/pytest tests/integration/ -v

# Run frontend unit tests (no regressions)
cd frontend && npm test

# Run existing Playwright E2E tests (no regressions)
cd frontend && npm run test:e2e

# Run AT-008 backend acceptance test (new — implementation verification)
cd backend && ../.venv/bin/pytest tests/integration/test_at008_acceptance.py -v

# Run AT-013 backend acceptance test (new — implementation verification)
cd backend && ../.venv/bin/pytest tests/integration/test_at013_acceptance.py -v

# Run acceptance harness in verification mode (new)
make acceptance-verify

# Verify repository cleanliness
git status --porcelain
```

**Formal-evidence validation (Phase C — separate authorization required):**

```bash
# Run full acceptance harness in formal-evidence mode
make acceptance-formal

# Verify evidence collected
ls -la evidence/

# Verify evidence integrity
find evidence/ -name "checksums.sha256" -exec cat {} \;

# Verify no secrets in evidence
find evidence/ -name "*.json" -exec grep -l "sk-" {} \;

# Verify repository cleanliness
git status --porcelain

# Verify evidence directory inventory
find evidence/ -type f | wc -l
```

---

## 9. Stop Conditions

The harness implementation (Phase B) must stop and report if:

1. **Production code change exceeds minimal injection point:** More than 3 files changed in `backend/app/` (excluding tests).
2. **Test isolation failure:** Acceptance tests modify any database other than `forgemind_acceptance`.
3. **Evidence redaction failure:** Secrets, tokens, or API keys found in redacted evidence files.
4. **Determinism failure:** Scenario providers produce non-deterministic output across runs.
5. **Container startup failure:** PostgreSQL or Redis containers fail to start within timeout.
6. **Migration failure:** Alembic migrations fail on `forgemind_acceptance` database.
7. **Seed failure:** Seed generator fails to populate golden dataset.
8. **Worker startup failure:** ARQ worker fails to start or connect to Redis.
9. **Test timeout:** Backend acceptance tests or Playwright scenarios exceed timeout (5 minutes each).
10. **Evidence collection failure:** Evidence collector fails to write artifacts or compute checksums.
11. **Fail-closed violation:** Unknown scenario name does not raise an error, or acceptance mode is accessible in production/staging.
12. **Database URL leak:** `DATABASE_URL` points to a non-acceptance database during harness execution.

---

## 10. Rollback Approach

### Phase B (Implementation) Failure

If the implementation package fails validation:

1. **Stop the task.** Do not attempt destructive remediation.
2. **Preserve the current diff** for review: `git diff` and `git diff --cached` capture the current state.
3. **Report the failure** with exact error message, stop condition triggered, and current working tree state.
4. **Revert through a later corrective commit** if required — do not use `git reset --hard`, `git stash`, `git clean`, or any destructive operation.
5. **Do not** modify `.env`, start/stop containers, run migrations, or write to any database.

### Phase C (Formal Execution) Failure

If the harness execution fails during formal evidence collection:

1. **Stop the orchestration script.** The script's teardown handler stops owned processes and containers.
2. **Preserve failure artifacts** in `evidence/{run_id}/raw/` for debugging.
3. **Report the failure** with test output, error logs, and the run ID.
4. **Do not** delete evidence, reset the repository, or modify any tracked files.
5. **Teardown owned resources only:** The script verifies container ownership via run-scoped names/labels before stopping or removing them. Containers not owned by the current run are left untouched.

### Prohibited Rollback Operations

The plan does **not** authorize:

- `git reset --hard`
- `git stash`
- `git clean`
- `git rebase`
- `git amend`
- `git push --force`
- `rm -rf` on any project directory
- `docker rm -f` on containers not owned by the current run
- `docker compose down -v`
- Deletion of Docker volumes
- Broad Docker cleanup

---

## 11. Security Constraints

The harness implementation and execution must ensure:

1. **Synthetic data only:** No real corporate, military, or confidential data.
2. **No real provider API calls:** Scenario providers do not make network requests.
3. **No real API keys:** Environment variables use sentinel values or empty strings.
4. **No secret values in artifacts:** Evidence collector redacts all secrets before saving.
5. **No uncontrolled external outage dependency:** Scenario providers simulate outages deterministically.
6. **No normal development or production database mutation:** Isolated `forgemind_acceptance` database with fail-closed URL validation.
7. **No deletion of Docker volumes:** Use `docker stop` and `docker rm` on owned containers only.
8. **No database recreation:** Orchestration script creates database if not exists, does not drop.
9. **No installation into running containers:** All dependencies installed via `pip` or `npm` before container start.
10. **No privilege or authorization bypass:** Tests use demo accounts with appropriate roles.
11. **No weakening of backend role enforcement:** Production RBAC unchanged.
12. **No acceptance-only route exposed in production:** Scenario module guarded by environment check; lazy import prevents loading in production/staging.
13. **Safe user-facing errors only:** Error messages do not expose secrets or stack traces.
14. **Deterministic teardown limited to harness-owned resources:** Only stop containers and processes verified as owned by the current run.

---

## 12. Definition of Done

### Phase B — Harness Implementation

The harness implementation is complete when:

1. ✅ All files in Section 5 are created or modified as specified.
2. ✅ Backend unit tests pass (no regressions).
3. ✅ Backend integration tests pass (no regressions).
4. ✅ Frontend unit tests pass (no regressions).
5. ✅ Existing Playwright E2E tests pass (no regressions).
6. ✅ AT-008 backend acceptance test passes (implementation verification).
7. ✅ AT-013 backend acceptance test passes (implementation verification).
8. ✅ `make acceptance-verify` completes successfully (implementation verification).
9. ✅ Lint passes: `make lint`.
10. ✅ No production code changes beyond minimal injection point (3 files, ~9 lines logic + ~150 lines acceptance module).
11. ✅ Fail-closed checks verified: unknown scenario raises, production/staging guard works.
12. ✅ Repository cleanliness: `git status --porcelain` shows only the protected audit file.

**The harness implementation does NOT:**

- Run the harness in formal-evidence mode.
- Collect formal acceptance evidence.
- Declare AT-008 or AT-013 PASS.
- Declare Phase 5 acceptance.
- Modify Source of Truth or Decision Log.
- Authorize formal acceptance execution.

### Phase C — Formal Acceptance Execution

Defined in a separate authorization after Phase B merge. The formal execution package will:

1. Run the merged harness via `make acceptance-formal`.
2. Collect the authoritative evidence package.
3. Verify evidence integrity (checksums, redaction).
4. Submit evidence for Product Owner review.

---

## 13. Authorization Boundary

**This planning document (Phase A):**

- ✅ Specifies an implementation-ready harness design.
- ❌ Does NOT authorize harness implementation.
- ❌ Does NOT authorize harness execution.
- ❌ Does NOT authorize evidence collection.
- ❌ Does NOT authorize any code changes.

**After Phase A merge, a separate Product Owner authorization is required for:**

- Phase B: Harness implementation.

**After Phase B merge, a separate Product Owner authorization is required for:**

- Phase C: Formal acceptance execution.

**After Phase C, a separate Product Owner action is required for:**

- Phase D: Evidence review and acceptance declaration.

**After Phase D, a separate Product Owner authorization is required for:**

- Phase E: Documentation lifecycle reconciliation.

No earlier step automatically authorizes a later step.

---

## 14. Implementation Package Contract

### 14.1 Objective

Implement the acceptance harness specified in this document (Phase B).

### 14.2 Included Scope

- All files listed in Section 5.
- Implementation-verification tests (Section 8, Phase B commands).
- Fail-closed validation of scenario control and database isolation.

### 14.3 Excluded Scope

- Formal-evidence mode execution (`--mode=formal`).
- Formal AT-008 or AT-013 PASS declaration.
- Phase 5 acceptance declaration.
- Source of Truth or Decision Log changes.
- Documentation lifecycle reconciliation.
- Authoritative evidence collection.

### 14.4 Prerequisites

- Docker installed and running.
- Python 3.12+ with venv at `/home/toha/Projects/forgemind-ai-operations/.venv/`.
- Node 22+ with npm.
- PostgreSQL 16 client tools (`psql`, `pg_isready`).
- Redis client tools (`redis-cli`).

### 14.5 Exact File Scope

See Section 5. Summary:

| # | File | Action | Scope |
|---|------|--------|-------|
| 1 | `backend/app/ai/provider/factory.py` | Modify | Production (guarded) |
| 2 | `backend/app/ai/provider/acceptance_scenarios.py` | Create | Production (guarded) |
| 3 | `backend/app/ai/workflow/vertical.py` | Modify | Production (1 line) |
| 4 | `backend/tests/integration/test_at008_acceptance.py` | Create | Test |
| 5 | `backend/tests/integration/test_at013_acceptance.py` | Create | Test |
| 6 | `backend/tests/integration/conftest.py` | Modify | Test infrastructure |
| 7 | `frontend/acceptance-e2e/at008-acceptance.spec.ts` | Create | Acceptance E2E (isolated from ordinary `e2e/`) |
| 8 | `frontend/acceptance-e2e/at013-acceptance.spec.ts` | Create | Acceptance E2E (isolated from ordinary `e2e/`) |
| 9 | `frontend/playwright.acceptance.config.ts` | Create | Acceptance test configuration (no webServer) |
| 10 | `scripts/acceptance_harness.py` | Create | Orchestration |
| 11 | `.gitignore` | Modify | Configuration |
| 12 | `Makefile` | Modify | Build automation |
| 13 | `docs/ACCEPTANCE_HARNESS.md` | Create (optional) | Documentation |

**Notes:**

- `frontend/playwright.config.ts` is **not** modified — ordinary E2E remains unchanged.
- Acceptance specs live in `frontend/acceptance-e2e/` (not `frontend/e2e/`) so ordinary `npm run test:e2e` cannot discover them.
- `frontend/playwright.acceptance.config.ts` sets `testDir: './acceptance-e2e'` and reads `PLAYWRIGHT_ACCEPTANCE_BASE_URL` (fail-closed).
- 12 required files + 1 optional documentation file = 13 total (12 mandatory).

### 14.6 Deterministic Scenario-Control Design

See Section 4.1. Key design: guarded acceptance-only module with lazy import, fail-closed for unknown scenarios, environment guard prevents production/staging access.

### 14.7 Database and Redis Isolation Design

See Sections 4.2 and 4.3. Key design: `DATABASE_URL` (not `TEST_DATABASE_URL`) propagated to all subprocesses, fail-closed URL validation, dedicated database and port.

### 14.8 Process-Orchestration Design

See Section 4.4. Key design: run-scoped container names and labels, ownership verification before teardown, port conflict detection, no destructive operations.

### 14.9 Backend Integration-Test Design

See Section 4.5.

### 14.10 Playwright Scenario Design

See Section 4.6.

### 14.11 Evidence Collector Design

See Section 4.7. Key design: run-scoped directories, raw preserved until redaction verified, checksums exclude self, screenshots reviewed for sensitive content.

### 14.12 CI Strategy

See Section 6.

### 14.13 Test Matrix

See Section 7.

### 14.14 Validation Commands

See Section 8.

### 14.15 Stop Conditions

See Section 9.

### 14.16 Rollback Approach

See Section 10. Key design: stop task, preserve diff, report failure, revert via corrective commit, no destructive operations.

### 14.17 Security Constraints

See Section 11.

### 14.18 Definition of Done

See Section 12 (Phase B).

### 14.19 Explicit Authorization Boundary

See Section 13.

### 14.20 Exact Next Action After Implementation Review

After harness implementation (Phase B) is reviewed and merged:

1. Product Owner authorizes formal acceptance execution (Phase C).
2. Formal execution package runs harness in `--mode=formal` and collects evidence.
3. Product Owner reviews evidence (Phase D).
4. Product Owner declares AT-008/AT-013 PASS and Phase 5 acceptance.
5. Documentation lifecycle reconciliation (Phase E, separate package).

---

## 15. Required Plan Conclusions

### 15.1 Is WP-REC-03H the correct bounded package name and scope?

**Yes.** WP-REC-03H is the correct name and scope. It follows the WP-REC-03 series (Phase 5 AI Workflow) and is bounded to the AT-008 and AT-013 acceptance harness specification. It does not expand into WP-REC-05, AT-006/AT-007 verification, Phase 6, or any unrelated package.

### 15.2 Can the harness be implemented without production-code changes?

**No.** Three production files require changes:

1. `backend/app/ai/provider/factory.py`: Add conditional acceptance scenario import (~8 lines).
2. `backend/app/ai/provider/acceptance_scenarios.py`: New guarded module (~150 lines).
3. `backend/app/ai/workflow/vertical.py`: Add `dispatch_generation` to provider context (1 line).

All changes are guarded by environment checks, fail-closed, and do not affect production behavior.

### 15.3 What exact mechanism selects deterministic chat-provider behavior?

**Environment variable `FORGEMIND_ACCEPTANCE_SCENARIO`** checked in `create_chat_provider()` (factory.py). When set and `environment` is `"development"`, the factory lazily imports `app.ai.provider.acceptance_scenarios` and calls `get_acceptance_provider(scenario_name, config)`. Unknown scenario names raise `ChatProviderConfigurationError` (fail closed). The module is never imported in production/staging.

### 15.4 How are the backend API and ARQ worker guaranteed to share the same provider scenario?

Both processes inherit the same `FORGEMIND_ACCEPTANCE_SCENARIO` environment variable from the orchestration script. Both call `create_chat_provider()` which reads the env var and returns the same scenario type. The scenario module is deterministic — given the same scenario name and config, it returns an equivalent provider.

### 15.5 How is the acceptance database isolated from the development database?

**Dedicated database `forgemind_acceptance`** on port 5433. The orchestration script sets `DATABASE_URL` (not `TEST_DATABASE_URL`) for all application subprocesses. Fail-closed validation rejects URLs pointing to the development database, production, or staging. All processes (backend, worker, Alembic, seed) receive the identical `DATABASE_URL` before module import.

### 15.6 How is Redis state isolated?

**Dedicated Redis on port 6380.** All processes receive `REDIS_URL=redis://localhost:6380/0` in their environment.

### 15.7 How does AT-013 fail before Retry and succeed after Retry without race-prone global state?

**Dispatch-generation-aware scenario provider.** The `OutageUntilRetryProvider` reads `context["dispatch_generation"]` (added to the context dict in `vertical.py`). When `dispatch_generation == 0`, it raises `TransientChatProviderError`. When `dispatch_generation >= 1`, it returns valid `RecommendationData`. Each ARQ job creates a fresh provider instance — there is no shared mutable state across jobs. The scenario behavior is determined entirely by the per-call context, not by any global registry.

### 15.8 Which Playwright interactions are real end-to-end rather than mocked?

**All interactions are real** except the external provider API:

- ✅ Real browser (Playwright).
- ✅ Real frontend (React app on port 5174).
- ✅ Real backend API (FastAPI + uvicorn on port 8001).
- ✅ Real PostgreSQL persistence (forgemind_acceptance on port 5433).
- ✅ Real Redis queue (port 6380).
- ✅ Real ARQ worker.
- ✅ Real provider adapter and retry wrapper (via acceptance scenario module).
- ✅ Real workflow state machine and trace persistence.
- ❌ External provider API (replaced by deterministic scenario provider).

### 15.9 Where are raw evidence artifacts written?

**`evidence/{run_id}/raw/`** (gitignored, preserved until redaction verification succeeds, then deleted).

### 15.10 Which evidence artifacts, if any, are later committed?

**None are committed automatically.** Evidence directories are gitignored. A future documentation lifecycle package (Phase E) may choose to commit selected redacted artifacts, but this is not authorized by WP-REC-03H.

### 15.11 How is repository cleanliness evaluated while evidence exists?

**Two separate checks:**

1. **Tracked worktree cleanliness:** `git status --porcelain` shows only the protected audit file. Evidence directories are gitignored and do not appear.
2. **Evidence inventory:** `ls evidence/{run_id}/redacted/` and `find evidence/ -type f | wc -l` verify evidence exists outside the tracked worktree.

### 15.12 What is the exact implementation file list?

See Section 14.5. Summary: 13 files (3 production, 3 backend tests, 3 acceptance test files [2 specs + 1 config], 3 orchestration/config, 1 optional docs).

### 15.13 What is the exact validation command sequence?

See Section 8. Phase B commands for implementation verification; Phase C commands for formal evidence (separate authorization).

### 15.14 Does harness implementation require CI changes?

**No.** The harness runs manually via `make acceptance-verify` (Phase B) or `make acceptance-formal` (Phase C). An optional CI workflow can be added later, but is not required for implementation.

### 15.15 What later package will execute formal acceptance?

**Phase C** (formal acceptance execution) is a separate authorization after Phase B merge. It will run the merged harness via `make acceptance-formal`, collect authoritative evidence, and submit it for Product Owner review (Phase D).

### 15.16 What conditions block formal acceptance execution?

1. Harness implementation (Phase B) is not reviewed and merged.
2. Product Owner has not authorized Phase C.
3. Harness execution fails (test failures, evidence collection failures).
4. Evidence contains secrets, tokens, or API keys.
5. Evidence does not demonstrate all AT-008 and AT-013 clauses.

---

## 16. Unresolved Questions

**One explicit design limitation:**

The `workflow_runs` table stores only the current state, not a history of transitions. State-transition evidence is reconstructed from workflow steps, structured logs, and API snapshots. If a persisted transition history is required for formal acceptance, that would be a product change outside the harness scope. The current evidence model is sufficient for AT-008 and AT-013 because the workflow steps table provides a complete append-only audit trail of all execution steps, and the structured logs capture state transitions with timestamps.

**No other unresolved questions.** All design decisions are resolved and specified in this document.

---

## 17. Lifecycle and Authorization Boundary Confirmation

**This planning document (Phase A) authorizes:**

- ✅ Specification of an implementation-ready harness design.
- ❌ Nothing else.

**Phase B (harness implementation) requires:**

- Separate Product Owner authorization after Phase A merge.
- May: implement harness code, run verification tests, create implementation PR.
- Must NOT: collect formal evidence, declare PASS, declare Phase 5 accepted.

**Phase C (formal execution) requires:**

- Separate Product Owner authorization after Phase B merge.
- May: run harness in formal mode, collect authoritative evidence.
- Must NOT: declare PASS.

**Phase D (acceptance declaration) requires:**

- Product Owner reviews evidence and explicitly declares AT-008/AT-013 PASS.
- Product Owner declares Phase 5 acceptance.

**Phase E (documentation reconciliation) requires:**

- Separate Product Owner authorization after Phase D.

---

## 18. Recommended Next Action

**After this planning PR (#82) is reviewed and merged:**

The Product Owner may authorize Phase B (harness implementation) with the following scope:

- Implement all files listed in Section 14.5.
- Run all Phase B validation commands in Section 8.
- Run `make acceptance-verify` to prove the harness works.
- Submit implementation PR for review.

**Do NOT authorize in the same task:**

- Formal acceptance execution (Phase C).
- AT-008 or AT-013 PASS declaration.
- Phase 5 acceptance declaration.
- Source of Truth or Decision Log changes.
- Documentation lifecycle reconciliation.

---

**End of WP-REC-03H Planning Document (Corrected)**
