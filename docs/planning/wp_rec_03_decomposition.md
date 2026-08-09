# WP-REC-03-DEC — MVP Phase 5 Controlled Decomposition

**Status:** PLANNING PACKAGE — lifecycle/status corrections applied 2026-08-09
**Date:** 2026-08-08 (corrected 2026-08-08; status-synced 2026-08-09)
**Baseline:** `origin/main` @ `fc48aed557d20f516cf46fe94175ce2d22c61dba`
**Authorizes:** This document authorizes planning and decomposition only.
**Does NOT authorize:** Any implementation code, test changes, dependency installation, migrations, or merge.

**Lifecycle summary (2026-08-09 status sync):**
- WP-REC-03A: COMPLETE — merged via PR #63
- WP-REC-03-DEC-GATE-1 (DEC-013): SATISFIED — DEC-013 Accepted (2026-08-09), merged via PR #64
- WP-REC-03B: COMPLETE — merged via PR #65 at `fc48aed557d20f516cf46fe94175ce2d22c61dba`
- WP-REC-03C through 03G: NOT AUTHORIZED — implementation sequence paused before 03C pending WP-STRAT-01 and WP-ARCH-01
- Feature development is temporarily paused after WP-REC-03B. The content, priority, and authorization of WP-REC-03C will be reassessed only after WP-STRAT-01 (Product Strategy and Release Replanning) and WP-ARCH-01 (Architecture Hygiene and Agent Onboarding) are complete.

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

7. **No workflow/approval/audit/procurement_task models exist.** `backend/app/models/` contains no workflow, approval, audit, or procurement task model. `backend/app/ai/workflow/` does not exist. All Phase 5 work is greenfield.

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

The design uses a **database-first, conditional-transition** delivery contract. The `workflow_runs` row with its unique state-transition constraint is the durability anchor; the ARQ enqueue is a best-effort notification. Recovery is achieved by a periodic reconciler that detects stuck `PENDING` rows.

| Concern | Behavior |
|---------|----------|
| **Commit-then-enqueue order** | The start endpoint **first** inserts the `workflow_runs` row with `state=PENDING` and commits (single-row transaction). **Then** it enqueues the ARQ job `workflow_start`. The committed `run_id` is returned to the caller. |
| **Worker starting before commit** | Cannot occur by construction — the ARQ enqueue happens only after commit. Even if Redis/ARQ were instantaneous, the worker dequeues only after enqueue, which is post-commit. |
| **Enqueue failure after the run exists (N3 scenario)** | If the ARQ enqueue raises (Redis unavailable, timeout, etc.), the endpoint returns `503 Service Unavailable` **without** `run_id` in the response body. The `PENDING` row is committed and durable but not exposed to the caller. Recovery relies entirely on the **reconciler** (below), which detects the orphaned `PENDING` row and re-enqueues. |
| **Process crash between commit and enqueue** | Identical to the enqueue-failure scenario. The `PENDING` row is committed; no job was enqueued. The caller receives no `run_id`. The reconciler detects the stuck row within one tick and re-enqueues. |
| **Durable recovery / reconciliation** | A periodic **reconciler** runs on a fixed interval (e.g. every 60 s) — implemented as a separate ARQ scheduled job or a worker bootstrap task. It queries `workflow_runs` where `state=PENDING` AND `created_at < now() - reconciliation_window` (e.g. 2 minutes, to avoid racing with an in-flight enqueue). For each stuck row, it re-enqueues `workflow_start` (idempotent by `run_id`). The reconciler logs every re-enqueue for auditability. |
| **Duplicate delivery** | ARQ jobs are keyed by a stable `run_id`-derived idempotency key. If a job with that key is already queued (ARQ dedup at enqueue time), the second enqueue is a no-op. The worker additionally guards execution via the database conditional-transition rule (below), so even if ARQ somehow delivered the job twice, only the first execution would successfully transition the state. |
| **Concurrent retries for the same run** | Serialized by an **explicit database conditional-transition rule** — NOT by the idempotency key alone. The retry endpoint requires the run to be in a terminal failure state (`FAILED_PROVIDER`, `FAILED_VALIDATION`, `FAILED_INTERNAL`) and uses a SQL `UPDATE ... WHERE id = :run_id AND state IN (:terminal_states)` with `RETURNING id`. Exactly one concurrent caller receives a non-empty result and is allowed to enqueue; all other concurrent callers receive an empty result and get `409 Conflict`. This is the serialization primitive — independent of the idempotency key. The ARQ worker performs the same conditional transition when starting execution: `UPDATE ... WHERE id = :run_id AND state = :expected_state` — only one worker proceeds; all others observe an empty result and exit silently. |
| **Idempotency key role** | Deduplicates enqueue requests with the same `run_id` at the ARQ level (prevents duplicate jobs in the queue). Does **not** serialize concurrent requests with different keys — that is the database conditional-transition rule's job. |
| **DEC-011 preservation** | No new orchestration technology is introduced. ARQ + Redis (Accepted in DEC-011) is the sole background-job mechanism. |

