"""WP-REC-05 F2 integrated vertical workflow tests.

These tests exercise the real production ``execute_workflow`` path (the ARQ
worker vertical wiring) with deterministic fakes/stubs ONLY at external
boundaries:

- AI provider (``_ConfigurableProvider``) — records the prompt, returns a
  configurable recommendation.
- EmbeddingProvider (``RecordingEmbeddingProvider``) — deterministic vectors,
  records every ``embed_text`` call.
- RetrievalService (``_StubRetrievalService``) — records ``allowed_role_ids``
  and returns configured ``RetrievalResult`` objects. Stubbed because direct
  pgvector/DB execution would make the scenario nondeterministic.

The orchestration functions under test (``execute_workflow``,
``_resolve_effective_role_ids``, query/allow-list/serialization/citation
validation) are NOT mocked. The SQL permission-filter evidence for the real
``RetrievalService`` remains in ``test_retriever_access_filtering.py`` /
``test_retriever_vector_query.py`` (unchanged).

The module seeds the deterministic Golden Dataset once
(``load_golden_dataset``) so ``PLAN-2026-W31`` yields its three canonical
risks and the retrieval loop genuinely executes.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Generator
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.rag.retriever import RetrievalResult
from app.ai.workflow import vertical as vertical_module
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.state_machine import WorkflowState
from app.ai.workflow.vertical import execute_workflow
from app.models.workflow import Recommendation, WorkflowRun, WorkflowStep
from app.seed.generator.loader import (
    _delete_existing_auth_data,
    _delete_existing_business_data,
    _find_alembic_ini,
    _SessionFactory,
    load_golden_dataset,
)
from app.services.embedding_provider import (
    EmbeddingProviderError,
    FakeEmbeddingProvider,
)
from tests.integration._workflow_rag_support import (
    RecordingEmbeddingProvider,
    insert_auth_record,
    insert_role,
    insert_user,
    link_user_role,
    seed_authorization_context,
)

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)

# FK-safe per-test teardown. production_plans is deliberately excluded: the
# Golden Dataset plan is module-scoped and must persist across the module.
_F2_CLEANUP_TABLES = (
    "recommendations",
    "workflow_steps",
    "workflow_authorization_records",
    "workflow_runs",
    "user_roles",
    "users",
    "roles",
)


@pytest.fixture(scope="module")
def _seeded_golden_dataset() -> Generator[None, None, None]:
    """Migrate to Alembic head and seed the Golden Dataset once."""
    from alembic.config import Config

    from alembic import command

    # A prior migration test may leave the DB downgraded; the Golden Dataset
    # loader requires the current Alembic head (bf6f888442e9).
    command.upgrade(Config(str(_find_alembic_ini())), "head")
    load_golden_dataset()
    yield
    session = _SessionFactory()
    try:
        _delete_existing_auth_data(session)
        _delete_existing_business_data(session)
        session.commit()
    finally:
        session.close()


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Async session against the live integration database."""
    assert _INTEGRATION_DB_URL is not None
    engine = create_async_engine(_INTEGRATION_DB_URL, echo=False)
    factory = async_sessionmaker[AsyncSession](
        bind=engine, expire_on_commit=False
    )
    async with factory() as session:
        yield session
        for table in _F2_CLEANUP_TABLES:
            # Table names come from the module-level _F2_CLEANUP_TABLES tuple
            # (a hardcoded allowlist), never from user input.
            await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
        await session.commit()
    await engine.dispose()


async def _get_plan_id(session: AsyncSession) -> UUID:
    result = await session.execute(
        text("SELECT id FROM production_plans WHERE code = 'PLAN-2026-W31'")
    )
    row = result.fetchone()
    assert row is not None, "Golden Dataset plan PLAN-2026-W31 not seeded"
    return cast(UUID, row[0])


