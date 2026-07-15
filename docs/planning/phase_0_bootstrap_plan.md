# Phase 0 — Bootstrap Plan

## Context

Repository: `/run/media/toha/Virtual Staff/VScode/AIAutomation`
Branch: `main`
HEAD: `506d5b3b74512bf00f2da7a3d2d1023c7d80132c`
Working tree: clean

Source of Truth documents reviewed:
- `forgemind_project_source_of_truth/README.md`
- `forgemind_project_source_of_truth/MANIFEST.md`
- `forgemind_project_source_of_truth/00_PROJECT_CHARTER.md`
- `forgemind_project_source_of_truth/01_PRODUCT_AND_MVP_SCOPE.md`
- `forgemind_project_source_of_truth/02_SYSTEM_BEHAVIOR_AND_DATA.md`
- `forgemind_project_source_of_truth/03_DEFINITION_OF_DONE.md`
- `forgemind_project_source_of_truth/04_ACCEPTANCE_TESTS.md`
- `forgemind_project_source_of_truth/05_DEPLOYMENT_AND_DEMO.md`
- `forgemind_project_source_of_truth/06_AI_AGENT_EXECUTION_RULES.md`
- `forgemind_project_source_of_truth/07_ROADMAP.md`
- `forgemind_project_source_of_truth/08_DECISION_LOG.md`
- `forgemind_project_source_of_truth/09_MASTER_TASK_FOR_HERMES.md`

---

## Phase 0 Status: UNBLOCKED

All blocking decisions approved by Product Owner (2026-07-15):
- DEC-010: Python 3.12 ✓
- DEC-011: ARQ + Redis ✓
- DEC-014: Caddy ✓

Phase 0 implementation may proceed.

---

## Detected Contradictions & Ambiguities

### C-1 — Role Count Mismatch
- `01_PRODUCT_AND_MVP_SCOPE.md` §5 lists FIVE target users: Production Manager, Procurement Specialist, Engineer, AI Administrator, Auditor.
- FR-01 lists only FOUR demo roles (no Engineer).
- Gate D §48 says "щонайменше чотири ролі".
- **Issue:** Is Engineer a distinct RBAC role or a label for a combination of other roles?

### C-2 — Python Version
- `02` says "Python 3.12+". Current environment is 3.14.5.
- **Issue:** Choice of 3.12 vs 3.13 vs 3.14 affects stdlib features and library compatibility. Needs an explicit pin.

### C-3 — Background Job Queue (Unresolved)
- `02` §2 says "ARQ, Dramatiq або Celery — обрати один".
- No decision recorded in Decision Log.

### C-4 — WebSocket vs Polling (Unresolved)
- `02` §2 says "WebSocket або polling — обрати найпростішу".
- No decision recorded.

### C-5 — Workflow Orchestration (Unresolved)
- `02` §2 says "LangGraph або власна explicit state machine".
- No decision recorded.

### C-6 — Reverse Proxy (Unresolved)
- `02`/`05` say "Caddy або Nginx".
- No decision recorded.

### C-7 — State Management (Unresolved)
- `02` §2 says "Zustand або мінімальний state layer".

### C-8 — Chart Library (Unresolved)
- `02` §2 says "ECharts або Recharts".

### C-9 — Component Library (Unspecified)
- `02` §2 says "component library із послідовною design system" but names no library.

### C-10 — Redis (Conditional)
- `02` §2 says "Redis лише за наявності реальної потреби".
- If ARQ/Dramatiq/Celery is chosen, Redis IS required.
- **Dependency:** Decision depends on C-3.

### C-11 — Reranker (Unspecified)
- `02` §2 says "optional reranker". MVP necessity unclear.

### C-12 — Object Storage (Unspecified)
- `02` §2 says "object storage опціонально".
- Synthetic documents could live in DB or filesystem.

### C-13 — Demo Reset Mechanism (Undefined)
- FR-12 says admin can reset, but does not specify:
  - drop database + re-seed?
  - soft-delete + restore from fixture?
  - which role can trigger it?
