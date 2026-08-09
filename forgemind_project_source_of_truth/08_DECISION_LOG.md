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
**Status:** Accepted  
**Context:** 01_PRODUCT_AND_MVP_SCOPE.md §5 lists five target users, but FR-01 lists four roles.  
**Decision:** Engineer is a distinct fifth role and must not automatically inherit privileges from any other role, including Production Manager, Procurement Specialist or AI Administrator.  Engineer has a dedicated `engineer.demo` account.  
**Reason:** Engineer has distinct behavior (views technical docs and alternatives) and warrants a separate RBAC identity.  
**Consequences:** Affects auth middleware, seed data, demo accounts. Roles table contains 5 codes.  
**Affected documents/tests:** FR-01, FR-02, AT-002  
**Approved by:** Product Owner (2026-07-17)

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

**Date:** 2026-07-15 (Accepted 2026-08-09)
**Status:** Accepted
**Approved by:** Product Owner (2026-08-09)

### Context

The recovery workflow (WP-REC-03 / MVP Phase 5: AI Workflow) requires a
mechanism to drive the sequence of steps that connect deterministic risk
calculation to AI provider invocation, structured-output validation,
recommendation persistence, and user-visible retry. The workflow must be
auditable: every state transition must be traceable, inspectable, and
reproducible from persisted records.

The existing background execution mechanism is ARQ + Redis (DEC-011,
Accepted). ARQ already runs document ingestion and diagnostic jobs in
`backend/app/worker.py`. ARQ handles dispatch and execution of background
jobs — it is not a workflow state machine and does not provide transition
validation, domain state introspection, or audit-grade transition
logging.

WP-REC-03A (AI Provider Adapter — Chat/Reasoning) is complete and merged
through PR #63 at `5c86000046ea265c799dab05d6e23601d0fe79c0`. The
`ChatProvider` abstraction (`backend/app/ai/provider/chat_provider.py`)
provides `async complete(prompt, schema, context) -> ChatResult` with
`correlation_id` propagation via the `context` dict. DEC-013 must preserve
compatibility with this merged provider abstraction — the workflow engine
calls the provider through the `ChatProvider` interface, not through any
LangGraph-specific contract.

WP-REC-03B (Workflow/State-Machine Foundation) is the next implementation
package. Its scope is an explicit state machine, workflow run/step models,
a `WorkflowEngine` class, correlation-ID propagation, and a migration.
DEC-013 is the decision gate (WP-REC-03-DEC-GATE-1) that unblocks 03B.

`02_SYSTEM_BEHAVIOR_AND_DATA.md` §2 lists "LangGraph або власна explicit
state machine — обрати один" as the open choice. This decision resolves
that choice.

### Decision

ForgeMind will use its own explicit application-owned workflow state
machine. LangGraph is not introduced.

Specifically:

1. **Explicit application-owned state machine.** The workflow lifecycle
   (PENDING → RUNNING → AWAITING_VALIDATION → COMPLETED /
   FAILED_VALIDATION / FAILED_PROVIDER / FAILED_INTERNAL) is defined as
   an explicit set of states and validated transitions owned by the
   application in `backend/app/ai/workflow/state_machine.py`. Transitions
   are declared as a static structure (e.g. a `dict` / `frozenset`) and
   validated before any state change is persisted. Invalid transitions
   raise `StateMachineError` and mark the run `FAILED_INTERNAL`.

2. **No LangGraph dependency.** LangGraph is not added to
   `backend/pyproject.toml`. No LangGraph imports appear in
   `backend/app/`. The workflow graph topology for the MVP vertical
   scenario is fixed and linear; it does not require dynamic graph
   composition.

3. **ARQ handles background dispatch and execution only.** ARQ + Redis
   (DEC-011) remains the sole background job queue and execution
   mechanism. The ARQ worker (`backend/app/ai/workflow/worker.py` in
   WP-REC-03F) enqueues and executes jobs. ARQ is not the workflow state
   machine — ARQ job state (queued / running / done / failed) is not
   used to infer domain workflow state.

