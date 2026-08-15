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
   periodic reconciler (D6, resolved as an ARQ cron job in
   `WorkerSettings`) detects stuck `PENDING` rows and re-enqueues,
   providing best-effort recovery via reconciliation — not via ARQ job
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
- The reconciler (WP-REC-03F, D6 resolved) detects stuck `PENDING` rows
  and re-enqueues using deterministic job identity
  `workflow:{run_id}:{dispatch_generation}`. Reconciliation is
  best-effort, not exactly-once.

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

## DEC-041 — WP-ARCH-01 closure

**Date:** 2026-08-09

**Status:** Accepted

**Context:** The WP-ARCH-01 planning artifact (`docs/planning/wp_arch_01_planning.md`) was merged via PR #69 at `3a2bc26028cac0352af2cdde8107df90f41f015c` (regular two-parent merge, 2026-08-09). The assessment produced two separate finding sets:

- Architecture hygiene: 17 `OK`, 0 `RECOMMENDED`, 0 `REQUIRED`, 0 `UNRESOLVED`.
- Agent onboarding: 6 `OK`, 1 `RECOMMENDED`, 0 `REQUIRED`, 0 `UNRESOLVED`.

The sole `RECOMMENDED` item is Finding 4.5.1, the optional agent-onboarding document. The planning artifact §7 listed 4 unresolved Product Owner decisions.

**Decision:**

1. Accept the WP-ARCH-01 planning artifact.
2. Close WP-ARCH-01 with no execution required — zero REQUIRED findings.
3. Defer the optional agent-onboarding document (Finding 4.5.1) — not authorized, not created.
4. Do not authorize WP-REC-03C, SP-0B, or any other package through this decision.
5. WP-REC-03C may be reassessed after a separate Product Owner decision; this closure does not start that reassessment.

**Reason:** No REQUIRED architecture-hygiene finding blocks a separate Product Owner reassessment of WP-REC-03C. The assessment found zero REQUIRED findings and zero UNRESOLVED findings. Closing WP-ARCH-01 after planning avoids unnecessary execution work. The agent-onboarding document is deferred because the current distributed documentation is sufficient for now. WP-REC-03C remains NOT AUTHORIZED. No conclusion is made about the readiness of WP-REC-03D through 03G. No subsequent phase is authorized or declared ready. Acceptance of WP-ARCH-01 does not replace package-specific planning, evidence, or authorization.

**Consequences:** WP-ARCH-01 is COMPLETED and CLOSED. No execution work package is spawned. The optional agent-onboarding document is not created. WP-REC-03C through 03G remain NOT AUTHORIZED. WP-REC-05 remains NOT AUTHORIZED. Bounded AT-006/AT-007 verification package remains NOT AUTHORIZED. SP-0B remains READY but NOT AUTHORIZED. Phase 4 remains PARTIALLY COMPLETE. No conclusion is made about the readiness of WP-REC-03D through 03G or any subsequent phase.

**Affected documents:** `docs/planning/wp_arch_01_planning.md`, `docs/ACTIVE_WORK.md`, `docs/next_steps.md`, `forgemind_project_source_of_truth/08_DECISION_LOG.md`. `docs/planning/wp_rec_03_decomposition.md` is NOT modified by this closure; its WP-ARCH-01 references will be synchronized during WP-REC-03 branch reconciliation.

**Approved by:** Product Owner (2026-08-09)

---

## DEC-042 — WP-REC-03F D6 reconciler mechanism resolved

**Date:** 2026-08-10

**Status:** Accepted

**Context:** WP-REC-03F planning required resolution of Decision D6: the mechanism for detecting and recovering durable `WorkflowRun` rows that remain in PENDING state after database commit but were not successfully dispatched or executed. An evidence-backed reconnaissance report (`/home/toha/forgemind-wp-rec-03f-d6-reconnaissance-report.md`) was produced and revised to correct material ARQ and concurrency errors from earlier drafts. The Product Owner reviewed the corrected report and approved all four D6 sub-decisions.

**Decision:** Approve Option A — an ARQ cron job registered in the existing `WorkerSettings` provides periodic best-effort reconciliation of stuck PENDING rows. Four sub-decisions are approved:

1. **Stale timestamp — dedicated `pending_since` field.** A dedicated `pending_since` timestamp column will be added to `WorkflowRun` during WP-REC-03F implementation. `pending_since` represents the beginning of the run's current continuous stay in PENDING. It is set on creation, reset on `FAILED_* → PENDING` retry transition, updated atomically with the dispatch_generation increment, and not modified by ordinary reconciliation scans. `created_at` must not be used for stale-candidate detection. `updated_at` must not be treated as the semantic stale-candidate timestamp. Adding `pending_since` requires a future schema migration. Migration/backfill behavior for existing rows must be defined in the implementation plan.

2. **Pagination and bounded scan — keyset pagination.** Each reconciliation occurrence processes pages using keyset pagination ordered by `pending_since ASC, id ASC`. Do not use OFFSET pagination. The scan stops when no eligible candidates remain, the maximum-page limit is reached, or the time budget is exhausted. Partial completion is valid. No durable cross-occurrence cursor is approved. Absolute starvation freedom is not claimed — this is an accepted bounded-throughput operational risk. External monitoring may alert on repeated budget exhaustion or excessive candidate age. Proposed configurable defaults (not permanently fixed): page size 100, maximum pages 5, scan time budget 50 seconds.

3. **Overlap policy — harmless overlap permitted.** ARQ cron `unique=True` deduplicates the same scheduled occurrence across workers; it does not serialize different scheduled occurrences. Distinct reconciliation occurrences may overlap. Do not add PostgreSQL advisory locks, distributed locks, or another scan-wide serialization mechanism. Correctness must not depend on a reconciliation-row claim or SELECT lock. The authoritative worker transition must atomically require `state = PENDING` AND `dispatch_generation = queued generation`. No exactly-once provider-execution guarantee is created. Reconciliation must not increment `dispatch_generation`.

4. **Dispatch target — generation-based selection.** `dispatch_generation = 0` → `workflow_start`. `dispatch_generation > 0` → `workflow_retry`. Reconciliation selects the target exclusively from the committed `dispatch_generation`. The deterministic job identity remains `workflow:{run_id}:{dispatch_generation}`. `run_id` remains the only workflow-specific function argument. Queued generation is recovered and validated from the ARQ job identity/context. Malformed, mismatched, or stale job identity must not authorize provider execution.

**Mandatory generation guard (D3/D5/D6 correctness contract, not an unresolved choice):** The execution-authorizing database transition must match both PENDING state and the queued `dispatch_generation`. A pre-read followed by an UPDATE filtered only by `state` is insufficient. Failure to match the committed generation produces a safe stale-generation skip. Stale-generation execution must not invoke the provider or regress workflow state.

**Proposed configuration defaults (not permanently fixed):** Reconciliation interval 60 seconds; stale threshold 2 minutes; page size 100; maximum pages 5; scan time budget 50 seconds; cron timeout 60 seconds; age-event thresholds: warning 1 hour, error 24 hours, critical 7 days.

**Guarantee statement:** Durable database workflow state survives queue loss. Initial enqueue and later reconciliation enqueue are best-effort. Repeated recovery attempts continue while infrastructure is available. No exactly-once provider-execution claim is created. No recovery progress is guaranteed while PostgreSQL, Redis, or workers are unavailable.

**Scope boundary:** PENDING recovery only. Stuck RUNNING recovery remains outside D6 unless separately authorized. No implementation is authorized by this decision. WP-REC-03F implementation remains NOT STARTED / NOT AUTHORIZED.

**Reason:** The reconnaissance report verified ARQ 0.28.0 source code and corrected material errors from earlier drafts (ARQ version, `unique=True` per-occurrence semantics, `minute={*}` invalid syntax, `created_at` stale-threshold invalidity, batch starvation, enqueue outcome classification, failure lifecycle, and correctness guarantee). The approved contracts use existing infrastructure (ARQ + Redis + PostgreSQL, DEC-011), introduce no new dependencies, and preserve D1-D5 contracts. The bounded-throughput risk is accepted as an operational characteristic, not a correctness defect.

**Consequences:**
- D6 is RESOLVED. All WP-REC-03F planning contracts (D1-D3, D5, D6) are resolved; D4 is superseded.
- WP-REC-03F implementation remains NOT AUTHORIZED. A separate Product Owner authorization decision is required.
- The D6 contract requires a future `pending_since` column migration during WP-REC-03F implementation.
- The D6 contract requires a future partial index `WHERE state = 'PENDING'` on `(pending_since ASC, id ASC)`.
- The generation guard is a mandatory correctness contract, not a parameter choice.
- Proposed configuration defaults (page size, max pages, time budget, thresholds) are implementation defaults, not permanently fixed Product Owner decisions.

