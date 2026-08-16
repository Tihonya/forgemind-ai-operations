"""Persistence/idempotency tests for the three new AT-012 workflow steps.

Covers the WP-REC-04-VFY AT-012 complete-trace remediation persistence
contract for the three missing Phase 5 trace items:

- ``user_action``       — emitted exactly once at run creation.
- ``deterministic_calculation`` — emitted once, immutable point-in-time
  snapshot, never duplicated/overwritten on retry.
- ``recommendation``    — emitted once, resolving to the persisted row.

Also verifies the legacy append-on-retry behavior of
``retrieval``/``provider_call``/``validation`` is preserved, that the new
steps carry the correct run_id/correlation_id, that rollback removes
uncommitted steps, and that no new step metadata carries a prompt, raw
payload, secret, or binding hash.

Uses the real ``execute_workflow`` vertical wiring with deterministic fakes
at the external boundaries only (AI provider, embedding, retrieval), against
a live PostgreSQL database seeded with the Golden Dataset.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Generator
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.ai.provider.chat_provider import ChatProvider, ChatResult
from app.ai.provider.exceptions import PermanentChatProviderError
from app.ai.rag.retriever import RetrievalResult
from app.ai.workflow import vertical as vertical_module
from app.ai.workflow.engine import WorkflowEngine
from app.ai.workflow.state_machine import WorkflowState
from app.ai.workflow.vertical import execute_workflow
from app.models.workflow import Recommendation, WorkflowStep
from app.seed.generator.loader import (
    _delete_existing_auth_data,
    _delete_existing_business_data,
    _find_alembic_ini,
    _SessionFactory,
    load_golden_dataset,
)
from tests.integration._workflow_rag_support import (
    RecordingEmbeddingProvider,
    seed_authorization_context,
)

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)

# FK-safe per-test teardown (children before parents). production_plans is
# excluded: the Golden Dataset plan is module-scoped and must persist.
_TRACE_CLEANUP_TABLES = (
    "recommendations",
    "workflow_steps",
    "workflow_authorization_records",
    "workflow_runs",
    "user_roles",
    "users",
    "roles",
)

_SECRET_BEARING_SUBSTRINGS = (
    "apikey",
    "api_key",
    "authorization",
    "password",
    "secret",
    "credential",
    "access_token",
    "refresh_token",
)


@pytest.fixture(scope="module")
def _seeded_golden_dataset() -> Generator[None, None, None]:
    """Migrate to head and seed the Golden Dataset once for this module."""
    from alembic.config import Config

    from alembic import command

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
        for table in _TRACE_CLEANUP_TABLES:
            # Table names come from the module-level allowlist tuple, never
            # from user input.
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

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def retrieve(
        self,
        session: AsyncSession,
        query_embedding: list[float],
        allowed_role_ids: set[UUID],
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        self.calls.append({"allowed_role_ids": set(allowed_role_ids), "top_k": top_k})
        if self.error is not None:
            raise self.error
        return []


class _ConfigurableProvider(ChatProvider):
    """Fake provider returning a valid recommendation or raising."""

    def __init__(self, *, error: Exception | None = None) -> None:
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
                    "summary": "Trace test summary",
                    "business_impact": "Trace test business impact",
                    "recommended_actions": [
                        {
                            "action_type": "CREATE_PROCUREMENT_TASK",
                            "title": "Procure replacement",
                            "rationale": "Shortage detected",
                            "requires_approval": True,
                        }
                    ],
                    "sources": [],
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


async def _get_steps(
    session: AsyncSession, run_id: UUID, step_name: str | None = None
) -> list[WorkflowStep]:
    stmt = select(WorkflowStep).where(WorkflowStep.run_id == run_id)
    if step_name is not None:
        stmt = stmt.where(WorkflowStep.step_name == step_name)
    result = await session.execute(stmt.order_by(WorkflowStep.seq))
    return list(result.scalars().all())


async def _get_recommendation(
    session: AsyncSession, run_id: UUID
) -> Recommendation | None:
    result = await session.execute(
        select(Recommendation).where(Recommendation.run_id == run_id)
    )
    return result.scalar_one_or_none()


async def _run_vertical_to_completion(
    session: AsyncSession,
    run_id: UUID,
    provider: ChatProvider,
    monkeypatch: pytest.MonkeyPatch,
    *,
    generation: int = 0,
) -> Any:
    """Execute the vertical wiring once and return the outcome.

    Binds a deterministic retrieval stub at the external boundary via
    ``monkeypatch`` (string-based attribute access, so mypy does not require
    the symbol to be explicitly re-exported).
    """
    retrieval_stub = _StubRetrievalService()
    monkeypatch.setattr(vertical_module, "RetrievalService", lambda: retrieval_stub)
    outcome = await execute_workflow(
        session=session,
        provider=provider,
        embedding_provider=RecordingEmbeddingProvider(),
        run_id=run_id,
        queued_generation=generation,
    )
    await session.commit()
    return outcome


def _assert_no_secrets_or_prompts(metadata: dict[str, Any] | None) -> None:
    """Recursively assert a metadata dict carries no secret/prompt/payload."""
    if metadata is None:
        return
    for key, value in metadata.items():
        lowered = key.lower()
        assert "prompt" not in lowered, f"prompt-bearing key leaked: {key}"
        assert "payload" not in lowered, f"payload-bearing key leaked: {key}"
        assert "binding" not in lowered, f"binding-bearing key leaked: {key}"
        for fragment in _SECRET_BEARING_SUBSTRINGS:
            assert fragment not in lowered, f"secret-bearing key leaked: {key}"
        if isinstance(value, dict):
            _assert_no_secrets_or_prompts(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    _assert_no_secrets_or_prompts(item)


class TestUserActionStep:
    async def test_create_run_emits_user_action_step_once(
        self, _seeded_golden_dataset: None, db_session: AsyncSession
    ) -> None:
        session = db_session
        plan_id = await _get_plan_id(session)
        engine = WorkflowEngine(provider=_ConfigurableProvider(), session=session)
        run = await engine.create_run(plan_id=plan_id, triggered_by="manager.demo")
        await session.commit()

        steps = await _get_steps(session, run.id, "user_action")
        assert len(steps) == 1
        step = steps[0]
        assert step.seq == 0
        assert step.status == "completed"
        assert step.run_id == run.id
        assert step.correlation_id == run.correlation_id
        assert step.step_metadata == {
            "capture_action": "start",
            "username": "manager.demo",
        }

    async def test_create_run_without_triggered_by_omits_username(
        self, _seeded_golden_dataset: None, db_session: AsyncSession
    ) -> None:
        session = db_session
        plan_id = await _get_plan_id(session)
        engine = WorkflowEngine(provider=_ConfigurableProvider(), session=session)
        run = await engine.create_run(plan_id=plan_id)
        await session.commit()

        steps = await _get_steps(session, run.id, "user_action")
        assert len(steps) == 1
        assert steps[0].step_metadata == {"capture_action": "start"}
        assert "username" not in steps[0].step_metadata

    async def test_rollback_removes_uncommitted_user_action_step(
        self, _seeded_golden_dataset: None, db_session: AsyncSession
    ) -> None:
        session = db_session
        plan_id = await _get_plan_id(session)
        engine = WorkflowEngine(provider=_ConfigurableProvider(), session=session)
        run = await engine.create_run(plan_id=plan_id, triggered_by="manager.demo")
        await session.flush()

        # Uncommitted user_action step must be visible in-session ...
        steps = await _get_steps(session, run.id, "user_action")
        assert len(steps) == 1

        await session.rollback()

        # ... and absent from the database after rollback.
        result = await session.execute(
            text("SELECT COUNT(*) FROM workflow_steps WHERE run_id = :rid"),
            {"rid": run.id},
        )
        assert result.scalar_one() == 0


class TestDeterministicCalculationStep:
    async def test_snapshot_recorded_once_with_immutable_summary(
        self, _seeded_golden_dataset: None, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        session = db_session
        plan_id = await _get_plan_id(session)
        engine = WorkflowEngine(provider=_ConfigurableProvider(), session=session)
        run = await engine.create_run(plan_id=plan_id, triggered_by="manager.demo")
        await session.commit()
        await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome = await _run_vertical_to_completion(
            session, run.id, _ConfigurableProvider(), monkeypatch
        )
        assert outcome.success is True

        steps = await _get_steps(session, run.id, "deterministic_calculation")
        assert len(steps) == 1
        step = steps[0]
        assert step.status == "completed"
        assert step.run_id == run.id
        assert step.correlation_id == run.correlation_id
        metadata = step.step_metadata or {}
        assert metadata["plan_code"] == "PLAN-2026-W31"
        assert metadata["risk_count"] == 3
        assert [r["risk_id"] for r in metadata["risks"]] == [
            "RISK-001",
            "RISK-002",
            "RISK-003",
        ]
        for risk in metadata["risks"]:
            assert set(risk.keys()) == {
                "risk_id",
                "component_code",
                "severity",
                "shortage",
            }
        _assert_no_secrets_or_prompts(metadata)

    async def test_snapshot_unchanged_after_mutable_state_changes(
        self, _seeded_golden_dataset: None, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        session = db_session
        plan_id = await _get_plan_id(session)
        engine = WorkflowEngine(provider=_ConfigurableProvider(), session=session)
        run = await engine.create_run(plan_id=plan_id, triggered_by="manager.demo")
        await session.commit()
        await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome = await _run_vertical_to_completion(
            session, run.id, _ConfigurableProvider(), monkeypatch
        )
        assert outcome.success is True

        steps = await _get_steps(session, run.id, "deterministic_calculation")
        original_metadata = steps[0].step_metadata

        # Mutate a mutable source of the deterministic calculation (on-hand
        # inventory, read by the risk engine) so a live recomputation would
        # diverge from the captured point-in-time result.
        await session.execute(
            text(
                "UPDATE inventory_balances SET quantity_on_hand = quantity_on_hand + 1000 "
                "WHERE id = (SELECT id FROM inventory_balances LIMIT 1)"
            )
        )
        await session.commit()

        # Re-read the persisted snapshot: it must be byte-for-byte the same
        # point-in-time result, never recomputed from the mutated state.
        steps_after = await _get_steps(
            session, run.id, "deterministic_calculation"
        )
        metadata_after = steps_after[0].step_metadata
        assert metadata_after == original_metadata
        assert metadata_after is not None
        assert metadata_after["risk_count"] == 3


class TestRecommendationStep:
    async def test_recommendation_step_recorded_once_and_resolves(
        self, _seeded_golden_dataset: None, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        session = db_session
        plan_id = await _get_plan_id(session)
        engine = WorkflowEngine(provider=_ConfigurableProvider(), session=session)
        run = await engine.create_run(plan_id=plan_id, triggered_by="manager.demo")
        await session.commit()
        await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome = await _run_vertical_to_completion(
            session, run.id, _ConfigurableProvider(), monkeypatch
        )
        assert outcome.success is True

        steps = await _get_steps(session, run.id, "recommendation")
        assert len(steps) == 1
        step = steps[0]
        assert step.status == "completed"
        assert step.run_id == run.id
        assert step.correlation_id == run.correlation_id

        recommendation = await _get_recommendation(session, run.id)
        assert recommendation is not None
        metadata = step.step_metadata or {}
        assert metadata["recommendation_id"] == str(recommendation.id)
        assert metadata["plan_id"] == str(run.plan_id)
        assert metadata["schema_version"] == "1.0"
        assert metadata["status"] == "VALIDATED"
        assert metadata["risk_ids"] == ["RISK-001"]
        assert metadata["action_types"] == ["CREATE_PROCUREMENT_TASK"]
        assert metadata["requires_approval"] is True
        # The full recommendation payload must not be copied into the step.
        assert "content" not in metadata
        _assert_no_secrets_or_prompts(metadata)


class TestRetrySemantics:
    async def test_retry_preserves_single_user_action_and_dc_snapshot(
        self, _seeded_golden_dataset: None, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        session = db_session
        plan_id = await _get_plan_id(session)
        engine = WorkflowEngine(provider=_ConfigurableProvider(), session=session)
        run = await engine.create_run(plan_id=plan_id, triggered_by="manager.demo")
        await session.commit()
        await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        # First attempt fails at the provider (after the DC snapshot).
        outcome = await _run_vertical_to_completion(
            session,
            run.id,
            _ConfigurableProvider(error=PermanentChatProviderError("boom")),
            monkeypatch,
        )
        assert outcome.success is False
        assert outcome.final_state == WorkflowState.FAILED_PROVIDER.value

        dc_before = await _get_steps(session, run.id, "deterministic_calculation")
        assert len(dc_before) == 1

        # Retry: transition back to PENDING and re-run to completion.
        engine = WorkflowEngine(provider=_ConfigurableProvider(), session=session)
        transitioned = await engine.retry_transition(run)
        assert transitioned is True
        await session.commit()
        await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=1, capture_action="retry"
        )

        outcome = await _run_vertical_to_completion(
            session, run.id, _ConfigurableProvider(), monkeypatch, generation=1
        )
        assert outcome.success is True

        user_actions = await _get_steps(session, run.id, "user_action")
        assert len(user_actions) == 1

        dc_after = await _get_steps(session, run.id, "deterministic_calculation")
        assert len(dc_after) == 1
        assert dc_after[0].id == dc_before[0].id
        assert dc_after[0].step_metadata == dc_before[0].step_metadata

        recommendations = await _get_steps(session, run.id, "recommendation")
        assert len(recommendations) == 1

    async def test_retry_preserves_legacy_append_on_retry_behavior(
        self, _seeded_golden_dataset: None, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        session = db_session
        plan_id = await _get_plan_id(session)
        engine = WorkflowEngine(provider=_ConfigurableProvider(), session=session)
        run = await engine.create_run(plan_id=plan_id, triggered_by="manager.demo")
        await session.commit()
        await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=0
        )

        outcome = await _run_vertical_to_completion(
            session,
            run.id,
            _ConfigurableProvider(error=PermanentChatProviderError("boom")),
            monkeypatch,
        )
        assert outcome.success is False

        engine = WorkflowEngine(provider=_ConfigurableProvider(), session=session)
        await engine.retry_transition(run)
        await session.commit()
        await seed_authorization_context(
            session, run_id=run.id, dispatch_generation=1, capture_action="retry"
        )
        outcome = await _run_vertical_to_completion(
            session, run.id, _ConfigurableProvider(), monkeypatch, generation=1
        )
        assert outcome.success is True

        # Legacy retrieval/provider_call append a new attempt per retry.
        retrieval_steps = await _get_steps(session, run.id, "retrieval")
        assert len(retrieval_steps) == 2
        provider_steps = await _get_steps(session, run.id, "provider_call")
        assert len(provider_steps) == 2
        statuses = sorted(s.status for s in provider_steps)
        assert statuses == ["completed", "failed"]

        validation_steps = await _get_steps(session, run.id, "validation")
        assert len(validation_steps) == 1
        assert validation_steps[0].status == "completed"
