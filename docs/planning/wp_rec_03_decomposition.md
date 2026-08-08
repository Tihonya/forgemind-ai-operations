# WP-REC-03-DEC — MVP Phase 5 Controlled Decomposition

**Status:** PLANNING PACKAGE — NOT AUTHORIZED FOR IMPLEMENTATION
**Date:** 2026-08-08
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

## 2. Validation Against Current Repository Evidence

The provisional decomposition in the SP-1 assessment (§18, line 1074) proposed:

| Provisional ID | Title | Size |
|----------------|-------|------|
| WP-REC-03A | AI provider adapter | M |
| WP-REC-03B | Workflow engine | M |
| WP-REC-03C | Structured output validation | S |
| WP-REC-03D | Model outage handling | S |
| WP-REC-03E | Workflow run detail UI | S |

### Validation findings

1. **The provisional decomposition is confirmed as structurally sound.** The five packages map cleanly to Phase 5 deliverables in `07_ROADMAP.md` (provider adapter, versioned prompt, structured output, workflow trace, error handling, model outage behavior) and to the AT requirements (AT-008, AT-013).

2. **Reordering is required.** The provisional list places structured output validation (03C) before model outage handling (03D). Repository evidence shows that structured output validation depends on the provider adapter returning a response, and model outage handling depends on the provider adapter's error hierarchy. Both 03C and 03D depend on 03A, but 03C should precede 03D because outage handling must validate the structured-output failure path (AT-008: `FAILED_VALIDATION`), not just the provider-unavailable path. The corrected order is: 03A → 03B → 03C → 03D → 03E.

3. **A decision gate must precede WP-REC-03B.** DEC-013 (workflow orchestration: custom state machine vs LangGraph) is **Proposed**, not **Accepted**. The assessment recommended a custom state machine, but the Product Owner has not accepted this. WP-REC-03B cannot begin until DEC-013 is resolved. A decision gate (WP-REC-03-DEC-GATE-1) is inserted before 03B.

4. **DEC-015 (state management) does not block Phase 5 backend work.** DEC-015 is Proposed for the permanent frontend state-library choice, but the Phase 1 approach (React hooks + TanStack Query) was approved by the Product Owner. WP-REC-03E (workflow run detail UI) can proceed with the approved Phase 1 approach. The permanent DEC-015 decision can be deferred until application-state complexity demonstrates a need. No gate is required for 03E.

5. **Existing embedding provider pattern is reusable evidence.** `backend/app/services/embedding_provider.py` defines an ABC interface with `OpenAIEmbeddingProvider` and `FakeEmbeddingProvider` adapters, plus `embedding_provider_factory.py` with environment-aware validation. WP-REC-03A (AI provider adapter for chat/reasoning) can follow this proven pattern.

6. **No workflow/approval/audit/procurement_task models exist.** `backend/app/models/` contains no workflow, approval, audit, or procurement task models. `backend/app/ai/workflow/` does not exist. All Phase 5 work is greenfield.

7. **Config already has OpenAI settings.** `backend/app/config.py` defines `openai_api_key`, `openai_api_base`, `openai_chat_model`, `openai_embedding_model`, `llm_timeout_seconds`, `llm_max_retries`, `ai_rate_limit_per_minute`. The adapter will reuse these settings, not invent new ones.

---

## 3. Corrected Decomposition and Package Order

| Order | ID | Title | Size | Depends On | AT Coverage |
|-------|----|-------|------|------------|-------------|
| Gate | WP-REC-03-DEC-GATE-1 | DEC-013 decision gate | — | 03A complete | Unblocks 03B |
| 1 | WP-REC-03A | AI provider adapter (chat/reasoning) | M | — | AT-013 (partial: provider unavailable) |
| Gate | WP-REC-03-DEC-GATE-1 | DEC-013 acceptance | — | 03A | Unblocks 03B |
| 2 | WP-REC-03B | Workflow/state-machine foundation | M | 03A + GATE-1 | AT-008 (partial: run lifecycle) |
| 3 | WP-REC-03C | Structured-output validation | S | 03A + 03B | AT-008 (complete) |
| 4 | WP-REC-03D | Model-outage and failure handling | S | 03A + 03B + 03C | AT-013 (complete) |
| 5 | WP-REC-03E | Workflow-run detail API + UI | S | 03A + 03B + 03C + 03D | AT-007 (partial: workflow trace) |

