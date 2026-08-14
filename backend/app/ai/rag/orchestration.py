"""Retrieval orchestration for the controlled workflow (WP-REC-05).

Deterministic, server-derived retrieval orchestration inserted between
deterministic risk calculation and prompt construction inside the vertical
workflow. The pure helpers in this module (query construction, citation
allow-list building, prompt-context serialization, and citation validation)
have no database or provider side effects; the actual retrieval execution
uses the existing :class:`~app.ai.rag.retriever.RetrievalService` and
``EmbeddingProvider``.

Citation identity contract (M3, DEC-045):

- ``Source.document_id`` ← ``str(Document.id)`` (repository document UUID);
- ``Source.version``      ← ``DocumentVersion.version_number``;
- ``Source.chunk_id``     ← ``KnowledgeChunk.id`` (UUID).

The citation allow-list is built deterministically from retrieval results
and is the only source of truth for what may appear in persisted
``sources``. Fabricated or unauthorized citations are rejected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.ai.rag.citations import build_citation
from app.ai.rag.retriever import TOP_K_DEFAULT, RetrievalResult
from app.schemas.recommendation import Source

# Per-chunk text truncation cap. chunk_size defaults to 1000 chars (§F);
# no unbounded chunk text may enter the prompt.
MAX_CHUNK_TEXT_LENGTH: int = 1000

# Workflow retrieval top_k. Bounded by the retriever (1..100); default 10.
WORKFLOW_TOP_K: int = TOP_K_DEFAULT


class FabricatedCitationError(Exception):
    """Raised when a persisted Source is not in the citation allow-list.

    Per the M2 failure-ownership contract, this maps to a validation
    failure (``FAILED_VALIDATION``) — never a retrieval execution failure
    (``FAILED_RETRIEVAL``).
    """


class DuplicateCitationError(FabricatedCitationError):
    """Raised when a single risk item cites the same source tuple more than once.

    Per §7, duplicate sources are rejected deterministically (not silently
    normalized). Like :class:`FabricatedCitationError`, this is a
    citation-integrity failure and maps to ``FAILED_VALIDATION``.
    """


@dataclass(frozen=True)
class RetrievalContext:
    """Bounded retrieval results and the citation allow-list for a run.

    Attributes:
        results: Immutable tuple of retrieval results (deduplicated,
            bounded by ``top_k``).
        allow_list: Immutable citation allow-list keyed by the wire
            ``Source`` identity ``(document_id_str, version_number,
            chunk_id)``.
    """

    results: tuple[RetrievalResult, ...]
    allow_list: frozenset[tuple[str, str, UUID]]


def build_retrieval_query_text(risk: dict[str, Any]) -> str:
    """Build a deterministic, server-derived retrieval query for one risk.

    The query is derived only from deterministic risk fields
    (DEC-004/039); it is never client-supplied. Format follows §F:
    ``"alternative component for {component_code} {component_name}"``.

    Args:
        risk: A single risk dict carrying ``component_code`` and
            ``component_name``.

    Returns:
        A non-empty deterministic query string.
    """
    component_code = str(risk.get("component_code") or "").strip()
    component_name = str(risk.get("component_name") or "").strip()
    parts = [p for p in (component_code, component_name) if p]
    if parts:
        return "alternative component for " + " ".join(parts)
    return "alternative component"


def build_citation_allow_list(
    results: list[RetrievalResult] | tuple[RetrievalResult, ...],
) -> frozenset[tuple[str, str, UUID]]:
    """Build the authoritative citation allow-list from retrieval results.

    Each identity is the wire ``Source`` tuple
    ``(str(document_id), version_number, chunk_id)`` per M3. Citation
    construction goes through :func:`~app.ai.rag.citations.build_citation`
    so the allow-list identity is exactly the retrieval citation identity.

    Args:
        results: Retrieval results for the run.

    Returns:
        An immutable allow-list of citation identity tuples.
    """
    return frozenset(
        (
            str(citation.document_id),
            citation.version_number,
            citation.chunk_id,
        )
        for citation in (build_citation(result) for result in results)
    )


def serialize_retrieval_context(
    results: list[RetrievalResult] | tuple[RetrievalResult, ...],
) -> str:
    """Serialize retrieved chunks into a bounded JSON prompt context.

    Each entry carries ``document_id`` (document-UUID string), ``version``
    (version_number), ``chunk_id``, ``chunk_index``, and ``chunk_text``
    truncated to :data:`MAX_CHUNK_TEXT_LENGTH`. The result is a JSON array
    string (``"[]"`` when empty).

    Args:
        results: Retrieval results for the run.

    Returns:
        A JSON array string of bounded citation-context entries.
    """
    entries = [
        {
            "document_id": str(result.document_id),
            "version": result.version_number,
            "chunk_id": str(result.chunk_id),
            "chunk_index": result.chunk_index,
            "chunk_text": result.chunk_text[:MAX_CHUNK_TEXT_LENGTH],
        }
        for result in results
    ]
    return json.dumps(entries, ensure_ascii=True)


def validate_sources_against_allow_list(
    sources: list[Source],
    allow_list: frozenset[tuple[str, str, UUID]],
) -> None:
    """Validate persisted ``sources`` against the citation allow-list.

    Every ``Source`` must match an allow-listed identity
    ``(str(document_id), version_number, chunk_id)``. A mismatch is a
    fabricated or unauthorized citation.

    Args:
        sources: List of wire ``Source`` objects from a validated
            recommendation risk item.
        allow_list: The run's authoritative citation allow-list.

    Raises:
        FabricatedCitationError: If any source is not allow-listed.
    """
    for source in sources:
        identity = (
            source.document_id,
            source.version,
            source.chunk_id,
        )
        if identity not in allow_list:
            raise FabricatedCitationError(
                "Persisted source is not in the citation allow-list"
            )


def build_per_risk_citation_allow_lists(
    results_by_risk: dict[str, list[RetrievalResult]],
) -> dict[str, frozenset[tuple[str, str, UUID]]]:
    """Build per-risk citation allow-lists from per-risk retrieval results.

    Each risk keeps its own authoritative allow-list so that a citation
    retrieved for one risk cannot be attached to a different risk (§7).
    The allow-list identity remains the wire ``Source`` tuple
    ``(str(document_id), version_number, chunk_id)`` per M3.

    Args:
        results_by_risk: Mapping of ``risk_id`` to that risk's retrieval
            results.

    Returns:
        Mapping of ``risk_id`` to its immutable per-risk allow-list.
    """
    return {
        risk_id: build_citation_allow_list(results)
        for risk_id, results in results_by_risk.items()
    }


def validate_per_risk_sources(
    sources: list[Source],
    *,
    risk_id: str,
    allow_lists_by_risk: dict[str, frozenset[tuple[str, str, UUID]]],
) -> None:
    """Validate one risk item's ``sources`` against its own allow-list.

    Implements the per-risk citation-integrity contract (§7):

    - membership is checked only against the allow-list for ``risk_id``;
    - a tuple retrieved for another risk is invalid (cross-risk);
    - duplicate source tuples within one risk item are rejected;
    - a zero-result risk has an empty allow-list, so ``sources == []``
      is required.

    Args:
        sources: The risk item's wire ``Source`` objects.
        risk_id: The risk item's ``risk_id``.
        allow_lists_by_risk: Mapping of ``risk_id`` → per-risk allow-list.

    Raises:
        DuplicateCitationError: If a source tuple repeats within ``sources``.
        FabricatedCitationError: If a source is not in ``risk_id``'s
            allow-list (fabricated or cross-risk).
    """
    allow_list = allow_lists_by_risk.get(risk_id, frozenset())
    seen: set[tuple[str, str, UUID]] = set()
    for source in sources:
        identity = (
            source.document_id,
            source.version,
            source.chunk_id,
        )
        if identity in seen:
            raise DuplicateCitationError(
                "Duplicate source citation within a risk item"
            )
        seen.add(identity)
        if identity not in allow_list:
            raise FabricatedCitationError(
                "Persisted source is not in the risk's citation allow-list"
            )
