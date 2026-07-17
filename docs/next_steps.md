# ForgeMind — Next Steps

**Last Updated:** 2026-07-17
**Current Phase:** Phase 1 (COMPLETE) — Phase 2 (PLANNING)

---

## Current Status

**Phase 1 — Running Skeleton: ✅ COMPLETE**

- **Branch:** `feature/phase-1-running-skeleton`
- **Final HEAD:** `58a2635cca179a38c5d885ae686af55551beca43`
- **MVP-1 live smoke:** PASS (full diagnostic flow verified end-to-end)
- **Completion Report:** [Phase 1 Completion Report](phase_1/phase_1_completion_report.md)

Phase 1 delivers the production-grade backend skeleton: FastAPI + PostgreSQL +
Redis + ARQ worker, structured logging, correlation ID traces, health checks,
and the diagnostic-job vertical slice. 239 backend tests passing, ruff + mypy
clean, live smoke verified.

---

## Immediate Actions (Phase 1 Closeout)

### 1. Merge Phase 1 to Main

**Action Required:** Product Owner approval
**Branch:** `feature/phase-1-running-skeleton` → `main`
**Recommended Strategy:** Merge commit (not squash — 14 commits evidence-bearing)

**Rationale:**
- All 14 Phase 1 commits are atomic and form a coherent implementation history
- Preserves the WP structure (database, core, diagnostics, runtime fix)
- Provides a clear audit trail for Phase 2 planning

**Steps (after PO approval):**
1. Open PR from `feature/phase-1-running-skeleton` → `main`
2. Include link to [Phase 1 Completion Report](phase_1/phase_1_completion_report.md)
3. Merge via GitHub merge commit (not squash, not rebase)
4. Tag: `phase-1-complete` pointing to merge commit
5. Release note: "Phase 1: Running Skeleton — MVP-1 verified, backend production-grade"

---

### 2. Track Technical Debt