**Eventual-completion guarantee:** The contract does **not** claim "no `PENDING` row without a job" (that would be false — the row is committed before the enqueue). A `PENDING` row without a job is an expected transient state that the reconciler is specifically designed to resolve. The contract guarantees: every `PENDING` row is either (a) being enqueued right now, or (b) will be re-enqueued by the reconciler within one tick. Therefore every committed `PENDING` row eventually reaches a terminal state.


**4. Exact included scope:**
- `backend/app/api/workflow.py` — extend with:
  - `POST /api/v1/workflow-runs` — enqueues ARQ job, returns `202 Accepted` with `run_id`
  - `POST /api/v1/workflow-runs/{run_id}/retry` — enqueues ARQ retry job, returns `202 Accepted`
- `backend/app/ai/workflow/vertical.py` — vertical wiring executed **inside the ARQ worker**: risk engine → provider call → schema validation → recommendation persistence; distinguishes automatic retry (03D) from user-initiated retry (this package)
- `backend/app/ai/workflow/worker.py` — ARQ worker functions `workflow_start(ctx, plan_id, ...)` and `workflow_retry(ctx, run_id, ...)`; idempotency-key handling; enqueue-failure path; state transitions; conditional-transition guards (`UPDATE ... WHERE state = :expected` with `RETURNING id`)
- `backend/app/ai/workflow/reconciler.py` — periodic reconciler that detects stuck `PENDING` rows (created_at older than reconciliation window) and re-enqueues `workflow_start` jobs (idempotent by `run_id`); implemented as a scheduled ARQ task or worker bootstrap hook
- `backend/app/schemas/workflow.py` — update with start/retry request schemas (`plan_id`) and accepted response schema (`run_id`, `state`, `location`)
- Unit tests: `backend/tests/unit/test_workflow_api_start_retry.py` (HTTP-level: enqueue mocked, 202 response shape, idempotency, terminal-state check on retry, enqueue-failure 503)
- Worker tests: `backend/tests/unit/test_workflow_worker.py` (worker logic: full lifecycle, risk-persistence-on-provider-failure, duplicate-key handling, retry-from-terminal-only, conditional-transition guards)
- Reconciler tests: `backend/tests/unit/test_workflow_reconciler.py` (reconciler detects stuck PENDING rows, re-enqueues idempotently, respects reconciliation window)
- Integration tests: `backend/tests/integration/test_workflow_start_retry.py` (enqueue → worker → state transitions → recommendation persistence; retry → terminal-state check; enqueue failure → 503 without run_id, reconciler re-enqueues stuck PENDING)

**5. Explicit exclusions:**
- No approval/audit/procurement logic (Phase 6 / WP-REC-04)
- No document access control or RAG integration (WP-REC-05)
- No new provider adapter or state machine logic (03A/03B)
- No automatic retry policy (03D — this package provides user-initiated retry only)
- No controlled write actions — no procurement task creation, no approval (Phase 6)
- No frontend changes (that is 03G)
- No modification to DEC-011 (ARQ + Redis) — DEC-011 is preserved as the accepted background-job mechanism
- No synchronous execution of risk calculation, provider call, validation, or persistence inside the HTTP request lifecycle

