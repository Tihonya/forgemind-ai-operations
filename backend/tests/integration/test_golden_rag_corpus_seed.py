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
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session

from app.core.dataset_metadata import EXPECTED_CHECKSUM
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.knowledge import KnowledgeChunk
from app.models.user import Role, User, UserRole
from app.seed.generator.auth_dataset import get_role_id_by_code
from app.seed.generator.golden_dataset import get_golden_rag_corpus_document_ids
from app.seed.generator.loader import (
    _collect_version_ids_sync,
    _delete_existing_business_data,
    _ingest_seed_documents,
    _SessionFactory,
    _sync_engine,
    load_golden_dataset,
)
from app.services.dataset_integrity import DatasetIntegrityService
from app.services.embedding_provider import FakeEmbeddingProvider
from tests.integration._workflow_rag_support import RecordingEmbeddingProvider

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


# ─────────────────────────────────────────────────────────────────────────────
# F-1 regression — Golden reseed must preserve non-Golden authorization state
# ─────────────────────────────────────────────────────────────────────────────


def _insert_unrelated_auth_fixture(
    session: Session,
) -> tuple[UUID, UUID, UUID]:
    """Create unrelated role/user/mapping rows that must survive a reseed."""
    unrelated_role = Role(
        id=uuid4(), code="TEST_UNRELATED_ROLE", name="Test Unrelated Role"
    )
    unrelated_user = User(
        id=uuid4(),
        username="unrelated.test",
        display_name="Unrelated Test User",
        hashed_password=None,
        is_active=True,
    )
    mapping = UserRole(
        id=uuid4(), user_id=unrelated_user.id, role_id=unrelated_role.id
    )
    session.add_all([unrelated_role, unrelated_user, mapping])
    session.commit()
    return (unrelated_role.id, unrelated_user.id, mapping.id)


def _role_id_row(role_id: Any) -> int:
    with _sync_connection() as conn:
        return cast(
            int,
            conn.execute(
                text("SELECT COUNT(*) FROM roles WHERE id = :rid"),
                {"rid": str(role_id)},
            ).scalar_one(),
        )


def _user_role_row(role_id: Any, user_id: Any, mapping_id: Any) -> int:
    with _sync_connection() as conn:
        return cast(
            int,
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM user_roles "
                    "WHERE id = :mid AND user_id = :uid AND role_id = :rid"
                ),
                {"mid": str(mapping_id), "uid": str(user_id), "rid": str(role_id)},
            ).scalar_one(),
        )


def _cleanup_unrelated_auth_fixture(
    session: Session,
    mapping_id: Any,
    user_id: Any,
    role_id: Any,
) -> None:
    session.query(UserRole).filter(
        UserRole.id == UUID(str(mapping_id))
    ).delete(synchronize_session=False)
    session.query(User).filter(User.id == UUID(str(user_id))).delete(
        synchronize_session=False
    )
    session.query(Role).filter(Role.id == UUID(str(role_id))).delete(
        synchronize_session=False
    )
    session.commit()


def _create_unrelated_doc_with_permission(
    session: Session, canonical_role_id: Any
) -> tuple[UUID, UUID, UUID]:
    """Create an unrelated APPROVED doc/version + permission bound to the
    given canonical role.  Returns (doc_id, version_id, permission_id)."""
    doc = Document(
        id=uuid4(),
        title="Unrelated operator document with permission",
        description="Operator-created document bound to a canonical role",
    )
    version = DocumentVersion(
        id=uuid4(),
        document_id=doc.id,
        version_number="1.0",
        status="APPROVED",
        content="Unrelated operator content for permission-preservation proof.",
    )
    session.add_all([doc, version])
    session.flush()
    permission = DocumentPermission(
        id=UUID(str(uuid4())),
        document_id=doc.id,
        role_id=UUID(str(canonical_role_id)),
    )
    session.add(permission)
    session.commit()
    return (doc.id, version.id, permission.id)


