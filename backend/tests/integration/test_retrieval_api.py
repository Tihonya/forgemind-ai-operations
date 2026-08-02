"""Integration tests for WP-4.4C: Retrieval API endpoint.

Tests the POST /api/v1/retrieval endpoint with authentication, authorization,
and citation construction.
"""

import re
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.main import app
from app.models.document import Document, DocumentPermission, DocumentVersion
from app.models.user import Role, User, UserRole
from app.services.auth_service import issue_token
from app.services.embedding_provider import FakeEmbeddingProvider
from app.services.ingestion import IngestionOrchestrator

# ---------------------------------------------------------------------------
# Integration-gate: skip entire module when no DB is reachable
# ---------------------------------------------------------------------------


def _get_test_database_url() -> str:
    """Resolve database URL from .env with placeholder interpolation."""
    import urllib.parse
    from pathlib import Path

    test_file_dir = Path(__file__).resolve().parent
    env_file = test_file_dir.parent.parent.parent / ".env"

    env_vars = {}
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Defensive pre-test cleanup for residual WP44C_* data
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def cleanup_residual_wp44c_data(async_session: AsyncSession) -> AsyncIterator[None]:
    """Clean up any residual WP44C_* test data from previous broken runs.

    This runs before each test to ensure a clean state.
    Only deletes data with WP44C_* role codes (test-owned records).
    """
    # Delete in FK-safe order
    # 1. knowledge_chunks linked to WP44C_* documents
    await async_session.execute(
        text(
            "DELETE FROM knowledge_chunks WHERE document_version_id IN "
            "(SELECT id FROM document_versions WHERE document_id IN "
            "(SELECT id FROM documents WHERE id IN "
            "(SELECT document_id FROM document_permissions WHERE role_id IN "
            "(SELECT id FROM roles WHERE code LIKE 'WP44C_%'))))"
        )
    )
    # 2. document_versions linked to WP44C_* documents
    await async_session.execute(
        text(
            "DELETE FROM document_versions WHERE document_id IN "
            "(SELECT id FROM documents WHERE id IN "
            "(SELECT document_id FROM document_permissions WHERE role_id IN "
            "(SELECT id FROM roles WHERE code LIKE 'WP44C_%')))"
        )
    )
    # 3. document_permissions linked to WP44C_* roles
    await async_session.execute(
        text(
            "DELETE FROM document_permissions WHERE role_id IN "
            "(SELECT id FROM roles WHERE code LIKE 'WP44C_%')"
        )
    )
    # 4. documents owned by WP44C_* permissions
    await async_session.execute(
        text(
            "DELETE FROM documents WHERE id IN "
            "(SELECT document_id FROM document_permissions WHERE role_id IN "
            "(SELECT id FROM roles WHERE code LIKE 'WP44C_%'))"
        )
    )
    # 5. user_roles linked to WP44C_* roles
    await async_session.execute(
        text(
            "DELETE FROM user_roles WHERE role_id IN "
            "(SELECT id FROM roles WHERE code LIKE 'WP44C_%')"
        )
    )
    # 6. users linked to WP44C_* user_roles
    await async_session.execute(
        text(
            "DELETE FROM users WHERE id IN "
            "(SELECT user_id FROM user_roles WHERE role_id IN "
            "(SELECT id FROM roles WHERE code LIKE 'WP44C_%'))"
        )
    )
    # 7. WP44C_* roles
    await async_session.execute(
        text("DELETE FROM roles WHERE code LIKE 'WP44C_%'")
    )
    await async_session.commit()

    yield