- AT-015 and `05` §5 mention it but don't resolve mechanics.

### C-14 — Risk Engine ↔ AI Schema Handoff
- `02` §6 shows a JSON schema with risk_id, but risk engine is deterministic code (`02` §1).
- Schema includes "summary", "business_impact", "recommended_actions".
- **Issue:** Are these filled by the engine or by the LLM? The split between engine output and LLM output needs a precise contract.

### C-15 — Correlation ID Format (Undefined)
- FR-07 / AT-012 require correlation IDs, but format is not specified (UUID v4? ULID? sequential?).

### C-16 — Document Permission Model (Undefined)
- `02` §3 lists `document_permissions` as an entity, but the permission semantics are not described (per-user? per-role? per-document-type? combination?).

### C-17 — Public Demo Accounts vs RBAC Roles
- `05` §5 lists demo accounts: manager.demo, procurement.demo, auditor.demo — but no engineer.demo or admin.demo.
- **Issue:** Are these accounts mapped 1:1 to RBAC roles?

### C-18 — Rate Limit Values (Undefined)
- Gate D and `05` §6 mention rate limiting but specify no numbers.

---

## Assumptions (Until Decisions Are Made)

| ID    | Assumption | Rationale |
|-------|------------|-----------|
| A-1   | Python 3.12+ minimum; target 3.12 for max compatibility | SoT says 3.12+ |
| A-2   | Engineer IS a distinct RBAC role (5 roles total) | `01` §5 lists Engineer with distinct behavior |
| A-3   | Background jobs: ARQ + Redis (lightest async-native option) | MVP scope; simpler than Celery |
| A-4   | Real-time: polling (simplest reliable; SSE can upgrade later) | "обрати найпростішу надійну реалізацію" |
| A-5   | Workflow: custom explicit state machine (no LangGraph) | More debuggable, no extra dependency |
| A-6   | Reverse proxy: Caddy (auto-HTTPS, minimal config) | Simpler than Nginx for MVP |
| A-7   | State management: Zustand | Specified in SoT, minimal |
| A-8   | Charts: Recharts | React-native, simpler |
| A-9   | Component library: shadcn/ui + Tailwind CSS | Modern, accessible, themeable |
| A-10  | Redis: YES, required for ARQ queue | Dependency on A-3 |
| A-11  | Reranker: NO for MVP | Keep scope minimal |
| A-12  | Object storage: NO — documents stored as DB text + file chunks | Synthetic data fits in DB |
| A-13  | React Flow: NO — use a vertical step/timeline component | Simpler for MVP |
| A-14  | Demo reset: truncate user-generated data, re-seed synthetic data | Matches AT-015 |
| A-15  | Reset role: AI Administrator only | Matches FR-12 "Адміністратор" |
| A-16  | Demo accounts map 1:1 to roles (add engineer.demo, admin.demo) | Completeness |
| A-17  | Rate limits: 60 req/min per user for API, 10 AI calls/min | Reasonable defaults |
| A-18  | Correlation ID: UUID v4 | Standard, collision-free |
| A-19  | Risk engine outputs deterministic struct; LLM fills summary/impact/actions (two-phase) | Matches `02` §1 architecture principle |
| A-20  | Document permissions: role-based (each role has allowed document access levels) | Matches FR-02 RBAC |

---