**Affected documents:** `docs/planning/wp_rec_03_decomposition.md`, `docs/ACTIVE_WORK.md`, `docs/next_steps.md`, `forgemind_project_source_of_truth/08_DECISION_LOG.md`

**Approved by:** Product Owner (2026-08-10)

---

## DEC-043 — WP-REC-03H Phase D acceptance and Phase 5 closure

**Date:** 2026-08-14

**Status:** Accepted

**Context:** WP-REC-03H Phase C (Formal Acceptance Execution) produced two formal runs. The first run `wp-rec-03h-phase-c-20260813-01` failed and is permanently preserved as non-final, non-acceptable, and non-reusable (71 files / 300481 bytes / aggregate `e04c7f9d…a981` / no manifest). The second run `wp-rec-03h-phase-c-20260813-02` executed once, finalized, and exited cleanly (41 files / 272956 bytes / aggregate `0efe3acb…88dd` / manifest `complete:true` / source commit `686739fd1e56ec4072b52029e01e3a6d8f9963cb`). A corrected independent read-only evidence review (`docs/reviews/wp_rec_03h_phase_d_independent_evidence_review.md`) concluded the `-02` run is acceptable for a separate Product Owner Phase D acceptance declaration. The Product Owner reviewed the unchanged evidence and issued the explicit acceptance declaration recorded in `docs/reviews/wp_rec_03h_phase_d_product_owner_acceptance_declaration.md`.

**Decision:** The Product Owner explicitly declares, based on unchanged authoritative evidence from formal run `wp-rec-03h-phase-c-20260813-02`:

```text
AT-008 — PASS
AT-013 — PASS
PHASE 5 — ACCEPTED
```

These declarations are Product Owner decisions, not automated inferences from test results. Phase 5 (Controlled AI workflow) is ACCEPTED. Findings F3–F8 (incorrect risk API probe URL; unauthenticated workflow-run API probe; BrowserResult files lacking individual checksum coverage under the current contract; AT-008 identity dispatch generation null while authoritative value 0 exists elsewhere; corrected manifest unique-path arithmetic; manifest lacking an explicit schema-version field) remain open/deferred technical debt and are non-blocking for this Phase D acceptance. They are not fixed, not closed, not remediated, and are deferred to a separately authorized harness-maintenance task.

**Reason:** The independent evidence review verified that run `-02` is complete, internally consistent, traceable to source commit `686739fd…`, and semantically sufficient for AT-008 and AT-013. Every AT-008 and AT-013 criterion was classified EVIDENCED; no criterion was contradicted or un-evidenced. None of F3–F8 compromises completeness, integrity, provenance, semantic sufficiency, or contract compliance. The failed run `-01` remains rejected and permanently non-reusable.