**6. Permitted repository areas:**
- `backend/app/api/workflow.py` (extend 03E)
- `backend/app/ai/workflow/vertical.py` (new)
- `backend/app/ai/workflow/worker.py` (new)
- `backend/app/ai/workflow/reconciler.py` (new)
- `backend/app/schemas/workflow.py` (update)
- `backend/tests/unit/test_workflow_api_start_retry.py` (new test)
- `backend/tests/unit/test_workflow_worker.py` (new test)
- `backend/tests/unit/test_workflow_reconciler.py` (new test)
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
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §8: "recommendation → draft action → approval request → human decision → procurement task → audit event" — no write action before approval (Phase 6)
- `04_ACCEPTANCE_TESTS.md` AT-013: "AI endpoint unavailable → risk engine result remains available, workflow shows failed AI step, UI does not freeze, user can retry" — AT-013 **backend clauses** PASS after 03F; UI clauses require 03G.
- `03_DEFINITION_OF_DONE.md` Gate C: "When model unavailable, system shows controlled failure state"
- DEC-004: deterministic business logic; LLM explains
- DEC-005: AI creates draft action only; write requires approval
- DEC-011: ARQ + Redis for background jobs (Accepted — **preserved, not modified**)
- DEC-012: HTTP polling (3s interval) for run progress

**9. Acceptance tests and additional unit/integration tests:**
- AT-013 backend clauses (PASS after 03F, pending all clauses verified): AI endpoint unavailable → risk engine result available, workflow shows failed AI step. All backend clauses verifiable: risk engine result persisted independently of provider call (03D backend + 03F worker); workflow shows failed AI step (03F worker transitions to `FAILED_PROVIDER`; 03E serves the trace). The UI clauses (non-freezing UI, user can retry in UI) require 03G.
- Additional unit tests (HTTP): start returns 202 with `run_id`; retry returns 202 only on terminal failure states; retry on non-terminal returns 409; duplicate start with same idempotency key returns existing `run_id`; enqueue failure returns 503.
- Additional worker tests: full lifecycle enqueue → run → complete; provider failure after risk engine → risk result persisted + run marked `FAILED_PROVIDER`; retry from `FAILED_PROVIDER` → success; retry from `FAILED_VALIDATION` → success; duplicate key at worker level skipped; enqueue failure → 503, no run row created.
- Additional integration tests: full start → run → complete lifecycle with recommendation persisted; start → provider outage → `FAILED_PROVIDER` → user retry via endpoint → success; start → invalid output → `FAILED_VALIDATION` → user retry; deterministic risk result queryable independently of provider outcome.

**10. Failure and rollback behavior:**
- Start API failure: 400 if plan not found, 401 if unauthenticated, 503 if ARQ enqueue fails, 500 on other internal error
- Retry API failure: 409 if run not in terminal failure state, 404 if run not found, 503 if ARQ enqueue fails
- Worker failure: exception in worker → run marked `FAILED_INTERNAL`; risk result (already persisted) remains queryable
- Concurrency: retry is idempotent per idempotency key; concurrent retry requests for the same run are serialized via the database conditional-transition rule (`UPDATE ... WHERE state IN (:terminal_states)`) — only one caller enqueues, others receive `409 Conflict`
- Reconciler failure: if the reconciler fails to re-enqueue, the next tick retries; stuck rows are logged for operational visibility
- No write actions created (by design — write actions are Phase 6)
- Rollback: revert feature branch; no database changes beyond 03B

**11. Security and secrets constraints:**
- Start/retry APIs require authentication (existing `get_current_user` dependency)
- Role-based access: only Production Manager can start workflow runs; only the run creator or authorized roles can retry
- No secrets in vertical wiring or API code
- Provider errors do not leak API keys or internal details to the client
- ARQ job payloads contain no secrets (risk engine input is deterministic data, no LLM tokens)

**12. Observability requirements:**
- Start API logs: correlation ID, user ID, plan_id, run_id, enqueue result
- Retry API logs: correlation ID, user ID, run_id, source state, enqueue result
- Worker logs: correlation ID, run_id, each step (risk engine, provider call, validation, persistence), enqueue duration, worker duration, final state
- Enqueue failure logged with correlation ID and cause

**13. Estimated size:** M (5-7 new/updated files, ~400-500 lines implementation + ~400-500 lines tests). Split from the prior monolithic 03F into backend execution (this package, M) and frontend interaction (03G, S) because the original 03F bundled HTTP/worker/persistence/UI concerns into one review unit.