4. **Domain workflow state is not inferred from ARQ job state.** The
   `workflow_runs` row and its `state` column are the source of truth
   for domain workflow state. The ARQ enqueue is a best-effort
   notification; a committed `PENDING` row is the durability anchor. A
   periodic reconciler detects stuck `PENDING` rows and re-enqueues,
   guaranteeing eventual completion via reconciliation — not via ARQ job
   state.

5. **Transitions are explicit and validated.** Every state change goes
   through the state machine's transition function. Concurrent
   transitions for the same run are serialized by a database
   conditional-transition rule (`UPDATE ... WHERE state = :expected`
   with `RETURNING id`), not by ARQ-level dedup alone.

6. **Persisted state remains the source of truth where persistence is
   required.** The `workflow_runs` and `workflow_steps` tables (created
   in WP-REC-03B) record the authoritative state, step history, and
   correlation IDs. In-memory state is ephemeral; the database row is
   authoritative.

### Responsibility boundaries

| Concern | Owner |
|---------|-------|
| Domain/workflow state and state definitions | WP-REC-03B (explicit state machine in `backend/app/ai/workflow/state_machine.py`) |
| Transition rules and validation | WP-REC-03B; extended by WP-03C (`FAILED_VALIDATION`) and WP-03D (`FAILED_PROVIDER`) |
| Persistence and transactions | WP-REC-03B (models + migration); WP-REC-03F (worker persistence path) |
| Background job dispatch and execution | ARQ + Redis (DEC-011); worker functions in WP-REC-03F |
| Model invocation | WP-REC-03A `ChatProvider` abstraction (`backend/app/ai/provider/`); the workflow engine calls `ChatProvider.complete()`, not any LangGraph or framework-specific interface |
| Structured-output handling | WP-REC-03C (`schema_validator.py`, `prompts.py`, Pydantic wire schema) — not part of the state machine itself |
| Retry ownership | Automatic backend retry: WP-REC-03D; user-initiated retry API + worker: WP-REC-03F; retry UI: WP-REC-03G |

Structured-output validation is planned for WP-REC-03C and is not
prematurely designed here. Retry orchestration is planned for WP-REC-03D
(automatic) and WP-REC-03F (user-initiated), per the current Source of
Truth decomposition in `docs/planning/wp_rec_03_decomposition.md`.

### Consequences

**Benefits:**

- No new dependency; the workflow engine is pure Python with no framework
  lock-in. Full control over transitions, validation, and audit logging.
- State machine transitions are inspectable in code (static structure)
  and in the database (`workflow_runs.state`), supporting audit and
  debugging.
- Compatible with the merged `ChatProvider` abstraction from WP-REC-03A
  — the engine calls the provider through the existing interface.
- Preserves DEC-011 (ARQ + Redis) as the background-job mechanism without
  modification; no competing orchestration technology is introduced.
- Testability: transition correctness is unit-testable in isolation
  without a running queue or database; integration tests verify the
  full lifecycle with real persistence.

**Implementation cost:**

- WP-REC-03B implements the state machine, `WorkflowEngine`, models, and
  migration. This is a bounded M-size package (6-8 files, ~400-500 lines
  implementation + ~300-400 lines tests per the decomposition plan).
- No framework-provided graph primitives; the application owns the
  transition table and engine. This is acceptable for the MVP's fixed,
  linear workflow topology.

**Testing implications:**

- State machine transitions (valid and invalid) are unit-tested in
  isolation.
- Workflow run lifecycle (create → run → complete/fail) is
  integration-tested with a real database.
- Correlation-ID propagation through all steps is verified.

**Concurrency and idempotency expectations:**

- Concurrent state transitions for the same run are serialized by the
  database conditional-transition rule (`UPDATE ... WHERE state =
  :expected` with `RETURNING id`).
- ARQ-level idempotency keys deduplicate enqueue requests; they do not
  replace the database-level serialization primitive.
- The reconciler (WP-REC-03F) detects stuck `PENDING` rows and re-enqueues
  idempotently by `run_id`.

**Observability and audit implications:**

- Every state transition is logged with correlation ID, run ID, old
  state, and new state.
- Every workflow step is logged with correlation ID, run ID, step name,
  duration, and status.
- The `workflow_steps` table provides the persistent audit trail for
  trace display (WP-REC-03E) and future audit events (Phase 6).

