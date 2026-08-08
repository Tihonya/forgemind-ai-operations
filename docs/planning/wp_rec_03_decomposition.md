# WP-REC-03-DEC — MVP Phase 5 Controlled Decomposition

**Status:** PLANNING PACKAGE — NOT AUTHORIZED FOR IMPLEMENTATION
**Date:** 2026-08-08 (corrected 2026-08-08)
**Baseline:** `origin/main` @ `a859c0d0fbee721ad0ea44a00682370d3da9355f`
**Authorizes:** This document authorizes planning and decomposition only.
**Does NOT authorize:** Any implementation code, test changes, dependency installation, migrations, or merge.

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

1. **The provisional five-package structure is insufficient.** The provisional list covers backend infrastructure but does not explicitly provide a workflow-start API, wiring from deterministic risk results into workflow input, recommendation persistence and presentation, or user-initiated retry. An additional package (WP-REC-03F) is required to deliver the user-facing vertical slice.

2. **The provisional order 03C before 03D is confirmed as correct.** The provisional list already places structured-output validation (03C) before model outage handling (03D). This order is preserved: 03C defines the `FAILED_VALIDATION` failure path, which 03D's outage handler must also handle as a non-retryable failure. No reordering was needed; the original order was already correct.

3. **A decision gate must precede WP-REC-03B.** DEC-013 (workflow orchestration: custom state machine vs LangGraph) is **Proposed**, not **Accepted**. The assessment recommended a custom state machine, but the Product Owner has not accepted this. WP-REC-03B cannot begin until DEC-013 is Accepted. A decision gate (WP-REC-03-DEC-GATE-1) is recorded before 03B.

4. **DEC-013 may be resolved at any time.** The gate has no dependency on WP-REC-03A completion. The Product Owner may accept DEC-013 before, during, or after 03A implementation. The only constraint is that DEC-013 must be Accepted before WP-REC-03B implementation begins.

5. **DEC-015 (state management) does not block Phase 5.** DEC-015 is Proposed for the permanent frontend state-library choice, but the Phase 1 approach (React hooks + TanStack Query) was approved by the Product Owner. WP-REC-03E (recommendation UI) and 03F (retry UI) can proceed with the approved Phase 1 approach. The permanent DEC-015 decision can be deferred until application-state complexity demonstrates a need. No gate is required for 03E or 03F.

6. **Existing embedding provider pattern is reusable evidence.** `backend/app/services/embedding_provider.py` defines an ABC interface with `OpenAIEmbeddingProvider` and `FakeEmbeddingProvider` adapters, plus `embedding_provider_factory.py` with environment-aware validation. WP-REC-03A (AI provider adapter for chat/reasoning) can follow this proven pattern.

7. **No workflow/approval/audit/procurement_task models exist.** `backend/app/models/` contains no workflow, approval, audit, or procurement task models. `backend/app/ai/workflow/` does not exist. All Phase 5 work is greenfield.

8. **Config already has OpenAI settings.** `backend/app/config.py` defines `openai_api_key`, `openai_api_base`, `openai_chat_model`, `openai_embedding_model`, `llm_timeout_seconds`, `llm_max_retries`, `ai_rate_limit_per_minute`. The adapter will reuse these settings, not invent new ones.

9. **RAG integration remains assigned to WP-REC-05.** Phase 5 does not complete document access control (AT-007) or grounded retrieval. The workflow may call the retrieval service for context, but document access control and full RAG integration with citations in the AI recommendation are WP-REC-05 scope. Phase 5 must not falsely claim AT-007 PASS.

---

## 4. Corrected Decomposition and Package Order

