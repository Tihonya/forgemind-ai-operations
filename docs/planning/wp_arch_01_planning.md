# WP-ARCH-01 — Architecture Hygiene and Agent Onboarding (Planning)

**Status:** ACCEPTED — Planning artifact accepted by Product Owner on 2026-08-09. WP-ARCH-01 is CLOSED with no execution required. The sole RECOMMENDED item (agent-onboarding document, Finding 4.5.1) is DEFERRED.
**Date:** 2026-08-09
**Inspection baseline:** `origin/main` @ `4e60de818e5f18c5f5184ab7ffb1d292551de6d8` — PR #68 merge commit
**Product Owner acceptance and closure baseline:** `origin/main` @ `3a2bc26028cac0352af2cdde8107df90f41f015c` (PR #69 merge commit), 2026-08-09.
**Authority:** Product Owner authorized planning-only creation on 2026-08-09.
**Relationship:** Follows WP-STRAT-01 (COMPLETED, MERGED via PR #67, merge commit `77d359c`). Strategic inputs sourced from `docs/planning/wp_strat_01_product_strategy.md` §17 and `docs/planning/wp_strat_01_reconnaissance.md` §13.3.

---

## 1. Purpose, Objectives, and Non-goals

### 1.1 Purpose

This document is a planning artifact. It records evidence from read-only inspection of the ForgeMind repository at `origin/main` @ `4e60de8` and proposes possible future scopes for Product Owner consideration.

This document:

- records evidence and proposes possible future scopes;
- does not itself approve any proposed scope;
- does not authorize WP-ARCH-01 execution;
- does not authorize WP-REC-03C;
- does not authorize SP-0B;
- does not authorize another repository or any Runtime movement.

### 1.2 Objectives

- Assess current architecture hygiene across backend, frontend, and infrastructure.
- Assess whether agent onboarding documentation or boundaries need improvement.
- Identify actual blockers, recommended improvements, and areas requiring no action.
- Determine whether any bounded WP-ARCH-01 execution work should be proposed.
- Provide evidence for a later Product Owner decision.

### 1.3 Non-goals

- No implementation, no code changes, no file movement, no restructuring.
- No configuration or CI changes.
- No acceptance-test execution (AT-006/AT-007 verification is a separate bounded package per DEC-035).
- No SP-0B execution.
- No WP-REC-03C execution or redesign.
- No Source of Truth, Decision Log, or existing planning document changes.
- No copying, moving, removing, genericizing, or migrating Runtime artifacts.

---

## 2. Evidence Method

For every finding, this document records:

- classification;
- affected area;
- exact repository evidence;
- impact;
- whether it blocks consideration of WP-REC-03C;
- smallest possible remediation scope, if remediation is warranted.

### 2.1 Classifications

| Classification | Meaning |
|----------------|---------|
| `OK` | No action needed. The current state is sufficient for the affected later work. |
| `RECOMMENDED` | Useful improvement but not a prerequisite. May be deferred without blocking. |
| `REQUIRED` | Evidence shows it must be resolved before the affected later work can safely begin. |
| `UNRESOLVED` | Insufficient evidence or Product Owner decision required. |

An item is classified `REQUIRED` only when concrete evidence shows that leaving it unresolved would cause incorrect behavior, a broken contract, or a safety risk in later work. Desirability alone does not justify `REQUIRED`.

---

## 3. Architecture-Hygiene Assessment

### 3.1 Backend module layout and boundaries

**Inspection scope:** `backend/app/` at `origin/main` @ `4e60de8`.

The backend follows a conventional layered FastAPI structure:

| Layer | Path | Responsibility |
|-------|------|----------------|
| API routers | `backend/app/api/` | HTTP endpoints, request/response handling |
| API middleware | `backend/app/api/middleware/` | Correlation ID middleware |
| Services | `backend/app/services/` | Business logic (risk engine, ingestion, auth, inventory, BOM, chunking, embeddings, diagnostics, dataset integrity, dependency health) |
| AI subsystem | `backend/app/ai/` | Provider (chat), RAG (retriever, citations), Workflow (state machine, engine) |
| Models | `backend/app/models/` | SQLAlchemy ORM models (14 entity modules + enums) |
| Schemas | `backend/app/schemas/` | Pydantic request/response schemas (17 schema modules) |
| Core | `backend/app/core/` | Cross-cutting: correlation, logging, security, context, build info, dataset metadata |
| Jobs | `backend/app/jobs/` | ARQ background job functions (diagnostics, ingestion) |
| Seed | `backend/app/seed/generator/` | Synthetic dataset generation |
| Configuration | `backend/app/config.py` | Pydantic Settings |
| Database | `backend/app/database.py` | Async session factory |
| Dependencies | `backend/app/dependencies.py` | Auth/RBAC dependency injection |
| Entry point | `backend/app/main.py` | FastAPI app factory, router registration, lifespan |
| Worker | `backend/app/worker.py` | ARQ worker configuration |

**Finding 3.1.1 — Backend layer separation**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | Backend services → API layer |
| Evidence | Services import from `app.schemas.*` and `app.models.*` but not from `app.api.*`. API routers import from `app.services.*`, `app.schemas.*`, `app.dependencies.*`, and `app.core.*`. No service module imports an API router. Verified by inspecting import sections of `risk_engine.py`, `ingestion.py`, `auth_service.py`, `risks.py`, `retrieval.py`. |
| Impact | Clean layer separation. Services are testable without HTTP context. |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

**Finding 3.1.2 — AI subsystem package structure**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `backend/app/ai/` |
| Evidence | Three sub-packages: `provider/` (chat_provider, openai_chat_provider, fake_chat_provider, factory, exceptions), `rag/` (retriever, citations), `workflow/` (state_machine, engine). Each sub-package has a clear single responsibility. The workflow engine imports from `ai.provider.chat_provider` (ChatProvider interface) but not from `ai.rag.*`. The retriever imports only `sqlalchemy` and standard library — no dependency on `ai.provider` or `ai.workflow`. |
| Impact | Clean internal boundaries. The AI subsystem is ready for WP-REC-03C (structured output validation) to be added without restructuring. |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

**Finding 3.1.3 — Model registry completeness**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `backend/app/models/__init__.py` |
| Evidence | The `__init__.py` re-exports all ORM models (Component, BomItem, ComponentAlternative, Document, DocumentVersion, DocumentPermission, KnowledgeChunk, Product, ProductVersion, ProductionPlan, ProductionOrder, ProductionOrderRequirement, Supplier, PurchaseOrder, PurchaseOrderLine, Warehouse, InventoryBalance, InventoryReservation, DiagnosticJob, Role, User, UserRole, WorkflowRun, WorkflowStep, Recommendation) and all enums. Alembic autogenerate discovery depends on this registration. |
| Impact | All models are discoverable by Alembic. No orphaned models found. |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

### 3.2 Dependency direction and import patterns

**Finding 3.2.1 — No circular dependencies detected**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | Backend import graph |
| Evidence | Dependency direction is unidirectional: `api → services → models/schemas`, `api → dependencies → services`, `ai.workflow → ai.provider`, `ai.rag → models`. No service imports from `api`. No model imports from `services` or `api`. The API calls domain services (including `ai.rag.retriever.RetrievalService`) through the expected FastAPI dependency-injection pattern. |
| Impact | No circular import risk. Module loading order is deterministic. |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

**Finding 3.2.2 — No LangGraph dependency**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | Backend dependencies |
| Evidence | `git grep -l 'langgraph' origin/main -- backend/` returns one match: `backend/tests/unit/test_workflow_migration_file.py`, which references the migration filename string, not a LangGraph import. `backend/pyproject.toml` does not list `langgraph` as a dependency. DEC-013 (Accepted): explicit application-owned state machine; LangGraph not introduced. |
| Impact | Consistent with DEC-013. No unwanted framework dependency. |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

**Finding 3.2.3 — No Zustand dependency in frontend**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | Frontend state management |
| Evidence | `git grep -l 'zustand' origin/main -- frontend/` returns no matches. DEC-015 (Proposed): Zustand remains in `package.json` from Phase 0 but is not imported or used. The frontend uses React hooks (`useState`, `useCallback`, `useMemo`) and TanStack Query for data fetching. |
| Impact | Consistent with DEC-015 (Proposed). No unused runtime dependency in application code. |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

### 3.3 Frontend layout, state-management, and data-fetching boundaries

**Inspection scope:** `frontend/src/` at `origin/main` @ `4e60de8`.

Frontend structure:

| Layer | Path | Responsibility |
|-------|------|----------------|
| Routes | `frontend/src/routes/` | Page components (dashboard, login, supply-risk, supply-risk-detail, not-found, protected, root) |
| Components | `frontend/src/components/` | Reusable UI (common, dashboard, layout, supply-risk, ui) |
| Contexts | `frontend/src/contexts/` | Auth context |
| Hooks | `frontend/src/hooks/` | Data hooks (useActivePlan, useDatasetStatus, useHealth, useRiskDetail, useRiskSummary, useRisks) |
| Lib | `frontend/src/lib/` | API clients (api.ts, auth-api, dataset-api, health-api, production-plans-api, risk-detail-api, risks-api, format, storage, utils) |
| Test | `frontend/src/test/` | Test setup |

**Finding 3.3.1 — Frontend API layer organization**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `frontend/src/lib/` |
| Evidence | Central axios instance (`api.ts`) with request interceptor for Bearer token attachment. Domain-specific API modules (`auth-api.ts`, `risks-api.ts`, `risk-detail-api.ts`, `health-api.ts`, `dataset-api.ts`, `production-plans-api.ts`) wrap domain endpoints. Hooks consume API modules. Auth context (`auth.context.tsx`) uses `auth-api.ts` and `storage.ts`. |
| Impact | Clean separation between API access, data hooks, and UI components. Ready for WP-REC-03G (frontend start/retry UI) to add workflow-related hooks and API modules without restructuring. |
| Blocks WP-REC-03C? | No (WP-REC-03C is backend-only). |
| Blocks WP-REC-03G? | No. |
| Remediation | None needed. |

**Finding 3.3.2 — Frontend component organization**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `frontend/src/components/` |
| Evidence | Components are organized by domain: `dashboard/` (5 widgets), `layout/` (AuthenticatedLayout, Header, Sidebar, navigation), `supply-risk/` (10 components including RiskList, RiskSummary, EvidencePanel, etc.), `common/` (DataEmptyState, DataErrorState), `ui/` (shadcn/ui primitives: alert, button, card, separator, skeleton, table, tooltip). Each component has a colocated test file. |
| Impact | Well-structured for Phase 5 frontend work. shadcn/ui primitives are available for workflow UI. |
| Blocks WP-REC-03G? | No. |
| Remediation | None needed. |

### 3.4 Infrastructure, Docker, and CI organization

**Inspection scope:** `infra/`, `docker-compose.yml`, `.github/workflows/` at `origin/main` @ `4e60de8`.

**Finding 3.4.1 — Docker Compose structure**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `docker-compose.yml` |
| Evidence | Services: postgres (pgvector/pgvector:pg16), redis (redis:7-alpine), backend, frontend, worker, caddy. Health checks for postgres and redis. Volume persistence for postgres_data and redis_data. Network isolation (backend network). Dev overlay (`docker-compose.dev.yml`) for development ports. |
| Impact | Complete application stack. Ready for Phase 5 (worker already configured) and Phase 7 (Caddy HTTPS). |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

**Finding 3.4.2 — Dockerfile organization**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `infra/docker/` |
| Evidence | Three Dockerfiles: `backend.dockerfile`, `frontend.dockerfile`, `worker.dockerfile`. Plus `nginx.conf` for frontend serving. Each service has a dedicated image. |
| Impact | Clean separation. Worker image is ready for WP-REC-03F (ARQ worker for workflow execution). |
| Blocks WP-REC-03F? | No. |
| Remediation | None needed. |

**Finding 3.4.3 — CI workflow organization**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `.github/workflows/` |
| Evidence | Three CI workflows: `ci-backend.yml` (pytest, ruff, mypy), `ci-frontend.yml` (vitest, eslint, tsc), `ci-e2e.yml` (Playwright golden scenario). Post-merge CI on main confirmed SUCCESS for all three after WP-REC-03B merge (per `docs/ACTIVE_WORK.md`). |
| Impact | CI covers backend, frontend, and E2E. Ready for Phase 5 work. |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

### 3.5 Alembic migration chain

**Finding 3.5.1 — Migration chain integrity**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `backend/alembic/versions/` |
| Evidence | Seven migration files in linear chain: `129270172ebc` (diagnostic_jobs) → `3f5e7a9b21cd` (phase 2 business schema) → `b4c5a6b7c8d9` (auth tables) → `a1b2c3d4e5f6` (document schema) → `c7d8e9f0a1b2` (knowledge chunks) → `625c9f549f2b` (document version content) → `f1a2b3c4d5e6` (workflow tables, WP-REC-03B head). Each revision correctly references its predecessor via `Revises:`. |
| Impact | Migration chain is linear and complete. WP-REC-03C–03G can add migrations without chain conflicts. |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

### 3.6 Makefile and test workflow

**Finding 3.6.1 — Makefile test targets**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `Makefile` |
| Evidence | `make test` runs backend pytest (`.venv/bin/pytest -v`) then frontend vitest. `make lint` runs ruff + mypy + eslint. `make seed` runs the seed generator via docker compose exec. `make reset` is a placeholder (reset_service.py not yet implemented — deferred to Phase 7). |
| Impact | Test and lint workflows are established and documented. |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

### 3.7 Test tree organization

**Finding 3.7.1 — Backend test organization**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `backend/tests/` |
| Evidence | 78 Python test files. Organized into `unit/` (35+ files), `integration/` (25+ files), `seed/` (3 files). Fixtures under `tests/fixtures/evaluation/` (rag_documents.json, rag_queries.json). Shared conftest at `tests/conftest.py` and `tests/integration/conftest.py`. Database URL helper at `tests/_db_url.py`. |
| Impact | Well-organized test tree. Unit and integration tests are separated. WP-REC-03C can add `test_schema_validator.py` and related tests without restructuring. |
| Blocks WP-REC-03C? | No. |
| Remediation | None needed. |

**Finding 3.7.2 — Frontend test organization**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `frontend/src/` |
| Evidence | 29 test files (`.test.*`). Tests are colocated with components (e.g., `RiskList.tsx` + `__tests__/RiskList.test.tsx`). Hooks have dedicated test files (`useRiskDetail.test.tsx`). API modules have test files (`api.test.ts`, `health-api.test.ts`, etc.). E2E test: `frontend/tests/` (Playwright golden scenario). |
| Impact | Well-organized. WP-REC-03G can add workflow UI tests following existing colocated patterns. |
| Blocks WP-REC-03G? | No. |
| Remediation | None needed. |

### 3.8 Potential cross-layer leakage check

**Finding 3.8.1 — Retrieval API calls RetrievalService in ai.rag**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `backend/app/api/retrieval.py` → `backend/app/ai/rag/retriever.py` |
| Evidence | `api/retrieval.py` imports `RetrievalService` from `ai.rag.retriever`. `RetrievalService` already exists as a service abstraction — the API calls a named service class, not a low-level standalone retrieval function. Its placement under `app.ai.rag` is consistent with the current AI subsystem boundary: the RAG retrieval logic, including role-filtered SQL and citation construction, belongs to the `ai.rag` domain package. No concrete duplication, coupling defect, circular dependency, or unsafe dependency direction was demonstrated. The dependency direction (`api → ai.rag.retriever`) does not cross the service/model boundary in a way that violates the layered architecture — the API layer calls a domain service, which is the expected FastAPI pattern. |
| Impact | The existing service abstraction is sufficient. Adding another `services/retrieval_service.py` wrapper would currently add indirection around an existing service without an evidenced requirement. |
| Blocks WP-REC-03C? | No. |
| Blocks WP-REC-05? | No. |
| Remediation | None required. WP-REC-05 may reassess service placement only if its concrete integration design demonstrates a shared orchestration requirement. |

### 3.9 Environment variable handling

**Finding 3.9.1 — .env.example uses ${VAR} interpolation**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `.env.example` |
| Evidence | `.env.example` contains `${POSTGRES_USER}`, `${POSTGRES_PASSWORD}`, etc. in `DATABASE_URL` and `REDIS_URL`. Pydantic Settings loads the configured `.env` through `python-dotenv`, which supports `${VAR}` interpolation. Docker Compose also resolves `${VAR}` interpolation natively. Bash expands `${VAR}` when sourcing assignments after the referenced variable has been assigned; sourcing and exporting are separate concerns (variables assigned by a sourced file are available in the current shell but are not necessarily exported to child processes unless export semantics are enabled). The current `.env.example` uses a comma-separated `CORS_ORIGINS` value, not a JSON-valued variable. |
| Impact | The existing `${VAR}` usage is compatible with the project's Pydantic/python-dotenv loading path and with Docker Compose interpolation. No configuration defect or setup instruction error was demonstrated. |
| Blocks WP-REC-03C? | No. |
| Remediation | None required for the inspected configuration path. |

### 3.10 Summary of architecture-hygiene findings

| # | Finding | Classification | Blocks WP-REC-03C? |
|---|---------|----------------|---------------------|
| 3.1.1 | Backend layer separation | `OK` | No |
| 3.1.2 | AI subsystem package structure | `OK` | No |
| 3.1.3 | Model registry completeness | `OK` | No |
| 3.2.1 | No circular dependencies | `OK` | No |
| 3.2.2 | No LangGraph dependency | `OK` | No |
| 3.2.3 | No Zustand dependency in frontend | `OK` | No |
| 3.3.1 | Frontend API layer organization | `OK` | No |
| 3.3.2 | Frontend component organization | `OK` | No |
| 3.4.1 | Docker Compose structure | `OK` | No |
| 3.4.2 | Dockerfile organization | `OK` | No |
| 3.4.3 | CI workflow organization | `OK` | No |
| 3.5.1 | Migration chain integrity | `OK` | No |
| 3.6.1 | Makefile test targets | `OK` | No |
| 3.7.1 | Backend test organization | `OK` | No |
| 3.7.2 | Frontend test organization | `OK` | No |
| 3.8.1 | Retrieval API calls RetrievalService in ai.rag | `OK` | No |
| 3.9.1 | .env.example uses ${VAR} interpolation | `OK` | No |

**Architecture-hygiene summary:**

- `OK`: 17 findings
- `RECOMMENDED`: 0 findings
- `REQUIRED`: 0 findings
- `UNRESOLVED`: 0 findings

No architecture-hygiene item is classified `REQUIRED`. No item blocks WP-REC-03C.

---

## 4. Agent-Onboarding Assessment

### 4.1 Current agent-loop integration surface

**Inspection scope:** `scripts/agent-loop/` and `.agent-loop/` at `origin/main` @ `4e60de8`.

**Agent-loop implementation:**

| Component | Path | Responsibility |
|-----------|------|----------------|
| Orchestrator | `scripts/agent-loop/run-story.sh` | Implementation → Verification → Review → Repair → Reverify → Report |
| Verifier | `scripts/agent-loop/verify-story.sh` | Scope, JSON/YAML syntax, targeted tests, lint, secrets, git diff check |
| Reporter | `scripts/agent-loop/report-story.sh` | Final report aggregation |
| Configuration | `scripts/agent-loop/config.sh` | Environment loading, tool detection, config validation |
| Python lib | `scripts/agent-loop/lib/` | 19 Python/bash modules (harness, config_loader, scope, failure_context, manifest_loader, review/repair adapters and contracts, mock actors, passport, etc.) |
| Tests | `scripts/agent-loop/tests/` | 23 test files (harness scenarios A-X, unit tests for all modules) |
| Templates | `scripts/agent-loop/templates/` | Story PRD manifest template |
| README | `scripts/agent-loop/README.md` | Comprehensive documentation (~400 lines) |

**Agent-loop configuration (`.agent-loop/`):**

| File | Purpose |
|------|---------|
| `project.json` | Project structure, runtime policy, secret handling, path policy |
| `gates.json` | Gate definitions (scope, json_syntax, yaml_syntax, targeted_tests, lint, secrets, git_diff_check) |
| `failure-context/SCHEMA.md` | Failure context schema v1.0 |
| `manifests/SCHEMA.md` | Manifest schema |
| `repair-adapter/SCHEMA.md` | Repair adapter schema |
| `repair/SCHEMA.md` | Repair contract schema |
| `review-adapter/SCHEMA.md` | Review adapter schema |
| `review/SCHEMA.md` | Review contract schema |

### 4.2 Product-owned versus Runtime-owned boundary clarity

**Finding 4.2.1 — Product/Runtime boundary is clearly documented**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `docs/planning/sp0a_separation_decision.md` §4 |
| Evidence | SP-0A (APPROVED, Option C) explicitly classifies: Product-owned artifacts (`backend/`, `frontend/`, `infra/`, `forgemind_project_source_of_truth/`, `HERMES.md`, `Makefile`, compose files, `.env.example`, `README.md`, CI workflows, `.agent-loop/project.json`, `.agent-loop/gates.json`, `scripts/agent-loop/templates/story-prd.json`, all `docs/planning/`). Runtime-owned artifacts (`scripts/agent-loop/lib/*.py`, `lib/*.sh`, `*.sh` entry points, `tests/`, `README.md`, `.agent-loop/*/SCHEMA.md`). Protected artifacts (`project.json`, `gates.json`, `HERMES.md`, Source of Truth). |
| Impact | The ownership boundary is clear. A new agent session can determine what it may and may not modify. |
| Blocks WP-ARCH-01 execution? | No. |
| Remediation | None needed. |

### 4.3 Repository navigation and Source of Truth discovery

**Finding 4.3.1 — HERMES.md provides clear governance entry point**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `HERMES.md` |
| Evidence | HERMES.md defines: normative sources (priority-ordered 1–9), current product boundary (one vertical scenario), core architecture rules (Python/SQL owns arithmetic, LLM explains), delivery discipline (state branch/HEAD/status before modifying), git rules (one feature branch per phase, conventional commits, no push to main), decision handling (inspect SoT → identify conflict → present options → recommend → stop), execution safety (minimal intervention, dangerous commands, secrets, shell construction, Docker/test environments, filesystem rules, env var handling, validation discipline, failure handling, PO stop conditions). |
| Impact | A new agent session that reads HERMES.md has clear guidance on what it may do, what it must not do, and how to handle ambiguity. |
| Blocks WP-ARCH-01 execution? | No. |
| Remediation | None needed. |

**Finding 4.3.2 — Source of Truth documents are discoverable**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `forgemind_project_source_of_truth/` |
| Evidence | 12 files (00_PROJECT_CHARTER through 09_MASTER_TASK_FOR_HERMES, MANIFEST.md, README.md). HERMES.md references them by priority. `docs/next_steps.md` links to each. The Decision Log (08) records all accepted decisions with DEC-XXX identifiers. |
| Impact | Source of Truth is navigable. Decision history is traceable. |
| Blocks WP-ARCH-01 execution? | No. |
| Remediation | None needed. |

### 4.4 Branch, test, validation, and prohibited-action guidance

**Finding 4.4.1 — Branch conventions are documented**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `HERMES.md` §"Git rules", `docs/next_steps.md` §"Delivery Sequence" |
| Evidence | One feature branch per approved phase. Conventional commit messages. No push to main. No force-push. No merge of own work. Branch naming: `feature/phase-N-*`, `docs/*`, `fix/*`. Recent examples: `docs/wp-strat-01-product-strategy`, `docs/post-merge-status-sync-wp-strat-01`, `docs/wp-arch-01-planning`. |
| Impact | Branch conventions are clear and consistently followed. |
| Blocks WP-ARCH-01 execution? | No. |
| Remediation | None needed. |

**Finding 4.4.2 — Test and validation workflow is documented**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `Makefile`, `scripts/agent-loop/README.md`, `.github/workflows/` |
| Evidence | `make test` runs backend pytest + frontend vitest. `make lint` runs ruff + mypy + eslint. CI workflows: `ci-backend.yml`, `ci-frontend.yml`, `ci-e2e.yml`. The agent-loop README documents the verification gate system (scope, syntax, tests, lint, secrets, diff-check). |
| Impact | A new agent session knows how to verify its work. |
| Blocks WP-ARCH-01 execution? | No. |
| Remediation | None needed. |

**Finding 4.4.3 — Prohibited actions are clearly documented**

| Field | Value |
|-------|-------|
| Classification | `OK` |
| Affected area | `HERMES.md` §"Execution Safety and Environment Discipline", `docs/next_steps.md` §"What Must NOT Be Started Automatically" |
| Evidence | HERMES.md lists: dangerous commands requiring approval (docker compose down -v, git reset --hard, branch deletion, etc.), secrets handling rules, shell command construction rules, Docker/test environment rules, filesystem rules, env var handling rules, validation discipline, failure handling, PO stop conditions. `docs/next_steps.md` lists what must not be started without authorization. `06_AI_AGENT_EXECUTION_RULES.md` lists prohibited AI behavior. |
| Impact | Prohibited actions are comprehensive and consistently enforced. |
| Blocks WP-ARCH-01 execution? | No. |
| Remediation | None needed. |

### 4.5 Agent onboarding documentation gap assessment

**Finding 4.5.1 — No dedicated agent-onboarding document exists**

| Field | Value |
|-------|-------|
| Classification | `RECOMMENDED` |
| Affected area | Repository-wide |
| Evidence | No file named `AGENT_ONBOARDING.md`, `docs/agent_onboarding.md`, or similar exists. Onboarding information is distributed across `HERMES.md` (governance), `docs/next_steps.md` (current status), `README.md` (product overview), `scripts/agent-loop/README.md` (agent-loop infrastructure), and `forgemind_project_source_of_truth/06_AI_AGENT_EXECUTION_RULES.md` (execution rules). A new agent session must read multiple documents to assemble a complete picture. |
| Impact | The information exists and is accessible, but there is no single entry point that consolidates: "read these files in this order, here is the current branch/phase, here is what you may and may not do, here is how to verify." Whether this constitutes a gap depends on the Product Owner's assessment. |
| Blocks WP-REC-03C? | No. |
| Blocks WP-ARCH-01 execution? | No. |
| Remediation (if pursued) | If the Product Owner decides a dedicated onboarding document is justified: create `docs/agent_onboarding.md` as a single-page entry point that references (not duplicates) the existing governance documents. Proposed scope: document reading order, current phase and branch, verification commands, prohibited actions summary, and pointers to canonical sources. This is a RECOMMENDED improvement, not a prerequisite. |

### 4.6 Summary of agent-onboarding findings

| # | Finding | Classification |
|---|---------|----------------|
| 4.2.1 | Product/Runtime boundary documented | `OK` |
| 4.3.1 | HERMES.md governance entry point | `OK` |
| 4.3.2 | Source of Truth discoverable | `OK` |
| 4.4.1 | Branch conventions documented | `OK` |
| 4.4.2 | Test/validation workflow documented | `OK` |
| 4.4.3 | Prohibited actions documented | `OK` |
| 4.5.1 | No dedicated agent-onboarding document | `RECOMMENDED` |

**Agent-onboarding summary:**

- `OK`: 6 findings
- `RECOMMENDED`: 1 finding
- `REQUIRED`: 0 findings
- `UNRESOLVED`: 0 findings

No agent-onboarding item is classified `REQUIRED`.

---

## 5. SP-0B Relationship

### 5.1 Accepted SP-0A decision (preserved)

SP-0A (APPROVED, Option C, 2026-08-08) established:

- A new Runtime repository (`forgemind-agent-runtime`) will be created — name approved, creation NOT AUTHORIZED.
- Runtime implementation and schemas will be **copied** (not moved) into the new repository.
- The existing ForgeMind copy will be retained through the parity gate (SP-3) and integration exercise (SP-4).
- The ForgeMind copy will be removed only at the explicit removal gate (SP-5).
- SP-0B (migration manifest) is a separate track: READY but NOT AUTHORIZED.

### 5.2 SP-0B status

| Field | Value |
|-------|-------|
| Classification | `OK` |
| SP-0B status | READY but NOT AUTHORIZED |
| Relationship to WP-ARCH-01 | Separate track. WP-ARCH-01 must not absorb SP-0B execution. |
| Evidence | `docs/planning/sp0a_separation_decision.md` §6, §10. `docs/next_steps.md` §"Delivery Sequence": "SP-0B (Runtime migration manifest): READY but NOT AUTHORIZED." `docs/ACTIVE_WORK.md` Lifecycle State: "SP-0B (Runtime migration manifest): READY but NOT AUTHORIZED." |

### 5.3 WP-ARCH-01 boundary regarding SP-0B

WP-ARCH-01 planning may inspect boundary clarity and identify ForgeMind-side documentation or architecture concerns relevant to future coordination. This planning artifact confirms:

- The Product/Runtime ownership boundary (SP-0A §4) is clear and unambiguous.
- The agent-loop code (`scripts/agent-loop/`) has zero runtime coupling with the ForgeMind Product (`backend/`, `frontend/`, `infra/`) — confirmed by SP-0A assessment evidence and consistent with the codebase inspection in §3.
- No ForgeMind-side preparation is needed before SP-0B can be authorized. SP-0B is READY.

WP-ARCH-01 must not propose copying, moving, removing, genericizing, or migrating Runtime artifacts under this authorization. No contradiction with the SP-0A boundary was found.

---

## 6. Relationship to WP-REC-03C

WP-REC-03C remains `NOT AUTHORIZED`.

WP-ARCH-01 planning has identified the following regarding the later reassessment of WP-REC-03C:

- No architecture-hygiene finding is classified `REQUIRED`. No finding blocks WP-REC-03C.
- The AI subsystem (`backend/app/ai/`) has clean internal boundaries ready for WP-REC-03C (structured output validation) to be added as a new module without restructuring.
- The workflow engine (`backend/app/ai/workflow/engine.py`) explicitly documents that structured-output validation is deferred to WP-REC-03C and the `AWAITING_VALIDATION → COMPLETED` transition is intentionally not implemented in 03B.
- The test tree is organized to accept new WP-REC-03C test files without restructuring.

Absence of `REQUIRED` findings does not authorize WP-REC-03C. Completion or merge of the WP-ARCH-01 planning artifact does not authorize WP-REC-03C. Any WP-REC-03C planning or execution requires a separate Product Owner decision after WP-ARCH-01 is reviewed.

WP-REC-03C may be reassessed for separate Product Owner authorization after WP-ARCH-01 is completed and accepted.

---

## 7. Resolved Product Owner Decisions

The following decisions were recorded as unresolved at planning-review time. The Product Owner has since resolved all four on 2026-08-09 (see DEC-041 in `forgemind_project_source_of_truth/08_DECISION_LOG.md`). Accepted decisions from SP-0A, WP-STRAT-01, and the Decision Log are not reopened.

### 7.1 Whether WP-ARCH-01 requires execution work or can close after planning

**RESOLVED (2026-08-09):** The Product Owner chose option (a) — close WP-ARCH-01 after planning. No execution work is required. The architecture-hygiene assessment found zero `REQUIRED` items and zero `UNRESOLVED` items. All architecture-hygiene findings are `OK` (17). One `RECOMMENDED` item exists in agent onboarding (Finding 4.5.1).

### 7.2 Whether the remaining RECOMMENDED item should be implemented, deferred, or rejected

**RESOLVED (2026-08-09):** The Product Owner deferred the remaining `RECOMMENDED` item (Finding 4.5.1 — No dedicated agent-onboarding document). It is not authorized, not implemented, and not created. It may be revisited in a future phase if justified.

### 7.3 Whether a dedicated agent-onboarding document is justified

**RESOLVED (2026-08-09):** Deferred. The Product Owner determined that the current distributed documentation is sufficient for now. A dedicated `docs/agent_onboarding.md` entry point is not authorized or created. This decision may be revisited in a future phase.

### 7.4 Whether WP-REC-03C is ready for a separate reassessment after WP-ARCH-01

**RESOLVED (2026-08-09):** WP-REC-03C may be reassessed for separate Product Owner authorization after a separate Product Owner decision. This closure does not start that reassessment. No conclusion is made about the readiness of WP-REC-03D through 03G or later phases. Reassessment does not authorize implementation. WP-REC-03C remains `NOT AUTHORIZED`.

---

## 8. Proposed Future Decomposition

Based on the evidence, this document recommends option 1:

### 8.1 Recommendation: No WP-ARCH-01 implementation required

**ACCEPTED — Product Owner accepted 2026-08-09.**

No REQUIRED architecture-hygiene finding blocks a separate Product Owner reassessment of WP-REC-03C. No conclusion is made about the readiness of WP-REC-03D through 03G or later phases. Acceptance of WP-ARCH-01 does not replace package-specific planning, evidence, or authorization. WP-ARCH-01 closes after planning. No execution package is needed.

One RECOMMENDED item remains (Finding 4.5.1 — agent-onboarding document). It has been deferred by the Product Owner. It is not authorized, not implemented, and not created. It may be revisited in a future phase if justified.

### 8.2 Alternative: Bounded execution for the remaining RECOMMENDED item

**DEFERRED — Product Owner deferred the agent-onboarding document on 2026-08-09. Not authorized. May be revisited in a future phase if justified.**

If the Product Owner decides that the remaining `RECOMMENDED` item should be implemented, the following bounded scope is proposed. No official WP identifier is assigned — identifiers and sequence positions require a later Product Owner decision.

#### Proposed scope A — Agent onboarding document

**DEFERRED — not authorized, not created.**

| Field | Value |
|-------|-------|
| Problem | Finding 4.5.1: No single-page onboarding entry point for new agent sessions. |
| Evidence | Onboarding information is distributed across HERMES.md, docs/next_steps.md, README.md, scripts/agent-loop/README.md, and 06_AI_AGENT_EXECUTION_RULES.md. |
| Objective | Create `docs/agent_onboarding.md` as a single-page entry point that references (not duplicates) existing governance documents. |
| Proposed file boundary | `docs/agent_onboarding.md` (new file only) |
| Dependencies | None. |
| Acceptance criteria | Document exists; references all canonical governance sources; does not duplicate content; does not authorize any work package; states current phase and authorization state. |
| Non-goals | No code changes. No Source of Truth changes. No Decision Log changes. No authorization of future work. |
| Risks | Low — documentation-only. Risk of content drift if not maintained alongside status updates. |
| Authorization required | Separate Product Owner authorization. |

---

## 9. Planning-Artifact Acceptance Criteria (Planning-Time Record)

The table below records the acceptance state of this planning artifact when PR #69 was reviewed. Its PASS results are historical planning evidence. The subsequent Product Owner resolutions are recorded in §§7–8 above and in DEC-041 (`forgemind_project_source_of_truth/08_DECISION_LOG.md`).

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Backend, frontend, infrastructure, and agent-onboarding areas assessed | PASS |
| 2 | Findings contain evidence and classification | PASS |
| 3 | Verified findings separated from hypotheses and preferences | PASS |
| 4 | Accepted decisions not reopened | PASS |
| 5 | SP-0B remains separate, NOT AUTHORIZED track | PASS |
| 6 | WP-REC-03C remains NOT AUTHORIZED | PASS |
| 7 | No automatic transition to WP-REC-03C implied | PASS |
| 8 | Unresolved Product Owner decisions listed | PASS |
| 9 | Proposed future scopes bounded and explicitly NOT AUTHORIZED | PASS |
| 10 | No unofficial WP identifiers invented | PASS |
| 11 | Only `docs/planning/wp_arch_01_planning.md` created | PASS |
| 12 | AT-006 and AT-007 not claimed as PASS | PASS |
| 13 | Phase 4 remains PARTIALLY COMPLETE | PASS |

---

## 10. Explicit Non-Authorization Boundary (Planning-Time Record)

This planning artifact does not authorize:

- WP-ARCH-01 execution;
- WP-REC-03C, WP-REC-03D, WP-REC-03E, WP-REC-03F, WP-REC-03G, or WP-REC-05;
- SP-0B execution;
- creation of `forgemind-agent-runtime`;
- agent automation activation;
- any code, test, infrastructure, CI, or configuration change;
- any Source of Truth or Decision Log change;
- any proposed future scope described in §8.

At planning-review time, every proposed scope in §8 was labeled `PROPOSED — NOT AUTHORIZED`. The Product Owner subsequently accepted §8.1 as a no-execution closure outcome and deferred §8.2 without authorizing its implementation. WP-REC-03C, WP-REC-03D through 03G, WP-REC-05, SP-0B, Runtime-repository creation, agent automation, and every other execution package remain separately NOT AUTHORIZED.

---

## END OF DOCUMENT
