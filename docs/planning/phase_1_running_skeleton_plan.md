# Phase 1 — Running Skeleton Plan

**Status:** ✅ COMPLETE
**Final HEAD:** `58a2635cca179a38c5d885ae686af55551beca43`
**Completion Date:** 2026-07-17
**Completion Report:** [docs/phase_1/phase_1_completion_report.md](../phase_1/phase_1_completion_report.md)

## 1. Repository State at Planning Time

| Field | Value |
|-------|-------|
| Branch | `main` |
| HEAD | `4e7879c3e1c4c576769720d52d2f43f1a3c1a418` |
| Working tree | clean |
| Phase 0 | accepted, merged via PR #1 (squash merge 2026-07-15) |
| Phase 1 branch | does not exist |
| Files in HEAD | 54 (Phase 0 bootstrap) |

## 2. Files Reviewed

### Source of Truth (12 files)
`forgemind_project_source_of_truth/` — all files from `MANIFEST.md`:
`00_PROJECT_CHARTER.md` through `09_MASTER_TASK_FOR_HERMES.md`, plus `README.md`.

### Planning documents (6 files)
- `docs/planning/phase_0_bootstrap_plan.md`
- `docs/planning/phase_0_implementation_log.md`
- `docs/planning/open_questions.md`
- `docs/planning/product_owner_decision_sheet.md`
- `docs/planning/proposed_repository_structure.md`
- `docs/planning/requirements_traceability_matrix.md`

### Phase 0 implementation (all 54 committed files)
Backend: `app/main.py`, `app/config.py`, `app/worker.py`, `app/__init__.py`,
`pyproject.toml`, `alembic/env.py`, `alembic.ini`, `alembic/README`,
`alembic/script.py.mako`, `tests/conftest.py`, `tests/__init__.py`,
`tests/unit/test_health.py`.

Frontend: `src/App.tsx`, `src/main.tsx`, `src/index.css`, `package.json`,
`package-lock.json`, `vite.config.ts`, `tailwind.config.ts`, `postcss.config.js`,
`tsconfig.json`, `tsconfig.node.json`, `index.html`, `.eslintrc.cjs`.

Infrastructure: `docker-compose.yml`, `docker-compose.dev.yml`,
`infra/caddy/Caddyfile`, `infra/docker/backend.dockerfile`,
`infra/docker/worker.dockerfile`, `infra/docker/frontend.dockerfile`,
`infra/docker/nginx.conf`, `.dockerignore`, `.env.example`, `.gitignore`,
`Makefile`, `README.md`, `HERMES.md`.

CI: `.github/workflows/ci-backend.yml`, `ci-frontend.yml`, `ci-e2e.yml`,
`.github/ISSUE_TEMPLATE/task.md`, `bug.md`.

Scripts: `scripts/seed.sh`, `scripts/reset.sh`, `scripts/run-tests.sh`,
`scripts/check-secrets.sh`.

Seed: `seed/README.md`.

Git: PR #1 full body, commit `4e7879c` stat (54 files, 10994 insertions).

## 3. Phase 0 Gap Analysis — What Exists vs. What Phase 1 Needs

| Component | Phase 0 state | Phase 1 requirement | Gap |
|-----------|---------------|---------------------|-----|
| Database module | **Missing** — no `database.py` | SQLAlchemy engine + session factory | Create `backend/app/database.py` |
| ORM models | **Missing** — no `models/` dir | Diagnostic job table model | Create `backend/app/models/` |
| Alembic target_metadata | `None` — no autogenerate | Must reference `Base.metadata` | Fix `alembic/env.py` |
| Alembic migrations | **None** — no `versions/` dir | At least one migration creating `diagnostic_jobs` | Generate initial migration |
| API router | **Missing** — no `api/` dir | `/api/v1/system/*` endpoints | Create `backend/app/api/` |
| Health endpoint | Returns `{"status": "healthy"}` only | Must check PG, Redis, worker, Alembic revision | Expand `/health`, add `/system/status` |
| Core utilities | **Missing** — no `core/` dir | Correlation ID, structured logging, build metadata | Create `backend/app/core/` |
| ARQ job functions | `WorkerSettings.functions = []` | At least one diagnostic job function | Register diagnostic task |
| Schemas | **Missing** — no `schemas/` dir | Pydantic request/response models for diagnostic | Create `backend/app/schemas/` |
| Frontend routing | None — single `App.tsx` placeholder | React Router with control-plane route | Add `react-router-dom` routes |
| Frontend API client | None | TanStack Query + fetch wrapper | Create `lib/api-client.ts`, hooks |
| Frontend components | Single placeholder `App.tsx` | System status panel, diagnostic trigger, job display | Build control-plane UI |
| shadcn/ui | Not initialized | Component primitives for UI | `npx shadcn-ui init` |
| Structured logging | `structlog` in deps, not used | JSON logs with correlation ID | Configure structlog |
| Build metadata | App version hardcoded `"0.1.0"` | Git SHA + version exposed in API | Add build-time metadata |
| Worker health | Not exposed | Worker availability check via Redis queue | Implement worker ping |
| Correlation ID | Not implemented | UUID v4 per request, in logs and responses | Implement middleware |

## 4. Phase 1 Boundary

### 4.1 In Scope

**Vertical scenario:** Operations Control Plane

**End-to-end data path:**
```
Browser → Caddy → React frontend → FastAPI backend → PostgreSQL
                                                → Redis → ARQ worker
```

**Mandatory deliverables:**