| Order | ID | Title | Size | Depends On | AT Coverage | Outcome Type |
|-------|----|-------|------|------------|-------------|--------------|
| 1 | WP-REC-03A | AI provider adapter (chat/reasoning) | M | — | — | Internal architectural enablement |
| Gate | WP-REC-03-DEC-GATE-1 | DEC-013 decision gate | — | — (no dependency on 03A) | Unblocks 03B | Decision |
| 2 | WP-REC-03B | Workflow/state-machine foundation | M | 03A + GATE-1 | — | Internal architectural enablement |
| 3 | WP-REC-03C | Structured-output validation | S | 03A + 03B | AT-008 (PASS after 03C, pending all clauses verified) | Internal architectural enablement |
| 4 | WP-REC-03D | Automatic provider retry/outage (backend) | S | 03A + 03B + 03C | — (backend retry only; AT-013 NOT PASS) | Internal architectural enablement |
| 5 | WP-REC-03E | Workflow-run detail + recommendation UI | S | 03A + 03B + 03C + 03D | FR-07, §3.6 (workflow trace); partial foundation for AT-012 | Externally observable demo progress |
| 6 | WP-REC-03F | Workflow start/retry API + vertical wiring | M | 03A + 03B + 03C + 03D + 03E | AT-013 (PASS after 03F, pending all clauses verified) | Complete user-visible increment |

**Phase 5 exit criteria:** AT-008 PASS (after 03C), AT-013 PASS (after 03F), model response validated, deterministic numbers preserved, user-visible recommendation and retry available (`07_ROADMAP.md` Phase 5).

**AT-013 PASS requires:** backend automatic retry (03D), user-initiated workflow retry API (03F), failed-step visibility in UI (03E+03F), non-freezing UI behavior (03E+03F), and user retry action (03F). AT-013 is NOT PASS after 03D alone.

---

## 5. Architecture Decision Gates

### GATE-1: DEC-013 — Workflow orchestration

**Current status:** Proposed (not Accepted). Approved by: Pending.

**Decision:** Use custom explicit state machine (no LangGraph).

**Why a gate is required:** WP-REC-03B (workflow/state-machine foundation) cannot be implemented without knowing whether to use a custom state machine or LangGraph. The choice affects the entire `backend/app/ai/workflow/` architecture.

**Timing:** DEC-013 may be resolved at any time. It has no dependency on WP-REC-03A or any other implementation package. The Product Owner may accept it before, during, or after 03A. The only constraint: DEC-013 must be Accepted before WP-REC-03B implementation begins.

**Gate requirement:** The Product Owner must accept, reject, or modify DEC-013 before WP-REC-03B implementation begins. This acceptance must be recorded in `forgemind_project_source_of_truth/08_DECISION_LOG.md` with status **Accepted**. Acceptance of DEC-013 remains separately unauthorized until Product Owner approval.

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
- `08_DECISION_LOG.md` DEC-013: "Use custom explicit state machine (no LangGraph)" — Status: Proposed

**9. Acceptance tests:** N/A (decision gate, not implementation)

**10. Failure and rollback behavior:** If the Product Owner rejects the custom state machine, the decomposition plan must be revised before 03B.

**11. Security and secrets constraints:** N/A

**12. Observability requirements:** N/A

**13. Estimated size:** S (decision recording only)

**14. Exit criteria:**
- DEC-013 status is **Accepted** in `08_DECISION_LOG.md`
- `Approved by: Product Owner` recorded

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. This gate requires explicit Product Owner decision. Acceptance of DEC-013 remains separately unauthorized until Product Owner approval.

---

### WP-REC-03B — Workflow/State-Machine Foundation

**1. Stable ID and title:** WP-REC-03B — Workflow/State-Machine Foundation

**2. Objective:** Implement the workflow run lifecycle (create → run → complete/fail) with an explicit state machine, workflow run/steps models, and correlation ID propagation.

**3. Outcome type:** Internal architectural enablement — no direct user-visible demo progress. The backend can create and persist workflow runs with steps and correlation IDs.

**4. Exact included scope:**
- `backend/app/models/workflow.py` — `WorkflowRun`, `WorkflowStep` SQLAlchemy models
- `backend/alembic/versions/XXX_workflow_models.py` — Alembic migration
- `backend/app/ai/workflow/__init__.py`
- `backend/app/ai/workflow/state_machine.py` — explicit state machine (states: PENDING, RUNNING, AWAITING_VALIDATION, COMPLETED, FAILED_VALIDATION, FAILED_PROVIDER, FAILED_INTERNAL; transitions defined as a dict/frozenset)
- `backend/app/ai/workflow/engine.py` — `WorkflowEngine` class: creates run, executes steps, calls `ChatProvider.complete()`, propagates correlation ID, records steps
- `backend/app/schemas/workflow.py` — Pydantic schemas for workflow run/step
- Unit tests: `backend/tests/unit/test_workflow_state_machine.py`, `backend/tests/unit/test_workflow_engine.py`
- Integration tests: `backend/tests/integration/test_workflow_run_lifecycle.py`

