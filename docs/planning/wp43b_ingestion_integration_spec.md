# WP-4.3B: Document Ingestion Integration Specification

## Document metadata

- **Status**: DRAFT_FOR_REVIEW
- **Depends on**: WP-4.1 (document schema), WP-4.2 (knowledge chunks schema), WP-4.3A (ingestion core)
- **Branch target**: feature/phase-4-wp-4-3b-ingestion-integration
- **Created**: 2026-07-29
- **Base commit**: b384c839e7f19dd7817c58c21331c5d4fe102f08
- **Amended decisions**: DEC-WP43B-08, DEC-WP43B-09, DEC-WP43B-10, DEC-WP43B-12

---

## 1. Repository evidence (verified)

**Base commit**: b384c839e7f19dd7817c58c21331c5d4fe102f08  
**Branch**: main  
**Working tree**: clean (verified via `git status --short`)

**Verified artifacts**:
- `backend/app/services/ingestion.py` (246 lines) — IngestionOrchestrator exists, does not commit
- `backend/app/services/embedding_provider.py` (175 lines) — OpenAI + fake providers, no typed errors, no NaN/Inf validation
- `backend/app/services/chunking.py` — chunk_text service
- `backend/app/worker.py` (63 lines) — ARQ WorkerSettings, imports run_diagnostic_job
- `backend/app/jobs/diagnostics.py` — ARQ worker function for diagnostics
- `backend/app/services/diagnostic_jobs.py` (348 lines) — enqueue_diagnostic_job service with Redis pool management
- `backend/app/api/` — flat structure (auth.py, components.py, inventory.py, etc.), no v1/endpoints subdirectory
- `backend/app/config.py` (223 lines) — settings.embedding_provider, settings.openai_api_key, settings.openai_api_base, settings.embedding_dimensions
- `backend/app/database.py` — async_session_factory
- `backend/app/seed/generator/loader.py` (481 lines) — synchronous seed loader, no async ingestion phase

**Reconnaissance accounting**: RECONNAISSANCE_EXECUTED_BUT_REJECTED_AS_UNRELIABLE. Local worker executed successfully at process level but produced material factual errors (incorrect API endpoint paths, incorrect worker module structure). Manager verified repository state directly via read_file and search_files.

**Key repository structure findings**:
1. API endpoints are flat under `backend/app/api/`, NOT `backend/app/api/v1/endpoints/`
2. ARQ worker functions are in `backend/app/jobs/`, NOT `backend/app/worker/`
3. ARQ worker configuration is in `backend/app/worker.py` (WorkerSettings class)
4. Session factory is `async_session_factory` from `app.database`
5. Existing diagnostic_jobs service demonstrates the enqueue pattern: create DB row → commit → enqueue to Redis → handle failures
6. Config already has `embedding_provider: Literal["openai", "fake"]` field

---

## 2. WP-4.3B0: Embedding Provider Runtime Contract Repair (prerequisite)

**Status**: APPROVED as first internal implementation slice  
**Scope**: Repair embedding provider before WP-4.3B integration work  
**PR strategy**: Part of WP-4.3B branch and PR, not standalone

### 2.1 Current defects (verified)

- `backend/app/services/embedding_provider.py:168-172` — validates numeric type but NOT `math.isfinite()`
- `backend/app/services/embedding_provider.py:139-142` — wraps all exceptions as RuntimeError (loses type information)
- `backend/app/services/embedding_provider.py:124` — AsyncOpenAI constructed without explicit `max_retries=0`
- `backend/app/services/ingestion.py:199-201` — wraps provider exceptions as RuntimeError (loses type information)

### 2.2 Mandatory repairs

1. **NaN/Inf rejection**: validate every embedding value with `math.isfinite()` at line 168
2. **Typed error hierarchy** (new module or in embedding_provider.py):
   - `EmbeddingProviderError` (base)
   - `TransientEmbeddingProviderError` (retryable)
   - `PermanentEmbeddingProviderError` (non-retryable)
   - `EmbeddingProviderConfigurationError` (fatal configuration)
3. **Error classification** in OpenAIEmbeddingProvider.embed_text:
   - Transient: `openai.APIConnectionError`, `openai.APITimeoutError`, `openai.RateLimitError`, 5xx `openai.APIStatusError`
   - Permanent: malformed responses, count mismatch, dimension mismatch, non-finite values, 4xx `openai.APIStatusError`
   - Configuration: missing API key for official endpoint, unknown provider
4. **Exception chaining**: preserve original exceptions through `raise ... from`
5. **Disable SDK retries**: construct `AsyncOpenAI` with `max_retries=0`
6. **Orchestrator preservation**: IngestionOrchestrator must NOT wrap typed provider errors in RuntimeError

---

## 3. Approved decisions

### DEC-WP43B-08: Retry policy — APPROVED_WITH_AMENDMENTS

**Contract**:
- ARQ `max_tries=3` means 3 total executions including initial attempt
- After first failure: retry after 2 seconds
- After second failure: retry after 4 seconds
- No jitter
- Use ARQ `Retry` with `defer` based on `ctx["job_try"]`
- ARQ is the only retry owner
- Construct `AsyncOpenAI` with `max_retries=0` (WP-4.3B0)
- Validation and configuration failures are permanent
- Missing DocumentVersion, blank content and path mismatch are permanent
- Embedding dimension/count/non-finite response defects are permanent
- Retry only explicitly typed transient provider errors
- Retry DB failures only when explicitly classified as transient
- Never retry `IntegrityError` or general `ValueError`

**Implementation location**: `backend/app/jobs/ingestion.py` (new file, parallel to diagnostics.py)

```python
@worker(
    keep_result=300,
    max_tries=3,
)
async def run_document_ingestion(ctx: dict, version_id: str, document_id: str) -> dict:
    job_try = ctx["job_try"]
    if job_try < 3:
        defer_seconds = [2, 4][job_try - 1]
        ctx["retry_defer"] = defer_seconds
    
    # ... ingestion logic ...
```

**Error handling**:
```python
try:
    result = await orchestrator.ingest_document_version(version_id)
    await session.commit()
    return result
except (TransientEmbeddingProviderError,) as exc:
    await session.rollback()
    raise  # ARQ will retry
except (
    PermanentEmbeddingProviderError,
    EmbeddingProviderConfigurationError,
    ValueError,
    IntegrityError,
) as exc:
    await session.rollback()
    raise  # ARQ will NOT retry
```

### DEC-WP43B-09: Seed async bridge — APPROVED_WITH_AMENDMENTS

**Contract**:
- Retain existing synchronous seed loader (`backend/app/seed/generator/loader.py`)
- Commit deterministic seed rows first
- Invoke one separate async phase through `asyncio.run()` from the outer seed command
- Do not manually construct nested event loops
- Use `async_session_factory` from `app.database`
- One transaction per DocumentVersion
- Commit only after successful ingestion of that version
- Rollback the failed version transaction
- Continue processing remaining versions to collect complete evidence
- Report all failed version IDs at the end
- Terminate the seed command with a non-zero exit code if any ingestion failed
- Reruns must be safe through atomic replacement
- Provider selection must be explicit
- No silent fake-provider fallback

**Implementation location**: Modify `backend/app/seed/generator/loader.py`, add `_ingest_seed_documents()` async function

