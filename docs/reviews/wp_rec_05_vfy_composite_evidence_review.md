# WP-REC-05-VFY — Composite Evidence Review

**Artifact type:** Independent composite evidence review
**Status:** Supplied to and accepted by the Product Owner (acceptance recorded separately)
**Date of Product Owner acceptance:** 2026-08-15

This document records the independent composite evidence review over the two sealed
WP-REC-05-VFY evidence packages. It is the durable record of the review that the
Product Owner used as the basis for the separate acceptance decision. This review
was supplied by the independent reviewer and accepted by the Product Owner; it is
not authored by the Hermes agent.

The review itself did **not** declare AT-006 or AT-007 PASS. PASS was declared only
through the later, explicit Product Owner acceptance decision (recorded in
`docs/reviews/wp_rec_05_phase_4_product_owner_acceptance.md` and the Decision Log).

---

## 1. Repository and source identities

| Item | Value |
|------|-------|
| Repository remote | `https://github.com/Tihonya/forgemind-ai-operations.git` |
| Authoritative GitHub `main` | `67844235c6ec412b11e9868451f41994142b86fc` |
| `origin/main` | `67844235c6ec412b11e9868451f41994142b86fc` |
| PR #93 state | MERGED |
| PR #93 merge commit | `67844235c6ec412b11e9868451f41994142b86fc` |
| PR #93 parents | `0db602d864dabde2f21ac83e84a5ad836619c411`, `b90d357e6f01fb2cafacafd78fd1734faa72e685` |
| PR #93 title | `fix(ai): replace deprecated Groq default model` |
| PR #93 merged at | 2026-08-14T22:46:28Z |

The two-parent merge structure was verified (a third parent does not exist), and the
GitHub API, `origin/main`, and the local worktree all resolve to the same commit.

## 2. Evidence run identities

| Attribute | Previous package | Current package |
|-----------|------------------|-----------------|
| Run ID | `wp-rec-05-vfy-20260814-01` | `wp-rec-05-vfy-20260815-02` |
| Authoritative source commit | `9add3b40f07b7669dced65dcca026468a09c6357` | `67844235c6ec412b11e9868451f41994142b86fc` |
| Aggregate SHA-256 | `f37f0ac8a6268dc95d2ef5b7216f3bc5c4d9f06aa2de3c9f8735bc0508b27177` | `2ce0ba6fc71ffed9d09f45dcea9c4dd898e4b5c967211df8d7717389716e9ec8` |
| Total package files | 26 | 32 |
| Files covered by aggregate | 25 (`aggregate-identity.json` excludes itself) | 31 (`aggregate-identity.json` excludes itself) |
| `manifest_complete` | `true` | `true` |

## 3. Integrity-verification results

Both sealed packages were verified read-only against the exact aggregate algorithm
(`'<sha256>  <relpath>'` lines, sorted by relpath, joined with `\n` plus one
trailing newline, then SHA-256 of the whole byte string):

- Previous package aggregate recomputes to `f37f0ac8…` — matches the pinned value and the recorded `aggregate_sha256` field.
- Current package aggregate recomputes to `2ce0ba6f…` — matches the pinned value and the recorded `aggregate_sha256` field.
- Per-file SHA-256 and byte counts: zero mismatches in both packages.
- Sealed permissions retained: all directories `555`, all payload files `444`.
- On-disk recursive file counts match `total_package_file_count` (26 and 32).

## 4. AT-006 evidence

**Previous package (incomplete):** the deterministic provider
(`FORGEMIND_ACCEPTANCE_SCENARIO=NORMAL_SUCCESS`) hard-codes `sources: []` and emits
no grounded citation. Assertion AT006-4 ("non-empty sources list") FAILED and
AT006-6 was PARTIAL — the correct M3 tuple was present in the retrieval allow-list
but was not persisted because the provider emitted no sources. This is why AT-006
was incomplete in the previous run.

**Current package (succeeds on current `main`):** live OpenRouter
`qwen/qwen3.7-flash` with `json_object` structured output. All 13 AT-006 assertions
SUCCEEDED. The workflow reached `COMPLETED`, the recommendation persisted with
`status=VALIDATED`, `schema_version=1.0`, and RISK-001 carried the exact M3 tuple:

```text
document_id = d0060000-0000-0000-0000-000000000006  (= str(Document.id))
version     = 1.0
chunk_id    = c0060000-0000-0000-0000-000000000006  (= KnowledgeChunk.id)
```

Per-risk citation validation succeeded; RISK-002 and RISK-003 `sources` remained
empty (no fabricated, duplicate, or cross-risk citation). The exact M3 tuple is
persisted.

## 5. Previous-package AT-007 evidence (exact canonical restricted-only Given)

The previous sealed package executes the exact canonical AT-007 Given:

1. The restricted answer exists only in the restricted document
   (`d0070000-…`, APPROVED, permission `PROCUREMENT_SPECIALIST`).
2. The user (`manager.demo`) has a non-empty effective role set
   (`PRODUCTION_MANAGER`).
3. No permitted document contains equivalent scenario material.
4. Retrieval returns zero accessible chunks (`result_count=0`,
   `accessible_document_count=0`).
5. Prompt retrieval context is empty
   (`serialize_retrieval_context([]) == "[]"`).
6. Restricted identity is absent from the response and the persisted
   Recommendation.

