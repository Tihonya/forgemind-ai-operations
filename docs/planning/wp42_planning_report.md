# WP-4.2 Planning Report

## Date: 2026-07-28
## Manager: Hermes (session continuation)
## Status: PLANNING COMPLETE — awaiting Product Owner decisions

---

## A. Worker Invocation Evidence

**Task ID:** WP42-TEST-INTEGRATION-RECON-003
**Parent Task ID:** WP-4.2-PLANNING
**Invocation ID:** lwm-185ca84564fd4901
**Exit code:** 0
**Duration:** not captured (foreground wrapper)
**Log path:** ~/.hermes/delegations/2026-07-28/WP42-TEST-INTEGRATION-RECON-003-lwm-185ca84564fd4901.stdout.log
**Worker model:** Qwopus3.6-27B-v2-MTP-Q5_K_M.gguf via local endpoint

---

## B. Worker Report (verbatim summary)

The worker inspected 18 files across unit tests, integration tests, seed loader,
CI workflows, Makefile, and pyproject.toml.

Key findings reported:
1. Unit tests use pure SQLAlchemy inspect() — no DB needed
2. Integration tests use live async PostgreSQL via TEST_DATABASE_URL/DATABASE_URL
3. EXPECTED_ALEMBIC_HEAD = "a1b2c3d4e5f6" in loader.py:41, imported by 2 test files
4. CI uses postgres:16 (NOT pgvector/pgvector:pg16) — flagged as highest risk
5. Phase 2 established static migration-file content test pattern
6. No @pytest.mark.unit or @pytest.mark.integration markers actually used
7. CI runs mypy . (whole project); Makefile runs mypy app/ (scope mismatch)
8. Integration conftest has autouse pool-disposal fixture

---

## C. Manager Accepted Findings

All material claims verified independently:

| # | Finding | Verification |
|---|---------|-------------|
| 1 | CI uses postgres:16 | ci-backend.yml:24 — CONFIRMED |
| 2 | Compose uses pgvector/pgvector:pg16 | docker-compose.yml:4 — CONFIRMED |
| 3 | EXPECTED_ALEMBIC_HEAD = "a1b2c3d4e5f6" | loader.py:41 — CONFIRMED |
| 4 | Current Alembic head: a1b2c3d4e5f6 | migration file line 37 — CONFIRMED |
| 5 | down_revision chain: ... → b4c5a6b7c8d9 → a1b2c3d4e5f6 | migration file line 38 — CONFIRMED |
| 6 | pgvector>=0.3.0 already in pyproject.toml | pyproject.toml:26 — CONFIRMED |
| 7 | test_loader.py imports EXPECTED_ALEMBIC_HEAD | line 62 import, line 291 assert — CONFIRMED |
| 8 | test_wp25_auth_integration.py imports EXPECTED_ALEMBIC_HEAD | line 66 import, line 97 assert — CONFIRMED |
| 9 | Unit test pattern: inspect() without DB | test_wp41_document_models.py — CONFIRMED |
| 10 | Integration test pattern: async engine + session | test_wp41_migration.py — CONFIRMED |
| 11 | Static migration file test pattern | test_phase2_migration.py — CONFIRMED |
| 12 | Integration conftest: autouse pool disposal | conftest.py lines 13-26 — CONFIRMED |
| 13 | CI commands: alembic → ruff → mypy → pytest | ci-backend.yml lines 63-83 — CONFIRMED |
| 14 | CI mypy runs on "." (whole project) | ci-backend.yml:75 — CONFIRMED |
| 15 | Makefile lint: mypy app/ (app only) | Makefile:19 — CONFIRMED |
| 16 | No pytest markers actually used on functions | pyproject.toml defines them; no test uses them — CONFIRMED |

---

## D. Manager Rejected Findings

| # | Worker Claim | Manager Correction |
|---|-------------|-------------------|
| 1 | test_build_info.py:148 contains "a1b2c3d4e5f60000..." as Alembic reference | REJECTED — this is a fabricated 40-char hex string used as a fake git SHA in a unit test for build_info service. Not an Alembic revision reference. |
| 2 | "test_wp25_auth_integration.py will inherit the new value via import (no hardcoded value)" | PARTIALLY CORRECT — the import cascade is correct, but the worker implied no change is needed. The file DOES need updating ONLY IF the constant location changes. For WP-4.2, only loader.py:41 needs updating. The two test files need NO changes. |
| 3 | Worker recommended J.1 test should check "G
[OUT-OF-BAND USER MESSAGE — a direct message from the user, delivered mid-turn; not tool output]
Do not run any commands. Just write the planning report and output it here in chat.
[/OUT-OF-BAND USER MESSAGE]
IN/IVFFlat index for vector search" | REJECTED — WP-4.2 scope explicitly excludes ANN index tuning. Decision #11 from Product Owner: "no HNSW or IVFFlat index in WP-4.2". |