**5. Explicit exclusions:**
- No structured-output schema validation (that is 03C)
- No automatic retry logic (that is 03D)
- No user-facing API endpoints (that is 03F)
- No frontend changes (that is 03E)
- No approval/audit/procurement models (those are Phase 6 / WP-REC-04)

**6. Permitted repository areas:**
- `backend/app/models/workflow.py` (new)
- `backend/app/ai/workflow/` (new directory)
- `backend/app/schemas/workflow.py` (new)
- `backend/alembic/versions/XXX_workflow_models.py` (new migration)
- `backend/tests/unit/test_workflow_*.py` (new tests)
- `backend/tests/integration/test_workflow_*.py` (new tests)

**7. Dependencies and predecessor gates:**
- WP-REC-03A complete (provider adapter must exist)
- WP-REC-03-DEC-GATE-1 complete (DEC-013 must be Accepted)

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

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. Requires explicit Product Owner authorization.

---

### WP-REC-03C — Structured-Output Validation

**1. Stable ID and title:** WP-REC-03C — Structured-Output Validation

**2. Objective:** Implement versioned JSON-schema validation for AI model output. Invalid output is rejected with `FAILED_VALIDATION` status; no write actions are created.

**3. Outcome type:** Internal architectural enablement — no direct user-visible demo progress. The system can validate AI output, but no user-facing endpoint exposes it yet.

**4. Exact included scope:**
- `backend/app/ai/workflow/schema_validator.py` — validates model output against the structured recommendation schema (§6 of SoT 02)
- `backend/app/schemas/recommendation.py` — Pydantic models matching the recommendation schema (schema_version, run_id, plan_id, risks[], sources[])
- `backend/app/ai/workflow/prompts.py` — versioned prompt template (system prompt instructing the model to return the schema)
- Unit tests: `backend/tests/unit/test_recommendation_schema.py`, `backend/tests/unit/test_schema_validator.py`

**5. Explicit exclusions:**
- No automatic retry or outage handling (that is 03D)
- No user-facing API endpoints (that is 03F)
- No frontend changes (that is 03E)
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
- AT-008 (PASS after 03C, pending all clauses verified): given a model returns an invalid structure → run gets `FAILED_VALIDATION`, no write actions, error visible in trace. All clauses of AT-008 must be verifiable: invalid structure → `FAILED_VALIDATION` status; no write actions created; error visible in trace. The "error visible in trace" clause requires 03E (trace UI) to be fully verifiable; AT-008 is conditionally PASS after 03C for the backend clauses and fully PASS after 03E renders the trace.
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
- Recommendation Pydantic schema matches SoT §6
- Validator accepts valid output, rejects invalid output
- Versioned prompt template created
- AT-008 backend clauses verifiable (FAILED_VALIDATION on invalid output, no write actions)
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

**5. Explicit exclusions:**
- No workflow start API (that is 03F)
- No user-initiated retry API or retry UI action (that is 03F)
- No approval center UI (that is Phase 6 / WP-REC-04D)
- No audit log UI (that is Phase 6 / WP-REC-04E)
- No automatic retry or outage logic (that is 03D — this package only displays errors)
- No new workflow engine logic (that is 03B — this package only reads and displays)
- No document access control or RAG integration (that is WP-REC-05)

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

### WP-REC-03F — Workflow Start/Retry API + Vertical Wiring

**1. Stable ID and title:** WP-REC-03F — Workflow Start/Retry API + Vertical Wiring

**2. Objective:** Implement the workflow-start API, user-initiated retry API, and vertical wiring that delivers the complete user-visible Phase 5 slice: Production Manager starts analysis → deterministic risks feed the workflow → AI runs → validated recommendation is persisted → progress and failures are visible → user may retry a failed AI run → no controlled write before Phase 6.

**3. Outcome type:** Complete user-visible increment — a reviewer can start a workflow, see it run, view the recommendation, and retry on failure. This is the package that makes Phase 5 produce visible AI-assisted value.

