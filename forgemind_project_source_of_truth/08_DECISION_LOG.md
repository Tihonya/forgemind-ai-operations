# 08. Decision Log

Цей файл є журналом рішень Product Owner. Нові записи додаються внизу.

---

## DEC-001 — Орієнтація проєкту

**Status:** Accepted  
**Decision:** Проєкт орієнтується не на копію конкретної компанії, а на ширший клас AI Solutions Engineer / internal AI automation roles.  
**Reason:** Це робить портфоліо придатним для кількох роботодавців, зберігаючи релевантність engineering/defence-tech середовищу.

## DEC-002 — Один вертикальний MVP

**Status:** Accepted  
**Decision:** Перший реліз реалізує Supply Risk Intelligence, а не повну AI Operations Platform.  
**Reason:** Один завершений end-to-end сценарій сильніший за багато напівготових модулів.

## DEC-003 — Synthetic data only

**Status:** Accepted  
**Decision:** Усі дані й документи вигадані та генеруються в репозиторії.  
**Reason:** Безпека, публічний deployment, відтворюваність.

## DEC-004 — Deterministic business logic

**Status:** Accepted  
**Decision:** Кількісні ризики обчислюються Python/SQL. LLM пояснює й працює з неструктурованими джерелами.  
**Reason:** Надійність, тестованість, демонстрація зрілої AI architecture.

## DEC-005 — Human-in-the-loop

**Status:** Accepted  
**Decision:** AI створює лише draft action; write action виконується після approval.  
**Reason:** Governance та контроль критичних бізнес-рішень.

## DEC-006 — Public deployment

**Status:** Accepted  
**Decision:** Portfolio Ready вимагає публічного HTTPS deployment на наявному VPS.  
**Reason:** Робочий URL є сильнішим доказом завершеності, ніж локальний репозиторій.

## DEC-007 — VPS is not required to host a large local LLM

**Status:** Accepted  
**Decision:** Публічний VPS хостить application stack. AI provider підключається через OpenAI-compatible adapter. Local model mode документується окремо.  
**Reason:** Обмеження VPS не повинні робити demo нестабільним або залежним від домашнього workstation.

## DEC-008 — Completion is binary

**Status:** Accepted  
**Decision:** Статус Portfolio Ready надається лише після проходження всіх gates і acceptance tests.  
**Reason:** Захист від нескінченного "майже готово".

---

## DEC-009 — Engineer RBAC role

**Date:** 2026-07-15  
**Status:** Proposed  
**Context:** 01_PRODUCT_AND_MVP_SCOPE.md §5 lists five target users, but FR-01 lists four roles.  
**Decision:** Engineer is a 5th distinct RBAC role with engineer.demo account.  
**Reason:** Engineer has distinct behavior (views technical docs and alternatives).  
**Consequences:** Affects auth middleware, seed data, demo accounts.  
**Affected documents/tests:** FR-01, FR-02, AT-002  
**Approved by:** Pending

## DEC-010 — Python version pin

**Date:** 2026-07-15  
**Status:** Accepted  
**Context:** 02_SYSTEM_BEHAVIOR_AND_DATA.md says "Python 3.12+". Current environment is 3.14.5.  
**Decision:** Pin to Python 3.12 for max library compatibility.  
**Reason:** Broadest library support, matches SoT minimum requirement.  
**Consequences:** Affects Dockerfile, pyproject.toml, CI configuration.  
**Affected documents/tests:** All backend Dockerfiles, pyproject.toml  
**Approved by:** Product Owner (2026-07-15)

## DEC-011 — Background job library

**Date:** 2026-07-15  
**Status:** Accepted  
**Context:** 02_SYSTEM_BEHAVIOR_AND_DATA.md §2 says "ARQ, Dramatiq або Celery — обрати один".  
**Decision:** Use ARQ + Redis for background jobs.  
**Reason:** Lightest async-native option with real queue semantics; sufficient for MVP.  
**Consequences:** Requires Redis service in docker-compose.yml.  
**Affected documents/tests:** docker-compose.yml, backend pyproject.toml, infra/docker/worker.dockerfile  
**Approved by:** Product Owner (2026-07-15)

## DEC-012 — Real-time updates

**Date:** 2026-07-15  
**Status:** Accepted (Phase 1 only)  
**Context:** 02_SYSTEM_BEHAVIOR_AND_DATA.md §2 says "WebSocket або polling".  
**Decision:** Use HTTP polling (3s interval) while a diagnostic job is pending or running. Stop polling at terminal state (completed/failed). Poll system status every 10s. Do not introduce WebSocket or SSE in Phase 1. This is NOT the permanent real-time architecture decision for later phases.  
**Reason:** Simplest reliable implementation for the Phase 1 diagnostic scenario. Upgrade path to SSE/WebSocket remains open for Phase 3+.  
**Consequences:** Affects frontend architecture in Phase 1 (use-diagnostic.ts, use-system-status.ts) and Phase 3 (workflow trace UI). Not a permanent architecture decision.  
**Affected documents/tests:** frontend/src/hooks/use-diagnostic.ts, frontend/src/hooks/use-system-status.ts  
**Approved by:** Product Owner (2026-07-15, Phase 1 scope only)

## DEC-013 — Workflow orchestration

