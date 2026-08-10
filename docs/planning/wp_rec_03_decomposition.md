# WP-REC-03-DEC — MVP Phase 5 Controlled Decomposition

**Status:** PLANNING PACKAGE — lifecycle/status corrections applied 2026-08-09; post-WP-ARCH-01 reconciliation applied 2026-08-09
**Date:** 2026-08-08 (corrected 2026-08-08; status-synced 2026-08-09; reconciled 2026-08-09)
**Baseline:** `origin/main` @ `fc48aed557d20f516cf46fe94175ce2d22c61dba` (lifecycle-correction baseline — repository state at which the 2026-08-09 status sync after WP-REC-03B was applied)
**Post-WP-ARCH-01 reconciliation baseline:** `origin/main` @ `0e0afd151098d85fdd9eaf12ba98147ed41b6336` (PR #70 merge commit), 2026-08-09.
**Authorizes:** This document authorizes planning and decomposition only.
**Does NOT authorize:** Any implementation code, test changes, dependency installation, migrations, or merge.

**Lifecycle summary (2026-08-09 status sync, reconciled 2026-08-09):**
- WP-REC-03A: COMPLETE — merged via PR #63
- WP-REC-03-DEC-GATE-1 (DEC-013): SATISFIED — DEC-013 Accepted (2026-08-09), merged via PR #64
- WP-REC-03B: COMPLETE — merged via PR #65 at `fc48aed557d20f516cf46fe94175ce2d22c61dba`
- WP-STRAT-01 (Product Strategy and Release 1 Alignment): COMPLETE — merged via PR #67 at `77d359c58cba43d310d2a532fda0836464adda2b` (2026-08-09)
- WP-ARCH-01 (Architecture Hygiene and Agent Onboarding): COMPLETED and CLOSED — planning artifact merged via PR #69 at `3a2bc26028cac0352af2cdde8107df90f41f015c`; Product Owner acceptance and closure recorded by DEC-041 and synchronized via PR #70 at `0e0afd151098d85fdd9eaf12ba98147ed41b6336` (2026-08-09). Zero REQUIRED findings. One RECOMMENDED item (agent-onboarding document, Finding 4.5.1) DEFERRED and not authorized.
- WP-REC-03C through 03E: COMPLETE — merged via PRs #72, #73, #74 respectively.
- WP-REC-03F: Planning contracts D1-D3, D5, and D6 resolved; D4 superseded; implementation NOT AUTHORIZED.
- WP-REC-03G: NOT AUTHORIZED.

---

## 1. Purpose

This document decomposes the oversized WP-REC-03 (MVP Phase 5: AI Workflow) into small, independently authorizable implementation work packages. Each resulting package has:

- independently reviewable scope;
- independently revertible scope;
- clear dependency on predecessor packages or decision gates;
- explicit acceptance-test mapping;
- no dependency on unauthorized Runtime separation.

WP-REC-03 as a single package is **too large** to implement, review, or revert as one unit. This decomposition ensures controlled delivery.

---

## 2. Release 1 Portfolio-Demo Outcome

ForgeMind Release 1 is a public portfolio MVP with a strong 3–5 minute demonstration on synthetic data. It must let a recruiter or technical reviewer see a complete working business scenario and then inspect the public GitHub repository.

Phase 5 must produce **visible AI-assisted value**, not only backend infrastructure. The end of Phase 5 must deliver an executable and visible vertical slice:

Production Manager starts analysis
→ deterministic risks remain authoritative
→ AI workflow runs
→ structured result is validated and persisted
→ progress and failures are visible
→ validated recommendation is shown in the UI
→ user may retry a failed AI run
→ no controlled write occurs before Phase 6 approval

For every Phase 5 package, the outcome type is stated:

- **internal architectural enablement** — no direct user-visible demo progress;
- **externally observable demo progress** — the reviewer can see something new in the demo;
- **complete user-visible increment** — the reviewer can interact with a new capability.

---

## 3. Validation Against Current Repository Evidence

The provisional decomposition in the SP-1 assessment (§18, line 1074) proposed:

| Provisional ID | Title | Size |
|----------------|-------|------|
| WP-REC-03A | AI provider adapter | M |
| WP-REC-03B | Workflow engine | M |
| WP-REC-03C | Structured output validation | S |
| WP-REC-03D | Model outage handling | S |
| WP-REC-03E | Workflow run detail UI | S |

### Validation findings

1. **The provisional five-package structure is insufficient.** The provisional list covers backend infrastructure but does not explicitly provide a workflow-start API, wiring from deterministic risk results into workflow input, recommendation persistence and presentation, or user-initiated retry. An additional package (WP-REC-03F) is required to deliver the user-facing vertical slice. The corrected decomposition produces **seven packages** (03A–03G) plus one decision gate.

2. **The provisional order 03C before 03D is confirmed as correct.** The provisional list already places structured-output validation (03C) before model outage handling (03D). This order is preserved: 03C defines the `FAILED_VALIDATION` failure path, which 03D's outage handler must also handle as a non-retryable failure. No reordering was needed; the original order was already correct.

3. **A decision gate must precede WP-REC-03B.** DEC-013 (workflow orchestration: custom state machine vs LangGraph) is **Accepted** (Product Owner accepted 2026-08-09; merged via PR #64 at `5d5616c12cf96049ef345b3d689be78d5359b352`; see `08_DECISION_LOG.md` DEC-013). The decision gate (WP-REC-03-DEC-GATE-1) is **SATISFIED**. WP-REC-03B is now COMPLETE (merged via PR #65).

4. **DEC-013 may be resolved at any time.** The gate has no dependency on WP-REC-03A completion. The Product Owner may accept DEC-013 before, during, or after 03A implementation. The only constraint is that DEC-013 must be Accepted before WP-REC-03B implementation begins.

5. **DEC-015 (state management) does not block Phase 5.** DEC-015 is Proposed for the permanent frontend state-library choice, but the Phase 1 approach (React hooks + TanStack Query) was approved by the Product Owner. WP-REC-03E (recommendation UI) and 03G (retry UI) can proceed with the approved Phase 1 approach. The permanent DEC-015 decision can be deferred until application-state complexity demonstrates a need. No gate is required for 03E or 03G.

6. **Existing embedding provider pattern is reusable evidence.** `backend/app/services/embedding_provider.py` defines an ABC interface with `OpenAIEmbeddingProvider` and `FakeEmbeddingProvider` adapters, plus `embedding_provider_factory.py` with environment-aware validation. WP-REC-03A (AI provider adapter for chat/reasoning) can follow this proven pattern.

7. **The original decomposition baseline was greenfield for workflow infrastructure.** At the 2026-08-08 decomposition baseline, the repository had no workflow engine, workflow state machine, workflow ORM models, or `backend/app/ai/workflow/` package. WP-REC-03B introduced that foundation, including the workflow package and the `WorkflowRun`, `WorkflowStep`, and `Recommendation` ORM models. WP-REC-03C through 03E are now COMPLETE (merged via PRs #72, #73, #74). WP-REC-03F and 03G remain NOT AUTHORIZED for implementation.

8. **Config already has OpenAI settings.** `backend/app/config.py` defines `openai_api_key`, `openai_api_base`, `openai_chat_model`, `openai_embedding_model`, `llm_timeout_seconds`, `llm_max_retries`, `ai_rate_limit_per_minute`. The adapter will reuse these settings, not invent new ones.

9. **RAG integration remains assigned to WP-REC-05.** Phase 5 does not complete document access control (AT-007) or grounded retrieval. The workflow may call the retrieval service for context, but document access control and full RAG integration with citations in the AI recommendation are WP-REC-05 scope. Phase 5 must not falsely claim AT-007 PASS.

10. **DEC-011 (Background job library) is Accepted.** DEC-011 accepts ARQ + Redis for background jobs. WP-REC-03F uses ARQ + Redis for workflow execution. DEC-011 is **preserved, not modified**. No new orchestration technology is introduced.

---

## 4. Corrected Decomposition and Package Order

| Order | ID | Title | Size | Depends On | AT Coverage | Outcome Type |
|-------|----|-------|------|------------|-------------|--------------|
| 1 | WP-REC-03A | AI provider adapter (chat/reasoning) | M | — | — | Internal architectural enablement |
| Gate | WP-REC-03-DEC-GATE-1 | DEC-013 decision gate | — | — (no dependency on 03A) | Unblocks 03B | Decision |
| 2 | WP-REC-03B | Workflow/state-machine foundation | M | 03A + GATE-1 | — | Internal architectural enablement |
| 3 | WP-REC-03C | Structured-output validation | S | 03A + 03B | AT-008 validator clauses only (unit-level); full PASS after 03F+03E | Internal architectural enablement |
| 4 | WP-REC-03D | Automatic provider retry/outage (backend) | S | 03A + 03B + 03C | — (backend retry only; AT-013 NOT PASS) | Internal architectural enablement |
| 5 | WP-REC-03E | Workflow-run detail + recommendation UI | S | 03A + 03B + 03C + 03D | FR-07, §3.6 (workflow trace); AT-008 trace-visibility clauses; partial foundation for AT-012 | Externally observable demo progress |
| 6 | WP-REC-03F | Backend workflow start/retry API + ARQ worker | M | 03A + 03B + 03C + 03D + 03E | AT-008 full PASS (with 03E); AT-013 backend clauses (PASS after 03F; 03G adds UI clauses) | Complete user-visible increment (backend half) |
| 7 | WP-REC-03G | Frontend start/retry UI interaction | S | 03A + 03B + 03C + 03D + 03E + 03F | AT-013 UI clauses (non-freeze, user retry action) | Complete user-visible increment (frontend half) |

**Phase 5 exit criteria:** AT-008 PASS (full PASS after 03F wires worker execution + 03E renders trace; 03C owns only the validator), AT-013 PASS (after 03F + 03G), model response validated, deterministic numbers preserved, user-visible recommendation and retry available (`07_ROADMAP.md` Phase 5).

**AT-008 PASS requires (full):** provider adapter (03A) + workflow state-machine (03B) + structured-output validator (03C, defines `FAILED_VALIDATION` on invalid output) + worker execution wiring that invokes the validator (03F) + trace retrieval that exposes the error in the workflow run (03E). AT-008 is NOT fully PASS after 03C alone — 03C only owns the validator and its unit-level verification; the end-to-end flow (provider → validation → state transition → recommendation persistence → trace display) is completed only after 03F wires the worker and 03E exposes the trace via the API/UI.

**AT-013 PASS requires:** backend automatic retry (03D), workflow start/retry ARQ worker (03F — enqueues jobs, owns long-running execution), failed-step visibility in UI (03E), start/retry UI action (03G), non-freezing UI behavior during long-running workflows (03E+03G), and user retry action (03G). AT-013 is NOT PASS after 03D alone, and NOT PASS after 03F alone (UI clauses require 03G).

---

## 5. Architecture Decision Gates

### GATE-1: DEC-013 — Workflow orchestration

**Current status:** Accepted (Product Owner accepted 2026-08-09; see `08_DECISION_LOG.md` DEC-013). Approved by: Product Owner.

**Decision:** Use custom explicit state machine (no LangGraph).

**Why a gate is required:** WP-REC-03B (workflow/state-machine foundation) cannot be implemented without knowing whether to use a custom state machine or LangGraph. The choice affects the entire `backend/app/ai/workflow/` architecture.

**Timing:** DEC-013 may be resolved at any time. It has no dependency on WP-REC-03A or any other implementation package. The Product Owner may accept it before, during, or after 03A. The only constraint: DEC-013 must be Accepted before WP-REC-03B implementation begins.

**Gate requirement:** ~~The Product Owner must accept, reject, or modify DEC-013 before WP-REC-03B implementation begins.~~ **SATISFIED:** DEC-013 is Accepted (2026-08-09, merged via PR #64 at `5d5616c12cf96049ef345b3d689be78d5359b352`). The gate is resolved. WP-REC-03B is COMPLETE (merged via PR #65 at `fc48aed557d20f516cf46fe94175ce2d22c61dba`).

**If accepted (custom state machine):** WP-REC-03B proceeds as specified below.

**If rejected (LangGraph chosen instead):** WP-REC-03B scope changes — LangGraph dependency added, architecture differs. The decomposition plan must be revised before 03B implementation.

**If modified:** The Product Owner's modification is authoritative; the plan must be updated.

### DEC-015 — State management

**Current status:** Proposed (permanent choice). Phase 1 approach (React hooks + local state, no Zustand) approved by Product Owner.

**Why no gate is required for Phase 5:** WP-REC-03E (recommendation UI) and 03F (retry UI) can use the approved Phase 1 approach (TanStack Query for server state, local component state for UI state). The permanent state-library decision does not block Phase 5 deliverables. The decision can be revisited when application-state complexity demonstrates a need.

**Recommendation:** Defer DEC-015 permanent decision until after Phase 6, when the approval center and audit log UI may create sufficient state complexity to justify a state library.

---

## 6. Package Specifications

Each package below specifies the 15 required attributes.

---

### WP-REC-03A — AI Provider Adapter (Chat/Reasoning)

**1. Stable ID and title:** WP-REC-03A — AI Provider Adapter (Chat/Reasoning)

**2. Objective:** Implement an OpenAI-compatible chat/reasoning provider adapter with a deterministic fake provider for testing, following the proven embedding provider pattern.

**3. Outcome type:** Internal architectural enablement — no direct user-visible demo progress. The backend gains the ability to call an OpenAI-compatible chat model, but no user-facing API or UI is exposed.

**4. Exact included scope:**
- `backend/app/ai/provider/__init__.py`
- `backend/app/ai/provider/chat_provider.py` — ABC interface `ChatProvider`, methods: `async complete(prompt, schema, context) -> ChatResult`
- `backend/app/ai/provider/openai_chat_provider.py` — `OpenAIChatProvider` using `AsyncOpenAI`, reusing `openai_api_key`, `openai_api_base`, `openai_chat_model`, `llm_timeout_seconds`, `llm_max_retries` from `Settings`
- `backend/app/ai/provider/fake_chat_provider.py` — `FakeChatProvider` returning deterministic responses for testing
- `backend/app/ai/provider/factory.py` — environment-aware factory (fake blocked in staging/production), following `embedding_provider_factory.py` pattern
- `backend/app/ai/provider/exceptions.py` — `ChatProviderError`, `TransientChatProviderError`, `PermanentChatProviderError`, `ChatProviderConfigurationError` (mirroring embedding provider hierarchy)
- Unit tests: `backend/tests/unit/test_chat_provider.py`, `backend/tests/unit/test_chat_provider_factory.py`

**5. Explicit exclusions:**
- No workflow engine or state machine (that is 03B)
- No structured-output schema validation (that is 03C)
- No automatic retry or outage handling (that is 03D)
- No API endpoints exposing the provider (that is 03F)
- No frontend changes
- No new database models or migrations

**6. Permitted repository areas:**
- `backend/app/ai/provider/` (new directory)
- `backend/tests/unit/test_chat_provider*.py` (new test files)
- `backend/pyproject.toml` (only if a new dependency is justified — openai SDK is already present)

**7. Dependencies and predecessor gates:**
- No predecessor implementation package required
- No predecessor decision gate required (DEC-013 affects 03B, not 03A)
- Existing infrastructure: `backend/app/config.py` (OpenAI settings), `backend/app/services/embedding_provider*.py` (pattern reference)

**8. Relevant Source-of-Truth requirements:**
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §2: "OpenAI-compatible provider interface; one main chat/reasoning model; cloud and local endpoint must connect through the same adapter contract"
- `03_DEFINITION_OF_DONE.md` Gate C: "All model calls have run ID, latency and model metadata"
- `08_DECISION_LOG.md` DEC-007: "AI provider connects through OpenAI-compatible adapter"

**9. Acceptance tests and additional unit/integration tests:**
- No AT is PASS after 03A alone. The provider adapter is foundational; AT coverage accrues in later packages.
- Additional unit tests: factory environment-aware validation, fake provider determinism, OpenAI provider construction with config, exception hierarchy correctness, timeout configuration, retry configuration

**10. Failure and rollback behavior:**
- Provider construction failure: `ChatProviderConfigurationError` raised at startup, application fails fast
- Transient API error: `TransientChatProviderError` raised to caller (workflow engine in 03B; automatic retry in 03D)
- Permanent API error: `PermanentChatProviderError` raised to caller (no retry)
- Rollback: revert the feature branch; no database changes to undo

**11. Security and secrets constraints:**
- `OPENAI_API_KEY` is read from `Settings.openai_api_key` (env var), never logged
- No API key in code, tests, or fixtures
- Fake provider uses no secrets
- Provider metadata (model name, latency) is logged; API key is never in logs
- Rate limiting config (`ai_rate_limit_per_minute`) respected by the adapter

**12. Observability requirements:**
- Every `complete()` call logs: correlation ID, model name, latency, token usage (if available), success/error status
- Logging follows `backend/app/core/logging.py` structured format
- Correlation ID propagated from request context (`backend/app/core/correlation.py`)

**13. Estimated size:** M (4-6 new files, ~300-400 lines implementation + ~200-300 lines tests)

**14. Exit criteria:**
- `ChatProvider` ABC defined with `complete()` method
- `OpenAIChatProvider` implemented and unit-tested (with mocked AsyncOpenAI)
- `FakeChatProvider` implemented and unit-tested (deterministic)
- Factory implemented with environment-aware validation
- Exception hierarchy mirrors embedding provider
- All unit tests pass
- No secrets in code or tests
- Linter and type checks pass

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. This package requires explicit Product Owner authorization before implementation begins.

---

### WP-REC-03-DEC-GATE-1 — DEC-013 Decision Gate

**1. Stable ID and title:** WP-REC-03-DEC-GATE-1 — DEC-013 (Workflow Orchestration) Decision Gate

**2. Objective:** Resolve DEC-013 (custom state machine vs LangGraph) before WP-REC-03B implementation.

**3. Outcome type:** Decision — no code output; unblocks 03B.

**4. Exact included scope:**
- Product Owner reviews DEC-013 context, decision, and consequences
- Product Owner accepts, rejects, or modifies the decision
- Decision recorded in `08_DECISION_LOG.md` with status **Accepted** and `Approved by: Product Owner`
- If accepted (custom state machine): no code changes; 03B proceeds
- If changed: this decomposition plan must be revised

**5. Explicit exclusions:**
- No implementation code
- No test changes
- No dependency installation

**6. Permitted repository areas:**
- `forgemind_project_source_of_truth/08_DECISION_LOG.md` (Decision Log update only — requires Product Owner approval as it is a Source-of-Truth file)

**7. Dependencies and predecessor gates:**
- None. DEC-013 may be resolved at any time. It has no dependency on WP-REC-03A or any other implementation package. The only constraint is that DEC-013 must be Accepted before WP-REC-03B implementation begins.

**8. Relevant Source-of-Truth requirements:**
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §2: "LangGraph or own explicit state machine — choose one"
- `08_DECISION_LOG.md` DEC-013: "Use custom explicit state machine (no LangGraph)" — Status: Accepted (2026-08-09)

**9. Acceptance tests:** N/A (decision gate, not implementation)

**10. Failure and rollback behavior:** If the Product Owner rejects the custom state machine, the decomposition plan must be revised before 03B.

**11. Security and secrets constraints:** N/A

**12. Observability requirements:** N/A

**13. Estimated size:** S (decision recording only)

**14. Exit criteria:**
- [x] DEC-013 status is **Accepted** in `08_DECISION_LOG.md`
- [x] `Approved by: Product Owner` recorded

**15. Separate Product Owner authorization requirement:** **SATISFIED.** The Product Owner accepted DEC-013 on 2026-08-09. The gate is resolved. WP-REC-03B now requires only explicit Product Owner implementation authorization.

---

### WP-REC-03B — Workflow/State-Machine Foundation

**1. Stable ID and title:** WP-REC-03B — Workflow/State-Machine Foundation

**2. Objective:** Implement the workflow run lifecycle (create → run → complete/fail) with an explicit state machine, workflow run/steps models, and correlation ID propagation.

**3. Outcome type:** Internal architectural enablement — no direct user-visible demo progress. The backend can create and persist workflow runs with steps and correlation IDs.

**4. Exact included scope:**
- `backend/app/models/workflow.py` — `WorkflowRun`, `WorkflowStep`, and `Recommendation` SQLAlchemy models
- `backend/alembic/versions/XXX_workflow_models.py` — Alembic migration creating `workflow_runs`, `workflow_steps`, and `recommendations` tables
- `backend/app/ai/workflow/__init__.py`
- `backend/app/ai/workflow/state_machine.py` — explicit state machine (states: PENDING, RUNNING, AWAITING_VALIDATION, COMPLETED, FAILED_VALIDATION, FAILED_PROVIDER, FAILED_INTERNAL; transitions defined as a dict/frozenset)
- `backend/app/ai/workflow/engine.py` — `WorkflowEngine` class: creates run, executes steps, calls `ChatProvider.complete()`, propagates correlation ID, records steps
- `backend/app/schemas/workflow.py` — Pydantic schemas for workflow run/step
- Unit tests: `backend/tests/unit/test_workflow_state_machine.py`, `backend/tests/unit/test_workflow_engine.py`
- Integration tests: `backend/tests/integration/test_workflow_run_lifecycle.py`

**Recommendation model ownership (N5 resolved):**

03B owns the SQLAlchemy `Recommendation` model and its Alembic migration. The Pydantic wire schema (`backend/app/schemas/recommendation.py`) is owned by 03C (see 03C §4). 03B does not create or modify `backend/app/schemas/recommendation.py`; it only creates `backend/app/models/workflow.py` containing the `Recommendation` SQLAlchemy ORM model.

**Persistence ownership:**

| Concern | Owner |
|---------|-------|
| Database table `recommendations` and Alembic migration | **03B** (this package) |
| SQLAlchemy `Recommendation` model | **03B** |
| Relationship to `workflow_runs`, `workflow_steps`, `plan_id`, `risk_id` | **03B** |
| Persistence path (worker writes validated recommendation) | **03F** (worker execution path uses 03B's SQLAlchemy model) |
| Read/retrieval path (API serves recommendation) | **03E** (uses 03B's SQLAlchemy model) |
| Validated-success behavior | Persisted with status `VALIDATED`, linked to workflow run and plan |
| FAILED_VALIDATION behavior | No `Recommendation` row persisted; workflow run marked `FAILED_VALIDATION` with error details in `workflow_steps` |
| Rollback / downgrade | Alembic downgrade drops `recommendations` table together with `workflow_runs` and `workflow_steps` (single migration, single downgrade) |
| Unit + integration coverage | 03B: model/migration/relationship tests; 03F: persistence-path tests; 03E: retrieval tests |

**5. Explicit exclusions:**
- No structured-output schema validation (that is 03C)
- No automatic retry logic (that is 03D)
- No user-facing API endpoints (that is 03F)
- No frontend changes (that is 03E)
- No approval/audit/procurement models (those are Phase 6 / WP-REC-04)
- **NOT permitted:** `backend/app/schemas/recommendation.py` — that file is owned by 03C (Pydantic wire schema). 03B owns only the SQLAlchemy ORM `Recommendation` model inside `backend/app/models/workflow.py`.

**6. Permitted repository areas:**
- `backend/app/models/workflow.py` (new) — contains `WorkflowRun`, `WorkflowStep`, and `Recommendation` SQLAlchemy models
- `backend/app/ai/workflow/` (new directory) — `__init__.py`, `state_machine.py`, `engine.py`
- `backend/app/schemas/workflow.py` (new) — Pydantic schemas for workflow run/step only
- `backend/alembic/versions/XXX_workflow_models.py` (new migration)
- `backend/tests/unit/test_workflow_*.py` (new tests)
- `backend/tests/integration/test_workflow_*.py` (new tests)
- **NOT permitted:** `backend/app/schemas/recommendation.py` — owned by 03C (Pydantic wire schema)

**7. Dependencies and predecessor gates:**
- WP-REC-03A complete (provider adapter must exist) — COMPLETE (merged via PR #63)
- WP-REC-03-DEC-GATE-1 complete (DEC-013 Accepted) — SATISFIED (Product Owner accepted 2026-08-09; merged via PR #64)

**8. Relevant Source-of-Truth requirements:**
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §2: "LangGraph or own explicit state machine"
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §3: `workflow_runs`, `workflow_steps` entities
- `03_DEFINITION_OF_DONE.md` Gate C: "All model calls have run ID"
- FR-07: "Every workflow step must be traceable by correlation ID"
- `08_DECISION_LOG.md` DEC-013: custom state machine (if accepted)
- `08_DECISION_LOG.md` DEC-024: UUID v4 for correlation IDs

**9. Acceptance tests and additional unit/integration tests:**
- No AT is PASS after 03B alone. The state machine is foundational; AT coverage accrues in later packages.
- Additional unit tests: state machine transition correctness (all valid/invalid transitions), workflow run creation, step recording, correlation ID propagation, concurrent run safety
- Additional integration tests: run lifecycle with real database (create → run → complete), failed run persistence

**10. Failure and rollback behavior:**
- Invalid state transition: `StateMachineError` raised, run marked `FAILED_INTERNAL`
- Provider error: run marked `FAILED_PROVIDER` (transient) or `FAILED_INTERNAL` (permanent) — automatic retry logic is 03D
- Rollback: revert feature branch; Alembic downgrade removes workflow tables

**11. Security and secrets constraints:**
- No secrets in workflow models or state machine
- Correlation IDs are UUIDs (not secrets)
- Model call metadata (model name, latency) logged; API key never in workflow logs

**12. Observability requirements:**
- Every state transition logged with correlation ID, run ID, old state, new state
- Every workflow step logged with correlation ID, run ID, step name, duration, status
- Structured logging via `backend/app/core/logging.py`

**13. Estimated size:** M (6-8 new files, ~400-500 lines implementation + ~300-400 lines tests)

**14. Exit criteria:**
- `WorkflowRun` and `WorkflowStep` models and migration created
- State machine implemented with all defined states and transitions
- `WorkflowEngine` creates runs, executes steps, records results
- Correlation ID propagated through all steps
- All unit and integration tests pass
- Linter and type checks pass
- Migration applies cleanly to a fresh database

**15. Separate Product Owner authorization requirement:** COMPLETE — merged via PR #65 at `fc48aed557d20f516cf46fe94175ce2d22c61dba` (2026-08-09).

---

### WP-REC-03C — Structured-Output Validation

**1. Stable ID and title:** WP-REC-03C — Structured-Output Validation

**2. Objective:** Implement versioned JSON-schema validation for AI model output. Invalid output is rejected with `FAILED_VALIDATION` status; no write actions are created.

**3. Outcome type:** Internal architectural enablement — no direct user-visible demo progress. The system can validate AI output, but no user-facing endpoint exposes it yet.

**4. Exact included scope:**
- `backend/app/ai/workflow/schema_validator.py` — validates model output against the structured recommendation schema (§6 of SoT 02)
- `backend/app/schemas/recommendation.py` — Pydantic models matching the recommendation schema (schema_version, run_id, plan_id, risks[], sources[]) — the **wire format** (input/output validation); 03B owns the database representation
- `backend/app/ai/workflow/prompts.py` — versioned prompt template (system prompt instructing the model to return the schema)
- Unit tests: `backend/tests/unit/test_recommendation_schema.py`, `backend/tests/unit/test_schema_validator.py`

**5. Explicit exclusions:**
- No automatic retry or outage handling (that is 03D)
- No user-facing API endpoints (that is 03F)
- No frontend changes (that is 03G)
- No persistence logic — no Recommendation row is written here; persistence is 03F's worker execution path (uses 03B's Recommendation model)
- No retrieval API (that is 03E)
- No approval/audit/procurement logic

**6. Permitted repository areas:**
- `backend/app/ai/workflow/schema_validator.py` (new)
- `backend/app/schemas/recommendation.py` (new)
- `backend/app/ai/workflow/prompts.py` (new)
- `backend/tests/unit/test_recommendation_schema*.py` (new tests)
- `backend/tests/unit/test_schema_validator*.py` (new tests)

**7. Dependencies and predecessor gates:**
- WP-REC-03A complete (provider adapter)
- WP-REC-03B complete (workflow engine and state machine — validation triggers `FAILED_VALIDATION` state transition)

**8. Relevant Source-of-Truth requirements:**
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §6: structured recommendation schema (schema_version, run_id, plan_id, risks[], sources[])
- `03_DEFINITION_OF_DONE.md` Gate C: "AI output passes Pydantic/JSON Schema validation; invalid result not recorded as success"
- `04_ACCEPTANCE_TESTS.md` AT-008: "model returned invalid structure → run gets FAILED_VALIDATION, no write actions, error visible in trace"
- FR-06: "Model returns result by versioned JSON schema. Invalid result is not recorded as successful."

**9. Acceptance tests and additional unit/integration tests:**
- **AT-008 validator clauses (03C owns):** Invalid output → `FAILED_VALIDATION` state transition; no write actions created. These clauses are verifiable at the unit level via the validator and state-machine in isolation.
- **AT-008 full PASS (requires 03F + 03E):** End-to-end flow: provider returns invalid structure → worker invokes validator (03C) → state machine transitions to `FAILED_VALIDATION` (03B) → error recorded in workflow step (03F) → trace retrieval exposes the error via API/UI (03E). AT-008 is NOT fully PASS after 03C alone.
- Additional unit tests: valid schema accepted, invalid schema rejected, missing fields rejected, wrong types rejected, extra fields rejected (strict mode), schema_version enforcement, source citation format validation

**10. Failure and rollback behavior:**
- Validation failure: workflow run transitions to `FAILED_VALIDATION` (via 03B state machine), error recorded in workflow step
- No write actions created (by design — write actions are Phase 6)
- Rollback: revert feature branch; no database changes

**11. Security and secrets constraints:**
- No secrets in schemas or prompts
- Prompts contain no real data — they instruct the model to use provided context
- Synthetic data only

**12. Observability requirements:**
- Validation result logged with correlation ID, run ID, schema version, validation errors (if any)
- Failed validation logged with the specific field errors

**13. Estimated size:** S (3-4 new files, ~200-250 lines implementation + ~200-250 lines tests)

**14. Exit criteria:**
- Recommendation Pydantic schema matches SoT §6 (owned by 03C)
- Validator accepts valid output, rejects invalid output
- Versioned prompt template created
- AT-008 validator clauses verifiable at unit level (FAILED_VALIDATION on invalid output, no write actions)
- AT-008 full PASS deferred to 03F+03E (requires worker wiring and trace retrieval)
- All unit tests pass
- Linter and type checks pass

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. Requires explicit Product Owner authorization.

---

### WP-REC-03D — Automatic Provider Retry/Outage (Backend)

**1. Stable ID and title:** WP-REC-03D — Automatic Provider Retry/Outage (Backend)

**2. Objective:** Implement backend automatic retry and outage handling for transient provider errors. When the AI endpoint is unavailable, the deterministic risk engine result remains available and the workflow run is marked `FAILED_PROVIDER` after retries are exhausted.

**3. Outcome type:** Internal architectural enablement — no direct user-visible demo progress. The backend handles provider outages gracefully, but no user-facing retry action or UI non-freeze behavior is implemented in this package.

**4. Exact included scope:**
- `backend/app/ai/workflow/outage_handler.py` — catches `TransientChatProviderError` and `PermanentChatProviderError` from 03A, implements **automatic** retry logic (`llm_max_retries` from config), marks workflow run as `FAILED_PROVIDER` after retries exhausted
- `backend/app/ai/workflow/retry_policy.py` — exponential backoff retry policy for transient errors
- Unit tests: `backend/tests/unit/test_outage_handler.py`, `backend/tests/unit/test_retry_policy.py`
- Integration tests: `backend/tests/integration/test_provider_outage.py` — simulates provider unavailable, verifies risk engine result still available, workflow run marked FAILED_PROVIDER

**5. Explicit exclusions:**
- No user-initiated retry API (that is 03F)
- No frontend changes (UI non-freeze behavior and retry UI action are 03E+03F)
- No approval/audit logic
- AT-013 is NOT PASS after 03D alone — AT-013 additionally requires failed-step visibility in UI, UI non-freeze, and user-initiated retry

**6. Permitted repository areas:**
- `backend/app/ai/workflow/outage_handler.py` (new)
- `backend/app/ai/workflow/retry_policy.py` (new)
- `backend/tests/unit/test_outage_handler*.py` (new tests)
- `backend/tests/integration/test_provider_outage.py` (new test)

**7. Dependencies and predecessor gates:**
- WP-REC-03A complete (provider adapter and exception hierarchy)
- WP-REC-03B complete (workflow state machine — `FAILED_PROVIDER` state)
- WP-REC-03C complete (structured-output validation — outage handler must also handle `FAILED_VALIDATION` as a non-retryable failure)

**8. Relevant Source-of-Truth requirements:**
- `03_DEFINITION_OF_DONE.md` Gate C: "When model unavailable, system shows controlled failure state"
- `04_ACCEPTANCE_TESTS.md` AT-013: "AI endpoint unavailable → risk engine result remains available, workflow shows failed AI step, UI does not freeze, user can retry"
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §2: "cloud and local endpoint must connect through same adapter contract"

**9. Acceptance tests and additional unit/integration tests:**
- AT-013 is NOT PASS after 03D. This package covers only the **automatic** backend retry/outage mechanics. AT-013 additionally requires: failed AI step visible to user (03E+03F), UI does not freeze (03E+03F), user can retry (03F). AT-013 becomes PASS only after 03F.
- Additional unit tests: transient error retried N times then `FAILED_PROVIDER`, permanent error not retried, exponential backoff timing, retry exhausted then graceful failure
- Additional integration tests: full outage scenario with mocked provider, partial outage (intermittent errors), retry-then-success

**10. Failure and rollback behavior:**
- Transient error: retried with exponential backoff (`llm_max_retries`); if exhausted, run marked `FAILED_PROVIDER`
- Permanent error: not retried; run marked `FAILED_PROVIDER` immediately
- Risk engine result: always available (deterministic, no LLM dependency — DEC-004)
- Rollback: revert feature branch; no database changes

**11. Security and secrets constraints:**
- No secrets in retry policy or outage handler
- Provider error messages logged without API keys
- Error responses to clients do not leak provider internal details

**12. Observability requirements:**
- Every automatic retry logged with correlation ID, run ID, attempt number, error type, backoff delay
- Final failure logged with correlation ID, run ID, total attempts, final error
- Risk engine result availability logged (confirms deterministic fallback works)

**13. Estimated size:** S (2-3 new files, ~150-200 lines implementation + ~200-250 lines tests)

**14. Exit criteria:**
- Outage handler catches provider exceptions and retries transient errors automatically
- Retry policy implements exponential backoff
- Risk engine result remains available during provider outage
- Workflow run marked `FAILED_PROVIDER` after retries exhausted
- All unit and integration tests pass
- Linter and type checks pass

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. Requires explicit Product Owner authorization.

---

### WP-REC-03E — Workflow-Run Detail + Recommendation UI

**1. Stable ID and title:** WP-REC-03E — Workflow-Run Detail + Recommendation UI

**2. Objective:** Expose workflow run details via read-only API and display them in the frontend, including steps, duration, model metadata, errors/retries, and the validated recommendation (summary, rationale, sources, proposed action). This package provides the user-visible trace and recommendation display but does not include the start/retry action (that is 03F).

**3. Outcome type:** Externally observable demo progress — a reviewer can view workflow run details and the validated AI recommendation in the UI, but cannot yet start or retry a workflow run.

**4. Exact included scope:**
- `backend/app/api/workflow.py` — read-only REST API: `GET /api/v1/workflow-runs/{run_id}` returns run with steps and recommendation; `GET /api/v1/workflow-runs` lists runs (paginated)
- `backend/app/schemas/workflow.py` — update with response schemas including recommendation fields (extends 03B schemas)
- `frontend/src/routes/workflow-run-detail.tsx` — workflow run detail page: renders steps, duration, model metadata, errors/retries, and the validated recommendation (summary, rationale, sources, proposed action)
- `frontend/src/hooks/use-workflow-run.ts` — TanStack Query hook for fetching run details
- Frontend tests: `frontend/src/routes/__tests__/workflow-run-detail.test.tsx`

**Recommendation retrieval ownership (resolved here):**

03E owns the **read/retrieval path** for validated recommendations. The API endpoint queries the `Recommendation` model owned by 03B and returns it in the workflow-run response. 03E does not own the Recommendation model or its persistence — it only reads and displays.

**5. Explicit exclusions:**
- No workflow start API (that is 03F)
- No user-initiated retry API or retry UI action (that is 03F backend + 03G frontend)
- No approval center UI (that is Phase 6 / WP-REC-04D)
- No audit log UI (that is Phase 6 / WP-REC-04E)
- No automatic retry or outage logic (that is 03D — this package only displays errors)
- No new workflow engine logic (that is 03B — this package only reads and displays)
- No document access control or RAG integration (that is WP-REC-05)
- No Recommendation persistence logic (that is 03F's worker execution path using 03B's model)

**6. Permitted repository areas:**
- `backend/app/api/workflow.py` (new)
- `backend/app/schemas/workflow.py` (update)
- `frontend/src/routes/workflow-run-detail.tsx` (new)
- `frontend/src/hooks/use-workflow-run.ts` (new)
- `frontend/src/routes/__tests__/workflow-run-detail.test.tsx` (new test)

**7. Dependencies and predecessor gates:**
- WP-REC-03A complete (provider adapter — model metadata in steps)
- WP-REC-03B complete (workflow models and engine — data to display)
- WP-REC-03C complete (validation results and recommendation schema to display)
- WP-REC-03D complete (error/retry information to display)

**8. Relevant Source-of-Truth requirements:**
- `01_PRODUCT_AND_MVP_SCOPE.md` §3.6: Workflow Run Details screen — steps, duration, input/output summary, tool calls, retrieval sources, model metadata, errors/retries
- FR-07: "Every workflow step must be traceable by correlation ID"
- `03_DEFINITION_OF_DONE.md` Gate B: "Frontend tests pass"
- DEC-012: HTTP polling (3s interval) for run progress — use approved Phase 1 approach
- Partial foundation for AT-012 (audit trace completeness) — workflow steps and correlation IDs are visible, but full audit events are Phase 6. AT-012 is NOT PASS during Phase 5.

**9. Acceptance tests and additional unit/integration tests:**
- AT-007 is NOT mapped to this package. AT-007 (Document Access Control) is exclusively WP-REC-05 scope. Workflow trace UI is not partial AT-007 coverage.
- No AT is PASS after 03E alone. This package provides the trace and recommendation display, which is a partial foundation for AT-012 (full AT-012 requires Phase 6 audit events).
- Additional unit tests: API response schema correctness, pagination, recommendation fields present
- Additional frontend tests: run detail renders steps, duration, model metadata, errors/retries, recommendation fields; polling updates run status
- Additional integration tests: API returns run with steps and recommendation from database

**10. Failure and rollback behavior:**
- API error: 404 if run not found, 500 on database error
- Frontend error: loading state, error state, empty state (if no runs)
- Rollback: revert feature branch; no database changes (models from 03B)

**11. Security and secrets constraints:**
- API requires authentication (existing `get_current_user` dependency)
- Role-based access: only users with permission to view workflow runs
- Model metadata shown (model name, latency) but API key never exposed
- No secrets in frontend code

**12. Observability requirements:**
- API requests logged with correlation ID
- Frontend polling logged via API correlation ID

**13. Estimated size:** S (4-5 new files, ~250-300 lines implementation + ~150-200 lines tests)

**14. Exit criteria:**
- `GET /api/v1/workflow-runs/{run_id}` returns run with steps and recommendation
- `GET /api/v1/workflow-runs` lists runs (paginated)
- Frontend run detail page renders steps, duration, model metadata, errors/retries, and recommendation fields
- Polling updates run status (DEC-012 approved approach)
- Loading, empty, and error states implemented
- All backend and frontend tests pass
- Linter and type checks pass

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. Requires explicit Product Owner authorization.

---

### WP-REC-03F — Backend Workflow Start/Retry API + ARQ Worker
**1. Stable ID and title:** WP-REC-03F — Backend Workflow Start/Retry API + ARQ Worker

**2. Objective:** Implement the workflow-start and user-initiated retry **HTTP endpoints** plus the **ARQ worker** that owns long-running workflow execution. Endpoints enqueue ARQ jobs (DEC-011) and return promptly with a `run_id` and an accepted response. The worker executes risk calculation → provider call → validation → recommendation persistence → state transition. No provider call, risk calculation, validation, or persistence blocks the HTTP request lifecycle.

**3. Outcome type:** Complete user-visible increment (backend half) — the HTTP contract exists, the worker runs the long-lived flow, deterministic risk results remain persisted and queryable, and the user can retry a failed AI run via the retry endpoint.

**Async execution contract (DEC-011 — ARQ + Redis, Accepted; N3 resolved — delivery contract):**

The design uses a **database-first, conditional-transition** delivery contract. The `workflow_runs` row with its unique state-transition constraint is the durability anchor; the ARQ enqueue is a best-effort notification. The contract does **not** claim "no `PENDING` row without a job" — a `PENDING` row without a job is an expected transient state. Recovery of stuck `PENDING` rows is handled by the D6 reconciler contract (resolved — see D6 contract below). 03F defines the durable dispatch facts needed for future recovery (committed `run_id`, committed `dispatch_generation`, deterministic `_job_id` reconstruction per D5 §3) and implements the reconciler function specified by the D6 contract below. The reconciler is registered as an ARQ cron job in `WorkerSettings.cron_jobs` per D6 §4.

| Concern | Behavior |
|---------|----------|
| `POST /api/v1/workflow-runs` | Requires `PRODUCTION_MANAGER` role (`require_role({"PRODUCTION_MANAGER"})`). Stores `current_user.username` in `WorkflowRun.triggered_by`. Request body must contain exactly one required `plan_id` (JSON string, exact `ProductionPlan.code`, non-empty, no leading/trailing whitespace — see D3). The endpoint resolves the code to `ProductionPlan.id` UUID and returns `404 production_plan_not_found` if no plan matches, before creating or committing any `WorkflowRun`. Request-schema validation and exact plan-code resolution occur synchronously. No provider call, risk calculation, recommendation-output/schema validation, or workflow execution occurs inside the HTTP request; persistence is limited to the initial durable `PENDING` run row after successful plan resolution. Enqueues an ARQ job (`workflow_start`) identified by `run_id` and returns `202 Accepted` with `{run_id, state: PENDING, location}`. |
| **Commit-then-enqueue order** | The start endpoint **first** inserts the `workflow_runs` row with `state=PENDING` and commits (single-row transaction). **Then** it enqueues the ARQ job `workflow_start`. The committed `run_id` is returned to the caller. |
| `POST /api/v1/workflow-runs/{run_id}/retry` | Requires authentication. Permitted when `current_user.username == workflow_run.triggered_by` (run creator) OR current user has `PRODUCTION_MANAGER` role. When `triggered_by IS NULL`, only `PRODUCTION_MANAGER` may retry. Authorization is evaluated before the D1 conditional transition. Performs one atomic conditional transition from an eligible failed state (`FAILED_PROVIDER`, `FAILED_VALIDATION`, `FAILED_INTERNAL`) to `PENDING`, reusing the same `run_id`. After the transition is committed, enqueues an ARQ job (`workflow_retry`) and returns `202 Accepted`. Exactly one concurrent caller may win the transition; losing concurrent callers receive `409 Conflict`. Retry must not modify `triggered_by`. |
| **Worker starting before commit** | Cannot occur by construction — the ARQ enqueue happens only after commit. Even if Redis/ARQ were instantaneous, the worker dequeues only after enqueue, which is post-commit. |
| ARQ worker ownership | The worker executes the full vertical wiring: risk engine → provider call → schema validation → recommendation persistence (03B's `Recommendation` model) → state transitions (03B's state machine). The worker owns all long-running work. |
| Polling | `GET /api/v1/workflow-runs/{run_id}` (03E) — the client polls persisted run state until a terminal state. DEC-012 approved approach (HTTP polling, 3s interval, stop at terminal). |
| Deterministic risk result persistence | The risk engine result is persisted as part of the workflow run **independently of the provider call**. If the provider fails after the risk engine succeeds, the deterministic risk result remains persisted and available. |
| Duplicate start requests | Duplicate start requests continue to follow the already recorded start idempotency contract. A duplicate start request returns the existing `run_id` with `202 Accepted` and does **not** re-execute. This start behavior does not define retry replay semantics. Retry requests are governed exclusively by the D1 atomic conditional transition. Once the run has left an eligible `FAILED_*` state, another retry request receives `409 Conflict`. ARQ `_job_id` remains queue-level deduplication only and does not replace database serialization (DEC-013 §5). |
| **Duplicate delivery** | ARQ jobs are keyed by a stable `run_id`-derived `_job_id` constructed as `workflow:{run_id}:{dispatch_generation}` per D5 §3. If a job with that key is already queued (ARQ dedup at enqueue time), the second enqueue is a no-op. The worker additionally guards execution via the database conditional-transition rule, so even if ARQ somehow delivered the job twice, only the first execution would successfully transition the state. |
| **Enqueue failure after the run exists (N3 scenario)** | If the ARQ enqueue raises (Redis unavailable, timeout, etc.), the endpoint returns `503 Service Unavailable` **without** `run_id` in the response body. The `PENDING` row is committed and durable but not exposed to the caller. For start enqueue failure, the `503` response must not expose the newly created `run_id`. A database failure before commit is a different failure category and must not be described as an enqueue failure. |
| **Process crash between commit and enqueue** | Identical to the enqueue-failure scenario. The `PENDING` row is committed; no job was enqueued. The caller receives no `run_id`. Recovery of the stuck row is handled by the D6 reconciler contract (resolved). |
| **Concurrent retries for the same run** | Serialized by an **explicit database conditional-transition rule** — NOT by the idempotency key alone. The retry endpoint requires the run to be in a terminal failure state (`FAILED_PROVIDER`, `FAILED_VALIDATION`, `FAILED_INTERNAL`) and uses a SQL `UPDATE ... WHERE id = :run_id AND state IN (:terminal_states)` with `RETURNING id`. Exactly one concurrent caller receives a non-empty result and is allowed to enqueue; all other concurrent callers receive an empty result and get `409 Conflict`. This is the serialization primitive — independent of the idempotency key. |
| **Idempotency key role** | Deduplicates enqueue requests with the same `run_id` at the ARQ level (prevents duplicate jobs in the queue). Does **not** serialize concurrent requests with different keys — that is the database conditional-transition rule's job. |
| No blocking of HTTP lifecycle | The HTTP request returns within the API latency budget. No synchronous provider call, no synchronous risk calculation longer than the API timeout, no synchronous persistence beyond the `PENDING` row. |
| DEC-011 preservation | No new orchestration technology is introduced. ARQ + Redis (already Accepted in DEC-011) is the sole background-job mechanism. DEC-011 is **not modified** by this package. |

**D1 retry state-transition contract (Product Owner decision, 2026-08-09):**

**Decision D1 — Select Option 1: an explicit user-initiated retry transitions an eligible failed run back to `PENDING`, reusing the same `run_id`.**

Permitted retry transitions (the only outgoing transitions from terminal states):

| Source state | Target state | Mechanism |
|--------------|--------------|----------|
| `FAILED_PROVIDER` | `PENDING` | Atomic conditional UPDATE (`WHERE state = 'FAILED_PROVIDER' RETURNING id`) |
| `FAILED_VALIDATION` | `PENDING` | Atomic conditional Update (`WHERE state = 'FAILED_VALIDATION' RETURNING id`) |
| `FAILED_INTERNAL` | `PENDING` | Atomic conditional Update (`WHERE state = 'FAILED_INTERNAL' RETURNING id`) |

`COMPLETED` remains ineligible for retry and has no outgoing transition. The three failed states remain terminal for ordinary workflow execution and polling. An authenticated and authorized retry request is an explicit external action that opens a new attempt through an approved state-machine transition. This is not authorization for direct SQL bypass of the state machine.

**Contract semantics:**

1. Retry reuses the existing workflow run and returns the same `run_id`.
2. The retry endpoint performs one atomic conditional transition from an eligible failed state to `PENDING`.
3. Exactly one concurrent caller may win the transition.
4. Losing concurrent callers receive `409 Conflict`.
5. ARQ `_job_id` remains queue-level deduplication only and does not replace database serialization.
6. After the transition to `PENDING` is committed, enqueue occurs.
7. If enqueue fails, the durable `PENDING` run remains available to the periodic reconciler.
8. The reconciler handles a retried `PENDING` run in the same manner as any other stale `PENDING` run.
9. The worker must retain its database state guard before execution (the conditional `PENDING → RUNNING` UPDATE in `WorkflowEngine._transition_run` is not bypassed).
10. Previous `WorkflowStep` records remain append-only; new steps for the retried attempt get new sequence numbers after the prior max.
11. Beginning a retry clears stale run-level terminal data required for the new attempt: `error_code`, `error_detail`, and `completed_at` are set to `NULL` atomically in the same conditional UPDATE that transitions to `PENDING`.
12. `started_at` handling: The existing model and engine semantics are **not authoritative** on whether `started_at` must be cleared for a retried attempt. The `WorkflowRun` model docstring says `started_at` is the "timestamp when the run transitioned to RUNNING"; the engine sets `started_at` only on the `PENDING → RUNNING` conditional UPDATE. However, no existing contract explicitly states whether a retried run (already having a prior `started_at` from a previous `RUNNING` transition) must clear `started_at` to `NULL` on the retry `→ PENDING` transition, or whether the subsequent `PENDING → RUNNING` transition overwrites it with a new timestamp. This is a narrowly identified implementation decision for 03F: the retry transition must either (a) clear `started_at` to `NULL` in the same conditional UPDATE that clears `error_code`/`error_detail`/`completed_at`, so the new `PENDING → RUNNING` sets a fresh `started_at`; or (b) leave `started_at` and let the subsequent `PENDING → RUNNING` overwrite it. Option (a) is recommended for data cleanliness (a retried run's `started_at` should reflect the new attempt, not a prior failed attempt), but the choice is deferred to implementation because no existing authoritative contract mandates either behavior.
13. `created_at` and prior step timestamps are preserved; the retry does not reset the run's creation time or modify existing step records.
14. Retry metadata or retry count: no existing canonical retry-count field exists on `WorkflowRun` as of the 03B implementation. D5 (resolved, 2026-08-10) authorizes adding a `dispatch_generation` field as a dispatch-identity field, not a retry-count field; this is the separately approved decision that permits the new field and migration. If a separate retry-count display mechanism is needed beyond `dispatch_generation`, it must be introduced in a separate approved work package.
15. A valid retry-eligible failed run should not contain a `Recommendation`: recommendation persistence occurs only after successful validation, successful validation produces `COMPLETED`, and `COMPLETED` cannot be retried. Do not justify recommendation upsert using the impossible scenario "a previous successful retry later becomes failed."
16. Defensive handling of inconsistent legacy data (a `Recommendation` row associated with a failed run) is not required by any existing authoritative contract; do not add speculative cleanup logic for this task.

**D2 role-based access contract (Product Owner decision, 2026-08-09):**

**Decision D2 — Start requires `PRODUCTION_MANAGER`; retry is permitted for the run creator OR `PRODUCTION_MANAGER`.**

1. `POST /api/v1/workflow-runs` requires the `PRODUCTION_MANAGER` role, enforced through the existing `require_role({"PRODUCTION_MANAGER"})` dependency.
2. A user-created run stores `current_user.username` in the existing `WorkflowRun.triggered_by` field on creation.
3. `POST /api/v1/workflow-runs/{run_id}/retry` is permitted when either:
   - `current_user.username == workflow_run.triggered_by` (run creator); or
   - the current user has the `PRODUCTION_MANAGER` role.
4. The exact authorized-role set for retry is `PRODUCTION_MANAGER` only. Do not add `AI_ADMINISTRATOR`, `ENGINEER`, `PROCUREMENT_SPECIALIST`, or `AUDITOR`.
5. When `triggered_by IS NULL`, ownership cannot authorize retry; a `PRODUCTION_MANAGER` may still retry.
6. Retry must not modify or replace `triggered_by`.
7. An authenticated user who is neither the run creator nor a `PRODUCTION_MANAGER` receives `403 Forbidden` with the existing `insufficient_permissions` error contract.
8. An unauthenticated caller receives `401`.
9. Authorization is evaluated before the D1 conditional retry transition:
   - unauthorized caller → `403`, with no transition or enqueue;
   - authorized caller whose run is no longer retry-eligible → `409`;
   - authorized concurrent loser → `409`.
10. This does not reopen or modify any accepted D1 semantics.

**D3 plan-identifier contract for the start request (Product Owner decision, 2026-08-10):**

**Decision D3 — The start request `plan_id` carries the external business identifier (`ProductionPlan.code`), not the database UUID (`ProductionPlan.id`). The workflow job is identified by `run_id`, not by `plan_id`.**

**1. Public identifier semantics:**

In the request body for `POST /api/v1/workflow-runs`, the field `plan_id` means the external business identifier stored in `ProductionPlan.code` (e.g. `"PLAN-2026-W31"`). It does not mean `ProductionPlan.id`. The field name remains `plan_id` because it is the established recommendation-wire identifier (SoT §6, `RecommendationData.plan_id: str`). No second `plan_code` or `plan_uuid` request field is introduced.

**2. Request JSON contract:**

The request must contain exactly one required `plan_id` value satisfying all of these rules:

- JSON type: string;
- identifier domain: exact `ProductionPlan.code`;
- non-empty;
- not whitespace-only;
- no leading or trailing whitespace;
- no automatic trimming;
- no case conversion;
- no lexical canonicalization;
- no UUID parsing;
- no regex restricting codes to the illustrative `PLAN-2026-W31` format.

The `PLAN-2026-W31` form remains an example, not a mandatory pattern.

Reject with `422 Unprocessable Entity`:
- missing `plan_id`;
- `null`;
- JSON numbers, booleans, arrays or objects;
- empty string;
- whitespace-only string;
- a value containing leading or trailing whitespace.

A syntactically valid UUID string is not interpreted as `ProductionPlan.id`. It is looked up only as an exact `ProductionPlan.code`; if no such code exists, return `404`.

**3. Plan resolution and persistence:**

After D2 authentication and authorization succeed, the start endpoint must:

1. resolve the exact request value against `ProductionPlan.code`;
2. return `404 Not Found` using the existing `production_plan_not_found` error contract when no matching plan exists;
3. perform this lookup before creating or committing a `WorkflowRun`;
4. pass the resolved `ProductionPlan.id` UUID to `WorkflowEngine.create_run`;
5. persist that UUID in `WorkflowRun.plan_id`.

An unknown plan therefore creates: no `WorkflowRun`, no state transition, no database commit for a run, and no ARQ enqueue.

**4. Read and response contracts (unchanged):**

- `WorkflowRun.plan_id` remains a UUID foreign key;
- `WorkflowRunSchema.plan_id` remains UUID;
- `WorkflowRunSummarySchema.plan_id` remains UUID;
- `RecommendationData.plan_id` remains the external string code.

The start response remains exactly `{run_id, state, location}` — it contains no `plan_id`. D3 does not add a UUID plan identifier to the response.

**5. Queue and worker boundary:**

D3 does not authorize duplicating both plan UUID and plan code as independent queue arguments. The durable `WorkflowRun` row remains the source of truth after the database-first commit. The workflow job is identified by `run_id`. The worker obtains the persisted plan UUID and the exact plan code through the committed run and its related `ProductionPlan` record.

- The planned start-worker input is `run_id` (not an untyped `plan_id`);
- ARQ `_job_id` is constructed as `workflow:{run_id}:{dispatch_generation}` per D5 §3 (resolved); D5 ensures that an earlier ARQ job record cannot prevent a later authorized retry of the same durable `run_id` from being enqueued;
- worker registration, `WorkerSettings.functions`, timeouts, retry counts and result retention are resolved by D5 (see D5 §5 and D5 §6);
- reconciler timing or stale-run recovery remains D6.

**6. Observability terminology:**

Where WP-REC-03F discusses logging:
- use `plan_code` for the external request identifier;
- use `plan_id` for the persisted UUID;
- use `run_id` for the workflow-run identifier.

No ambiguous statement saying only "log plan_id" when it is unclear whether it means code or UUID.

**7. Compatibility:**

D3 does not reopen or modify D1 retry transitions, same-`run_id` retry, duplicate-start idempotency, commit-before-enqueue, enqueue-failure `503`, reconciler recovery, D2 authentication/authorization/ownership, or D4's superseded status. Authorization remains before plan lookup:

- unauthenticated → `401`;
- authenticated but unauthorized → `403`;
- authorized request with invalid body → `422`;
- authorized valid request with unknown plan code → `404`;
- accepted start followed by enqueue failure → D1/C1 `503`.

No schema migration is required for `plan_id`: `WorkflowRun.plan_id` is already a UUID FK and remains unchanged. D5 separately authorizes a migration for `dispatch_generation` — see the D5 contract below.

**D5 worker registration and dispatch-identity contract (Product Owner decision, 2026-08-10):**

**Decision D5 — Accept Candidate E: a persisted `dispatch_generation` integer counter on `WorkflowRun` provides the durable dispatch identity for ARQ `_job_id` construction. Worker registration uses `arq.func(...)` with `keep_result=0`, `max_tries=1`, and timeout from `settings.arq_job_timeout`. No reconciler is registered.** (D5 boundary only — D5 did not authorize a reconciler. The later approved D6/DEC-042 contract supersedes this boundary for the final combined WP-REC-03F package; see the D6 contract below.)

D5 supersedes the earlier no-migration/no-schema-change assumption recorded in D3 §7 and WP-REC-03F §4/§5/§14. Durable dispatch identity could not be satisfied by the existing `WorkflowRun` schema — no existing field is created atomically with the authorized dispatch transition, unique per dispatch attempt, recoverable after commit-before-enqueue failure, or guaranteed to differ for every later authorized retry. D5 does not reopen or weaken D1, D2, or D3. D1 §14 prohibits introducing a retry-count field "during this task"; `dispatch_generation` is a dispatch-identity field, not a retry-count field, and D5 is the separately approved decision that authorizes it.

**D5 §1. Durable dispatch identity:**

`WorkflowRun` gains a persisted, non-null integer field `dispatch_generation`.

- The initial workflow start uses `dispatch_generation = 0`.
- Every later authorized retry receives t

... [OUTPUT TRUNCATED - 1,917 chars omitted out of 51,845 total] ...

e operations for the same committed dispatch generation use the same `_job_id`;
- the same-generation duplicate is deduplicated by ARQ;
- a later authorized retry uses a different generation and therefore a different `_job_id`;
- an earlier queued, running, completed, failed, aborted, retained, or stale Redis job key cannot collide with a later authorized retry generation;
- `_job_id` never replaces D1 database serialization;
- no timestamp, random nonce, `WorkflowStep.seq`, or process-local counter is used as dispatch identity.

The canonical persisted `run_id` representation is used when constructing the job ID.

**D5 §4. Worker input and stale-job validation:**

D3 is preserved: `run_id` remains the durable workflow identifier and the only workflow-specific argument passed to `workflow_start` and `workflow_retry`. Do not add `dispatch_generation`, plan UUID, external plan code, or another workflow identifier to the worker-function argument contract.

The worker obtains the queued generation from the ARQ job identity/context and compares it with the committed `WorkflowRun.dispatch_generation`. A job whose queued generation is not the currently committed generation is stale and must not execute the provider workflow or regress workflow state. The stale-job behavior does not introduce a new state transition; the worker skips execution for a stale generation and the committed state remains authoritative.

**D5 §5. Worker registration:**

D5 accepts:
- one canonical `WorkerSettings` (existing `backend/app/worker.py:52`);
- one existing queue: `forgemind-tasks` (existing `settings.arq_queue_name`, `backend/app/config.py:62`);
- explicit registration of `workflow_start` and `workflow_retry` through `arq.func(...)`;
- callable registration (not persisted ad hoc aliases);
- no additional worker role or queue;
- no separate Redis topology.

Future import and registration locations established by reconnaissance:
- Worker functions will be defined in `backend/app/ai/workflow/worker.py` (new, per §4 scope below);
- Registration will be added to `WorkerSettings.functions` in `backend/app/worker.py`;
- The existing `arq.func()` pattern (as used for `run_document_ingestion` at `backend/app/worker.py:57`) is the registration model;
- The `arq.func()` wrapper provides per-function `keep_result`, `max_tries`, and `timeout` configuration.

The two registered functions remain distinct because they represent different workflow entry semantics, even though both accept `run_id` and share the deterministic dispatch-generation identity model.

**D5 §6. ARQ retention, retry, and timeout contract:**

- `keep_result = 0` — no ARQ result key is stored; no result key can block a later authorized retry enqueue;
- `max_tries = 1` — no ARQ automatic retry for these functions; ARQ infrastructure retry is disabled;
- job timeout is obtained from `settings.arq_job_timeout` (current configured/default: `300` seconds, `backend/app/config.py:63`); D5 does not introduce another hard-coded timeout value;
- provider-level retry remains owned by WP-REC-03D;
- user-authorized retry remains owned by D1 and D2;
- commit-before-enqueue recovery remains dependent on durable dispatch identity;
- stale-run detection and recovery policy remain owned by D6.

**D5 §7. Startup and shutdown context:**

The evidence-backed lifecycle model from the D5 reconnaissance is accepted:
- worker-wide resources suitable for safe reuse are initialized through the ARQ startup hook (`on_startup`) and stored in worker `ctx`;
- those resources are closed through the shutdown hook (`on_shutdown`);
- database session/transaction lifetime remains bounded per job and is not shared unsafely across jobs;
- resource construction and cleanup must preserve test seams for dependency substitution;
- no new global import-time database, Redis, or provider side effects are introduced.

The existing startup/shutdown hooks in `backend/app/worker.py:14-29` are the implementation locations. Each worker function creates its own session via `async_session_factory` (existing pattern in `backend/app/jobs/diagnostics.py` and `backend/app/jobs/ingestion.py`).

**D5 §8. Reconciler boundary:**

D5 registers no reconciler function. D5 adds no reconciler entry to `WorkerSettings.functions`, `WorkerSettings.cron_jobs`, another queue, another worker process, or an external scheduler.

D5 defines only the durable information required for future recovery:
- committed `run_id`;
- committed `dispatch_generation`;
- deterministic reconstruction of `workflow:{run_id}:{dispatch_generation}`;
- selection of the already defined start/retry dispatch path from committed workflow facts.

D6 remains exclusively responsible for:
- whether reconciliation uses ARQ, cron, another worker, a separate process, or an external scheduler;
- reconciler callable and registration;
- scheduling and trigger policy;
- interval;
- stale-run definition and threshold;
- reconciliation window;
- batch size;
- locking;
- recovery limits;
- escalation and observability policy.

No speculative reconciler callable is registered or reserved in D5.

**D5 §9. Required D5 test contract:**

The following test obligations are required to make D5 implementable. These tests are not written during this documentation pass.

1. Migration and model behavior:
   - existing rows receive generation `0`;
   - new runs start at generation `0`;
   - generation is non-null and cannot become negative;

2. Authorized retry:
   - one accepted D1 retry transition increments generation exactly once;
   - generation increment is atomic with `FAILED_* → PENDING`;
   - rejected or concurrent duplicate retry requests do not increment it;
   - enqueue failure does not allocate another generation;

3. Deterministic job ID:
   - repeated enqueue of one generation produces the same `_job_id`;
   - later authorized retry produces a different `_job_id`;
   - start and later retry cannot collide;
   - stale keys belonging to earlier generations cannot block a later generation;

4. Worker registration:
   - `workflow_start` and `workflow_retry` are both registered;
   - ARQ can resolve both functions;
   - no reconciler is registered (D5 boundary — superseded by D6 for the final 03F package; see D6 §4 and the D6 test contract below);
   - the configured queue remains `forgemind-tasks`;

5. Worker contract:
   - both workflow functions accept `run_id` as the only workflow-specific input;
   - matching queued and committed generations may proceed through the normal D1-controlled transition;
   - a stale-generation job does not execute provider work or regress state;

6. ARQ behavior:
   - `keep_result = 0`;
   - `max_tries = 1`;
   - timeout is sourced from `settings.arq_job_timeout`;
   - duplicate `enqueue_job` behavior is handled without treating `_job_id` as the database concurrency authority;

7. Lifecycle:
   - startup creates the required worker context;
   - shutdown releases resources;
   - job-scoped database resources have the correct lifetime;
   - test substitutes can be injected without import-time external connections;

8. Regression protection:
   - D1 database conditional-transition serialization remains authoritative;
   - D1 commit-before-enqueue, `409`, `503`, and reconciler dependency remain unchanged;
   - D2 authorization-before-lookup and `triggered_by` audit requirements remain unchanged;
   - D3 plan identifiers, `run_id` input, persistence rules, and exact start response remain unchanged;
   - D4 remains superseded;
   - D6 is resolved (see D6 contract below).

**D5 §10. Compatibility:**

D5 does not reopen or modify D1 retry transitions, same-`run_id` retry, duplicate-start idempotency, commit-before-enqueue, enqueue-failure `503`, reconciler recovery, D2 authentication/authorization/ownership, D3 plan-identifier contracts, or D4's superseded status. The `dispatch_generation` field is a dispatch-identity field, not a retry-count field. D5 is the separately approved decision that authorizes the new field and migration. D6 is resolved (see D6 contract below).

**D5 §9 note — D5 test contract superseded by D6:** The D5 §9 test obligation "no reconciler is registered" is a D5 boundary assertion only. D6 (resolved, DEC-042) supersedes this boundary for the final combined WP-REC-03F package. The final 03F implementation must register the D6 reconciler cron job and must include reconciler tests. See the D6 contract below (§2–§7, §10) and the D6 exit criteria in §14.

**D6 reconciler mechanism contract (Product Owner decision, 2026-08-10):**

**Decision D6 — Approve Option A: an ARQ cron job registered in the existing `WorkerSettings` provides periodic best-effort reconciliation of stuck PENDING rows. The following four sub-decisions are approved: stale timestamp, pagination, overlap, and dispatch target.**

D6 is resolved. WP-REC-03F implementation remains NOT AUTHORIZED — D6 resolution is a planning contract, not an implementation authorization.

**D6 §1. Stale timestamp — dedicated `pending_since` field:**

A dedicated `pending_since` timestamp column will be added to `WorkflowRun` during WP-REC-03F implementation. `created_at` must not be used for stale-candidate detection. `updated_at` must not be treated as the semantic stale-candidate timestamp.

- `pending_since` represents the beginning of the run's current continuous stay in PENDING.
- It is set when a new `WorkflowRun` is created in PENDING.
- It is reset to the current authoritative UTC timestamp whenever an authorized retry transition moves a run from `FAILED_*` back to PENDING.
- It is updated atomically with the PENDING transition and `dispatch_generation` increment.
- Ordinary reconciliation scans do not modify `pending_since`.
- Adding `pending_since` requires a future schema migration and ORM/schema updates during implementation.
- Migration/backfill behavior for existing rows must be defined in the future implementation plan.

**D6 §2. Pagination and bounded scan — keyset pagination:**

Each reconciliation occurrence processes pages using keyset pagination ordered by `pending_since ASC, id ASC`. Do not use OFFSET pagination. Do not repeatedly query only the first page within the same occurrence.

- The next page must continue strictly after the last processed tuple: `(pending_since, id)`.
- The scan stops when: no eligible candidates remain; the configured maximum-page limit is reached; or the configured time budget is exhausted.
- Partial completion is valid.
- Pagination or time-budget exhaustion must produce a structured observability event.
- Restart or cancellation may cause candidates to be scanned again and must remain harmless.
- No durable cross-occurrence cursor is approved.
- Therefore, do not claim absolute starvation freedom across an indefinitely persistent backlog larger than the per-occurrence bound. This is an accepted bounded-throughput operational risk.
- External monitoring may alert on repeated budget exhaustion or excessive candidate age.

Proposed configurable implementation defaults (not permanently fixed Product Owner decisions): page size 100; maximum pages per occurrence 5; scan time budget 50 seconds.

**D6 §3. Overlap policy — harmless overlap permitted:**

ARQ cron `unique=True` deduplicates the same scheduled occurrence across workers; it does not serialize different scheduled occurrences. Distinct reconciliation occurrences may overlap.

- Do not add PostgreSQL advisory locks, distributed locks, or another scan-wide serialization mechanism.
- Overlapping scans may attempt to enqueue the same candidate.
- Correctness must not depend on a reconciliation-row claim or SELECT lock.
- Deterministic workflow job identity provides queue-level same-generation deduplication while the relevant ARQ identity exists.
- The authoritative worker transition must atomically require: `state = PENDING` AND `dispatch_generation = queued generation`.
- Duplicate scans and duplicate enqueue attempts must be harmless.
- No exactly-once provider-execution guarantee is created.
- Reconciliation must not increment `dispatch_generation`.

**D6 §4. Dispatch target — generation-based selection:**

- `dispatch_generation = 0` → `workflow_start`.
- `dispatch_generation > 0` → `workflow_retry`.
- Reconciliation selects the target exclusively from the committed `dispatch_generation`.
- Reconciliation does not invent, increment, or repair the generation.
- The deterministic job identity remains: `workflow:{run_id}:{dispatch_generation}`.
- `run_id` remains the only workflow-specific function argument.
- Queued generation is recovered and validated from the ARQ job identity/context.
- Malformed, mismatched, or stale job identity must not authorize provider execution.

**D6 §5. Mandatory generation guard (D3/D5/D6 correctness contract):**

The generation guard is not an unresolved Product Owner choice. It is a mandatory correctness contract:

- The execution-authorizing database transition must match both PENDING state and the queued `dispatch_generation`.
- A pre-read followed by an UPDATE filtered only by `state` is insufficient.
- Failure to match the committed generation produces a safe stale-generation skip.
- Stale-generation execution must not invoke the provider or regress workflow state.

**D6 §6. Candidate predicate and enqueue outcomes:**

Candidate predicate: `state = PENDING` AND `pending_since <= authoritative UTC cutoff` AND `dispatch_generation` is present and valid.

Per-row enqueue outcomes:
- `enqueue_job` returns a `Job` instance → accepted (increment `accepted_count`).
- `enqueue_job` returns `None` → deduplicated/already present (increment `deduplicated_count`, do NOT increment `accepted_count`).
- Approved exception class → enqueue error (increment `enqueue_error_count`).
- Per-candidate isolation: one candidate's enqueue error must not prevent later candidates from being attempted, unless Redis is detected as globally unavailable and a documented fail-fast policy is selected.
- Do not log raw exception text. Record only safe exception type or approved bounded error code.

**D6 §7. Guarantee statement:**

- Durable database workflow state survives queue loss.
- Initial enqueue and later reconciliation enqueue are best-effort.
- Repeated recovery attempts continue while infrastructure is available.
- No exactly-once provider-execution claim is created.
- No recovery progress is guaranteed while PostgreSQL, Redis, or workers are unavailable.

**D6 §8. Scope boundary:**

- PENDING recovery only.
- Stuck RUNNING recovery remains outside D6 unless separately authorized.
- No implementation is authorized by this documentation change. WP-REC-03F implementation remains NOT STARTED / NOT AUTHORIZED.

**D6 §9. Proposed configuration defaults (not permanently fixed):**

- Reconciliation interval: 60 seconds.
- Stale threshold: 2 minutes.
- Page size: 100.
- Maximum pages per occurrence: 5.
- Scan time budget: 50 seconds.
- Cron timeout: 60 seconds.
- Age-event thresholds: warning 1 hour, error 24 hours, critical 7 days.

These are proposed implementation defaults, not approved architectural constants.

**D6 §10. Observability:**

The contract must include at least: scan/occurrence ID, cutoff, scanned count, accepted count, deduplicated count, enqueue-error count, skipped-invalid count, candidate age, run_id, dispatch_generation, selected target, safe error classification, scan duration, and pagination/budget exhaustion indicator. Do not promise "send alert" unless an alerting integration exists. External monitoring may alert on emitted structured events.

**D6 §11. Index requirement:**

The candidate predicate (`state = PENDING AND pending_since <= cutoff`) requires a future partial index: `CREATE INDEX ... ON workflow_runs (pending_since ASC, id ASC) WHERE state = 'PENDING'`. This index does not currently exist and must be added during WP-REC-03F implementation. Do not claim the query is indexed until the migration is applied.

**D6 §12. Compatibility:**

D6 does not reopen or modify D1 retry transitions, D2 authorization, D3 plan-identifier contracts, D4's superseded status, or D5 worker registration and dispatch identity. D6 defines the reconciler mechanism only. D6 resolution does not authorize WP-REC-03F implementation.

**4. Exact included scope:**
- `backend/app/models/workflow.py` — add the `dispatch_generation` column (non-null, non-negative integer, default `0`) per D5 §2; add the `pending_since` timestamp column per D6 §1 (set on creation, reset on `FAILED_* → PENDING` retry, updated atomically with `dispatch_generation` increment)
- `backend/alembic/versions/XXX_add_dispatch_generation.py` — one new Alembic migration adding both `workflow_runs.dispatch_generation` with `server_default=0` for existing rows per D5 §2 and `workflow_runs.pending_since` with a backfill policy for existing rows per D6 §1; the migration also creates the partial PENDING index `CREATE INDEX ... ON workflow_runs (pending_since ASC, id ASC) WHERE state = 'PENDING'` per D6 §11. (Alternatively, a justified migration split into two migrations may be used if the implementation plan provides rationale; the single-migration approach is the default.)
- `backend/app/ai/workflow/state_machine.py` — extend the existing transition table with the three approved retry transitions (`FAILED_PROVIDER → PENDING`, `FAILED_VALIDATION → PENDING`, `FAILED_INTERNAL → PENDING`) per the D1 retry contract above. No new state, no `RETRY_PENDING`, no ORM CHECK-constraint change. No CHECK-constraint migration is required for the state-machine extension.
- `backend/app/api/workflow.py` — extend with:
  - `POST /api/v1/workflow-runs` — requires `PRODUCTION_MANAGER` via `require_role({"PRODUCTION_MANAGER"})`; stores `current_user.username` in `triggered_by`; request body carries `plan_id` as a JSON string matching an exact `ProductionPlan.code` (see D3 contract); resolves the code to `ProductionPlan.id` UUID before `WorkflowRun` creation, returns `404 production_plan_not_found` if no plan matches; enqueues an ARQ job (`workflow_start`) identified by `run_id`, returns `202 Accepted` with `run_id`
  - `POST /api/v1/workflow-runs/{run_id}/retry` — requires authentication; permits run creator (`triggered_by` match) OR `PRODUCTION_MANAGER`; performs the atomic conditional `→ PENDING` transition (including atomic increment of `dispatch_generation` and atomic update of `pending_since` per D5 §1 and D6 §1), then enqueues ARQ retry job (`workflow_retry`) identified by `run_id`, returns `202 Accepted`; does not modify `triggered_by`
- `backend/app/ai/workflow/vertical.py` — vertical wiring executed **inside the ARQ worker**: risk engine → provider call → schema validation → recommendation persistence; distinguishes automatic retry (03D) from user-initiated retry (this package)
- `backend/app/ai/workflow/worker.py` — ARQ worker functions `workflow_start(ctx, run_id, ...)` and `workflow_retry(ctx, run_id, ...)`; the start-worker input is `run_id` (not an untyped `plan_id`); the worker obtains the persisted plan UUID and the exact plan code through the committed `WorkflowRun` row and its related `ProductionPlan` record (D3 §5); the worker validates `dispatch_generation` by comparing the queued generation (from ARQ job identity/context) with the committed `WorkflowRun.dispatch_generation` and skips stale-generation jobs per D5 §4; the execution-authorizing database transition must atomically require both `state = PENDING` AND `dispatch_generation = queued generation` per D6 §5; `_job_id` is constructed as `workflow:{run_id}:{dispatch_generation}` per D5 §3; idempotency-key handling; enqueue-failure path; state transitions; conditional-transition guards (`UPDATE ... WHERE state = :expected` with `RETURNING id`)
- `backend/app/ai/workflow/reconciler.py` (new) — ARQ cron reconciler function implementing D6 §2–§7: bounded keyset pagination ordered by `pending_since ASC, id ASC` (no OFFSET); candidate predicate `state = PENDING AND pending_since <= cutoff`; generation-based dispatch target selection (`dispatch_generation = 0` → `workflow_start`, `> 0` → `workflow_retry` per D6 §4); per-candidate failure isolation; accepted/deduplicated/error enqueue outcome classification per D6 §6; must not increment `dispatch_generation`; harmless overlap between distinct cron occurrences; no advisory locks or scan-wide serialization; observability without raw exception text per D6 §10
- `backend/app/worker.py` (extend — register `workflow_start` and `workflow_retry` in `WorkerSettings.functions` via `arq.func(...)` per D5 §5; register the D6 reconciler as an ARQ cron job in `WorkerSettings.cron_jobs` per D6 §4)
- `backend/app/schemas/workflow.py` — update with the start request schema (`plan_id: str`, `min_length=1`, exact `ProductionPlan.code` domain, no UUID parsing, no trimming, no regex — see D3) and the retry request schema; accepted response schema (`run_id`, `state`, `location`)
- Unit tests: `backend/tests/unit/test_workflow_api_start_retry.py` (HTTP-level: enqueue mocked, 202 response shape, idempotency, terminal-state check on retry, enqueue-failure 503, concurrent-retry 409)
- State-machine tests: `backend/tests/unit/test_workflow_state_machine.py` (extend existing tests to verify the three new retry transitions `FAILED_PROVIDER → PENDING`, `FAILED_VALIDATION → PENDING`, `FAILED_INTERNAL → PENDING` are accepted, `COMPLETED → PENDING` is rejected, and terminal-state behavior is updated for the three retry-eligible failed states)
- Worker tests: `backend/tests/unit/test_workflow_worker.py` (worker logic: full lifecycle, risk-persistence-on-provider-failure, duplicate-key handling, retry-from-terminal-only, conditional-transition guards, atomic `state = PENDING AND dispatch_generation = queued` authorization per D6 §5, stale-generation safe skip)
- Dispatch-generation tests: `backend/tests/unit/test_dispatch_generation.py` (D5 §9 test contract: migration/model, retry increment, deterministic job ID, stale-generation skip, `pending_since` set on creation, `pending_since` reset on retry, `pending_since` updated atomically with `dispatch_generation`)
- Reconciler tests: `backend/tests/unit/test_workflow_reconciler.py` (new — D6 §2–§7, §10: keyset pagination, candidate predicate, generation-based dispatch target, per-candidate failure isolation, accepted/deduplicated/error classification, `dispatch_generation` not incremented, harmless overlap, no raw exception text in observability, budget/pagination exhaustion observability, partial completion)
- Migration tests: verify `pending_since` backfill for existing rows, partial PENDING index creation, `dispatch_generation` `server_default=0`, non-negative constraint, and downgrade removes both columns and drops the index
- Integration tests: `backend/tests/integration/test_workflow_start_retry.py` (enqueue → worker → state transitions → recommendation persistence; retry → terminal-state check; enqueue failure → 503 without `run_id` exposed)

**5. Explicit exclusions:**
- No approval/audit/procurement logic (Phase 6 / WP-REC-04)
- No document access control or RAG integration (WP-REC-05)
- No new provider adapter logic (03A) and no unrelated state-machine redesign (03B) — **except** the three narrowly approved retry transitions (`FAILED_PROVIDER → PENDING`, `FAILED_VALIDATION → PENDING`, `FAILED_INTERNAL → PENDING`) added to the existing transition table in `backend/app/ai/workflow/state_machine.py` per the D1 retry contract below. This resolves reconnaissance contradiction **C2**: the WP-REC-03F retry requirement needed `FAILED_* → PENDING` transitions, but the former exclusion prohibited all new state-machine logic. C2 is resolved by permitting only these three approved transitions while continuing to prohibit unrelated state-machine redesign. No `RETRY_PENDING` state, no new state, no ORM CHECK-constraint change, and no other transition-table changes are introduced. The Alembic migration (D5 §2 + D6 §1/§11) adds the `dispatch_generation` and `pending_since` columns and the partial PENDING index; no CHECK-constraint migration is required.
- No automatic retry policy (03D — this package provides user-initiated retry only)
- No controlled write actions — no procurement task creation, no approval (Phase 6)
- No frontend changes (that is 03G)
- No modification to DEC-011 (ARQ + Redis) — DEC-011 is preserved as the accepted background-job mechanism
- No synchronous execution of risk calculation, provider call, validation, or persistence inside the HTTP request lifecycle

**6. Permitted repository areas:**
- `backend/app/models/workflow.py` (extend 03B — add `dispatch_generation` column per D5 §2; add `pending_since` timestamp column per D6 §1)
- `backend/alembic/versions/XXX_add_dispatch_generation.py` (new migration per D5 §2 and D6 §1 — adds `dispatch_generation`, `pending_since`, and partial PENDING index per D6 §11; or a justified migration split)
- `backend/app/ai/workflow/state_machine.py` (extend 03B — add three retry transitions only)
- `backend/app/api/workflow.py` (extend 03E)
- `backend/app/ai/workflow/vertical.py` (new)
- `backend/app/ai/workflow/worker.py` (new)
- `backend/app/ai/workflow/reconciler.py` (new — D6 reconciler function)
- `backend/app/worker.py` (extend — register `workflow_start` and `workflow_retry` in `WorkerSettings.functions` via `arq.func(...)` per D5 §5; register D6 reconciler in `WorkerSettings.cron_jobs` per D6 §4)
- `backend/app/schemas/workflow.py` (update)
- `backend/tests/unit/test_workflow_state_machine.py` (extend 03B tests — verify new retry transitions)
- `backend/tests/unit/test_workflow_api_start_retry.py` (new test)
- `backend/tests/unit/test_workflow_worker.py` (new test)
- `backend/tests/unit/test_dispatch_generation.py` (new test — D5 §9 test contract: migration/model, retry increment, deterministic job ID, stale-generation skip, `pending_since` behavior)
- `backend/tests/unit/test_workflow_reconciler.py` (new test — D6 §2–§7, §10 reconciler test contract)
- `backend/tests/integration/test_workflow_start_retry.py` (new test)

**7. Dependencies and predecessor gates:**
- WP-REC-03A complete (provider adapter)
- WP-REC-03B complete (workflow engine, state machine, and Recommendation model)
- WP-REC-03C complete (structured-output validation)
- WP-REC-03D complete (automatic provider retry/outage)
- WP-REC-03E complete (run detail API + recommendation retrieval API)

**8. Relevant Source-of-Truth requirements:**
- `01_PRODUCT_AND_MVP_SCOPE.md` §2 Golden Scenario steps 3–7: start analysis, deterministic risk, AI workflow, structured recommendation, UI display
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §2: "LLM is not the source of truth for arithmetic" — deterministic risk result is authoritative input to the workflow
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §6: structured recommendation schema — `"plan_id": "PLAN-2026-W31"` is the external plan identifier; D3 aligns the start request `plan_id` with this external identifier, not with the database UUID
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §8: "recommendation → draft action → approval request → human decision → procurement task → audit event" — no write action before approval (Phase 6)
- `04_ACCEPTANCE_TESTS.md` AT-013: "AI endpoint unavailable → risk engine result remains available, workflow shows failed AI step, UI does not freeze, user can retry" — AT-013 **backend clauses** PASS after 03F; UI clauses require 03G.
- `03_DEFINITION_OF_DONE.md` Gate C: "When model unavailable, system shows controlled failure state"
- DEC-004: deterministic business logic; LLM explains
- DEC-005: AI creates draft action only; write requires approval
- DEC-011: ARQ + Redis for background jobs (Accepted — **preserved, not modified**)
- DEC-012: HTTP polling (3s interval) for run progress

**9. Acceptance tests and additional unit/integration tests:**
- AT-013 backend clauses (PASS after 03F, pending all clauses verified): AI endpoint unavailable → risk engine result available, workflow shows failed AI step. All backend clauses verifiable: risk engine result persisted independently of provider call (03D backend + 03F worker); workflow shows failed AI step (03F worker transitions to `FAILED_PROVIDER`; 03E serves the trace). The UI clauses (non-freezing UI, user can retry in UI) require 03G.
- Additional unit tests (HTTP): start returns 202 with `run_id` (as `PRODUCTION_MANAGER`); start returns 403 for authenticated non-`PRODUCTION_MANAGER`; start returns 401 for unauthenticated; `triggered_by` is set to `current_user.username` on start; retry returns 202 only on eligible failed states (`FAILED_PROVIDER`, `FAILED_VALIDATION`, `FAILED_INTERNAL`) for run creator or `PRODUCTION_MANAGER`; retry on `COMPLETED` returns 409 (non-retryable terminal); retry on non-terminal (`RUNNING`, `AWAITING_VALIDATION`) returns 409; retry on `PENDING` returns 409; retry by non-creator/non-`PRODUCTION_MANAGER` returns 403; retry when `triggered_by IS NULL` by non-`PRODUCTION_MANAGER` returns 403; retry when `triggered_by IS NULL` by `PRODUCTION_MANAGER` returns 202; retry does not modify `triggered_by`; duplicate start with same idempotency key returns existing `run_id`; enqueue failure returns 503; concurrent retry — losing caller receives 409.
- Additional D3 unit tests (start-request `plan_id` validation): valid exact `ProductionPlan.code` accepted and resolves to the persisted `WorkflowRun.plan_id` UUID; missing `plan_id` returns 422; `plan_id: null` returns 422; JSON number/boolean/array/object `plan_id` returns 422; empty-string `plan_id` returns 422; whitespace-only `plan_id` returns 422; `plan_id` with leading or trailing whitespace returns 422; a syntactically valid UUID string is NOT resolved through `ProductionPlan.id` — it is looked up only as an exact `ProductionPlan.code` and returns 404 when no such code exists; unknown exact code returns 404 `production_plan_not_found` and creates no `WorkflowRun`, no state transition, no commit, and no ARQ enqueue; persisted `WorkflowRun.plan_id` is the resolved UUID; the start response remains exactly `{run_id, state, location}` with no `plan_id`; no trimming, case normalization, or `PLAN-*` regex is applied.
- Additional state-machine unit tests: `FAILED_PROVIDER → PENDING` accepted; `FAILED_VALIDATION → PENDING` accepted; `FAILED_INTERNAL → PENDING` accepted; `COMPLETED → PENDING` rejected (non-retryable terminal); `get_allowed_transitions` for the three failed states now includes `PENDING`; `get_allowed_transitions` for `COMPLETED` remains empty; `is_terminal` for the three failed states still returns `True` (terminal for ordinary execution); `TERMINAL_STATES` frozenset unchanged (the three failed states remain in it — retry is an explicit external action, not a polling/ordinary transition).
- Additional worker tests: full lifecycle enqueue → run → complete; provider failure after risk engine → risk result persisted + run marked `FAILED_PROVIDER`; retry from `FAILED_PROVIDER` → success; retry from `FAILED_VALIDATION` → success; ARQ duplicate delivery at worker level skipped (queue-level `_job_id` deduplication only; does not alter the retry endpoint's `409` behavior); enqueue failure → 503 (committed `PENDING` row remains, reconciler can recover); start enqueue failure → 503 (response does not expose `run_id`); worker retains database state guard (conditional `PENDING → RUNNING` UPDATE) before execution on a retried run.
- Additional integration tests: full start → run → complete lifecycle with recommendation persisted; start → provider outage → `FAILED_PROVIDER` → user retry via endpoint → success; start → invalid output → `FAILED_VALIDATION` → user retry; deterministic risk result queryable independently of provider outcome.

**10. Failure and rollback behavior:**
- Start API failure: 401 if unauthenticated, 403 if authenticated but not `PRODUCTION_MANAGER`, 422 if the request body `plan_id` is missing, null, non-string, empty, whitespace-only, or contains leading/trailing whitespace (D3), 404 `production_plan_not_found` if no `ProductionPlan.code` matches the exact request value (D3; the lookup occurs before any `WorkflowRun` creation, commit, or enqueue), 503 if ARQ enqueue fails, 500 on other internal error
- Retry API failure: 401 if unauthenticated, 403 if authenticated but neither run creator nor `PRODUCTION_MANAGER`, 409 if run not in an eligible failed state (including `COMPLETED`, `PENDING`, `RUNNING`, `AWAITING_VALIDATION`), 404 if run not found, 503 if ARQ enqueue fails (committed `PENDING` run remains for reconciler)
- Worker failure: exception in worker → run marked `FAILED_INTERNAL`; risk result (already persisted) remains queryable
- Concurrency: retry is serialized by the database conditional-transition rule (`UPDATE ... WHERE state = :expected RETURNING id`); exactly one concurrent caller wins the `→ PENDING` transition; losing concurrent callers receive `409 Conflict`. ARQ `_job_id` deduplication is queue-level only.
- No write actions created (by design — write actions are Phase 6)
- Rollback: revert feature branch; Alembic downgrade removes the `dispatch_generation` column (D5 §2), the `pending_since` column (D6 §1), and drops the partial PENDING index (D6 §11). No other database changes beyond 03B.

**11. Security and secrets constraints:**
- Start API requires `PRODUCTION_MANAGER` role via `require_role({"PRODUCTION_MANAGER"})` (D2); unauthenticated → 401; authenticated non-`PRODUCTION_MANAGER` → 403
- Start stores `current_user.username` in `WorkflowRun.triggered_by` on creation (D2)
- Retry API requires authentication; permitted for run creator (`current_user.username == triggered_by`) OR `PRODUCTION_MANAGER` (D2); unauthenticated → 401; authenticated non-creator/non-`PRODUCTION_MANAGER` → 403; when `triggered_by IS NULL`, only `PRODUCTION_MANAGER` may retry
- Retry does not modify or replace `triggered_by` (D2)
- Authorization is evaluated before the D1 conditional retry transition: unauthorized → 403 with no transition or enqueue; authorized but state-ineligible → 409; authorized concurrent loser → 409 (D2)
- No secrets in vertical wiring or API code
- Provider errors do not leak API keys or internal details to the client
- ARQ job payloads contain no secrets (risk engine input is deterministic data, no LLM tokens)

**12. Observability requirements:**
- Start API logs: correlation ID, user ID, `plan_code` (external request identifier), `plan_id` (persisted UUID after resolution), `run_id`, enqueue result
- Retry API logs: correlation ID, user ID, `run_id`, source state, enqueue result
- Worker logs: correlation ID, `run_id`, each step (risk engine, provider call, validation, persistence), enqueue duration, worker duration, final state; the worker obtains `plan_id` (UUID) and `plan_code` (string) from the committed `WorkflowRun` and its related `ProductionPlan` record — no duplicate queue argument
- Enqueue failure logged with correlation ID and cause

**13. Estimated size:** M (6-9 new/updated files, ~450-550 lines implementation + ~450-550 lines tests). Includes the state-machine transition-table extension and its tests. Split from the prior monolithic 03F into backend execution (this package, M) and frontend interaction (03G, S) because the original 03F bundled HTTP/worker/persistence/UI concerns into one review unit.

**14. Exit criteria:**
- `POST /api/v1/workflow-runs` requires `PRODUCTION_MANAGER` via `require_role({"PRODUCTION_MANAGER"})`; stores `current_user.username` in `triggered_by`; request body `plan_id` is a JSON string matching an exact `ProductionPlan.code` (D3); the endpoint resolves the code to `ProductionPlan.id` UUID and returns `404 production_plan_not_found` when no plan matches, before creating any `WorkflowRun`; request-schema validation and exact plan-code resolution occur synchronously; no provider call, risk calculation, recommendation-output/schema validation, or workflow execution occurs inside the HTTP request; persistence is limited to the initial durable `PENDING` run row after successful plan resolution; enqueues an ARQ job (`workflow_start`) identified by `run_id` and returns `202 Accepted` with `run_id` within API latency budget
- Start-request `plan_id` validation (D3): missing, null, non-string, empty, whitespace-only, and leading/trailing-whitespace values return 422; a syntactically valid UUID string is never resolved through `ProductionPlan.id` — it is looked up only as an exact `ProductionPlan.code` and returns 404 when no such code exists; no trimming, case normalization, or `PLAN-*` regex is applied; an unknown plan code creates no `WorkflowRun`, no state transition, no commit, and no ARQ enqueue
- `POST /api/v1/workflow-runs/{run_id}/retry` requires authentication; permits run creator (`triggered_by` match) OR `PRODUCTION_MANAGER`; performs one atomic conditional transition from an eligible failed state to `PENDING`, then enqueues an ARQ retry job and returns `202 Accepted`; rejects `COMPLETED`, `PENDING`, `RUNNING`, and `AWAITING_VALIDATION` with 409; does not modify `triggered_by`
- Unauthenticated start/retry returns 401; authenticated non-`PRODUCTION_MANAGER` start returns 403; authenticated non-creator/non-`PRODUCTION_MANAGER` retry returns 403; `triggered_by IS NULL` retry by non-`PRODUCTION_MANAGER` returns 403
- State machine transition table extended with `FAILED_PROVIDER → PENDING`, `FAILED_VALIDATION → PENDING`, `FAILED_INTERNAL → PENDING`; `COMPLETED` has no outgoing transition; no new state, no `RETRY_PENDING`, no ORM CHECK-constraint change. The Alembic migration (D5 §2 + D6 §1/§11) adds the `dispatch_generation` and `pending_since` columns and the partial PENDING index; no CHECK-constraint migration is required for the state-machine extension.
- State-machine unit tests verify the three new retry transitions are accepted, `COMPLETED → PENDING` is rejected, and `TERMINAL_STATES` frozenset is unchanged
- ARQ worker executes vertical wiring: risk engine → provider → validation → recommendation persistence
- Duplicate start requests return the existing `run_id` under the existing start idempotency contract without re-executing; retry requests use the D1 atomic state transition, and any caller that does not win an eligible `FAILED_* → PENDING` transition receives `409 Conflict`
- Enqueue failure returns `503 Service Unavailable` (no `run_id` exposed to the caller); the committed `PENDING` run remains durable. Recovery of stuck `PENDING` rows is handled by the D6 reconciler contract (resolved).
- Concurrent retry requests for the same `run_id` are serialized by the database conditional-transition rule; exactly one caller wins, losing callers receive `409 Conflict`
- Worker retains its database state guard (conditional `PENDING → RUNNING` UPDATE) before execution on a retried run
- Read and response contracts unchanged (D3 §4): `WorkflowRun.plan_id` remains a UUID FK; `WorkflowRunSchema.plan_id` and `WorkflowRunSummarySchema.plan_id` remain UUID; `RecommendationData.plan_id` remains the external string code; the start response remains exactly `{run_id, state, location}` with no `plan_id`
- Workflow job identified by `run_id` (D3 §5): the start-worker input is `run_id`, not an untyped `plan_id`; the worker obtains the persisted plan UUID and the exact plan code through the committed `WorkflowRun` row and its related `ProductionPlan` record; ARQ `_job_id` is constructed as `workflow:{run_id}:{dispatch_generation}` per D5 §3; `_job_id` remains queue-level deduplication only, as accepted by D1; D5 ensures that an earlier ARQ job record cannot prevent a later authorized retry of the same durable `run_id` from being enqueued — each authorized retry receives a new `dispatch_generation`, producing a different `_job_id`; `keep_result=0` ensures no result key blocks re-enqueue
- Dispatch identity (D5 §1): `WorkflowRun.dispatch_generation` is non-null, non-negative, initialized to `0` on run creation, incremented atomically in the same conditional UPDATE that performs the `FAILED_* → PENDING` retry transition; existing rows receive `0` via migration; the generation is durable and recoverable from the committed row; duplicate enqueue calls or reconciler passes do not increment it; every later authorized retry receives a different generation
- Worker stale-job validation (D5 §4): the worker compares the queued generation (from ARQ job identity/context) with the committed `WorkflowRun.dispatch_generation`; a stale-generation job does not execute provider work or regress state; no new state transition is introduced for stale-job behavior
- Worker registration (D5 §5): `workflow_start` and `workflow_retry` are registered in `WorkerSettings.functions` via `arq.func(...)` with `keep_result=0`, `max_tries=1`, and timeout from `settings.arq_job_timeout`; the D6 reconciler cron job is registered in `WorkerSettings.cron_jobs` per D6 §4; the queue remains `forgemind-tasks`; no additional worker role or queue is introduced
- Deterministic risk result persisted and queryable even when provider fails after the risk engine succeeds
- AT-013 backend clauses verifiable (risk engine result available, failed step visible in API trace)
- All backend unit, worker, and integration tests pass (including extended `test_workflow_state_machine.py`)
- Linter and type checks pass
- DEC-011 (ARQ + Redis) explicitly preserved; no new orchestration technology introduced
- `pending_since` column exists on `WorkflowRun` (D6 §1): set on creation, reset to current UTC timestamp on `FAILED_* → PENDING` retry, updated atomically with `dispatch_generation` increment; ordinary reconciliation scans do not modify it
- Partial PENDING index exists: `CREATE INDEX ... ON workflow_runs (pending_since ASC, id ASC) WHERE state = 'PENDING'` per D6 §11
- Migration/backfill for `pending_since` on existing rows is defined and applied per D6 §1
- D6 reconciler cron job registered in `WorkerSettings.cron_jobs` per D6 §4
- Reconciler uses bounded keyset pagination ordered by `pending_since ASC, id ASC`; no OFFSET pagination per D6 §2
- Reconciler candidate predicate: `state = PENDING AND pending_since <= authoritative UTC cutoff` per D6 §6
- Reconciler per-candidate failure isolation: one candidate's enqueue error does not prevent later candidates from being attempted per D6 §6
- Reconciler does not increment `dispatch_generation` per D6 §3
- Reconciler selects dispatch target from committed `dispatch_generation` (`0` → `workflow_start`, `> 0` → `workflow_retry`) per D6 §4
- Reconciler overlap is harmless; no advisory locks or scan-wide serialization per D6 §3
- Reconciler enqueue outcomes classified as accepted (`Job` instance), deduplicated (`None`), or error (approved exception class) per D6 §6
- Reconciler observability events emitted without raw exception text per D6 §10
- Reconciler budget or pagination exhaustion produces a structured observability event per D6 §2
- PENDING-only reconciliation scope; stuck-RUNNING recovery remains excluded per D6 §8
- No exactly-once provider-execution guarantee is claimed per D6 §7
- No recovery progress is guaranteed during PostgreSQL, Redis, or worker outages per D6 §7
- Reconciler tests pass (keyset pagination, candidate predicate, dispatch target selection, per-candidate isolation, enqueue classification, `dispatch_generation` not incremented, harmless overlap, observability without raw exception text, budget/pagination exhaustion)
- Migration tests pass (`pending_since` backfill, partial PENDING index creation, `dispatch_generation` `server_default=0`, non-negative constraint, downgrade removes both columns and drops the index)

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. Requires explicit Product Owner authorization.
---

### WP-REC-03G — Frontend Start/Retry UI Interaction

**1. Stable ID and title:** WP-REC-03G — Frontend Start/Retry UI Interaction

**2. Objective:** Add the frontend start/retry UI actions that complete AT-013's user-visible clauses: a "Start AI Analysis" button on the supply-risk detail page, a "Retry" button visible only when a run is in a terminal failure state, a non-freezing UI during long-running workflow execution, and polling-driven status updates until a terminal state is reached.

**3. Outcome type:** Complete user-visible increment (frontend half) — the reviewer can start a workflow, observe non-blocking progress, and retry a failed run. Together with 03F (backend), this package completes AT-013.

**4. Exact included scope:**
- `frontend/src/routes/supply-risk-detail.tsx` — update with "Start AI Analysis" button and "Retry" button (retry visible only when run is in a terminal failure state)
- `frontend/src/hooks/use-workflow-start.ts` — TanStack Query mutation hook for starting a workflow (POST to 03F's start endpoint)
- `frontend/src/hooks/use-workflow-retry.ts` — TanStack Query mutation hook for retrying a failed run (POST to 03F's retry endpoint)
- `frontend/src/routes/__tests__/supply-risk-detail-workflow.test.tsx` — frontend tests
- No backend changes; uses 03F's start/retry endpoints and 03E's polling endpoint

**5. Explicit exclusions:**
- No workflow start/retry API logic (that is 03F backend)
- No ARQ worker logic (that is 03F)
- No recommendation persistence (that is 03F's worker execution path using 03B's model)
- No read-only workflow-run detail UI (that is 03E)
- No approval center UI (that is Phase 6 / WP-REC-04D)
- No audit log UI (that is Phase 6 / WP-REC-04E)
- No automatic retry logic (that is 03D)
- No document access control or RAG integration (that is WP-REC-05)

**6. Permitted repository areas:**
- `frontend/src/routes/supply-risk-detail.tsx` (update)
- `frontend/src/hooks/use-workflow-start.ts` (new)
- `frontend/src/hooks/use-workflow-retry.ts` (new)
- `frontend/src/routes/__tests__/supply-risk-detail-workflow.test.tsx` (new test)

**7. Dependencies and predecessor gates:**
- WP-REC-03A complete (provider adapter — model metadata in UI)
- WP-REC-03B complete (workflow models — state used to drive button visibility)
- WP-REC-03C complete (validation results — failure display)
- WP-REC-03D complete (error/retry information — failure display)
- WP-REC-03E complete (run detail UI + polling endpoint extended by this package)
- WP-REC-03F must be complete before WP-REC-03G begins (start/retry API + ARQ worker — HTTP contract consumed by this package); WP-REC-03F implementation is currently NOT AUTHORIZED

**8. Relevant Source-of-Truth requirements:**
- `04_ACCEPTANCE_TESTS.md` AT-013 UI clauses: "UI does not freeze, user can retry" — PASS after 03G (combined with 03F backend)
- `01_PRODUCT_AND_MVP_SCOPE.md` §3.6: Workflow Run Details screen — start and retry actions
- DEC-012: HTTP polling (3s interval) for run progress
- FR-07: "Every workflow step must be traceable by correlation ID" (displayed via 03E's trace)

**9. Acceptance tests and additional unit/integration tests:**
- AT-013 UI clauses (PASS after 03G, pending all clauses verified): UI does not freeze during long-running workflow; user can click retry; retry button visible only when run is in terminal failure state; after retry, polling resumes and shows updated state.
- Additional frontend tests: "Start AI Analysis" button POSTs to 03F's start endpoint; "Retry" button POSTs to 03F's retry endpoint; "Retry" button hidden when run is not in a terminal failure state; polling starts after successful start/retry and stops at terminal state; loading, error, and non-freezing states implemented.

**10. Failure and rollback behavior:**
- Start API error surfaced in UI: error state with retryable message
- Retry API error surfaced in UI: error state with retryable message
- Polling timeout: UI shows "workflow still running" state; user may manually refresh
- No write actions created (by design — write actions are Phase 6)
- Rollback: revert feature branch; no database changes

**11. Security and secrets constraints:**
- Frontend uses existing authenticated TanStack Query client (03F's endpoints require authentication)
- Role-based access enforced on the backend (03F); frontend hides buttons the user cannot invoke
- No secrets in frontend code

**12. Observability requirements:**
- Frontend logs start/retry actions with correlation ID (from backend response)
- Polling activity logged via API correlation ID

**13. Estimated size:** S (3-4 new/updated files, ~150-250 lines implementation + ~150-200 lines tests)

**14. Exit criteria:**
- "Start AI Analysis" button POSTs to 03F's start endpoint and transitions UI to polling
- "Retry" button POSTs to 03F's retry endpoint and is visible only on terminal failure states
- Polling updates run status (DEC-012 approved approach)
- Loading, error, and non-freezing UI states implemented
- AT-013 UI clauses verifiable (non-freezing UI, user retry action visible)
- All frontend tests pass
- Linter and type checks pass

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. Requires explicit Product Owner authorization.
---

## 7. Acceptance-Test Mapping Summary

| AT | Description | Phase 5 Package(s) | PASS Point | Status After Phase 5 |
|----|-------------|---------------------|------------|------------------------|
| AT-007 | Document access control | WP-REC-05 only (NOT Phase 5) | After WP-REC-05 | NOT covered by Phase 5 |
| AT-008 | Structured output validation | WP-REC-03A + 03B + 03C + 03E + 03F | Validator clauses after 03C (unit-level); full PASS after 03F wires worker + 03E renders trace | PASS (after 03F + 03E) |
| AT-013 | Model outage | WP-REC-03A + 03D + 03E + 03F + 03G | After 03F + 03G (backend clauses after 03F; UI clauses require 03G) | PASS (after 03F + 03G) |

AT-009, AT-010, AT-011, AT-012 are Phase 6 (WP-REC-04) and are NOT covered by Phase 5. 03E provides a partial foundation for AT-012 (workflow trace visibility) but AT-012 is NOT PASS during Phase 5.

**RAG integration note:** Document access control (AT-007) and grounded retrieval with citations in the AI recommendation remain assigned to WP-REC-05. Phase 5 may call the retrieval service for context, but does not implement document access control or complete RAG integration. Phase 5 must not falsely claim AT-007 PASS.

---

## 8. Planning Quality Gate Checklist

| Criterion | Status |
|-----------|--------|
| No package is oversized | ✅ All packages are M or S; no L packages; 03F split into backend (M) + frontend (S) |
| Each package has independently reviewable scope | ✅ Each package has explicit included scope and exclusions |
| Each package can be reverted independently | ✅ Each package is a feature branch; migrations have downgrade paths |
| Tests map to AT requirements | ✅ AT-008 validator clauses after 03C (unit-level); AT-008 full PASS after 03F+03E (end-to-end); AT-013 after 03F+03G |
| No package depends on unauthorized Runtime separation | ✅ No package touches `scripts/agent-loop/` or `.agent-loop/`; zero runtime coupling |
| No implementation is described as already authorized | ✅ 03A, 03B, 03C, 03D, 03E are COMPLETE (merged); 03F and 03G say \"NOT AUTHORIZED\" in §15 |
| Exact first candidate identified but unauthorized | ✅ WP-REC-03A was the first candidate; COMPLETE (merged via PR #63); WP-REC-03B was the second candidate; COMPLETE (merged via PR #65). WP-REC-03C, 03D, 03E are now COMPLETE (merged via PRs #72, #73, #74). WP-REC-03F planning contracts D1-D3, D5, and D6 resolved; D4 superseded; implementation NOT AUTHORIZED. WP-REC-03G NOT AUTHORIZED. |
| Deterministic risk calculation is authoritative input | ✅ DEC-004 preserved; risk engine feeds workflow via 03F worker |
| Structured and schema-validated model output | ✅ 03C enforces SoT §6 schema; AT-008 validator clauses (unit-level) after 03C; full PASS after 03F+03E |
| Human approval before controlled writes | ✅ No write actions in Phase 5; approval is Phase 6 (WP-REC-04) |
| Complete audit traceability | ✅ Workflow steps and correlation IDs (03B); full audit events in Phase 6 |
| Graceful model/provider outage behavior | ✅ 03D (automatic backend retry) + 03F (ARQ worker, persistence) + 03E (trace) + 03G (UI non-freeze, user retry); AT-013 PASS after 03F + 03G |
| Synthetic-data-only policy | ✅ DEC-003 preserved; fake provider uses no real data |
| No runtime dependency on scripts/agent-loop | ✅ No package imports or depends on agent-loop code |
| No coupling to forgemind-agent-runtime | ✅ Runtime separation (SP-0B) is NOT AUTHORIZED and not required |
| AT-007 maps only to WP-REC-05 | ✅ AT-007 is NOT mapped to any Phase 5 package |
| AT-008 ownership clear | ✅ 03C owns validator (unit-level); 03F wires worker execution; 03E renders trace; full PASS after 03F+03E |
| AT-013 not PASS before full retry+UI | ✅ AT-013 PASS only after 03F + 03G (03D is backend-only; 03F is backend-only; 03G adds UI clauses) |
| Start/retry API has explicit package owner | ✅ 03F owns start/retry API + ARQ worker (backend half) |
| Recommendation UI has explicit package owner | ✅ 03E owns recommendation display; 03G adds start/retry UI actions |
| Recommendation persistence has explicit package owner | ✅ 03B owns SQLAlchemy Recommendation model and migration; 03C owns Pydantic wire schema; 03F's worker writes; 03E reads |
| Recommendation schema file ownership (N5) | ✅ `backend/app/schemas/recommendation.py` owned exclusively by 03C (Pydantic wire schema); 03B owns `backend/app/models/workflow.py` (SQLAlchemy ORM); no duplicate ownership |
| DB/ARQ delivery contract (N3) | ✅ 03F defines commit-then-enqueue order, conditional-transition rule for concurrency, durable dispatch identity (D5 `dispatch_generation`), and eventual-completion need; D6 reconciler contract resolved |
| DEC-013 gate appears exactly once, no 03A dependency | ✅ Gate has no dependency on 03A |
| DEC-011 (ARQ + Redis) explicitly preserved | ✅ 03F uses DEC-011's ARQ + Redis; DEC-011 not modified |
| Start/retry endpoints enqueue rather than execute inline | ✅ 03F start/retry enqueue ARQ jobs; worker owns long-running execution |
| Package sequence identical across all files | ✅ 03A → GATE → 03B → 03C → 03D → 03E → 03F → 03G in decomposition, ACTIVE_WORK, next_steps, PR description |

---

## 9. Architecture Invariants Preserved

The decomposition preserves these invariants from the Source of Truth:

1. **Deterministic risk calculation is authoritative input** (DEC-004, SoT §2): The risk engine output feeds the workflow via 03F's ARQ worker; the LLM never recalculates risks.
2. **Structured and schema-validated model output** (FR-06, SoT §6, AT-008): WP-REC-03C enforces the versioned recommendation schema.
3. **Human approval before controlled writes** (DEC-005, FR-08, AT-009): No write actions in Phase 5; procurement requires Phase 6 approval.
4. **Complete audit traceability** (FR-07, FR-09, AT-012): Workflow steps and correlation IDs (03B+03E); full audit events in Phase 6.
5. **Graceful model/provider outage behavior** (AT-013, Gate C): 03D (automatic backend retry) + 03F (ARQ worker, risk result persistence, retry endpoint) + 03E (trace display) + 03G (UI non-freeze, user retry) ensure deterministic results remain available and users can retry.
6. **Synthetic-data-only policy** (DEC-003): Fake provider uses no real data; all test data is synthetic.
7. **No runtime dependency on scripts/agent-loop**: No package imports or depends on agent-loop code.
8. **No coupling to forgemind-agent-runtime**: SP-0B is NOT AUTHORIZED and not required for any Phase 5 package.
9. **RAG integration assigned to WP-REC-05**: Document access control (AT-007) and grounded retrieval are NOT claimed by Phase 5.
10. **Background job mechanism is ARQ + Redis** (DEC-011, Accepted): 03F uses ARQ + Redis for workflow execution; DEC-011 is preserved, not modified. No other orchestration technology introduced.

---

## 10. Runtime Repository vs Agent Automation Distinction

The following distinction is preserved throughout this decomposition:

- **forgemind-agent-runtime** remains the planned second repository under the separately authorized Runtime-separation workflow (SP-0A approved Option C; SP-0B migration manifest READY but NOT AUTHORIZED).
- Creation of the `forgemind-agent-runtime` repository is currently **NOT AUTHORIZED**, but it is not postponed merely because agent automation is unavailable.
- **Activation/integration of real agent automation** is what remains deferred until it becomes available on general terms.
- Neither the second repository nor agent automation is a runtime dependency or blocker for ForgeMind Release 1.
- **SP-0B remains READY but NOT AUTHORIZED.**

No Phase 5 package depends on, creates, or activates agent automation or the second repository.

---

## 11. First Candidate Implementation Package

**WP-REC-03A — AI Provider Adapter (Chat/Reasoning)** is the first candidate implementation package.

**Rationale:**
- No predecessor implementation package or decision gate required
- Follows the proven embedding provider pattern (`embedding_provider.py`, `embedding_provider_factory.py`)
- Reuses existing config (`openai_api_key`, `openai_chat_model`, `llm_timeout_seconds`, `llm_max_retries`)
- Unblocks WP-REC-03B (after GATE-1) and 03C/03D/03E/03F
- No database changes (lowest risk, easiest to revert)

**Status: COMPLETE — merged via PR #63 (2026-08-09).** The first candidate implementation package is complete.

**WP-REC-03B (Workflow/State-Machine Foundation) is also COMPLETE — merged via PR #65 at `fc48aed557d20f516cf46fe94175ce2d22c61dba` (2026-08-09).** The second candidate implementation package is complete.

**Phase 5 implementation status (2026-08-10 reconciliation):** WP-REC-03A through WP-REC-03E are COMPLETE (merged via PRs #63, #65, #72, #73, #74 respectively). WP-REC-03F planning contracts D1-D3, D5, and D6 are resolved; D4 superseded. WP-REC-03F implementation is NOT AUTHORIZED pending explicit Product Owner authorization. WP-REC-03G is NOT AUTHORIZED.

---

## 12. Summary of NOT AUTHORIZED Items

| Item | Status |
|------|--------|
| WP-REC-03A (AI provider adapter) | COMPLETE — merged via PR #63 |
| WP-REC-03-DEC-GATE-1 (DEC-013 decision) | SATISFIED — DEC-013 Accepted (2026-08-09); merged via PR #64 |
| WP-REC-03B (workflow/state-machine) | COMPLETE — merged via PR #65 |
| WP-REC-03C (structured-output validation) | COMPLETE — merged via PR #72 |
| WP-REC-03D (automatic provider retry/outage — backend) | COMPLETE — merged via PR #73 |
| WP-REC-03E (workflow-run detail + recommendation UI) | COMPLETE — merged via PR #74 |
| WP-REC-03F (backend workflow start/retry API + ARQ worker) | NOT AUTHORIZED |
| WP-REC-03G (frontend start/retry UI interaction) | NOT AUTHORIZED |
| WP-REC-03 implementation (as a whole) | MIXED LIFECYCLE — WP-REC-03A through WP-REC-03E are COMPLETE (merged via PRs #63, #65, #72, #73, #74); WP-REC-03F implementation is NOT AUTHORIZED (planning contracts D1-D3, D5, and D6 resolved, D4 superseded); WP-REC-03G is NOT AUTHORIZED |
| SP-0B (Runtime migration manifest) | READY but NOT AUTHORIZED |
| Creation of forgemind-agent-runtime | NOT AUTHORIZED |
| Activation of agent automation | NOT AUTHORIZED (deferred until available on general terms) |
| DEC-013 acceptance | ACCEPTED (Product Owner accepted 2026-08-09; merged via PR #64) |
| DEC-015 permanent decision | NOT AUTHORIZED (Proposed, deferred) |