**4. Exact included scope:**
- `backend/app/api/workflow.py` — extend with:
  - `POST /api/v1/workflow-runs` — start a new workflow for a production plan (authenticated; accepts `plan_id`; resolves plan, calls risk engine for deterministic result, creates workflow run, calls provider, validates output, persists recommendation)
  - `POST /api/v1/workflow-runs/{run_id}/retry` — retry a failed workflow run (authenticated; allowed only from terminal failure states: `FAILED_PROVIDER`, `FAILED_VALIDATION`, `FAILED_INTERNAL`; idempotent per run; concurrency-safe)
- `backend/app/ai/workflow/vertical.py` — vertical wiring: orchestrates risk engine → provider call → schema validation → recommendation persistence; distinguishes automatic retry (03D) from user-initiated retry (this package)
- `backend/app/schemas/workflow.py` — update with start/retry request and response schemas
- `frontend/src/routes/supply-risk-detail.tsx` — update with "Start AI Analysis" button and "Retry" button (retry visible only when run is in a terminal failure state)
- `frontend/src/hooks/use-workflow-start.ts` — TanStack Query mutation hook for starting a workflow
- `frontend/src/hooks/use-workflow-retry.ts` — TanStack Query mutation hook for retrying a failed run
- Frontend tests: `frontend/src/routes/__tests__/supply-risk-detail-workflow.test.tsx`
- Integration tests: `backend/tests/integration/test_workflow_start_retry.py`

**5. Explicit exclusions:**
- No approval/audit/procurement logic (Phase 6 / WP-REC-04)
- No document access control or RAG integration (WP-REC-05)
- No new provider adapter or state machine logic (03A/03B)
- No automatic retry policy (03D — this package provides user-initiated retry only)
- No controlled write actions — no procurement task creation, no approval (Phase 6)

**6. Permitted repository areas:**
- `backend/app/api/workflow.py` (extend 03E)
- `backend/app/ai/workflow/vertical.py` (new)
- `backend/app/schemas/workflow.py` (update)
- `frontend/src/routes/supply-risk-detail.tsx` (update)
- `frontend/src/hooks/use-workflow-start.ts` (new)
- `frontend/src/hooks/use-workflow-retry.ts` (new)
- `frontend/src/routes/__tests__/supply-risk-detail-workflow.test.tsx` (new test)
- `backend/tests/integration/test_workflow_start_retry.py` (new test)

**7. Dependencies and predecessor gates:**
- WP-REC-03A complete (provider adapter)
- WP-REC-03B complete (workflow engine and state machine)
- WP-REC-03C complete (structured-output validation)
- WP-REC-03D complete (automatic provider retry/outage)
- WP-REC-03E complete (run detail + recommendation UI to extend with start/retry actions)

**8. Relevant Source-of-Truth requirements:**
- `01_PRODUCT_AND_MVP_SCOPE.md` §2 Golden Scenario steps 3–7: start analysis, deterministic risk, AI workflow, structured recommendation, UI display
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §2: "LLM is not the source of truth for arithmetic" — deterministic risk result is authoritative input to the workflow
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §8: "recommendation → draft action → approval request → human decision → procurement task → audit event" — no write action before approval (Phase 6)
- `04_ACCEPTANCE_TESTS.md` AT-013: "AI endpoint unavailable → risk engine result remains available, workflow shows failed AI step, UI does not freeze, user can retry"
- `03_DEFINITION_OF_DONE.md` Gate C: "When model unavailable, system shows controlled failure state"
- DEC-004: deterministic business logic; LLM explains
- DEC-005: AI creates draft action only; write requires approval

**9. Acceptance tests and additional unit/integration tests:**
- AT-013 (PASS after 03F, pending all clauses verified): AI endpoint unavailable → risk engine result available, workflow shows failed AI step, UI does not freeze, user can retry. All clauses verifiable: risk engine result available (03D backend + 03F vertical wiring); workflow shows failed AI step (03E+03F UI); UI does not freeze (03E+03F loading/error states); user can retry (03F retry API + UI action).
- Additional unit tests: start API creates run with correct plan_id, retry API rejects non-terminal states, retry API idempotency, concurrency safety
- Additional integration tests: full start → run → complete lifecycle; start → provider outage → FAILED_PROVIDER → user retry → success; start → invalid output → FAILED_VALIDATION → user retry
- Additional frontend tests: "Start AI Analysis" button creates workflow; "Retry" button visible only on failed runs; loading state during workflow; non-freezing UI during long-running workflow; recommendation displayed after completion

