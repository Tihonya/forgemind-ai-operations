"""Document ingestion API router for WP-4.3B3.

Endpoint:
- POST /api/v1/documents/{document_id}/versions/{version_id}/ingest

Authorization:
*** AI_ADMINISTRATOR role required (RBAC via require_role dependency).

Flow:
1. Validate DocumentVersion exists for the given document_id + version_id
   (single combined query for ownership validation).
2. Enqueue the ARQ ingestion job with deterministic _job_id.
3. Return 202 with job_id, correlation_id, and status.

Error handling:
- 404: DocumentVersion not found (document doesn't exist, version doesn't exist,
  or version belongs to a different document).
- 409: An ingestion job is already active for this document version
  (ARQ enqueue_job returns None due to duplicate _job_id).
- 503: Redis/ARQ enqueue failure.

Testability:
- ``_pool_factory``: module-level async callable; production uses
  ``arq.connections.create_pool``. Tests monkeypatch this attribute on
  the module directly, no implementation-internals patching needed.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.context import get_correlation_id
from app.core.correlation import generate_correlation_id
from app.database import get_async_session
from app.dependencies import require_role
from app.models.document import DocumentVersion
from app.schemas.ingestion import IngestionEnqueueResponse
from app.services.auth_service import AuthenticatedUser

if TYPE_CHECKING:  # pragma: no cover - typing only
    from arq.connections import ArqRedis

router = APIRouter(tags=["Ingestion"])

# ---------------------------------------------------------------------------
# Pool-factory seam (mirrors diagnostic_jobs pattern)
# ---------------------------------------------------------------------------

PoolFactory = Callable[[], Awaitable["ArqRedis"]]


def _build_redis_settings() -> Any:
    """Build ARQ RedisSettings from app config without connecting."""
    from arq.connections import RedisSettings

    parsed = urlparse(settings.redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379
    path = parsed.path.lstrip("/")
    db = int(path) if path else 0
    password = parsed.password
    return RedisSettings(
        host=host,
        port=port,
        database=db,
        password=password,
    )


async def _default_pool_factory() -> ArqRedis:
    """Production pool factory wrapping arq.connections.create_pool."""
    from arq.connections import create_pool

    return await create_pool(_build_redis_settings())


# Module-level reference; monkeypatchable by tests.
_pool_factory: PoolFactory = _default_pool_factory


async def _get_version_and_enqueue(
    document_id: UUID,
    version_id: UUID,
    session: AsyncSession,
    correlation_id: str,
) -> IngestionEnqueueResponse:
    """Validate document version ownership and enqueue the ingestion job.

    Uses a single combined query to verify both document_id and version_id
    in one round-trip, ensuring the version belongs to the specified document.

    Args:
        document_id: Document UUID from path parameter.
        version_id: DocumentVersion UUID from path parameter.
        session: Active database session.
        correlation_id: Request correlation ID.

    Returns:
        IngestionEnqueueResponse with job_id, document_id, correlation_id, status.

    Raises:
        HTTPException(404): DocumentVersion not found.
        HTTPException(409): Duplicate job already active.
        HTTPException(503): Enqueue failed.
    """
    # 1. Validate document version exists with correct ownership (single query)
    result = await session.execute(
        select(DocumentVersion).where(
            DocumentVersion.id == version_id,
            DocumentVersion.document_id == document_id,
        )
    )
    doc_version = result.scalar_one_or_none()

    if doc_version is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "document_version_not_found",
                "message": "Document version not found",
            },
        )

    # 2. Build deterministic ARQ job id
    arq_job_id_value = f"document-ingestion:{version_id}"

    # 3. Create owned pool via _pool_factory
    pool: ArqRedis | None = None

    try:
        pool = await _pool_factory()

        # 4. Enqueue the ARQ task
        enqueued_job = await pool.enqueue_job(
            "run_document_ingestion",
            str(version_id),
            correlation_id,
            _job_id=arq_job_id_value,
            _queue_name=settings.arq_queue_name,
        )

        # 5. Handle duplicate (ARQ returns None when _job_id already exists)
        if enqueued_job is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "error": "ingestion_job_already_active",
                    "message": "An ingestion job is already active for this document version",
                },
            )

    except HTTPException:
        # Re-raise application-level errors without swallowing
        raise
    except Exception:
        # Map any pool creation or enqueue exception to HTTP 503.
        # No Redis URL, password, or exception details in the response.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "ingestion_enqueue_failed",
                "message": "The ingestion job could not be enqueued. Please retry.",
            },
        ) from None
    finally:
        # 6. Close owned pool in finally — never leaks on any exit path.
        if pool is not None:
            await pool.close()

    # 7. Return 202 response
    return IngestionEnqueueResponse(
        job_id=arq_job_id_value,
        document_id=str(document_id),
        document_version_id=str(version_id),
        correlation_id=correlation_id,
        status="pending",
    )


@router.post(
    "/documents/{document_id}/versions/{version_id}/ingest",
    response_model=IngestionEnqueueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_document_ingestion(
    document_id: UUID,
    version_id: UUID,
    _current_user: AuthenticatedUser = Depends(require_role({"AI_ADMINISTRATOR"})),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> IngestionEnqueueResponse:
    """Enqueue a document ingestion background job.

    Validates that the document version exists and belongs to the specified
    document, then enqueues an ARQ job to process the document for RAG
    ingestion (chunking, embedding, and vector storage).

    The ARQ job uses a deterministic _job_id derived from the version_id,
    preventing duplicate ingestion attempts for the same version.

    Args:
        document_id: Document UUID (path parameter).
        version_id: DocumentVersion UUID (path parameter).
        _current_user: Authenticated user with AI_ADMINISTRATOR role.
        session: Async database session.

    Returns:
        IngestionEnqueueResponse with job_id and correlation_id.

    Raises:
        HTTPException(422): Malformed UUID in path parameters.
        HTTPException(404): DocumentVersion not found.
        HTTPException(409): Ingestion job already active for this version.
        HTTPException(503): Redis/ARQ enqueue failure.
    """
    # Get correlation ID from middleware context; generate if not bound
    correlation_id = get_correlation_id()
    if correlation_id is None:
        correlation_id = generate_correlation_id()

    return await _get_version_and_enqueue(
        document_id=document_id,
        version_id=version_id,
        session=session,
        correlation_id=correlation_id,
    )
