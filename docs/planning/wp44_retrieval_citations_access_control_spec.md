# WP-4.4 — Retrieval, Citations and Access Control

## Document metadata

- **Status**: APPROVED_WITH_CORRECTIONS
- **Depends on**: WP-4.1 (document schema), WP-4.2 (knowledge chunks schema),
  WP-4.3A (ingestion core), WP-4.3B (ingestion integration)
- **Branch target**: feature/phase-4-wp-4-4-retrieval-citations-access-control
- **Created**: 2026-07-30
- **Base commit**: 88a7102b15a15fab0927cfaeb5c7f2b9e6708176
- **Product Owner approval**: 2026-07-30 (DEC-WP44-01 through DEC-WP44-05)

---

## 1. Purpose and Phase 4 relationship

This work package completes the remaining Phase 4 scope defined in
`07_ROADMAP.md § Phase 4`:

> Knowledge and RAG — deliverables: document ingestion, document versions/status,
> pgvector index, retrieval, access filtering, citations. Exit criteria: AT-006,
> AT-007 pass; evaluation fixtures created.

WP-4.3A and WP-4.3B delivered document ingestion, document versions/status,
and the pgvector index. WP-4.4 delivers retrieval, access filtering,
citations, evaluation fixtures and AT-006/AT-007 automation.

---

## 2. Current repository baseline (verified at 88a7102)

### 2.1 Existing retrieval-related code

| File | Content | Status |
|------|---------|--------|
| `backend/app/models/document.py` | `Document`, `DocumentVersion`, `DocumentPermission` | present |
| `backend/app/models/knowledge.py` | `KnowledgeChunk` with `Vector(1536)`, `chunk_index`, `chunk_text`, `metadata` JSONB | present |
| `backend/app/models/enums.py` | `DocumentVersionStatus` | present |
| `backend/app/models/user.py` | `User`, `Role`, `UserRole` | present |
| `backend/app/services/ingestion.py` | `IngestionOrchestrator` | present |
| `backend/app/services/embedding_provider.py` | `EmbeddingProvider` interface, OpenAI + fake | present |
| `backend/app/services/chunking.py` | `chunk_text()` | present |
| `backend/app/dependencies.py` | `get_current_user()`, `require_role()` | present |
| `backend/app/services/auth_service.py` | `AuthenticatedUser`, `resolve_token()` | present |
| `backend/tests/integration/test_rag_retrieval.py` | referenced in traceability matrix | **NOT PRESENT** |
| `backend/tests/integration/test_rbac.py` | referenced in traceability matrix | **NOT PRESENT** |

### 2.2 Missing components

1. **Retrieval service**: no vector similarity search function.
2. **Access-filtering query**: no join/filter against `document_permissions`.
3. **Citation construction**: no citation builder or response schema.
4. **Retrieval API endpoint**: no `/api/v1/retrieval` (or similar) route.
5. **Evaluation fixtures**: no deterministic Q&A dataset for AT-006/AT-007.
6. **AT-006 test**: not implemented.
7. **AT-007 test**: not implemented.
8. **pgvector index**: the `Vector(1536)` column exists but no IVFFlat/HNSW
   index has been created via Alembic migration. (Performance concern for
   retrieval; correctness is not blocked — sequential scan works.)

### 2.3 Literal AT-006 definition (from 04_ACCEPTANCE_TESTS.md)

```
## AT-006 — RAG retrieval

**Given:** approved document про альтернативу компонента
**When:** workflow шукає mitigation
**Then:** відповідь містить valid document ID, version і chunk ID.
```

English translation:

- **Given:** an approved document about a component alternative exists;
- **When:** the workflow searches for mitigation;
- **Then:** the response contains a valid document ID, version, and chunk ID.

### 2.4 Literal AT-007 definition (from 04_ACCEPTANCE_TESTS.md)

```
## AT-007 — Document access control

**Given:** користувач без доступу до restricted document
**When:** він ставить запит, відповідь на який є лише в цьому документі
**Then:** restricted chunk не потрапляє до retrieval context або response.
```

English translation:

- **Given:** a user without access to a restricted document;
- **When:** they make a query whose answer exists only in that document;
- **Then:** the restricted chunk does not appear in retrieval context or
  response.

---

## 3. Formal requirements mapping (from requirements_traceability_matrix.md)

| Req | Implementation (to build) | Test (to build) | AT |
|-----|---------------------------|-----------------|-----|
| FR-02 | `backend/app/ai/rag/retriever.py` — role-filtered retrieval | `tests/unit/test_rbac.py`, `tests/integration/test_rag_retrieval.py` | AT-007 |
| FR-05 | `backend/app/ai/rag/indexer.py`, `backend/app/ai/rag/retriever.py`, `backend/app/ai/rag/citations.py` | `tests/integration/test_rag_retrieval.py` | AT-006, AT-007 |

Note: the traceability matrix lists `indexer.py` under FR-05. Ingestion
(WP-4.3A/4.3B) already covers indexing. `indexer.py` should not duplicate
ingestion; it may either be a thin alias that the retrieval service calls,
or be omitted if the retrieval service is self-contained. Decision: **no
separate `indexer.py`**; the retrieval service calls `chunk_text` and the
embedding provider directly only for the query vector, and relies on
WP-4.3B for stored chunks.

---

## 4. AT-006 detailed scenario

### 4.1 Fixture requirements

1. Seed (or test fixture) creates one `Document` + `DocumentVersion` with
   `status = "APPROVED"` describing a component alternative.
2. The document is chunked and embedded; chunks are stored in
   `knowledge_chunks` with their embeddings.
3. A query string semantically close to the mitigation language is supplied
   to the retriever.
4. The retriever returns at least one result.
5. Each result contains:
   - `document_id` (UUID)
   - `document_version_id` (UUID)
   - `version_number` (string)
   - `chunk_id` (UUID)
   - `chunk_index` (int)
   - `similarity_score` (float in [0, 1])

### 4.2 Negative cases

- Unauthenticated request → 401.
- Query text too short (< 3 tokens) → 400 with `invalid_query`.
- Empty knowledge base → 200 with empty results list.

---

## 5. AT-007 detailed scenario

### 5.1 Fixture requirements

1. Seed creates one restricted `Document` + `DocumentVersion` (APPROVED),
   chunked and embedded.
2. `document_permissions` contains NO row for the target role (e.g.
   `ENGINEER`) on that document.
3. A query targeting the restricted content is issued by an `ENGINEER` user.
4. The retriever returns zero results (the restricted chunk is excluded).

### 5.2 Positive control

1. The same query issued by an `AI_ADMINISTRATOR` user (who has permission)
   returns at least one result containing the restricted chunk.

### 5.3 Negative controls

- A user with a different role but no permission → 0 results.
- Role mismatch between `document_permissions.role_id` and the user's
  `user_roles[].role_id` → the chunk is never exposed.

---

## 6. Retrieval contract

### 6.1 Service interface

```python
# backend/app/ai/rag/retriever.py

from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True)
class RetrievalResult:
    document_id: UUID
    document_version_id: UUID
    version_number: str
    chunk_id: UUID
    chunk_index: int
    chunk_text: str
    similarity_score: float  # cosine similarity in [0, 1]
    citation: "Citation"

class RetrievalService:
    async def retrieve(
        self,
        session: AsyncSession,
        query_text: str,
        allowed_role_ids: set[UUID],
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[RetrievalResult]:
        ...
```

### 6.2 Input validation

- `query_text` must be non-empty after `.strip()`; max 2000 characters.
- `limit` (top_k) must be in `[1, 100]`; minimum 1, default 10, maximum 100.
- `min_score` must be in `[0.0, 1.0]`.

### 6.3 Output contract

- Results ordered deterministically by the following composite key:
  1. `similarity_score` DESC;
  2. `document_id` ASC;
  3. `document_version_id` ASC;
  4. `chunk_index` ASC;
  5. `chunk_id` ASC (final stable tie-breaker).
- Results list length ≤ `limit`.
- Each result contains a fully-populated `Citation` (see §9).

---

## 7. Vector similarity-search design

### 7.1 Provider

PostgreSQL with `pgvector` extension (already configured in WP-4.2).

