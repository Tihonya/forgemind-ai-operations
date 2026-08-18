"""Seeded Golden RAG corpus runtime retrieval + access-control tests
(WP-P7-02 remediation).

Proves over the seeded deterministic corpus:

- the FULL production seed path (migrated DB -> business+auth seed ->
  deterministic corpus -> ingestion bridge -> knowledge chunks) can run
  offline via the canonical factory seam with FakeEmbeddingProvider;
- the real `RetrievalService` returns citations whose source identity maps
  back to the canonical Golden document/version (document_id / version_id /
  version_number);
- a SENSOR-L9 + VALVE-V3 query semantically resolves through a source that
  names VALVE-V3 as the PROPOSED alternative pending engineering review;
- seeded DocumentPermission rows remain meaningful: an allowed role reaches
  its corpus document, a role without permission cannot retrieve it.

No external chat/provider call is made anywhere in this module.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.rag.retriever import RetrievalService
from app.models.document import Document
from app.seed.generator.auth_dataset import get_role_id_by_code
from app.seed.generator.golden_dataset import (
    GOLDEN_RAG_3_CONTENT,
    generate_golden_rag_corpus,
    get_golden_rag_corpus_document_ids,
)
from app.seed.generator.loader import (
    _delete_existing_business_data,
    _ingest_seed_documents,
    _SessionFactory,
    _sync_engine,
    load_golden_dataset,
)
from app.services.embedding_provider import FakeEmbeddingProvider

_INTEGRATION_DB_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get(
    "DATABASE_URL"
)

pytestmark = pytest.mark.skipif(
    not _INTEGRATION_DB_URL,
    reason="integration database not configured",
)


def _get_async_engine() -> AsyncEngine:
    assert _INTEGRATION_DB_URL
    url = _INTEGRATION_DB_URL
    if "+psycopg" in url:
        url = url.replace("+psycopg", "+asyncpg")
    return create_async_engine(url, echo=False, pool_pre_ping=True)


@pytest.fixture
async def async_session() -> AsyncIterator[AsyncSession]:
    engine = _get_async_engine()
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session
    await engine.dispose()


@contextlib.contextmanager
def _sync_connection() -> Iterator[Connection]:
    with _sync_engine.connect() as conn:
        yield conn


def _role_id_by_code(role_code: str) -> Any:
    return get_role_id_by_code(role_code)


@pytest.fixture(scope="module", autouse=True)
def seeded_golden_state() -> Iterator[None]:
    """Full production seed path offline: seed + ingest with fake embeddings.

    Patches the canonical factory seam directly (no pytest monkeypatch:
    module scope cannot consume function-scoped fixtures) and restores it
    in a finally block.
    """
    import app.services.embedding_provider_factory as factory_module
    from app.config import Settings
    from app.services.embedding_provider import EmbeddingProvider

    def _offline_factory(config: Settings | None = None) -> EmbeddingProvider:
        return FakeEmbeddingProvider(dimension=1536)

    original_factory = factory_module.create_embedding_provider
    factory_module.create_embedding_provider = _offline_factory
    try:
        load_golden_dataset()
        with _sync_connection() as conn:
            version_ids = conn.execute(
                text(
                    "SELECT dv.id FROM document_versions dv "
                    "WHERE dv.document_id = ANY(:ids)"
                ),
                {"ids": list(get_golden_rag_corpus_document_ids().values())},
            ).scalars().all()
        result = asyncio.run(_ingest_seed_documents(list(version_ids)))
        assert result.failed_count == 0
        assert result.succeeded_count == 3
        yield
    finally:
        factory_module.create_embedding_provider = original_factory
        # Bounded canonical cleanup (cascades versions/permissions/chunks),
        # plus business-data cleanup (test_dataset_integrity convention) so
        # downstream modules never inherit seeded production plans.
        session = _SessionFactory()
        try:
            session.query(Document).filter(
                Document.id.in_(list(get_golden_rag_corpus_document_ids().values()))
            ).delete(synchronize_session=False)
            _delete_existing_business_data(session)
            session.commit()
        finally:
            session.close()


class TestSeededRuntimeRetrievalAndCitations:
    async def test_sensor_l9_valve_v3_query_resolves_to_golden_source(
        self, async_session
    ):
        corpus = generate_golden_rag_corpus()
        g_rag_3_version = corpus["document_versions"][2]
        assert "SENSOR-L9" in GOLDEN_RAG_3_CONTENT

        query_provider = FakeEmbeddingProvider(dimension=1536)
        query_embedding = (
            await query_provider.embed_text(
                ["SENSOR-L9 shortage VALVE-V3 proposed alternative engineering review"]
            )
        )[0]

        allowed_roles = {_role_id_by_code("PRODUCTION_MANAGER")}
        service = RetrievalService()
        results = await service.retrieve(
            session=async_session,
            query_embedding=query_embedding,
            allowed_role_ids=allowed_roles,
            top_k=10,
        )

        assert results, "no retrieval results for a validly permitted query"

        canonical_doc_id = get_golden_rag_corpus_document_ids()["G-RAG-3"]
        surviving_text = " ".join(r.chunk_text for r in results).lower()
        assert "valve-v3" in surviving_text
        assert "proposed" in surviving_text
        assert "pending engineering review" in surviving_text

        # Semantic requirement: the retrieved source explains VALVE-V3 is
        # the PROPOSED alternative for SENSOR-L9, not an approved one.
        assert "sensor-l9" in surviving_text

        # Citation source identity must map to the canonical Golden
        # document/version.  With a shared account vocabulary every seeded
        # chunk is from the corpus, so the authoritative version id is the
        # canonical identity contract to prove.
        canonical_version_id = g_rag_3_version["id"]
        canonical_hit = next(
            (r for r in results if r.version_id == canonical_version_id), None
        )
        assert canonical_hit is not None, (
            "top results did not include the canonical Golden version"
        )
        assert canonical_hit.document_id == canonical_doc_id
        assert canonical_hit.version_number == "1.0"

    async def test_production_manager_can_retrieve_allowed_document(
        self, async_session
    ):
        provider = FakeEmbeddingProvider(dimension=1536)
        query_embedding = (
            await provider.embed_text(["CTRL-X4 production shortage mitigation"])
        )[0]
        service = RetrievalService()
        results = await service.retrieve(
            session=async_session,
            query_embedding=query_embedding,
            allowed_role_ids={_role_id_by_code("PRODUCTION_MANAGER")},
            top_k=10,
        )
        assert results
        assert "ctrl-x4" in " ".join(r.chunk_text for r in results).lower()

    async def test_procurement_specialist_can_retrieve_procurement_document(
        self, async_session
    ):
        provider = FakeEmbeddingProvider(dimension=1536)
        query_embedding = (
            await provider.embed_text(["MOTOR-M2 late supply procurement status"])
        )[0]
        service = RetrievalService()
        results = await service.retrieve(
            session=async_session,
            query_embedding=query_embedding,
            allowed_role_ids={_role_id_by_code("PROCUREMENT_SPECIALIST")},
            top_k=10,
        )
        assert results
        assert "motor-m2" in " ".join(r.chunk_text for r in results).lower()

    async def test_unpermitted_role_cannot_retrieve_restricted_source(
        self, async_session
    ):
        """PROCUREMENT_SPECIALIST has no permission on the SENSOR-L9 document,
        and ENGINEER has none on the MOTOR-M2 document — the SQL-side
        permission filter must exclude those sources entirely.  The
        retriever returns the top-k permitted chunks for any valid query,
        so the assertion targets the restricted source identity, not a
        global empty result."""
        provider = FakeEmbeddingProvider(dimension=1536)
        restricted_for_procurement = (
            await provider.embed_text(
                ["SENSOR-L9 VALVE-V3 proposed alternative engineering review"]
            )
        )[0]
        service = RetrievalService()

        results = await service.retrieve(
            session=async_session,
            query_embedding=restricted_for_procurement,
            allowed_role_ids={_role_id_by_code("PROCUREMENT_SPECIALIST")},
            top_k=10,
        )
        assert results, "procurement specialist should still retrieve its own allowed document"
        g_rag_3_version_id = generate_golden_rag_corpus()["document_versions"][2]["id"]
        assert g_rag_3_version_id not in {
            r.version_id for r in results
        }, (
            "procurement specialist must not reach the G-RAG-3 document "
            "(permission mapping wrong on the production seed)"
        )

        # ENGINEER has no permission on the MOTOR-M2 (G-RAG-2) document.
        motor_query = (
            await provider.embed_text(["MOTOR-M2 late supply procurement status"])
        )[0]
        engineer_results = await service.retrieve(
            session=async_session,
            query_embedding=motor_query,
            allowed_role_ids={_role_id_by_code("ENGINEER")},
            top_k=10,
        )
        assert engineer_results, "engineer should still retrieve its own allowed document"
        g_rag_2_version_id = generate_golden_rag_corpus()["document_versions"][1]["id"]
        assert g_rag_2_version_id not in {
            r.version_id for r in engineer_results
        }, (
            "engineer must not reach the G-RAG-2 document "
            "(permission mapping wrong on the production seed)"
        )