**Consequences:**
- Phase C (Formal Acceptance Execution) is complete using accepted run `-02`.
- Phase D (Product Owner Evidence Review and Acceptance Declaration) is complete.
- AT-008 is PASS; AT-013 is PASS; Phase 5 is ACCEPTED.
- Phase 5 implementation packages WP-REC-03A through WP-REC-03G remain COMPLETE (PRs #63, #65, #72, #73, #74, #78, #80). PR #84 (`fix(acceptance): implement missing formal-evidence mode for Phase C` correction) merge commit `466b70b9dfd96728c0b966c9c59755c982b9ca87`; PR #85 (`fix(acceptance): repair WP-REC-03H formal finalization`) merge commit `686739fd1e56ec4072b52029e01e3a6d8f9963cb`.
- Phase E is documentation lifecycle reconciliation only. It does not authorize any implementation, acceptance rerun, evidence change, or later work package.
- No later work package is authorized by this decision. WP-REC-05, Phase 6, Phase 7, SP-0B, the bounded AT-006/AT-007 verification package, and deployment remain NOT AUTHORIZED unless already governed otherwise.
- Phase 4 remains PARTIALLY COMPLETE. AT-006 and AT-007 remain not verified as PASS. Phase 6 (approval and audit) and Phase 7 (public deployment) are not completed. Release 1 is NOT declared ready or deployed.

**Affected documents:** `docs/reviews/wp_rec_03h_phase_d_independent_evidence_review.md`, `docs/reviews/wp_rec_03h_phase_d_product_owner_acceptance_declaration.md`, `README.md`, `docs/ACTIVE_WORK.md`, `docs/next_steps.md`, `docs/planning/wp_rec_03_decomposition.md`, `docs/planning/wp_rec_03h_acceptance_harness.md`, `docs/planning/requirements_traceability_matrix.md`, `forgemind_project_source_of_truth/04_ACCEPTANCE_TESTS.md`, `forgemind_project_source_of_truth/07_ROADMAP.md`

**Approved by:** Product Owner (2026-08-14)

---

## DEC-044 — WP-REC-05 planning authorization and AT-006/AT-007 sequencing

**Date:** 2026-08-14

**Status:** Accepted

**Context:** The Release 1 residual-blocker reassessment concluded Release 1 is NOT READY and NOT DEPLOYED; WP-REC-03H is complete and closed; Phase 5 is ACCEPTED; AT-008 and AT-013 are PASS; Phase 4 remains PARTIALLY COMPLETE; AT-006 and AT-007 are not PASS; isolated RAG retrieval, citations, document permissions, and role filtering exist, but the controlled AI workflow does not currently call the retriever; recommendation `sources` may remain empty because RAG workflow integration was deferred; Golden Scenario step 6 is the earliest incomplete critical-path step; Phase 6 depends on RAG citations under DEC-037; and WP-REC-05 lacks a complete decomposed implementation specification. F3–F8 and SP-0B are not Release 1 blockers.

**Decision:** Authorize the planning-only package **WP-REC-05-DEC** (RAG Integration Decomposition and Planning). The authorized outcome is a complete, reviewable implementation specification for WP-REC-05, a separate AT-006/AT-007 verification contract (WP-REC-05-VFY), recorded sequencing, and a Draft documentation PR. The accepted order is: **WP-REC-05 implementation first, separate bounded WP-REC-05-VFY verification second.**

**Reason:** The decomposition must precede implementation; the verification contract must remain separate from implementation (DEC-035). Implementation and verification each require their own explicit authorization.

**Consequences:**
- WP-REC-05 implementation is NOT AUTHORIZED.
- WP-REC-05-VFY is NOT AUTHORIZED.
- AT-006 and AT-007 remain not PASS.
- Phase 4 remains PARTIALLY COMPLETE.
- Phase 6 and Phase 7 remain not authorized.
- Release 1 remains NOT READY and NOT DEPLOYED.
- F3–F8 remain deferred and out of scope.

**Affected documents/tests:** `docs/planning/wp_rec_05_rag_integration.md` (new), `docs/planning/requirements_traceability_matrix.md`, `docs/ACTIVE_WORK.md`, `docs/next_steps.md`, `forgemind_project_source_of_truth/08_DECISION_LOG.md`

**Approved by:** Product Owner (2026-08-14)

---

## DEC-045 — WP-REC-05 authorization, retrieval-failure, and citation-identity contracts

**Date:** 2026-08-14

**Status:** Accepted

**Context:** PR #87 planning artifact (`docs/planning/wp_rec_05_rag_integration.md`) passed the corrected independent re-review. F1–F7 are resolved; no BLOCKING/HIGH/MEDIUM findings remain. The three planning decisions M1 (authorization-context persistence), M2 (retrieval-failure behavior), and M3 (citation document identity) were ready for Product Owner decisions. Release 1 remains NOT READY and NOT DEPLOYED.

**Decision:** The Product Owner accepts the M1/M2/M3 planning contracts as follows.

M1 — Authorization capture is append-only per dispatch generation:
- append-only authorization identity keyed by `(run_id, dispatch_generation)`;
- durable `user_id` and an immutable captured role snapshot;
- execution uses the intersection of the captured role snapshot and the user's currently active roles;
- document permissions remain dynamically evaluated at retrieval time;
- retry creates a new immutable authorization record;
- null/system/unresolvable identity fails closed.

M2 — Retrieval execution failure is fail-closed:
- dedicated `FAILED_RETRIEVAL` state;
- `RUNNING → FAILED_RETRIEVAL`;
- explicit authorized retry `FAILED_RETRIEVAL → PENDING`;
- safe run-level error code `RETRIEVAL_FAILED`;
- one failed retrieval WorkflowStep with safe metadata;
- no Recommendation is created on retrieval execution failure;
- dispatch-generation and stale-job protection remain mandatory;
- risks remain deterministically recomputable through the read-only risk API.

M3 — The repository document UUID string is the canonical `Source.document_id`:
- `Source.document_id = str(Document.id)`;
- no artificial external document identifier;
- Source wire shape and `schema_version = "1.0"` retained;
- mandatory compatibility preflight before implementation mutation;
- a dependency on legacy external-ID semantics is a stop condition requiring a separate schema-evolution decision.

**Reason:** The selected contracts provide strong, inspectable authorization, failure handling, traceability, and citation integrity appropriate for a portfolio MVP intended for technical employer review, while remaining bounded and testable.

**Consequences:**
- M1/M2/M3 are resolved as planning decisions.
- The WP-REC-05 specification becomes decision-complete.
- WP-REC-05 implementation still requires separate explicit Product Owner authorization.
- Implementation must satisfy the M3 compatibility preflight.
- WP-REC-05-VFY remains separate and NOT AUTHORIZED.
- AT-006 and AT-007 remain not PASS.
- Phase 4 remains PARTIALLY COMPLETE.
- Phase 5 remains ACCEPTED.
- Release 1 remains NOT READY and NOT DEPLOYED.
- Phase 6/7, deployment, SP-0B, and F3–F8 remediation remain unauthorized.

**Affected documents/tests:** `docs/planning/wp_rec_05_rag_integration.md`, `forgemind_project_source_of_truth/08_DECISION_LOG.md`

**Approved by:** Product Owner (2026-08-14)

---

## DEC-046 — WP-REC-05 empty-effective-role authorization boundary

**Date:** 2026-08-14

**Status:** Accepted

**Context:**
- independent review of the M1/M2/M3 decision application found an ambiguity
  between empty-role fail-closed behavior and legitimate zero-result behavior;
- DEC-045 established role intersection but did not explicitly define the
  empty-intersection outcome;
- the Product Owner has now resolved that boundary.

**Decision:**
- empty `effective_role_ids` is a fail-closed authorization failure;
- retrieval is not executed;
- no Recommendation is created;
- use the accepted `FAILED_RETRIEVAL` / `RETRIEVAL_FAILED` path with safe
  bounded reason metadata;
- non-empty `effective_role_ids` followed by a successful retrieval with no
  permitted approved document/chunk is a legitimate zero-result;
- legitimate zero-result continues as explicitly ungrounded with empty sources.

**Reason:**
- revoked or absent authorization must not silently continue as a valid
  workflow execution;
- absence of accessible documents for an otherwise valid authorization context
  is not a system failure;
- the distinction is explicit, secure, testable, and suitable for technical
  review of the portfolio MVP.

**Consequences:**
- DEC-APP-01 is resolved;
- M1 and M2 authorization/failure boundaries are unambiguous;
- DEC-045 remains accepted and is clarified, not replaced;
- WP-REC-05 implementation remains separately NOT AUTHORIZED;
- migration implementation remains NOT AUTHORIZED;
- WP-REC-05-VFY remains NOT AUTHORIZED;
- AT-006/AT-007 remain not PASS;
- Phase 4 remains PARTIALLY COMPLETE;
- Phase 5 remains ACCEPTED;
- Release 1 remains NOT READY and NOT DEPLOYED;
- no Phase 6/7, deployment, SP-0B, or F3–F8 work is authorized.

**Affected documents/tests:**
- docs/planning/wp_rec_05_rag_integration.md
- forgemind_project_source_of_truth/08_DECISION_LOG.md

**Approved by:** Product Owner (2026-08-14)

---

## DEC-047 — WP-REC-05 implementation authorization and incorporation

**Date:** 2026-08-14

**Status:** Accepted

**Context:**
- WP-REC-05-DEC was completed and closed.
- The Product Owner subsequently gave separate implementation-only authorization for WP-REC-05 against the accepted DEC-045/DEC-046 contracts.
- The Product Owner also authorized the minimal bounded frontend extension required for FAILED_RETRIEVAL handling.
- That authorization explicitly excluded WP-REC-05-VFY, AT-006/AT-007 verification, Phase 4 acceptance, Phase 6/7 and deployment.
- PR #89 implemented WP-REC-05 and was merged through the regular merge commit `86e2d0cd3d6d3eaf889ca6d674829f7ac541778c`.
- Strict post-merge verification passed.

**Decision:**
- Record the earlier Product Owner implementation authorization as exercised.
- Record WP-REC-05 implementation as complete and incorporated into main.
- Preserve WP-REC-05-VFY as a separate, not-authorized package.
- Do not infer AT-006/AT-007 PASS or Phase 4 acceptance.

**Reason:**
- The DEC-044/DEC-045/DEC-046 statements that WP-REC-05 implementation and its migration were not authorized were correct at the time those decisions were recorded and remain immutable historical decisions.
- This decision resolves the current-state discrepancy by recording the subsequent implementation-only authorization as exercised and the completed merge, without rewriting those earlier decisions.

**Consequences:**
- The next possible lifecycle action is a separate Product Owner decision on whether to authorize WP-REC-05-VFY.
- This reconciliation does not itself authorize that verification.
- Phase 4 remains PARTIALLY COMPLETE.
- Release 1 remains NOT READY and NOT DEPLOYED.
- Phase 6/7, deployment and deferred findings remain outside scope.

**Affected documents/tests:** `docs/ACTIVE_WORK.md`, `docs/next_steps.md`, `docs/planning/requirements_traceability_matrix.md`, `forgemind_project_source_of_truth/08_DECISION_LOG.md`

**Approved by:** Product Owner (2026-08-14)

---

## DEC-048 — WP-REC-05 external provider architecture and formal VFY pinning

**Date:** 2026-08-14

**Status:** Accepted

**Context:**
- WP-REC-05 implementation is complete and incorporated into main (DEC-047).
- A follow-up bounded implementation package (WP-REC-05-PROVIDER-IMP) was authorized to decouple chat-provider selection from embedding-provider selection and to harden grounded output for an external chat-provider chain.
- The historical WP-REC-05-VFY run (`wp-rec-05-vfy-20260814-01`) remains FAILED/INCOMPLETE: AT-006 (grounded-source assertion) failed, AT-007 (negative assertions) succeeded, and both remain NOT PASS.

**Decision:**
- Groq free is the primary external chat provider, using a compatible model pinned at implementation time (`llama-3.3-70b-versatile`).
- OpenRouter paid is the commercial fallback, protected by an externally configured hard budget of approximately USD 5.
- The application does not claim to enforce the USD 5 budget; that budget is an external OpenRouter account/key control configured separately by the Product Owner (on exhaustion OpenRouter returns HTTP 402, treated as a permanent failure).
- The formal WP-REC-05-VFY will later run AT-006 and AT-007 against one exact pinned commercial provider/model with automatic provider fallback disabled inside those scenarios. A failover smoke test is a separate scenario.
- Structured-output capability modes (`json_schema`, `json_object`, `prompt_json`) are configuration-driven and observable, with server-side validation remaining authoritative.
- Per-risk citation allow-list validation closes the run-global citation gap (a tuple retrieved for one risk cannot be attached to another).
- This package authorizes implementation only: no live external-provider calls, no WP-REC-05-VFY rerun, no Product Owner acceptance, and no AT-006/AT-007 PASS declaration.

**Reason:**
- Decouples chat-provider selection from embedding-provider selection and introduces a bounded, fail-closed external provider chain without changing the Recommendation wire shape, `schema_version`, database schema, or frontend.

**Consequences:**
- Phase 4 remains PARTIALLY COMPLETE.
- Release 1 remains NOT READY and NOT DEPLOYED.
- WP-REC-05-VFY rerun and Product Owner acceptance remain separate, not-authorized actions.
- The only next lifecycle action for this package is a separate independent implementation review.

**Affected documents/tests:** `backend/app/config.py`, `backend/app/ai/provider/*`, `backend/app/ai/rag/orchestration.py`, `backend/app/ai/workflow/vertical.py`, bounded provider/workflow/RAG tests, `.env.example`, `README.md`, `docs/planning/wp_rec_05_rag_integration.md`, `forgemind_project_source_of_truth/08_DECISION_LOG.md`

**Approved by:** Product Owner (2026-08-14)

---

## DEC-049 — WP-REC-05-VFY composite-evidence acceptance and AT-006/AT-007 PASS

**Date:** 2026-08-15

**Status:** Accepted

**Context:**
- An independent composite evidence review (`docs/reviews/wp_rec_05_vfy_composite_evidence_review.md`) over the two sealed WP-REC-05-VFY evidence packages concluded: `APPROVE — COMPOSITE EVIDENCE IS SUFFICIENT FOR A SEPARATE PRODUCT OWNER ACCEPTANCE DECISION`.
- Previous sealed package `wp-rec-05-vfy-20260814-01` (source `9add3b40f07b7669dced65dcca026468a09c6357`, aggregate `f37f0ac8a6268dc95d2ef5b7216f3bc5c4d9f06aa2de3c9f8735bc0508b27177`) executes the exact canonical AT-007 restricted-only Given.
- Current sealed package `wp-rec-05-vfy-20260815-02` (source `67844235c6ec412b11e9868451f41994142b86fc`, aggregate `2ce0ba6fc71ffed9d09f45dcea9c4dd898e4b5c967211df8d7717389716e9ec8`) proves AT-006 on current `main` using live OpenRouter and persists the exact M3 tuple; independently demonstrates equal-similarity AT-007 permission discrimination; and confirms empty-role fail-closed behavior.
- `backend/app/ai/rag/retriever.py` and `backend/app/ai/workflow/prompts.py` are byte-identical between the two source commits.

**Decision:**
The Product Owner accepts the composite of the two sealed evidence packages as sufficient evidence that the AT-006 and AT-007 acceptance contracts are satisfied, and declares:
- AT-006 — PASS
- AT-007 — PASS

**Reason:**
Taken together the packages cover the canonical restricted-only case, current-main role filtering, live grounded output, citation validation, and empty-role fail-closed behavior. The review verified integrity, provenance, and contract coverage across both sealed packages.

**Consequences:**
- AT-006 is PASS; AT-007 is PASS.
- Phase 4 closure, documentation reconciliation, Phase 6/7, and deployment are NOT authorized by this decision.
- Phase 6 remains NOT STARTED / NOT AUTHORIZED; Phase 7 remains NOT STARTED / NOT AUTHORIZED; deployment remains NOT AUTHORIZED; Release 1 remains NOT READY / NOT DEPLOYED.

**Affected documents/tests:** `docs/reviews/wp_rec_05_vfy_composite_evidence_review.md`, `docs/reviews/wp_rec_05_phase_4_product_owner_acceptance.md`, `forgemind_project_source_of_truth/04_ACCEPTANCE_TESTS.md`, `docs/planning/requirements_traceability_matrix.md`, `docs/ACTIVE_WORK.md`, `docs/next_steps.md`

**Approved by:** Product Owner (2026-08-15)

---

## DEC-050 — Bounded documentation-only Phase 4 closure package authorization

**Date:** 2026-08-15

**Status:** Accepted

**Context:**
- The Product Owner separately accepted the composite WP-REC-05-VFY evidence and declared AT-006/AT-007 PASS (DEC-049).
- A bounded documentation-only Phase 4 closure package was then requested to record the composite evidence review, the Product Owner acceptance, the AT-006/AT-007 PASS statuses, and to prepare the Phase 4 closure.

**Decision:**
Authorize a bounded documentation-only Phase 4 closure package. The authorized scope is documentation only: record the composite evidence review and Product Owner acceptance artifacts, set AT-006 and AT-007 to PASS, reconcile Phase 4 to closed/accepted, and update the Decision Log. Phase 6/7, deployment, and any non-documentation change are NOT authorized.

**Reason:**
Phase 4 exit criteria (AT-006 and AT-007 PASS) are now satisfied by the accepted composite evidence; the closure must be recorded without expanding scope into implementation or later phases.

**Consequences:**
- Phase 4 is closed/accepted (documentation reconciled).
- WP-REC-05 implementation: CLOSED; WP-REC-05-PROVIDER-IMP: CLOSED; WP-REC-05-VFY: ACCEPTED.
- Phase 6 and Phase 7 remain NOT STARTED / NOT AUTHORIZED; deployment remains NOT AUTHORIZED; Release 1 remains NOT READY / NOT DEPLOYED.
- Closing Phase 4 does NOT start Phase 6.

**Affected documents/tests:** `docs/reviews/wp_rec_05_vfy_composite_evidence_review.md`, `docs/reviews/wp_rec_05_phase_4_product_owner_acceptance.md`, `docs/ACTIVE_WORK.md`, `docs/next_steps.md`, `docs/planning/requirements_traceability_matrix.md`, `forgemind_project_source_of_truth/04_ACCEPTANCE_TESTS.md`, `forgemind_project_source_of_truth/08_DECISION_LOG.md`

**Approved by:** Product Owner (2026-08-15)

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