class _StubRetrievalService:
    """Deterministic stand-in for RetrievalService (external boundary)."""

    def __init__(
        self,
        results: list[RetrievalResult] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.results = list(results or [])
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def retrieve(
        self,
        session: AsyncSession,
        query_embedding: list[float],
        allowed_role_ids: set[UUID],
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        self.calls.append(
            {"allowed_role_ids": set(allowed_role_ids), "top_k": top_k}
        )
        if self.error is not None:
            raise self.error
        return list(self.results)


class _ConfigurableProvider(ChatProvider):
    """Fake provider that records the prompt and returns configurable output."""

    def __init__(
        self,
        sources: list[dict[str, Any]] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._sources = list(sources or [])
        self._error = error
        self.prompts: list[str] = []

    async def complete(
        self,
        prompt: str,
        schema: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> ChatResult:
        self.prompts.append(prompt)
        if self._error is not None:
            raise self._error
        run_id = context.get("run_id", "") if context else ""
        content = {
            "schema_version": "1.0",
            "run_id": run_id,
            "plan_id": "PLAN-2026-W31",
            "risks": [
                {
                    "risk_id": "RISK-001",
                    "summary": "Test risk summary",
                    "business_impact": "Test business impact",
                    "recommended_actions": [],
                    "sources": self._sources,
                }
            ],
        }
        return ChatResult(
            content=json.dumps(content),
            model="fake-model",
            finish_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            metadata={"provider": "fake"},
        )


class _FailingEmbeddingProvider(FakeEmbeddingProvider):
    """Embedding provider that raises a controlled exception."""

    async def embed_text(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingProviderError("embedding service unavailable")


def _mk_result(
    doc_id: UUID,
    version_id: UUID,
    version_number: str,
    chunk_id: UUID,
    chunk_text: str,
) -> RetrievalResult:
    return RetrievalResult(
        document_id=doc_id,
        version_id=version_id,
        version_number=version_number,
        chunk_id=chunk_id,
        chunk_index=0,
        chunk_text=chunk_text,
        metadata=None,
        similarity=0.95,
    )


def _mk_source(doc_id: UUID, version_number: str, chunk_id: UUID) -> dict[str, Any]:
    return {
        "document_id": str(doc_id),
        "version": version_number,
        "chunk_id": str(chunk_id),
    }


async def _get_auth_snapshot(
    session: AsyncSession, run_id: UUID, generation: int
) -> list[str] | None:
    result = await session.execute(
        text(
            "SELECT role_snapshot FROM workflow_authorization_records "
            "WHERE run_id = :run_id AND dispatch_generation = :gen"
        ),
        {"run_id": run_id, "gen": generation},
    )
    row = result.fetchone()
    return list(row[0]) if row is not None else None


async def _get_run(session: AsyncSession, run_id: UUID) -> WorkflowRun:
    result = await session.execute(
        select(WorkflowRun).where(WorkflowRun.id == run_id)
    )
    return result.scalar_one()


async def _get_recommendation(
    session: AsyncSession, run_id: UUID
) -> Recommendation | None:
    result = await session.execute(
        select(Recommendation).where(Recommendation.run_id == run_id)
    )
    return result.scalar_one_or_none()


async def _get_retrieval_steps(
    session: AsyncSession, run_id: UUID
) -> list[WorkflowStep]:
    result = await session.execute(
        select(WorkflowStep).where(
            WorkflowStep.run_id == run_id,
            WorkflowStep.step_name == "retrieval",
        )
    )
    return list(result.scalars().all())


class TestWorkflowRagVertical:
    """Integrated production-path tests for WP-REC-05 RAG workflow."""

    async def test_grounded_success_reaches_completed(
        self,
        _seeded_golden_dataset: None,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """1. GROUNDED SUCCESS — real execute_workflow with stubbed retrieval."""
        session = db_session
        plan_id = await _get_plan_id(session)

        doc_id, version_id, chunk_id = uuid4(), uuid4(), uuid4()
        version_number = "2.1"
        chunk_text = "Accessible engineering note for CTRL-X4 alternative."
        stub = _StubRetrievalService(
            [_mk_result(doc_id, version_id, version_number, chunk_id, chunk_text)]
        )
        monkeypatch.setattr(vertical_module, "RetrievalService", lambda: stub)
        provider = _ConfigurableProvider(
            sources=[_mk_source(doc_id, version_number, chunk_id)]
        )
        embedding = RecordingEmbeddingProvider()

        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()
        _, role_id = await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome = await execute_workflow(
            session=session,
            provider=provider,
            embedding_provider=embedding,
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()

        assert outcome.success is True
        assert outcome.final_state == WorkflowState.COMPLETED.value

        # Effective role IDs reach retrieval for each of the three risks.
        assert len(stub.calls) == 3
        assert all(c["allowed_role_ids"] == {role_id} for c in stub.calls)
        assert all(c["top_k"] == 10 for c in stub.calls)

        # Embedding is invoked with the server-derived deterministic query.
        assert embedding.calls == [
            ["alternative component for CTRL-X4 Control Unit X4"],
            ["alternative component for MOTOR-M2 Motor M2"],
            ["alternative component for SENSOR-L9 Sensor L9"],
        ]

        # Accessible retrieved context reaches the provider prompt.
        assert len(provider.prompts) == 1
        assert str(doc_id) in provider.prompts[0]
        assert chunk_text in provider.prompts[0]

        # Allow-listed sources persisted in the Recommendation using
        # str(Document.id) / version_number / KnowledgeChunk.id.
        rec = await _get_recommendation(session, run.id)
        assert rec is not None
        assert rec.status == "VALIDATED"
        assert rec.content is not None
        sources = rec.content["risks"][0]["sources"]
        assert sources == [
            {
                "document_id": str(doc_id),
                "version": version_number,
                "chunk_id": str(chunk_id),
            }
        ]

        # Retrieval WorkflowStep records safe bounded metadata.
        retrieval_steps = await _get_retrieval_steps(session, run.id)
        assert len(retrieval_steps) == 1
        assert retrieval_steps[0].status == "completed"
        meta = retrieval_steps[0].step_metadata or {}
        assert meta["result_count"] == 1
        assert meta["citation_count"] == 1
        assert meta["citation_ids"] == [
            {
                "document_id": str(doc_id),
                "version": version_number,
                "chunk_id": str(chunk_id),
            }
        ]
        assert "chunk_text" not in meta
        assert "query_text" not in meta

    async def test_restricted_chunks_never_reach_prompt_or_persistence(
        self,
        _seeded_golden_dataset: None,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """2. RESTRICTED-CONTENT BOUNDARY — non-returned chunks stay out."""
        session = db_session
        plan_id = await _get_plan_id(session)

        acc_doc, acc_ver, acc_chunk = uuid4(), uuid4(), uuid4()
        res_doc = uuid4()
        accessible_text = "ACCESSIBLE-ENGINEERING-NOTE"
        restricted_text = "RESTRICTED-SECRET-CONTENT-MARKER"

        stub = _StubRetrievalService(
            [_mk_result(acc_doc, acc_ver, "2.1", acc_chunk, accessible_text)]
        )
        monkeypatch.setattr(vertical_module, "RetrievalService", lambda: stub)
        provider = _ConfigurableProvider(
            sources=[_mk_source(acc_doc, "2.1", acc_chunk)]
        )
        embedding = RecordingEmbeddingProvider()

        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()
        _, role_id = await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome = await execute_workflow(
            session=session,
            provider=provider,
            embedding_provider=embedding,
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()

        assert outcome.final_state == WorkflowState.COMPLETED.value

        # The effective role set reached the retrieval boundary.
        assert all(c["allowed_role_ids"] == {role_id} for c in stub.calls)

        # Restricted identity never appears in the prompt.
        assert str(acc_doc) in provider.prompts[0]
        assert accessible_text in provider.prompts[0]
        assert str(res_doc) not in provider.prompts[0]
        assert restricted_text not in provider.prompts[0]

        # Restricted identity never appears in persisted sources.
        rec = await _get_recommendation(session, run.id)
        assert rec is not None
        persisted = json.dumps(rec.content)
        assert str(acc_doc) in persisted
        assert str(res_doc) not in persisted

        # Restricted identity never appears in workflow-step metadata.
        retrieval_steps = await _get_retrieval_steps(session, run.id)
        assert len(retrieval_steps) == 1
        meta_json = json.dumps(retrieval_steps[0].step_metadata or {})
        assert str(acc_doc) in meta_json
        assert str(res_doc) not in meta_json
        assert restricted_text not in meta_json

    async def test_legitimate_zero_result_completes_ungrounded(
        self,
        _seeded_golden_dataset: None,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """3. LEGITIMATE ZERO RESULT — ungrounded recommendation, not failure."""
        session = db_session
        plan_id = await _get_plan_id(session)

        stub = _StubRetrievalService([])
        monkeypatch.setattr(vertical_module, "RetrievalService", lambda: stub)
        provider = _ConfigurableProvider(sources=[])
        embedding = RecordingEmbeddingProvider()

        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()
        _, role_id = await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome = await execute_workflow(
            session=session,
            provider=provider,
            embedding_provider=embedding,
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()

        # Non-empty effective roles, retrieval returns nothing → success.
        assert outcome.final_state == WorkflowState.COMPLETED.value
        assert len(stub.calls) == 3
        assert all(c["allowed_role_ids"] == {role_id} for c in stub.calls)

        # Provider received empty retrieval context ("[]").
        assert provider.prompts[0].count("Retrieved document context") == 1

        # Recommendation explicitly ungrounded: every sources list empty.
        rec = await _get_recommendation(session, run.id)
        assert rec is not None
        assert rec.content is not None
        assert rec.content["risks"][0]["sources"] == []

        # Retrieval step metadata reports zero results.
        retrieval_steps = await _get_retrieval_steps(session, run.id)
        assert len(retrieval_steps) == 1
        assert retrieval_steps[0].status == "completed"
        assert (retrieval_steps[0].step_metadata or {})["result_count"] == 0

        # Not classified as FAILED_RETRIEVAL.
        run_row = await _get_run(session, run.id)
        assert run_row.state == WorkflowState.COMPLETED.value
        assert run_row.error_code is None

    async def test_retrieval_failure_reaches_failed_retrieval(
        self,
        _seeded_golden_dataset: None,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """4. RETRIEVAL FAILURE — controlled exception → FAILED_RETRIEVAL."""
        session = db_session
        plan_id = await _get_plan_id(session)

        stub = _StubRetrievalService(error=RuntimeError("pgvector exploded"))
        monkeypatch.setattr(vertical_module, "RetrievalService", lambda: stub)
        provider = _ConfigurableProvider()
        embedding = RecordingEmbeddingProvider()

        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()
        await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome = await execute_workflow(
            session=session,
            provider=provider,
            embedding_provider=embedding,
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()

        assert outcome.final_state == WorkflowState.FAILED_RETRIEVAL.value
        assert outcome.success is False

        run_row = await _get_run(session, run.id)
        assert run_row.state == WorkflowState.FAILED_RETRIEVAL.value
        assert run_row.error_code == "RETRIEVAL_FAILED"

        # Exactly one failed retrieval step; no recommendation; no raw error.
        retrieval_steps = await _get_retrieval_steps(session, run.id)
        assert len(retrieval_steps) == 1
        assert retrieval_steps[0].status == "failed"
        assert retrieval_steps[0].error_code == "RETRIEVAL_FAILED"
        assert retrieval_steps[0].error_detail == "RETRIEVAL_FAILED"
        assert "pgvector exploded" not in (
            retrieval_steps[0].error_detail or ""
        )
        assert await _get_recommendation(session, run.id) is None
        # Provider never called (failure precedes prompt construction).
        assert provider.prompts == []

    async def test_embedding_failure_reaches_failed_retrieval(
        self,
        _seeded_golden_dataset: None,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """4b. Embedding failure also maps to FAILED_RETRIEVAL (same boundary)."""
        session = db_session
        plan_id = await _get_plan_id(session)

        stub = _StubRetrievalService([])
        monkeypatch.setattr(vertical_module, "RetrievalService", lambda: stub)
        provider = _ConfigurableProvider()

        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()
        await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome = await execute_workflow(
            session=session,
            provider=provider,
            embedding_provider=_FailingEmbeddingProvider(),
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()

        assert outcome.final_state == WorkflowState.FAILED_RETRIEVAL.value
        run_row = await _get_run(session, run.id)
        assert run_row.error_code == "RETRIEVAL_FAILED"
        assert await _get_recommendation(session, run.id) is None
        assert stub.calls == []  # embedding failed before retrieval

    async def test_empty_authorization_context_fails_closed(
        self,
        _seeded_golden_dataset: None,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """5. EMPTY AUTHORIZATION CONTEXT — fail closed before retrieval."""
        session = db_session
        plan_id = await _get_plan_id(session)

        stub = _StubRetrievalService([])
        monkeypatch.setattr(vertical_module, "RetrievalService", lambda: stub)
        provider = _ConfigurableProvider()
        embedding = RecordingEmbeddingProvider()

        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()

        # Snapshot role differs from the user's current role → empty
        # intersection → effective_role_ids is empty → fail closed.
        snapshot_role = await insert_role(session, f"SNAP-{uuid4().hex[:8]}")
        current_role = await insert_role(session, f"CURR-{uuid4().hex[:8]}")
        user_id = await insert_user(session, f"user-{uuid4().hex[:8]}")
        await link_user_role(session, user_id, current_role)
        await insert_auth_record(
            session,
            run_id=run.id,
            dispatch_generation=0,
            user_id=user_id,
            role_snapshot=[snapshot_role],
            capture_action="start",
        )

        outcome = await execute_workflow(
            session=session,
            provider=provider,
            embedding_provider=embedding,
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()

        assert outcome.final_state == WorkflowState.FAILED_RETRIEVAL.value
        run_row = await _get_run(session, run.id)
        assert run_row.error_code == "RETRIEVAL_FAILED"
        assert run_row.error_detail == "AUTHORIZATION_CONTEXT_EMPTY"

        # Embedding and retrieval were not called; no recommendation.
        assert embedding.calls == []
        assert stub.calls == []
        assert await _get_recommendation(session, run.id) is None

        retrieval_steps = await _get_retrieval_steps(session, run.id)
        assert len(retrieval_steps) == 1
        assert retrieval_steps[0].status == "failed"
        assert retrieval_steps[0].error_detail == "AUTHORIZATION_CONTEXT_EMPTY"

    async def test_fabricated_citation_reaches_failed_validation(
        self,
        _seeded_golden_dataset: None,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """6. FABRICATED CITATION — FAILED_VALIDATION, never FAILED_RETRIEVAL."""
        session = db_session
        plan_id = await _get_plan_id(session)

        allow_doc, allow_ver, allow_chunk = uuid4(), uuid4(), uuid4()
        fake_doc, fake_chunk = uuid4(), uuid4()

        stub = _StubRetrievalService(
            [_mk_result(allow_doc, allow_ver, "2.1", allow_chunk, "real note")]
        )
        monkeypatch.setattr(vertical_module, "RetrievalService", lambda: stub)
        # Provider cites a Source not present in the actual retrieval allow-list.
        provider = _ConfigurableProvider(
            sources=[_mk_source(fake_doc, "9.9", fake_chunk)]
        )
        embedding = RecordingEmbeddingProvider()

        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()
        await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome = await execute_workflow(
            session=session,
            provider=provider,
            embedding_provider=embedding,
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()

        assert outcome.final_state == WorkflowState.FAILED_VALIDATION.value
        run_row = await _get_run(session, run.id)
        assert run_row.state == WorkflowState.FAILED_VALIDATION.value
        assert run_row.error_code == "VALIDATION_FAILED"
        assert run_row.error_detail == "FabricatedCitationError"

        # Fabricated Source is not persisted in a Recommendation.
        assert await _get_recommendation(session, run.id) is None

    async def test_retry_creates_new_authorization_record(
        self,
        _seeded_golden_dataset: None,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """7. RETRY / GENERATION — new auth record, prior record unchanged."""
        session = db_session
        plan_id = await _get_plan_id(session)

        # Generation 0 → retrieval failure → FAILED_RETRIEVAL.
        monkeypatch.setattr(
            vertical_module,
            "RetrievalService",
            lambda: _StubRetrievalService(error=RuntimeError("retrieval down")),
        )
        provider = _ConfigurableProvider()
        engine = WorkflowEngine(provider=provider, session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()
        _, role_0 = await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome0 = await execute_workflow(
            session=session,
            provider=provider,
            embedding_provider=RecordingEmbeddingProvider(),
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()
        assert outcome0.final_state == WorkflowState.FAILED_RETRIEVAL.value
        assert await _get_auth_snapshot(session, run.id, 0) == [str(role_0)]

        # Authorized retry → generation 1.
        await session.refresh(run)
        won = await engine.retry_transition(run)
        await session.commit()
        assert won is True
        assert run.dispatch_generation == 1

        # New generation-specific record with a different role.
        _, role_1 = await seed_authorization_context(
            session,
            run_id=run.id,
            dispatch_generation=1,
            capture_action="retry",
        )

        # A stale prior-generation job cannot mutate the current run.
        stale = await execute_workflow(
            session=session,
            provider=provider,
            embedding_provider=RecordingEmbeddingProvider(),
            run_id=run.id,
            queued_generation=0,
        )
        await session.commit()
        assert stale.final_state == WorkflowState.PENDING.value
        run_row = await _get_run(session, run.id)
        assert run_row.state == WorkflowState.PENDING.value
        assert run_row.dispatch_generation == 1

        # Generation 1 executes, reading the NEW record and re-running retrieval.
        doc_id, version_id, chunk_id = uuid4(), uuid4(), uuid4()
        stub1 = _StubRetrievalService(
            [_mk_result(doc_id, version_id, "2.1", chunk_id, "retry note")]
        )
        monkeypatch.setattr(vertical_module, "RetrievalService", lambda: stub1)
        provider1 = _ConfigurableProvider(
            sources=[_mk_source(doc_id, "2.1", chunk_id)]
        )
        outcome1 = await execute_workflow(
            session=session,
            provider=provider1,
            embedding_provider=RecordingEmbeddingProvider(),
            run_id=run.id,
            queued_generation=1,
        )
        await session.commit()
        assert outcome1.final_state == WorkflowState.COMPLETED.value

        # Retried execution read the NEW generation record (role_1).
        assert len(stub1.calls) == 3
        assert all(c["allowed_role_ids"] == {role_1} for c in stub1.calls)

        # Previous generation record remains unchanged.
        assert await _get_auth_snapshot(session, run.id, 0) == [str(role_0)]
        assert await _get_auth_snapshot(session, run.id, 1) == [str(role_1)]