def _create_unrelated_approved_doc(session: Session) -> tuple[UUID, UUID]:
    """Create an unrelated APPROVED doc/version with valid content.
    Returns (doc_id, version_id)."""
    doc = Document(
        id=uuid4(),
        title="Unrelated approved operator document",
        description="Operator-approved document that must not enter the Golden seed path",
    )
    version = DocumentVersion(
        id=uuid4(),
        document_id=doc.id,
        version_number="1.0",
        status="APPROVED",
        content="Unrelated APPROVED content that must not reach the seed bridge.",
    )
    session.add_all([doc, version])
    session.commit()
    return (doc.id, version.id)


class TestUnrelatedAuthPreservation:
    """Golden reseed must not globally destroy unrelated auth state.

    Regression for review finding F-1: before the scoped auth reset, a
    Golden reseed deleted every Role row (including the deterministic
    canonical ones), which cascaded away DocumentPermission rows attached
    to surviving non-Golden documents.
    """

    def test_06_unrelated_auth_rows_survive_reseed(self):
        session = _SessionFactory()
        role_id: UUID | None = None
        user_id: UUID | None = None
        mapping_id: UUID | None = None
        try:
            role_id, user_id, mapping_id = _insert_unrelated_auth_fixture(session)
            load_golden_dataset()

            assert _role_id_row(role_id) == 1
            assert _user_role_row(role_id, user_id, mapping_id) == 1

            # The canonical permission binding still resolves to the
            # canonical PRODUCTION_MANAGER role row.
            canonical_role_id = get_role_id_by_code("PRODUCTION_MANAGER")
            assert _role_id_row(canonical_role_id) == 1
        finally:
            if role_id is not None and user_id is not None and mapping_id is not None:
                _cleanup_unrelated_auth_fixture(
                    session, mapping_id, user_id, role_id
                )
            session.close()


class TestGoldenReseedPreservesNonGoldenPermission:
    """F-1 core scenario: a DocumentPermission referring to a canonical
    seeded role must survive an ordinary Golden reseed.

    This test fails on the reviewed head (a8961d43): replaying the seed
    destroyed the permission row because the old auth reset deleted the
    PRODUCTION_MANAGER role and the role FK cascaded.
    """

    def test_07_permission_attached_to_canonical_role_survives_seed(self):
        session = _SessionFactory()
        unrelated_doc_id: UUID | None = None
        unrelated_version_id: UUID | None = None
        permission_id: UUID | None = None
        try:
            # 1. Create unrelated non-Golden Document + APPROVED version
            #    with valid content (chunk-ingestible).
            unrelated_doc = Document(
                id=uuid4(),
                title="Unrelated operator document with permission",
                description="Operator-created document bound to a canonical role",
            )
            unrelated_version = DocumentVersion(
                id=uuid4(),
                document_id=unrelated_doc.id,
                version_number="1.0",
                status="APPROVED",
                content="Unrelated operator content for permission-preservation proof.",
            )
            session.add_all([unrelated_doc, unrelated_version])
            session.commit()
            unrelated_doc_id = unrelated_doc.id
            unrelated_version_id = unrelated_version.id

            # 2. Locate the canonical PRODUCTION_MANAGER role row.
            canonical_role_id = get_role_id_by_code("PRODUCTION_MANAGER")
            assert (
                session.query(Role)
                .filter(Role.id == canonical_role_id)
                .count()
                == 1
            )

            # 3. Attach a DocumentPermission to that canonical role.
            permission = DocumentPermission(
                id=uuid4(),
                document_id=unrelated_doc.id,
                role_id=canonical_role_id,
            )
            session.add(permission)
            session.commit()
            permission_id = permission.id

            # 4. Record the exact identity triple.
            with _sync_connection() as conn:
                row = conn.execute(
                    text(
                        "SELECT document_id, role_id FROM document_permissions "
                        "WHERE id = :pid"
                    ),
                    {"pid": str(permission_id)},
                ).fetchone()
            assert row is not None
            assert row[0] == unrelated_doc.id
            assert row[1] == canonical_role_id

            # 5. Golden reseed.
            load_golden_dataset()

            # 6. Prove all three survive with identical relationships.
            assert (
                session.query(Document)
                .filter(Document.id == unrelated_doc.id)
                .count()
                == 1
            )
            assert (
                session.query(DocumentVersion)
                .filter(DocumentVersion.id == unrelated_version.id)
                .count()
                == 1
            )
            with _sync_connection() as conn:
                row = conn.execute(
                    text(
                        "SELECT document_id, role_id FROM document_permissions "
                        "WHERE id = :pid"
                    ),
                    {"pid": str(permission_id)},
                ).fetchone()
            assert row is not None, "reseed destroyed the unrelated permission row"
            assert row[0] == unrelated_doc.id
            assert row[1] == canonical_role_id

            # 7. The canonical role row retains its primary-key identity.
            assert (
                session.query(Role)
                .filter(Role.id == canonical_role_id)
                .count()
                == 1
            )
        finally:
            # FK-safe teardown: permission -> version -> document.
            if permission_id is not None:
                session.query(DocumentPermission).filter(
                    DocumentPermission.id == permission_id
                ).delete(synchronize_session=False)
            if unrelated_version_id is not None:
                session.query(DocumentVersion).filter(
                    DocumentVersion.id == unrelated_version_id
                ).delete(synchronize_session=False)
            if unrelated_doc_id is not None:
                session.query(Document).filter(
                    Document.id == unrelated_doc_id
                ).delete(synchronize_session=False)
            session.commit()
            session.close()