1. **Database foundation** — SQLAlchemy async engine/session, Alembic migration creating `diagnostic_jobs` table, migration runnable from clean state.

2. **Core infrastructure** — Correlation ID middleware (UUID v4), structured JSON logging (structlog), build/version metadata (app version + Git SHA).

3. **Health/readiness** — Expanded `/health` with real dependency checks (PostgreSQL connectivity, Redis connectivity, worker availability, current Alembic revision). Separate `/ready` semantics if justified.

4. **System status API** — `GET /api/v1/system/status` returning:
   - backend health
   - PostgreSQL connectivity
   - Redis connectivity
   - worker availability
   - current Alembic revision
   - application version / Git SHA
   - response latency
   - correlation ID (per-request)
   - latest diagnostic job status

5. **Diagnostic background job** — Real ARQ job that:
   - is enqueued via API
   - executes through the worker
   - runs real checks (PG query, Redis ping, etc.)
   - persists lifecycle + result in PostgreSQL
   - carries correlation ID through logs

6. **Diagnostic API endpoints:**
   - `POST /api/v1/system/diagnostics` — enqueue diagnostic, return job ID + correlation ID
   - `GET /api/v1/system/diagnostics/{job_id}` — return job status + result

7. **Frontend Operations Control Plane:**
   - System status panel with real backend-derived data
   - "Run system diagnostic" button
   - Polling for diagnostic job status (3-5s interval)
   - Loading, empty, error, success states
   - Industrial design system (dark theme, steel/primary palette already started)
   - Correlation ID visible in UI

8. **Docker Compose** — Full stack runs from `docker compose up -d --build`, all services reach healthy.

9. **CI** — Backend and frontend CI pass with the new code. E2E gate remains deferred (no Playwright tests yet).

### 4.2 Out of Scope

- Supply-risk domain logic
- RAG or embeddings
- AI recommendations or LLM calls
- Approval workflow
- Procurement tasks
- Production authentication (JWT, password hashing, RBAC middleware, demo accounts) — deferred to Phase 2 per DEC-029 with constraints: no public deployment, no real/sensitive data, diagnostic endpoints documented as development/demo-only
- Decorative/fake service statuses
- Seed data generators (Phase 2)
- E2E Playwright tests (Phase 2+)
- Public VPS deployment (Phase 7)

### 4.3 Source of Truth Alignment

| SoT Reference | Phase 1 Coverage |
|---------------|-----------------|
| `07_ROADMAP.md` Phase 1 deliverables: React frontend, FastAPI backend, PostgreSQL, migrations, health checks, Docker Compose, basic login page | All covered except "basic login page" — see blocking decision BD-1 |
| `07_ROADMAP.md` Phase 1 exit criteria: clean deployment, frontend→backend, backend→database, automated smoke test | All four satisfied by this plan |
| `03_DEFINITION_OF_DONE.md` Gate B: migrations create DB from clean state | Satisfied — Alembic migration from empty DB |
| `03_DEFINITION_OF_DONE.md` Gate B: no hardcoded Golden Scenario results | Satisfied — no domain data in Phase 1 |
| `04_ACCEPTANCE_TESTS.md` AT-001 (clean deployment) | Partially — local Docker clean deploy; public deployment deferred to Phase 7 |
| `04_ACCEPTANCE_TESTS.md` AT-002 (demo authentication) | See blocking decision BD-1 |
| `06_AI_AGENT_EXECUTION_RULES.md` §3: task format | Each work package follows the required task format |
| `06` §4: mandatory cycle (inspect → propose → implement → check → fix → check → docs → commit → evidence) | Each WP follows this cycle |
| `06` §7: evidence contract (branch, commit, files, commands, results, limitations, tree status) | Implementation agent must provide this per WP |
| `06` §10: stop conditions | Correlation ID format (DEC-024), polling (DEC-012) are now accepted decisions that Phase 1 uses |

## 5. Definition of Done for Phase 1

Phase 1 is complete when ALL of the following are true and verified with executable evidence:

### 5.1 Database
- [ ] SQLAlchemy async engine and session factory exist in `backend/app/database.py`
- [ ] At least one ORM model exists for the diagnostic job table
- [ ] Alembic `env.py` references `Base.metadata` (target_metadata is not None)
- [ ] At least one migration exists in `backend/alembic/versions/`
- [ ] Migration runs successfully from a clean PostgreSQL instance
- [ ] `alembic current` returns the expected revision after migration

### 5.2 Backend
- [ ] Correlation ID middleware generates UUID v4 per request
- [ ] Correlation ID appears in structured logs (structlog JSON output)
- [ ] Correlation ID appears in API responses (header or body)
- [ ] `GET /health` returns real dependency status (PG, Redis, worker, Alembic revision)
- [ ] `GET /api/v1/system/status` returns all required system information fields
- [ ] `POST /api/v1/system/diagnostics` enqueues a real ARQ job and returns job ID + correlation ID
- [ ] `GET /api/v1/system/diagnostics/{job_id}` returns job status and result
- [ ] Build metadata (version + Git SHA) is exposed in the API
- [ ] All endpoints have Pydantic request/response schemas
- [ ] ruff check passes
- [ ] mypy strict passes
- [ ] pytest passes (unit + integration tests for new endpoints)
- [ ] No hardcoded/fake service statuses — all health data is real