**10. Failure and rollback behavior:**
- Start API failure: 400 if plan not found, 401 if unauthenticated, 500 on internal error
- Retry API failure: 409 if run not in terminal failure state, 404 if run not found
- Concurrency: retry is idempotent per run_id; concurrent retry requests for the same run are serialized
- No write actions created (by design — write actions are Phase 6)
- Rollback: revert feature branch; no database changes beyond 03B

**11. Security and secrets constraints:**
- Start/retry APIs require authentication (existing `get_current_user` dependency)
- Role-based access: only Production Manager can start workflow runs; only the run creator or authorized roles can retry
- No secrets in vertical wiring or API code
- Provider errors do not leak API keys or internal details to the client

**12. Observability requirements:**
- Start API logs: correlation ID, user ID, plan_id, run_id
- Retry API logs: correlation ID, user ID, run_id, source state, attempt number
- Vertical wiring logs: correlation ID, run_id, each step (risk engine, provider call, validation, persistence)

**13. Estimated size:** M (5-7 new/updated files, ~400-500 lines implementation + ~300-400 lines tests)

**14. Exit criteria:**
- `POST /api/v1/workflow-runs` starts a workflow for a production plan
- `POST /api/v1/workflow-runs/{run_id}/retry` retries a failed run (terminal failure states only, idempotent, concurrency-safe)
- Vertical wiring: risk engine → provider → validation → recommendation persistence
- Frontend "Start AI Analysis" and "Retry" buttons functional
- Loading, error, and non-freezing UI states implemented
- AT-013 all clauses verifiable (risk engine result available, failed step visible, UI non-freeze, user retry)
- All backend and frontend tests pass
- Linter and type checks pass

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. Requires explicit Product Owner authorization.

---

## 7. Acceptance-Test Mapping Summary

| AT | Description | Phase 5 Package(s) | PASS Point | Status After Phase 5 |
|----|-------------|---------------------|------------|------------------------|
| AT-007 | Document access control | WP-REC-05 only (NOT Phase 5) | After WP-REC-05 | NOT covered by Phase 5 |
| AT-008 | Structured output validation | WP-REC-03A + 03B + 03C + 03E | Backend clauses after 03C; fully verifiable after 03E renders trace | PASS (after 03E) |
| AT-013 | Model outage | WP-REC-03A + 03D + 03E + 03F | After 03F (all clauses: backend retry, failed-step UI, non-freeze, user retry) | PASS (after 03F) |

AT-009, AT-010, AT-011, AT-012 are Phase 6 (WP-REC-04) and are NOT covered by Phase 5. 03E provides a partial foundation for AT-012 (workflow trace visibility) but AT-012 is NOT PASS during Phase 5.

**RAG integration note:** Document access control (AT-007) and grounded retrieval with citations in the AI recommendation remain assigned to WP-REC-05. Phase 5 may call the retrieval service for context, but does not implement document access control or complete RAG integration. Phase 5 must not falsely claim AT-007 PASS.

---

## 8. Planning Quality Gate Checklist