# ---------------------------------------------------------------------------
# Test setup fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def test_setup(async_session: AsyncSession) -> AsyncIterator[dict]:
    """Create test user, role, document, and chunks for API testing."""
    import bcrypt

    from app.models.user import UserRole

    # Create role with unique code
    test_suffix = uuid4().hex[:8]
    role = Role(id=uuid4(), code=f"WP44C_TEST_ROLE_{test_suffix}", name="WP-4.4C Test Role")
    async_session.add(role)
    await async_session.flush()

    # Create user
    user_id = uuid4()
    user = User(
        id=user_id,
        username="wp44c_test_user",
        display_name="WP-4.4C Test User",
        hashed_password=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode("utf-8"),
    )
    async_session.add(user)
    await async_session.flush()

    # Assign role to user using ORM
    user_role = UserRole(id=uuid4(), user_id=user_id, role_id=role.id)
    async_session.add(user_role)
    await async_session.flush()

    # Create document with content
    content = "WP-4.4C test document content. " * 200

    # Issue JWT for the test user
    token = issue_token(user, [role.code])

    # Create document with permission for this role
    doc_id = uuid4()
    version_id = uuid4()

    doc = Document(id=doc_id, title="WP-4.4C API Test Document", description=None)
    version = DocumentVersion(
        id=version_id,
        document_id=doc_id,
        version_number="1.0",
        status="APPROVED",
        content_hash=None,
        content=content,
    )

    async_session.add(doc)
    async_session.add(version)
    await async_session.flush()

    perm = DocumentPermission(
        id=uuid4(),
        document_id=doc_id,
        role_id=role.id,
    )
    async_session.add(perm)
    await async_session.flush()

    # Ingest to create chunks
    provider = FakeEmbeddingProvider(dimension=1536)
    orchestrator = IngestionOrchestrator(async_session, provider)
    await orchestrator.ingest_document_version(version_id)
    await async_session.commit()

    # Generate query embedding
    embeddings = await provider.embed_text([content])
    query_embedding = embeddings[0]

    yield {
        "token": token,
        "role_id": role.id,
        "doc_id": doc_id,
        "version_id": version_id,
        "query_embedding": query_embedding,
        "content": content,
        "user": user,
        "role": role,
    }

    # Cleanup
    await async_session.rollback()
    await async_session.execute(
        text("DELETE FROM knowledge_chunks WHERE document_version_id = :vid"),
        {"vid": version_id},
    )
    await async_session.execute(
        text("DELETE FROM document_versions WHERE id = :vid"),
        {"vid": version_id},
    )
    await async_session.execute(
        text("DELETE FROM document_permissions WHERE document_id = :did"),
        {"did": doc_id},
    )
    await async_session.execute(
        text("DELETE FROM documents WHERE id = :did"),
        {"did": doc_id},
    )
    await async_session.execute(
        text("DELETE FROM user_roles WHERE role_id = :rid"),
        {"rid": role.id},
    )
    await async_session.execute(
        text("DELETE FROM roles WHERE id = :rid"),
        {"rid": role.id},
    )
    await async_session.execute(
        text("DELETE FROM users WHERE id = :uid"),
        {"uid": user_id},
    )
    await async_session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_unauthenticated_request_rejected(client: AsyncClient) -> None:
    """Unauthenticated request returns 401."""
    response = await client.post(
        "/api/v1/retrieval",
        json={
            "query_embedding": [0.1] * 1536,
            "top_k": 10,
        },
    )
    assert response.status_code == 401