**Phase 5 exit criteria:** AT-008 PASS, AT-013 PASS, model response validated, deterministic numbers preserved (`07_ROADMAP.md` Phase 5).

---

## 4. Architecture Decision Gates

### GATE-1: DEC-013 — Workflow orchestration

**Current status:** Proposed (not Accepted). Approved by: Pending.

**Decision:** Use custom explicit state machine (no LangGraph).

**Why a gate is required:** WP-REC-03B (workflow/state-machine foundation) cannot be implemented without knowing whether to use a custom state machine or LangGraph. The choice affects the entire `backend/app/ai/workflow/` architecture.

**Gate requirement:** The Product Owner must accept, reject, or modify DEC-013 before WP-REC-03B implementation begins. This acceptance must be recorded in `forgemind_project_source_of_truth/08_DECISION_LOG.md` with status **Accepted**.

**If accepted (custom state machine):** WP-REC-03B proceeds as specified below.

**If rejected (LangGraph chosen instead):** WP-REC-03B scope changes — LangGraph dependency added, architecture differs. The decomposition plan must be revised before 03B implementation.

**If modified:** The Product Owner's modification is authoritative; the plan must be updated.

### DEC-015 — State management

**Current status:** Proposed (permanent choice). Phase 1 approach (React hooks + local state, no Zustand) approved by Product Owner.

**Why no gate is required for Phase 5:** WP-REC-03E (workflow run detail UI) can use the approved Phase 1 approach (TanStack Query for server state, local component state for UI state). The permanent state-library decision does not block Phase 5 deliverables. The decision can be revisited when application-state complexity demonstrates a need.

**Recommendation:** Defer DEC-015 permanent decision until after Phase 6, when the approval center and audit log UI may create sufficient state complexity to justify a state library.

---

## 5. Package Specifications

Each package below specifies the 15 required attributes.

---

### WP-REC-03A — AI Provider Adapter (Chat/Reasoning)

**1. Stable ID and title:** WP-REC-03A — AI Provider Adapter (Chat/Reasoning)

**2. Objective:** Implement an OpenAI-compatible chat/reasoning provider adapter with a deterministic fake provider for testing, following the proven embedding provider pattern.

**3. User-visible or architectural outcome:** The backend can call an OpenAI-compatible chat model to generate structured recommendations. In test/dev, a deterministic fake provider returns canned responses without network calls.

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
- No model outage handling beyond exception hierarchy (that is 03D)
- No API endpoints exposing the provider (that is 03E)
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
- AT-013 (partial): provider-unavailable path — when the OpenAI endpoint is unreachable, `TransientChatProviderError` is raised; this exception will be caught by 03D's outage handler
- Additional unit tests: factory environment-aware validation, fake provider determinism, OpenAI provider construction with config, exception hierarchy correctness, timeout configuration, retry configuration

**10. Failure and rollback behavior:**
- Provider construction failure: `ChatProviderConfigurationError` raised at startup, application fails fast
- Transient API error: `TransientChatProviderError` raised to caller (workflow engine in 03B will handle retry)
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

**3. User-visible or architectural outcome:** The workflow engine architecture is determined and recorded as Accepted in the Decision Log.

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
- WP-REC-03A complete (provider adapter must exist so the workflow engine has something to call)

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

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. This gate requires explicit Product Owner decision.

---

### WP-REC-03B — Workflow/State-Machine Foundation

**1. Stable ID and title:** WP-REC-03B — Workflow/State-Machine Foundation

**2. Objective:** Implement the workflow run lifecycle (create → run → complete/fail) with an explicit state machine, workflow run/steps models, and correlation ID propagation.

**3. User-visible or architectural outcome:** A workflow run can be created, executed through defined states, and persisted with steps and correlation IDs. The state machine is explicit and debuggable.

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
- No model outage retry logic (that is 03D)
- No API endpoints (that is 03E)
- No frontend changes
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
- AT-008 (partial): workflow run lifecycle — when the model returns an invalid structure, the run transitions to `FAILED_VALIDATION` (the validation itself is 03C, but the state transition is 03B)
- Additional unit tests: state machine transition correctness (all valid/invalid transitions), workflow run creation, step recording, correlation ID propagation, concurrent run safety
- Additional integration tests: run lifecycle with real database (create → run → complete), failed run persistence

**10. Failure and rollback behavior:**
- Invalid state transition: `StateMachineError` raised, run marked `FAILED_INTERNAL`
- Provider error: run marked `FAILED_PROVIDER` (transient) or `FAILED_INTERNAL` (permanent) — retry logic is 03D
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