### Rejected alternative — LangGraph

LangGraph is not selected for the current project scope. This is a
decision based on current project requirements, not a judgment about the
library's general quality.

Reasons LangGraph is not justified now:

1. The MVP workflow is a single fixed linear vertical scenario (risk
   calculation → provider call → validation → recommendation
   persistence). The topology does not require dynamic graph
   composition, conditional branching across many nodes, or runtime
   graph modification.
2. Introducing LangGraph would add a dependency and an abstraction layer
   whose graph-composition primitives are not exercised by the MVP's
   linear flow. The explicit state machine provides the same
   auditability with fewer moving parts and zero framework lock-in.
3. The project's auditability requirement (FR-07, AT-012) is satisfied by
   explicit transition logging and persisted `workflow_steps`. The state
   machine makes transitions directly inspectable in code and in the
   database; this directness is harder to achieve when transitions are
   implicit in a framework's graph execution model.
4. DEC-011 (ARQ + Redis) is already Accepted for background dispatch.
   LangGraph would introduce a second orchestration abstraction that
   overlaps with ARQ's role, increasing integration complexity without a
   demonstrated MVP benefit.

### Reconsideration triggers

This decision should be revisited when one or more of the following
conditions are demonstrated:

1. **Workflows become substantially more dynamic.** If future phases
   require runtime-composed workflow graphs (e.g. user-defined or
   data-dependent branching across many nodes), an explicit static
   transition table may become a maintenance burden that a graph
   framework could reduce.

2. **Graph composition becomes a dominant requirement.** If the
   number of workflow nodes and edges grows such that maintaining the
   transition table by hand is a significant source of defects, a
   framework with graph-composition primitives may produce a net
   maintenance benefit.

3. **Human-in-the-loop branching outgrows the explicit transition
   model.** If approval workflows (Phase 6) introduce complex
   branching (multi-approver, conditional routes, parallel approvals)
   that exceeds what an explicit transition table can express cleanly,
   a framework with native human-in-the-loop support may be justified.

4. **Framework capabilities produce a demonstrated maintenance
   benefit.** If a concrete evaluation shows that LangGraph (or a
   comparable framework) reduces code, defect rate, or integration
   complexity by an amount greater than the dependency and migration
   cost, the decision should be revisited.

Until such conditions are demonstrated, the explicit application-owned
state machine remains the architectural choice. This keeps framework
lock-in avoided: the workflow engine is pure Python with no
framework-specific contracts, so a future migration to a graph framework
would replace the engine's internals without changing the
`ChatProvider` interface, the `workflow_runs` schema, or the ARQ worker
contract.

**Affected documents/tests:** `backend/app/ai/workflow/` (WP-REC-03B),
`backend/app/ai/provider/` (WP-REC-03A — compatibility preserved),
`docs/planning/wp_rec_03_decomposition.md`, `docs/ACTIVE_WORK.md`,
`docs/next_steps.md`

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

## DEC-028 — Demo account ↔ role mapping

**Date:** 2026-07-17  
**Status:** Accepted  
**Context:** DEC-009 approved the Engineer role; DEC-029 deferred authentication to Phase 2. Planning documents (docs/next_steps.md, docs/phase_1/phase_1_completion_report.md, docs/planning/product_owner_decision_sheet.md) consistently referenced DEC-028 as the identifier for demo account ↔ role mapping, but it was never formally recorded in this Decision Log. The mapping was required before auth middleware and seed data could be implemented.  
**Numbering note:** This entry uses the identifier DEC-028, consistent with established references in planning documents since Phase 1 closeout.  
**Decision:** One primary role per demo account in Phase 2. The `user_roles` data model supports multiple roles per user (for future phases), but each Golden Dataset demo account receives exactly one role.  
**Account mapping:**
- `manager.demo` → Production Manager (code: `PRODUCTION_MANAGER`)
- `procurement.demo` → Procurement Specialist (code: `PROCUREMENT_SPECIALIST`)
- `engineer.demo` → Engineer (code: `ENGINEER`)
- `admin.demo` → AI Administrator (code: `AI_ADMINISTRATOR`)
- `auditor.demo` → Auditor (code: `AUDITOR`)  
**Constraints:**
- Document-level authorization and RAG filtering deferred to Phase 4.
- Phase 2 does not implement `document_permissions` or RAG-based access control.  
**Consequences:** Roles table contains 5 initial rows. Users table contains 5 demo accounts. User_roles table contains 5 rows (one per user). Auth middleware and seed generator enforce this exact mapping.  
**Affected documents/tests:** `users`, `roles`, `user_roles` tables; seed generator; auth middleware; AT-002.  
**Approved by:** Product Owner (2026-07-17)

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