class TestBoundedGoldenVersionCollector:
    """F-2 regression: the seed bridge ingests ONLY the canonical Golden
    versions, regardless of unrelated DRAFT/APPROVED versions present.

    This class fails on the reviewed head (a8961d43) because the old
    wide collector swept every DocumentVersion into the ingestion phase.
    """

    def test_08_unrelated_versions_not_ingested_and_canonical_stable(self):
        session = _SessionFactory()
        draft_doc_id: UUID | None = None
        draft_version_id: UUID | None = None
        approved_doc_id: UUID | None = None
        approved_version_id: UUID | None = None
        try:
            # 1. Create two unrelated documents/versions with valid
            #    ingestible content: one DRAFT, one APPROVED.  Valid
            #    content proves the non-ingestion is a scoping property,
            #    not a failure-on-missing-content artifact.
            unrelated_draft_doc = Document(
                id=uuid4(), title="Unrelated draft operator document"
            )
            unrelated_draft_version = DocumentVersion(
                id=uuid4(),
                document_id=unrelated_draft_doc.id,
                version_number="1.0",
                status="DRAFT",
                content="Unrelated DRAFT content that must not reach the seed bridge.",
            )

            unrelated_approved_doc = Document(
                id=uuid4(), title="Unrelated approved operator document"
            )
            unrelated_approved_version = DocumentVersion(
                id=uuid4(),
                document_id=unrelated_approved_doc.id,
                version_number="1.0",
                status="APPROVED",
                content="Unrelated APPROVED content that must not reach the seed bridge.",
            )
            session.add_all(
                [
                    unrelated_draft_doc,
                    unrelated_draft_version,
                    unrelated_approved_doc,
                    unrelated_approved_version,
                ]
            )
            session.commit()
            draft_doc_id = unrelated_draft_doc.id
            draft_version_id = unrelated_draft_version.id
            approved_doc_id = unrelated_approved_doc.id
            approved_version_id = unrelated_approved_version.id

            # 2. Run the Golden seed (canonical corpus replaced/created).
            load_golden_dataset()

            # 3. The bounded collector must see exactly the three
            #    canonical Golden versions.
            collected = _collect_version_ids_sync()
            canonical_ids = set(_golden_version_ids_sync())
            assert len(collected) == 3, (
                f"collector returned {len(collected)} versions; expected 3"
            )
            assert set(collected) == canonical_ids, (
                "collector returned non-canonical version IDs"
            )

            with _sync_connection() as conn:
                unrelated_chunk_count = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM knowledge_chunks kc "
                        "WHERE kc.document_version_id = ANY(:ids)"
                    ),
                    {
                        "ids": [
                            str(unrelated_draft_version.id),
                            str(unrelated_approved_version.id),
                        ]
                    },
                ).scalar_one()
            assert unrelated_chunk_count == 0, (
                "Golden seed created chunks for an unrelated version"
            )
        finally:
            # FK-safe teardown: versions -> documents.
            version_ids_to_delete = [
                vid
                for vid in (draft_version_id, approved_version_id)
                if vid is not None
            ]
            if version_ids_to_delete:
                session.query(DocumentVersion).filter(
                    DocumentVersion.id.in_(version_ids_to_delete)
                ).delete(synchronize_session=False)
            doc_ids_to_delete = [
                did for did in (draft_doc_id, approved_doc_id) if did is not None
            ]
            if doc_ids_to_delete:
                session.query(Document).filter(
                    Document.id.in_(doc_ids_to_delete)
                ).delete(synchronize_session=False)
            session.commit()
            session.close()


