# WP-REC-05 — RAG Integration into the Controlled AI Workflow (Decomposition and Planning)

This is the complete standalone planning artifact for the RAG-integration work
package. It is **planning only**. It does not authorize implementation,
verification, evidence generation, or any later phase.

---

## A. Identity and authority

| Field | Value |
|-------|-------|
| Planning package | **WP-REC-05-DEC** — RAG Integration Decomposition and Planning |
| Planned downstream implementation package | **WP-REC-05** |
| Planned separate verification package | **WP-REC-05-VFY** |
| Authoritative base commit | `18d6ac6f4ebadbab4040e89146c4f559948f0fa3` |
| Product Owner authorization date | 2026-08-14 |
| Authorization scope | **Planning only** |

The Product Owner authorization is recorded exactly in substance as:

> Авторизую planning-only package WP-REC-05-DEC. Приймаю послідовність: спочатку окрема реалізація WP-REC-05, потім окрема bounded verification AT-006/AT-007. Реалізацію та verification цим рішенням не авторизую.

**Only planning is authorized.** The following are NOT authorized by this
package:

- WP-REC-05 implementation;
- test implementation;
- AT-006 or AT-007 execution;
- formal evidence generation;
- Product Owner acceptance of Phase 4;
- Phase 6 or Phase 7 work.

This authorization is recorded in the Decision Log as DEC-044.

---

## B. Current verified baseline