## DEC-034 — Phase 4 status: PARTIALLY COMPLETE (SD-1)

**Date:** 2026-08-09
**Status:** Accepted
**Context:** SoT 07_ROADMAP.md Phase 4 exit criteria require "AT-006, AT-007 pass." docs/next_steps.md previously marked Phase 4 as COMPLETE. However, AT-006 has a test file and retrieval infrastructure but has NOT been verified as PASS (requires live database execution). AT-007 has implementation at service/API level (DocumentPermission model, role-filtered retriever SQL, server-side role derivation, unauthorized-role test) but has NOT been verified as PASS under its complete Source of Truth acceptance contract.
**Decision:** Reclassify Phase 4 as PARTIALLY COMPLETE until AT-006 and AT-007 have accepted PASS evidence. The exit criteria (AT-006, AT-007 pass; evaluation fixtures створені) are not weakened.
**Reason:** SoT 07 exit criteria require AT-006+AT-007 PASS. Evidence is incomplete. Keeping COMPLETE while exit criteria are unmet creates a documentation/status and acceptance-evidence contradiction. Substantial implementation exists — this is not a false technical foundation, but incomplete formal acceptance evidence.
**Consequences:** Phase 4 status is PARTIALLY COMPLETE across all status documents. Phase 5 builds on real, implemented infrastructure.
**Affected documents/tests:** `07_ROADMAP.md`, `docs/next_steps.md`, `docs/ACTIVE_WORK.md`, `README.md`, `docs/planning/requirements_traceability_matrix.md`
**Approved by:** Product Owner (2026-08-09)

## DEC-035 — Separate AT-006/AT-007 verification package (SD-2)

**Date:** 2026-08-09
**Status:** Accepted
**Context:** AT-006 and AT-007 both have relevant implementation but neither has been confirmed as PASS under the complete Source of Truth acceptance contract. AT-006 requires live database execution. AT-007 requires formal execution and confirmation that restricted content is excluded from the complete authenticated retrieval context/response path.
**Decision:** Use a separate, bounded verification package for AT-006 and AT-007. Do not assign acceptance-test execution to WP-ARCH-01.
**Reason:** WP-ARCH-01 owns architecture hygiene and agent onboarding, not acceptance-test verification. A bounded verification package keeps scope clean.
**Consequences:** A bounded verification package will be separately authorized. This decision does not authorize execution of that package.
**Affected documents/tests:** `docs/next_steps.md`, `docs/planning/wp_strat_01_product_strategy.md`
**Approved by:** Product Owner (2026-08-09)

## DEC-036 — WP-REC-03C–03G sequence preserved (SD-3)

**Date:** 2026-08-09
**Status:** Accepted
**Context:** The WP-REC-03 decomposition defines a dependency chain: 03C → 03D → 03E → 03F → 03G. An alternative sequence could prioritize 03E (first externally observable demo progress) earlier.
**Decision:** Keep the current sequence: 03C → 03D → 03E → 03F → 03G. User-visible velocity does not justify violating the established dependency sequence.
**Reason:** The decomposition's dependency chain is internally consistent. Reordering would break dependencies and increase risk.
**Consequences:** The delivery sequence preserves the decomposed order. Each package requires separate authorization.
**Affected documents/tests:** `docs/planning/wp_rec_03_decomposition.md`, `docs/next_steps.md`, `docs/planning/wp_strat_01_product_strategy.md`
**Approved by:** Product Owner (2026-08-09)

## DEC-037 — WP-REC-05 positioning (SD-4)

