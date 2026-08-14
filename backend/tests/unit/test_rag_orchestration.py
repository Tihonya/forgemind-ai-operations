"""Unit tests for WP-REC-05 RAG orchestration (deterministic, no database).

Covers the server-derived query construction, citation allow-list building,
prompt-context serialization, and citation-integrity validation (M3/DEC-045,
§F/§G). Fabricated-source rejection and legitimate zero-result behavior are
pure functions of the retrieval results, so they are exercised here without a
live database or provider.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from app.ai.rag.orchestration import (
    MAX_CHUNK_TEXT_LENGTH,
    WORKFLOW_TOP_K,
    DuplicateCitationError,
    FabricatedCitationError,
    build_citation_allow_list,
    build_per_risk_citation_allow_lists,
    build_retrieval_query_text,
    serialize_retrieval_context,
    validate_per_risk_sources,
    validate_sources_against_allow_list,
)
from app.ai.rag.retriever import TOP_K_DEFAULT, RetrievalResult
from app.schemas.recommendation import Source


def _result(
    *,
    document_id: UUID | None = None,
    version_number: str = "1.0",
    chunk_id: UUID | None = None,
    chunk_text: str = "chunk text",
    chunk_index: int = 0,
    similarity: float = 0.9,
) -> RetrievalResult:
    return RetrievalResult(
        document_id=document_id or uuid4(),
        version_id=uuid4(),
        version_number=version_number,
        chunk_id=chunk_id or uuid4(),
        chunk_index=chunk_index,
        chunk_text=chunk_text,
        metadata=None,
        similarity=similarity,
    )


class TestRetrievalQueryConstruction:
    """§F: deterministic server-derived query construction."""

    def test_query_uses_component_code_and_name(self) -> None:
        risk = {"component_code": "CTRL-X4", "component_name": "Controller X4"}
        assert build_retrieval_query_text(risk) == (
            "alternative component for CTRL-X4 Controller X4"
        )

    def test_query_uses_component_code_only(self) -> None:
        risk = {"component_code": "CTRL-X4", "component_name": ""}
        assert build_retrieval_query_text(risk) == (
            "alternative component for CTRL-X4"
        )

    def test_query_uses_component_name_only(self) -> None:
        risk = {"component_code": "", "component_name": "Controller X4"}
        assert build_retrieval_query_text(risk) == (
            "alternative component for Controller X4"
        )

    def test_query_falls_back_to_generic(self) -> None:
        risk: dict[str, str] = {"component_code": "", "component_name": ""}
        assert build_retrieval_query_text(risk) == "alternative component"


class TestCitationAllowList:
    """§G / M3: allow-list identity is (str(document_id), version_number, chunk_id)."""

    def test_allow_list_identity_uses_uuid_string_and_version_number(self) -> None:
        doc_id = uuid4()
        chunk_id = uuid4()
        result = _result(
            document_id=doc_id,
            version_number="2.1",
            chunk_id=chunk_id,
        )
        allow_list = build_citation_allow_list([result])
        assert allow_list == frozenset({(str(doc_id), "2.1", chunk_id)})

    def test_allow_list_is_empty_for_zero_results(self) -> None:
        assert build_citation_allow_list([]) == frozenset()

    def test_allow_list_deduplicates_identical_chunks(self) -> None:
        doc_id = uuid4()
        chunk_id = uuid4()
        result = _result(document_id=doc_id, chunk_id=chunk_id)
        allow_list = build_citation_allow_list([result, result])
        assert len(allow_list) == 1


class TestPromptContextSerialization:
    """§F: bounded JSON prompt context carrying citation identities."""

    def test_context_carries_citation_identity_fields(self) -> None:
        doc_id = uuid4()
        chunk_id = uuid4()
        result = _result(
            document_id=doc_id,
            version_number="1.0",
            chunk_id=chunk_id,
            chunk_text="accessible text",
            chunk_index=2,
        )
        context = json.loads(serialize_retrieval_context([result]))
        assert context == [
            {
                "document_id": str(doc_id),
                "version": "1.0",
                "chunk_id": str(chunk_id),
                "chunk_index": 2,
                "chunk_text": "accessible text",
            }
        ]

    def test_context_truncates_chunk_text(self) -> None:
        long_text = "x" * (MAX_CHUNK_TEXT_LENGTH + 500)
        result = _result(chunk_text=long_text)
        context = json.loads(serialize_retrieval_context([result]))
        assert len(context[0]["chunk_text"]) == MAX_CHUNK_TEXT_LENGTH

    def test_empty_context_is_json_empty_array(self) -> None:
        assert serialize_retrieval_context([]) == "[]"


class TestCitationValidation:
    """§G: fabricated or unauthorized citations are rejected."""

    def test_allow_listed_source_accepted(self) -> None:
        doc_id = uuid4()
        chunk_id = uuid4()
        result = _result(
            document_id=doc_id, version_number="1.0", chunk_id=chunk_id
        )
        allow_list = build_citation_allow_list([result])
        source = Source(
            document_id=str(doc_id), version="1.0", chunk_id=chunk_id
        )
        validate_sources_against_allow_list([source], allow_list)

    def test_fabricated_document_id_rejected(self) -> None:
        allow_list = build_citation_allow_list([_result()])
        source = Source(
            document_id=str(uuid4()), version="1.0", chunk_id=uuid4()
        )
        with pytest.raises(FabricatedCitationError):
            validate_sources_against_allow_list([source], allow_list)

    def test_fabricated_chunk_id_rejected(self) -> None:
        result = _result()
        allow_list = build_citation_allow_list([result])
        source = Source(
            document_id=str(result.document_id),
            version="1.0",
            chunk_id=uuid4(),
        )
        with pytest.raises(FabricatedCitationError):
            validate_sources_against_allow_list([source], allow_list)

    def test_wrong_version_number_rejected(self) -> None:
        result = _result(version_number="1.0")
        allow_list = build_citation_allow_list([result])
        source = Source(
            document_id=str(result.document_id),
            version="99.0",
            chunk_id=result.chunk_id,
        )
        with pytest.raises(FabricatedCitationError):
            validate_sources_against_allow_list([source], allow_list)

    def test_empty_allow_list_rejects_any_source(self) -> None:
        source = Source(
            document_id=str(uuid4()), version="1.0", chunk_id=uuid4()
        )
        with pytest.raises(FabricatedCitationError):
            validate_sources_against_allow_list([source], frozenset())

    def test_empty_sources_accepted_for_zero_results(self) -> None:
        # Legitimate zero-result: empty allow-list, empty sources → no error.
        validate_sources_against_allow_list([], frozenset())


class TestTopKBound:
    """Workflow retrieval top_k is bounded by the retriever default."""

    def test_workflow_top_k_matches_retriever_default(self) -> None:
        assert WORKFLOW_TOP_K == TOP_K_DEFAULT == 10


class TestPerRiskCitationAllowLists:
    """§7: per-risk allow-lists preserve authoritative retrieval provenance."""

    def test_per_risk_allow_lists_from_per_risk_results(self) -> None:
        doc_a = uuid4()
        doc_b = uuid4()
        chunk_a = uuid4()
        chunk_b = uuid4()
        results = {
            "RISK-001": [
                _result(document_id=doc_a, version_number="1.0", chunk_id=chunk_a)
            ],
            "RISK-002": [
                _result(document_id=doc_b, version_number="2.0", chunk_id=chunk_b)
            ],
        }
        lists = build_per_risk_citation_allow_lists(results)
        assert lists["RISK-001"] == frozenset({(str(doc_a), "1.0", chunk_a)})
        assert lists["RISK-002"] == frozenset({(str(doc_b), "2.0", chunk_b)})

    def test_per_risk_allow_lists_empty(self) -> None:
        assert build_per_risk_citation_allow_lists({}) == {}

    def test_same_chunk_retrieved_for_multiple_risks_is_in_both(self) -> None:
        doc_id = uuid4()
        chunk_id = uuid4()
        result = _result(document_id=doc_id, chunk_id=chunk_id)
        results = {
            "RISK-001": [result],
            "RISK-002": [result],
        }
        lists = build_per_risk_citation_allow_lists(results)
        assert lists["RISK-001"] == frozenset({(str(doc_id), "1.0", chunk_id)})
        assert lists["RISK-002"] == frozenset({(str(doc_id), "1.0", chunk_id)})


class TestPerRiskCitationValidation:
    """§7: every RiskItem.sources validates only against its own allow-list."""

    def _lists(self) -> dict[str, frozenset[tuple[str, str, UUID]]]:
        doc_a = uuid4()
        chunk_a = uuid4()
        doc_b = uuid4()
        chunk_b = uuid4()
        self.doc_a = doc_a
        self.chunk_a = chunk_a
        self.doc_b = doc_b
        self.chunk_b = chunk_b
        return {
            "RISK-001": frozenset({(str(doc_a), "1.0", chunk_a)}),
            "RISK-002": frozenset({(str(doc_b), "2.0", chunk_b)}),
        }

    def test_correct_source_on_correct_risk(self) -> None:
        lists = self._lists()
        source = Source(
            document_id=str(self.doc_a), version="1.0", chunk_id=self.chunk_a
        )
        validate_per_risk_sources(
            [source], risk_id="RISK-001", allow_lists_by_risk=lists
        )

    def test_source_from_risk_a_attached_to_risk_b(self) -> None:
        lists = self._lists()
        source = Source(
            document_id=str(self.doc_a), version="1.0", chunk_id=self.chunk_a
        )
        with pytest.raises(FabricatedCitationError):
            validate_per_risk_sources(
                [source], risk_id="RISK-002", allow_lists_by_risk=lists
            )

    def test_fabricated_tuple_rejected(self) -> None:
        source = Source(
            document_id=str(uuid4()), version="1.0", chunk_id=uuid4()
        )
        with pytest.raises(FabricatedCitationError):
            validate_per_risk_sources(
                [source], risk_id="RISK-001", allow_lists_by_risk={}
            )

    def test_duplicate_source_rejected(self) -> None:
        lists = self._lists()
        source = Source(
            document_id=str(self.doc_a), version="1.0", chunk_id=self.chunk_a
        )
        with pytest.raises(DuplicateCitationError):
            validate_per_risk_sources(
                [source, source], risk_id="RISK-001", allow_lists_by_risk=lists
            )

    def test_empty_retrieval_requires_empty_sources(self) -> None:
        lists: dict[str, frozenset[tuple[str, str, UUID]]] = {
            "RISK-001": frozenset()
        }
        # Zero-result → empty sources is valid (ungrounded).
        validate_per_risk_sources(
            [], risk_id="RISK-001", allow_lists_by_risk=lists
        )
        # Any non-empty source on a zero-result risk is rejected.
        source = Source(
            document_id=str(uuid4()), version="1.0", chunk_id=uuid4()
        )
        with pytest.raises(FabricatedCitationError):
            validate_per_risk_sources(
                [source], risk_id="RISK-001", allow_lists_by_risk=lists
            )

    def test_multiple_risks_with_distinct_allow_lists(self) -> None:
        lists = self._lists()
        sa = Source(
            document_id=str(self.doc_a), version="1.0", chunk_id=self.chunk_a
        )
        sb = Source(
            document_id=str(self.doc_b), version="2.0", chunk_id=self.chunk_b
        )
        validate_per_risk_sources(
            [sa], risk_id="RISK-001", allow_lists_by_risk=lists
        )
        validate_per_risk_sources(
            [sb], risk_id="RISK-002", allow_lists_by_risk=lists
        )
        with pytest.raises(FabricatedCitationError):
            validate_per_risk_sources(
                [sa], risk_id="RISK-002", allow_lists_by_risk=lists
            )
        with pytest.raises(FabricatedCitationError):
            validate_per_risk_sources(
                [sb], risk_id="RISK-001", allow_lists_by_risk=lists
            )

    def test_unknown_risk_id_has_empty_allow_list(self) -> None:
        source = Source(
            document_id=str(uuid4()), version="1.0", chunk_id=uuid4()
        )
        with pytest.raises(FabricatedCitationError):
            validate_per_risk_sources(
                [source], risk_id="UNKNOWN", allow_lists_by_risk={}
            )
        validate_per_risk_sources(
            [], risk_id="UNKNOWN", allow_lists_by_risk={}
        )