| Criterion | Status |
|-----------|--------|
| No package is oversized | ✅ All packages are M or S; no L packages |
| Each package has independently reviewable scope | ✅ Each package has explicit included scope and exclusions |
| Each package can be reverted independently | ✅ Each package is a feature branch; migrations have downgrade paths |
| Tests map to AT requirements | ✅ AT-008 (after 03C+03E), AT-013 (after 03F); unit/integration tests specified per package |
| No package depends on unauthorized Runtime separation | ✅ No package touches `scripts/agent-loop/` or `.agent-loop/`; zero runtime coupling |
| No implementation is described as already authorized | ✅ Every package says "NOT AUTHORIZED" in §15 |
| Exact first candidate identified but unauthorized | ✅ WP-REC-03A is the first candidate; NOT AUTHORIZED |
| Deterministic risk calculation is authoritative input | ✅ DEC-004 preserved; risk engine feeds workflow via 03F vertical wiring |
| Structured and schema-validated model output | ✅ 03C enforces SoT §6 schema; AT-008 |
| Human approval before controlled writes | ✅ No write actions in Phase 5; approval is Phase 6 (WP-REC-04) |
| Complete audit traceability | ✅ Workflow steps and correlation IDs (03B); full audit events in Phase 6 |
| Graceful model/provider outage behavior | ✅ 03D (automatic backend retry) + 03E+03F (UI non-freeze, user retry); AT-013 PASS after 03F |
| Synthetic-data-only policy | ✅ DEC-003 preserved; fake provider uses no real data |
| No runtime dependency on scripts/agent-loop | ✅ No package imports or depends on agent-loop |
| No coupling to forgemind-agent-runtime | ✅ Runtime separation (SP-0B) is NOT AUTHORIZED and not required |
| AT-007 maps only to WP-REC-05 | ✅ AT-007 is NOT mapped to any Phase 5 package |
| AT-013 not PASS before full retry+UI | ✅ AT-013 PASS only after 03F (03D is backend-only) |
| Start/retry API has explicit package owner | ✅ 03F owns start/retry API + vertical wiring |
| Recommendation UI has explicit package owner | ✅ 03E owns recommendation display; 03F adds start/retry actions |
| DEC-013 gate appears exactly once, no 03A dependency | ✅ Gate has no dependency on 03A |
| Package sequence identical across all files | ✅ 03A → GATE → 03B → 03C → 03D → 03E → 03F in decomposition, ACTIVE_WORK, next_steps, PR description |

---

## 9. Architecture Invariants Preserved

The decomposition preserves these invariants from the Source of Truth:

1. **Deterministic risk calculation is authoritative input** (DEC-004, SoT §2): The risk engine output feeds the workflow via 03F vertical wiring; the LLM never recalculates risks.
2. **Structured and schema-validated model output** (FR-06, SoT §6, AT-008): WP-REC-03C enforces the versioned recommendation schema.
3. **Human approval before controlled writes** (DEC-005, FR-08, AT-009): No write actions in Phase 5; procurement requires Phase 6 approval.
4. **Complete audit traceability** (FR-07, FR-09, AT-012): Workflow steps and correlation IDs (03B+03E); full audit events in Phase 6.
5. **Graceful model/provider outage behavior** (AT-013, Gate C): 03D (automatic backend retry) + 03E+03F (UI non-freeze, user retry) ensure deterministic results remain available and users can retry.
6. **Synthetic-data-only policy** (DEC-003): Fake provider uses no real data; all test data is synthetic.
7. **No runtime dependency on scripts/agent-loop**: No package imports or depends on agent-loop code.
8. **No coupling to forgemind-agent-runtime**: SP-0B is NOT AUTHORIZED and not required for any Phase 5 package.
9. **RAG integration assigned to WP-REC-05**: Document access control (AT-007) and grounded retrieval are NOT claimed by Phase 5.

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

**Status: NOT AUTHORIZED.** This package requires explicit Product Owner authorization before implementation begins.

---

## 12. Summary of NOT AUTHORIZED Items

| Item | Status |
|------|--------|
| WP-REC-03A (AI provider adapter) | NOT AUTHORIZED |
| WP-REC-03-DEC-GATE-1 (DEC-013 decision) | NOT AUTHORIZED |
| WP-REC-03B (workflow/state-machine) | NOT AUTHORIZED |
| WP-REC-03C (structured-output validation) | NOT AUTHORIZED |
| WP-REC-03D (automatic provider retry/outage — backend) | NOT AUTHORIZED |
| WP-REC-03E (workflow-run detail + recommendation UI) | NOT AUTHORIZED |
| WP-REC-03F (workflow start/retry API + vertical wiring) | NOT AUTHORIZED |
| WP-REC-03 implementation (as a whole) | NOT AUTHORIZED |
| SP-0B (Runtime migration manifest) | READY but NOT AUTHORIZED |
| Creation of forgemind-agent-runtime | NOT AUTHORIZED |
| Activation of agent automation | NOT AUTHORIZED (deferred until available on general terms) |
| DEC-013 acceptance | NOT AUTHORIZED (Proposed, pending PO) |
| DEC-015 permanent decision | NOT AUTHORIZED (Proposed, deferred) |