**Date:** 2026-08-09
**Status:** Accepted
**Context:** WP-REC-05 (RAG integration into the AI workflow) needs positioning relative to Phase 5 packages and Phase 6. Formal AT-006/AT-007 execution and accepted PASS evidence are owned by a separate bounded verification package (DEC-035), not by WP-REC-05. Phase 4 closure depends on both packages.
**Decision:** Position WP-REC-05 after WP-REC-03C–03G completion and before Phase 6. SD-4 positions only WP-REC-05; it does not establish the execution timing of the separate AT-006/AT-007 verification package.
**Reason:** RAG integration into the AI workflow requires the workflow pipeline (03F) to exist. Phase 6 (approval/audit) requires RAG citations in recommendations. The verification package (DEC-035) is separately authorized and its timing is not governed by SD-4.
**Consequences:** The planning sequence is: 03C–03G → WP-REC-05 → Phase 6. WP-REC-05 is NOT AUTHORIZED by this decision. The bounded AT-006/AT-007 verification package remains separately NOT AUTHORIZED. Authorization of one package must not authorize the other. Phase 4 cannot be classified COMPLETE until all unchanged exit criteria are satisfied, including accepted AT-006/AT-007 PASS evidence from the verification package.
**Affected documents/tests:** `07_ROADMAP.md`, `docs/next_steps.md`, `docs/planning/wp_strat_01_product_strategy.md`
**Approved by:** Product Owner (2026-08-09)

## DEC-038 — Release 1 framing (SD-5)

**Date:** 2026-08-09
**Status:** Accepted
**Context:** The product needs a concise, canonical framing that communicates its scope and positioning to recruiters and technical reviewers.
**Decision:** Use the framing: "Controlled AI-assisted Supply Risk Intelligence portfolio MVP demonstrating one complete, auditable, human-approved vertical workflow."
**Reason:** Emphasizes deterministic control, AI assistance (not autonomy), auditability, human approval, and single vertical workflow.
**Consequences:** This framing is applied in README.md and all status documents. It does not change the product scope or acceptance criteria.
**Affected documents/tests:** `README.md`, `docs/next_steps.md`, `docs/planning/wp_strat_01_product_strategy.md`
**Approved by:** Product Owner (2026-08-09)

## DEC-039 — Two-phase risk engine ↔ AI contract (TD-4)

**Date:** 2026-08-09
**Status:** Accepted
**Context:** Open question Q-19 proposed a two-phase approach for the risk engine ↔ AI output contract. The architectural principle (SoT 02 §1, DEC-004) requires that the LLM does not own deterministic values.
**Decision:** Two-phase contract: deterministic code owns quantities, severity, constraints, feasible facts, state transitions, and business-rule enforcement. AI enriches validated facts with explanations, business impact, and structured recommendations.
**Reason:** Matches the architectural principle that LLM doesn't do arithmetic. Deterministic numbers come from the engine; LLM adds human-readable context and recommendations.
**Consequences:** Affects structured-output schema design (WP-REC-03C) and recommendation schema. Consistent with DEC-004.
**Affected documents/tests:** `docs/planning/wp_strat_01_product_strategy.md`, `docs/planning/open_questions.md`
**Approved by:** Product Owner (2026-08-09)

## DEC-040 — Role-based document permissions direction (TD-5)

**Date:** 2026-08-09
**Status:** Accepted
**Context:** Open question Q-20 proposed role-based document permissions. The current implementation already uses role-based behavior: retriever.py filters via document_permissions join on role_id, and retrieval.py derives role IDs server-side from the authenticated user.
**Decision:** Role-based document permissions match the current implementation direction. Each role has access to certain document access levels (public, internal, restricted).
**Reason:** Simpler, matches RBAC model. Sufficient for MVP synthetic data. Consistent with the existing implementation.
**Consequences:** Formal decision is recorded. AT-007 verification remains required via a bounded verification package (DEC-035). The current implementation direction is confirmed.
**Affected documents/tests:** `docs/planning/wp_strat_01_product_strategy.md`, `docs/planning/open_questions.md`, `backend/app/ai/rag/retriever.py`, `backend/app/api/retrieval.py`
**Approved by:** Product Owner (2026-08-09)

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