### 5.3 Worker
- [ ] At least one ARQ job function is registered in `WorkerSettings.functions`
- [ ] Worker connects to Redis and processes the diagnostic job
- [ ] Worker writes diagnostic result to PostgreSQL
- [ ] Worker logs include correlation ID
- [ ] Worker availability is detectable from the backend (Redis queue check)

### 5.4 Frontend
- [ ] React Router is configured with at least the control-plane route
- [ ] TanStack Query is configured with an API client
- [ ] System status panel displays real backend-derived data
- [ ] "Run system diagnostic" button calls the backend API
- [ ] Diagnostic job status is polled and displayed until terminal state
- [ ] Loading, empty, error, and success states are implemented
- [ ] Correlation ID is visible in the UI
- [ ] No fake/mock data — all values come from the backend API
- [ ] ESLint passes
- [ ] TypeScript type-check passes
- [ ] Vite build succeeds
- [ ] Vitest tests pass (at least one component test)

### 5.5 Infrastructure
- [ ] `docker compose up -d --build` starts all services
- [ ] All services reach healthy state
- [ ] Caddy serves the frontend and proxies `/api/*` to the backend
- [ ] The full diagnostic flow works through Caddy (not just direct backend access)

### 5.6 CI
- [ ] Backend CI passes (ruff, mypy, pytest)
- [ ] Frontend CI passes (eslint, tsc, vitest, build)
- [ ] No secrets committed
- [ ] Docker Compose config validates

## 6. Acceptance-Test Gates

| Gate ID | Description | Verification Command | Expected Evidence |
|---------|-------------|---------------------|-------------------|
| P1-G1 | Docker Compose config valid | `docker compose config > /dev/null` | exit 0 |
| P1-G2 | Backend ruff | `cd backend && ruff check .` | "All checks passed" |
| P1-G3 | Backend mypy | `cd backend && mypy app/` | "Success: no issues found" |
| P1-G4 | Backend pytest | `cd backend && pytest -v` | all pass |
| P1-G5 | Alembic migration from clean | `docker compose down -v && docker compose up -d && docker compose exec backend alembic upgrade head` | revision applied |
| P1-G6 | Alembic current revision | `docker compose exec backend alembic current` | prints revision hash |
| P1-G7 | Frontend eslint | `cd frontend && npm run lint` | 0 errors |
| P1-G8 | Frontend tsc | `cd frontend && npm run type-check` | 0 errors |
| P1-G9 | Frontend build | `cd frontend && npm run build` | build success |
| P1-G10 | Frontend vitest | `cd frontend && npm run test` | all pass |
| P1-G11 | Full stack up | `docker compose up -d --build` && wait for healthy | all services healthy |
| P1-G12 | Health endpoint real checks | `curl http://localhost/health` | JSON with PG/Redis/worker/revision fields |
| P1-G13 | System status API | `curl http://localhost/api/v1/system/status` | all required fields present, real values |
| P1-G14 | Diagnostic enqueue | `curl -X POST http://localhost/api/v1/system/diagnostics` | 202 with job_id + correlation_id |
| P1-G15 | Diagnostic job completes | Poll `GET /api/v1/system/diagnostics/{job_id}` until terminal | status=completed, checks present |
| P1-G16 | Worker processed job | `docker compose logs worker` contains correlation ID | structured log with correlation_id |
| P1-G17 | Secret scan | `./scripts/check-secrets.sh` | "No secrets detected" |
| P1-G18 | Frontend loads through Caddy | `curl http://localhost` | HTML with root div |

## 7. Source of Truth Requirements Mapping

| SoT Requirement | Phase 1 Coverage | Evidence |
|----------------|-------------------|----------|
| `07` Phase 1: React frontend | Control Plane UI | P1-G9, P1-G18 |
| `07` Phase 1: FastAPI backend | System status + diagnostic API | P1-G4, P1-G13 |
| `07` Phase 1: PostgreSQL | Diagnostic jobs persisted | P1-G5, P1-G15 |
| `07` Phase 1: migrations | Alembic migration | P1-G5, P1-G6 |
| `07` Phase 1: health checks | Expanded /health | P1-G12 |
| `07` Phase 1: Docker Compose | Full stack | P1-G11 |
| `07` Phase 1: basic login page | **Blocking decision BD-1** | — |
| `07` Phase 1 exit: clean deployment | Docker compose from clean | P1-G5, P1-G11 |
| `07` Phase 1 exit: frontend→backend | API calls from React | P1-G13, P1-G14 |
| `07` Phase 1 exit: backend→database | PG connectivity in health | P1-G12 |
| `07` Phase 1 exit: automated smoke test | P1-G12 through P1-G16 | all pass |
| `03` Gate B: migrations from clean state | Alembic from clean PG | P1-G5 |
| `03` Gate B: no hardcoded results | No fake statuses | manual verification |
| `06` §7: evidence contract | Per-WP evidence report | commit messages + test output |
| `06` §8: dependency justification | Any new dep justified in WP | WP documentation |
| `06` §10: stop conditions | Correlation ID (DEC-024), polling (DEC-012), state management (DEC-015) accepted/recorded | Decision Log |

## 8. Product Owner Decisions — RESOLVED

All six blocking decisions have been resolved by the Product Owner (2026-07-15).
Phase 1 is unblocked. See Decision Log entries DEC-012 (polling, updated for
Phase 1), DEC-015 (state management, open with Phase 1 note), DEC-017
(component library), DEC-024 (correlation ID format), DEC-029 (authentication
deferral), and DEC-033 (feature branch).

### BD-1 — Authentication Inclusion — APPROVED WITH CONSTRAINTS (DEC-029)