```python
def main() -> None:
    """CLI entry point for seed generator."""
    logging.basicConfig(...)
    
    try:
        # Phase 1: synchronous seed load
        counts = load_golden_dataset()
        logger.info("Seed data loaded successfully")
        
        # Phase 2: async ingestion
        failed_versions = asyncio.run(_ingest_seed_documents())
        
        if failed_versions:
            logger.error(f"Failed to ingest {len(failed_versions)} versions: {failed_versions}")
            raise SystemExit(1)
        
        logger.info("All seed documents ingested successfully")
    
    except RuntimeError as e:
        logger.error(f"Error: {e}")
        raise SystemExit(1) from None
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise SystemExit(1) from None


async def _ingest_seed_documents() -> list[UUID]:
    """Ingest all DocumentVersions using configured provider."""
    from app.database import async_session_factory
    from app.services.embedding_provider_factory import create_embedding_provider
    from app.services.ingestion import IngestionOrchestrator
    from app.models.document import DocumentVersion
    from sqlalchemy import select
    
    provider = create_embedding_provider()  # explicit provider selection
    failed_versions: list[UUID] = []
    
    async with async_session_factory() as session:
        result = await session.execute(select(DocumentVersion))
        versions = result.scalars().all()
    
    for version in versions:
        try:
            async with async_session_factory() as version_session:
                orchestrator = IngestionOrchestrator(version_session, provider)
                await orchestrator.ingest_document_version(version.id)
                await version_session.commit()
                logger.info(f"Ingested version {version.id}")
        except Exception as exc:
            logger.error(f"Failed to ingest version {version.id}: {exc}")
            failed_versions.append(version.id)
    
    return failed_versions
```

### DEC-WP43B-10: Provider factory and runtime contract — APPROVED_WITH_AMENDMENTS

**Contract**:
- Create `backend/app/services/embedding_provider_factory.py` (new file)
- Accepted provider names: `openai`, `fake` (from `settings.embedding_provider`)
- Lazy validation at factory-call time
- Unknown provider raises `EmbeddingProviderConfigurationError`
- No fallback
- Official api.openai.com endpoint requires API key
- Custom/local OpenAI-compatible endpoint may omit a user API key
- Use an internal non-secret sentinel only when required by the SDK
- Fake provider is explicitly selectable in development and automated tests
- Fake provider is rejected in staging and production
- `AsyncOpenAI` `max_retries=0`
- Preserve configured base URL, model, dimension and timeout

**Implementation**:

```python
def create_embedding_provider(
    provider_name: str | None = None,
) -> EmbeddingProvider:
    """Create an embedding provider based on configuration or explicit name."""
    from app.config import settings
    from app.services.embedding_provider import (
        EmbeddingProvider,
        FakeEmbeddingProvider,
        OpenAIEmbeddingProvider,
    )
    
    name = provider_name or settings.embedding_provider
    
    if name == "fake":
        if settings.environment in ("production", "staging"):
            raise EmbeddingProviderConfigurationError(
                "Fake embedding provider is not allowed in production/staging"
            )
        return FakeEmbeddingProvider(dimension=settings.embedding_dimensions)
    
    if name == "openai":
        api_key = settings.openai_api_key
        base_url = settings.openai_api_base
        
        # Official endpoint requires API key
        if base_url == "https://api.openai.com/v1" and not api_key:
            raise EmbeddingProviderConfigurationError(
                "API key required for official OpenAI endpoint"
            )
        
        # Custom endpoint may use sentinel if API key is empty
        if not api_key:
            api_key = "sentinel-not-a-real-key"
        
        return OpenAIEmbeddingProvider(
            api_key=api_key,
            model=settings.openai_embedding_model,
            dimension=settings.embedding_dimensions,
            base_url=base_url if base_url != "https://api.openai.com/v1" else None,
            timeout_seconds=settings.embedding_timeout_seconds,
        )
    
    raise EmbeddingProviderConfigurationError(f"Unknown embedding provider: {name}")
```

### DEC-WP43B-11: Authentication, authorization and path mismatch — APPROVED

**Contract**:
- Authenticate and enforce `AI_ADMINISTRATOR` first
- Query DocumentVersion using `version_id AND document_id`
- Return identical 404 for missing version and mismatched document
- Do not reveal whether the version exists under another document

**Implementation location**: `backend/app/api/ingestion.py` (new file, parallel to other API modules)

```python
@router.post("/documents/{document_id}/versions/{version_id}/ingest")
async def ingest_document_version(
    document_id: UUID,
    version_id: UUID,
    current_user: User = Depends(require_ai_administrator),
):
    # Query with BOTH conditions
    async with async_session_factory() as session:
        result = await session.execute(
            select(DocumentVersion).where(
                DocumentVersion.id == version_id,
                DocumentVersion.document_id == document_id,
            )
        )
        doc_version = result.scalar_one_or_none()
        
        # Identical 404 for missing OR mismatched
        if doc_version is None:
            raise HTTPException(status_code=404, detail="Document version not found")
    
    correlation_id = uuid4()
    
    enqueued = await enqueue_ingestion_job(
        version_id=doc_version.id,
        document_id=doc_version.document_id,
        correlation_id=correlation_id,
    )
    
    return JSONResponse(
        status_code=202,
        content={
            "job_id": enqueued["job_id"],
            "correlation_id": str(enqueued["correlation_id"]),
            "status": enqueued["status"],
        },
    )
```

### DEC-WP43B-12: Enqueue atomicity — APPROVED_WITH_AMENDMENTS

**Contract**:
- No database ingestion-status row (unlike diagnostic_jobs which creates a DiagnosticJob row)
- Return 202 only after Redis accepts the job
- Enqueue exception returns 503
- Safe generic error contract, no Redis internals
- No fake job identifier
- Response fields:
  - `job_id: str` (real ARQ job ID)
  - `correlation_id: UUID v4`
  - `status: literal "pending"`

**Implementation** (simpler than diagnostic_jobs, no DB row):

```python
async def enqueue_ingestion_job(
    version_id: UUID,
    document_id: UUID,
    correlation_id: UUID,
) -> dict:
    """Enqueue document ingestion job to ARQ."""
    from arq.connections import create_pool
    from app.config import settings
    from app.worker import _build_redis_settings
    
    pool = await create_pool(_build_redis_settings())
    
    try:
        arq_job_id = f"document-ingestion:{version_id}"
        
        enqueued_job = await pool.enqueue_job(
            "run_document_ingestion",
            str(version_id),
            str(document_id),
            _job_id=arq_job_id,
            _queue_name=settings.arq_queue_name,
        )
        
        if enqueued_job is None:
            # Duplicate active job
            raise HTTPException(status_code=409, detail="Ingestion job already active")
        
        return {
            "job_id": arq_job_id,
            "correlation_id": correlation_id,
            "status": "pending",
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ingestion_enqueue_failed",
                "detail": "The ingestion job could not be enqueued. Please retry.",
            },
        ) from None
    finally:
        await pool.close()
```

### DEC-WP43B-13: Job deduplication — APPROVED

**Contract**:
- One active ingestion job per DocumentVersion
- Deterministic ARQ job ID: `document-ingestion:{version_id}`
- Register with `max_tries=3`
- Configure `keep_result=300` seconds
- `enqueue_job` returning `None` means an equivalent job key already exists
- Return 409 Conflict for duplicate active/recent job
- Do not return a second 202
- Different versions may run concurrently
- After result retention expires, explicit re-ingestion is allowed

**Implementation**: See DEC-WP43B-12 above. The `_job_id=f"document-ingestion:{version_id}"` ensures deduplication. ARQ returns `None` when job key already exists.

---

## 4. In-scope boundary

### 4.1 Explicitly in scope