### 7.2 Query embedding

- Use the configured `EmbeddingProvider` to embed the query text.
- The fake provider must be used in tests — no external calls.
- The OpenAI provider may be used in production; dimension must match the
  stored `embedding` dimension (1536).

### 7.3 Similarity function

Cosine distance via pgvector operator `<=>`. Similarity score =
`1 - cosine_distance`.

**Embedding validation** (see DEC-WP44-02):
- Expected dimension check.
- Finite values only (reject NaN, Inf).
- Reject zero-norm vectors (cosine distance undefined).
- Pre-normalization is optional; not a compatibility requirement.

### 7.4 SQL shape (core)

```sql
SELECT kc.id AS chunk_id,
       kc.chunk_index,
       kc.chunk_text,
       dv.id AS document_version_id,
       dv.version_number,
       d.id AS document_id,
       1 - (kc.embedding <=> :query_vector) AS similarity_score
FROM   knowledge_chunks kc
JOIN   document_versions dv ON dv.id = kc.document_version_id
JOIN   documents d ON d.id = dv.document_id
WHERE  dv.status = 'APPROVED'
  AND  d.id IN (
           SELECT dp.document_id
           FROM   document_permissions dp
           WHERE  dp.role_id = ANY(:allowed_role_ids)
       )
  AND  kc.embedding IS NOT NULL
ORDER BY similarity_score DESC,
         d.id ASC,
         dv.id ASC,
         kc.chunk_index ASC,
         kc.id ASC
LIMIT  :limit;
```

### 7.5 Index (performance, not correctness)

A follow-up WP-4.4F (optional, not in this spec) may add an HNSW index.
For Phase 4 exit verification, sequential scan with the seed dataset (< 1000
chunks) is acceptable.

---

## 8. Access-filtering design

### 8.1 Mandatory enforcement

Access filtering is applied **inside the PostgreSQL retrieval query**, before
results are materialized. The retriever never returns chunks the caller
is not permitted to see. **Post-retrieval filtering in application code is
forbidden.**

### 8.2 Permission resolution

- The caller's `allowed_role_ids` are derived from the authenticated user's
  `user_roles[].role_id` set.
- A document is accessible if at least one row exists in
  `document_permissions` with `(document_id = d.id, role_id ∈ allowed_role_ids)`.

### 8.3 No fallback to permissive mode

If no permissions match, the query returns zero results. There is no
"public document" bypass in Phase 4; every document must have at least one
`document_permissions` row to be retrievable. Seed data must ensure this.

### 8.4 Status filter

Only `DocumentVersion.status = 'APPROVED'` chunks are eligible. Draft and
superseded versions are excluded from retrieval.

---

## 9. Citation model and API response contract

### 9.1 Citation dataclass

The citation identity is the minimal tuple that uniquely identifies the
source of a retrieval result. Required fields:
- `document_id` (UUID)
- `document_version_id` (UUID) — referred to as `version_id`
- `chunk_id` (UUID)
- `chunk_index` (int)

```python
# backend/app/ai/rag/citations.py

@dataclass(frozen=True)
class Citation:
    document_id: UUID
    document_version_id: UUID   # version_id
    chunk_id: UUID
    chunk_index: int
    version_number: str
    similarity_score: float
```

### 9.2 API response schema

```
POST /api/v1/retrieval
Authorization: Bearer <token>
Content-Type: application/json

Request:
{
  "query": "alternative for component X",
  "limit": 10
}

Response (200):
{
  "results": [
    {
      "document_id": "<uuid>",
      "document_version_id": "<uuid>",
      "version_number": "1.0",
      "chunk_id": "<uuid>",
      "chunk_index": 3,
      "chunk_text": "...",
      "similarity_score": 0.87,
      "citation": {
        "document_id": "<uuid>",
        "document_version_id": "<uuid>",
        "version_number": "1.0",
        "chunk_id": "<uuid>",
        "chunk_index": 3,
        "similarity_score": 0.87
      }
    }
  ],
  "query_embedding_dimension": 1536,
  "total_results": 1
}
```

### 9.3 Endpoint authorization

