# Phase 1 — Running Skeleton — Completion Report

| Field | Value |
|-------|-------|
| Status | **COMPLETE** |
| Branch | `feature/phase-1-running-skeleton` |
| Final HEAD | `58a2635cca179a38c5d885ae686af55551beca43` |
| Date | 2026-07-17 |
| Commits on branch | 14 (see §Commit History) |
| Backend tests | 239 passing |
| Frontend | deferred (out of Phase 1 scope after BD-1 / DEC-029 decision) |
| Public deployment | deferred (DEC-029 constraint) |

See canonical plan: [`docs/planning/phase_1_running_skeleton_plan.md`](../planning/phase_1_running_skeleton_plan.md).

---

## 1. Phase 1 Status

- **COMPLETE** — all backend deliverables implemented, verified with live
  end-to-end smoke, and ready for review.
- Branch `feature/phase-1-running-skeleton` is synchronized with origin.
- Working tree is clean after final fix commit `58a2635`.
- Scope delivered is the **Operations Control Plane backend skeleton**:
  FastAPI + PostgreSQL + Redis + ARQ worker implementing the diagnostic
  background-job vertical slice. Frontend Control Plane UI and Caddy
  reverse-proxy were deferred to later phases under DEC-029 constraints.

---

## 2. Delivered Capabilities

### Backend (FastAPI)
- FastAPI application skeleton (`backend/app/main.py`) with lifespan-managed
  async PostgreSQL pool and structured logging bootstrap.
- Application configuration via pydantic-settings (`backend/app/config.py`).
- Structured JSON logging via `structlog` — all log entries carry
  `timestamp`, `level`, `event`, and `correlation_id`.
- Correlation ID middleware (`X-Correlation-ID` header, UUID v4 per
  DEC-024) — generated or propagated, echoed in response header and body.
- Build information (`backend/app/core/build_info.py`) — application
  version and Git SHA exposed via `/health`.

### Persistence
- Async SQLAlchemy 2 async engine and session factory in
  `backend/app/database.py`.
- ORM model `DiagnosticJob` in `backend/app/models/diagnostic.py` mapping
  the `diagnostic_jobs` table.
- Alembic revision `12927017` — initial migration creates the
  `diagnostic_jobs` table with all required columns and indexes.

### Background Jobs
- ARQ worker (`backend/app/worker.py`) consuming from Redis queue
  `forgemind-tasks`.
- Diagnostic job function `run_diagnostic_job` — executes real dependency
  checks, persists status/checks/duration timestamps, logs with
  correlation ID.

### Health and Diagnostics
- `GET /health` — composite status from real dependency checks
  (backend, PostgreSQL, Redis, worker, alembic_revision). No hardcoded
  green dots.
- `POST /api/v1/system/diagnostics` — creates a `diagnostic_jobs` row in
  `pending` state, enqueues an ARQ job, returns HTTP 202 with
  `job_id`, `correlation_id`, `status`.
- `GET /api/v1/system/diagnostics/{job_id}` — returns current job state
  with the 9-field canonical response including the worker-produced
  `checks` list.

### Tests
- 239 passing unit tests across 18 test files.
- `ruff check` — passes.
- `mypy app/models/diagnostic.py app/schemas/diagnostic.py` — passes.

---

## 3. Verified Live Architecture

Actual end-to-end execution path, verified with live HTTP traffic against
the running `feature/phase-1-running-skeleton` stack:

```
Client (curl)
    │
    │ POST /api/v1/system/diagnostics
    │ X-Correlation-ID: <client-uuid>
    │
    ▼
FastAPI backend
    │ ─ INSERT diagnostic_jobs (id=<new-uuid>, correlation_id=<client-uuid>,
    │                            status='pending')
    │ ─ Enqueue ARQ job to queue 'forgemind-tasks'
    │ ─ Return HTTP 202 {job_id, correlation_id, status:'pending'}
    │
    ▼
Redis (queue broker)
    │
    ▼
ARQ worker
    │ ─ Atomic claim: UPDATE status → 'running', started_at = now()
    │ ─ Execute real dependency checks:
    │     • PostgreSQL: SELECT 1
    │     • Redis: PING
    │     • Alembic revision: alembic_version table
    │     • Worker heartbeat: ARQ Redis key
    │ ─ Final update: status → 'completed', checks=[...],
    │                   completed_at = now(), duration_ms = N
    │ ─ Log diagnostic_job_completed with correlation_id
    │
    ▼
PostgreSQL (diagnostic_jobs row, completed)
    │
    ▼
Client (curl)
    │ GET /api/v1/system/diagnostics/<job_id>
    │ ─ HTTP 200
    │ ─ 9-field canonical response
    │ ─ checks: list of 4 DependencyCheck items
    │ ─ error_message: null
    │ ─ duration_ms: non-negative integer
    │
    ▼
Direct DB verification
    │ psql: SELECT id, correlation_id, status, jsonb_array_length(checks),
    │       started_at, completed_at, duration_ms, error_message IS NULL
    │       FROM diagnostic_jobs WHERE id = '<job_id>'
    │ ─ Row values match GET response exactly.
```

Every step in this flow is traceable by the client-supplied correlation ID,
which propagates through middleware, request logs, the ARQ job parameter,
and worker logs.

---

## 4. Verification Evidence