1. Embedding provider runtime contract repair (WP-4.3B0)
2. Provider factory with environment-aware validation (`backend/app/services/embedding_provider_factory.py`)
3. Typed provider error hierarchy (in `backend/app/services/embedding_provider.py`)
4. ARQ worker function for document ingestion (`backend/app/jobs/ingestion.py`)
5. Deterministic ARQ job ID for deduplication
6. API endpoint: `POST /api/v1/documents/{document_id}/versions/{version_id}/ingest` (`backend/app/api/ingestion.py`)
7. Endpoint authentication: `AI_ADMINISTRATOR` role required
8. Endpoint authorization: 404 for missing/mismatched document/version
9. Enqueue service: 202 only after Redis acceptance, 503 on failure, 409 on duplicate
10. Seed-loader async bridge: `asyncio.run()` after sync commit (modify `backend/app/seed/generator/loader.py`)
11. Per-version async transaction with rollback on failure
12. Aggregated failure reporting with non-zero exit code
13. Unit tests for provider factory, typed errors, retry policy
14. Integration tests for endpoint, deduplication, enqueue atomicity
15. E2E tests for full ingestion flow (fake provider)

### 4.2 Explicitly out of scope

1. Retrieval endpoints (search, query)
2. Vector similarity indexing
3. Citation rendering in frontend
4. AT-006 (risk recommendation with document citations)
5. AT-007 (end-to-end supply risk workflow)
6. Production OpenAI API calls (tests use fake provider only)
7. Database ingestion-status table (no DB row, unlike diagnostic_jobs)
8. Manual event loop construction
9. Silent fake-provider fallback
10. Any modification to diagnostic_jobs service or diagnostics worker

---

## 5. API contract

### 5.1 Endpoint: Ingest Document Version

**HTTP**: `POST /api/v1/documents/{document_id}/versions/{version_id}/ingest`  
**Router location**: `backend/app/api/ingestion.py` (new file)  
**Router prefix**: Will be mounted at `/api/v1` in `backend/app/main.py`

**Authentication**: Bearer token with `AI_ADMINISTRATOR` role (via `require_ai_administrator` dependency)

**Path parameters**:
- `document_id`: UUID
- `version_id`: UUID

**Request body**: empty (no body required)

**Success response** (202 Accepted):
```json
{
  "job_id": "document-ingestion:550e8400-e29b-41d4-a716-446655440000",
  "correlation_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "status": "pending"
}
```

**Error responses**:
- 401 Unauthorized: missing or invalid token
- 403 Forbidden: insufficient role (not AI_ADMINISTRATOR)
- 404 Not Found: document/version missing or mismatched
- 409 Conflict: duplicate active/recent ingestion job
- 503 Service Unavailable: Redis enqueue failure

**Response contract**:
- `job_id`: real ARQ job identifier (deterministic key `document-ingestion:{version_id}`)
- `correlation_id`: UUID v4 generated per request
- `status`: literal `"pending"`

---

## 6. ARQ retry and deduplication contract

### 6.1 Worker function signature

**Location**: `backend/app/jobs/ingestion.py` (new file)

```python
from arq import worker

@worker(
    keep_result=300,
    max_tries=3,
)
async def run_document_ingestion(
    ctx: dict,
    version_id: str,
    document_id: str,
) -> dict:
    """ARQ worker function for document ingestion."""
    from uuid import UUID
    from app.database import async_session_factory
    from app.services.embedding_provider_factory import create_embedding_provider
    from app.services.ingestion import IngestionOrchestrator
    
    # Retry policy: defer 2s after first failure, 4s after second failure
    job_try = ctx["job_try"]
    if job_try < 3:
        defer_seconds = [2, 4][job_try - 1]
        ctx["retry_defer"] = defer_seconds
    
    version_uuid = UUID(version_id)
    document_uuid = UUID(document_id)
    
    async with async_session_factory() as session:
        provider = create_embedding_provider()
        orchestrator = IngestionOrchestrator(session, provider)
        
        try:
            result = await orchestrator.ingest_document_version(version_uuid)
            await session.commit()
            return {
                "document_version_id": str(result.document_version_id),
                "chunks_count": result.chunks_count,
                "embeddings_count": result.embeddings_count,
                "status": result.status,
            }
        except (
            PermanentEmbeddingProviderError,
            EmbeddingProviderConfigurationError,
            ValueError,
            IntegrityError,
            ProgrammingError,
            DataError,
            InvalidRequestError,
            DBAPIError,
        ) as exc:
            await session.rollback()
            raise  # ARQ will NOT retry (permanent failure)
        except (
            TransientEmbeddingProviderError,
            OperationalError,
            DisconnectionError,
            TimeoutError,
        ) as exc:
            await session.rollback()
            raise  # ARQ will retry (if attempts remain)
        # Any other exception: also NOT retried (no catch-all retry).
        # The session rollback happens via context manager exit.
```

### 6.2 Retry policy

- `max_tries=3` → 3 total executions (1 initial + 2 retries)
- `ctx["job_try"]` = 1 on first failure → defer 2 seconds
- `ctx["job_try"]` = 2 on second failure → defer 4 seconds
- `ctx["job_try"]` = 3 on third failure → no more retries, job fails
- No jitter is applied; delays are strictly deterministic.

### 6.3 Deduplication

- Job key: `f"document-ingestion:{version_id}"`
- `enqueue_job(..., _job_id=job_key)`
- If returns `None`: duplicate active/recent job → return 409
- `keep_result=300`: job result retained for 5 minutes
- After 300 seconds: job key expires, re-ingestion allowed

### 6.4 Transaction semantics

- Each attempt creates a new `AsyncSession` via `async_session_factory()`
- On success: commit transaction
- On failure: rollback transaction (explicit `await session.rollback()`)
- No partial `KnowledgeChunk` replacement after failure
- Atomic replacement: delete old chunks, insert new chunks, flush, commit

### 6.5 Error handling

```python
try:
    result = await orchestrator.ingest_document_version(version_id)
    await session.commit()
    return result
except (
    PermanentEmbeddingProviderError,
    EmbeddingProviderConfigurationError,
    ValueError,
    IntegrityError,
) as exc:
    await session.rollback()
    raise  # ARQ will NOT retry (permanent failure)
except TransientEmbeddingProviderError as exc:
    await session.rollback()
    raise  # ARQ will retry (if attempts remain)
```

### 6.6 Database exception classification

SQLAlchemy database exceptions are explicitly classified as transient or permanent. Only transient DB errors trigger ARQ retries.

| SQLAlchemy exception | Classification | Retry behavior |
|---------------------|----------------|----------------|
| OperationalError (connection, deadlock) | Transient | Retry |
| DisconnectionError | Transient | Retry |
| TimeoutError (DB) | Transient | Retry |
| IntegrityError (unique, FK) | Permanent | Never retry |
| ProgrammingError (syntax, missing column) | Permanent | Never retry |
| DataError (type mismatch, overflow) | Permanent | Never retry |
| InvalidRequestError | Permanent | Never retry |
| SQLAlchemy general DBAPIError | Permanent | Never retry |

Any DB exception not explicitly classified as transient is treated as permanent and is NOT retried.

---

## 7. Provider factory and error contract

### 7.1 Factory function

**Location**: `backend/app/services/embedding_provider_factory.py` (new file)