**Decision:** Defer all authentication to Phase 2. Phase 1 does not implement
login, JWT, sessions, RBAC, or demo accounts.

**Constraints (Product Owner):**
- Phase 1 must not be publicly deployed.
- Phase 1 must not process real, sensitive, or production data.
- Diagnostic endpoints must be documented as development/demo-only.

**Recorded in:** 08_DECISION_LOG.md DEC-029.

### BD-2 — Correlation ID Format — APPROVED (DEC-024)

**Decision:** UUID v4.

**Recorded in:** 08_DECISION_LOG.md DEC-024.

### BD-3 — Polling for Real-Time Updates — APPROVED FOR PHASE 1 ONLY (DEC-012)

**Decision:** HTTP polling every 3 seconds while a diagnostic job is pending
or running. No WebSocket or SSE in Phase 1. Not the permanent real-time
architecture decision for later phases.

**Recorded in:** 08_DECISION_LOG.md DEC-012 (updated, Phase 1 scope only).

### BD-4 — Component Library — APPROVED (DEC-017)

**Decision:** shadcn/ui with Tailwind CSS.

**Recorded in:** 08_DECISION_LOG.md DEC-017.

### BD-5 — State Management — REJECTED FOR PHASE 1 (DEC-015)

**Decision:** Do not add Zustand. Use React hooks and local component state
for the Phase 1 control plane. DEC-015 remains open for reconsideration when
application state complexity provides a demonstrated need.

**Recorded in:** 08_DECISION_LOG.md DEC-015 (Phase 1 note in decision body).

### BD-6 — Phase 1 Feature Branch Name — APPROVED (DEC-033)

**Decision:** `feature/phase-1-running-skeleton`

**Recorded in:** 08_DECISION_LOG.md DEC-033.

## 9. Technical Risks and Stop Conditions

| Risk | Likelihood | Impact | Mitigation | Stop? |
|------|-----------|--------|------------|-------|
| Docker Compose services don't reach healthy on PO's machine | Medium | High | Verify with `docker compose ps` before claiming done; document any platform-specific issues | YES — cannot verify without running stack |
| ARQ worker can't connect to Redis with password | Low | High | Worker already parses Redis URL with password; verify in dev compose | YES — worker is core to the vertical |
| Alembic migration fails on clean PG | Low | High | Test from `docker compose down -v` before claiming done | YES — Gate B requirement |
| Structured logging not actually structured (stdout text) | Medium | Medium | Verify log output is valid JSON with `docker compose logs backend \| jq .` | NO — fixable after detection |
| Correlation ID not propagating to worker logs | Medium | High | Verify worker logs contain the same correlation_id as the API response | YES — auditability requirement |
| Frontend shows stale/fake data | Medium | High | Verify all displayed values come from API calls; no hardcoded status strings | YES — SoT prohibits fake data |
| shadcn/ui initialization conflicts with existing Tailwind config | Low | Medium | Use `shadcn-ui init` with existing Tailwind; verify build passes | NO — fixable |
| Health check blocks on slow PG/Redis | Low | Medium | Add timeouts to dependency checks (2s each); don't let /health hang | NO — fixable |

**Stop conditions (from `06` §10):**
- Requirements contradict Source of Truth → stop.
- Scope change needed → stop, get PO approval.
- Missing credentials → stop.
- Migration may destroy data → stop.
- Acceptance criteria cannot be verified → stop.
- External API has unknown license/cost → stop.
- Deployment action may break another VPS service → stop (not applicable in Phase 1 — no VPS deployment).

## 10. Database Foundation for Diagnostic Scenario

### 10.1 Table: `diagnostic_jobs`

Only one table is needed for Phase 1. No business schema, no pgvector, no
seed data.

```sql
CREATE TABLE diagnostic_jobs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    correlation_id  UUID NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending | running | completed | failed
    triggered_by    VARCHAR(100),
    checks          JSONB,
    -- {"postgresql": "ok", "redis": "ok", "worker": "ok", ...}
    error_message   TEXT,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    duration_ms     INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_diagnostic_jobs_correlation_id ON diagnostic_jobs(correlation_id);
CREATE INDEX idx_diagnostic_jobs_created_at ON diagnostic_jobs(created_at DESC);
```

### 10.2 Alembic Migration

- First migration: `create_diagnostic_jobs_table`
- Must be runnable from clean database (`alembic upgrade head` from empty PG)
- `env.py` must import `Base.metadata` from the models module
- `alembic current` must return the revision after migration

### 10.3 No Other Tables

Phase 1 creates ONLY the `diagnostic_jobs` table. No users, roles, business
entities, or knowledge entities. The `alembic_version` table is created
automatically by Alembic.

## 11. API Contracts and Background-Job Lifecycle

### 11.1 API Endpoints

All under prefix `/api/v1`.

#### `GET /health`
**Response 200:**
```json
{
  "status": "healthy" | "degraded" | "unhealthy",
  "timestamp": "2026-07-15T14:00:00Z",
  "correlation_id": "uuid-v4",
  "checks": {
    "backend": "ok",
    "postgresql": "ok" | "error: ...",
    "redis": "ok" | "error: ...",
    "worker": "ok" | "unavailable",
    "alembic_revision": "<hash>"
  }
}
```