**14. Exit criteria:**
- `POST /api/v1/workflow-runs` enqueues an ARQ job and returns `202 Accepted` with `run_id` within API latency budget (no provider call, no risk calculation, no validation, no persistence beyond `PENDING` row inside the HTTP request)
- `POST /api/v1/workflow-runs/{run_id}/retry` enqueues an ARQ retry job and returns `202 Accepted`; rejects non-terminal states with `409 Conflict` via the database conditional-transition rule
- ARQ worker executes vertical wiring: risk engine → provider → validation → recommendation persistence
- Duplicate start/retry requests return the same `run_id` without re-executing (idempotency key)
- Enqueue failure returns `503 Service Unavailable` (no `run_id` exposed); the reconciler detects the orphaned `PENDING` row and re-enqueues within one tick
- Concurrent retry requests for the same `run_id` are serialized by the database conditional-transition rule — only one caller receives a non-empty `RETURNING` result and enqueues; others receive `409 Conflict`
- Reconciler runs periodically (e.g. every 60 s), detects `PENDING` rows older than the reconciliation window, and re-enqueues `workflow_start` (idempotent by `run_id`)
- Deterministic risk result persisted and queryable even when provider fails after the risk engine succeeds
- AT-013 backend clauses verifiable (risk engine result available, failed step visible in API trace)
- All backend unit, worker, reconciler, and integration tests pass
- Linter and type checks pass
- DEC-011 (ARQ + Redis) explicitly preserved; no new orchestration technology introduced

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
- WP-REC-03F complete (start/retry API + ARQ worker — HTTP contract consumed by this package)

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
| No implementation is described as already authorized | ✅ 03A and 03B are COMPLETE in §15 (merged); 03C–03G say \"NOT AUTHORIZED\" in §15 |
| Exact first candidate identified but unauthorized | ✅ WP-REC-03A was the first candidate; COMPLETE (merged via PR #63); WP-REC-03B was the second candidate; COMPLETE (merged via PR #65). Next technical candidate WP-REC-03C is NOT AUTHORIZED and implementation is paused pending WP-STRAT-01 and WP-ARCH-01 |
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
| DB/ARQ delivery contract (N3) | ✅ 03F defines commit-then-enqueue order, conditional-transition rule for concurrency, reconciler for stuck PENDING rows, explicit eventual-completion guarantee via reconciliation |
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

**Next technical candidate:** WP-REC-03C (Structured-Output Validation). However, implementation is **paused** — the Product Owner has directed that before WP-REC-03C, the project will proceed through WP-STRAT-01 (Product Strategy and Release Replanning) and WP-ARCH-01 (Architecture Hygiene and Agent Onboarding). The content, priority, and authorization of WP-REC-03C will be reassessed only after those packages are complete. WP-REC-03C remains **NOT AUTHORIZED**. The "next candidate" designation here reflects technical sequence only, not authorization.

---

## 12. Summary of NOT AUTHORIZED Items

| Item | Status |
|------|--------|
| WP-REC-03A (AI provider adapter) | COMPLETE — merged via PR #63 |
| WP-REC-03-DEC-GATE-1 (DEC-013 decision) | SATISFIED — DEC-013 Accepted (2026-08-09); merged via PR #64 |
| WP-REC-03B (workflow/state-machine) | COMPLETE — merged via PR #65 |
| WP-REC-03C (structured-output validation) | NOT AUTHORIZED (implementation paused pending WP-STRAT-01 and WP-ARCH-01) |
| WP-REC-03D (automatic provider retry/outage — backend) | NOT AUTHORIZED (implementation paused) |
| WP-REC-03E (workflow-run detail + recommendation UI) | NOT AUTHORIZED (implementation paused) |
| WP-REC-03F (backend workflow start/retry API + ARQ worker) | NOT AUTHORIZED (implementation paused) |
| WP-REC-03G (frontend start/retry UI interaction) | NOT AUTHORIZED (implementation paused) |
| WP-REC-03 implementation (as a whole) | NOT AUTHORIZED — implementation sequence paused before 03C pending WP-STRAT-01 and WP-ARCH-01 |
| SP-0B (Runtime migration manifest) | READY but NOT AUTHORIZED |
| Creation of forgemind-agent-runtime | NOT AUTHORIZED |
| Activation of agent automation | NOT AUTHORIZED (deferred until available on general terms) |
| DEC-013 acceptance | ACCEPTED (Product Owner accepted 2026-08-09; merged via PR #64) |
| DEC-015 permanent decision | NOT AUTHORIZED (Proposed, deferred) |
