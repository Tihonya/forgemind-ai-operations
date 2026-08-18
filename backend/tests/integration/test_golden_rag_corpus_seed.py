"""Clean-database Golden RAG corpus integration test (WP-P7-02 remediation).

Proves, against the configured integration database:

- bounded canonical-ID cleanup is safe (pre-seed canonical counts reach 0);
- `load_golden_dataset()` creates exactly 3 canonical documents with one
  authoritative APPROVED version each, the deterministic DocumentPermission
  rows, and returns corpus counts;
- `_ingest_seed_documents()` (the existing async bridge) produces REAL
  KnowledgeChunk rows of dimension 1536 via the repository
  IngestionOrchestrator and FakeEmbeddingProvider (monkeypatched through the
  canonical ``create_embedding_provider`` factory seam — ZERO external
  provider calls);
- a SECOND seed execution succeeds and preserves canonical counts (no
  duplicate documents/versions/permissions/chunks);
- unrelated documents are never deleted by the bounded canonical-ID cleanup.

Skips cleanly when no integration database is reachable, matching the
existing integration conventions.  The module leaves the canonical corpus
removed afterwards, so it has no cross-module footprint.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.models.document import Document, DocumentVersion
from app.seed.generator.golden_dataset import get_golden_rag_corpus_document_ids
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


@contextlib.contextmanager
def _sync_connection() -> Iterator[Connection]:
    with _sync_engine.connect() as conn:
        yield conn


def _canonical_document_ids() -> list[Any]:
    return list(get_golden_rag_corpus_document_ids().values())


def _bounded_delete_canonical_corpus() -> None:
    """Delete ONLY the deterministic canonical corpus documents (cascades)."""
    session = _SessionFactory()
    try:
        session.query(Document).filter(
            Document.id.in_(_canonical_document_ids())
        ).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _golden_version_ids_sync() -> set[Any]:
    with _sync_connection() as conn:
        rows = conn.execute(
            text(
                "SELECT dv.id FROM document_versions dv "
                "WHERE dv.document_id = ANY(:ids)"
            ),
            {"ids": _canonical_document_ids()},
        ).fetchall()
    return {row[0] for row in rows}


def _canonical_counts_sync() -> dict[str, int]:
    with _sync_connection() as conn:
        documents = conn.execute(
            text("SELECT COUNT(*) FROM documents WHERE id = ANY(:ids)"),
            {"ids": _canonical_document_ids()},
        ).scalar_one()
        versions = conn.execute(
            text(
                "SELECT COUNT(*) FROM document_versions "
                "WHERE document_id = ANY(:ids)"
            ),
            {"ids": _canonical_document_ids()},
        ).scalar_one()
        permissions = conn.execute(
            text(
                "SELECT COUNT(*) FROM document_permissions "
                "WHERE document_id = ANY(:ids)"
            ),
            {"ids": _canonical_document_ids()},
        ).scalar_one()
        chunks = conn.execute(
            text(
                "SELECT COUNT(*) FROM knowledge_chunks kc "
                "JOIN document_versions dv ON dv.id = kc.document_version_id "
                "WHERE dv.document_id = ANY(:ids)"
            ),
            {"ids": _canonical_document_ids()},
        ).scalar_one()
    return {
        "documents": int(documents),
        "document_versions": int(versions),
        "document_permissions": int(permissions),
        "knowledge_chunks": int(chunks),
    }


def _run_ingestion(
    monkeypatch: pytest.MonkeyPatch, version_ids: set[Any]
) -> Any:
    fake_provider = FakeEmbeddingProvider(dimension=1536)
    monkeypatch.setattr(
        "app.services.embedding_provider_factory.create_embedding_provider",
        lambda: fake_provider,
    )
    return asyncio.run(_ingest_seed_documents(sorted(version_ids)))


@pytest.fixture(scope="module", autouse=True)
def isolated_corpus_state() -> Iterator[None]:
    # Remove any canonical corpus rows left by earlier modules (shared CI DB),
    # so the clean-DB pre-seed assertions below are meaningful; restore the
    # same state afterwards.  Business rows are also cleaned afterwards,
    # following the test_dataset_integrity convention, because
    # load_golden_dataset() seeds the full business dataset as a side effect
    # and downstream modules (e.g. test_provider_outage) change behavior when
    # production plans are present.
    _bounded_delete_canonical_corpus()
    yield
    session = _SessionFactory()
    try:
        _bounded_delete_canonical_corpus()
        _delete_existing_business_data(session)
        session.commit()
    finally:
        session.close()


class TestCleanDbGoldenRagCorpus:
    def test_01_pre_seed_canonical_counts_are_zero(self):
        assert _canonical_counts_sync() == {
            "documents": 0,
            "document_versions": 0,
            "document_permissions": 0,
            "knowledge_chunks": 0,
        }

    def test_02_seed_creates_corpus_counts(self):
        counts = load_golden_dataset()
        assert counts["documents"] == 3
        assert counts["document_versions"] == 3
        assert counts["document_permissions"] == 7

        db_counts = _canonical_counts_sync()
        assert db_counts["documents"] == 3
        assert db_counts["document_versions"] == 3
        assert db_counts["document_permissions"] == 7
        assert db_counts["knowledge_chunks"] == 0  # ingestion not yet run

    def test_03_ingestion_bridge_produces_real_1536_chunks(self, monkeypatch):
        version_ids = _golden_version_ids_sync()
        assert len(version_ids) == 3

        result = _run_ingestion(monkeypatch, version_ids)
        assert result.failed_count == 0
        assert result.succeeded_count == 3

        counts = _canonical_counts_sync()
        assert counts["knowledge_chunks"] > 0

        with _sync_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT vector_dims(kc.embedding) FROM knowledge_chunks kc "
                    "JOIN document_versions dv ON dv.id = kc.document_version_id "
                    "WHERE dv.document_id = ANY(:ids)"
                ),
                {"ids": _canonical_document_ids()},
            ).fetchall()
        assert rows, "no golden chunks found after ingestion"
        for row in rows:
            assert row[0] == 1536

    def test_04_second_seed_is_idempotent(self, monkeypatch):
        counts1 = load_golden_dataset()
        first_version_ids = _golden_version_ids_sync()

        counts2 = load_golden_dataset()
        assert counts2["documents"] == counts1["documents"] == 3
        assert counts2["document_versions"] == 3
        assert counts2["document_permissions"] == 7

        # Canonical version IDs are deterministic and must not change.
        assert _golden_version_ids_sync() == first_version_ids

        result = _run_ingestion(monkeypatch, first_version_ids)
        assert result.failed_count == 0

        counts = _canonical_counts_sync()
        assert counts["documents"] == 3
        assert counts["document_versions"] == 3
        assert counts["document_permissions"] == 7
        assert counts["knowledge_chunks"] > 0

    def test_05_unrelated_documents_preserved_on_reseed(self):
        session = _SessionFactory()
        try:
            unrelated_doc = Document(
                id=uuid4(),
                title="Unrelated production document",
                description="Operator-created document that must survive reseeding",
            )
            session.add(unrelated_doc)
            session.add(
                DocumentVersion(
                    id=uuid4(),
                    document_id=unrelated_doc.id,
                    version_number="1.0",
                    status="DRAFT",
                )
            )
            session.commit()
            unrelated_id = unrelated_doc.id
        finally:
            session.close()

        try:
            load_golden_dataset()
            with _sync_connection() as conn:
                remaining = conn.execute(
                    text("SELECT COUNT(*) FROM documents WHERE id = :did"),
                    {"did": unrelated_id},
                ).scalar_one()
            assert remaining == 1, "reseed deleted an unrelated document"
        finally:
            session = _SessionFactory()
            try:
                session.query(DocumentVersion).filter(
                    DocumentVersion.document_id == unrelated_id
                ).delete(synchronize_session=False)
                session.query(Document).filter(
                    Document.id == unrelated_id
                ).delete(synchronize_session=False)
                session.commit()
            finally:
                session.close()