#### `GET /api/v1/system/status`
**Response 200:**
```json
{
  "correlation_id": "uuid-v4",
  "version": "0.1.0",
  "git_sha": "<short-sha>",
  "environment": "development" | "production",
  "alembic_revision": "<hash>",
  "latency_ms": 42,
  "checks": {
    "postgresql": {"status": "ok", "latency_ms": 5},
    "redis": {"status": "ok", "latency_ms": 2},
    "worker": {"status": "ok", "queue": "forgemind-tasks"}
  },
  "latest_diagnostic": {
    "id": "uuid",
    "status": "completed" | "pending" | "running" | "failed",
    "completed_at": "2026-07-15T14:00:00Z",
    "duration_ms": 150
  }
}
```

#### `POST /api/v1/system/diagnostics`
**Request body:** (optional)
```json
{
  "triggered_by": "operator"
}
```
**Response 202:**
```json
{
  "job_id": "uuid",
  "correlation_id": "uuid-v4",
  "status": "pending"
}
```

#### `GET /api/v1/system/diagnostics/{job_id}`
**Response 200:**
```json
{
  "id": "uuid",
  "correlation_id": "uuid-v4",
  "status": "pending" | "running" | "completed" | "failed",
  "checks": {
    "postgresql": "ok",
    "redis": "ok",
    "worker": "ok"
  },
  "error_message": null,
  "started_at": "2026-07-15T14:00:00Z",
  "completed_at": "2026-07-15T14:00:01Z",
  "duration_ms": 150,
  "created_at": "2026-07-15T14:00:00Z"
}
```
**Response 404:** if job_id not found

### 11.2 Background-Job Lifecycle

```
1. POST /diagnostics
   ├── Generate correlation_id (UUID v4)
   ├── INSERT diagnostic_jobs (id, correlation_id, status='pending')
   ├── Enqueue ARQ job with (job_id, correlation_id)
   └── Return 202 {job_id, correlation_id, status='pending'}

2. Worker picks up job
   ├── UPDATE diagnostic_jobs SET status='running', started_at=now()
   ├── Run checks:
   │   ├── SELECT 1 (PostgreSQL)
   │   ├── PING (Redis)
   │   └── Check worker queue depth / self-ping
   ├── UPDATE diagnostic_jobs SET status='completed', checks={...},
   │   completed_at=now(), duration_ms=...
   └── Log structured event with correlation_id

3. Frontend polls GET /diagnostics/{job_id} every 3-5s
   └── Displays status transitions: pending → running → completed

Error path:
   ├── UPDATE diagnostic_jobs SET status='failed', error_message=...
   └── Log error with correlation_id
```

### 11.3 Pydantic Schemas

- `SystemStatusResponse` — fields per §11.1
- `DiagnosticCreateRequest` — optional `triggered_by`
- `DiagnosticCreateResponse` — `job_id`, `correlation_id`, `status`
- `DiagnosticJobResponse` — full job detail
- `HealthResponse` — health check composite

## 12. Frontend Control-Plane States and Error Handling

### 12.1 Routes

```
/ → redirect to /control-plane
/control-plane → Operations Control Plane (main route)
```

No other routes in Phase 1 (login deferred per BD-1 recommendation).

### 12.2 Component Structure

```
src/
├── routes/
│   └── control-plane.tsx        # Main control-plane page
├── components/
│   ├── layout/
│   │   └── app-shell.tsx        # Header, sidebar shell
│   ├── system/
│   │   ├── status-panel.tsx     # System status grid
│   │   ├── service-card.tsx     # Individual service health card
│   │   ├── diagnostic-trigger.tsx  # "Run system diagnostic" button
│   │   └── diagnostic-result.tsx   # Job status + result display
│   └── ui/                      # shadcn/ui primitives
├── hooks/
│   ├── use-system-status.ts     # TanStack Query for /system/status
│   └── use-diagnostic.ts        # Post + poll diagnostic job
├── lib/
│   ├── api-client.ts            # Fetch wrapper, base URL, error handling
│   └── query-client.ts          # TanStack Query client config
```

### 12.3 States

| State | Trigger | Display |
|-------|---------|---------|
| Loading | Initial fetch | Skeleton/spinner, no fake data |
| Healthy | All checks "ok" | Green indicators, real latency values |
| Degraded | One+ check failing | Yellow/red indicator for failing service |
| Error | Backend unreachable | Error message, retry button, no fake data |
| Diagnostic pending | Job status=pending | "Diagnostic queued..." with correlation ID |
| Diagnostic running | Job status=running | "Running checks..." with live correlation ID |
| Diagnostic completed | Job status=completed | Results table with per-check status |
| Diagnostic failed | Job status=failed | Error message from backend, retry button |

### 12.4 Polling

- Poll `GET /api/v1/system/status` every 10s for system status
- When diagnostic is running, poll `GET /api/v1/system/diagnostics/{job_id}` every 3s
- Stop polling when terminal state (completed/failed) is reached
- Use TanStack Query `refetchInterval` with conditional logic

### 12.5 Design System

- Dark industrial theme (steel-900 background, already in `tailwind.config.ts`)
- Primary accent (primary-400/500, already configured)
- Monospace font for technical values (correlation ID, Git SHA, revision hash)
- Card-based layout for service status
- Real data only — no hardcoded statuses, no decorative charts

## 13. Observability Requirements

### 13.1 Structured Logs

- Use `structlog` (already in `pyproject.toml`)
- JSON output to stdout
- Every log entry includes: `timestamp`, `level`, `event`, `correlation_id`
- Configure in `backend/app/core/logging.py`
- Apply to both backend and worker

### 13.2 Correlation IDs