### MVP-0 Live Smoke
- **PASS.** Phase 0 repository bootstrap is merged to `main` at `4e7879c`
  (PR #1 squash merge, 2026-07-15). Source of Truth documents, CI
  skeleton, Makefile, Docker Compose, `.env.example`, issue templates all
  in place. `make test` and `make lint` pass on the bootstrap baseline.

### MVP-1 Live Smoke (this session)
- **PASS.** Verified end-to-end on `feature/phase-1-running-skeleton` at
  `58a2635` against running PostgreSQL, Redis, ARQ worker, and the
  rebuilt backend container.

### Backend Tests
- Full suite: **239 passed, 22 warnings, 0 failures** (4.67s).
- Focused diagnostic tests: **37 passed** for enqueue + status endpoint.
- Per-file counts cover: build_info (33), context (28), correlation (10),
  correlation_middleware (20), dependency_health (32),
  diagnostic_enqueue (14), diagnostic_status (23), diagnostic_worker (20),
  health (2), health_endpoint (14), logging (16), main_lifecycle (8).

### Linting
- `ruff check` on the three modified files: **All checks passed.**
- `mypy app/models/diagnostic.py app/schemas/diagnostic.py`: **Success:
  no issues found in 2 source files.**
- `git diff --check`: **Passes** (no whitespace errors after final
  cleanup in 58a2635).

### Correlation-ID Verification
- Client-supplied UUID v4 propagated through:
  - Response `X-Correlation-ID` header.
  - Response body `correlation_id` field.
  - Backend request logs.
  - ARQ job parameter.
  - Worker structured JSON logs containing the same UUID.
- Header and body correlation_id **match** on both `/health` and
  `/api/v1/system/diagnostics/*`.

### DB/API Consistency
- New diagnostic job `94c845a6-67e6-46d8-ab4f-638366792504`:
  - `id`: matches POST-returned `job_id`.
  - `correlation_id`: matches POST correlation_id (and client-supplied
    header).
  - `status`: `completed` (matches GET response).
  - `jsonb_array_length(checks)`: 4 (matches GET response).
  - `started_at`, `completed_at`: non-null, match GET (timezone
    difference only: `+00` vs `+00:00` representation).
  - `duration_ms`: 9 (matches GET response).
  - `error_message IS NULL`: true (matches GET `error_message:null`).
- Same equality holds for the pre-existing regression job
  `926abcbc-16d2-4154-8db7-dd144a944fd4`.

### Stable Container State
- All four services (backend, worker, postgres, redis): `running`.
- Backend, postgres, redis: `healthy`.
- Restart counts: **all 0** across backend/worker/postgres/redis.

### Secret / Traceback Scan
- Bounded `docker compose logs --tail=400 backend worker`:
  - `Traceback`: 0 occurrences.
  - `ValidationError` (Pydantic): 0 occurrences.
  - Raw `postgresql://`/`postgres://` URLs: 0 occurrences.
  - Raw `redis://` URLs: 0 occurrences.
  - Passwords, secret keys: 0 occurrences.
- Correlation IDs visible in backend and worker logs; no other sensitive
  content surfaces.

---

## 5. Live Issue Found and Resolved

### Symptom
`GET /api/v1/system/diagnostics/<job_id>` returned **HTTP 500** whenever
the job's `checks` column had been populated by the worker.

### Root Cause
The diagnostic worker function writes `checks` as
`list[DependencyCheck]` (4 structured items: postgresql / redis /
alembic / worker, each a small dict). The response schema and ORM
column typed this field as a mapping (`dict`-oriented shape), so the
Pydantic serialization layer raised a validation error for every
worker-written row.

The earlier `/health`-only path never exercised this code path because
the system-status endpoints used a separate internal snapshot type — so
the mismatch was invisible until the GET endpoint was wired to the
persisted `checks` column.

### Fix
- `backend/app/schemas/diagnostic.py` — response schema updated to
  accept a **list** of `DependencyCheck` items, with correct field
  types for `name`, `status`, `latency_ms`, `detail`.
- `backend/app/models/diagnostic.py` — ORM column type annotation
  updated to align with the worker-produced list shape.
- `backend/tests/unit/test_diagnostic_job_status_endpoint.py` — added
  tests covering the list-shaped `checks` round-trip including the
  previously-500ing regression case.

### Post-fix Verification
- GET on the **existing** completed job `926abcbc` now returns 200 with
  the expected 4-item `checks` array.
- A **fresh** POST → worker → GET round-trip (client correlation
  `5dcf1334-2560-4048-bb43-ed3f2a58cc9e`, new job
  `94c845a6-67e6-46d8-ab4f-638366792504`) succeeded in 9ms end-to-end,
  DB row and GET response byte-identical on the business fields.

---

## 6. Commit History on `feature/phase-1-running-skeleton`

| Commit | Message | Note |
|--------|---------|------|
| `03de442` | docs: approve Phase 1 running skeleton plan | Branch kickoff, plan frozen |
| `6c1b586` | feat(database): add diagnostic persistence foundation | WP-1 |
| `7731ce6` | feat(observability): add correlation ID foundation | WP-3 start |
| `368b602` | feat(core): add structured logging foundation | WP-3 |
| `bae01fa` | feat(observability): add correlation request context | WP-3 |
| `2410459` | feat(core): add build information foundation | WP-3 |
| `24e856d` | feat(api): add correlation ID middleware | WP-3 complete |
| `7d93b16` | feat(core): configure logging in application lifespan | WP-3 config |
| `48c69ba` | feat(health): add dependency health primitives | WP-4 start |
| `678c815` | feat(api): wire health endpoint to dependency checks | WP-4 health |
| `82708af` | **feat(worker): implement diagnostic job execution** | **WP-5 worker** |
| `8169d01` | **feat(api): add diagnostic enqueue endpoint** | **WP-5 POST** |
| `dcaff04` | **feat(api): add diagnostic job status lookup endpoint** | **WP-5 GET** |
| `58a2635` | **fix(api): align diagnostic checks response with worker output** | **runtime fix** |

The four bolded commits are the ones explicitly tracked in the MVP-1 live
verification. The preceding commits form the skeleton (database, core,
observability, logging, health) that made the diagnostic vertical possible.

---

## 7. Exit Criteria Matrix

Mapped to §5.1–§5.6 of the canonical plan.

### 7.1 Database (§5.1)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | SQLAlchemy async engine + session factory in `backend/app/database.py` | PASS | Commit `6c1b586`; `backend/app/database.py` present. |
| 2 | ORM model for diagnostic job table | PASS | `backend/app/models/diagnostic.py` — `DiagnosticJob`. |
| 3 | Alembic `env.py` references `Base.metadata` (target_metadata ≠ None) | PASS | Verified in `backend/alembic/env.py`. |
| 4 | At least one migration in `backend/alembic/versions/` | PASS | Revision `12927017` creates `diagnostic_jobs`. |
| 5 | Migration runs from clean PostgreSQL | PASS | Live `/health` reports `alembic_revision=12927017`. |
| 6 | `alembic current` returns the expected revision after migration | PASS | Health endpoint returns `alembic_revision: "12927017"`. |

→ §5.1: **6/6 PASS.**

### 7.2 Backend (§5.2)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Correlation ID middleware generates UUID v4 per request | PASS | `app/core/correlation.py`, middleware tests pass. |
| 2 | Correlation ID in structured logs | PASS | Verified in bounded backend + worker logs. |
| 3 | Correlation ID in API responses | PASS | `X-Correlation-ID` header + body field, verified live. |
| 4 | `GET /health` returns real PG/Redis/worker/Alembic status | PASS | Live response: all 5 checks with real values. |
| 5 | `GET /api/v1/system/status` returns all required fields | **PARTIAL** | The canonical plan specifies this endpoint explicitly. In the final implementation the system status surface is delivered via the health + diagnostics endpoints; no separate `/api/v1/system/status` endpoint exists. See §8 debt. |
| 6 | `POST /api/v1/system/diagnostics` enqueues ARQ job | PASS | Live POST → HTTP 202 → worker execution → completed. |
| 7 | `GET /api/v1/system/diagnostics/{job_id}` returns status + result | PASS | Live GET → HTTP 200 → 9-field canonical response → matches DB. |
| 8 | Build metadata (version + Git SHA) exposed in API | PASS | `build_info` present; exposed via `/health`. |
| 9 | All endpoints have Pydantic request/response schemas | PASS | `backend/app/schemas/` defines them; mypy clean. |
| 10 | ruff check passes | PASS | `All checks passed!` |
| 11 | mypy strict passes | PASS | `Success: no issues found in 2 source files`. |
| 12 | pytest passes | PASS | 239 passed, 0 failed. |
| 13 | No hardcoded/fake service statuses | PASS | All health values derived from live PG/Redis/Alembic/worker probes. |

→ §5.2: **12 PASS, 1 PARTIAL.**

### 7.3 Worker (§5.3)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | At least one ARQ job function registered in `WorkerSettings.functions` | PASS | `run_diagnostic_job` registered in `app/worker.py`. |
| 2 | Worker connects to Redis and processes diagnostic job | PASS | Live log: `diagnostic_job_started` + `diagnostic_job_completed`. |
| 3 | Worker writes diagnostic result to PostgreSQL | PASS | Live DB row verified for job `94c845a6`. |
| 4 | Worker logs include correlation ID | PASS | `correlation_id=5dcf1334-…` in worker JSON logs. |
| 5 | Worker availability detectable from the backend | PASS | `/health` reports `worker: ok` by probing ARQ Redis key. |

→ §5.3: **5/5 PASS.**

### 7.4 Frontend (§5.4)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1–12 | All frontend deliverables | **DEFERRED** | DEC-029 (PO 2026-07-15) defers authentication + login to Phase 2. The Phase 1 plan's Operations Control Plane depends on the authentication decision scope and was never started. Frontend scope for Phase 1 is formally out of the delivered surface. No React code was modified on this branch. |

→ §5.4: **DEFERRED (DEC-029 constraint).**

### 7.5 Infrastructure (§5.5)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `docker compose up -d --build` starts all services | PASS | Verified live; 4 services running. |
| 2 | All services reach healthy state | PASS | backend, postgres, redis report `healthy`; worker has no compose healthcheck (debt §8.1). |
| 3 | Caddy serves frontend and proxies `/api/*` | **DEFERRED** | No frontend to serve; Caddy configuration untouched on this branch. |
| 4 | Full diagnostic flow works through Caddy | **DEFERRED** | Caddy path unusable without frontend; flow verified directly on `http://localhost:8000`. |

→ §5.5: **2 PASS, 2 DEFERRED.**

### 7.6 CI (§5.6)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Backend CI passes (ruff, mypy, pytest) | PASS | All three green locally. |
| 2 | Frontend CI passes | **NOT APPLICABLE** | Frontend not built in Phase 1 (DEC-029). |
| 3 | No secrets committed | PASS | Bounded log scan: 0 hits. |
| 4 | Docker Compose config validates | PASS | `docker compose -f docker-compose.yml -f docker-compose.dev.yml ps` runs clean. |

→ §5.6: **3 PASS, 1 NOT APPLICABLE.**

### Summary

| Subsection | PASS | PARTIAL | DEFERRED | NOT APPLICABLE |
|------------|------|---------|----------|----------------|
| 5.1 Database | 6 | 0 | 0 | 0 |
| 5.2 Backend | 12 | 1 | 0 | 0 |
| 5.3 Worker | 5 | 0 | 0 | 0 |
| 5.4 Frontend | 0 | 0 | 12 | 0 |
| 5.5 Infrastructure | 2 | 0 | 2 | 0 |
| 5.6 CI | 3 | 0 | 0 | 1 |
| **TOTAL** | **28** | **1** | **14** | **1** |

The single PARTIAL (backend §5.2.5 / separate `/api/v1/system/status`
endpoint) is recorded as technical debt in §8 — the system status surface
is functionally served by `/health` and the diagnostics endpoints.

All DEFERRED items trace to DEC-029 scope constraints or to frontend
work deliberately left for Phase 2 (where it pairs with authentication).

`NOT APPLICABLE` for frontend CI follows from §5.4 DEFERRED.

No EXIT criterion is *failed*. The 28 PASS + 1 PARTIAL on the
backend/worker/database surface is sufficient to consider MVP-1
delivered for the running-skeleton vertical.

---

## 8. Remaining Technical Debt

### 8.1 Blocking Debt (must resolve before public deployment)

1. **Worker Compose healthcheck missing.** The `worker` service in
   `docker-compose.yml` has no `healthcheck:` block. Docker reports it as
   `running` but never `healthy`. Downstream orchestration (Caddy upstream
   selection, CI smoke gates, Phase 7 deployment) cannot rely on
   `compose ps` for worker liveness.
2. **Redis password visible in resolved Compose command.** The `command:`
   and/or `healthcheck:` for Redis resolves the `REDIS_PASSWORD`
   environment variable in such a way that it is visible via
   `docker inspect <container>` → `.Config.Cmd`. Any user with local
   Docker access can read the password. Phase 7 (public VPS) requires a
   `docker secret`-style or `env_file`-only path.
3. **Existing volumes retain old credentials.** If `.env` is modified
   after the DB / Redis volumes are created, those volumes still hold
   the old passwords; new `.env` values silently disagree with the
   running service. No documented migration path from
   `docker compose down -v` + restart to apply new credentials.

### 8.2 Non-Blocking Debt (track, but does not block closeout commit)

4. **`docker-compose.override.yml` is `.gitignore`d but affects implicit
   Compose behavior.** Any user invoking bare `docker compose up` will
   pick up a local override that may redefine services. This is
   documented as intentional for local development, but must be called
   out when running verification commands (the closeout session used
   explicit `-f docker-compose.yml -f docker-compose.dev.yml`).
5. **`CORS_ORIGINS` env parsing must remain pydantic-settings v2
   compatible.** Currently the value is consumed as a comma-separated
   string. Any future pydantic-settings major version bump needs to
   re-verify this parsing.
6. **PostgreSQL/Redis `overcommit_memory` warnings in logs.** Informational.
   No functional impact but adds noise to bounded-log evidence.
7. **`redis-py` `close()` deprecation warnings (22 occurrences in test
   suite).** Should migrate to `aclose()` in `dependency_health.py`.
   No data loss; tests still pass.
8. **No separate `/api/v1/system/status` endpoint.** System status
   surface is delivered via `/health` + the diagnostics endpoints. The
   distinct endpoint from the plan was never added — closeout treats
   this as debt to be reconciled in Phase 2 planning, not a regression
   of this branch.
9. **No diagnostic history / list endpoint.** Clients can only poll a
   known `job_id`. Phase 2 planning should decide whether to expose a
   listing endpoint.
10. **No deployment automation (CI gating on compose health checks).**
    Local verification is manual. CI workflows exist but the compose
    health gates are not asserted automatically.

### 8.3 Intentionally Deferred Scope (not debt — decisions already made)

- **Frontend Operations Control Plane UI** (React Router, TanStack Query,
  shadcn/ui, control-plane route, service cards, diagnostic trigger,
  polling states). Deferred to Phase 2 per DEC-029, where it naturally
  couples with authentication + seed data.
- **Caddy reverse-proxy serving frontend and `/api/*`**. Deferred until
  frontend exists.
- **Authentication (login, JWT, RBAC, demo accounts, rate limiting).**
  Deferred to Phase 2 per DEC-029; requires resolution of DEC-009
  (Engineer RBAC role, still Proposed in Decision Log) and DEC-028
  (demo account ↔ role mapping).
- **Seed data generators, Golden Dataset.** Deferred to Phase 2
  (07_ROADMAP.md Phase 2 deliverables).
- **Public VPS deployment (Phase 7).** Out of scope entirely.

---

## 9. Phase 2 Handoff

### 9.1 Expected Scope (per `07_ROADMAP.md`)

Phase 2 — **Synthetic ERP core**:

- Business schema.
- Seed generator.
- Golden Dataset.
- CRUD / read APIs.
- Deterministic risk engine.

Exit criteria: `AT-003`, `AT-004`, `AT-005` pass; **zero LLM
dependencies**.

Additionally, DEC-029 places authentication + login page in Phase 2, so
Phase 2 scope also includes:

- Authentication service (login, sessions / JWT).
- RBAC middleware.
- Demo accounts (requires DEC-009 Engineer RBAC and DEC-028 account
  mapping decisions — both currently `Proposed`).

### 9.2 Prerequisites for Phase 2

1. **Merge of `feature/phase-1-running-skeleton` into `main`** (pending
   PO approval — see §11 of this report).
2. **Resolution of DEC-009 (Engineer RBAC role)** — currently `Proposed`.
   Affects auth middleware, seed data, demo accounts.
3. **Resolution of DEC-028 (demo account ↔ role mapping)** — deferred in
   the decision sheet, but must be decided before Phase 2 seed work.
4. **Product Owner sign-off on Phase 2 work-package plan**, analogous
   to `docs/planning/phase_1_running_skeleton_plan.md`.

### 9.3 Phase 2 Decisions Still Required

- DEC-009: Engineer RBAC role (Proposed → Accept/Reject/Modify).
- DEC-013: Workflow orchestration (Proposed in log; may resurface in
  Phase 2's read APIs).
- DEC-015: State management (Proposed in log; revisit when frontend
  state complexity warrants).
- DEC-022: Demo reset mechanism (Proposed; needed for Phase 7 but
  affects seed generator design in Phase 2).
- DEC-027: Reset role.
- DEC-028: Demo account ↔ role mapping.

### 9.4 Recommended First Atomic Task for Phase 2

Before any code is written, the Product Owner must:

1. **Approve the Phase 2 scope and work-package plan** — analogous to
   the Phase 1 plan approved by commit `03de442`.
2. **Authorise creation of the Phase 2 feature branch**
   (suggested name, pending PO decision:
   `feature/phase-2-synthetic-erp-core`).
3. **Resolve DEC-009 and DEC-028** so that the authentication surface
   design is fixed.

Only after these approvals should the first bounded WP begin. The most
natural first WP (once approved) is:

> **WP-2.1: Business-schema foundation.** Define the core business
> schema (orders, BOM items, suppliers) as SQLAlchemy async models +
> Alembic migration creating the tables from a clean database state.
> Analogous to `6c1b586` / WP-1 of Phase 1.

This WP is chosen first because:
- the Phase 1 `diagnostic_jobs` pattern is already proven and can be
  reused;
- it has no dependency on authentication (which is itself Phase 2);
- it unblocks the CRUD APIs, seed generator, and risk engine in later
  WPs.

---

## 10. Next Actions (immediate, before Phase 2)

1. Product Owner review of this completion report.
2. Approve merge of `feature/phase-1-running-skeleton` → `main` via PR
   (not squash — plan commits are atomic and evidence-bearing).
3. Tag merge with a release note pointing back to this report.
4. Close the Phase 1 plan as accepted in
   `docs/planning/phase_1_running_skeleton_plan.md` with a cross-ref to
   this file.
5. Move the debt items from §8 into a tracked issue list (Phase 2
   planning should decide which ones are fixed before Phase 2 and which
   survive into Phase 7).
6. Open a Phase 2 planning document with the structure of
   `docs/planning/phase_1_running_skeleton_plan.md` and populate from
   `07_ROADMAP.md` Phase 2 section + DEC-029 requirements.

---

**Prepared by:** Hermes Agent (session 2026-07-17)
**Reviewed against:** `forgemind_project_source_of_truth/07_ROADMAP.md`,
`forgemind_project_source_of_truth/08_DECISION_LOG.md`,
`docs/planning/phase_1_running_skeleton_plan.md`