```python
def create_embedding_provider(
    provider_name: str | None = None,
) -> EmbeddingProvider:
    """Create an embedding provider based on configuration or explicit name.
    
    Args:
        provider_name: Override settings.embedding_provider
        
    Returns:
        Configured EmbeddingProvider
        
    Raises:
        EmbeddingProviderConfigurationError: unknown provider, missing API key,
        fake provider in production/staging
    """
```

### 7.2 Provider selection logic

1. If `provider_name` is None, use `settings.embedding_provider`
2. If `provider_name == "fake"`:
   - If `settings.environment` is production or staging: raise `EmbeddingProviderConfigurationError`
   - Else: return `FakeEmbeddingProvider(dimension=settings.embedding_dimensions)`
3. If `provider_name == "openai"`:
   - If `settings.openai_api_key` is empty AND `settings.openai_api_base` is official (`https://api.openai.com/v1`):
     - Raise `EmbeddingProviderConfigurationError("API key required for official OpenAI endpoint")`
   - If `settings.openai_api_key` is empty AND `settings.openai_api_base` is custom:
     - Use sentinel value `"sentinel-not-a-real-key"` (non-secret, required by SDK)
   - Return `OpenAIEmbeddingProvider(...)` with `max_retries=0`
4. Else: raise `EmbeddingProviderConfigurationError(f"Unknown embedding provider: {provider_name}")`

### 7.3 Error hierarchy

**Location**: `backend/app/services/embedding_provider.py` (add to existing file)

```python
class EmbeddingProviderError(Exception):
    """Base class for embedding provider errors."""

class TransientEmbeddingProviderError(EmbeddingProviderError):
    """Retryable error (connection, timeout, rate limit, 5xx)."""

class PermanentEmbeddingProviderError(EmbeddingProviderError):
    """Non-retryable error (malformed response, dimension mismatch, NaN/Inf)."""

class EmbeddingProviderConfigurationError(EmbeddingProviderError):
    """Fatal configuration error (missing API key, unknown provider)."""
```

### 7.4 Error classification in OpenAIEmbeddingProvider

```python
async def embed_text(self, texts: list[str]) -> list[list[float]]:
    try:
        response = await self._client.embeddings.create(...)
    except (openai.APIConnectionError, openai.APITimeoutError) as exc:
        raise TransientEmbeddingProviderError(...) from exc
    except openai.RateLimitError as exc:
        raise TransientEmbeddingProviderError(...) from exc
    except openai.APIStatusError as exc:
        if 500 <= exc.status_code < 600:
            raise TransientEmbeddingProviderError(...) from exc
        else:
            raise PermanentEmbeddingProviderError(...) from exc
    except Exception as exc:
        raise PermanentEmbeddingProviderError(...) from exc
    
    # Validate response
    if not response.data:
        raise PermanentEmbeddingProviderError("no data returned")
    
    if len(response.data) != len(texts):
        raise PermanentEmbeddingProviderError(
            f"count mismatch: expected {len(texts)}, got {len(response.data)}"
        )
    
    for item in response.data:
        embedding = item.embedding
        if not isinstance(embedding, list):
            raise PermanentEmbeddingProviderError("malformed embedding")
        
        if len(embedding) != self._expected_dimension:
            raise PermanentEmbeddingProviderError(
                f"dimension mismatch: expected {self._expected_dimension}, got {len(embedding)}"
            )
        
        for v in embedding:
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise PermanentEmbeddingProviderError("non-finite value in embedding")
    
    return [[float(v) for v in item.embedding] for item in response.data]
```

### 7.5 OpenAIEmbeddingProvider constructor repair

```python
def __init__(
    self,
    *,
    api_key: str,
    model: str = "text-embedding-3-small",
    dimension: int = 1536,
    base_url: str | None = None,
    timeout_seconds: int = 30,
) -> None:
    if not api_key:
        raise EmbeddingProviderConfigurationError("api_key must not be empty")
    if dimension <= 0:
        raise EmbeddingProviderConfigurationError(f"dimension must be positive, got {dimension}")

    self._model = model
    self._expected_dimension = dimension
    self._timeout_seconds = timeout_seconds

    client_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "timeout": float(timeout_seconds),
        "max_retries": 0,  # Disable SDK retries, ARQ owns retry
    }
    if base_url is not None:
        client_kwargs["base_url"] = base_url

    self._client = AsyncOpenAI(**client_kwargs)
```

### 7.6 IngestionOrchestrator preservation

```python
async def _generate_embeddings(
    self,
    chunks: list[ChunkData],
) -> list[list[float]]:
    """Generate embeddings for a list of chunks.
    
    Raises:
        TransientEmbeddingProviderError: retryable provider error
        PermanentEmbeddingProviderError: non-retryable provider error
        EmbeddingProviderConfigurationError: configuration error
        ValueError: chunking failed
    """
    if not chunks:
        return []

    texts = [chunk.chunk_text for chunk in chunks]
    # Do NOT wrap provider errors — preserve typed errors for ARQ retry logic
    return await self._embedding_provider.embed_text(texts)
```

---

## 8. Seed-loader/async-phase lifecycle

### 8.1 Current state

- `loader.py:main()` calls `load_golden_dataset()` (synchronous)
- `load_golden_dataset()` commits all seed data in one transaction
- No async ingestion phase exists
- No DocumentVersion ingestion

### 8.2 Target state

**Location**: Modify `backend/app/seed/generator/loader.py`

```python
def main() -> None:
    """CLI entry point for seed generator."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        # Phase 1: synchronous seed load
        counts = load_golden_dataset()

        logger.info("Golden Dataset loaded successfully")
        logger.info("Inserted records:")
        for k, v in counts.items():
            logger.info("  %s: %s", k, v)

        # Phase 2: async ingestion
        logger.info("Starting async document ingestion phase...")
        failed_versions = asyncio.run(_ingest_seed_documents())

        if failed_versions:
            logger.error(f"Failed to ingest {len(failed_versions)} versions: {failed_versions}")
            raise SystemExit(1)

        logger.info("All seed documents ingested successfully")

    except RuntimeError as e:
        logger.error(f"Error: {e}")
        raise SystemExit(1) from None
    except Exception as e:
        logger.error(f"Database error: {e}")
        raise SystemExit(1) from None


async def _ingest_seed_documents() -> list[UUID]:
    """Ingest all DocumentVersions using configured provider.
    
    Returns:
        List of version IDs that failed ingestion
    """
    from app.database import async_session_factory
    from app.services.embedding_provider_factory import create_embedding_provider
    from app.services.ingestion import IngestionOrchestrator
    from app.models.document import DocumentVersion
    from sqlalchemy import select
    
    provider = create_embedding_provider()  # explicit provider selection
    failed_versions: list[UUID] = []
    
    # Query all DocumentVersions
    async with async_session_factory() as session:
        result = await session.execute(select(DocumentVersion))
        versions = result.scalars().all()
    
    if not versions:
        logger.info("No DocumentVersions found, skipping ingestion")
        return []
    
    logger.info(f"Found {len(versions)} DocumentVersions to ingest")
    
    # Ingest each version in its own transaction
    for version in versions:
        try:
            async with async_session_factory() as version_session:
                orchestrator = IngestionOrchestrator(version_session, provider)
                result = await orchestrator.ingest_document_version(version.id)
                await version_session.commit()
                logger.info(
                    f"Ingested version {version.id}: "
                    f"{result.chunks_count} chunks, {result.embeddings_count} embeddings"
                )
        except Exception as exc:
            try:
                await version_session.rollback()
            except Exception:
                pass  # rollback best-effort
            logger.error(f"Failed to ingest version {version.id}: {exc}")
            failed_versions.append(version.id)
    
    return failed_versions
```