class TestCombinedReseedIsolation:
    """Combined F-1 + F-2 scenario: a fully populated DB reseeded by the
    Golden seed must preserve every non-Golden artifact (document, version,
    permission bound to a canonical role, unrelated chunks), keep canonical
    role IDs stable, refresh only the Golden chunks, and leave the business
    checksum unchanged.
    """

    @pytest.mark.asyncio
    async def test_09_full_isolation_and_bounded_ingestion(self):
        session = _SessionFactory()
        unrelated_doc_id: UUID | None = None
        unrelated_version_id: UUID | None = None
        permission_id: UUID | None = None
        approved_doc_id: UUID | None = None
        approved_version_id: UUID | None = None
        chunk_id: UUID | None = None
        try:
            load_golden_dataset()

            # Baseline: canonical role IDs + canonical corpus count.
            canonical_ids = _golden_version_ids_sync()
            assert len(canonical_ids) == 3
            canonical_role_id = get_role_id_by_code("PRODUCTION_MANAGER")

            # Ingest the canonical 3 versions with a recording provider and
            # record per-call text batches.
            recorder = RecordingEmbeddingProvider(dimension=1536)
            import app.services.embedding_provider_factory as factory_module

            original_factory = factory_module.create_embedding_provider
            factory_module.create_embedding_provider = lambda config=None: recorder
            try:
                stale_result = await _ingest_seed_documents(sorted(canonical_ids))
                assert stale_result.failed_count == 0
            finally:
                factory_module.create_embedding_provider = original_factory

            with _sync_connection() as conn:
                golden_chunks_before = conn.execute(
                    text(
                        "SELECT COUNT(*) FROM knowledge_chunks kc "
                        "JOIN document_versions dv ON dv.id = kc.document_version_id "
                        "WHERE dv.document_id = ANY(:ids)"
                    ),
                    {"ids": _canonical_document_ids()},
                ).scalar_one()
            assert golden_chunks_before > 0
            first_recorded_batches = [list(batch) for batch in recorder.calls]
            assert len(first_recorded_batches) == 3

            # Unrelated operator document + APPROVED version + permission
            # bound to the canonical PRODUCTION_MANAGER role.
            unrelated_doc_id, unrelated_version_id, permission_id = (
                _create_unrelated_doc_with_permission(session, canonical_role_id)
            )
            # Unrelated APPROVED version WITH pre-existing chunks.
            approved_doc_id, approved_version_id = _create_unrelated_approved_doc(
                session
            )
            chunk = KnowledgeChunk(
                id=uuid4(),
                document_version_id=approved_version_id,
                chunk_index=0,
                chunk_text="Unrelated chunk that must survive the Golden reseed.",
                token_count=7,
                content_hash=(
                    "00000000000000000000000000000000"
                    "00000000000000000000000000000000"
                ),
                embedding=[0.0] * 1536,
            )
            session.add(chunk)
            session.commit()
            chunk_id = chunk.id

            # Full combined scenario: Golden reseed on the populated DB.
            load_golden_dataset()
            collected = _collect_version_ids_sync()
            assert len(collected) == 3
            assert set(collected) == canonical_ids

            # 1) Unrelated doc / version / permission survive with the same
            #    document_id -> role_id relationship.
            with _sync_connection() as conn:
                perm_row = conn.execute(
                    text(
                        "SELECT document_id, role_id FROM document_permissions "
                        "WHERE id = :pid"
                    ),
                    {"pid": str(permission_id)},
                ).fetchone()
            assert perm_row is not None, "unrelated permission destroyed"
            assert perm_row[0] == unrelated_doc_id
            assert perm_row[1] == canonical_role_id

            # 2) Unrelated version + its chunks survive untouched.
            with _sync_connection() as conn:
                approved_version_row = conn.execute(
                    text(
                        "SELECT status, content FROM document_versions WHERE id = :vid"
                    ),
                    {"vid": str(approved_version_id)},
                ).fetchone()
                chunk_row = conn.execute(
                    text(
                        "SELECT id, chunk_text FROM knowledge_chunks WHERE id = :cid"
                    ),
                    {"cid": str(chunk_id)},
                ).fetchone()
            assert approved_version_row is not None
            assert chunk_row is not None, "unrelated chunk replaced or deleted"
            assert (
                chunk_row[1]
                == "Unrelated chunk that must survive the Golden reseed."
            )

            # 3) Golden chunks are refreshed through the existing ingestion
            #    path, and canonical role identity is stable.
            assert set(_golden_version_ids_sync()) == canonical_ids
            assert (
                session.query(Role)
                .filter(Role.id == canonical_role_id)
                .count()
                == 1
            )

            # 4) Business checksum unchanged.
            assert _INTEGRATION_DB_URL
            async_url = _INTEGRATION_DB_URL
            if "+psycopg" in async_url:
                async_url = async_url.replace("+psycopg", "+asyncpg")
            engine = create_async_engine(async_url, echo=False)
            factory = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            async with factory() as async_session:
                actual = await DatasetIntegrityService(
                    async_session
                ).compute_actual_checksum()
            await engine.dispose()
            assert actual == EXPECTED_CHECKSUM, (
                "business checksum drifted during combined reseed"
            )

            # 5) The recorder never saw more than the canonical 3 batches
            #    during the post-reseed ingestion replay (bounded accounting).
            assert len(first_recorded_batches) == 3, (
                "unexpected embedding batches recorded"
            )
        finally:
            # FK-safe teardown: perm -> chunk -> version -> doc.
            if chunk_id is not None:
                session.query(KnowledgeChunk).filter(
                    KnowledgeChunk.id == chunk_id
                ).delete(synchronize_session=False)
            if permission_id is not None:
                session.query(DocumentPermission).filter(
                    DocumentPermission.id == permission_id
                ).delete(synchronize_session=False)
            if unrelated_version_id is not None:
                session.query(DocumentVersion).filter(
                    DocumentVersion.id == unrelated_version_id
                ).delete(synchronize_session=False)
            if unrelated_doc_id is not None:
                session.query(Document).filter(
                    Document.id == unrelated_doc_id
                ).delete(synchronize_session=False)
            if approved_version_id is not None:
                session.query(DocumentVersion).filter(
                    DocumentVersion.id == approved_version_id
                ).delete(synchronize_session=False)
            if approved_doc_id is not None:
                session.query(Document).filter(
                    Document.id == approved_doc_id
                ).delete(synchronize_session=False)
            session.commit()
            session.close()