- Requires authentication (`get_current_user`).
- Any authenticated role may call retrieval; access is then filtered by
  `document_permissions`.

---

## 10. Evaluation-fixture design

### 10.1 Purpose

Deterministic fixtures allow AT-006 and AT-007 to be automated without
depending on external LLMs or live embedding endpoints.

### 10.2 Fixture files

- `backend/tests/fixtures/evaluation/rag_documents.json` — list of
  documents with title, version_number, status, content, and permissions
  (role codes).
- `backend/tests/fixtures/evaluation/rag_queries.json` — list of
  `{query_id, query_text, expected_document_ids, expected_chunk_indices,
  expected_role_access}`.

### 10.3 Fixture loading

- A pytest fixture `rag_evaluation_dataset` loads the JSON files and
  inserts them into the test database within a transaction that rolls back
  after the test session.
- The fake embedding provider is used for all chunks and queries.

### 10.4 Determinism guarantee

- The fake provider generates vectors deterministically from text content
  (already implemented in `FakeEmbeddingProvider._deterministic_vector`).
- Fixture documents and queries are committed to the repository and
  checksummed.

---

## 11. Transaction and error semantics

### 11.1 Read-only

Retrieval is strictly read-only. No writes to `knowledge_chunks`,
`document_versions`, or `documents`.

### 11.2 Session management

- The caller supplies an `AsyncSession`; the retriever does not commit.
- All queries run within the caller's transaction scope.

### 11.3 Error classification

| Condition | Error type | HTTP status |
|-----------|------------|-------------|
| Empty/blank query | `RetrievalValidationError` | 400 |
| Query too long | `RetrievalValidationError` | 400 |
| Limit out of range | `RetrievalValidationError` | 400 |
| Embedding provider failure | `EmbeddingProviderError` (propagated) | 502 (endpoint) |
| Dimension mismatch | `EmbeddingProviderError` | 502 (endpoint) |
| Database error | `SQLAlchemyError` (propagated) | 500 |

### 11.4 No silent degradation

If the embedding provider fails, the retriever raises. There is no fallback
to "return all chunks" or "return empty."

---

## 12. Security and data-isolation requirements

### 12.1 Mandatory

1. **No chunk leaks**: unauthorized chunks must never appear in retrieval
   results, even under adversarial query construction.
2. **No information leakage via error messages**: error responses must not
   reveal whether a restricted document exists.
3. **Role-based filtering is server-side**: the client cannot bypass access
   control by manipulating request parameters.
4. **No external network calls in tests**: the fake embedding provider must
   be the only provider used in automated tests.

### 12.2 Audit (Phase 4 minimal)

Retrieval events are logged with:
- `correlation_id`
- `username`
- `query_text_hash` (sha256, not the raw query)
- `result_count`
- `latency_ms`

Full audit trail is Phase 6 scope; Phase 4 provides only structured logging.

---

## 13. Work-package decomposition

### WP-4.4A — Retrieval domain contract and vector query service

**Scope**:
- `backend/app/ai/rag/retriever.py` — `RetrievalService`, `RetrievalResult`.
- Unit tests: `backend/tests/unit/test_retriever.py`.
- Integration tests: `backend/tests/integration/test_retriever_vector_query.py`.

**Dependencies**: WP-4.3B (ingestion must be merged; embedding provider
contract repaired).

**Out of scope**: access filtering, citations, API endpoint, evaluation
fixtures.

**Acceptance criteria**:
- [ ] AC-4.4A-01: `RetrievalService.retrieve()` executes a pgvector cosine
      similarity query and returns results ordered by score DESC.
- [ ] AC-4.4A-02: Results include `document_id`, `document_version_id`,
      `version_number`, `chunk_id`, `chunk_index`, `similarity_score`.
- [ ] AC-4.4A-03: Deterministic ordering uses composite sort:
      similarity DESC, document_id ASC, version_id ASC, chunk_index ASC,
      chunk_id ASC.
- [ ] AC-4.4A-04: `limit` (top_k) parameter is enforced (minimum 1,
      default 10, maximum 100).