async def test_authenticated_caller_role_ids_derived_server_side(
    client: AsyncClient,
    test_setup: dict,
) -> None:
    """Authenticated caller's role IDs are derived server-side."""
    response = await client.post(
        "/api/v1/retrieval",
        json={
            "query_embedding": test_setup["query_embedding"],
            "top_k": 10,
        },
        headers={"Authorization": f"Bearer {test_setup['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    # Should return results because user has permission
    assert data["total_results"] > 0


async def test_request_provided_role_escalation_impossible(
    client: AsyncClient,
    async_session: AsyncSession,
) -> None:
    """Request body cannot expand user's access via role_ids field.

    Creates an inaccessible document permitted only to a different role,
    submits that role_id in the request body, and proves the restricted
    document/chunk is still absent from results.
    """
    import bcrypt

    # Create two roles: one for the user, one for the restricted document
    # Use unique codes with UUID suffix to avoid conflicts
    suffix = uuid4().hex[:8]
    user_role = Role(id=uuid4(), code=f"WP44C_USER_ROLE_{suffix}", name="User Role")
    other_role = Role(id=uuid4(), code=f"WP44C_OTHER_ROLE_{suffix}", name="Other Role")
    async_session.add(user_role)
    async_session.add(other_role)
    await async_session.flush()

    # Create user with user_role
    user_id = uuid4()
    user = User(
        id=user_id,
        username=f"wp44c_escalation_test_user_{suffix}",
        display_name="WP-4.4C Escalation Test User",
        hashed_password=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode("utf-8"),
    )
    async_session.add(user)
    await async_session.flush()

    # Create UserRole with explicit ID
    user_role_link = UserRole(id=uuid4(), user_id=user_id, role_id=user_role.id)
    async_session.add(user_role_link)
    await async_session.flush()

    # Create restricted document permitted only to other_role
    restricted_content = "Restricted content for escalation test. " * 200
    restricted_doc_id = uuid4()
    restricted_version_id = uuid4()

    restricted_doc = Document(
        id=restricted_doc_id,
        title="Restricted Document",
        description=None,
    )
    restricted_version = DocumentVersion(
        id=restricted_version_id,
        document_id=restricted_doc_id,
        version_number="1.0",
        status="APPROVED",
        content_hash=None,
        content=restricted_content,
    )

    async_session.add(restricted_doc)
    async_session.add(restricted_version)
    await async_session.flush()

    # Permission only for other_role (not user_role)
    restricted_perm = DocumentPermission(
        id=uuid4(),
        document_id=restricted_doc_id,
        role_id=other_role.id,
    )
    async_session.add(restricted_perm)
    await async_session.flush()

    # Ingest restricted document
    provider = FakeEmbeddingProvider(dimension=1536)
    orchestrator = IngestionOrchestrator(async_session, provider)
    await orchestrator.ingest_document_version(restricted_version_id)
    await async_session.commit()

    # Generate query embedding matching restricted content
    embeddings = await provider.embed_text([restricted_content])
    query_embedding = embeddings[0]

    # Issue token for user with user_role
    token = issue_token(user, [user_role.code])

    # Submit request with other_role's ID in request body (should be ignored)
    response = await client.post(
        "/api/v1/retrieval",
        json={
            "query_embedding": query_embedding,
            "top_k": 10,
            "role_ids": [str(other_role.id)],  # This should be ignored
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    # User has no permissions, so should get empty results
    assert data["total_results"] == 0
    assert data["results"] == []

    # Verify restricted document is not in results (vacuously true since empty)
    for result in data["results"]:
        assert result["document_id"] != str(restricted_doc_id)

    # Cleanup
    await async_session.rollback()
    await async_session.execute(
        text("DELETE FROM knowledge_chunks WHERE document_version_id = :vid"),
        {"vid": restricted_version_id},
    )
    await async_session.execute(
        text("DELETE FROM document_versions WHERE id = :vid"),
        {"vid": restricted_version_id},
    )
    await async_session.execute(
        text("DELETE FROM document_permissions WHERE document_id = :did"),
        {"did": restricted_doc_id},
    )
    await async_session.execute(
        text("DELETE FROM documents WHERE id = :did"),
        {"did": restricted_doc_id},
    )
    await async_session.execute(
        text("DELETE FROM user_roles WHERE user_id = :uid"),
        {"uid": user_id},
    )
    await async_session.execute(
        text("DELETE FROM users WHERE id = :uid"),
        {"uid": user_id},
    )
    await async_session.execute(
        text("DELETE FROM roles WHERE id IN (:rid1, :rid2)"),
        {"rid1": user_role.id, "rid2": other_role.id},
    )
    await async_session.commit()


async def test_authorized_retrieval_returns_citation_data(
    client: AsyncClient,
    test_setup: dict,
) -> None:
    """Authorized retrieval returns results with citation data."""
    response = await client.post(
        "/api/v1/retrieval",
        json={
            "query_embedding": test_setup["query_embedding"],
            "top_k": 10,
        },
        headers={"Authorization": f"Bearer {test_setup['token']}"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total_results"] > 0
    assert len(data["results"]) > 0

    result = data["results"][0]
    assert "document_id" in result
    assert "version_id" in result
    assert "chunk_id" in result
    assert "chunk_index" in result
    assert "similarity" in result
    assert "citation" in result

    citation = result["citation"]
    assert citation["document_id"] == str(test_setup["doc_id"])
    assert citation["version_id"] == str(test_setup["version_id"])
    assert citation["chunk_index"] >= 0


async def test_restricted_chunk_never_appears(
    client: AsyncClient,
    test_setup: dict,
) -> None:
    """Restricted chunk (no permission) never appears in results."""
    # Create a second role with no permission
    from uuid import uuid4

    import bcrypt
    from sqlalchemy import text

    from app.database import async_session_factory

    async with async_session_factory() as session:
        restricted_role_id = uuid4()
        # Use unique code with UUID suffix to avoid conflicts
        suffix = uuid4().hex[:8]
        await session.execute(
            text(
                "INSERT INTO roles (id, code, name) VALUES (:id, :code, :name)"
            ),
            {
                "id": restricted_role_id,
                "code": f"WP44C_RESTRICTED_ROLE_{suffix}",
                "name": "Restricted Role",
            },
        )
        await session.commit()

        # Create user with restricted role
        user_id = uuid4()
        hashed_pw = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode("utf-8")
        await session.execute(
            text(
                "INSERT INTO users (id, username, display_name, hashed_password) "
                "VALUES (:id, :username, :display_name, :password)"
            ),
            {
                "id": user_id,
                "username": f"restricted_user_{suffix}",
                "display_name": "Restricted User",
                "password": hashed_pw,
            },
        )
        # Fix: provide explicit ID for UserRole
        session.add(UserRole(id=uuid4(), user_id=user_id, role_id=restricted_role_id))
        await session.commit()

        # Issue token
        from app.models.user import User
        from app.services.auth_service import issue_token

        user = await session.get(User, user_id)
        token = issue_token(user, [f"WP44C_RESTRICTED_ROLE_{suffix}"])

        # Query with restricted role — should get no results
        response = await client.post(
            "/api/v1/retrieval",
            json={
                "query_embedding": test_setup["query_embedding"],
                "top_k": 10,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_results"] == 0

        # Cleanup
        await session.execute(
            text("DELETE FROM user_roles WHERE role_id = :rid"),
            {"rid": restricted_role_id},
        )
        await session.execute(
            text("DELETE FROM roles WHERE id = :rid"),
            {"rid": restricted_role_id},
        )
        await session.execute(
            text("DELETE FROM users WHERE id = :uid"),
            {"uid": user_id},
        )
        await session.commit()


async def test_empty_result_set_returns_successful_empty_response(
    client: AsyncClient,
    async_session: AsyncSession,
) -> None:
    """Empty result set returns 200 with exactly zero results.

    Creates an authenticated principal with no matching DocumentPermission
    and asserts status_code == 200, total_results == 0, results == [].
    """
    import bcrypt

    # Create role with no document permissions - use unique code
    suffix = uuid4().hex[:8]
    empty_role = Role(id=uuid4(), code=f"WP44C_EMPTY_ROLE_{suffix}", name="Empty Role")
    async_session.add(empty_role)
    await async_session.flush()

    # Create user with this role
    user_id = uuid4()
    user = User(
        id=user_id,
        username=f"wp44c_empty_user_{suffix}",
        display_name="WP-4.4C Empty User",
        hashed_password=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode("utf-8"),
    )
    async_session.add(user)
    await async_session.flush()

    async_session.add(UserRole(id=uuid4(), user_id=user_id, role_id=empty_role.id))
    await async_session.flush()
    await async_session.commit()

    # Issue token
    token = issue_token(user, [empty_role.code])

    # Query with valid embedding
    query_embedding = [0.1] * 1536

    response = await client.post(
        "/api/v1/retrieval",
        json={
            "query_embedding": query_embedding,
            "top_k": 10,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_results"] == 0
    assert data["results"] == []

    # Cleanup
    await async_session.execute(
        text("DELETE FROM user_roles WHERE user_id = :uid"),
        {"uid": user_id},
    )
    await async_session.execute(
        text("DELETE FROM users WHERE id = :uid"),
        {"uid": user_id},
    )
    await async_session.execute(
        text("DELETE FROM roles WHERE id = :rid"),
        {"rid": empty_role.id},
    )
    await async_session.commit()


async def test_top_k_reaches_service_correctly(
    client: AsyncClient,
    test_setup: dict,
) -> None:
    """top_k parameter is passed to service correctly."""
    response = await client.post(
        "/api/v1/retrieval",
        json={
            "query_embedding": test_setup["query_embedding"],
            "top_k": 5,
        },
        headers={"Authorization": f"Bearer {test_setup['token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    # Should return at most 5 results
    assert data["total_results"] <= 5


async def test_invalid_embedding_returns_client_error(
    client: AsyncClient,
    test_setup: dict,
) -> None:
    """Invalid embedding returns 400."""
    # Wrong dimension
    response = await client.post(
        "/api/v1/retrieval",
        json={
            "query_embedding": [0.1] * 100,  # Wrong dimension
            "top_k": 10,
        },
        headers={"Authorization": f"Bearer {test_setup['token']}"},
    )
    assert response.status_code == 400
    data = response.json()
    assert "error" in data["detail"]


async def test_deterministic_ordering_remains_intact(
    client: AsyncClient,
    async_session: AsyncSession,
) -> None:
    """Deterministic ordering is preserved with multiple chunks.

    Creates at least two authorized chunks with deterministic retrieval
    ordering and asserts total_results >= 2, exact order by similarity DESC,
    then stable tie ordering by document_id, version_id, chunk_index, chunk_id.
    """
    import bcrypt

    # Create role - use unique code
    suffix = uuid4().hex[:8]
    role = Role(id=uuid4(), code=f"WP44C_ORDER_ROLE_{suffix}", name="Order Test Role")
    async_session.add(role)
    await async_session.flush()

    # Create user
    user_id = uuid4()
    user = User(
        id=user_id,
        username=f"wp44c_order_user_{suffix}",
        display_name="WP-4.4C Order Test User",
        hashed_password=bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode("utf-8"),
    )
    async_session.add(user)
    await async_session.flush()

    async_session.add(UserRole(id=uuid4(), user_id=user_id, role_id=role.id))
    await async_session.flush()

    # Create two documents with different content (different embeddings)
    content_a = "Document A content for ordering test. " * 200
    content_b = "Document B content for ordering test. " * 200

    doc_a_id = uuid4()
    version_a_id = uuid4()
    doc_a = Document(id=doc_a_id, title="Document A", description=None)
    version_a = DocumentVersion(
        id=version_a_id,
        document_id=doc_a_id,
        version_number="1.0",
        status="APPROVED",
        content_hash=None,
        content=content_a,
    )

    doc_b_id = uuid4()
    version_b_id = uuid4()
    doc_b = Document(id=doc_b_id, title="Document B", description=None)
    version_b = DocumentVersion(
        id=version_b_id,
        document_id=doc_b_id,
        version_number="1.0",
        status="APPROVED",
        content_hash=None,
        content=content_b,
    )

    async_session.add(doc_a)
    async_session.add(version_a)
    async_session.add(doc_b)
    async_session.add(version_b)
    await async_session.flush()

    # Permissions for both documents
    perm_a = DocumentPermission(
        id=uuid4(), document_id=doc_a_id, role_id=role.id
    )
    perm_b = DocumentPermission(
        id=uuid4(), document_id=doc_b_id, role_id=role.id
    )
    async_session.add(perm_a)
    async_session.add(perm_b)
    await async_session.flush()

    # Ingest both documents
    provider = FakeEmbeddingProvider(dimension=1536)
    orchestrator = IngestionOrchestrator(async_session, provider)
    await orchestrator.ingest_document_version(version_a_id)
    await orchestrator.ingest_document_version(version_b_id)
    await async_session.commit()

    # Generate query embedding matching content_a (higher similarity)
    embeddings = await provider.embed_text([content_a])
    query_embedding = embeddings[0]

    # Issue token
    user_from_db = await async_session.get(User, user_id)
    assert user_from_db is not None
    token = issue_token(user_from_db, [role.code])

    # Query
    response = await client.post(
        "/api/v1/retrieval",
        json={
            "query_embedding": query_embedding,
            "top_k": 10,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()

    # Should have at least 2 results (chunks from both documents)
    assert data["total_results"] >= 2

    # Verify ordering: similarity DESC
    similarities = [r["similarity"] for r in data["results"]]
    assert similarities == sorted(similarities, reverse=True), (
        "Results not ordered by similarity DESC"
    )

    # Verify stable tie ordering for same similarity
    # Group by similarity and check tie-breakers
    for i in range(len(data["results"]) - 1):
        r1 = data["results"][i]
        r2 = data["results"][i + 1]

        if r1["similarity"] == r2["similarity"]:
            # Same similarity — check tie-breakers
            # document_id ASC
            if r1["document_id"] == r2["document_id"]:
                # version_id ASC
                if r1["version_id"] == r2["version_id"]:
                    # chunk_index ASC
                    if r1["chunk_index"] == r2["chunk_index"]:
                        # chunk_id ASC
                        assert r1["chunk_id"] <= r2["chunk_id"], (
                            "Tie-breaker chunk_id not in ASC order"
                        )
                    else:
                        assert r1["chunk_index"] < r2["chunk_index"], (
                            "Tie-breaker chunk_index not in ASC order"
                        )
                else:
                    assert r1["version_id"] < r2["version_id"], (
                        "Tie-breaker version_id not in ASC order"
                    )
            else:
                assert r1["document_id"] < r2["document_id"], (
                    "Tie-breaker document_id not in ASC order"
                )

    # Cleanup
    await async_session.rollback()
    await async_session.execute(
        text("DELETE FROM knowledge_chunks WHERE document_version_id = :vid"),
        {"vid": version_a_id},
    )
    await async_session.execute(
        text("DELETE FROM knowledge_chunks WHERE document_version_id = :vid"),
        {"vid": version_b_id},
    )
    await async_session.execute(
        text("DELETE FROM document_versions WHERE id IN (:vid1, :vid2)"),
        {"vid1": version_a_id, "vid2": version_b_id},
    )
    await async_session.execute(
        text("DELETE FROM document_permissions WHERE document_id IN (:did1, :did2)"),
        {"did1": doc_a_id, "did2": doc_b_id},
    )
    await async_session.execute(
        text("DELETE FROM documents WHERE id IN (:did1, :did2)"),
        {"did1": doc_a_id, "did2": doc_b_id},
    )
    await async_session.execute(
        text("DELETE FROM user_roles WHERE user_id = :uid"),
        {"uid": user_id},
    )
    await async_session.execute(
        text("DELETE FROM users WHERE id = :uid"),
        {"uid": user_id},
    )
    await async_session.execute(
        text("DELETE FROM roles WHERE id = :rid"),
        {"rid": role.id},
    )
    await async_session.commit()


async def test_exact_document_version_chunk_ids_returned(
    client: AsyncClient,
    test_setup: dict,
) -> None:
    """Exact document_id, version_id, chunk_id are returned."""
    response = await client.post(
        "/api/v1/retrieval",
        json={
            "query_embedding": test_setup["query_embedding"],
            "top_k": 10,
        },
        headers={"Authorization": f"Bearer {test_setup['token']}"},
    )
    assert response.status_code == 200
    data = response.json()

    assert data["total_results"] > 0
    result = data["results"][0]

    # Verify exact IDs
    assert result["document_id"] == str(test_setup["doc_id"])
    assert result["version_id"] == str(test_setup["version_id"])
    assert "chunk_id" in result
    assert result["citation"]["document_id"] == str(test_setup["doc_id"])
    assert result["citation"]["version_id"] == str(test_setup["version_id"])