---

## E. Final WP-4.2 Schema Contract

### Table: knowledge_chunks

```
Column               Type              Nullable   Default                    Notes
─────────────────────────────────────────────────────────────────────────────────────
id                   UUID              NOT NULL   gen_random_uuid()          PK
document_version_id  UUID              NOT NULL   —                          FK → document_versions.id ON DELETE CASCADE
chunk_index          Integer           NOT NULL   —                          Zero-based ordering
chunk_text           Text              NOT NULL   —                          Raw chunk content
token_count          Integer           NULL       —                          Optional token count
metadata             JSONB             NULL       —                          Extensible metadata
content_hash         String(64)        NULL       —                          SHA-256 of chunk_text
embedding            Vector(1536)      NULL       —                          Nullable per PO decision #2
created_at           DateTime(tz=True) NOT NULL   now()                      Server-side timestamp
```

### Constraints

| Constraint | Type | Columns/Details |
|-----------|------|-----------------|
| pk_knowledge_chunks | PRIMARY KEY | (id) |
| uq_knowledge_chunks_dv_chunk | UNIQUE | (document_version_id, chunk_index) |
| fk_knowledge_chunks_document_version | FOREIGN KEY | document_version_id → document_versions.id ON DELETE CASCADE |

### Indexes

| Index Name | Type | Columns |
|-----------|------|---------|
| ix_knowledge_chunks_document_version_id | B-tree (ordinary) | (document_version_id) |

NO ANN vector index (HNSW, IVFFlat). Deferred to retrieval work package.

### Model: KnowledgeChunk

- Module: backend/app/models/knowledge_chunk.py
- __tablename__: "knowledge_chunks"
- Inherits from Base (app.models.base.Base)
- Relationship: document_version (back_populates managed by DocumentVersion)
- Exported from app/models/__init__.py __all__

---

## F. Migration Contract

### File: backend/alembic/versions/<new_revision>_add_knowledge_chunks.py

```python
revision: str = "<new_revision_id>"
down_revision: str | None = "a1b2c3d4e5f6"

def upgrade() -> None:
    # 1. CREATE EXTENSION IF NOT EXISTS vector
    # 2. op.create_table("knowledge_chunks", ...)
    # 3. op.create_index("ix_knowledge_chunks_document_version_id", ...)

def downgrade() -> None:
    # 1. op.drop_index("ix_knowledge_chunks_document_version_id", ...)
    # 2. op.drop_table("knowledge_chunks")
    # 3. DO NOT drop the vector extension (PO decision #13)
```

### Migration Rules

- Extension created in upgrade, NOT dropped in downgrade
- FK uses ondelete="CASCADE" matching repo convention
- UUID columns use postgresql.UUID(as_uuid=True) + server_default=sa.text("gen_random_uuid()")
- Timestamps use sa.DateTime(timezone=True) + server_default=sa.text("now()")
- Vector column uses pgvector.sqlalchemy.Vector(1536)

---

## G. Unit/Integration Test Contract

### Unit Test File: backend/tests/unit/test_wp42_knowledge_chunk_models.py

Pattern: pure SQLAlchemy inspect(), no database required.

```
class TestKnowledgeChunkModel:
    test_knowledge_chunk_table_name
    test_knowledge_chunk_columns          # set equality via inspect()
    test_knowledge_chunk_id_primary_key
    test_knowledge_chunk_document_version_id_not_nullable
    test_knowledge_chunk_document_version_id_foreign_key   # target = document_versions.id
    test_knowledge_chunk_chunk_index_not_nullable
    test_knowledge_chunk_chunk_text_not_nullable
    test_knowledge_chunk_token_count_nullable
    test_knowledge_chunk_metadata_nullable
    test_knowledge_chunk_content_hash_nullable
    test_knowledge_chunk_content_hash_max_length           # 64
    test_knowledge_chunk_embedding_nullable
    test_knowledge_chunk_embedding_dimension               # 1536
    test_knowledge_chunk_created_at_not_nullable
    test_knowledge_chunk_unique_constraint                 # (document_version_id, chunk_index)
    test_knowledge_chunk_indexes                             # ix_knowledge_chunks_document_version_id
    test_knowledge_chunk_relationships                     # {document_version}
```