### 8.3 Lifecycle guarantees

1. Sync seed data commits before async phase starts
2. Each version gets its own async session
3. Each version transaction commits only on success
4. Each version transaction rolls back on failure
5. All versions are attempted (no early exit)
6. Failed version IDs are aggregated
7. Non-zero exit code if any version failed
8. Reruns are safe (atomic replacement via IngestionOrchestrator)

---

## 9. Transaction and rollback model

### 9.1 API endpoint transaction

- No database transaction in endpoint handler
- Endpoint only enqueues ARQ job
- 202 returned only after Redis accepts job
- 503 returned if Redis enqueue fails
- 409 returned if duplicate active job

### 9.2 ARQ worker transaction

```python
async def run_document_ingestion(ctx, version_id, document_id):
    async with async_session_factory() as session:
        provider = create_embedding_provider()
        orchestrator = IngestionOrchestrator(session, provider)
        
        try:
            result = await orchestrator.ingest_document_version(version_id)
            await session.commit()
            return result
        except Exception:
            await session.rollback()
            raise
```

### 9.3 Orchestrator transaction semantics

- `IngestionOrchestrator.ingest_document_version()` does NOT commit (verified at line 43-46)
- Caller owns transaction
- Orchestrator flushes after storage (rows visible within transaction, line 109)
- On success: caller commits
- On failure: caller rolls back
- No partial `KnowledgeChunk` replacement after failure

### 9.4 Atomic replacement

```python
async def _store_knowledge_chunks(self, version_id, chunks, embeddings):
    # Delete existing chunks (within transaction)
    result = await self._session.execute(
        select(KnowledgeChunk).where(
            KnowledgeChunk.document_version_id == version_id
        )
    )
    for existing in result.scalars().all():
        await self._session.delete(existing)
    
    # Insert new chunks (within transaction)
    for chunk, embedding in zip(chunks, embeddings, strict=True):
        kc = KnowledgeChunk(...)
        self._session.add(kc)
    
    # Flush (not commit)
    await self._session.flush()
```

If commit fails, all changes (delete + insert) are rolled back together.

---

## 10. Proposed file inventory

### 10.1 New files

1. `backend/app/services/embedding_provider_factory.py` — provider factory
2. `backend/app/jobs/ingestion.py` — ARQ worker function
3. `backend/app/api/ingestion.py` — API endpoint
4. `backend/tests/unit/test_embedding_provider_factory.py` — factory unit tests
5. `backend/tests/unit/test_embedding_provider_errors.py` — typed error unit tests
6. `backend/tests/integration/test_ingestion_endpoint.py` — endpoint integration tests
7. `backend/tests/integration/test_ingestion_worker.py` — worker integration tests

### 10.2 Modified files

1. `backend/app/services/embedding_provider.py` — add typed errors, NaN/Inf validation, `max_retries=0`
2. `backend/app/services/ingestion.py` — preserve typed errors (no RuntimeError conversion)
3. `backend/app/seed/generator/loader.py` — add async ingestion phase (`_ingest_seed_documents()`)
4. `backend/app/main.py` — register ingestion endpoint router
5. `backend/app/worker.py` — register ingestion worker function in `WorkerSettings.functions`

### 10.3 Unchanged files

- All Source of Truth documents
- All migration files
- All model files
- All existing tests (no test removal or modification)
- `backend/app/services/diagnostic_jobs.py` (no modification)
- `backend/app/jobs/diagnostics.py` (no modification)

---

## 11. Bounded delegation sequence

### 11.1 Phase 1: WP-4.3B0 — Provider Contract Repair

**TASK_ID**: WP43B0-PROVIDER-REPAIR-01  
**ROLE**: IMPLEMENTER  
**MODE**: PATCH-ALLOWED  
**Scope**:
- Add typed error hierarchy to `backend/app/services/embedding_provider.py`
- Add NaN/Inf validation with `math.isfinite()` at line 168
- Set `max_retries=0` on `AsyncOpenAI` constructor at line 124
- Classify errors into transient/permanent/configuration
- Preserve exception chaining with `raise ... from`
- Modify `backend/app/services/ingestion.py` to preserve typed errors (remove RuntimeError wrapping at line 199-201)

**Deliverables**:
- Modified `backend/app/services/embedding_provider.py`
- Modified `backend/app/services/ingestion.py`
- Unit tests for error classification
- Unit tests for NaN/Inf rejection

**Verification**:
- `cd backend && ../.venv/bin/pytest tests/unit/test_embedding_provider_errors.py -v`
- `cd backend && ../.venv/bin/ruff check app/services/embedding_provider.py`
- `cd backend && ../.venv/bin/mypy app/services/embedding_provider.py`

**Read Allowlist**:
- `backend/app/services/embedding_provider.py`
- `backend/app/services/ingestion.py`
- `backend/tests/unit/test_embedding_provider.py`
- `backend/app/config.py`

**Patch Allowlist**:
- `backend/app/services/embedding_provider.py`
- `backend/app/services/ingestion.py`
- `backend/tests/unit/test_embedding_provider_errors.py`

**Timeout**: 30 minutes

**Max Turns**: 50

**Behavioral Tests**:
1. TransientEmbeddingProviderError raised on openai.APIConnectionError
2. TransientEmbeddingProviderError raised on openai.APITimeoutError
3. TransientEmbeddingProviderError raised on openai.RateLimitError
4. TransientEmbeddingProviderError raised on 5xx openai.APIStatusError
5. PermanentEmbeddingProviderError raised on 4xx openai.APIStatusError
6. PermanentEmbeddingProviderError raised on malformed response
7. PermanentEmbeddingProviderError raised on dimension mismatch
8. PermanentEmbeddingProviderError raised on NaN values (math.isfinite)
9. PermanentEmbeddingProviderError raised on Inf values (math.isfinite)
10. EmbeddingProviderConfigurationError raised on missing API key
11. AsyncOpenAI constructed with max_retries=0
12. IngestionOrchestrator preserves typed provider errors (no RuntimeError wrapping)
13. Exception chaining preserved via raise ... from

**Manager Gates**:
- pytest exit code 0 on test_embedding_provider_errors.py
- ruff exit code 0 on patched files
- mypy exit code 0 on patched files
- No unrelated file changes (diff limited to allowlist)

**Stop Conditions**:
- Task timeout exceeded (30 minutes)
- Max turns exceeded (50)
- Unrecoverable error (report to manager)
- Scope creep detected (stop and report)

### 11.2 Phase 2: Provider Factory

**TASK_ID**: WP43B-FACTORY-01  
**ROLE**: IMPLEMENTER  
**MODE**: PATCH-ALLOWED  
**Scope**:
- Create `backend/app/services/embedding_provider_factory.py`
- Implement provider selection logic
- Implement environment validation (production/staging reject fake)
- Implement API key validation

**Deliverables**:
- New `backend/app/services/embedding_provider_factory.py`
- Unit tests for factory

**Verification**:
- `cd backend && ../.venv/bin/pytest tests/unit/test_embedding_provider_factory.py -v`
- `cd backend && ../.venv/bin/ruff check app/services/embedding_provider_factory.py`
- `cd backend && ../.venv/bin/mypy app/services/embedding_provider_factory.py`

**Read Allowlist**:
- `backend/app/services/embedding_provider.py`
- `backend/app/services/embedding_provider_factory.py`
- `backend/app/config.py`
- `backend/tests/unit/test_embedding_provider_factory.py`