**Location:** GitHub Issues (or project management tool)
**Source:** [Completion Report §8](phase_1/phase_1_completion_report.md#8-technical-debt)

Debt triage required before Phase 2 begins:

**Blocking debt** (must resolve before public deployment):
- Worker Compose healthcheck missing
- Redis password visible in resolved Compose command
- Existing volumes retain old `.env` credentials

**Non-blocking debt** (track, fix opportunistically):
- `redis-py` `close()` deprecation warnings (22 occurrences)
- No separate `/api/v1/system/status` endpoint (partial plan coverage)
- No diagnostic history/list endpoint
- No CI gating on compose health checks

**Recommendation:** Create GitHub issues for each debt item, label with `debt`,
prioritize blocking items for Phase 2 pre-flight, defer non-blocking to Phase 7.

---

## Phase 2 Planning (Next)

**Phase 2 — Synthetic ERP Core**
**Roadmap Reference:** [07_ROADMAP.md](../forgemind_project_source_of_truth/07_ROADMAP.md) Phase 2 section

### 2.1 Phase 2 Scope

Phase 2 delivers the business-schema foundation + seed data + deterministic
risk engine:

- **Business schema** — core tables (production plans, BOM items, suppliers,
  orders, parts) with foreign keys and indexes
- **Alembic migrations** — create schema from clean state, reversible
- **Seed generator** — deterministic fixture data for the Golden Dataset
- **Golden Dataset** — the "real-world" synthetic business dataset
- **CRUD / read APIs** — business-entity endpoints with validation
- **Deterministic risk engine** — pure Python/SQL arithmetic, no LLM dependencies

Exit criteria: `AT-003`, `AT-004`, `AT-005` pass; **zero LLM dependencies**.

### 2.2 Additional Phase 2 Requirements (from DEC-029)

Phase 2 also includes authentication + login page (deferred from Phase 1):

- Authentication service (login, JWT sessions)
- RBAC middleware (demo accounts for all 5 roles)
- Login page (frontend, once frontend scope is finalized)
- Rate limiting (Caddy + backend middleware)

### 2.3 Prerequisites for Phase 2

Before Phase 2 implementation begins, the Product Owner must approve:

1. ✅ Phase 1 merge to `main` (this step)
2. ⏳ Phase 2 work-package plan (analogous to `docs/planning/phase_1_…`)
3. ⏳ **DEC-009 resolution** — Engineer RBAC role (currently `Proposed`)
4. ⏳ **DEC-028 resolution** — demo account ↔ role mapping

Without DEC-009 and DEC-028, the authentication surface cannot be finalized.

### 2.4 Recommended First Atomic Task for Phase 2

Once Product Owner approves Phase 2 scope and decisions:

**WP-2.1 — Business-Schema Foundation**

- Define core business schema as SQLAlchemy async models
- Create Alembic migration(s) creating tables from clean state
- Follow the Phase 1 WP-1 pattern (`6c1b586`) for consistency
- Scope: orders, BOM items, suppliers, parts (no risk engine yet)

**Rationale for WP-2.1 first:**
- Reuses the proven Phase 1 database pattern
- No dependency on authentication (auth is a separate WP)
- Unblocks CRUD APIs, seed generator, and risk engine in later WPs
- Minimal scope, easy to verify with `make test + make dev`

---

## Phase 3+ (Future)

**Phase 3 — Core UI**
**Phase 4 — Knowledge and RAG**
**Phase 5 — Controlled AI workflow**
**Phase 6 — Approval and audit**
**Phase 7 — Public deployment**
**Phase 8 — Portfolio release**

Detailed in [`07_ROADMAP.md`](../forgemind_project_source_of_truth/07_ROADMAP.md).

Each phase requires:
- Approved work-package plan (analogous to Phase 1 plan)
- Resolved blocking decisions from the Decision Log
- Phase N-1 exit criteria satisfied (no phase skipping)

---

## Decision Log Status

See [`08_DECISION_LOG.md`](../forgemind_project_source_of_truth/08_DECISION_LOG.md) for full history.

**Resolved (Accepted) — Phase 1 uses these:**
- DEC-010: Python 3.12
- DEC-011: ARQ + Redis
- DEC-012: HTTP polling (Phase 1 only)
- DEC-014: Caddy
- DEC-017: shadcn/ui + Tailwind
- DEC-024: Correlation ID = UUID v4
- DEC-029: Authentication deferred to Phase 2
- DEC-033: Phase 1 branch = `feature/phase-1-running-skeleton`

**Proposed (pending PO decision) — Phase 2 needs these:**
- DEC-009: Engineer RBAC role
- DEC-013: Workflow orchestration
- DEC-015: State management
- DEC-022: Demo reset mechanism
- DEC-027: Reset role
- DEC-028: Demo account ↔ role mapping

---

## Documentation Index

**Planning:**
- [Phase 1 Running Skeleton Plan](planning/phase_1_running_skeleton_plan.md) ✅ COMPLETE
- [Phase 1 Completion Report](phase_1/phase_1_completion_report.md) ✅ NEW
- Phase 2 Plan (not yet created)

**Source of Truth:**
- [Project Charter](../forgemind_project_source_of_truth/00_PROJECT_CHARTER.md)
- [Product and MVP Scope](../forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md)
- [System Behavior and Data](../forgemind_project_source_of_truth/02_SYSTEM_BEHAVIOR_AND_DATA.md)
- [Definition of Done](../forgemind_project_source_of_truth/03_DEFINITION_OF_DONE.md)
- [Acceptance Tests](../forgemind_project_source_of_truth/04_ACCEPTANCE_TESTS.md)
- [Deployment and Demo](../forgemind_project_source_of_truth/05_DEPLOYMENT_AND_DEMO.md)
- [AI Agent Execution Rules](../forgemind_project_source_of_truth/06_AI_AGENT_EXECUTION_RULES.md)
- [Delivery Roadmap](../forgemind_project_source_of_truth/07_ROADMAP.md)
- [Decision Log](../forgemind_project_source_of_truth/08_DECISION_LOG.md)
- [Master Task for Hermes](../forgemind_project_source_of_truth/09_MASTER_TASK_FOR_HERMES.md)

**Open Questions:**
- [Open Questions (Phase 2 decisions)](planning/open_questions.md)

---

## Contact

For questions about Phase 2 planning or Phase 1 review:
- Product Owner: [name/contact]
- Engineering Lead: [name/contact]
- Hermes Agent: session `2026-07-17` (Phase 1 implementation + closeout)

---

**Next Milestone:** Phase 2 planning approved, first WP started.