All 7 AT-007 negative assertions PASS. The run reached `COMPLETED` as a legitimate
ungrounded zero-result (not `AUTHORIZATION_CONTEXT_EMPTY`).

## 6. Current-package AT-007 discrimination evidence

The current package independently demonstrates on current `main` that permitted and
restricted documents with **equal similarity** are discriminated by role filtering.
The restricted document (`d0070000`, `PROCUREMENT_SPECIALIST` only) and the
permitted document (`d0060000`, `PRODUCTION_MANAGER`) were seeded with identical
query embeddings. `manager.demo` retrieved only `d0060000`; `d0070000` was excluded
by the `document_permissions` role join despite identical similarity. All 8 AT-007
assertions SUCCEEDED, including the log scan (`total_restricted_matches=0`).

This is a stronger negative proof than a pure zero-result: it proves the role filter
discriminates between a permitted and a restricted document with equal similarity.

## 7. Empty-role fail-closed evidence

Both packages demonstrate the empty-effective-role fail-closed boundary
(DEC-046): with an empty effective role set, retrieval is not executed, the run
transitions to `FAILED_RETRIEVAL` with `error_code=RETRIEVAL_FAILED` and
`error_detail=AUTHORIZATION_CONTEXT_EMPTY`, and no Recommendation is created.

In the current package all 7 empty-role control assertions SUCCEEDED, and the
control made **zero** provider calls — the global live HTTP attempt count remained
exactly 2 (AT-006 + AT-007).

## 8. Unchanged retriever and prompt blob identities

Byte-identical between the two source commits
(`9add3b40…` and `67844235…`):

| File | Git blob |
|------|----------|
| `backend/app/ai/rag/retriever.py` | `4d19603c894e6eabeb10722116fbe176f6e53b53` |
| `backend/app/ai/workflow/prompts.py` | `e10a67017ca684ba2ea0f67c2dd5630e74074244` |

Current `backend/app/ai/workflow/vertical.py` constructs the provider context only
from authorization-filtered retrieval results: the retrieval service returns only
role-filtered results, the citation allow-list is built from those results, and
`serialize_retrieval_context(retrieval_results)` supplies the prompt context.
Fail-closed authorization (empty role set, absent record, or mismatched generation)
short-circuits before retrieval and produces no provider call.

## 9. Provider / call-bound findings

Current package (formal rerun):

- Live OpenRouter `qwen/qwen3.7-flash`, structured output `json_object`.
- OpenRouter-only chain — no fallback member, no Groq member in the effective chain.
- Retries zero (`llm_max_retries=0`, `retry_policy_max_retries=0`, `sdk_max_retries=0`).
- Exactly two live OpenRouter HTTP attempts (AT-006 = 1, AT-007 = 1, empty-role = 0),
  within the "at most 2" global bound. `no_fallback=true`, `no_groq_request=true`.

## 10. Non-blocking review findings

These are recorded transparently and are **not** acceptance blockers:

1. The current package's AT-006/AT-007 worker logs were truncated when services
   were restarted for the empty-role control. Authoritative provider metadata is
   preserved in the persisted `workflow_steps.metadata`
   (`database-evidence-sanitized.json`) and per-scenario API evidence.
2. The current package's redaction statement is broader than the actual package:
   supporting scripts contain synthetic demo credentials / local database
   credentials and portions of synthetic restricted seed material, but no real
   provider API key, raw JWT, or external secret was found.
3. The current report's causal statement involving PR #93 is inaccurate: PR #93
   changed the Groq default, while the successful formal rerun was pinned only to
   OpenRouter.
4. The current package's AT-007 scenario is a strong permission-discrimination
   control but is not, alone, the literal restricted-only Given. The previous sealed
   package supplies that exact scenario.
5. Read-only filesystem permissions (`444`/`555`) are not equivalent to an OS
   immutable attribute; integrity is anchored by the verified aggregate hashes.

## 11. Composite verdict

The independent composite review verdict is:

```text
APPROVE — COMPOSITE EVIDENCE IS SUFFICIENT FOR A SEPARATE PRODUCT OWNER ACCEPTANCE DECISION
```

Composite reasoning:

1. The current package proves AT-006 on current `main` using live OpenRouter and
   persists the exact M3 tuple.
2. The previous package executes the exact canonical AT-007 Given (restricted-only
   scenario, empty prompt retrieval context, restricted identity absent).
3. The current package independently demonstrates on current `main` that permitted
   and restricted documents with equal similarity are discriminated by role
   filtering.
4. `backend/app/ai/rag/retriever.py` is byte-identical between the two source
   commits (blob `4d19603c894e6eabeb10722116fbe176f6e53b53`).
5. `backend/app/ai/workflow/prompts.py` is byte-identical (blob
   `e10a67017ca684ba2ea0f67c2dd5630e74074244`).
6. Current `vertical.py` constructs provider context only from
   authorization-filtered retrieval results.
7. Taken together, the packages cover the canonical restricted-only case,
   current-main filtering behavior, live grounded output, citation validation, and
   empty-role fail-closed behavior.

## 12. PASS boundary

This review is evidence only. It did **not** declare AT-006 or AT-007 PASS. The
declaration of `AT-006 PASS` and `AT-007 PASS` occurred only through the later,
explicit Product Owner acceptance decision of 2026-08-15, recorded separately in
`docs/reviews/wp_rec_05_phase_4_product_owner_acceptance.md` and in the Decision
Log.