**3. User-visible or architectural outcome:** The system validates AI model output against the versioned recommendation schema (`02_SYSTEM_BEHAVIOR_AND_DATA.md` §6). Invalid output is visible in the workflow trace as `FAILED_VALIDATION`.

**4. Exact included scope:**
- `backend/app/ai/workflow/schema_validator.py` — validates model output against the structured recommendation schema (§6 of SoT 02)
- `backend/app/schemas/recommendation.py` — Pydantic models matching the recommendation schema (schema_version, run_id, plan_id, risks[], sources[])
- `backend/app/ai/workflow/prompts.py` — versioned prompt template (system prompt instructing the model to return the schema)
- Unit tests: `backend/tests/unit/test_recommendation_schema.py`, `backend/tests/unit/test_schema_validator.py`

**5. Explicit exclusions:**
- No model outage handling (that is 03D)
- No API endpoints (that is 03E)
- No frontend changes
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
- AT-008 (complete): given a model returns an invalid structure → run gets `FAILED_VALIDATION`, no write actions, error visible in trace
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
- AT-008 test passes (FAILED_VALIDATION on invalid output, no write actions, error visible)
- All unit tests pass
- Linter and type checks pass

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. Requires explicit Product Owner authorization.

---

### WP-REC-03D — Model-Outage and Failure Handling

**1. Stable ID and title:** WP-REC-03D — Model-Outage and Failure Handling

**2. Objective:** Implement graceful model/provider outage behavior. When the AI endpoint is unavailable, the deterministic risk engine result remains available, the workflow shows a failed AI step, the UI does not freeze, and the user can retry.

**3. User-visible or architectural outcome:** When the AI provider is unavailable, the system degrades gracefully: deterministic risk results are still shown, the workflow run shows a failed AI step with a clear error, and the user can retry the workflow.

**4. Exact included scope:**
- `backend/app/ai/workflow/outage_handler.py` — catches `TransientChatProviderError` and `PermanentChatProviderError` from 03A, implements retry logic (`llm_max_retries` from config), marks workflow run as `FAILED_PROVIDER` after retries exhausted
- `backend/app/ai/workflow/retry_policy.py` — exponential backoff retry policy for transient errors
- Unit tests: `backend/tests/unit/test_outage_handler.py`, `backend/tests/unit/test_retry_policy.py`
- Integration tests: `backend/tests/integration/test_model_outage_at013.py` — simulates provider unavailable, verifies risk engine result still available, workflow shows failed step, retry works

**5. Explicit exclusions:**
- No API endpoints (that is 03E)
- No frontend changes (the UI behavior is verified via API contract; frontend implementation is 03E)
- No approval/audit logic

**6. Permitted repository areas:**
- `backend/app/ai/workflow/outage_handler.py` (new)
- `backend/app/ai/workflow/retry_policy.py` (new)
- `backend/tests/unit/test_outage_handler*.py` (new tests)
- `backend/tests/integration/test_model_outage_at013.py` (new test)

**7. Dependencies and predecessor gates:**
- WP-REC-03A complete (provider adapter and exception hierarchy)
- WP-REC-03B complete (workflow state machine — `FAILED_PROVIDER` state)
- WP-REC-03C complete (structured-output validation — outage handler must also handle `FAILED_VALIDATION` as a non-retryable failure)

**8. Relevant Source-of-Truth requirements:**
- `03_DEFINITION_OF_DONE.md` Gate C: "When model unavailable, system shows controlled failure state"
- `04_ACCEPTANCE_TESTS.md` AT-013: "AI endpoint unavailable → risk engine result remains available, workflow shows failed AI step, UI does not freeze, user can retry"
- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §2: "cloud and local endpoint must connect through same adapter contract"

**9. Acceptance tests and additional unit/integration tests:**
- AT-013 (complete): AI endpoint unavailable → risk engine result available, workflow shows failed AI step, UI does not freeze, user can retry
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
- Every retry logged with correlation ID, run ID, attempt number, error type, backoff delay
- Final failure logged with correlation ID, run ID, total attempts, final error
- Risk engine result availability logged (confirms deterministic fallback works)

**13. Estimated size:** S (2-3 new files, ~150-200 lines implementation + ~200-250 lines tests)