- [ ] AC-4.4A-05: Empty knowledge base returns an empty list.
- [ ] AC-4.4A-06: Query text validation rejects empty/oversized input.
- [ ] AC-4.4A-07: Embedding provider dimension mismatch raises typed error.

### WP-4.4B — Document access filtering

**Scope**:
- Extend `RetrievalService.retrieve()` to accept `allowed_role_ids` and
  filter via `document_permissions` join.
- Unit tests: `backend/tests/unit/test_access_filter.py`.
- Integration tests:
  `backend/tests/integration/test_retriever_access_control.py`.

**Dependencies**: WP-4.4A.

**Out of scope**: citation construction, API endpoint, evaluation fixtures.

**Acceptance criteria**:
- [ ] AC-4.4B-01: Only chunks whose document has at least one
      `document_permissions` row matching `allowed_role_ids` are returned.
- [ ] AC-4.4B-02: A user with no matching permissions receives zero results.
- [ ] AC-4.4B-03: A user with matching permissions receives only the
      permitted chunks.
- [ ] AC-4.4B-04: Only `DocumentVersion.status = 'APPROVED'` chunks are
      eligible.
- [ ] AC-4.4B-05: Multiple roles on a single user are handled correctly
      (union of permissions).

### WP-4.4C — Citation construction and retrieval API

**Scope**:
- `backend/app/ai/rag/citations.py` — `Citation` dataclass, builder.
- `backend/app/api/retrieval.py` — `POST /api/v1/retrieval` endpoint.
- API tests: `backend/tests/integration/test_api_retrieval.py`.

**Dependencies**: WP-4.4A, WP-4.4B.

**Out of scope**: evaluation fixtures, AT-006/AT-007 automation.

**Acceptance criteria**:
- [ ] AC-4.4C-01: `Citation` identity contains `document_id`,
      `document_version_id`, `chunk_id`, `chunk_index` (plus
      `version_number` and `similarity_score`).
- [ ] AC-4.4C-02: Endpoint returns 200 with results list.
- [ ] AC-4.4C-03: Endpoint returns 400 for invalid query/limit.
- [ ] AC-4.4C-04: Endpoint returns 401 for unauthenticated request.
- [ ] AC-4.4C-05: Response JSON matches schema in §9.2.

### WP-4.4D — Evaluation fixtures and AT-006/AT-007 automation

**Scope**:
- `backend/tests/fixtures/evaluation/rag_documents.json`.
- `backend/tests/fixtures/evaluation/rag_queries.json`.
- `backend/tests/integration/test_at006_rag_retrieval.py`.
- `backend/tests/integration/test_at007_document_access_control.py`.

**Dependencies**: WP-4.4A, WP-4.4B, WP-4.4C.

**Out of scope**: Phase 5 AI workflow, LLM answer generation.

**Acceptance criteria**:
- [ ] AC-4.4D-01: AT-006 test passes: given an approved document about a
      component alternative, a mitigation query returns retrieval results
      with valid citation evidence (`document_id`, `version_number`,
      `chunk_id`). This test validates retrieval and citation evidence
      only — not LLM-generated prose.
- [ ] AC-4.4D-02: AT-007 test passes: a user without permission receives
      zero results for a query whose answer exists only in a restricted
      document. The test proves the restricted chunk is absent from both
      the retrieval context (SQL query result set) and the API response.
- [ ] AC-4.4D-03: Fixtures are deterministic (same inputs → same results).
- [ ] AC-4.4D-04: No automated test contacts an external embedding endpoint.
- [ ] AC-4.4D-05: Fixtures are committed to the repository and versioned.

### WP-4.4E — Live E2E and Phase 4 exit verification

**Scope**:
- `backend/tests/e2e/test_retrieval_e2e.py` — end-to-end retrieval with
  real Postgres, real Redis (no ARQ worker needed), fake embedding provider.
- `docs/planning/wp44_phase_4_exit_report.md` — Phase 4 closure evidence.

**Dependencies**: WP-4.4A through WP-4.4D.

**Out of scope**: Phase 5, LLM answer generation, pgvector index (optional).