The baseline was verified against `origin/main @ 18d6ac6…` (merge commit of
PR #86, parents `686739f…` and `6aee638…`). The following statements are
precise and cite exact repository paths and symbols.

1. **Retrieval service exists.** `backend/app/ai/rag/retriever.py` defines
   `RetrievalService.retrieve(session, query_embedding, allowed_role_ids,
   top_k)` — cosine similarity over `knowledge_chunks` via pgvector, ordered
   by similarity DESC with deterministic tie-breakers, with access filtering
   enforced inside the SQL via a `document_permissions` join (WP-4.4B). The
   immutable `RetrievalResult` dataclass carries `document_id`, `version_id`,
   `chunk_id`, `chunk_index`, `chunk_text`, `metadata`, `similarity`.

2. **Citation structures exist.** `backend/app/ai/rag/citations.py` defines
   the immutable `Citation` dataclass (`document_id`, `version_id`, `chunk_id`,
   `chunk_index`, `similarity`) and `build_citation(result)`.

3. **Role filtering exists at retrieval service/API level.**
   `backend/app/api/retrieval.py` (`POST /api/v1/retrieval`) derives role IDs
   server-side from `current_user.roles` via `_resolve_role_ids` and calls
   `RetrievalService.retrieve` with those `allowed_role_ids`. The SQL filters
   `dv.status = 'APPROVED'` and requires a matching `document_permissions`
   row for one of the allowed roles.

4. **Workflow integration does not exist.** The controlled AI workflow does
   not call the retriever. `backend/app/ai/workflow/vertical.py`
   (`execute_workflow`) proceeds directly from deterministic risk calculation
   (step 4) to prompt construction (`build_system_prompt`) and provider
   invocation (step 5), then validation (step 6) and persistence (step 7).
   There is no retrieval step.

5. **`vertical.py` goes from risk calculation to prompt/provider without a
   retrieval step.** Confirmed: `execute_workflow` calls
   `build_system_prompt(plan_id=plan_code, run_id=…, risk_data=…)` and then
   `provider.complete(prompt=prompt, …)`. `build_system_prompt` (in
   `backend/app/ai/workflow/prompts.py`) accepts only `plan_id`, `run_id`, and
   `risk_data`; it has no retrieval-context parameter.

6. **Recommendation schema already includes source identity.**
   `backend/app/schemas/recommendation.py` defines `Source(document_id: str,
   version: str, chunk_id: UUID)` and `RiskItem.sources: list[Source]`
   (required, may be empty). The docstring states that empty `sources` means
   the recommendation is not grounded and must never be described or logged as
   grounded. The wire `document_id`/`version` fields are **string** fields
   (`Source.document_id` documented as "External document identifier"), while
   the retrieval citation identity is in **UUID** space
   (`Citation.document_id`, `Citation.version_id`). This mapping gap is
   addressed in §G.

7. **AT-006 and AT-007 are not PASS.** `forgemind_project_source_of_truth/
   04_ACCEPTANCE_TESTS.md` carries no PASS status for AT-006 or AT-007.
   The requirements traceability matrix records them as "IMPLEMENTED — NOT
   VERIFIED AS PASS" (AT-006) and "IMPLEMENTED AT SERVICE/API LEVEL — NOT
   VERIFIED AS AT-007 PASS" (AT-007).

8. **Phase 4 is PARTIALLY COMPLETE.** Recorded in DEC-034 and preserved by
   DEC-043.

9. **WP-REC-05 implementation is not authorized.** Recorded in DEC-037 and
   preserved by DEC-043.

10. **Deterministic risk result survives provider failure.** Already
    implemented in `execute_workflow`: risk calculation is persisted
    independently of provider success (AT-013 pattern).

11. **The Golden Scenario step 6 is the earliest incomplete critical-path
    step.** `01_PRODUCT_AND_MVP_SCOPE.md` §2 step 6: "RAG шукає лише доступні
    користувачеві документи про альтернативні компоненти." Steps 1–5 are
    implemented; step 6 (workflow-embedded RAG retrieval over accessible
    documents) is the first unfulfilled step.

12. **Phase 5 is ACCEPTED** (AT-008 PASS, AT-013 PASS; Product Owner
    acceptance 2026-08-14, DEC-043; accepted evidence run
    `wp-rec-03h-phase-c-20260813-02`).

13. **Release 1 is NOT READY and NOT DEPLOYED.**

14. **Phase 6 and Phase 7 are not authorized and not completed.**

15. **F3–F8 and SP-0B are deferred and are not Release 1 blockers.**

---

## C. Dependency boundary

- **WP-REC-03F is complete** and satisfies the workflow-pipeline prerequisite:
  the start/retry API (`backend/app/api/workflow.py`), ARQ worker
  (`backend/app/ai/workflow/worker.py`), and vertical wiring
  (`backend/app/ai/workflow/vertical.py`) are all merged. WP-REC-05 can only
  exist because the controlled workflow pipeline now exists.
- **WP-REC-05 precedes Phase 6 under DEC-037**: Phase 6 (approval/audit)
  requires RAG citations in recommendations; WP-REC-05 delivers the workflow
  integration that makes citations real.
- **WP-REC-05 implementation precedes WP-REC-05-VFY**: the separate bounded
  verification package (DEC-035) executes against the implemented, integrated
  workflow. Verification cannot precede the implementation it verifies.
- **WP-REC-05-VFY remains separate from implementation**: DEC-035 mandates a
  bounded verification package distinct from the implementation package.
- **Phase 4 cannot close** until both WP-REC-05 implementation exists AND
  accepted AT-006/AT-007 PASS evidence exists (from WP-REC-05-VFY). Neither
  is authorized by this planning package.

The fixed sequence (also recorded in DEC-044 and §L) is:

```
WP-REC-05 implementation → separate WP-REC-05-VFY bounded verification
→ separate Product Owner Phase 4 acceptance/closure
```

---

## D. Full 15-attribute implementation specification for WP-REC-05

This specification is **implementation-ready but does not authorize
implementation**.

### D1. Stable ID and title

**WP-REC-05** — RAG Integration into the Controlled AI Workflow.

### D2. Objective

Wire the existing role-filtered retrieval service and citation structures into
the controlled AI workflow (`execute_workflow`) so that, after deterministic
risk calculation, the workflow:

1. derives a deterministic retrieval query for the risks;
2. retrieves only chunks accessible to the initiating user's roles;
3. serializes accessible chunks into the model prompt;
4. constrains the model to cite only retrieved chunks;
5. persists grounded `sources` validated against the retrieved allow-list.

### D3. Outcome type and user-visible behavior

- **Outcome type:** backend implementation (deterministic orchestration,
  prompt construction, citation integrity, workflow-step trace), plus a schema
  migration for authorization-context persistence.
- **User-visible behavior:** for a Golden Scenario run, the produced
  recommendation's `sources` are populated from documents the initiating user
  is actually permitted to see; restricted documents never appear; empty
  `sources` are surfaced as ungrounded (not silently presented as grounded).
  This closes Golden Scenario step 6.

### D4. Exact included scope

1. Retrieval orchestration inside the workflow (trigger, granularity, query
   construction, result bounds) — §F.
2. Server-derived authorization-context persistence from the authenticated
   start/retry request into the background worker (migration) — §F, §H.
3. Deterministic prompt construction that injects accessible retrieved chunks
   with their citation identities — §F.
4. Citation-integrity validation of persisted `sources` against the retrieved
   allow-list — §G.
5. Retrieval workflow-step trace records — §I.
6. Implementation tests specified in §J.

### D5. Explicit exclusions

- No WP-REC-05-VFY execution (separate package, §K).
- No AT-006/AT-007 formal execution or PASS claim.
- No Phase 6 work (approval service, audit event service, procurement task
  service, approval/audit UI).
- No Phase 7 work (deployment, rate limiting, backup/restore, runbooks, demo
  reset).
- No change to the deterministic risk engine or its outputs.
- No change to the provider/retry/outage contracts (WP-REC-03A/03D).
- No change to the structured-output wire schema's deterministic-value rules
  (DEC-004/039).
- No frontend change unless a later authorized slice requires it; the default
  WP-REC-05 scope is backend-only.
- No new external dependency.

### D6. Exact permitted repository areas

Confirmed by reconnaissance. Final allowlist is set at implementation
authorization; the expected areas are:

- `backend/app/ai/workflow/vertical.py` (insert retrieval step)
- `backend/app/ai/workflow/prompts.py` (extend prompt to carry retrieval context)
- `backend/app/ai/rag/retriever.py` (read; possibly a bounded query-construction helper)
- `backend/app/ai/rag/citations.py` (citation allow-list construction)
- `backend/app/models/workflow.py` (authorization-context persistence)
- `backend/app/api/workflow.py` (resolve + persist role context at start/retry)
- `backend/app/schemas/recommendation.py` (bounded `Source` identity-mapping clarification only, if required)
- a new Alembic migration file
- new backend tests under `backend/tests/` (implementation phase only)

Explicitly prohibited (in the WP-REC-05 implementation, mirroring this
planning package's prohibitions): Source of Truth documents, README.md, the
closed WP-REC-03/WP-REC-03H planning artifacts, frontend code (unless a later
slice is separately authorized), CI/infra, dependencies, evidence, and the
protected audit file.

### D7. Dependencies and predecessor gates

- WP-REC-03A–03G complete (workflow pipeline, provider, validator, persistence,
  start/retry API + worker, UI) — verified COMPLETE.
- WP-REC-03F complete — the ARQ worker and vertical wiring are live.
- Retrieval service, citations, document permissions, ingestion, embedding
  provider all exist (WP-4.x foundations).
- DEC-013 (workflow orchestration), DEC-011 (ARQ + Redis), DEC-040 (role-based
  document permissions), DEC-004/039 (deterministic ownership) all Accepted.

### D8. Relevant Source-of-Truth requirements and accepted decisions

- `02_SYSTEM_BEHAVIOR_AND_DATA.md` §6 — structured recommendation schema,
  including `sources` with document ID, version, chunk ID.
- `01_PRODUCT_AND_MVP_SCOPE.md` §2 step 6 — RAG searches only documents the
  user may access.
- `04_ACCEPTANCE_TESTS.md` — AT-006 (valid document ID, version, chunk ID in
  the answer), AT-007 (restricted chunk never reaches retrieval context or
  response).
- DEC-004 / DEC-039 — deterministic code owns facts; the LLM enriches, does
  not invent.
- DEC-035 — AT-006/AT-007 verification is a separate bounded package.
- DEC-037 — WP-REC-05 positioned after 03C–03G, before Phase 6.
- DEC-040 — role-based document permissions are the confirmed direction.
- DEC-044 — this planning authorization and the implementation-before-
  verification sequence.

### D9. Acceptance-test ownership and additional test contract

- WP-REC-05 owns the **implementation-completion** of the workflow path for
  AT-006 and AT-007 (see §J for the test contract).
- WP-REC-05-VFY owns the **formal execution** and accepted PASS evidence for
  AT-006 and AT-007 (see §K).
- WP-REC-05 must not claim AT-006 or AT-007 PASS; those statuses remain "not
  PASS" until WP-REC-05-VFY is executed and accepted by the Product Owner.

### D10. Failure behavior and rollback

- Retrieval failure, no-result, provider failure, and validation failure are
  specified in §F and §G. The deterministic risk result must remain persisted
  and independently available regardless of retrieval or provider outcome
  (consistent with the existing AT-013 contract).
- Rollback: WP-REC-05 changes are additive within the existing workflow
  vertical. There is no destructive migration; the authorization-context
  migration must be forward-compatible (additive column) with a downgrade that
  drops the added column without data loss to existing rows beyond the new
  provenance field.

### D11. Security and authorization constraints

Full contract in §H. Summary: server-derived authorization only; no
client-provided role trust; restricted chunks excluded before prompt
construction; no restricted content in logs or errors; fail-closed where the
AT-007 contract requires it.

### D12. Observability and trace requirements

Full contract in §I. A retrieval workflow-step record is required per run with
safe normalized metadata (correlation ID, run ID, query identity, result
count, accessible-document count, citation IDs, latency, success/failure, safe
error code). Phase 6 still owns the complete AT-012 audit contract.

### D13. Estimated size

- Backend implementation: moderate. The retrieval service, citations, embedding
  provider, and recommendation schema already exist; the core work is the
  workflow orchestration slice, prompt-construction extension, citation
  integrity check, authorization-context persistence, and one migration.
- Expected change set: ~4–6 existing files modified, ~1–2 new files, 1 new
  migration, and a bounded set of implementation tests (unit + integration).

### D14. Exact exit criteria

1. `execute_workflow` performs role-filtered retrieval between deterministic
   risk calculation and prompt construction.
2. The retrieval query is derived deterministically from risk data, server-side.
3. Retrieved chunks are serialized into the model prompt with their citation
   identities, bounded deterministically.
4. Persisted recommendation `sources` are validated against the retrieved
   allow-list; fabricated or unauthorized citations are rejected.
5. Restricted chunks never appear in prompts, responses, logs, or errors.
6. Empty `sources` are represented as ungrounded, never as grounded output.
7. Retrieval workflow-step trace records satisfy §I.
8. All §J implementation tests pass; no regression to AT-008/AT-013.
9. AT-006 and AT-007 remain not PASS (verification is separate).

### D15. Separate Product Owner authorization requirement

WP-REC-05 implementation is **NOT AUTHORIZED** by this planning package. A
separate, explicit Product Owner authorization decision is required before any
implementation begins.

---

## E. Anticipated file-level implementation scope

**Confirmed existing files likely to change:**

- `backend/app/ai/workflow/vertical.py` — insert the retrieval orchestration
  step between risk calculation (step 4) and prompt construction (step 5).
- `backend/app/ai/workflow/prompts.py` — extend `build_system_prompt` (and
  `SYSTEM_PROMPT_TEMPLATE`) to carry a retrieval context (accessible chunks +
  citation identities) with an explicit "cite only retrieved chunks" rule.
- `backend/app/ai/rag/citations.py` — build the authoritative citation
  allow-list from `RetrievalResult`s.
- `backend/app/models/workflow.py` — add authorization-context persistence on
  `WorkflowRun` (see migration status below).
- `backend/app/api/workflow.py` — resolve the authenticated user's role UUIDs
  at start/retry and persist them on the run for the worker.
- `backend/app/schemas/recommendation.py` — bounded clarification of the
  `Source` identity mapping only if the citation-integrity contract (§G)
  requires a docstring/semantics change; no schema-version bump.

**Possible new files:**

- `backend/app/ai/rag/orchestration.py` (or equivalent) — deterministic query
  construction + retrieval orchestration, if kept out of `vertical.py`.
- `backend/app/ai/rag/citation_validation.py` (or equivalent) — citation
  allow-list validation, if kept out of `vertical.py`/`schema_validator.py`.
- A new Alembic migration file for the authorization-context column.

**Files explicitly prohibited (implementation phase):**

- `forgemind_project_source_of_truth/` (all 9 documents).
- `README.md`.
- `docs/planning/wp_rec_03_decomposition.md`,
  `docs/planning/wp_rec_03h_acceptance_harness.md` (closed historical lifecycles).
- The two durable Phase D review/declaration reports.
- Frontend, CI, infra, dependency, evidence, and deployment files (unless a
  later separately-authorized slice adds frontend scope).
- The protected audit `docs/reviews/wp-rec-03f-post-pr76-readiness-audit.md`.

**Migration status: REQUIRED (with a Product Owner decision pending).**

Evidence: `WorkflowRun` (`backend/app/models/workflow.py`) persists only
`triggered_by` (a `String(100)` username, nullable) and `correlation_id`. It
persists **no** user ID foreign key and **no** role-identity column. The ARQ
worker (`backend/app/ai/workflow/worker.py`) receives only `run_id`; the worker
has no HTTP/authentication context. The retrieval service requires
`allowed_role_ids` (role UUIDs) to enforce AT-007 access filtering.

Therefore the initiating user's role context, which exists at the authenticated
start request (`backend/app/api/workflow.py` `start_workflow_run`,
`current_user.roles`), is **not** preserved into the background worker. A
migration is required to persist durable authorization/retrieval provenance.
The exact persistence strategy is a genuine Product Owner decision (see §M,
M1). The migration is not authorized by this planning package.

---

## F. Retrieval orchestration contract

### Trigger point in the workflow

After deterministic risk calculation succeeds and before prompt construction,
inside `execute_workflow` (`backend/app/ai/workflow/vertical.py`). The risk
result is already computed and persisted independently; retrieval is inserted
between that step and `build_system_prompt`.

### Retrieval granularity

**Per-risk.** Each `RiskItem` in the recommendation wire schema carries its own
`sources` list (`backend/app/schemas/recommendation.py`). Per-risk retrieval
(one bounded query per risk, identified by `component_code`/`component_name`)
maps retrieved chunks directly to the risk that cites them. This follows
unambiguously from the per-risk `sources` schema.

### Deterministic query construction

The query is **server-derived and deterministic** (DEC-004/039). For each
risk, build a query text from the deterministic risk fields — e.g.
`"alternative component for {component_code} {component_name}"` — and embed it
via the existing `EmbeddingProvider.embed_text`
(`backend/app/services/embedding_provider.py`). The query embedding is never
client-supplied; the workflow has no request body carrying an embedding. The
embedding dimension must match `EXPECTED_EMBEDDING_DIMENSION = 1536`
(`backend/app/ai/rag/retriever.py`).

### Role/access context

Server-derived from the persisted run's authorization context (§D15 / §M M1).
`allowed_role_ids` is the set of role UUIDs frozen at the authenticated
start/retry request. The worker passes this set to
`RetrievalService.retrieve`. No client-provided role is trusted.

### Accessible-document filtering

Enforced inside the existing retrieval SQL (`document_permissions` join +
`dv.status = 'APPROVED'`). Restricted documents are excluded before any chunk
reaches application code. `top_k` (default 10, bounded 1..100) is applied
**after** authorization filtering.

### Result ordering and bounds

Existing deterministic ordering (similarity DESC, then document/version/chunk
identity tie-breakers) is preserved. `top_k` bounds result count. Prompt size
is bounded by `top_k × max_chunk_text_length` (chunk_size default 1000 chars),
with an explicit per-chunk text truncation cap in the serializer. No unbounded
chunk text enters the prompt.

### Prompt construction

`build_system_prompt` is extended to accept a retrieval context: a bounded
JSON list of `{document_id, version, chunk_id, chunk_index, chunk_text}` plus
the authoritative citation allow-list. The prompt instructs the model to cite
**only** the supplied chunk identities and to leave `sources` empty when no
context is available. The existing rule "Do not fabricate document citations"
is preserved and strengthened.

### No-result behavior

When no accessible document is found (empty role set or no matching approved
chunks), `sources` is empty and the recommendation is explicitly ungrounded.
The run still completes; the retrieval step records `result_count = 0` and the
empty state is surfaced as ungrounded, never as grounded. (This follows the
existing wire-schema contract: empty `sources` = not grounded.)

### Retrieval-failure behavior

Retrieval failure (embedding provider error, database error, validation
error) is distinguished from no-result. The deterministic risk result remains
persisted and available. Whether the run then (a) fails closed with a safe
retrieval error code (retryable) or (b) degrades to an ungrounded
recommendation with explicit retrieval-failure metadata is a genuine Product
Owner decision — see §M, M2. The recommended default is **fail-closed** with a
safe, retryable retrieval error code, consistent with AT-013's "failed step is
visible and retryable" pattern.

### Retry behavior

A retry re-derives the authorization context from the retrying user and
re-runs retrieval fresh (new query embedding, new role set). Document-version
changes are naturally reflected because retrieval always filters on the
currently `APPROVED` version. There is no cross-run citation cache; the
citation allow-list is re-derived per run and per retry.

---

## G. Citation-integrity contract

### Authoritative citation allow-list

The allow-list is the set of `Citation` identities built deterministically
from the retrieval results for the run (`build_citation`, in
`backend/app/ai/rag/citations.py`). It is the **only** source of truth for
what may appear in persisted `sources`.

### Source identity fields

The authoritative retrieval identity is the UUID tuple `(document_id,
version_id, chunk_id)`. The wire `Source` schema
(`backend/app/schemas/recommendation.py`) carries `document_id: str`,
`version: str`, `chunk_id: UUID`. The deterministic mapping is:

- `Source.document_id` ← `str(document_id UUID)` (unique, stable);
- `Source.version` ← `DocumentVersion.version_number` (string, e.g. `"1.0"`);
- `Source.chunk_id` ← `KnowledgeChunk.id` (UUID, already matches).

Note: the `Source.document_id` docstring's "external document identifier
(e.g. 'DOC-…')" predates the current document model; documents carry a UUID
`id` and a `title`, no external code. The mapping above is deterministic and
unambiguous. WP-REC-05 implementation may record a bounded docstring
clarification but must not bump the schema version.

### Validation against retrieved chunks

After `validate_structured_output` succeeds, a deterministic post-validation
step verifies every `Source` in every `RiskItem.sources` against the run's
allow-list. Any `chunk_id`/`document_id`/`version` that does not match an
allow-listed citation is rejected.

### Rejection of fabricated or unauthorized citations

A `Source` whose identity is not in the allow-list is fabricated or
unauthorized. The run must not persist it. The rejection path maps to a
validation/retrieval-integrity failure with a safe, bounded error code; raw
model output and any fabricated identity are never logged or returned.

### Persistence representation

Persisted citations live in `Recommendation.content.sources` (already part of
the wire schema). Retrieval provenance (allow-list) is recorded in the
retrieval workflow-step metadata (§I). The recommendation row and its step
trace are linked by `run_id` and `correlation_id`.

### Frontend/API compatibility

The read-only workflow-run detail API (`backend/app/api/workflow.py`) already
validates persisted `Recommendation.content` against the typed wire schema and
surfaces `sources`. No API contract change is required to display grounded
citations; the existing `Source` fields are preserved.

### Empty `sources` ≠ grounded

Empty `sources` must never be represented, logged, or surfaced as grounded
output. The wire schema and prompt already encode this rule; WP-REC-05 enforces
it operationally (empty allow-list → empty sources → explicit ungrounded
state).

---

## H. Security contract

1. **Authorization context is server-derived.** Role identity comes only from
   the authenticated request (`get_current_user` / `require_role`), resolved to
   role UUIDs server-side, and persisted on the run for the worker. No client
   may supply its own roles.
2. **No client-provided role trust.** The workflow never reads roles from a
   request body, query parameter, or model output.
3. **Restricted chunks excluded before prompt construction.** The
   `document_permissions` join in the retrieval SQL guarantees restricted
   chunks never enter the result set, hence never reach the prompt.
4. **No restricted content in logs or error details.** Retrieval logs carry
   only safe normalized metadata (IDs, counts, latency, error code) — never
   chunk text, document titles of restricted content, or model output.
5. **No secret exposure.** The workflow continues to expose no API keys,
   credentials, or provider payloads. Embedding/chat providers are constructed
   through existing factories that already enforce environment rules.
6. **Fail-closed behavior** where the AT-007 contract requires it: if role
   identity is absent or unresolvable at start time, the run must not execute
   retrieval with an empty/privileged role assumption; it must fail closed or
   produce zero accessible results (per the chosen persistence strategy, §M M1).

---

## I. Observability contract

WP-REC-05 adds a retrieval workflow-step record (`step_name = "retrieval"`)
per run, using the existing `WorkflowStep` model
(`backend/app/models/workflow.py`). Required safe metadata (in
`step_metadata` JSONB and/or bounded columns):

- correlation ID (`correlation_id`);
- run ID (`run_id`);
- query identity or safe normalized metadata (e.g. risk IDs queried, never
  full query embeddings or raw chunk text);
- result count (`result_count`);
- accessible-document count (`accessible_document_count`);
- citation IDs (the allow-list identities — document/version/chunk IDs);
- latency (`latency_ms`);
- success/failure (`status`);
- safe error code (`error_code`, e.g. `RETRIEVAL_FAILED`, `RETRIEVAL_EMPTY`).

No restricted content appears in logs. This satisfies the retrieval-leg of the
AT-012 audit trace for the workflow path, but **does not claim AT-012
completion** — Phase 6 still owns the complete audit contract (user action,
approval, human decision, write action).

---

## J. Implementation test contract (WP-REC-05 — later, not now)

The following tests are required for WP-REC-05 implementation. **No test is
created or run in this planning task.**

1. Workflow invokes retrieval between risk calculation and provider call.
2. Accessible citations reach the provider prompt context.
3. Persisted recommendation `sources` match the retrieved allow-list.
4. Restricted chunks never reach the prompt or the response.
5. Fabricated source identity is rejected.
6. Zero-result behavior yields empty `sources` marked ungrounded.
7. Retrieval-failure behavior follows the chosen contract (§M M2).
8. Retry re-derives authorization context and re-runs retrieval.
9. Deterministic risk result survives retrieval/provider failure (no
   regression to AT-013).
10. No regression to AT-008/AT-013.
11. Authorization context is server-derived and durable (persisted on the run,
    used by the worker).

Existing reusable tests (no new test file creation required to reuse them):
`backend/tests/unit/test_retriever.py`,
`backend/tests/unit/test_citations.py`,
`backend/tests/integration/test_retriever_access_filtering.py`,
`backend/tests/integration/test_retriever_vector_query.py`,
`backend/tests/integration/test_retrieval_api.py`,
`backend/tests/integration/test_at006_rag_retrieval.py`.

---

## K. Separate WP-REC-05-VFY contract

WP-REC-05-VFY is the separate bounded verification package that executes
AT-006 and AT-007 end-to-end and produces accepted PASS evidence.

**WP-REC-05-VFY is NOT AUTHORIZED.** This section defines the contract; it
does not authorize or execute it.

### AT-006 end-to-end scenario

Given an approved document describing an alternative component, when the
workflow searches for mitigation, the produced recommendation must contain a
valid `document_id`, `version`, and `chunk_id` matching the retrieved
allow-list.

### AT-007 end-to-end restricted-document scenario

Given a user without access to a restricted document, when that user runs a
workflow whose answer exists only in that document, the restricted chunk must
not appear in the retrieval context, prompt, response, or logs.

### Authenticated role identities

The verification uses the seeded demo accounts and roles (DEC-028) to exercise
distinct role access levels (public / internal / restricted, DEC-040).

### Exact expected source fields

- document ID (deterministic identity per §G);
- version (`DocumentVersion.version_number`);
- chunk ID (`KnowledgeChunk.id`).

### Database/API/UI evidence required

- Persisted `Recommendation.content.sources` matching the allow-list;
- retrieval workflow-step record satisfying §I;
- workflow-run detail API returning typed `sources` with no integrity error.

### Prompt/retrieval-context evidence (safe/redacted)

Redacted evidence that accessible chunks reached the prompt context and that
restricted chunks are absent — with chunk text and restricted content
redacted, retaining only safe identity metadata.

### Negative evidence

Proof that restricted chunks are absent from retrieval context, prompt,
response, and logs (absence is the positive assertion of AT-007).

### Correlation and run identity

Each evidence artifact must be traceable to a `run_id` and `correlation_id`.

### Evidence integrity and redaction requirements

Follow the established formal-evidence discipline (aggregate hashes, manifest,
source-commit pinning) as used in WP-REC-03H Phase C.

### Product Owner acceptance boundary

AT-006 and AT-007 become PASS only by explicit Product Owner acceptance
declaration based on the unchanged evidence, exactly as AT-008/AT-013 were
accepted (DEC-043). Automated test results alone do not declare PASS.

---

## L. Accepted sequencing decision

The following sequence is **fixed** and must not be re-presented as open:

```
WP-REC-05 implementation
→ separate WP-REC-05-VFY bounded verification
→ separate Product Owner Phase 4 acceptance/closure
```

"Verification first" and "fold verification into implementation" are
**rejected** sequences. The Product Owner has already rejected them.

---

## M. Open decisions

Only genuine unresolved decisions discovered during planning are listed.
DEC-035, DEC-037, DEC-039, DEC-040, DEC-043, and the new sequencing decision
(DEC-044) are not reopened.

### M1. Authorization-context persistence strategy (migration)

- **Question:** How is the initiating user's role identity persisted so the
  background worker can enforce AT-007 role-filtered retrieval?
- **Options:**
  1. Persist a frozen snapshot of resolved role UUIDs on `WorkflowRun`
     (e.g. `authorized_role_ids` JSONB) at start/retry; worker uses the
     snapshot.
  2. Persist a `user_id` foreign key on `WorkflowRun`; worker re-resolves
     roles from the user at execution time.
  3. No migration; worker re-resolves roles from the stored `triggered_by`
     username at execution time.
- **Recommendation:** Option 1 — freeze the role snapshot at the authenticated
  request. It is durable, auditable, and independent of later role changes,
  and it avoids trusting a mutable username→role resolution at execution time.
- **Consequence:** Options 1 and 2 require a migration; option 3 does not but
  weakens the authorization guarantee (roles may change between start and
  execution; `triggered_by` is nullable for system runs).
- **Blocks WP-REC-05 implementation authorization?** Yes — the migration
  decision must be recorded before implementation.

### M2. Retrieval-failure behavior

- **Question:** When retrieval fails (embedding/database error) but
  deterministic risk calculation succeeds, does the run fail closed or degrade
  to an ungrounded recommendation?
- **Options:**
  1. Fail closed with a safe, retryable retrieval error code; deterministic
     risk result remains persisted and available (mirrors AT-013).
  2. Degrade to an ungrounded recommendation with empty `sources` and explicit
     retrieval-failure step metadata.
- **Recommendation:** Option 1 — fail closed. Phase 6 depends on grounded
  citations (DEC-037); silently producing an ungrounded recommendation on
  retrieval failure would under-deliver that dependency.
- **Consequence:** Option 1 adds a retrieval-failure terminal/retry path; the
  retry eligibility must include the new failure. Option 2 would allow runs to
  complete without grounding.
- **Blocks WP-REC-05 implementation authorization?** Yes — the failure
  behavior must be recorded before implementation.

---

## N. Lifecycle after planning

1. WP-REC-05-DEC documentation review (independent, read-only).
2. Bounded correction of this artifact if the review requires it.
3. Ready-for-Review transition (Product Owner).
4. Merge-only authorization for the planning PR.
5. Post-merge verification.
6. Separate Product Owner decision on WP-REC-05 implementation.
7. WP-REC-05 implementation (separately authorized).
8. Implementation verification and review.
9. Separate WP-REC-05-VFY (separately authorized).
10. Product Owner Phase 4 closure.

No step after step 1 is authorized by this planning task.