## Technology Choices (Within Allowed Stack)

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.12 | Max compatibility; 3.12+ required |
| Backend framework | FastAPI | Specified in SoT |
| ORM | SQLAlchemy 2 | Specified in SoT |
| Migrations | Alembic | Specified in SoT |
| Validation | Pydantic v2 | Specified in SoT |
| Background jobs | ARQ + Redis | Lightest async-native option |
| Real-time | Polling (3-5s) | Simplest; upgrade path to SSE |
| Database | PostgreSQL + pgvector | Specified in SoT |
| Embedding model | OpenAI-compatible | Single adapter contract |
| Vector search | pgvector direct | No extra service |
| Reranker | None (MVP) | Keep scope minimal |
| Workflow engine | Custom state machine | Explicit, debuggable, no magic |
| Frontend framework | React 18 + TypeScript | Specified in SoT |
| Build tool | Vite | Specified in SoT |
| Routing | React Router v6 | Specified in SoT |
| Server state | TanStack Query | Specified in SoT |
| Client state | Zustand | Minimal, specified in SoT |
| Charts | Recharts | React-native, simpler |
| UI components | shadcn/ui + Tailwind | Modern, accessible, themeable |
| Workflow visualization | Step timeline (custom) | No React Flow dependency |
| Reverse proxy | Caddy | Auto-HTTPS, minimal config |
| Containerization | Docker Compose | Specified in SoT |
| CI | GitHub Actions | Specified in SoT |
| Testing (backend) | pytest + httpx | Standard FastAPI testing |
| Testing (frontend) | Vitest + Testing Library | Standard Vite ecosystem |
| Testing (e2e) | Playwright | Headless browser, reliable |
| Linting (backend) | ruff | Fast, replaces flake8+black |
| Linting (frontend) | ESLint + Prettier | Standard |
| Type checking | mypy (backend), TypeScript strict (frontend) | Implicit requirement |

---

## Phase 0 — Bootstrap Implementation Plan

### Branch
`feature/phase-0-repository-bootstrap` (from `main` at `506d5b3`)

### Items

#### MANDATORY (must be in bootstrap commit)

| #  | File | Purpose |
|----|------|---------|
| 1  | `.gitignore` | Python, Node, Docker, env, IDE patterns |
| 2  | `.dockerignore` | Exclude node_modules, .git, __pycache__ |
| 3  | `.env.example` | All env vars with placeholder values, no secrets |
| 4  | `README.md` (root) | Project overview, quick start, architecture link |
| 5  | `Makefile` | Convenience targets: dev, test, seed, reset, deploy |
| 6  | `docker-compose.yml` | Full stack skeleton (backend, frontend, worker, postgres, redis, caddy) |
| 7  | `docker-compose.dev.yml` | Dev overrides (bind mounts, hot reload, debug ports) |
| 8  | `backend/pyproject.toml` | Python deps: FastAPI, SQLAlchemy, Alembic, Pydantic, ARQ, pytest, ruff, mypy |
| 9  | `backend/app/__init__.py` | Package init |
| 10 | `backend/app/main.py` | Minimal FastAPI app with `/health` endpoint |
| 11 | `backend/app/config.py` | pydantic-settings skeleton (all config keys) |
| 12 | `backend/tests/__init__.py` | Test package init |
| 13 | `backend/tests/conftest.py` | Placeholder fixtures |
| 14 | `backend/tests/unit/test_health.py` | Health endpoint test |
| 15 | `frontend/package.json` | React + Vite + TS deps |
| 16 | `frontend/tsconfig.json` | TypeScript strict config |
| 17 | `frontend/vite.config.ts` | Proxy /api → backend:8000 |
| 18 | `frontend/tailwind.config.ts` | Tailwind with shadcn preset |
| 19 | `frontend/postcss.config.js` | PostCSS for Tailwind |
| 20 | `frontend/src/main.tsx` | Minimal React entry point |
| 21 | `frontend/src/App.tsx` | Placeholder component |
| 22 | `frontend/index.html` | Vite HTML entry |
| 23 | `infra/docker/backend.dockerfile` | Backend container build |
| 24 | `infra/docker/frontend.dockerfile` | Frontend container build |
| 25 | `infra/docker/worker.dockerfile` | Worker container build |
| 26 | `infra/caddy/Caddyfile` | Reverse proxy skeleton (frontend, backend, /api proxy) |
| 27 | `.github/workflows/ci-backend.yml` | CI placeholder: install + lint + test |
| 28 | `.github/workflows/ci-frontend.yml` | CI placeholder: install + build |
| 29 | `.github/workflows/ci-e2e.yml` | CI placeholder |
| 30 | `.github/ISSUE_TEMPLATE/task.md` | Task template per `06` §3 format |
| 31 | `.github/ISSUE_TEMPLATE/bug.md` | Bug report template |
| 32 | `scripts/seed.sh` | Wrapper for seed command |
| 33 | `scripts/reset.sh` | Wrapper for reset command |
| 34 | `scripts/run-tests.sh` | Run all test suites |
| 35 | `scripts/check-secrets.sh` | Pre-commit secret detection |
| 36 | `seed/README.md` | Describes golden dataset |
| 37 | `docs/planning/open_questions.md` | Open questions for Product Owner |
| 38 | `docs/planning/proposed_repository_structure.md` | Full repository tree |
| 39 | `docs/planning/requirements_traceability_matrix.md` | Requirement-to-test traceability |
| 40 | `docs/planning/phase_0_bootstrap_plan.md` | This file |