**Acceptance criteria**:
- [ ] AC-4.4E-01: Full test suite (`make test`) passes.
- [ ] AC-4.4E-02: Lint (`make lint`) passes.
- [ ] AC-4.4E-03: mypy (`make mypy`) passes.
- [ ] AC-4.4E-04: AT-006 and AT-007 automated tests pass.
- [ ] AC-4.4E-05: Phase 4 exit criteria from `07_ROADMAP.md` are satisfied.

### WP-4.4F (optional, out of Phase 4 exit scope) — pgvector index

**Scope**:
- Alembic migration adding HNSW index on `knowledge_chunks.embedding`.
- Performance benchmark.

**Status**: DEFERRED. Not required for Phase 4 exit. May be added later if
retrieval performance degrades with larger datasets.

### Merge order

1. WP-4.4A
2. WP-4.4B (depends on 4.4A)
3. WP-4.4C (depends on 4.4A, 4.4B)
4. WP-4.4D (depends on 4.4A, 4.4B, 4.4C)
5. WP-4.4E (depends on 4.4A through 4.4D)

---

## 14. Acceptance criteria (summary)

| WP | Count |
|----|-------|
| WP-4.4A | 7 |
| WP-4.4B | 5 |
| WP-4.4C | 5 |
| WP-4.4D | 5 |
| WP-4.4E | 5 |
| **Total** | **27** |

---

## 15. Verification matrix

| Gate | Command | Expected |
|------|---------|----------|
| Unit tests (per WP) | `pytest backend/tests/unit/test_wp44_*` | all pass |
| Integration tests (per WP) | `pytest backend/tests/integration/test_wp44_*` | all pass |
| AT-006 | `pytest backend/tests/integration/test_at006_rag_retrieval.py` | pass |
| AT-007 | `pytest backend/tests/integration/test_at007_document_access_control.py` | pass |
| E2E | `pytest backend/tests/e2e/test_retrieval_e2e.py` | pass |
| Full suite | `make test` | all pass |
| Lint | `make lint` | no errors |
| Types | `make mypy` | no errors |

---

## 16. Definition of Done for WP-4.4

WP-4.4 is complete when:

1. All 27 acceptance criteria pass.
2. AT-006 and AT-007 are automated and passing.
3. Evaluation fixtures are committed and deterministic.
4. No external embedding endpoint is contacted by automated tests.
5. Full test suite, lint, and mypy pass.
6. Phase 4 exit criteria from `07_ROADMAP.md` are satisfied.
7. Phase 4 closure evidence document is created.

---

## 17. Risks and unresolved questions

### 17.1 pgvector index (performance)

Without an HNSW or IVFFlat index, retrieval uses sequential scan. For the
seed dataset (< 1000 chunks), performance is acceptable. If the dataset
grows, WP-4.4F should be added.

**Risk**: LOW for Phase 4.

### 17.2 Similarity score interpretation

### 17.2 Similarity score range

Cosine distance in pgvector returns values in `[0, 2]`. The conversion
`1 - cosine_distance` yields `[-1, 1]`. For unit-normalized vectors the
range is `[0, 1]`. Pre-normalization is optional (see DEC-WP44-02).
The retrieval service must accept similarity scores in the full `[-1, 1]`
range and must not reject results whose score falls outside `[0, 1]`.

**Risk**: LOW. Mitigation: do not clamp or reject scores outside `[0, 1]`;
document the full range in the API response contract.

### 17.3 Deterministic tie-breaking

The composite ORDER BY clause (similarity DESC, document_id ASC, version_id
ASC, chunk_index ASC, chunk_id ASC) guarantees deterministic ordering
within a single database state. Fixtures are committed with fixed UUIDs so
ordering is reproducible across test runs.

### 17.4 Embedding provider dimension

The `KnowledgeChunk.embedding` column is `Vector(1536)`. The retrieval
service must verify that the query embedding dimension matches. If the
configured provider produces a different dimension, retrieval must fail with
a typed error.

**Risk**: LOW. Mitigation: dimension check in `RetrievalService.retrieve()`.

---

## 18. Product Owner decisions

### DEC-WP44-01 — No separate `indexer.py`

**Status**: APPROVED