### Static Migration Test: backend/tests/unit/test_wp42_migration_file.py

Pattern: read migration file content, assert expected strings.

```
class TestMigrationFileStructure:
    test_migration_file_exists
    test_migration_has_correct_down_revision       # "a1b2c3d4e5f6"
    test_migration_has_upgrade_function
    test_migration_has_downgrade_function

class TestMigrationUpgrade:
    test_creates_vector_extension
    test_creates_knowledge_chunks_table

class TestMigrationColumnTypes:
    test_uuid_primary_key
    test_vector_column_dimension_1536
    test_timestamps_timezone_aware

class TestMigrationConstraints:
    test_creates_unique_constraint_dv_chunk
    test_creates_foreign_key_with_cascade
    test_creates_btree_index_on_document_version_id

class TestMigrationDowngrade:
    test_downgrade_drops_table
    test_downgrade_drops_index_before_table
    test_downgrade_does_not_drop_vector_extension

class TestMigrationDoesNotAffect:
    test_does_not_drop_existing_tables
    test_does_not_alter_existing_tables
```

### Integration Test: backend/tests/integration/test_wp42_migration.py

Pattern: live async PostgreSQL, information_schema queries.

```
_INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    session_factory = async_sessionmaker[AsyncSession](bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()

class TestKnowledgeChunksMigration:
    test_knowledge_chunks_table_exists
    test_knowledge_chunks_columns
    test_knowledge_chunks_foreign_key_to_document_versions
    test_knowledge_chunks_foreign_key_on_delete_cascade
    test_knowledge_chunks_unique_constraint_dv_chunk
    test_knowledge_chunks_index_exists
    test_pgvector_extension_active
    test_vector_column_type
    test_downgrade_upgrade_reupgrade    # downgrade → upgrade → verify table exists again
```

### Downgrade/Re-upgrade Verification

The integration test must:
1. Verify table exists after initial migration (already applied by CI)
2. Run alembic downgrade to previous head (a1b2c3d4e5f6)
3. Verify knowledge_chunks table does NOT exist
4. Run alembic upgrade head again
5. Verify knowledge_chunks table exists again with correct schema
6. Verify pgvector extension is still active

---

## H. Exact Files to Create or Modify

### Files to CREATE

| # | File Path | Purpose |
|---|-----------|---------|
| 1 | backend/app/models/knowledge_chunk.py | KnowledgeChunk SQLAlchemy model |
| 2 | backend/alembic/versions/<rev>_add_knowledge_chunks.py | Alembic migration |
| 3 | backend/tests/unit/test_wp42_knowledge_chunk_models.py | Unit tests for model |
| 4 | backend/tests/unit/test_wp42_migration_file.py | Static migration content tests |
| 5 | backend/tests/integration/test_wp42_migration.py | Live DB migration integration tests |

### Files to MODIFY

| # | File Path | Change |
|---|-----------|--------|
| 1 | backend/app/models/__init__.py | Add KnowledgeChunk to __all__ and imports |
| 2 | backend/app/seed/generator/loader.py | Update EXPECTED_ALEMBIC_HEAD to new revision |

### Files that MUST NOT change

| # | File Path | Reason |
|---|-----------|--------|
| 1 | .github/workflows/ci-backend.yml | Infrastructure change requires PO approval |
| 2 | docker-compose.yml | Infrastructure change requires PO approval |
| 3 | backend/pyproject.toml | pgvector already present; no new deps needed |
| 4 | backend/tests/seed/test_loader.py | Imports EXPECTED_ALEMBIC_HEAD — no change needed |
| 5 | backend/tests/integration/test_wp25_auth_integration.py | Imports EXPECTED_ALEMBIC_HEAD — no change needed |
| 6 | All existing model files | WP-4.2 adds a new model, does not modify existing ones |

---

## I. Revised Delegation Plan

### Phase 1: Implementation Proposal

**Worker type:** local-worker (foreground, READ-ONLY)
**Task:** Verify the exact contract can be satisfied by inspecting existing patterns
**Duration estimate:** 60-120s
**Output:** Confirmation that all imports, patterns, and naming are consistent

### Phase 2: Implementation

**Worker type:** local-worker (foreground, PATCH-ALLOWED)
**Scope:** Create 5 files, modify 2 files per section H
**Constraints:**
- Follow exact WP-4.1 patterns from test_wp41_document_models.py and test_wp41_migration.py
- Migration must use down_revision = "a1b2c3d4e5f6"
- Model must use postgresql.UUID(as_uuid=True), gen_random_uuid(), DateTime(timezone=True)
- Vector(1536) from pgvector.sqlalchemy
- No ANN index
- No changes outside allowlist

