"""Integration tests for the normalized audit-trace API (AT-012 remediation).

Tests ``GET /api/v1/audit-trace/{correlation_id}`` against a live PostgreSQL
database:

- A completed approved run exposes all nine categories exactly once, ordered
  1-9, belonging to one correlation lineage.
- Canonical selection is deterministic when retry produced multiple
  retrieval/provider attempts.
- AUDITOR and AI_ADMINISTRATOR succeed; PRODUCTION_MANAGER,
  PROCUREMENT_SPECIALIST and ENGINEER receive 403; unauthenticated receives
  401; unknown correlation receives an indistinguishable 404.
- The endpoint is read-only (no mutation route).
- Legacy runs return ``complete=false`` with exact ``missing_categories``.
- ``binding_hash`` (all spelling variants) and secret-bearing keys never reach
  the trace response; safe adjacent values and the ``[REDACTED]`` sentinel are
  preserved.
- Existing ``/audit-events`` behavior is unchanged.

The module seeds the Golden Dataset once (for the demo users used by RBAC)
and inserts trace rows directly — the persistence path is covered separately
by ``tests/unit/test_workflow_step_trace.py``.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.main import app
from app.models.audit import AuditEvent
from app.models.enums import AuditEntityType, AuditEventType
from app.models.workflow import WorkflowRun, WorkflowStep
from app.services.audit_service import AuditService

_INTEGRATION_DB_URL = (
    os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
)

pytestmark = pytest.mark.skipif(
    _INTEGRATION_DB_URL is None,
    reason="DATABASE_URL or TEST_DATABASE_URL not set",
)

_DEMO_PASSWORDS = {
    "manager.demo": "ManagerPass123!",
    "procurement.demo": "ProcurementPass123!",
    "engineer.demo": "EngineerPass123!",
    "admin.demo": "AdminPass123!",
    "auditor.demo": "AuditorPass123!",
}

_TRACE_CATEGORY_ORDER = [
    "user_action",
    "deterministic_calculation",
    "retrieval",
    "model_call",
    "structured_validation",
    "recommendation",
    "approval_request",
    "human_decision",
    "write_action",
]


@pytest.fixture(scope="module")
def _seeded_golden_dataset() -> Generator[None, None, None]:
    """Migrate to head and seed the Golden Dataset once for this module."""
    from alembic.config import Config

    from alembic import command
    from app.seed.generator.loader import _find_alembic_ini, load_golden_dataset

    command.upgrade(Config(str(_find_alembic_ini())), "head")
    load_golden_dataset()
    yield


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
        # FK-safe teardown (children before parents).
        await session.execute(text("DELETE FROM audit_events"))
        await session.execute(text("DELETE FROM recommendations"))
        await session.execute(text("DELETE FROM workflow_steps"))
        await session.execute(text("DELETE FROM workflow_runs"))
        await session.commit()
    await engine.dispose()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def _login(client: AsyncClient, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, (
        f"seed login failed: {response.status_code} {response.text}"
    )
    return cast(str, response.json()["access_token"])


async def _get_plan_id(db_session: AsyncSession) -> UUID:
    result = await db_session.execute(
        text("SELECT id FROM production_plans LIMIT 1")
    )
    row = result.fetchone()
    assert row is not None, "no production plans seeded"
    return cast(UUID, row[0])


async def _get_user_id(db_session: AsyncSession, username: str) -> UUID:
    result = await db_session.execute(
        text("SELECT id FROM users WHERE username = :u"), {"u": username}
    )
    row = result.fetchone()
    assert row is not None, f"user not seeded: {username}"
    return cast(UUID, row[0])


async def _create_run(
    db_session: AsyncSession, plan_id: UUID, *, state: str = "COMPLETED"
) -> WorkflowRun:
    run = WorkflowRun(
        id=uuid4(),
        correlation_id=uuid4(),
        state=state,
        plan_id=plan_id,
        triggered_by="manager.demo",
    )
    db_session.add(run)
    await db_session.flush()
    return run


async def _create_step(
    db_session: AsyncSession,
    run: WorkflowRun,
    *,
    seq: int,
    step_name: str,
    status: str = "completed",
    step_metadata: dict[str, Any] | None = None,
) -> WorkflowStep:
    step = WorkflowStep(
        id=uuid4(),
        run_id=run.id,
        correlation_id=run.correlation_id,
        seq=seq,
        step_name=step_name,
        status=status,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        step_metadata=step_metadata,
    )
    db_session.add(step)
    await db_session.flush()
    return step


async def _create_event(
    db_session: AsyncSession,
    *,
    correlation_id: UUID,
    workflow_run_id: UUID | None,
    event_type: AuditEventType,
    entity_type: AuditEntityType,
    actor_id: UUID,
    actor_username: str,
    after_summary: dict[str, Any] | None = None,
) -> AuditEvent:
    service = AuditService(db_session)
    return await service.create_event(
        event_type=event_type,
        entity_type=entity_type,
        entity_id=uuid4(),
        actor_id=actor_id,
        actor_username=actor_username,
        correlation_id=str(correlation_id),
        workflow_run_id=workflow_run_id,
        risk_id="RISK-001",
        before_summary={"status": "PENDING"},
        after_summary=after_summary or {"status": "APPROVED"},
    )


async def _seed_complete_trace(
    db_session: AsyncSession, plan_id: UUID
) -> WorkflowRun:
    """Seed a fully-populated nine-item trace for a COMPLETED approved run."""
    run = await _create_run(db_session, plan_id)
    actor_id = await _get_user_id(db_session, "manager.demo")
    await _create_step(
        db_session, run, seq=0, step_name="user_action",
        step_metadata={"capture_action": "start", "username": "manager.demo"},
    )
    await _create_step(
        db_session, run, seq=1, step_name="deterministic_calculation",
        step_metadata={
            "plan_code": "PLAN-2026-W31",
            "risk_count": 1,
            "risks": [
                {"risk_id": "RISK-001", "component_code": "CTRL-X4",
                 "severity": "CRITICAL", "shortage": "8"},
            ],
        },
    )
    await _create_step(
        db_session, run, seq=2, step_name="retrieval",
        step_metadata={"result_count": 0},
    )
    await _create_step(
        db_session, run, seq=3, step_name="provider_call",
        step_metadata={"provider": "fake"},
    )
    await _create_step(db_session, run, seq=4, step_name="validation")
    await _create_step(
        db_session, run, seq=5, step_name="recommendation",
        step_metadata={
            "recommendation_id": str(uuid4()),
            "plan_id": str(plan_id),
            "schema_version": "1.0",
            "status": "VALIDATED",
            "risk_ids": ["RISK-001"],
            "action_types": ["CREATE_PROCUREMENT_TASK"],
            "requires_approval": True,
        },
    )
    await _create_event(
        db_session,
        correlation_id=run.correlation_id,
        workflow_run_id=run.id,
        event_type=AuditEventType.APPROVAL_REQUEST_CREATED,
        entity_type=AuditEntityType.APPROVAL_REQUEST,
        actor_id=actor_id,
        actor_username="manager.demo",
        after_summary={"status": "PENDING", "action_type": "CREATE_PROCUREMENT_TASK"},
    )
    await _create_event(
        db_session,
        correlation_id=run.correlation_id,
        workflow_run_id=run.id,
        event_type=AuditEventType.APPROVAL_APPROVED,
        entity_type=AuditEntityType.APPROVAL_REQUEST,
        actor_id=actor_id,
        actor_username="procurement.demo",
        after_summary={"status": "APPROVED", "decided_by_username": "procurement.demo"},
    )
    await _create_event(
        db_session,
        correlation_id=run.correlation_id,
        workflow_run_id=run.id,
        event_type=AuditEventType.PROCUREMENT_TASK_CREATED,
        entity_type=AuditEntityType.PROCUREMENT_TASK,
        actor_id=actor_id,
        actor_username="procurement.demo",
        after_summary={
            "quantity": "8",
            "task_state": "CREATED",
            "component_code": "CTRL-X4",
        },
    )
    await db_session.commit()
    return run


async def _seed_legacy_trace(
    db_session: AsyncSession, plan_id: UUID
) -> WorkflowRun:
    """Seed a pre-remediation run: only the three legacy steps, no events."""
    run = await _create_run(db_session, plan_id)
    await _create_step(db_session, run, seq=0, step_name="retrieval")
    await _create_step(db_session, run, seq=1, step_name="provider_call")
    await _create_step(db_session, run, seq=2, step_name="validation")
    await db_session.commit()
    return run


def _assert_no_binding_hash(value: Any) -> None:
    """Recursively assert no binding-hash key (any variant) is present."""
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("_", "").replace("-", "")
            assert normalized != "bindinghash", f"binding hash leaked: {key}"
            _assert_no_binding_hash(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_binding_hash(item)


class TestCompleteTrace:
    async def test_complete_run_exposes_nine_categories_in_order(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _seed_complete_trace(db_session, plan_id)

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            f"/api/v1/audit-trace/{run.correlation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()

        assert data["correlation_id"] == str(run.correlation_id)
        assert data["workflow_run_id"] == str(run.id)
        assert data["triggered_by"] == "manager.demo"
        assert data["final_state"] == "COMPLETED"
        assert data["complete"] is True
        assert data["is_legacy"] is False
        assert data["missing_categories"] == []

        categories = [item["category"] for item in data["items"]]
        assert categories == _TRACE_CATEGORY_ORDER
        orders = [item["category_order"] for item in data["items"]]
        assert orders == list(range(1, 10))

        # Every item belongs to the single correlation lineage.
        for item in data["items"]:
            assert item["source"] in ("workflow_step", "audit_event")
            assert item["occurred_at"] is not None

    async def test_complete_run_has_correct_category_mapping(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _seed_complete_trace(db_session, plan_id)

        token = await _login(client, "admin.demo", _DEMO_PASSWORDS["admin.demo"])
        response = await client.get(
            f"/api/v1/audit-trace/{run.correlation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()

        by_category = {item["category"]: item for item in data["items"]}
        assert by_category["user_action"]["source"] == "workflow_step"
        assert by_category["deterministic_calculation"]["source"] == "workflow_step"
        assert by_category["retrieval"]["source"] == "workflow_step"
        assert by_category["model_call"]["source"] == "workflow_step"
        assert by_category["structured_validation"]["source"] == "workflow_step"
        assert by_category["recommendation"]["source"] == "workflow_step"
        assert by_category["approval_request"]["source"] == "audit_event"
        assert by_category["human_decision"]["source"] == "audit_event"
        assert by_category["write_action"]["source"] == "audit_event"
        assert by_category["write_action"]["entity_type"] == "PROCUREMENT_TASK"
        assert by_category["approval_request"]["entity_type"] == "APPROVAL_REQUEST"
        assert by_category["human_decision"]["actor"] == "procurement.demo"

    async def test_all_items_belong_to_one_correlation_lineage(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _seed_complete_trace(db_session, plan_id)
        # A second, unrelated run must not contribute items.
        other = await _create_run(db_session, plan_id)
        await _create_step(db_session, other, seq=0, step_name="user_action")
        await db_session.commit()

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            f"/api/v1/audit-trace/{run.correlation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 9
        # No item should reference the unrelated run (steps are run-scoped;
        # the unrelated run has no audit events under this correlation).
        categories = {item["category"] for item in data["items"]}
        assert categories == set(_TRACE_CATEGORY_ORDER)


class TestCanonicalSelection:
    async def test_retry_attempts_select_completed_latest_step(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_run(db_session, plan_id)
        actor_id = await _get_user_id(db_session, "manager.demo")

        # First attempt fails at the provider; retry succeeds.
        await _create_step(db_session, run, seq=0, step_name="user_action")
        await _create_step(
            db_session, run, seq=1, step_name="deterministic_calculation",
            step_metadata={"plan_code": "PLAN-2026-W31", "risk_count": 0, "risks": []},
        )
        await _create_step(db_session, run, seq=2, step_name="retrieval", status="failed")
        await _create_step(db_session, run, seq=3, step_name="provider_call", status="failed")
        completed_retrieval = await _create_step(
            db_session, run, seq=4, step_name="retrieval", status="completed"
        )
        completed_provider = await _create_step(
            db_session, run, seq=5, step_name="provider_call", status="completed"
        )
        await _create_step(db_session, run, seq=6, step_name="validation")
        await _create_step(db_session, run, seq=7, step_name="recommendation")

        await _create_event(
            db_session, correlation_id=run.correlation_id, workflow_run_id=run.id,
            event_type=AuditEventType.APPROVAL_REQUEST_CREATED,
            entity_type=AuditEntityType.APPROVAL_REQUEST,
            actor_id=actor_id, actor_username="manager.demo",
        )
        await _create_event(
            db_session, correlation_id=run.correlation_id, workflow_run_id=run.id,
            event_type=AuditEventType.APPROVAL_APPROVED,
            entity_type=AuditEntityType.APPROVAL_REQUEST,
            actor_id=actor_id, actor_username="procurement.demo",
        )
        await _create_event(
            db_session, correlation_id=run.correlation_id, workflow_run_id=run.id,
            event_type=AuditEventType.PROCUREMENT_TASK_CREATED,
            entity_type=AuditEntityType.PROCUREMENT_TASK,
            actor_id=actor_id, actor_username="procurement.demo",
        )
        await db_session.commit()

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            f"/api/v1/audit-trace/{run.correlation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is True
        assert len(data["items"]) == 9

        by_category = {item["category"]: item for item in data["items"]}
        assert by_category["retrieval"]["source_id"] == str(completed_retrieval.id)
        assert by_category["model_call"]["source_id"] == str(completed_provider.id)


class TestAuthorization:
    async def test_auditor_and_admin_succeed(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _seed_complete_trace(db_session, plan_id)

        for username in ("auditor.demo", "admin.demo"):
            token = await _login(client, username, _DEMO_PASSWORDS[username])
            response = await client.get(
                f"/api/v1/audit-trace/{run.correlation_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 200, username

    @pytest.mark.parametrize(
        "username",
        ["manager.demo", "procurement.demo", "engineer.demo"],
    )
    async def test_non_audit_roles_denied(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None, username: str,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _seed_complete_trace(db_session, plan_id)

        token = await _login(client, username, _DEMO_PASSWORDS[username])
        response = await client.get(
            f"/api/v1/audit-trace/{run.correlation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403
        assert response.json()["detail"]["error"] == "insufficient_permissions"

    async def test_unauthenticated_denied(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        response = await client.get(f"/api/v1/audit-trace/{uuid4()}")
        assert response.status_code == 401

    async def test_unknown_correlation_returns_indistinguishable_404(
        self, client: AsyncClient, _seeded_golden_dataset: None,
    ) -> None:
        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            f"/api/v1/audit-trace/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404
        assert response.json()["detail"]["error"] == "audit_trace_not_found"


class TestReadOnly:
    @pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
    async def test_no_mutation_route(
        self, client: AsyncClient, _seeded_golden_dataset: None, method: str,
    ) -> None:
        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        request = getattr(client, method)
        response = await request(
            f"/api/v1/audit-trace/{uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in (404, 405)


class TestLegacyIncomplete:
    async def test_legacy_run_reports_exact_missing_categories(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _seed_legacy_trace(db_session, plan_id)

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            f"/api/v1/audit-trace/{run.correlation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["is_legacy"] is True
        assert data["missing_categories"] == [
            "user_action",
            "deterministic_calculation",
            "recommendation",
            "approval_request",
            "human_decision",
            "write_action",
        ]
        categories = [item["category"] for item in data["items"]]
        assert categories == ["retrieval", "model_call", "structured_validation"]


class TestLegacyClassification:
    async def test_current_incomplete_with_user_action_is_not_legacy(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """A current run carrying the user_action marker is never legacy."""
        plan_id = await _get_plan_id(db_session)
        run = await _create_run(db_session, plan_id, state="FAILED_PROVIDER")
        await _create_step(
            db_session, run, seq=0, step_name="user_action",
            step_metadata={"capture_action": "start", "username": "manager.demo"},
        )
        await db_session.commit()

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            f"/api/v1/audit-trace/{run.correlation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["is_legacy"] is False
        assert data["missing_categories"] == [
            "deterministic_calculation",
            "retrieval",
            "model_call",
            "structured_validation",
            "recommendation",
            "approval_request",
            "human_decision",
            "write_action",
        ]
        # No fabricated item: only the single user_action step is present.
        assert [item["category"] for item in data["items"]] == ["user_action"]

    async def test_current_incomplete_with_deterministic_calculation_is_not_legacy(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        """A current run carrying the deterministic_calculation marker is not legacy."""
        plan_id = await _get_plan_id(db_session)
        run = await _create_run(db_session, plan_id, state="FAILED_PROVIDER")
        await _create_step(
            db_session, run, seq=0, step_name="deterministic_calculation",
            step_metadata={
                "plan_code": "PLAN-2026-W31",
                "risk_count": 1,
                "risks": [{"risk_id": "RISK-001", "component_code": "CTRL-X4",
                           "severity": "CRITICAL", "shortage": "8"}],
            },
        )
        await db_session.commit()

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            f"/api/v1/audit-trace/{run.correlation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["complete"] is False
        assert data["is_legacy"] is False
        assert data["missing_categories"] == [
            "user_action",
            "retrieval",
            "model_call",
            "structured_validation",
            "recommendation",
            "approval_request",
            "human_decision",
            "write_action",
        ]
        assert [item["category"] for item in data["items"]] == [
            "deterministic_calculation"
        ]


class TestRedaction:
    async def test_binding_hash_and_secrets_absent_from_trace(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        plan_id = await _get_plan_id(db_session)
        run = await _create_run(db_session, plan_id)
        actor_id = await _get_user_id(db_session, "manager.demo")
        await _create_event(
            db_session,
            correlation_id=run.correlation_id,
            workflow_run_id=run.id,
            event_type=AuditEventType.PROCUREMENT_TASK_CREATED,
            entity_type=AuditEntityType.PROCUREMENT_TASK,
            actor_id=actor_id,
            actor_username="procurement.demo",
            after_summary={
                "quantity": "8",
                "binding_hash": "top-level-hash",
                "nested": {
                    "bindingHash": "nested-camel-hash",
                    "deeper": {"binding-hash": "nested-kebab-hash"},
                    "safe_adjacent": "keep-me",
                },
                "client_secret": "s3cr3t-value",
            },
        )
        await db_session.commit()

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        response = await client.get(
            f"/api/v1/audit-trace/{run.correlation_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()

        # No item category carries a binding hash at any nesting depth.
        for item in data["items"]:
            _assert_no_binding_hash(item["summary"])

        write_action = next(
            item for item in data["items"] if item["category"] == "write_action"
        )
        summary = write_action["summary"]
        assert summary["quantity"] == "8"
        assert summary["nested"]["safe_adjacent"] == "keep-me"
        assert summary["client_secret"] == "[REDACTED]"
        # binding-hash keys were removed entirely (not merely redacted).
        assert "binding_hash" not in summary
        assert "bindingHash" not in summary["nested"]
        assert "binding-hash" not in summary["nested"]["deeper"]


class TestExistingAuditEventsUnchanged:
    async def test_audit_events_endpoint_still_works(
        self, client: AsyncClient, db_session: AsyncSession,
        _seeded_golden_dataset: None,
    ) -> None:
        actor_id = await _get_user_id(db_session, "manager.demo")
        event = await _create_event(
            db_session,
            correlation_id=uuid4(),
            workflow_run_id=None,
            event_type=AuditEventType.APPROVAL_REQUEST_CREATED,
            entity_type=AuditEntityType.APPROVAL_REQUEST,
            actor_id=actor_id,
            actor_username="manager.demo",
        )
        await db_session.commit()

        token = await _login(client, "auditor.demo", _DEMO_PASSWORDS["auditor.demo"])
        list_response = await client.get(
            "/api/v1/audit-events",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_response.status_code == 200
        assert list_response.json()["limit"] == 50
        assert list_response.json()["offset"] == 0

        detail_response = await client.get(
            f"/api/v1/audit-events/{event.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert detail_response.status_code == 200
        assert detail_response.json()["id"] == str(event.id)