**14. Exit criteria:**
- Outage handler catches provider exceptions and retries transient errors
- Retry policy implements exponential backoff
- AT-013 test passes (risk engine result available during outage, workflow shows failed step, retry works)
- All unit and integration tests pass
- Linter and type checks pass

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. Requires explicit Product Owner authorization.

---

### WP-REC-03E — Workflow-Run Detail API + UI

**1. Stable ID and title:** WP-REC-03E — Workflow-Run Detail API + UI

**2. Objective:** Expose workflow run details via API and display them in the frontend, including steps, duration, input/output summary, retrieval sources, model metadata, and errors/retries.

**3. User-visible or architectural outcome:** A user can view a workflow run's details: execution steps, duration, input/output summary, tool calls, retrieval sources, model metadata, and errors/retries (`01_PRODUCT_AND_MVP_SCOPE.md` §3.6).

**4. Exact included scope:**
- `backend/app/api/workflow.py` — REST API: `GET /api/v1/workflow-runs/{run_id}` returns run with steps, `GET /api/v1/workflow-runs` lists runs (paginated)
- `backend/app/schemas/workflow.py` — update with response schemas (extends 03B schemas)
- `frontend/src/routes/workflow-run-detail.tsx` — workflow run detail page
- `frontend/src/hooks/use-workflow-run.ts` — TanStack Query hook for fetching run details
- Frontend tests: `frontend/src/routes/__tests__/workflow-run-detail.test.tsx`

**5. Explicit exclusions:**
- No approval center UI (that is Phase 6 / WP-REC-04D)
- No audit log UI (that is Phase 6 / WP-REC-04E)
- No model outage handling logic (that is 03D — this package only displays errors)
- No new workflow engine logic (that is 03B — this package only reads and displays)

**6. Permitted repository areas:**
- `backend/app/api/workflow.py` (new)
- `backend/app/schemas/workflow.py` (update)
- `frontend/src/routes/workflow-run-detail.tsx` (new)
- `frontend/src/hooks/use-workflow-run.ts` (new)
- `frontend/src/routes/__tests__/workflow-run-detail.test.tsx` (new test)

**7. Dependencies and predecessor gates:**
- WP-REC-03A complete (provider adapter — model metadata in steps)
- WP-REC-03B complete (workflow models and engine — data to display)
- WP-REC-03C complete (validation results to display)
- WP-REC-03D complete (error/retry information to display)

**8. Relevant Source-of-Truth requirements:**
- `01_PRODUCT_AND_MVP_SCOPE.md` §3.6: Workflow Run Details screen — steps, duration, input/output summary, tool calls, retrieval sources, model metadata, errors/retries
- FR-07: "Every workflow step must be traceable by correlation ID"
- `03_DEFINITION_OF_DONE.md` Gate B: "Frontend tests pass"
- DEC-012: HTTP polling (3s interval) for run progress — use approved Phase 1 approach

**9. Acceptance tests and additional unit/integration tests:**
- AT-007 (partial): workflow trace — the run detail page shows all steps with correlation IDs (full AT-007 also requires document access control, which is WP-REC-05)
- Additional unit tests: API response schema correctness, pagination
- Additional frontend tests: run detail renders steps, duration, model metadata, errors; polling updates run status
- Additional integration tests: API returns run with steps from database

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
- `GET /api/v1/workflow-runs/{run_id}` returns run with steps
- `GET /api/v1/workflow-runs` lists runs (paginated)
- Frontend run detail page renders steps, duration, model metadata, errors/retries
- Polling updates run status (DEC-012 approved approach)
- All backend and frontend tests pass
- Linter and type checks pass

**15. Separate Product Owner authorization requirement:** YES — **NOT AUTHORIZED**. Requires explicit Product Owner authorization.

---

## 6. Acceptance-Test Mapping Summary

| AT | Description | Phase 5 Package | Status After Phase 5 |
|----|-------------|------------------|----------------------|
| AT-007 | Document access control | WP-REC-03E (partial: workflow trace) + WP-REC-05 (full) | PARTIAL |
| AT-008 | Structured output validation | WP-REC-03A + 03B + 03C | PASS (after 03C) |
| AT-013 | Model outage | WP-REC-03A + 03D | PASS (after 03D) |

AT-009, AT-010, AT-011, AT-012 are Phase 6 (WP-REC-04) and are NOT covered by Phase 5.

---

## 7. Planning Quality Gate Checklist

