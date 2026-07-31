"""Retrieval API router for WP-4.4C.

Endpoint:
- POST /api/v1/retrieval

Authorization:
- Any authenticated user (get_current_user dependency).
- Role IDs are derived server-side from the user's role codes.

Flow:
1. Authenticate user and extract role codes.
2. Query roles table to resolve role codes -> role UUIDs.
3. Call RetrievalService.retrieve() with role UUIDs.
4. Build Citation for each result.
5. Return response with results and citations.

Error handling:
- 400: Invalid embedding or top_k.
- 401: Unauthenticated request.
- 500: Database error.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.rag.citations import build_citation
from app.ai.rag.retriever import RetrievalService, RetrievalValidationError
from app.database import get_async_session
from app.dependencies import get_current_user
from app.models.user import Role
from app.schemas.retrieval import (
    CitationResponse,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResultResponse,
)
from app.services.auth_service import AuthenticatedUser

router = APIRouter(tags=["Retrieval"])


async def _resolve_role_ids(
    session: AsyncSession,
    role_codes: frozenset[str],
) -> set:
    """Resolve role codes to role UUIDs.

    Args:
        session: Async database session.
        role_codes: Set of role codes from the authenticated user.

    Returns:
        Set of role UUIDs.

    Raises:
        HTTPException(500): If no roles found for user (data integrity issue).
    """
    if not role_codes:
        # User has no roles — cannot retrieve anything
        return set()

    # Query roles table for UUIDs matching the user's role codes
    stmt = select(Role.id).where(Role.code.in_(role_codes))
    result = await session.execute(stmt)
    role_ids = {row[0] for row in result.fetchall()}

    return role_ids


@router.post(
    "/retrieval",
    response_model=RetrievalResponse,
    status_code=status.HTTP_200_OK,
)
async def retrieve_documents(
    request: RetrievalRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),  # noqa: B008
    session: AsyncSession = Depends(get_async_session),  # noqa: B008
) -> RetrievalResponse:
    """Execute vector similarity search over knowledge chunks.

    Retrieves chunks from documents the user is authorized to access.
    Access filtering is enforced inside the PostgreSQL query via
    document_permissions join.

    Args:
        request: Retrieval request with query embedding and top_k.
        current_user: Authenticated user (dependency-injected).
        session: Async database session (dependency-injected).

    Returns:
        RetrievalResponse with results, citations, and metadata.

    Raises:
        HTTPException(400): Invalid embedding or top_k.
        HTTPException(401): Missing or invalid authentication.
        HTTPException(500): Database or service error.
    """
    # 1. Resolve role codes to role UUIDs (server-side, not from request)
    role_ids = await _resolve_role_ids(session, current_user.roles)

    # If user has no roles, return empty result (no permissions)
    if not role_ids:
        return RetrievalResponse(
            results=[],
            total_results=0,
            query_embedding_dimension=len(request.query_embedding),
        )

    # 2. Execute retrieval with role-based access filtering
    service = RetrievalService()

    try:
        retrieval_results = await service.retrieve(
            session=session,
            query_embedding=request.query_embedding,
            allowed_role_ids=role_ids,
            top_k=request.top_k,
        )
    except RetrievalValidationError as exc:
        # Map validation errors to 400
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_retrieval_request",
                "message": str(exc),
            },
        ) from exc
    except Exception as exc:
        # Database or service error -> 500
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "retrieval_failed",
                "message": "Retrieval failed due to an internal error.",
            },
        ) from exc

    # 3. Build response with citations
    response_results = []
    for result in retrieval_results:
        citation = build_citation(result)
        citation_response = CitationResponse(
            document_id=citation.document_id,
            version_id=citation.version_id,
            chunk_id=citation.chunk_id,
            chunk_index=citation.chunk_index,
            similarity=citation.similarity,
        )
        response_results.append(
            RetrievalResultResponse(
                document_id=result.document_id,
                version_id=result.version_id,
                chunk_id=result.chunk_id,
                chunk_index=result.chunk_index,
                chunk_text=result.chunk_text,
                similarity=result.similarity,
                metadata=result.metadata,
                citation=citation_response,
            )
        )

    return RetrievalResponse(
        results=response_results,
        total_results=len(response_results),
        query_embedding_dimension=len(request.query_embedding),
    )