**Patch Allowlist**:
- `backend/app/services/embedding_provider_factory.py`
- `backend/tests/unit/test_embedding_provider_factory.py`

**Timeout**: 30 minutes

**Max Turns**: 50

**Behavioral Tests**:
1. Factory creates OpenAIEmbeddingProvider when name is "openai" with valid API key
2. Factory creates FakeEmbeddingProvider when name is "fake" in development
3. Factory raises EmbeddingProviderConfigurationError when name is "fake" in production
4. Factory raises EmbeddingProviderConfigurationError when name is "fake" in staging
5. Factory raises EmbeddingProviderConfigurationError when API key missing for official endpoint
6. Factory uses sentinel when API key missing for custom endpoint
7. Factory raises EmbeddingProviderConfigurationError for unknown provider name
8. Factory uses settings.embedding_provider when provider_name is None

**Manager Gates**:
- pytest exit code 0 on test_embedding_provider_factory.py
- ruff exit code 0 on patched files
- mypy exit code 0 on patched files
- No unrelated file changes (diff limited to allowlist)

**Stop Conditions**:
- Task timeout exceeded (30 minutes)
- Max turns exceeded (50)
- Unrecoverable error (report to manager)
- Scope creep detected (stop and report)

### 11.3 Phase 3: ARQ Worker Function

**TASK_ID**: WP43B-WORKER-01  
**ROLE**: IMPLEMENTER  
**MODE**: PATCH-ALLOWED  
**Scope**:
- Create `backend/app/jobs/ingestion.py`
- Implement retry policy (max_tries=3, defer 2s/4s)
- Implement transaction with rollback
- Register worker in `backend/app/worker.py` (add to `WorkerSettings.functions`)

**Deliverables**:
- New `backend/app/jobs/ingestion.py`
- Modified `backend/app/worker.py`
- Integration tests for worker

**Verification**:
- `cd backend && ../.venv/bin/pytest tests/integration/test_ingestion_worker.py -v`
- `cd backend && ../.venv/bin/ruff check app/jobs/ingestion.py`
- `cd backend && ../.venv/bin/mypy app/jobs/ingestion.py`

**Read Allowlist**:
- `backend/app/jobs/ingestion.py`
- `backend/app/worker.py`
- `backend/app/services/embedding_provider_factory.py`
- `backend/app/services/ingestion.py`
- `backend/app/database.py`
- `backend/tests/integration/test_ingestion_worker.py`

**Patch Allowlist**:
- `backend/app/jobs/ingestion.py`
- `backend/app/worker.py`
- `backend/tests/integration/test_ingestion_worker.py`

**Timeout**: 30 minutes

**Max Turns**: 50

**Behavioral Tests**:
1. Worker decorated with @worker(keep_result=300, max_tries=3)
2. Worker calls create_embedding_provider() and IngestionOrchestrator
3. Worker commits session on successful ingestion
4. Worker rolls back session on failure
5. Worker defers 2 seconds on first failure (job_try=1)
6. Worker defers 4 seconds on second failure (job_try=2)
7. Worker does not retry PermanentEmbeddingProviderError
8. Worker does not retry EmbeddingProviderConfigurationError
9. Worker does not retry ValueError or IntegrityError
10. Worker retries TransientEmbeddingProviderError
11. Worker registered in WorkerSettings.functions
12. Worker uses deterministic job ID document-ingestion:{version_id}

**Manager Gates**:
- pytest exit code 0 on test_ingestion_worker.py
- ruff exit code 0 on patched files
- mypy exit code 0 on patched files
- No unrelated file changes (diff limited to allowlist)

**Stop Conditions**:
- Task timeout exceeded (30 minutes)
- Max turns exceeded (50)
- Unrecoverable error (report to manager)
- Scope creep detected (stop and report)

### 11.4 Phase 4: API Endpoint

**TASK_ID**: WP43B-ENDPOINT-01  
**ROLE**: IMPLEMENTER  
**MODE**: PATCH-ALLOWED  
**Scope**:
- Create `backend/app/api/ingestion.py`
- Implement AI_ADMINISTRATOR authentication
- Implement document/version path validation (query with BOTH conditions)
- Implement enqueue with deduplication
- Implement 202/409/503 responses
- Register router in `backend/app/main.py`

**Deliverables**:
- New `backend/app/api/ingestion.py`
- Modified `backend/app/main.py`
- Integration tests for endpoint

**Verification**:
- `cd backend && ../.venv/bin/pytest tests/integration/test_ingestion_endpoint.py -v`
- `cd backend && ../.venv/bin/ruff check app/api/ingestion.py`
- `cd backend && ../.venv/bin/mypy app/api/ingestion.py`

**Read Allowlist**:
- `backend/app/api/ingestion.py`
- `backend/app/main.py`
- `backend/app/services/diagnostic_jobs.py`
- `backend/tests/integration/test_ingestion_endpoint.py`

**Patch Allowlist**:
- `backend/app/api/ingestion.py`
- `backend/app/main.py`
- `backend/tests/integration/test_ingestion_endpoint.py`

**Timeout**: 30 minutes

**Max Turns**: 50

**Behavioral Tests**:
1. Endpoint decorated with @router.post for correct path
2. Endpoint requires AI_ADMINISTRATOR role
3. Endpoint returns 403 for non-AI_ADMINISTRATOR users
4. Endpoint queries DocumentVersion with BOTH version_id AND document_id
5. Endpoint returns identical 404 for missing version
6. Endpoint returns identical 404 for mismatched document/version
7. Endpoint enqueues job with deterministic ID document-ingestion:{version_id}
8. Endpoint returns 202 with job_id, correlation_id, status="pending" on success
9. Endpoint returns 409 when duplicate active job exists
10. Endpoint returns 503 when Redis enqueue fails
11. Router registered in main.py

**Manager Gates**:
- pytest exit code 0 on test_ingestion_endpoint.py
- ruff exit code 0 on patched files
- mypy exit code 0 on patched files
- No unrelated file changes (diff limited to allowlist)

**Stop Conditions**:
- Task timeout exceeded (30 minutes)
- Max turns exceeded (50)
- Unrecoverable error (report to manager)
- Scope creep detected (stop and report)

### 11.5 Phase 5: Seed Async Bridge

**TASK_ID**: WP43B-SEED-BRIDGE-01  
**ROLE**: IMPLEMENTER  
**MODE**: PATCH-ALLOWED  
**Scope**:
- Add `_ingest_seed_documents()` async function to `backend/app/seed/generator/loader.py`
- Modify `main()` to call `asyncio.run(_ingest_seed_documents())` after sync commit
- Implement per-version transaction
- Implement failure aggregation
- Implement non-zero exit code

**Deliverables**:
- Modified `backend/app/seed/generator/loader.py`
- Integration tests for seed ingestion

**Verification**:
- `cd backend && ../.venv/bin/pytest tests/integration/test_seed_ingestion.py -v`
- `cd backend && ../.venv/bin/ruff check app/seed/generator/loader.py`
- `cd backend && ../.venv/bin/mypy app/seed/generator/loader.py`
- Manual: `cd backend && ../.venv/bin/python -m app.seed.generator.loader` succeeds with fake provider

**Read Allowlist**:
- `backend/app/seed/generator/loader.py`
- `backend/app/services/embedding_provider_factory.py`
- `backend/tests/integration/test_seed_ingestion.py`

**Patch Allowlist**:
- `backend/app/seed/generator/loader.py`
- `backend/tests/integration/test_seed_ingestion.py`

**Timeout**: 30 minutes

