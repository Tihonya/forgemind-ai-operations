# WP-REC-03D — Read-Only Reconnaissance and Implementation-Readiness Assessment

**Date:** 2026-08-09
**Assessment type:** Read-only reconnaissance gate (no implementation authorized)
**Baseline:** `origin/main` @ `d82b9aaacaab461e099099785b30022777a145d7` (PR #72 merge commit)
**Assessor:** Hermes Agent (read-only, planning branch `docs/wp-rec-03-controlled-decomposition`)

---

## 1. Verified Repository and Worktree State

### 1.1 Remote and origin/main

- **Remote:** `https://github.com/Tihonya/forgemind-ai-operations.git`
- **origin/main HEAD:** `d82b9aaacaab461e099099785b30022777a145d7`
- **Expected:** `d82b9aaacaab461e099099785b30022777a145d7`
- **Match:** EXACT MATCH

### 1.2 CI state for origin/main

- **PR #72** (WP-REC-03C): MERGED at `2026-08-09T15:44:01Z`, merge commit `d82b9aa`.
- **Backend CI** on `main` @ `d82b9aa`: `completed` / `success` (2m8s).
- **End-to-End Tests** on `main` @ `d82b9aa`: `completed` / `success` (2m49s).
- **PR #72 checks:** `test` pass (2m9s), `Run Golden Scenario E2E Tests` pass (2m49s).

### 1.3 Worktrees

| Worktree | HEAD | Branch |
|----------|------|--------|
| `/home/toha/Projects/forgemind-ai-operations` | `cbcac23` | `feature/phase-3-wp-3-6-risk-detail` |
| `.../forgemind-post-merge-sync` | `a838445` | `docs/post-merge-status-sync-wp-strat-01` |
| `.../forgemind-wp-arch-01-closure` | `8a82221` | `docs/wp-arch-01-closure-sync` |
| `.../forgemind-wp-arch-01-planning` | `28c9c00` | `docs/wp-arch-01-planning` |
| `.../forgemind-wp-rec-03` (current) | `8d77f1d` | `docs/wp-rec-03-controlled-decomposition` |
| `.../forgemind-wp-rec-03-post-arch` | `efc17cb` | `docs/wp-rec-03-post-arch-reconciliation` |
| `.../forgemind-wp-rec-03c` | `9810a9d` | `feature/phase-5-wp-rec-03c-structured-output-validation` |

Current worktree is on planning branch `docs/wp-rec-03-controlled-decomposition` at `8d77f1d` — 3 commits ahead, 39 commits behind `origin/main`. This is expected: the planning branch was not rebased after 03C merge. Working tree is clean (zero staged, zero unstaged, zero untracked).

### 1.4 WP-REC-03D branch/PR check

- No local or remote branch containing "03d" or "03D" exists.
- No open or closed PR referencing "03D" exists.
- No WP-REC-03D work is expected to exist. Confirmed: none does.

### 1.5 Repository state vs. prompt

Repository state matches the prompt exactly. No material difference detected. No unrelated dirty work present.

---

## 2. Current 03A/03B/03C Implementation Contracts Relevant to 03D

### 2.1 WP-REC-03A — Chat Provider Adapter (COMPLETE, PR #63)

Files on `origin/main`:

- `backend/app/ai/provider/chat_provider.py` — `ChatProvider` ABC with `async complete(prompt, schema, context) -> ChatResult`. `ChatResult` is a frozen dataclass: `content`, `model`, `finish_reason`, `usage: dict[str,int]`, `metadata: dict[str, Any]`.
- `backend/app/ai/provider/exceptions.py` — Four exception types:
  - `ChatProviderError` (base)
  - `TransientChatProviderError` (retryable)
  - `PermanentChatProviderError` (non-retryable)
  - `ChatProviderConfigurationError` (construction-time, non-retryable)
- `backend/app/ai/provider/openai_chat_provider.py` — `OpenAIChatProvider`:
  - SDK retries **disabled** (`max_retries=0`) — single attempt only.
  - `_classify_error()` maps SDK exceptions deterministically:
    - Transient: `APIConnectionError`, `APITimeoutError`, `RateLimitError`, `InternalServerError`, 5xx `APIStatusError`
    - Permanent: `AuthenticationError`, `PermissionDeniedError`, `BadRequestError`, `UnprocessableEntityError`, `NotFoundError`, `ConflictError`, 4xx `APIStatusError`, unrecognized errors (safe default)
  - Rate limiter: per-instance sliding window, cancellation-safe.
  - Logging: safe metadata only (model, latency, status, error_type). Never logs exception messages, API keys, or response bodies.
- `backend/app/ai/provider/fake_chat_provider.py` — `FakeChatProvider`: deterministic SHA-256-based responses, no network, injectable clock.
- `backend/app/ai/provider/factory.py` — `create_chat_provider()`: environment-aware, fake blocked in staging/production.

**Key 03D-relevant fact:** The OpenAI provider already performs error classification and SDK retries are disabled. The provider surfaces `TransientChatProviderError` / `PermanentChatProviderError` to the caller. 03D owns retry orchestration on top of this single-attempt contract.

### 2.2 WP-REC-03B — Workflow State Machine and Engine (COMPLETE, PR #65)

Files on `origin/main`:

- `backend/app/ai/workflow/state_machine.py` — `WorkflowState` enum (7 states), immutable transition table, `validate_transition()`, `TransitionConflictError`.
  - States: `PENDING`, `RUNNING`, `AWAITING_VALIDATION`, `COMPLETED`, `FAILED_VALIDATION`, `FAILED_PROVIDER`, `FAILED_INTERNAL`.
  - Terminal: `COMPLETED`, `FAILED_VALIDATION`, `FAILED_PROVIDER`, `FAILED_INTERNAL`.
  - Transitions from `RUNNING`: → `AWAITING_VALIDATION`, → `FAILED_PROVIDER`, → `FAILED_INTERNAL`.
- `backend/app/ai/workflow/engine.py` — `WorkflowEngine`:
  - `create_run()` → creates `WorkflowRun` in `PENDING`.
  - `execute_provider_call(run, prompt, schema)`:
    1. Transitions `PENDING → RUNNING` (conditional UPDATE).
    2. Creates a `WorkflowStep` (seq=0, step_name="provider_call", status="started").
    3. Calls `self._provider.complete(prompt, schema, context)` with `correlation_id` and `run_id` in context.
    4. On success: step → "completed" with model metadata; transitions `RUNNING → AWAITING_VALIDATION`.
    5. On `TransientChatProviderError`: step → "failed" with `error_code=PROVIDER_TRANSIENT`; transitions `RUNNING → FAILED_PROVIDER`.
    6. On `PermanentChatProviderError`: step → "failed" with `error_code=PROVIDER_PERMANENT`; transitions `RUNNING → FAILED_PROVIDER`.
    7. On `ChatProviderConfigurationError`: step → "failed" with `error_code=PROVIDER_CONFIG`; transitions `RUNNING → FAILED_PROVIDER`.
    8. On unknown `ChatProviderError`: treated as permanent.
    9. On unknown `Exception`: `error_code=INTERNAL_ERROR`; transitions `RUNNING → FAILED_INTERNAL`.
  - `_transition_run()`: conditional UPDATE with `WHERE state = :expected RETURNING id`. On conflict: refreshes ORM instance, raises `TransitionConflictError`.
  - `_safe_error_summary(exc)`: returns `type(exc).__name__` only — never the exception message.
  - `_classify_safe_error_detail(detail)`: allowlist-based; unrecognized values → `INTERNAL_ERROR`.
  - `fail_internal(run, error_detail)`: transitions to `FAILED_INTERNAL` with allowlisted safe detail.
  - Constructor accepts injectable `clock` for deterministic tests.
  - Caller owns the transaction boundary (no commit/rollback inside the engine).
- `backend/app/models/workflow.py` — `WorkflowRun`, `WorkflowStep`, `Recommendation` ORM models.
  - `WorkflowStep`: `seq` (int), `step_name`, `status` (started/completed/failed), `model_name`, `latency_ms`, `token_usage` (JSONB), `step_metadata` (JSONB), `error_code`, `error_detail`.
- `backend/app/schemas/workflow.py` — Pydantic schemas for run/step.
- Migration: `backend/alembic/versions/f1a2b3c4d5e6_add_workflow_tables.py`.

**Key 03D-relevant fact:** The engine currently performs NO retry. On `TransientChatProviderError`, it immediately transitions to `FAILED_PROVIDER`. 03D must intercept the provider call to add retry BEFORE the engine sees the failure. The engine's error handling and state transitions are correct for the post-retry-exhaustion case — once retries are exhausted, the same `TransientChatProviderError` surfaces to the engine, which transitions to `FAILED_PROVIDER` as it already does.

### 2.3 WP-REC-03C — Structured-Output Validation (COMPLETE, PR #72)

Files on `origin/main`:

- `backend/app/ai/workflow/schema_validator.py` — `validate_structured_output(content) -> RecommendationData`:
  - Pure function, no side effects, no persistence.
  - Raises `StructuredOutputValidationError` (unified exception) with `reason` (`INVALID_JSON` or `INVALID_SCHEMA`), `error_count`, `field_locations`, `error_types`.
  - Safe metadata only — never raw model output, input values, or full Pydantic error messages.
  - `__cause__` preserves original exception but must not be exposed.
- `backend/app/schemas/recommendation.py` — `RecommendationData`, `RiskItem`, `RecommendedAction`, `Source` Pydantic models. `extra="forbid"`, strict bool validation.
- `backend/app/ai/workflow/prompts.py` — Versioned prompt template (`PROMPT_VERSION = "1.0"`).

**Key 03D-relevant fact:** `StructuredOutputValidationError` is NOT a `ChatProviderError` subclass. It is a separate exception type that the future 03F caller catches to map to `FAILED_VALIDATION`. 03D's retry logic must NOT catch or retry `StructuredOutputValidationError` — it is a non-retryable validation failure, not a provider failure.

---

## 3. Exact Retry Ownership and Call Flow

### 3.1 Retry ownership

**Retry belongs in a provider-level wrapper (`RetryingChatProvider`), NOT in the workflow engine.**

The `ChatProvider` ABC is designed for transparent wrapping. A `RetryingChatProvider(ChatProvider)` wraps a delegate provider and implements retry inside `complete()`. The engine calls `complete()` as usual and sees only the final outcome (success or exhausted-transient-failure). The engine's existing exception handling and state transitions remain correct without modification.

### 3.2 Call flow

```
WorkflowEngine.execute_provider_call(run, prompt, schema)
  → transitions PENDING → RUNNING
  → creates WorkflowStep (seq=N, "provider_call", "started")
  → calls RetryingChatProvider.complete(prompt, schema, context)
      → calls delegate.complete(prompt, schema, context)  [attempt 1]
      → on success: returns ChatResult
      → on TransientChatProviderError:
          → logs retry attempt (correlation_id, run_id, attempt, error_type, backoff_delay)
          → sleeps backoff (via injectable sleeper)
          → calls delegate.complete() again  [attempt 2]
          → ... repeats up to max_retries
          → on exhaustion: raises TransientChatProviderError to engine
      → on PermanentChatProviderError: raises immediately (no retry)
      → on ChatProviderConfigurationError: raises immediately (no retry)
  → on ChatResult: step → "completed", transitions RUNNING → AWAITING_VALIDATION
  → on TransientChatProviderError: step → "failed" (PROVIDER_TRANSIENT), transitions RUNNING → FAILED_PROVIDER
  → on PermanentChatProviderError: step → "failed" (PROVIDER_PERMANENT), transitions RUNNING → FAILED_PROVIDER
```

### 3.3 Nested-retry proof

- OpenAI SDK retries: **disabled** (`max_retries=0` in `OpenAIChatProvider.__init__`).
- Engine retries: **none** (engine calls `complete()` once, catches the result/exception).
- RetryingChatProvider retries: **the sole retry layer**.
- No multiplication: SDK (0) × engine (0) × wrapper (N) = N total attempts.

---

## 4. Retry-Count Truth Table

### 4.1 Semantics of `llm_max_retries`

**`llm_max_retries` means retries after the initial attempt.** Total attempts = `1 + llm_max_retries`.

Evidence:
- `config.py`: `llm_max_retries: int = Field(default=3, ge=0, le=10)` — the field name says "max_retries", implying additional attempts beyond the first.
- `openai_chat_provider.py` docstring: "SDK retries are always disabled (max_retries=0) regardless of ``llm_max_retries``. The ``llm_max_retries`` setting is owned by the workflow-level outage handler (WP-REC-03D)."
- The OpenAI SDK's own `max_retries` parameter also means "retries after initial attempt."

### 4.2 Truth table

| `llm_max_retries` | Initial attempt | Retries | Total provider calls |
|-------------------|-----------------|---------|---------------------|
| 0                 | 1               | 0       | 1                   |
| 1                 | 1               | 1       | 2                   |
| 3 (default)       | 1               | 3       | 4                   |

### 4.3 No silent semantic change

The existing semantics ("retries after initial attempt") are preserved. 03D reads `llm_max_retries` from `Settings` and uses it as the retry count (not total attempt count). Total attempts = `1 + llm_max_retries`.

---

## 5. Exception-Classification Table

| Exception | Source | Classification | Retryable by 03D? | Action |
|-----------|--------|----------------|-------------------|--------|
| `TransientChatProviderError` | 03A provider | Retryable transient provider failure | YES | Retry up to `llm_max_retries` times with backoff. On exhaustion, raise to engine → `FAILED_PROVIDER`. |
| `PermanentChatProviderError` | 03A provider | Non-retryable permanent provider failure | NO | Raise immediately to engine → `FAILED_PROVIDER`. |
| `ChatProviderConfigurationError` | 03A provider | Configuration failure (non-retryable) | NO | Raise immediately to engine → `FAILED_PROVIDER`. |
| `ChatProviderError` (unknown subclass) | 03A provider | Treated as permanent by engine | NO | Raise immediately. Engine treats as `PROVIDER_PERMANENT`. |
| `StructuredOutputValidationError` | 03C validator | Validation failure | NO | Not caught by 03D. Not a `ChatProviderError` subclass. Propagates to caller. **03D never retries validation failures.** |
| `StateMachineError` | 03B state machine | Internal failure | NO | Not caught by 03D. Propagates to caller. |
| `TransitionConflictError` | 03B engine | Concurrency conflict | NO (must propagate) | Not caught by 03D. Propagates to caller. Cancellation-like — the caller must re-read state. |
| `asyncio.CancelledError` | Async runtime | Cancellation | NO (must propagate) | Not caught by 03D. Propagates immediately. No backoff sleep is performed. |
| `RuntimeError` / other `Exception` | Unknown | Internal failure | NO | Not caught by 03D wrapper (only `ChatProviderError` subclasses are caught). Propagates to engine → `FAILED_INTERNAL`. |

**`FAILED_VALIDATION` is never automatically retried by 03D.** `StructuredOutputValidationError` is not a `ChatProviderError` and is not caught by the retry wrapper. Validation failures occur after the provider call succeeds (the provider returned content, but the content failed schema validation). Retry of validation failures would require re-calling the provider with the same prompt, which is a user-initiated retry action owned by 03F, not an automatic provider retry.

---

## 6. Proposed Backoff Contract

### 6.1 Formula

```
delay = min(base_delay * (2 ** attempt_index), max_delay)
```

Where `attempt_index` is the zero-based index of the retry (0 for the first retry, 1 for the second, etc.).

### 6.2 Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| `base_delay` | 1.0 seconds | Hardcoded constant in `retry_policy.py`. The project has no existing backoff configuration in `Settings`. Adding a new config field would require modifying `config.py` (not in 03D's permitted scope per decomposition doc). 1.0s is a safe, conventional base for API retry. |
| `max_delay` | 30.0 seconds | Hardcoded constant. Caps the exponential growth. 30s aligns with `llm_timeout_seconds` default (30s), preventing a single retry's backoff from exceeding the provider call's own timeout. |
| `jitter` | Excluded | Jitter is excluded for testability and determinism. The project's testing discipline requires deterministic, injectable time. Jitter would require a random source injection and complicate assertion of exact retry timing. The fake provider and injectable sleeper already provide deterministic test behavior. In production, the sliding-window rate limiter in `OpenAIChatProvider` provides some natural desynchronization. |

### 6.3 Truth table for default `llm_max_retries=3`

| Retry # | attempt_index | Raw delay | Capped delay |
|---------|---------------|-----------|--------------|
| 1st retry | 0 | 1.0s | 1.0s |
| 2nd retry | 1 | 2.0s | 2.0s |
| 3rd retry | 2 | 4.0s | 4.0s |

Total backoff time before exhaustion: 1.0 + 2.0 + 4.0 = 7.0 seconds.

### 6.4 Sleeper/clock injection

- `RetryPolicy` accepts an injectable `sleeper: Callable[[float], Awaitable[None]]` (defaults to `asyncio.sleep`).
- Tests inject a recording fake sleeper that records delays without waiting.
- `RetryingChatProvider` accepts an injectable `clock` (already established pattern from `OpenAIChatProvider` and `FakeChatProvider`).
- **Tests must never perform real waiting.** All tests use the fake sleeper.

### 6.5 Cancellation behavior

- If `asyncio.CancelledError` is raised during `sleeper(delay)`, it propagates immediately. No further retry attempts are made. The partial state is clean: no `WorkflowStep` is left in an inconsistent state because the step is created and managed by the engine, not the retry wrapper.
- `CancelledError` is never caught by the retry wrapper's `except ChatProviderError` handlers (it is not a `ChatProviderError` subclass).

### 6.6 No new dependency

The backoff contract uses only `asyncio.sleep` and standard Python math. No external retry library (tenacity, backoff, etc.) is needed. The project's dependency list in `pyproject.toml` already includes `asyncio` via the standard library. No new dependency is introduced.

---

## 7. State-Transition and Workflow-Step Behavior

### 7.1 State before first provider attempt

- Run state: `RUNNING` (engine transitions `PENDING → RUNNING` before calling the provider).
- No `WorkflowStep` for this run's provider call exists yet (engine creates it after the transition).

### 7.2 Representation of each retry attempt

**Each retry attempt does NOT create a separate `WorkflowStep`.** The retry attempts are sub-events within the single "provider_call" step. Retry attempt details are:

1. **Logged** via structured logging: `correlation_id`, `run_id`, `attempt_number`, `total_allowed_attempts`, `error_type` (exception class name), `backoff_delay`, `outcome` ("retrying" or "exhausted").
2. **Stored in `step_metadata` (JSONB)** on the single `WorkflowStep` created by the engine. The `RetryingChatProvider` can include retry metadata in the `ChatResult.metadata` dict on success, or attach it to the raised exception on failure for the engine to extract.

**Design choice:** The `RetryingChatProvider` stores an `attempt_history` list internally. On success, it includes `retry_count` and `attempt_history` in `ChatResult.metadata`. On exhaustion, it raises a `TransientChatProviderError` that carries retry metadata (as a custom attribute, not in the message). The engine's existing `_safe_error_summary()` extracts only the type name — the retry metadata is accessed separately.

**IMPORTANT:** The engine's existing `_safe_error_summary(exc)` returns `type(exc).__name__`. If we want retry metadata in the step record, the engine would need modification. However, the decomposition doc's permitted-file list does NOT include `engine.py`. Therefore, the design must work WITHOUT modifying the engine:

- On success: retry metadata flows through `ChatResult.metadata` → `step.step_metadata` (engine already copies `chat_result.metadata` to `step_metadata`).
- On failure: retry metadata is in logs only. The step's `error_code` and `error_detail` are the safe classification codes already handled by the engine.

This is sufficient. The audit trail (FR-07) is preserved: the step records the overall provider-call outcome, and detailed retry attempt history is in structured logs with `correlation_id` and `run_id` for traceability.

### 7.3 Attempt numbering

- Attempt 0: initial call (not a retry).
- Attempt 1: first retry.
- Attempt N: Nth retry.
- Total attempts = `1 + llm_max_retries`.
- `total_allowed_attempts` in logs = `1 + llm_max_retries`.

### 7.4 Metadata recorded for each attempt (in logs)

| Field | Value | Safe? |
|-------|-------|-------|
| `correlation_id` | From context dict | Yes (UUID) |
| `run_id` | From context dict | Yes (UUID) |
| `attempt_number` | 0-based index | Yes (int) |
| `total_allowed_attempts` | `1 + llm_max_retries` | Yes (int) |
| `error_type` | `type(exc).__name__` | Yes (bounded string, class name only) |
| `backoff_delay_seconds` | Computed delay | Yes (float) |
| `outcome` | "retrying" or "exhausted" or "success" | Yes (bounded string) |

### 7.5 Terminal transition after exhaustion

- `RetryingChatProvider` raises `TransientChatProviderError` after exhausting all retries.
- Engine catches it, creates step with `error_code=PROVIDER_TRANSIENT`, transitions `RUNNING → FAILED_PROVIDER`.
- `TransitionConflictError` is possible if a concurrent operation already moved the run out of `RUNNING`. The engine's conditional UPDATE handles this (refreshes ORM, raises `TransitionConflictError`).

### 7.6 Immediate permanent-failure transition

- `RetryingChatProvider` raises `PermanentChatProviderError` (or `ChatProviderConfigurationError`) immediately without retry.
- Engine catches it, creates step with appropriate `error_code`, transitions `RUNNING → FAILED_PROVIDER`.

### 7.7 Retry-then-success transition

- `RetryingChatProvider` returns `ChatResult` after a successful retry.
- Engine records step as "completed" with model metadata (including retry count in `step_metadata`), transitions `RUNNING → AWAITING_VALIDATION`.

### 7.8 Transition conflicts and concurrent execution

- The engine's conditional UPDATE (`WHERE state = :expected RETURNING id`) serializes concurrent transitions. This guarantee from WP-REC-03B is preserved unchanged.
- The `RetryingChatProvider` does not interact with the database or state machine. It only wraps `complete()`. Concurrency safety is entirely owned by the engine.
- If two workers somehow execute `execute_provider_call` for the same run concurrently, the engine's `PENDING → RUNNING` conditional UPDATE ensures only one proceeds. The loser gets `TransitionConflictError` and the provider is NOT called (existing 03B test: `test_losing_execute_does_not_invoke_provider`).

### 7.9 Preservation of WP-REC-03B guarantees

- Conditional transitions: preserved (engine unchanged).
- Safe error persistence: preserved (engine's `_safe_error_summary` and `_classify_safe_error_detail` unchanged).
- ORM refresh on conflict: preserved (engine unchanged).
- Transaction ownership: preserved (caller owns commit/rollback; `RetryingChatProvider` does not touch the session).

---

## 8. Security and Observability Contract

### 8.1 Safe fields permitted in logs

| Field | Permitted | Source |
|-------|-----------|--------|
| `correlation_id` | YES | UUID, propagated from request context |
| `run_id` | YES | UUID |
| `attempt_number` | YES | Integer |
| `total_allowed_attempts` | YES | Integer |
| `error_type` (exception class name) | YES | Bounded string, deterministic |
| `backoff_delay_seconds` | YES | Float |
| `outcome` | YES | Bounded enum string |
| `model` | YES | Model name (already logged by provider) |

### 8.2 Forbidden fields (never logged or persisted)

| Field | Reason |
|-------|--------|
| Raw exception messages | May contain API keys, bearer tokens, passwords, provider response bodies |
| Provider response bodies | May contain sensitive content, internal details |
| Authorization headers | Contains API keys / bearer tokens |
| API keys | Secret |
| Prompts | May contain business data |
| Stack traces | May contain internal paths, variable values |
| `StructuredOutputValidationError.__cause__` | May contain raw Pydantic error messages echoing rejected input |

### 8.3 Safe fields permitted in persisted error metadata

- `WorkflowStep.error_code`: one of `PROVIDER_TRANSIENT`, `PROVIDER_PERMANENT`, `PROVIDER_CONFIG`, `INTERNAL_ERROR` (existing engine allowlist).
- `WorkflowStep.error_detail`: exception type name only (via `_safe_error_summary`).
- `WorkflowStep.step_metadata`: on success, includes `retry_count` and safe provider metadata. On failure, not populated with retry details (retry details are in logs only).

### 8.4 Observability requirements (met by current logging infrastructure)

- Structured logging via `backend/app/core/logging.py` (structlog).
- Every retry attempt logged with: `correlation_id`, `run_id`, `attempt_number`, `total_allowed_attempts`, `error_type`, `backoff_delay_seconds`, `outcome`.
- Final failure logged with: `correlation_id`, `run_id`, `total_attempts`, `final_error_type`, `final_outcome`.
- Final success (after retry) logged with: `correlation_id`, `run_id`, `total_attempts`, `final_outcome`.
- Risk engine result availability: NOT logged by 03D (risk engine is a separate service; its availability is guaranteed by architectural separation, not by 03D).

---

## 9. Integration-Test Feasibility Verdict

### 9.1 Testable in 03D

| Scenario | Feasible? | Test type |
|----------|-----------|-----------|
| Transient failure → bounded retries → `FAILED_PROVIDER` | YES | Unit test with fake provider raising `TransientChatProviderError`, fake sleeper, assert retry count and final state via engine. |
| Transient failure → later success | YES | Unit test with fake provider that fails N times then succeeds, fake sleeper, assert `ChatResult` returned and retry count in metadata. |
| Permanent failure → zero retries | YES | Unit test with fake provider raising `PermanentChatProviderError`, assert no sleep calls, immediate failure. |
| `llm_max_retries=0` → single attempt, no retry | YES | Unit test with `llm_max_retries=0`, transient failure, assert single call, immediate failure. |
| Backoff timing correctness | YES | Unit test with fake sleeper recording delays, assert exponential sequence. |
| Cancellation propagation | YES | Unit test with fake sleeper raising `CancelledError`, assert immediate propagation, no further retries. |
| No secret leakage in logs | YES | Unit test with exception message containing fake secrets, assert log output does not contain them. |

### 9.2 Integration test (database-backed)

| Scenario | Feasible? | Approach |
|----------|-----------|----------|
| Transient failure → retries → `FAILED_PROVIDER` persisted | YES | Integration test with `RetryingChatProvider` wrapping a fake provider that always raises `TransientChatProviderError`, real database, assert `WorkflowRun.state=FAILED_PROVIDER`, `WorkflowStep` recorded, `error_code=PROVIDER_TRANSIENT`. |
| Transient failure → retry → success → `AWAITING_VALIDATION` | YES | Integration test with fake provider that fails twice then succeeds, assert run reaches `AWAITING_VALIDATION`, step "completed" with retry metadata. |
| Permanent failure → `FAILED_PROVIDER` immediately | YES | Integration test with `PermanentChatProviderError`, assert no retry, immediate `FAILED_PROVIDER`. |

### 9.3 "Risk engine result remains available during provider outage"

**Classification: Architectural invariant already guaranteed by separation.**

The deterministic risk engine is a separate Phase 2 service (`backend/app/services/risk_engine.py` or equivalent) that does not depend on the AI provider (DEC-004). AT-004 (Deterministic risk calculation) is already PASS. The risk engine result is queryable via existing APIs independently of the AI workflow. 03D does not wire the risk engine into the workflow (that is 03F's vertical wiring). Therefore, 03D cannot honestly prove "risk engine result remains available during provider outage" with an end-to-end integration test that exercises both the risk engine and the provider outage path.

**This is not a gap — it is an architectural invariant.** The risk engine's availability is guaranteed by:
1. DEC-004: deterministic code owns quantities; LLM explains.
2. Phase 2 complete: risk engine exists and is tested (AT-004 PASS).
3. Architectural separation: the risk engine service has no dependency on `ChatProvider` or `WorkflowEngine`.

**The end-to-end verification of "risk engine result available during outage" is owned by 03F**, which wires the risk engine into the workflow and can demonstrate that the risk result is persisted even when the provider call fails. 03D's integration test should NOT create a misleading test that calls the risk engine independently and calls it an "outage workflow."

**03D integration test should assert:** When the provider is unavailable, the workflow run reaches `FAILED_PROVIDER` after bounded retries, and the `WorkflowStep` records the failure with safe error metadata. The risk engine's independent availability is noted as an architectural invariant, not tested in 03D.

---

## 10. Documentation Contradictions and Their Classification

### 10.1 Stale 03C status references

**Finding:** WP-REC-03C is now COMPLETE (merged via PR #72, merge commit `d82b9aa`), but active governance documents still reference it as "NOT AUTHORIZED" or "NOT IMPLEMENTED":

- `docs/next_steps.md`: "AT-008 | Structured output validation | NOT IMPLEMENTED" (line 157). Reconciled against PR #69 (`3a2bc26`), which predates 03C merge.
- `docs/ACTIVE_WORK.md`: "WP-REC-03C is the next candidate... NOT AUTHORIZED" (line 44). Reconciled against PR #69.
- `docs/planning/wp_rec_03_decomposition.md`: "03C–03G say 'NOT AUTHORIZED' in §15" (quality gate checklist). 03C's §15 still says "NOT AUTHORIZED."

**Classification:** Separate status-synchronization work. This is a post-merge status sync task (same pattern as the PR #66 and PR #68 sync PRs). It should NOT be included in the 03D implementation PR because it touches governance documents outside 03D's scope. A separate bounded documentation PR should update `next_steps.md`, `ACTIVE_WORK.md`, and the decomposition doc's 03C §15 to reflect 03C completion.

**Urgency:** Required before 03D implementation begins — the 03D implementation prompt must reference the correct baseline (03C complete, not "NOT AUTHORIZED"). However, the correction itself is a separate documentation PR, not part of 03D.

### 10.2 AT-013 PASS timing contradiction

**Finding:** The decomposition doc contains an internal contradiction about when AT-013 becomes PASS:

- Line 486: "AT-013 becomes PASS only after 03F."
- Line 819 (summary table): "PASS (after 03F + 03G)."
- Line 110: "AT-013 is NOT PASS after 03D alone, and NOT PASS after 03F alone (UI clauses require 03G)."
- Line 848: "AT-013 PASS only after 03F + 03G."

**Classification:** Correction that may be included in the 03D PR. Line 486 is stale — it should say "AT-013 becomes PASS only after 03F + 03G" (consistent with lines 110, 819, 848). This is a one-line text correction in the decomposition doc's 03D section (§9). Since 03D implementation will touch the decomposition doc's 03D section for status updates, this correction can be included in the same PR if the PO permits documentation corrections in the implementation PR.

**Alternative classification:** Separate status-synchronization work — if the PO prefers to keep implementation PRs code-only, this correction belongs in the same status-sync PR as finding 10.1.

### 10.3 03D permitted-file list completeness

**Finding:** The decomposition doc's 03D §6 lists only:
- `backend/app/ai/workflow/outage_handler.py` (new)
- `backend/app/ai/workflow/retry_policy.py` (new)
- `backend/tests/unit/test_outage_handler*.py` (new tests)
- `backend/tests/integration/test_provider_outage.py` (new test)

**Question:** Does 03D require modifying `engine.py` or any other existing production file?

**Answer:** NO. The `RetryingChatProvider` wrapper design (see §3 above) implements retry inside a `ChatProvider` wrapper. The engine receives the wrapper as its `provider` argument and calls `complete()` as usual. The engine's existing exception handling correctly processes the wrapper's final outcome. No engine modification is needed.

**Classification:** The permitted-file list is correct and executable as written. This is a clarification of the existing package design, not an architecture/scope change. No PO approval is needed for the design — the `ChatProvider` ABC was designed in 03A for exactly this kind of transparent wrapping.

### 10.4 Retry UI behavior assignment to 03F vs 03G

**Finding:** Some decomposition text may assign retry UI behavior ambiguously between 03F and 03G:

- 03D §9 line 486: "user can retry (03F)" — this refers to the backend retry API.
- 03G §9: "user can click retry" — this refers to the frontend retry button.
- 03F §4: "POST /api/v1/workflow-runs/{run_id}/retry" — the backend retry endpoint.

**Assessment:** This is NOT a contradiction. 03F owns the backend retry API (HTTP endpoint + ARQ worker). 03G owns the frontend retry UI action (button + hook). The decomposition is consistent: 03F provides the API, 03G provides the UI. The 03D §9 reference to "user can retry (03F)" is shorthand for "the backend capability that enables user retry" — it is not claiming 03F provides the UI.

**Classification:** Harmless historical text that must remain unchanged. The ownership boundary is clear and consistent across all packages.

### 10.5 ACTIVE_WORK.md / next_steps.md reconciliation baseline

**Finding:** Both files are "Reconciled against: origin/main @ `3a2bc26028cac0352af2cdde8107df90f41f015c` (PR #69 merge commit)." This predates PR #71 (reconciliation), PR #72 (03C merge), and the current `origin/main` at `d82b9aa`.

**Classification:** Separate status-synchronization work. The reconciliation baseline should be updated to `d82b9aa` in the same post-03C-merge status-sync PR that addresses finding 10.1.

---

## 11. Exact Minimal Production Files That Must Change

**No existing production file must change.** The 03D implementation creates only new files:

| File | Action | Purpose |
|------|--------|---------|
| `backend/app/ai/workflow/retry_policy.py` | NEW | `RetryPolicy` dataclass: backoff formula, base delay, max delay, sleeper injection. Pure calculation, no side effects. |
| `backend/app/ai/workflow/outage_handler.py` | NEW | `RetryingChatProvider(ChatProvider)`: wraps a delegate `ChatProvider`, catches `TransientChatProviderError`, retries per `RetryPolicy`, raises after exhaustion. Logs each attempt with safe metadata. |

**No modification to:**
- `backend/app/ai/workflow/engine.py` — unchanged
- `backend/app/ai/workflow/state_machine.py` — unchanged
- `backend/app/ai/provider/` (all files) — unchanged
- `backend/app/models/workflow.py` — unchanged
- `backend/app/schemas/` (all files) — unchanged
- `backend/app/config.py` — unchanged
- `backend/alembic/` — unchanged (no migration needed)
- `backend/pyproject.toml` — unchanged (no new dependency)

---

## 12. Exact Test Files That Must Be Created or Changed

| File | Action | Purpose |
|------|--------|---------|
| `backend/tests/unit/test_retry_policy.py` | NEW | Unit tests for `RetryPolicy`: backoff formula correctness, max delay cap, sleeper injection, deterministic delays, cancellation propagation. |
| `backend/tests/unit/test_outage_handler.py` | NEW | Unit tests for `RetryingChatProvider`: transient → retry → success; transient → retry → exhaustion → `TransientChatProviderError`; permanent → no retry; config error → no retry; `llm_max_retries=0` → single attempt; attempt counting; metadata in `ChatResult`; safe logging (no secret leakage); cancellation during sleep. |
| `backend/tests/integration/test_provider_outage.py` | NEW | Integration tests with real database: transient → retries → `FAILED_PROVIDER` persisted; transient → retry → success → `AWAITING_VALIDATION`; permanent → `FAILED_PROVIDER` immediately; step recording with correct `error_code`; conditional-transition safety preserved. |

**No existing test file must change.** The existing `test_workflow_engine.py` tests use `_RecordingFakeProvider` which can be wrapped by `RetryingChatProvider` in new tests without modifying existing tests.

---

## 13. Files Explicitly Forbidden from Change

- `forgemind_project_source_of_truth/` (all 9 documents) — Source of Truth, PO authority required
- `backend/app/ai/workflow/engine.py` — production file, no modification needed
- `backend/app/ai/workflow/state_machine.py` — production file, no modification needed
- `backend/app/ai/workflow/schema_validator.py` — 03C production file
- `backend/app/ai/workflow/prompts.py` — 03C production file
- `backend/app/ai/provider/` (all files) — 03A production files
- `backend/app/models/workflow.py` — 03B production file
- `backend/app/schemas/` (all files) — existing schemas
- `backend/app/config.py` — existing configuration
- `backend/alembic/` — existing migrations
- `backend/pyproject.toml` — dependencies
- `docs/ACTIVE_WORK.md` — governance document (separate sync PR)
- `docs/next_steps.md` — governance document (separate sync PR)
- `docs/planning/wp_rec_03_decomposition.md` — planning document (status update only, separate sync PR, unless PO permits inline correction of finding 10.2)
- `.github/workflows/` — CI configuration
- `Makefile` — build configuration
- `docker-compose*.yml` — infrastructure
- `frontend/` (all files) — 03D is backend-only
- `scripts/agent-loop/` — Runtime, not Product
- `.agent-loop/` — Runtime, not Product

---

## 14. Exact Local and CI-Equivalent Validation Commands

### 14.1 CI commands (from `.github/workflows/ci-backend.yml`)

```bash
# Run from backend/ directory
cd backend

# Lint
ruff check .

# Type check
mypy .

# Tests with coverage
DATABASE_URL=postgresql+asyncpg://forgemind:forgemind@localhost:5432/forgemind \
REDIS_URL=redis://localhost:6379/0 \
SECRET_KEY=test_secret_key_for_ci_only_32_chars_minimum \
pytest --cov=app --cov-report=xml --cov-report=term-missing -v
```

### 14.2 Local host-side commands (from memory/established pattern)

```bash
# Activate venv
cd /home/toha/Projects/forgemind-ai-operations
source .venv/bin/activate

# Set resolved DB URLs (NEVER source .env — see memory)
export DATABASE_URL="postgresql+asyncpg://forgemind:PASSWORD@localhost:5432/forgemind"
export TEST_DATABASE_URL="$DATABASE_URL"

# Lint
cd backend && ../.venv/bin/ruff check .

# Type check
../.venv/bin/mypy app/

# Unit tests only (no DB needed)
../.venv/bin/pytest tests/unit/ -v

# Integration tests (requires PostgreSQL)
../.venv/bin/pytest tests/integration/ -v

# Full suite
../.venv/bin/pytest -v
```

### 14.3 Specific 03D test commands

```bash
# Unit tests for retry policy and outage handler
cd backend && ../.venv/bin/pytest tests/unit/test_retry_policy.py tests/unit/test_outage_handler.py -v

# Integration test for provider outage
../.venv/bin/pytest tests/integration/test_provider_outage.py -v

# Existing workflow tests (regression — must still pass)
../.venv/bin/pytest tests/unit/test_workflow_engine.py tests/unit/test_workflow_state_machine.py tests/integration/test_workflow_run_lifecycle.py -v
```

### 14.4 Baseline test profile

Per memory: baseline at `origin/main` (pre-03D) = 1226 passed, 2 failed (DB connection refused, embedding default), 29 errors (DATABASE_URL not set). After 03D, the profile should be: 1226 + new_03D_tests passed, same 2 failed, same 29 errors (if no DB). With DB: all pass.

---

## 15. Expected Test Evidence

### 15.1 Unit test evidence

- `test_retry_policy.py`: ~8-12 tests covering backoff formula, max cap, sleeper injection, cancellation.
- `test_outage_handler.py`: ~12-18 tests covering all exception classifications, retry counting, metadata, logging safety, cancellation, `llm_max_retries=0` edge case.
- All unit tests use fake sleeper and fake provider — no real waiting, no network, no database.

### 15.2 Integration test evidence

- `test_provider_outage.py`: ~4-6 tests with real PostgreSQL:
  - Transient always → retries exhausted → `FAILED_PROVIDER` persisted, step recorded.
  - Transient N then success → `AWAITING_VALIDATION`, step "completed" with retry metadata.
  - Permanent → no retry → `FAILED_PROVIDER` immediately.
  - `llm_max_retries=0` → single attempt → `FAILED_PROVIDER`.
- Integration tests require `TEST_DATABASE_URL` or `DATABASE_URL` set (same skipif pattern as existing workflow tests).

### 15.3 Regression evidence

- Existing `test_workflow_engine.py` (all classes) passes unchanged.
- Existing `test_workflow_state_machine.py` passes unchanged.
- Existing `test_workflow_run_lifecycle.py` passes unchanged.
- Existing `test_schema_validator.py` passes unchanged.
- `ruff check .` passes with zero new violations.
- `mypy app/` passes with zero new errors.

---

## 16. Risks, Ambiguities, and Product Owner Decisions

### 16.1 Risk: Stale documentation baseline

**Risk:** The governance documents (`ACTIVE_WORK.md`, `next_steps.md`) are reconciled against PR #69, not the current `origin/main` at `d82b9aa` (PR #72). They still say 03C is "NOT AUTHORIZED" / "NOT IMPLEMENTED." A fresh session reading these documents would get incorrect context.

**Mitigation:** A separate post-03C-merge status-sync PR should be created before or alongside 03D implementation. This is the same pattern as PR #66 (post-03B sync) and PR #68 (post-WP-STRAT-01 sync).

**PO decision required:** Should the status-sync PR be created before 03D implementation begins, or can 03D implementation proceed with the understanding that the sync will follow?

### 16.2 Risk: `llm_max_retries` semantics ambiguity

**Risk:** While the evidence strongly supports "retries after initial attempt" (total = 1 + N), the config field has no docstring explicitly stating this. A developer might interpret it as "total attempts."

**Mitigation:** 03D implementation must include a clear docstring in `retry_policy.py` and `outage_handler.py` stating: "`llm_max_retries` is the number of retries after the initial attempt. Total provider calls = 1 + llm_max_retries."

**PO decision required:** None — the semantics are derivable from existing evidence (field name, OpenAI SDK convention, provider docstring). This is a planning clarification, not a new decision.

### 16.3 Ambiguity: Retry metadata in WorkflowStep

**Ambiguity:** Should retry attempt details (count, per-attempt error types, backoff delays) be persisted in `WorkflowStep.step_metadata`, or only in logs?

**Current design:** On success, retry count and safe metadata flow through `ChatResult.metadata` → `step.step_metadata`. On failure, retry details are in logs only (the step's `error_code` and `error_detail` are the safe classification, not retry details).

**Alternative:** Modify `engine.py` to extract retry metadata from the exception and store it in `step_metadata`. This would require changing the permitted-file list.

**Recommendation:** Keep the current design (no engine modification). Retry details in logs with `correlation_id` and `run_id` provide full traceability (FR-07). The step records the overall outcome. If the PO wants per-attempt step records, that would be a scope change requiring a new decision.

**PO decision required:** None if the current design is accepted. If the PO wants per-attempt WorkflowStep records, a new decision is required (scope change, engine modification).

### 16.4 Ambiguity: `llm_max_retries` config source

**Ambiguity:** The `RetryingChatProvider` needs to read `llm_max_retries` from `Settings`. The decomposition doc says 03D's permitted files do not include `config.py`. The `RetryingChatProvider` can receive `max_retries` as a constructor parameter (injected by the caller/factory), avoiding any config.py modification.

**Resolution:** `RetryingChatProvider.__init__` accepts `max_retries: int` as a parameter. The caller (future 03F worker or test) reads it from `Settings` and passes it in. No config.py modification needed. This is consistent with the `OpenAIChatProvider` pattern (constructor receives config values, does not read `Settings` directly).

**PO decision required:** None.

### 16.5 No new dependencies

No new dependencies are introduced. The backoff contract uses only `asyncio.sleep` and standard Python. `pyproject.toml` is not modified.

### 16.6 No new migrations

No database schema changes. No new Alembic migration. 03D uses existing `WorkflowRun` and `WorkflowStep` models unchanged.

### 16.7 No architecture/scope change

The `RetryingChatProvider` wrapper is a clarification of the existing `ChatProvider` ABC design (03A). The ABC was designed for transparent wrapping (the `FakeChatProvider` is already a wrapper-like implementation). Adding a retrying wrapper is the expected use of the ABC, not an architecture change.

---

## 17. Recommended Branch Name and Commit Structure

### 17.1 Branch name

```
feature/phase-5-wp-rec-03d-provider-retry-outage
```

Following the established naming pattern: `feature/phase-5-wp-rec-03{X}-{description}`.

### 17.2 Commit structure

One commit (or two if the PO permits documentation correction):

**Commit 1 (implementation):**
```
feat(ai): WP-REC-03D — automatic provider retry/outage handling

Add RetryingChatProvider that wraps ChatProvider with bounded
exponential backoff retry for transient failures. Permanent and
configuration errors are not retried. After retries are exhausted,
TransientChatProviderError surfaces to the existing engine, which
transitions the workflow run to FAILED_PROVIDER.

New files:
- backend/app/ai/workflow/retry_policy.py — pure backoff calculation
  with injectable sleeper for deterministic tests
- backend/app/ai/workflow/outage_handler.py — RetryingChatProvider
  wrapping a delegate ChatProvider with retry logic
- backend/tests/unit/test_retry_policy.py
- backend/tests/unit/test_outage_handler.py
- backend/tests/integration/test_provider_outage.py

No existing production file modified. No new dependencies. No new
migrations. SDK retries remain disabled (max_retries=0) to prevent
nested retry. llm_max_retries means retries after the initial attempt
(total calls = 1 + llm_max_retries).

AT-013 is NOT PASS after 03D alone — backend retry only.
```

**Optional Commit 2 (documentation correction, if PO permits):**
```
docs: correct AT-013 PASS timing in 03D section

Line 486 said "AT-013 becomes PASS only after 03F" but the accepted
sequence requires 03F + 03G (UI clauses). Corrected to match lines
110, 819, and 848.
```

---

## 18. Realistic Verdict

### READY FOR BOUNDED IMPLEMENTATION

**Conditions:**

1. The PO explicitly authorizes WP-REC-03D implementation.
2. A post-03C-merge status-sync PR (or the 03D PR itself) updates `ACTIVE_WORK.md`, `next_steps.md`, and the decomposition doc's 03C §15 to reflect 03C completion. This should ideally happen before or alongside 03D implementation.
3. The PO confirms the `RetryingChatProvider` wrapper design (no engine modification) is acceptable.
4. The PO confirms that retry attempt details in logs (not in per-attempt `WorkflowStep` records) satisfies FR-07 traceability.

**No blocking architectural decisions are required.** The design is derivable from:
- The existing `ChatProvider` ABC (03A) designed for wrapping.
- The existing engine exception handling (03B) that correctly processes `TransientChatProviderError` → `FAILED_PROVIDER`.
- The existing `llm_max_retries` config field (03A).
- The existing safe-error persistence pattern (03B).
- DEC-013's retry ownership assignment: "Automatic backend retry: WP-REC-03D."

---

## 19. Proposed Implementation Prompt (DO NOT EXECUTE)

```text
TASK: WP-REC-03D — Automatic Provider Retry/Outage (Backend)

GOAL
Implement backend automatic retry and outage handling for transient
AI provider errors. When the provider is temporarily unavailable,
transient failures are retried with bounded exponential backoff.
Permanent failures are not retried. After retries are exhausted,
the workflow run reaches FAILED_PROVIDER. No secret, provider
payload, or unsafe raw error text is persisted or logged.

BUSINESS REASON
When the AI provider is temporarily unavailable, deterministic risk
results must remain available (architectural invariant — DEC-004,
Phase 2 complete, AT-004 PASS). Transient provider failures must be
retried according to a bounded policy. Permanent failures must not be
retried. The workflow must reach a controlled FAILED_PROVIDER state
after exhaustion.

IN SCOPE
- backend/app/ai/workflow/retry_policy.py (NEW)
- backend/app/ai/workflow/outage_handler.py (NEW)
- backend/tests/unit/test_retry_policy.py (NEW)
- backend/tests/unit/test_outage_handler.py (NEW)
- backend/tests/integration/test_provider_outage.py (NEW)

OUT OF SCOPE
- No modification to engine.py, state_machine.py, or any existing
  production file
- No modification to config.py (max_retries passed as constructor arg)
- No new dependencies, migrations, or config fields
- No user-initiated retry API (03F)
- No frontend changes (03E/03G)
- No approval/audit logic (Phase 6)
- No RAG integration (WP-REC-05)
- AT-013 is NOT PASS after 03D

FILES ALLOWED TO CHANGE
- backend/app/ai/workflow/retry_policy.py (new)
- backend/app/ai/workflow/outage_handler.py (new)
- backend/tests/unit/test_retry_policy.py (new)
- backend/tests/unit/test_outage_handler.py (new)
- backend/tests/integration/test_provider_outage.py (new)

FILES FORBIDDEN TO CHANGE
- All files under forgemind_project_source_of_truth/
- backend/app/ai/workflow/engine.py
- backend/app/ai/workflow/state_machine.py
- backend/app/ai/workflow/schema_validator.py
- backend/app/ai/workflow/prompts.py
- backend/app/ai/provider/ (all files)
- backend/app/models/workflow.py
- backend/app/schemas/ (all files)
- backend/app/config.py
- backend/alembic/ (all files)
- backend/pyproject.toml
- .github/workflows/
- Makefile
- docker-compose*.yml
- frontend/ (all files)
- docs/ACTIVE_WORK.md
- docs/next_steps.md
- docs/planning/wp_rec_03_decomposition.md
- scripts/agent-loop/
- .agent-loop/

DESIGN CONTRACT

1. RetryPolicy (retry_policy.py):
   - Dataclass with: base_delay=1.0, max_delay=30.0, max_retries (int),
     sleeper (Callable[[float], Awaitable[None]], defaults to asyncio.sleep)
   - Method: compute_delay(attempt_index: int) -> float
     Formula: min(base_delay * (2 ** attempt_index), max_delay)
   - Method: should_retry(attempt_number: int, exc: Exception) -> bool
     Returns True only for TransientChatProviderError and only if
     attempt_number < max_retries
   - Pure calculation — no side effects, no I/O

2. RetryingChatProvider (outage_handler.py):
   - Class extending ChatProvider
   - Constructor: delegate (ChatProvider), policy (RetryPolicy),
     clock (optional, defaults to time.monotonic)
   - async complete(prompt, schema, context) -> ChatResult:
     a. Call delegate.complete(prompt, schema, context) [attempt 0]
     b. On success: return ChatResult with retry metadata in .metadata
        (retry_count, attempt_history with safe fields only)
     c. On TransientChatProviderError:
        - If should_retry: log attempt, compute backoff, sleep, retry
        - If not should_retry (exhausted): log final failure, raise
          TransientChatProviderError
     d. On PermanentChatProviderError: log, raise immediately (no retry)
     e. On ChatProviderConfigurationError: log, raise immediately
     f. On CancelledError: propagate immediately (do not catch)
     g. On any other Exception: propagate immediately (do not catch)
   - Logging: structured log per attempt with correlation_id, run_id,
     attempt_number, total_allowed_attempts, error_type (class name only),
     backoff_delay_seconds, outcome. NEVER log exception messages,
     response bodies, API keys, or secrets.
   - llm_max_retries semantics: retries after initial attempt.
     Total calls = 1 + max_retries. max_retries=0 means single attempt.

ACCEPTANCE CRITERIA
- TransientChatProviderError retried up to max_retries times with
  exponential backoff, then FAILED_PROVIDER
- PermanentChatProviderError not retried, immediate FAILED_PROVIDER
- ChatProviderConfigurationError not retried
- StructuredOutputValidationError never caught or retried (not a
  ChatProviderError subclass)
- CancelledError propagates immediately
- No real waiting in tests (injectable sleeper)
- No secret leakage in logs (exception type name only, never message)
- Existing workflow engine tests pass unchanged (regression)
- ruff check . passes
- mypy app/ passes
- AT-013 is NOT PASS after 03D

COMMANDS TO RUN
cd backend
../.venv/bin/ruff check .
../.venv/bin/mypy app/
../.venv/bin/pytest tests/unit/test_retry_policy.py tests/unit/test_outage_handler.py -v
export DATABASE_URL="postgresql+asyncpg://forgemind:PASSWORD@localhost:5432/forgemind"
export TEST_DATABASE_URL="$DATABASE_URL"
../.venv/bin/pytest tests/integration/test_provider_outage.py -v
../.venv/bin/pytest tests/unit/test_workflow_engine.py tests/unit/test_workflow_state_machine.py tests/integration/test_workflow_run_lifecycle.py -v
../.venv/bin/pytest -v  # full suite regression

STOP CONDITIONS
- Stop if any existing test fails (regression)
- Stop if ruff or mypy reports new errors
- Stop if the design requires modifying engine.py (scope change)
- Stop if a new dependency is needed (justify or find alternative)
- Stop if the PO has not explicitly authorized 03D implementation

COMMIT REQUIREMENT
Conventional commit: feat(ai): WP-REC-03D — automatic provider retry/outage handling
One commit for implementation. No push, no PR, no merge without PO approval.
```

---

## Summary

This reconnaissance confirms that WP-REC-03D is **READY FOR BOUNDED IMPLEMENTATION**. The design is a clean provider-wrapper pattern (`RetryingChatProvider`) that requires no modification to any existing production file. The decomposition doc's permitted-file list is correct and executable. The only pre-implementation requirement is a post-03C-merge status-sync PR to update stale governance documents, and explicit PO authorization.

No blocking architectural decisions remain. The retry ownership, semantics, classification, backoff, state transitions, security, and test feasibility are all fully resolved by the existing 03A/03B/03C implementation contracts.
