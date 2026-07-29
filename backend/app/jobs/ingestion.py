"""Document ingestion ARQ worker function.

Executes the document ingestion pipeline with retry semantics,
transaction isolation, and correlation context binding.

Retry policy:
- max_tries=3 means 3 total executions (initial + 2 retries)
- After attempt 1 failure: retry after 2 seconds
- After attempt 2 failure: retry after 4 seconds
- No jitter

Transaction contract:
- Fresh session per attempt (no state survives between retries)
- Commit only after complete successful ingestion
- Rollback on every exception before retry or re-raise
- IngestionOrchestrator flushes but does NOT commit (caller owns transaction)

Error classification:
- Retry: TransientEmbeddingProviderError, transient DB OperationalError
- No retry: PermanentEmbeddingProviderError, EmbeddingProviderConfigurationError,
  ValueError, IntegrityError, general Exception
"""

from __future__ import annotations

import uuid
from typing import Any, NoReturn

from arq import Retry
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.context import correlation_context
from app.core.correlation import validate_correlation_id
from app.core.logging import get_logger
from app.database import async_session_factory
from app.services.embedding_provider import (
    EmbeddingProviderConfigurationError,
    PermanentEmbeddingProviderError,
    TransientEmbeddingProviderError,
)
from app.services.embedding_provider_factory import create_embedding_provider
from app.services.ingestion import IngestionOrchestrator

logger = get_logger(__name__)

# Maximum retry attempts (3 total executions)
_MAX_TRIES = 3


async def run_document_ingestion(
    ctx: dict[str, Any],
    document_version_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    """ARQ worker function for document ingestion.

    Args:
        ctx: ARQ worker context dictionary. Contains 'job_try' (1-indexed).
        document_version_id: UUID string of the DocumentVersion to ingest.
        correlation_id: UUID v4 string for correlation context.

    Returns:
        JSON-serializable dict with document_version_id, status, chunks_count,
        embeddings_count.

    Raises:
        ValueError: If inputs are invalid or DocumentVersion not found.
        TransientEmbeddingProviderError: Transient provider error (retryable).
        PermanentEmbeddingProviderError: Permanent provider error (non-retryable).
        EmbeddingProviderConfigurationError: Configuration error (non-retryable).
        IntegrityError: Database constraint violation (non-retryable).
        OperationalError: Transient DB connection failure (retryable if < max_tries).
        Exception: Unclassified errors (non-retryable).
    """
    # Validate inputs BEFORE any database access
    _validate_inputs(document_version_id, correlation_id)

    job_try: int = ctx.get("job_try", 1)

    with correlation_context(correlation_id):
        version_uuid = uuid.UUID(document_version_id)

        logger.info(
            "ingestion_job_started",
            document_version_id=document_version_id,
            job_try=job_try,
        )

        # Fresh session per attempt (context manager ensures cleanup)
        async with async_session_factory() as session:
            try:
                # Construct provider through factory
                provider = create_embedding_provider()

                # Construct orchestrator with session and provider
                orchestrator = IngestionOrchestrator(session, provider)

                # Run ingestion (flushes but does NOT commit)
                result = await orchestrator.ingest_document_version(version_uuid)

                # Commit only after complete successful ingestion
                await session.commit()

                logger.info(
                    "ingestion_job_completed",
                    document_version_id=document_version_id,
                    job_try=job_try,
                    status="completed",
                    chunks_count=result.chunks_count,
                    embeddings_count=result.embeddings_count,
                )

                # Return JSON-serializable payload
                return {
                    "document_version_id": str(result.document_version_id),
                    "status": result.status,
                    "chunks_count": result.chunks_count,
                    "embeddings_count": result.embeddings_count,
                }

            except TransientEmbeddingProviderError as exc:
                # Transient provider error — retryable
                await _handle_retryable_error(
                    session, document_version_id, job_try, exc
                )

            except OperationalError as exc:
                # Transient DB connection failure — retryable
                await _handle_retryable_error(
                    session, document_version_id, job_try, exc
                )

            except (
                PermanentEmbeddingProviderError,
                EmbeddingProviderConfigurationError,
                ValueError,
                IntegrityError,
            ) as exc:
                # Non-retryable errors — rollback and re-raise
                await _handle_non_retryable_error(
                    session, document_version_id, job_try, exc
                )

            except Exception as exc:
                # Unclassified error — rollback and re-raise without retry
                await _handle_non_retryable_error(
                    session, document_version_id, job_try, exc
                )

    # Unreachable — all except handlers raise NoReturn
    raise RuntimeError("Unexpected control flow in run_document_ingestion")


def _validate_inputs(document_version_id: str, correlation_id: str) -> None:
    """Validate both inputs; raises ValueError on failure. No DB access."""
    try:
        uuid.UUID(document_version_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"Invalid document_version_id: {document_version_id!r} is not a valid UUID"
        ) from exc

    # validate_correlation_id raises InvalidCorrelationIdError (ValueError subclass)
    validate_correlation_id(correlation_id)


async def _handle_retryable_error(
    session: Any,
    document_version_id: str,
    job_try: int,
    exc: Exception,
) -> NoReturn:
    """Handle retryable errors: rollback, log, and raise Retry or re-raise."""
    # Rollback before retry
    await session.rollback()

    if job_try < _MAX_TRIES:
        # Calculate defer delay: 2s after attempt 1, 4s after attempt 2
        defer_seconds = [2, 4][job_try - 1]

        logger.warning(
            "ingestion_job_retrying",
            document_version_id=document_version_id,
            job_try=job_try,
            retry_delay=defer_seconds,
            error_type=type(exc).__name__,
        )

        raise Retry(defer=defer_seconds) from exc
    # Final attempt failed — log and re-raise
    logger.error(
        "ingestion_job_final_failure",
        document_version_id=document_version_id,
        job_try=job_try,
        error_type=type(exc).__name__,
    )
    raise


async def _handle_non_retryable_error(
    session: Any,
    document_version_id: str,
    job_try: int,
    exc: Exception,
) -> NoReturn:
    """Handle non-retryable errors: rollback, log, and re-raise."""
    # Rollback before re-raise
    await session.rollback()

    logger.error(
        "ingestion_job_failed",
        document_version_id=document_version_id,
        job_try=job_try,
        status="failed",
        error_type=type(exc).__name__,
    )

    raise