- Generate UUID v4 per HTTP request (middleware)
- Attach to request context (contextvar)
- Include in all log entries within the request
- Include in API responses (header `X-Correlation-ID` and response body)
- Pass to ARQ jobs as parameter
- Worker logs include the same correlation_id
- Visible in frontend UI

### 13.3 Health/Readiness Semantics

- `GET /health` — liveness: "is the process running?" Returns 200 if the
  process is up. Includes dependency checks for observability but does NOT
  fail if a dependency is down (returns `degraded` status).
- `GET /ready` — readiness: "can this handle traffic?" Returns 200 only if
  PG and Redis are reachable. Returns 503 if a critical dependency is down.
  Used by Docker healthcheck and Caddy.
- Worker availability: check if the ARQ queue has active workers by
  querying Redis for the queue configuration. Not a direct ping — use
  `arq`'s built-in queue inspection.

### 13.4 Build/Version Metadata

- Application version: from `pyproject.toml` (`version = "0.1.0"`)
- Git SHA: at build time, write to a file or environment variable.
  Approach: Docker build step runs `git rev-parse --short HEAD` and sets
  `GIT_SHA` env var. Alternatively, write a `backend/app/_version.py` at
  build time. The simplest approach: read from environment variable
  `GIT_SHA` with fallback to `"unknown"`.
- Exposed in `GET /api/v1/system/status` as `version` and `git_sha`.

## 14. Ordered Implementation Plan — Atomic Work Packages

Each work package follows the task format from `06_AI_AGENT_EXECUTION_RULES.md` §3.

### WP-1: Database Foundation

**Goal:** Create SQLAlchemy async engine, session factory, Base, and the
diagnostic_jobs ORM model. Fix Alembic env.py.

**In scope:**
- `backend/app/database.py` — async engine, session factory, Base
- `backend/app/models/__init__.py` — package init
- `backend/app/models/diagnostic.py` — DiagnosticJob model
- Fix `backend/alembic/env.py` — import Base.metadata, set target_metadata

**Out of scope:** migration generation (WP-2), API endpoints, frontend.

**Files allowed to change:** `backend/app/database.py` (new),
`backend/app/models/` (new), `backend/alembic/env.py` (modify).

**Files forbidden to change:** `backend/app/main.py`, `backend/app/config.py`,
`backend/app/worker.py`, frontend, infra, CI.

**Acceptance criteria:**
- `from app.database import Base, engine` works
- `from app.models.diagnostic import DiagnosticJob` works
- `alembic env.py` loads without error
- ruff + mypy pass on new files

**Commands:** `cd backend && ruff check . && mypy app/ && python -c "from app.models.diagnostic import DiagnosticJob"`

### WP-2: Alembic Migration

**Goal:** Generate and verify the initial Alembic migration creating
`diagnostic_jobs` table.

**In scope:**
- `backend/alembic/versions/<hash>_create_diagnostic_jobs_table.py`

**Out of scope:** API, frontend, worker.

**Files allowed to change:** `backend/alembic/versions/` (new file).

**Files forbidden to change:** all existing files.

**Acceptance criteria:**
- `alembic upgrade head` runs from clean PG
- `alembic current` returns the revision
- `diagnostic_jobs` table exists with correct columns
- ruff passes on migration file

**Commands:** `cd backend && alembic revision --autogenerate -m "create diagnostic_jobs table" && alembic upgrade head && ruff check .`

### WP-3: Core Infrastructure

**Goal:** Create correlation ID middleware, structured logging, build metadata.

**In scope:**
- `backend/app/core/__init__.py`
- `backend/app/core/correlation.py` — UUID v4 generation, contextvar, middleware
- `backend/app/core/logging.py` — structlog configuration
- `backend/app/core/build_info.py` — version + Git SHA

**Out of scope:** API endpoints, worker functions, frontend.

**Files allowed to change:** `backend/app/core/` (new), `backend/app/main.py`
(add middleware + logging).

**Files forbidden to change:** `config.py`, `worker.py`, frontend, infra.

**Acceptance criteria:**
- Every HTTP response has `X-Correlation-ID` header
- Logs are valid JSON with `correlation_id` field
- Build info endpoint returns version + Git SHA
- ruff + mypy + pytest pass

**Commands:** `cd backend && ruff check . && mypy app/ && pytest -v`

### WP-4: Health & System Status API

**Goal:** Expand `/health` with real dependency checks. Add
`GET /api/v1/system/status`.

**In scope:**
- `backend/app/api/__init__.py`
- `backend/app/api/router.py` — top-level router
- `backend/app/api/health.py` — expanded health endpoint
- `backend/app/api/system.py` — system status endpoint
- `backend/app/schemas/__init__.py`
- `backend/app/schemas/system.py` — Pydantic schemas
- Modify `backend/app/main.py` — include router

**Out of scope:** diagnostic endpoints (WP-5), worker functions, frontend.

**Files allowed to change:** `backend/app/api/` (new), `backend/app/schemas/`
(new), `backend/app/main.py` (modify to include router).

**Acceptance criteria:**
- `GET /health` returns real PG, Redis, worker, Alembic revision status
- `GET /api/v1/system/status` returns all required fields
- No fake/hardcoded statuses
- ruff + mypy + pytest pass (new tests for endpoints)

**Commands:** `cd backend && ruff check . && mypy app/ && pytest -v`

### WP-5: Diagnostic Background Job & API

**Goal:** Create ARQ diagnostic job function, register it in WorkerSettings,
add diagnostic API endpoints.