**Rationale**: Ingestion (WP-4.3A/4.3B) already implements indexing. A
separate `indexer.py` would duplicate logic. The retrieval service relies on
WP-4.3B for stored chunks.

### DEC-WP44-02 — Cosine similarity with `1 - cosine_distance`

**Status**: APPROVED_WITH_CORRECTION

**Rationale**: Use PostgreSQL/pgvector cosine distance for ranking. Similarity
may be represented as `1 - cosine_distance`. Do not state that stored vectors
must be pre-normalized for cosine distance to work. Pre-normalization is
optional and must not become a hidden compatibility requirement unless
implemented consistently for both stored and query vectors.

**Required embedding validation**:
- Expected dimension (must match `KnowledgeChunk.embedding` column dimension).
- Finite values only (reject NaN and Inf via `math.isfinite()`).
- Reject zero-norm vectors where cosine distance would be undefined.

### DEC-WP44-03 — No LLM answer generation in Phase 4

**Status**: APPROVED

**Rationale**: AT-006 and AT-007 test retrieval, not answer generation.
LLM integration belongs to Phase 5. Phase 4 returns raw retrieval results
with citations. AT-006 validates retrieval and citation evidence only —
not LLM prose.

### DEC-WP44-04 — Mandatory `document_permissions` for all documents

**Status**: APPROVED_WITH_REQUIREMENT

**Rationale**: No implicit public-document bypass. A document without a
matching permission is inaccessible to a normal user. Unauthorized chunks
must be excluded in the SQL query before result materialization. Filtering
after retrieval is forbidden.

**Additional requirements**:
- AI_ADMINISTRATOR behavior must follow the existing authoritative RBAC
  contract; do not invent an administrator bypass if none exists.
- Deterministic AT-007 fixtures must include allowed and restricted documents.
- Seed data must ensure every document has at least one `document_permissions`
  row to be retrievable by authorized roles.

### DEC-WP44-05 — pgvector index deferred to WP-4.4F (optional)

**Status**: APPROVED

**Rationale**: Sequential scan is acceptable for the seed dataset. HNSW
index may be added later if performance degrades.

---

## 19. Recommended first implementation slice

**WP-4.4A — Retrieval domain contract and vector query service**

This slice establishes the core retrieval logic without access filtering,
citations, or API endpoints. It can be tested independently with the fake
embedding provider and a test database.

**Files to create**:
- `backend/app/ai/rag/retriever.py`
- `backend/tests/unit/test_retriever.py`
- `backend/tests/integration/test_retriever_vector_query.py`

**Dependencies**: WP-4.3B (already merged).

**Estimated effort**: 1–2 days.

---

## 20. Stop conditions

### 20.1 Do not proceed without Product Owner approval for:

- Changing infrastructure state (Docker, Redis, Postgres).
- Changing credentials or secrets.
- Deleting data or volumes.
- Changing the approved architecture.
- Modifying Source of Truth documents.
- Adding dependencies.
- Expanding work-package scope.
- Committing unexpected files.
- Pushing.
- Creating a PR.
- Merging.

### 20.2 Stop and report if:

- A command fails and classification is unclear.
- A test fails and root cause is not identified.
- A dependency conflict arises.
- An environment defect is suspected (not a code defect).
- Scope creep is attempted (LLM answer generation, Phase 5 workflow).
- A worker produces factually incorrect output.

### 20.3 Do not:

- Implement WP-4.4A until planning is approved.
- Modify application code until planning is approved.
- Modify tests until planning is approved.
- Commit until planning is approved.
- Push until planning is approved.
- Create a PR until planning is approved.
- Merge until planning is approved.
- Implement LLM answer generation (Phase 5 scope).
- Contact external embedding endpoints in tests.
- Use silent fake-provider fallback.

---

## 21. Next Product Owner action

**Action**: Review and approve this planning specification.

**Approval grants**:
- Permission to create feature branch
  `feature/phase-4-wp-4-4-retrieval-citations-access-control` (already
  created locally).
- Permission to implement WP-4.4A (retrieval domain contract and vector
  query service).
- Permission to commit and push.
- Permission to create PR (not merge).

---

**End of Specification**