**Max Turns**: 50

**Behavioral Tests**:
1. Async ingestion phase runs after sync seed load
2. Each DocumentVersion gets its own async session
3. Successful ingestion commits the version transaction
4. Failed ingestion rolls back the version transaction
5. All versions attempted even if some fail
6. Failed version IDs aggregated in list
7. Non-zero exit code (SystemExit(1)) when failures occur
8. Zero exit code when all succeed
9. Uses create_embedding_provider() with explicit selection
10. No silent fake-provider fallback

**Manager Gates**:
- pytest exit code 0 on test_seed_ingestion.py
- ruff exit code 0 on patched files
- mypy exit code 0 on patched files
- Manual seed command exit code 0 with fake provider
- No unrelated file changes (diff limited to allowlist)

**Stop Conditions**:
- Task timeout exceeded (30 minutes)
- Max turns exceeded (50)
- Unrecoverable error (report to manager)
- Scope creep detected (stop and report)

### 11.6 Phase 6: E2E Tests

**TASK_ID**: WP43B-E2E-01  
**ROLE**: TEST_IMPLEMENTER  
**MODE**: PATCH-ALLOWED  
**Scope**:
- Create E2E test for full ingestion flow
- Use fake provider (no network)
- Verify 202 response
- Verify job execution
- Verify KnowledgeChunk creation

**Deliverables**:
- New `backend/tests/e2e/test_ingestion_e2e.py`

**Verification**:
- `cd backend && ../.venv/bin/pytest tests/e2e/test_ingestion_e2e.py -v`

**Read Allowlist**:
- `backend/app/api/ingestion.py`
- `backend/app/jobs/ingestion.py`
- `backend/app/services/embedding_provider.py`
- `backend/tests/e2e/test_ingestion_e2e.py`

**Patch Allowlist**:
- `backend/tests/e2e/test_ingestion_e2e.py`

**Timeout**: 30 minutes

**Max Turns**: 50

**Behavioral Tests**:
1. E2E test creates a document and version
2. POST to ingestion endpoint returns 202
3. Job executes successfully
4. KnowledgeChunks created with embeddings
5. Fake provider used (no network calls)
6. Full workflow completes end-to-end

**Manager Gates**:
- pytest exit code 0 on test_ingestion_e2e.py
- No network calls detected (fake provider only)
- No unrelated file changes (diff limited to allowlist)

**Stop Conditions**:
- Task timeout exceeded (30 minutes)
- Max turns exceeded (50)
- Unrecoverable error (report to manager)
- Scope creep detected (stop and report)

### 11.7 Phase 7: Full Verification

**TASK_ID**: WP43B-VERIFY-01  
**ROLE**: REVIEWER  
**MODE**: READ-ONLY  
**Scope**:
- Run full test suite
- Run full lint suite
- Run full mypy
- Verify no regressions

**Deliverables**:
- Verification report

**Verification**:
- `make test`
- `make lint`
- `make mypy`

**Read Allowlist**:
- `backend/tests/` (all tests, read-only)
- `backend/app/` (all application code, read-only)

**Patch Allowlist**:
- (none — READ-ONLY mode)

**Timeout**: 30 minutes

**Max Turns**: 50

**Behavioral Tests**:
1. All unit tests pass
2. All integration tests pass
3. All E2E tests pass
4. Ruff passes with zero errors
5. mypy passes with zero errors
6. No regressions compared to baseline

**Manager Gates**:
- make test exit code 0
- make lint exit code 0
- make mypy exit code 0
- No unrelated file changes (no patches permitted in READ-ONLY mode)

**Stop Conditions**:
- Task timeout exceeded (30 minutes)
- Max turns exceeded (50)
- Unrecoverable error (report to manager)
- Any gate failure (report to manager, do not attempt fixes)

### 11.8 Generic Failure Workflow

When any implementation task fails:

1. Preserve exact failing logs
   - Capture full pytest/ruff/mypy output
   - Save to docs/planning/failures/{TASK_ID}_{timestamp}.log

2. Fresh READ-ONLY DIAGNOSTIC worker
   - TASK_ID: {TASK_ID}-DIAG-01
   - ROLE: DIAGNOSTIC
   - MODE: READ-ONLY
   - Input: exact failing logs
   - Output: root cause analysis + recommended patch

3. Manager validates diagnosis
   - Review diagnostic report
   - Confirm root cause is correctly identified
   - Approve or reject diagnostic findings

4. Fresh IMPLEMENTER_CORRECTION worker
   - TASK_ID: {TASK_ID}-CORRECTION-01
   - ROLE: IMPLEMENTER_CORRECTION
   - MODE: PATCH-ALLOWED
   - Input: exact patch allowlist from diagnostic report
   - Apply ONLY the approved patch
   - No scope expansion

5. Rerun affected and authoritative gates
   - Run pytest on affected tests
   - Run full authoritative gates (pytest, ruff, mypy)
   - Report pass/fail

Manager direct-edit target remains zero. All corrections go through workers.

---

## 12. Unit/integration/E2E test matrix

### 12.1 Unit tests

| Test file | Coverage | Assertions |
|-----------|----------|------------|
| `test_embedding_provider_errors.py` | Typed error hierarchy | Transient/permanent/configuration errors are distinguishable |
| `test_embedding_provider_factory.py` | Factory logic | Correct provider created for each config; production rejects fake; local endpoint works without API key |
| `test_embedding_provider.py` (extended) | NaN/Inf rejection | Non-finite values raise PermanentEmbeddingProviderError |

### 12.2 Integration tests

| Test file | Coverage | Assertions |
|-----------|----------|------------|
| `test_ingestion_endpoint.py` | Endpoint behavior | AI_ADMINISTRATOR-only; 404 for missing/mismatched; 202 with real job ID; 409 for duplicate; 503 for Redis failure |
| `test_ingestion_worker.py` | Worker behavior | max_tries=3; retry delays 2s/4s; permanent failures not retried; transaction rollback on failure; no partial chunks |
| `test_seed_ingestion.py` | Seed async bridge | Seed data commits before async phase; per-version transaction; failure aggregation; non-zero exit code |

### 12.3 E2E tests

| Test file | Coverage | Assertions |
|-----------|----------|------------|
| `test_ingestion_e2e.py` | Full flow | POST → 202 → job executes → KnowledgeChunk created; fake provider used; no network calls |

### 12.4 Negative tests

| Scenario | Expected behavior |
|----------|-------------------|
| Non-AI_ADMINISTRATOR user | 403 Forbidden |
| Missing document_id | 404 Not Found |
| Missing version_id | 404 Not Found |
| Mismatched document_id/version_id | 404 Not Found (identical to missing) |
| Duplicate active job | 409 Conflict |
| Redis failure | 503 Service Unavailable |
| Permanent embedding error | No retry; job fails immediately |
| Transient embedding error | Retry after 2s, then 4s |
| Third failure | No more retries; job fails |
| NaN/Inf in embedding | PermanentEmbeddingProviderError |

---

## 13. Acceptance criteria

### 13.1 Provider factory and runtime contract (DEC-WP43B-10)

- [ ] AC-01: Factory creates correct provider for every supported configuration
- [ ] AC-02: Production/staging reject fake provider
- [ ] AC-03: Local OpenAI-compatible provider works without user-supplied API key
- [ ] AC-04: OpenAI SDK internal retries disabled (max_retries=0)
- [ ] AC-05: NaN and Inf embeddings are rejected
- [ ] AC-06: Transient and permanent provider errors are distinguishable