**In scope:**
- `backend/app/tasks/__init__.py`
- `backend/app/tasks/diagnostics.py` — `run_diagnostic` ARQ function
- `backend/app/schemas/diagnostic.py` — diagnostic request/response schemas
- `backend/app/api/diagnostics.py` — POST + GET endpoints
- Modify `backend/app/worker.py` — register `run_diagnostic`
- Modify `backend/app/api/router.py` — include diagnostics router

**Out of scope:** frontend.

**Files allowed to change:** `backend/app/tasks/` (new),
`backend/app/schemas/diagnostic.py` (new), `backend/app/api/diagnostics.py`
(new), `backend/app/worker.py` (modify), `backend/app/api/router.py` (modify).

**Acceptance criteria:**
- `POST /api/v1/system/diagnostics` returns 202 with job_id + correlation_id
- Worker processes the job and persists result to PostgreSQL
- `GET /api/v1/system/diagnostics/{job_id}` returns status + result
- Worker logs contain correlation_id
- ruff + mypy + pytest pass

**Commands:** `cd backend && ruff check . && mypy app/ && pytest -v`

### WP-6: Frontend Foundation

**Goal:** Set up React Router, TanStack Query, API client, app shell layout,
shadcn/ui initialization.

**In scope:**
- `frontend/src/App.tsx` — router setup
- `frontend/src/components/layout/app-shell.tsx`
- `frontend/src/lib/api-client.ts`
- `frontend/src/lib/query-client.ts`
- `frontend/components.json` — shadcn/ui config
- shadcn/ui init + first components (Card, Button, Badge)

**Out of scope:** control-plane components (WP-7).

**Files allowed to change:** `frontend/src/App.tsx` (modify),
`frontend/src/components/` (new), `frontend/src/lib/` (new),
`frontend/components.json` (new),
`frontend/package.json` (add shadcn deps if needed).

**Note:** No Zustand. State is managed via React hooks and local component
state per DEC-015. No `frontend/src/store/` directory in Phase 1.

**Acceptance criteria:**
- React Router renders the app shell
- TanStack Query is configured
- API client can fetch from `/api/v1`
- ESLint + tsc + build pass

**Commands:** `cd frontend && npm run lint && npm run type-check && npm run build`

### WP-7: Operations Control Plane UI

**Goal:** Build the system status panel, diagnostic trigger, and result display.

**In scope:**
- `frontend/src/routes/control-plane.tsx`
- `frontend/src/components/system/status-panel.tsx`
- `frontend/src/components/system/service-card.tsx`
- `frontend/src/components/system/diagnostic-trigger.tsx`
- `frontend/src/components/system/diagnostic-result.tsx`
- `frontend/src/hooks/use-system-status.ts`
- `frontend/src/hooks/use-diagnostic.ts`

**Out of scope:** backend changes, new API endpoints.

**Files allowed to change:** `frontend/src/routes/` (new),
`frontend/src/components/system/` (new), `frontend/src/hooks/` (new).

**Acceptance criteria:**
- System status panel shows real backend data
- "Run system diagnostic" button triggers the API
- Job status is polled and displayed
- All states (loading, healthy, degraded, error, diagnostic pending/running/completed/failed) work
- Correlation ID is visible
- No fake data
- ESLint + tsc + build + vitest pass

**Commands:** `cd frontend && npm run lint && npm run type-check && npm run build && npm run test`

### WP-8: Integration Verification

**Goal:** Verify the full stack runs end-to-end through Docker Compose.

**In scope:**
- Docker Compose up + all services healthy
- Full diagnostic flow through Caddy
- Structured log verification
- Alembic migration from clean state

**Out of scope:** new code (verification only).

**Files allowed to change:** none (verification only; may fix minor config issues).

**Acceptance criteria:**
- `docker compose up -d --build` — all services healthy
- `curl http://localhost/health` returns real checks
- `curl http://localhost/api/v1/system/status` returns all fields
- `curl -X POST http://localhost/api/v1/system/diagnostics` returns 202
- Polling the job returns `completed`
- Worker logs contain correlation_id
- `curl http://localhost` serves the frontend
- `docker compose down -v && docker compose up -d` — migration runs from clean

**Commands:** full P1-G11 through P1-G16 sequence.

### WP-9: CI & Documentation Sync

**Goal:** Update CI if needed, sync documentation with actual implementation,
create Phase 1 implementation log.

**In scope:**
- `.github/workflows/ci-backend.yml` — add integration test step if needed
- `docs/planning/phase_1_implementation_log.md` — evidence log
- `README.md` — update quick start if commands changed
- `docs/architecture.md` — create now that skeleton is running (deferred from Phase 0)

**Out of scope:** new functionality.

**Files allowed to change:** CI workflows, docs, README.

**Acceptance criteria:**
- CI passes on the feature branch
- Implementation log has evidence
- Architecture diagram reflects actual state

**Commands:** full CI suite + `make test && make lint`

## 15. Portfolio "Wow Effect" Without Expanding MVP Scope

The following elements provide genuine portfolio impact within Phase 1 scope:

1. **Real service health checks** — Not fake green dots. Each check
   performs a real query/ping and shows actual latency. Demonstrates
   production-grade observability thinking.

2. **Live diagnostic run with full traceability** — A real ARQ background
   job that executes through the worker, persists to PostgreSQL, and is
   traceable by correlation ID from button-click to worker log. This is
   the "not a set of static mocks" proof.