**Duration estimate:** 300-420s

### Phase 3: Authoritative Manager Validation

**Manager (Hermes) performs:**
1. git status — verify only allowlisted files changed
2. read each created/modified file — verify contract compliance
3. Run make lint (ruff + mypy app/) — verify no lint errors
4. Run unit tests: pytest backend/tests/unit/test_wp42_*
5. Start live PostgreSQL (pgvector/pgvector:pg16), run migration
6. Run integration tests: pytest backend/tests/integration/test_wp42_migration.py
7. Run downgrade → upgrade → re-upgrade cycle
8. Run full test suite: pytest -v
9. Verify EXPECTED_ALEMBIC_HEAD matches new revision
10. Verify pgvector extension not dropped after downgrade

### Phase 4: Fresh Independent Reviewer

**Worker type:** local-worker (foreground, READ-ONLY)
**Task:** Independent review of all changes against this planning contract
**Checks:**
- Every field in schema contract E is present
- Every constraint in schema contract E is correct
- Migration down_revision matches current head
- loader.py EXPECTED_ALEMBIC_HEAD updated
- No files outside allowlist modified
- All tests pass
- No regressions in existing tests

**Duration estimate:** 180-300s

---

## J. Remaining Product Owner Decisions

### DECISION REQUIRED: CI PostgreSQL Image

The CI pipeline uses `postgres:16` (standard image without pgvector).
The knowledge_chunks migration requires `CREATE EXTENSION IF NOT EXISTS vector`.

This will FAIL in CI because the vector extension is not available in standard postgres:16.

Options:

1. Change CI image to `pgvector/pgvector:pg16` in .github/workflows/ci-backend.yml
   - Pros: cleanest solution, matches local dev environment
   - Cons: infrastructure change, CI workflow modification

2. Install pgvector extension in CI via apt-get before migration
   - Pros: keeps existing image
   - Cons: adds CI build steps, fragile, slow

3. Defer CI fix to a separate work package
   - Pros: keeps WP-4.2 scope minimal
   - Cons: WP-4.2 cannot pass CI without this fix

RECOMMENDATION: Option 1. The pgvector extension handling is explicitly in WP-4.2 scope.
The CI image change is a necessary consequence, not scope creep.
This requires explicit Product Owner approval to modify .github/workflows/ci-backend.yml.

### DECISION REQUIRED: Relationship back_populates

The KnowledgeChunk model has a FK to document_versions. Two options:

1. Add a `chunks` relationship on DocumentVersion (back_populates="document_version")
   - Requires modifying backend/app/models/document.py
   - Cons: modifies an existing model file outside WP-4.2 minimal scope

2. No relationship on DocumentVersion; only unidirectional from KnowledgeChunk
   - KnowledgeChunk.document_version exists but DocumentVersion has no .chunks
   - Pros: no modification to existing files
   - Cons: incomplete ORM navigation

RECOMMENDATION: Option 2 for WP-4.2. Add the back-reference in a later WP
when chunk retrieval is in scope. This keeps the file allowlist minimal and
avoids modifying DocumentVersion model.

If Product Owner prefers Option 1, backend/app/models/document.py must be added
to the modification allowlist.

---

## K. One Smallest Next Product Owner Action

Answer two decisions:

1. Approve or reject CI image change to pgvector/pgvector:pg16 in ci-backend.yml
2. Approve or reject Option 2 (no back-reference on DocumentVersion in WP-4.2)

Once these are answered, the feature branch can be created and implementation
can begin.

---

## Appendix: Revision ID Generation

The new migration needs a 12-character hex revision ID.
Recommended: generate via `alembic revision -m "add_knowledge_chunks"` which
auto-generates a unique revision ID.

Alternatively, use a deterministic ID for testability:
- "c7d8e9f0a1b2" follows the existing naming pattern (12 hex chars)
- But auto-generation is preferred to avoid collisions

---

## Summary

WP-4.2 planning is complete. All patterns verified against WP-4.1 and Phase 2
precedents. Two Product Owner decisions remain before implementation can begin:

1. CI pgvector image change (REQUIRED for CI to pass)
2. DocumentVersion.chunks relationship (deferred to later WP recommended)

File allowlist: 5 new files, 2 modified files, many protected files.
Delegation plan: 4 phases (proposal → implementation → manager validation → independent review).