| Criterion | Status |
|-----------|--------|
| No package is oversized | ✅ All packages are M or S; no L packages |
| Each package has independently reviewable scope | ✅ Each package has explicit included scope and exclusions |
| Each package can be reverted independently | ✅ Each package is a feature branch; migrations have downgrade paths |
| Tests map to AT requirements | ✅ AT-008, AT-013 mapped; unit/integration tests specified per package |
| No package depends on unauthorized Runtime separation | ✅ No package touches `scripts/agent-loop/` or `.agent-loop/`; zero runtime coupling |
| No implementation is described as already authorized | ✅ Every package says "NOT AUTHORIZED" in §15 |
| Exact first candidate identified but unauthorized | ✅ WP-REC-03A is the first candidate; NOT AUTHORIZED |
| Deterministic risk calculation is authoritative input | ✅ DEC-004 preserved; risk engine feeds workflow, not vice versa |
| Structured and schema-validated model output | ✅ 03C enforces SoT §6 schema; AT-008 |
| Human approval before controlled writes | ✅ No write actions in Phase 5; approval is Phase 6 (WP-REC-04) |
| Complete audit traceability | ✅ Workflow steps and correlation IDs (03B); full audit is Phase 6 |
| Graceful model/provider outage behavior | ✅ 03D implements AT-013 |
| Synthetic-data-only policy | ✅ DEC-003 preserved; fake provider uses no real data |
| No runtime dependency on scripts/agent-loop | ✅ No package imports or depends on agent-loop |
| No coupling to forgemind-agent-runtime | ✅ Runtime separation (SP-0B) is NOT AUTHORIZED and not required |

---

## 8. Architecture Invariants Preserved

The decomposition preserves these invariants from the Source of Truth:

1. **Deterministic risk calculation is authoritative input** (DEC-004, SoT §2): The risk engine output feeds the workflow; the LLM never recalculates risks.
2. **Structured and schema-validated model output** (FR-06, SoT §6, AT-008): WP-REC-03C enforces the versioned recommendation schema.
3. **Human approval before controlled writes** (DEC-005, FR-08, AT-009): No write actions in Phase 5; procurement requires Phase 6 approval.
4. **Complete audit traceability** (FR-07, FR-09, AT-012): Workflow steps and correlation IDs (03B); full audit events in Phase 6.
5. **Graceful model/provider outage behavior** (AT-013, Gate C): WP-REC-03D ensures deterministic results remain available during outages.
6. **Synthetic-data-only policy** (DEC-003): Fake provider uses no real data; all test data is synthetic.
7. **No runtime dependency on scripts/agent-loop**: No package imports or depends on agent-loop code.
8. **No coupling to forgemind-agent-runtime**: SP-0B is NOT AUTHORIZED and not required for any Phase 5 package.

---

## 9. First Candidate Implementation Package

**WP-REC-03A — AI Provider Adapter (Chat/Reasoning)** is the first candidate implementation package.

**Rationale:**
- No predecessor implementation package or decision gate required
- Follows the proven embedding provider pattern (`embedding_provider.py`, `embedding_provider_factory.py`)
- Reuses existing config (`openai_api_key`, `openai_chat_model`, `llm_timeout_seconds`, `llm_max_retries`)
- Unblocks WP-REC-03B (via GATE-1) and 03C/03D/03E
- No database changes (lowest risk, easiest to revert)

**Status: NOT AUTHORIZED.** This package requires explicit Product Owner authorization before implementation begins.

---

## 10. Summary of NOT AUTHORIZED Items

| Item | Status |
|------|--------|
| WP-REC-03A (AI provider adapter) | NOT AUTHORIZED |
| WP-REC-03-DEC-GATE-1 (DEC-013 decision) | NOT AUTHORIZED |
| WP-REC-03B (workflow/state-machine) | NOT AUTHORIZED |
| WP-REC-03C (structured-output validation) | NOT AUTHORIZED |
| WP-REC-03D (model-outage handling) | NOT AUTHORIZED |
| WP-REC-03E (workflow-run detail API/UI) | NOT AUTHORIZED |
| WP-REC-03 implementation (as a whole) | NOT AUTHORIZED |
| SP-0B (Runtime migration manifest) | READY but NOT AUTHORIZED |
| Creation of forgemind-agent-runtime | NOT AUTHORIZED |
| DEC-013 acceptance | NOT AUTHORIZED (Proposed, pending PO) |
| DEC-015 permanent decision | NOT AUTHORIZED (Proposed, deferred) |