3. **Correlation ID visible end-to-end** — From the HTTP response header,
   through the API body, into the worker logs, and visible in the UI.
   Demonstrates auditability discipline early.

4. **Alembic revision in the UI** — Shows database migration awareness.
   A detail that signals engineering maturity.

5. **Git SHA in the UI** — Build provenance. Signals deployment discipline.

6. **Industrial design system** — Dark steel theme, monospace technical
   values, card-based status layout. Looks like an operations product,
   not a tutorial.

7. **Genuinely running full stack** — Browser → Caddy → React → FastAPI →
   PG → Redis → ARQ worker. All real, all running, all healthy. This is
   the "running skeleton" that proves the architecture works before
   domain logic is added.

8. **Polished state transitions** — Loading skeletons, error retries,
   diagnostic progress. Not a bare-bones UI.

None of these expand MVP scope. They are all infrastructure/observability
qualities that make the skeleton genuinely impressive.

## 16. GLM Review Checks After Qwen Implementation

After the implementation agent (Qwen) completes Phase 1, the architect/critic
model (GLM) should perform the following verification:

### 16.1 Automated Gate Verification (re-run fresh)
1. `docker compose down -v` — clean slate
2. `docker compose up -d --build` — full rebuild
3. Wait for all services healthy (`docker compose ps`)
4. `cd backend && ruff check .` — P1-G2
5. `cd backend && mypy app/` — P1-G3
6. `cd backend && pytest -v` — P1-G4
7. `docker compose exec backend alembic current` — P1-G6
8. `cd frontend && npm run lint` — P1-G7
9. `cd frontend && npm run type-check` — P1-G8
10. `cd frontend && npm run build` — P1-G9
11. `cd frontend && npm run test` — P1-G10
12. `./scripts/check-secrets.sh` — P1-G17

### 16.2 End-to-End Flow Verification
13. `curl -sf http://localhost/health | jq .` — verify real PG/Redis/worker/revision fields
14. `curl -sf http://localhost/api/v1/system/status | jq .` — verify all required fields present
15. `curl -sf -X POST http://localhost/api/v1/system/diagnostics | jq .` — verify 202 + job_id + correlation_id
16. Poll `GET /api/v1/system/diagnostics/{job_id}` until `completed` — P1-G15
17. Verify `checks` object has real results, not hardcoded strings

### 16.3 Anti-Cheat Verification
18. `docker compose logs backend | grep correlation_id | head -5` — verify structured logs have correlation_id
19. `docker compose logs worker | grep correlation_id | head -5` — verify worker logs have correlation_id
20. Verify the correlation_id in the API response matches the one in the worker logs
21. Grep frontend source for hardcoded status strings: `grep -r "healthy\|ok\|up" frontend/src/ --include="*.tsx" | grep -v "import\|type\|interface"` — verify no hardcoded statuses
22. Verify no `mock`, `fake`, `dummy`, `placeholder` in frontend src (except comments)
23. Verify no supply-risk, RAG, AI, approval, or procurement code exists (scope check)

### 16.4 Visual Review
24. Open `http://localhost` in browser
25. Screenshot the control plane
26. Verify: industrial design, real data, correlation ID visible, no fake charts
27. Click "Run system diagnostic" and screenshot the running state
28. Screenshot the completed state with results

### 16.5 Documentation Verification
29. Verify implementation log exists with evidence
30. Verify README reflects actual state
31. Verify no claims of functionality that doesn't exist
32. Verify Decision Log entries exist for accepted decisions

### 16.6 Scope Violation Check
33. Verify NO files exist for: risk engine, BOM, inventory, RAG, AI provider, prompts, approval, procurement, audit, RBAC, auth
34. Verify only `diagnostic_jobs` table exists in migrations
35. Verify no seed data generators exist
36. Verify no E2E Playwright tests exist (deferred)

## 17. Proposed Branch

```
feature/phase-1-running-skeleton
```

From `main` at `4e7879c3e1c4c576769720d52d2f43f1a3c1a418`.

## 18. Summary

Phase 1 delivers a genuinely running end-to-end application skeleton with
the Operations Control Plane as the vertical scenario. The plan creates
the minimal database foundation (one table), core infrastructure
(correlation IDs, structured logging, build metadata), real health checks,
a real ARQ background job, and a professional industrial-grade frontend.

No domain logic, no AI, no RAG, no auth (DEC-029, with constraints), no fake data.
No Zustand (DEC-015 — React hooks and local state only for Phase 1).

All six blocking Product Owner decisions have been resolved (2026-07-15).
Phase 1 is unblocked. See Decision Log entries DEC-012, DEC-015, DEC-017,
DEC-024, DEC-029, DEC-033.

## 19. Exit Criteria Verification

**Status:** ✅ COMPLETE
**Completion Date:** 2026-07-17
**Verified By:** Hermes Agent

All Section 5 exit criteria are satisfied. The final verification run
(239 backend tests, ruff + mypy clean, live smoke through worker pipeline)
confirms the Running Skeleton is production-grade.

**Key Commits:**
- `03de442` — Plan approved, branch created
- `6c1b586..48c69ba` — Database + core infrastructure (WPs 1-4)
- `82708af..dcaff04` — Diagnostic endpoints + worker (WP-5)
- `58a2635` — Runtime fix: align schema/ORM with worker output

See [Phase 1 Completion Report](../phase_1/phase_1_completion_report.md) for
full evidence, debt tracking, and Phase 2 handoff.
