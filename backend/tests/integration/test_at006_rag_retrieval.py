"""Integration test for AT-006: RAG retrieval and citation verification.

Proves that a mitigation query retrieves the approved component-alternative
document with valid citation evidence (document_id, version_number, chunk_id).

Uses deterministic evaluation fixtures from US-001:
- backend/tests/fixtures/evaluation/rag_documents.json
- backend/tests/fixtures/evaluation/rag_queries.json

No external embedding endpoints are contacted. No LLM prose is generated.
"""

import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.rag.citations import Citation, build_citation
from app.ai.rag.retriever import RetrievalService
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.knowledge import KnowledgeChunk
from app.models.user import Role

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "evaluation"


def _get_test_database_url() -> str:
    import urllib.parse

    test_file_dir = Path(__file__).resolve().parent
    env_file = test_file_dir.parent.parent.parent / ".env"

    env_vars: dict[str, str] = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env_vars[key.strip()] = value.strip()

    def interpolate(value: str) -> str:
        pattern = re.compile(r"\$\{(\w+)\}")

        def replacer(match: re.Match[str]) -> str:
            var_name: str = match.group(1)
            return env_vars.get(var_name, match.group(0))

        prev: str | None = None
        while prev != value:
            prev = value
            value = pattern.sub(replacer, value)
        return value

    user = interpolate(env_vars.get("POSTGRES_USER", ""))
    password = interpolate(env_vars.get("POSTGRES_PASSWORD", ""))
    host = "localhost"
    port = interpolate(env_vars.get("POSTGRES_PORT", "5432"))
    db = interpolate(env_vars.get("POSTGRES_DB", ""))

    password_encoded = urllib.parse.quote_plus(password)

    return f"postgresql+asyncpg://{user}:{password_encoded}@{host}:{port}/{db}"


INTEGRATION_DB_URL = _get_test_database_url()


def _can_connect() -> bool:
    if not INTEGRATION_DB_URL:
        return False
    try:
        from sqlalchemy import create_engine

        url = INTEGRATION_DB_URL.replace("+asyncpg", "+psycopg")
        eng = create_engine(url, pool_pre_ping=True)
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _can_connect(),
    reason="Integration database not available",
)


def _get_async_engine() -> AsyncEngine:
    assert INTEGRATION_DB_URL is not None
    url = INTEGRATION_DB_URL
    if "+psycopg" in url:
        url = url.replace("+psycopg", "+asyncpg")
    return create_async_engine(url, echo=False, pool_pre_ping=True)


@pytest.fixture
async def async_session() -> AsyncIterator[AsyncSession]:
    engine = _get_async_engine()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture(scope="module")
def rag_documents() -> dict:
    with open(FIXTURES_DIR / "rag_documents.json") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def rag_queries() -> dict:
    with open(FIXTURES_DIR / "rag_queries.json") as f:
        return json.load(f)


@pytest.fixture
async def fixture_data(
    async_session: AsyncSession,
    rag_documents: dict,
    rag_queries: dict,
) -> AsyncIterator[dict]:
    doc_fixture = rag_documents["documents"][0]
    query_fixture = rag_queries["queries"][0]

    doc_id = UUID(doc_fixture["document_id"])
    version_id = UUID(doc_fixture["version"]["version_id"])
    version_number = doc_fixture["version"]["version_number"]
    role_id = UUID(doc_fixture["permissions"][0]["role_id"])

    role = Role(id=role_id, code=f"AT006_ROLE_{role_id.hex[:8]}", name="AT-006 Test Role")
    async_session.add(role)
    await async_session.flush()

    doc = Document(
        id=doc_id,
        title=doc_fixture["title"],
        description=doc_fixture.get("description"),
    )
    async_session.add(doc)
    await async_session.flush()

    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number=version_number,
        status=doc_fixture["version"]["status"],
        content_hash=None,
        content=" ".join(c["chunk_text"] for c in doc_fixture["chunks"]),
    )
    async_session.add(version)
    await async_session.flush()

    perm = DocumentPermission(
        id=uuid4(),
        document_id=doc_id,
        role_id=role_id,
    )
    async_session.add(perm)
    await async_session.flush()

    for chunk_data in doc_fixture["chunks"]:
        chunk = KnowledgeChunk(
            id=UUID(chunk_data["chunk_id"]),
            document_version_id=version_id,
            chunk_index=chunk_data["chunk_index"],
            chunk_text=chunk_data["chunk_text"],
            content_hash=chunk_data.get("content_hash"),
            token_count=chunk_data.get("token_count"),
            chunk_metadata=chunk_data.get("metadata"),
            embedding=chunk_data["embedding"],
        )
        async_session.add(chunk)
    await async_session.flush()
    await async_session.commit()

    yield {
        "doc_id": doc_id,
        "version_id": version_id,
        "version_number": version_number,
        "role_id": role_id,
        "query_fixture": query_fixture,
        "doc_fixture": doc_fixture,
    }

    await async_session.rollback()
    await async_session.execute(
        text("DELETE FROM knowledge_chunks WHERE document_version_id = :vid"),
        {"vid": version_id},
    )
    await async_session.execute(
        text("DELETE FROM document_permissions WHERE document_id = :did"),
        {"did": doc_id},
    )
    await async_session.execute(
        text("DELETE FROM document_versions WHERE id = :vid"),
        {"vid": version_id},
    )
    await async_session.execute(
        text("DELETE FROM documents WHERE id = :did"),
        {"did": doc_id},
    )
    await async_session.execute(
        text("DELETE FROM user_roles WHERE role_id = :rid"),
        {"rid": role_id},
    )
    await async_session.execute(
        text("DELETE FROM roles WHERE id = :rid"),
        {"rid": role_id},
    )
    await async_session.commit()