**Date:** 2026-07-15  
**Status:** Proposed  
**Context:** 02_SYSTEM_BEHAVIOR_AND_DATA.md §2 says "LangGraph або власна explicit state machine".  
**Decision:** Use custom explicit state machine (no LangGraph).  
**Reason:** No extra dependency, fully debuggable, matches SoT preference.  
**Consequences:** Defines backend/ai/workflow/ architecture in Phase 5.  
**Affected documents/tests:** backend/app/ai/workflow/  
**Approved by:** Pending

## DEC-014 — Reverse proxy

**Date:** 2026-07-15  
**Status:** Accepted  
**Context:** 02_SYSTEM_BEHAVIOR_AND_DATA.md and 05_DEPLOYMENT_AND_DEMO.md say "Caddy або Nginx".  
**Decision:** Use Caddy as reverse proxy.  
**Reason:** Auto-provisions HTTPS with zero config, ideal for MVP.  
**Consequences:** Affects infra/caddy/ directory and docker-compose.yml.  
**Affected documents/tests:** infra/caddy/Caddyfile, docker-compose.yml  
**Approved by:** Product Owner (2026-07-15)

---

## DEC-015 — State management

**Date:** 2026-07-15  
**Status:** Proposed  
**Context:** 02_SYSTEM_BEHAVIOR_AND_DATA.md §2 says "Zustand або мінімальний state layer." Zustand was recommended.  
**Decision:** The permanent state-management choice remains open. For Phase 1, use React hooks and local component state — no Zustand. No `frontend/src/store/` directory in Phase 1. Zustand remains in package.json from Phase 0 but is not imported or used. Revisit when application state complexity provides a demonstrated need.  
**Reason:** Phase 1 control plane state is minimal (polling status, diagnostic results). Local component state and TanStack Query are sufficient. No demonstrated need for an external state library.  
**Consequences:** Affects frontend/src/hooks/, frontend/src/components/. No external state library in Phase 1.  
**Affected documents/tests:** frontend/src/hooks/, frontend/src/components/  
**Approved by:** Pending (Phase 1 approach: Product Owner 2026-07-15)

## DEC-017 — Component library

**Date:** 2026-07-15  
**Status:** Accepted  
**Context:** 02_SYSTEM_BEHAVIOR_AND_DATA.md §2 says "component library із послідовною design system" but names no specific library.  
**Decision:** Use shadcn/ui with Tailwind CSS.  
**Reason:** Accessible, no lock-in, pairs naturally with Tailwind (already configured). Full control over component source code.  
**Consequences:** Affects all frontend component work. `frontend/components.json` will be added. shadcn/ui components are copy-paste, not an npm dependency.  
**Affected documents/tests:** frontend/src/components/ui/  
**Approved by:** Product Owner (2026-07-15)

## DEC-024 — Correlation ID format

**Date:** 2026-07-15  
**Status:** Accepted  
**Context:** FR-07 / AT-012 require correlation IDs. Format was not specified in Source of Truth.  
**Decision:** Use UUID v4 for all correlation IDs.  
**Reason:** Standard, collision-free, no coordination needed, universally supported.  
**Consequences:** Affects backend/app/core/correlation.py, all API responses, worker logs, and frontend display.  
**Affected documents/tests:** backend/app/core/correlation.py, backend/tests/  
**Approved by:** Product Owner (2026-07-15)

## DEC-029 — Phase 1 scope: authentication deferral

**Date:** 2026-07-15  
**Status:** Accepted  
**Context:** 07_ROADMAP.md Phase 1 deliverables include "basic login page." 04_ACCEPTANCE_TESTS.md AT-002 (demo authentication) is mapped to Phase 1. The Phase 1 brief focuses on the Operations Control Plane.  
**Decision:** Defer all authentication to Phase 2. Phase 1 does not implement login, JWT, sessions, RBAC, or demo accounts.  
**Reason:** The Operations Control Plane does not require authentication to demonstrate a running skeleton. Authentication is better implemented when RBAC decisions (DEC-009) are resolved and seed data exists (Phase 2).  
**Consequences:** `07_ROADMAP.md` Phase 1 deliverable "basic login page" is deferred to Phase 2. AT-002 moves to Phase 2. This is a scope change approved by the Product Owner.  
**Constraints (approved by Product Owner):**
- Phase 1 must not be publicly deployed.
- Phase 1 must not process real, sensitive, or production data.
- Diagnostic endpoints must be documented as development/demo-only.  
**Affected documents/tests:** AT-002, 07_ROADMAP.md Phase 1 deliverables, requirements_traceability_matrix.md  
**Approved by:** Product Owner (2026-07-15, with constraints above)

## DEC-033 — Phase 1 feature branch

**Date:** 2026-07-15  
**Status:** Accepted  
**Context:** Phase 0 established one-feature-branch-per-phase convention (feature/phase-0-repository-bootstrap).  
**Decision:** Use `feature/phase-1-running-skeleton` as the Phase 1 feature branch.  
**Reason:** Follows established naming convention. Descriptive of the Phase 1 objective.  
**Consequences:** Branch must be created from `main` at `4e7879c`. No direct commits to main.  
**Affected documents/tests:** Git workflow  
**Approved by:** Product Owner (2026-07-15)

---

## Template for new decisions

```markdown
## DEC-XXX — Назва

**Date:** YYYY-MM-DD  
**Status:** Proposed | Accepted | Rejected | Superseded  
**Context:**  
**Decision:**  
**Reason:**  
**Consequences:**  
**Affected documents/tests:**  
**Approved by:**  
```