### 13.2 Retry policy (DEC-WP43B-08)

- [ ] AC-07: ARQ performs at most three total executions
- [ ] AC-08: Retry delays are deterministically 2 and 4 seconds
- [ ] AC-09: Permanent failures are never retried
- [ ] AC-10: Every failed attempt rolls back its transaction
- [ ] AC-11: No partial KnowledgeChunk replacement remains after failure

### 13.3 Authentication, authorization and path mismatch (DEC-WP43B-11)

- [ ] AC-12: Endpoint is AI_ADMINISTRATOR-only
- [ ] AC-13: Missing and mismatched document/version combinations both return 404

### 13.4 Enqueue atomicity (DEC-WP43B-12)

- [ ] AC-14: Successful enqueue returns 202 with real ARQ job ID
- [ ] AC-15: Redis failure returns 503

### 13.5 Job deduplication (DEC-WP43B-13)

- [ ] AC-16: Duplicate active ingestion returns 409
- [ ] AC-17: Two simultaneous requests for one version create at most one ARQ job
- [ ] AC-18: Separate versions can be queued independently

### 13.6 Seed async bridge (DEC-WP43B-09)

- [ ] AC-19: Seed data commits before async ingestion phase starts
- [ ] AC-20: Every seed ingestion uses a separate async transaction
- [ ] AC-21: Seed ingestion failures are aggregated and cause non-zero command exit

### 13.7 Test isolation (DEC-WP43B-10)

- [ ] AC-22: Explicit fake provider can be used by automated tests without network
- [ ] AC-23: No automated test contacts an external embedding endpoint

### 13.8 Package-level gates

- [ ] AC-24: Full unit, integration, Ruff, mypy and E2E gates pass
- [ ] AC-25: Retrieval, vector similarity indexing, citations, AT-006 and AT-007 remain explicitly out of scope

---

## 14. CI-equivalent verification commands

### 14.1 Pre-implementation baseline

```bash
# Verify clean state
git status --short
# Expected: empty

# Verify base commit
git rev-parse HEAD
# Expected: b384c839e7f19dd7817c58c21331c5d4fe102f08
```

### 14.2 Unit tests

```bash
cd backend
../.venv/bin/pytest tests/unit/test_embedding_provider_errors.py -v
../.venv/bin/pytest tests/unit/test_embedding_provider_factory.py -v
../.venv/bin/pytest tests/unit/test_embedding_provider.py -v
```

### 14.3 Integration tests

```bash
cd backend
../.venv/bin/pytest tests/integration/test_ingestion_endpoint.py -v
../.venv/bin/pytest tests/integration/test_ingestion_worker.py -v
../.venv/bin/pytest tests/integration/test_seed_ingestion.py -v
```

### 14.4 E2E tests

```bash
cd backend
../.venv/bin/pytest tests/e2e/test_ingestion_e2e.py -v
```

### 14.5 Full test suite

```bash
make test
# Expected: all tests pass
```

### 14.6 Lint

```bash
make lint
# Expected: no errors
```

### 14.7 Type checking

```bash
make mypy
# Expected: no errors
```

### 14.8 Seed ingestion (manual)

```bash
# With fake provider
export FORGEMIND_ENVIRONMENT=development
export FORGEMIND_EMBEDDING_PROVIDER=fake
cd backend
../.venv/bin/python -m app.seed.generator.loader
# Expected: all seed data loaded, all versions ingested, exit code 0
```

### 14.9 Git verification

```bash
git status --short
# Expected: empty (all changes committed)

git diff main..feature/phase-4-wp-4-3b-ingestion-integration --stat
# Expected: only files listed in Section 10
```

---

## 15. Rollback plan

### 15.1 Branch deletion

```bash
git checkout main
git branch -D feature/phase-4-wp-4-3b-ingestion-integration
```

### 15.2 No database migration

- WP-4.3B does not introduce new migrations
- Existing schema (document_versions, knowledge_chunks) unchanged
- No rollback of schema required

### 15.3 No deployment

- WP-4.3B is backend-only
- No infrastructure changes
- No configuration changes (except optional `FORGEMIND_EMBEDDING_PROVIDER`)
- Rollback = branch deletion

### 15.4 Seed data

- If seed ingestion fails, existing seed data (products, components, etc.) remains intact
- KnowledgeChunks may be partially created
- Re-running seed command will atomically replace (delete + insert) KnowledgeChunks
- No manual cleanup required

---

## 16. Stop conditions

### 16.1 Do not proceed without Product Owner approval for:

- Changing infrastructure state (Docker, Redis, Postgres)
- Changing credentials or secrets
- Deleting data or volumes
- Changing the approved architecture
- Modifying Source of Truth documents
- Adding dependencies
- Expanding work-package scope
- Committing unexpected files
- Pushing
- Creating a PR
- Merging

### 16.2 Stop and report if:

- A command fails and classification is unclear
- A test fails and root cause is not identified
- A dependency conflict arises
- An environment defect is suspected (not a code defect)
- Scope creep is attempted (retrieval, citations, AT-006, AT-007)
- A worker produces factually incorrect output (reconnaissance rejected)

### 16.3 Do not:

- Implement WP-4.3B0 or WP-4.3B until planning is approved
- Modify application code until planning is approved
- Modify tests until planning is approved
- Commit until planning is approved
- Push until planning is approved
- Create a PR until planning is approved
- Merge until planning is approved
- Implement retrieval, vector indexing, citations, AT-006, AT-007
- Contact external embedding endpoints in tests
- Use silent fake-provider fallback
- Construct nested event loops manually
- Create database ingestion-status table
- Return fake job identifiers

---

## 17. Decision traceability table

| Decision ID | Status | Section | Acceptance criteria |
|-------------|--------|---------|---------------------|
| DEC-WP43B-08 | APPROVED_WITH_AMENDMENTS | 6 | AC-07, AC-08, AC-09, AC-10, AC-11 |
| DEC-WP43B-09 | APPROVED_WITH_AMENDMENTS | 8 | AC-19, AC-20, AC-21 |
| DEC-WP43B-10 | APPROVED_WITH_AMENDMENTS | 7 | AC-01, AC-02, AC-03, AC-04, AC-05, AC-06, AC-22, AC-23 |
| DEC-WP43B-11 | APPROVED | 5 | AC-12, AC-13 |
| DEC-WP43B-12 | APPROVED_WITH_AMENDMENTS | 5, 6 | AC-14, AC-15 |
| DEC-WP43B-13 | APPROVED | 6 | AC-16, AC-17, AC-18 |

---

## 18. Next Product Owner action

**Action**: Review and approve this planning specification.

**Approval grants**:
- Permission to create feature branch `feature/phase-4-wp-4-3b-ingestion-integration`
- Permission to implement WP-4.3B0 (provider contract repair)
- Permission to implement WP-4.3B (ingestion integration)
- Permission to commit and push
- Permission to create PR (not merge)

**After approval**:
1. Create feature branch from main
2. Implement WP-4.3B0 (provider repair)
3. Implement WP-4.3B Phases 2-5 (factory, worker, endpoint, seed bridge)
4. Implement E2E tests
5. Run full verification
6. Invoke independent planning reviewer
7. Report results to Product Owner
8. Await merge approval

**Reconnaissance note**: Local worker reconnaissance was rejected as unreliable. All repository evidence in this document was verified directly by manager via read_file and search_files. Repository structure differs from initial assumptions: API endpoints are flat under `backend/app/api/`, ARQ worker functions are in `backend/app/jobs/`.