async def test_at006_mitigation_query_retrieves_approved_document_with_citations(
    async_session: AsyncSession,
    fixture_data: dict,
) -> None:
    """AT-006: mitigation query retrieves approved component-alternative document.

    Given an approved document about a component alternative, a mitigation
    query returns retrieval results with valid citation evidence
    (document_id, version_number, chunk_id).

    This test validates retrieval and citation evidence only — not LLM prose.
    No external embedding endpoint is contacted.
    """
    doc_id: UUID = fixture_data["doc_id"]
    version_id: UUID = fixture_data["version_id"]
    version_number: str = fixture_data["version_number"]
    role_id: UUID = fixture_data["role_id"]
    query_fixture: dict = fixture_data["query_fixture"]
    doc_fixture: dict = fixture_data["doc_fixture"]

    query_embedding: list[float] = query_fixture["embedding"]
    allowed_role_ids = {UUID(r) for r in query_fixture["allowed_role_ids"]}
    top_k: int = query_fixture["top_k"]
    expected_results: list[dict] = query_fixture["expected_results"]

    service = RetrievalService()
    retrieval_results = await service.retrieve(
        async_session,
        query_embedding,
        allowed_role_ids=allowed_role_ids,
        top_k=top_k,
    )

    assert len(retrieval_results) > 0, "Mitigation query returned no results"

    for result in retrieval_results:
        assert result.document_id is not None
        assert result.version_id is not None
        assert result.chunk_id is not None

    for expected in expected_results:
        expected_doc_id = UUID(expected["document_id"])
        expected_version_id = UUID(expected["version_id"])
        expected_chunk_id = UUID(expected["chunk_id"])
        expected_chunk_index: int = expected["chunk_index"]
        expected_version_number: str = expected["version_number"]

        matching = [
            r for r in retrieval_results
            if r.chunk_id == expected_chunk_id
        ]
        assert len(matching) == 1, (
            f"Expected chunk {expected_chunk_id} not found in retrieval results"
        )
        result = matching[0]

        assert result.document_id == expected_doc_id, (
            f"document_id mismatch: {result.document_id} != {expected_doc_id}"
        )
        assert result.version_id == expected_version_id, (
            f"version_id mismatch: {result.version_id} != {expected_version_id}"
        )
        assert result.chunk_index == expected_chunk_index, (
            f"chunk_index mismatch: {result.chunk_index} != {expected_chunk_index}"
        )

    version_row = await async_session.execute(
        text("SELECT version_number FROM document_versions WHERE id = :vid"),
        {"vid": version_id},
    )
    actual_version_number = version_row.scalar()
    assert actual_version_number == version_number, (
        f"version_number mismatch: {actual_version_number} != {version_number}"
    )
    for expected in expected_results:
        assert expected["version_number"] == version_number

    for result in retrieval_results:
        citation: Citation = build_citation(result)
        assert citation.document_id == result.document_id
        assert citation.version_id == result.version_id
        assert citation.chunk_id == result.chunk_id
        assert citation.chunk_index == result.chunk_index

    expected_doc_id = UUID(doc_fixture["document_id"])
    for result in retrieval_results:
        assert result.document_id == expected_doc_id, (
            f"Retrieved chunk from wrong document: {result.document_id}"
        )


async def test_at006_retrieval_returns_no_results_without_permission(
    async_session: AsyncSession,
    fixture_data: dict,
) -> None:
    """AT-006: unauthorized role receives zero results for the same query.

    Proves access filtering works: the same query with a different role
    that lacks document permission returns zero results.
    """
    query_fixture: dict = fixture_data["query_fixture"]
    query_embedding: list[float] = query_fixture["embedding"]

    other_role_id = uuid4()
    other_role = Role(
        id=other_role_id,
        code=f"AT006_OTHER_{other_role_id.hex[:8]}",
        name="AT-006 Other Role",
    )
    async_session.add(other_role)
    await async_session.flush()

    try:
        service = RetrievalService()
        results = await service.retrieve(
            async_session,
            query_embedding,
            allowed_role_ids={other_role_id},
            top_k=query_fixture["top_k"],
        )

        assert len(results) == 0, (
            "Unauthorized role should receive zero results"
        )
    finally:
        await async_session.execute(
            text("DELETE FROM roles WHERE id = :rid"),
            {"rid": other_role_id},
        )
        await async_session.commit()


async def test_at006_fixture_determinism(
    async_session: AsyncSession,
    fixture_data: dict,
) -> None:
    """AT-006: repeated queries produce identical results (deterministic)."""
    query_fixture: dict = fixture_data["query_fixture"]
    query_embedding: list[float] = query_fixture["embedding"]
    allowed_role_ids = {UUID(r) for r in query_fixture["allowed_role_ids"]}
    top_k: int = query_fixture["top_k"]

    service = RetrievalService()

    results_1 = await service.retrieve(
        async_session, query_embedding, allowed_role_ids=allowed_role_ids, top_k=top_k
    )
    results_2 = await service.retrieve(
        async_session, query_embedding, allowed_role_ids=allowed_role_ids, top_k=top_k
    )

    assert len(results_1) == len(results_2)
    for r1, r2 in zip(results_1, results_2):
        assert r1.chunk_id == r2.chunk_id
        assert r1.document_id == r2.document_id
        assert r1.version_id == r2.version_id
        assert r1.similarity == r2.similarity