#### MAY BE DEFERRED (not blocking bootstrap)

| #  | File | Reason it can wait |
|----|------|--------------------|
| D-1 | `docs/architecture.md` | Written after Phase 1 skeleton is running |
| D-2 | `docs/deployment-guide.md` | Written during Phase 7 |
| D-3 | `docs/trade-offs.md` | Populated incrementally |
| D-4 | `docs/runbooks/*.md` | Written during Phase 7 |
| D-5 | `release-evidence/.gitkeep` | Can be created in Phase 8 |
| D-6 | `LICENSE` | Low risk; can add anytime |
| D-7 | `seed/fixtures/.gitkeep` | Created when fixtures exist (Phase 2) |
| D-8 | `seed/documents/.gitkeep` | Created when documents exist (Phase 4) |

---

## Verification Commands

```bash
# 1. Validate Docker Compose syntax
docker compose config > /dev/null && echo "PASS: compose valid"

# 2. Check .env.example has no real secrets
grep -rE '(sk-|ghp_|password\s*=\s*"[^$])' .env.example && \
  echo "FAIL: secrets in .env.example" || echo "PASS: no secrets"

# 3. Check no secrets anywhere in committed files
./scripts/check-secrets.sh

# 4. Backend: install + health test
cd backend && python -m venv .venv && \
  source .venv/bin/activate && \
  pip install -e ".[dev]" && \
  pytest tests/unit/test_health.py -v

# 5. Frontend: install + build
cd frontend && npm ci && npm run build

# 6. CI smoke (simulates GitHub Actions)
./scripts/run-tests.sh

# 7. Full stack smoke
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
sleep 5
curl -sf http://localhost:8000/health && echo "PASS: backend"
curl -sf http://localhost:5173 && echo "PASS: frontend"
docker compose down -v

# 8. Verify tree structure
find . -maxdepth 3 -type f | sort | head -60
```

---

## Proposed First Commit Message

```
chore: bootstrap repository structure and CI skeleton

- Create directory tree for backend, frontend, seed, infra, docs
- Add Docker Compose skeleton (all services)
- Add GitHub Actions CI placeholders
- Add .env.example, .gitignore, Makefile
- Add minimal FastAPI /health endpoint
- Add minimal React entry point
- Add issue templates and runbook placeholders
- No application logic — Phase 0 governance only
```

---

## Git Branch Strategy

```
main ──────────────────────────────────────────────►
  │
  ├── feature/phase-0-repository-bootstrap
  │       └── PR → main (squash merge)
  │
  ├── feature/phase-1-running-skeleton
  │       └── PR → main
  │
  ├── feature/phase-2-synthetic-erp-core
  │       └── PR → main
  │
  ├── ... (one feature branch per phase)
  │
  └── feature/phase-8-portfolio-release
          └── PR → main
```

Rules:
- No direct commits to main.
- Each phase = one branch, one PR, one squash merge.
- Commit messages follow conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `chore:`, `ci:`
- Each commit must pass CI before merge.
- Tags: v0.1.0 (phase 1 done), v0.2.0 (phase 2), ..., v1.0.0 (portfolio ready)
