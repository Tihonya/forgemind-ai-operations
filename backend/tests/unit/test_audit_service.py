"""Unit tests for the audit-event write service (WP-REC-04B).

Covers the pure redaction function, the correlation-ID resolver, the
append-only service surface, and event construction/validation using a
mock ``AsyncSession`` (no live database required).

No secret values are stored or printed: synthetic sentinels only.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.core.context import correlation_context
from app.models.audit import AuditEvent
from app.models.enums import AuditEntityType, AuditEventType
from app.services.audit_service import (
    REDACTED,
    AuditService,
    _is_secret_key,
    _redact_structured_field,
    redact_secrets,
)

# A valid UUID v4 used as a fixed correlation ID throughout.
CORRELATION_ID = "550e8400-e29b-41d4-a716-446655440000"


# ---------------------------------------------------------------------------
# Redaction — pure function
# ---------------------------------------------------------------------------


class TestRedactSecrets:
    def test_redacts_top_level_secret_keys_case_insensitively(self) -> None:
        payload = {
            "api_key": "sk-abc",
            "API_KEY": "sk-def",
            "Authorization": "Bearer xyz",
            "password": "hunter2",
            "secret": "s3cr3t",
        }
        result = redact_secrets(payload)
        assert result == dict.fromkeys(payload, REDACTED)

    def test_redacts_nested_secret_keys(self) -> None:
        payload = {
            "entity": {"status": "PENDING"},
            "provider": {
                "auth": {"api_key": "sk-123", "client_secret": "cs-456"}
            },
        }
        result = redact_secrets(payload)
        assert result["entity"] == {"status": "PENDING"}
        assert result["provider"]["auth"]["api_key"] == REDACTED
        assert result["provider"]["auth"]["client_secret"] == REDACTED

    def test_redacts_credential_named_container_wholesale(self) -> None:
        # A container named "credentials" is itself secret-bearing and is
        # redacted as a whole (fail-safe: no credential structure survives).
        payload = {"credentials": {"api_key": "sk-1", "client_secret": "cs-2"}}
        result = redact_secrets(payload)
        assert result == {"credentials": REDACTED}

    def test_redacts_secret_keys_inside_lists(self) -> None:
        payload = {
            "items": [
                {"name": "ok", "token": "t-1"},
                {"name": "ok2", "access_token": "t-2"},
            ]
        }
        result = redact_secrets(payload)
        assert result["items"][0] == {"name": "ok", "token": REDACTED}
        assert result["items"][1] == {"name": "ok2", "access_token": REDACTED}

    def test_does_not_mutate_caller_mapping(self) -> None:
        payload = {"api_key": "sk-secret-value", "nested": {"password": "p"}}
        snapshot = {"api_key": "sk-secret-value", "nested": {"password": "p"}}
        redact_secrets(payload)
        assert payload == snapshot
        assert payload["api_key"] == "sk-secret-value"

    def test_rejects_non_string_keys(self) -> None:
        with pytest.raises(TypeError):
            redact_secrets({1: "value"})


class TestSecretKeyClassification:
    @pytest.mark.parametrize(
        "key",
        [
            "api_key",
            "API_KEY",
            "Api-Key",
            "apiKey",
            "authorization",
            "Authorization",
            "token",
            "access_token",
            "refresh_token",
            "password",
            "secret",
            "client_secret",
            "groq_api_key",
            "openrouter_api_key",
            "api_credential",
            "bearer_token",
        ],
    )
    def test_secret_bearing_keys_detected(self, key: str) -> None:
        assert _is_secret_key(key) is True

    @pytest.mark.parametrize(
        "key",
        [
            "client_id",
            "status",
            "action_type",
            "quantity",
            "component_id",
            "token_usage",
            "token_count",
        ],
    )
    def test_non_secret_keys_not_detected(self, key: str) -> None:
        assert _is_secret_key(key) is False


class TestRedactStructuredField:
    def test_none_returns_none(self) -> None:
        assert _redact_structured_field(None, "metadata") is None

    def test_non_dict_raises(self) -> None:
        with pytest.raises(TypeError):
            _redact_structured_field(["not", "a", "dict"], "metadata")

    def test_dict_is_redacted_and_caller_unchanged(self) -> None:
        original = {"api_key": "sk-1", "ok": "v"}
        result = _redact_structured_field(original, "metadata")
        assert result == {"api_key": REDACTED, "ok": "v"}
        assert original == {"api_key": "sk-1", "ok": "v"}


# ---------------------------------------------------------------------------
# Correlation-ID resolution
# ---------------------------------------------------------------------------


class TestResolveCorrelationId:
    def test_explicit_valid_id_used(self) -> None:
        assert AuditService._resolve_correlation_id(CORRELATION_ID) == UUID(
            CORRELATION_ID
        )

    def test_explicit_uuid_object_used(self) -> None:
        value = uuid4()
        assert AuditService._resolve_correlation_id(value) == value

    def test_falls_back_to_bound_context(self) -> None:
        with correlation_context(CORRELATION_ID):
            assert AuditService._resolve_correlation_id(None) == UUID(CORRELATION_ID)

    def test_generates_when_none(self) -> None:
        result = AuditService._resolve_correlation_id(None)
        assert isinstance(result, UUID)
        assert result.version == 4

    def test_invalid_id_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            AuditService._resolve_correlation_id("not-a-uuid")


# ---------------------------------------------------------------------------
# Append-only service surface
# ---------------------------------------------------------------------------


class TestAppendOnlySurface:
    def test_service_exposes_only_create_event(self) -> None:
        public = {name for name in dir(AuditService) if not name.startswith("_")}
        assert public == {"create_event"}

    def test_create_event_has_no_timestamp_or_actor_body_parameter(self) -> None:
        import inspect

        params = inspect.signature(AuditService.create_event).parameters
        assert "created_at" not in params
        assert "timestamp" not in params


# ---------------------------------------------------------------------------
# Event creation (mock session)
# ---------------------------------------------------------------------------


def _make_session() -> MagicMock:
    """Build a mock session with a sync ``add`` and an async ``flush``."""
    session = MagicMock()
    session.flush = AsyncMock()
    return session


class TestCreateEvent:
    async def test_persists_all_required_safe_fields(self) -> None:
        session = _make_session()
        service = AuditService(session)
        actor_id = uuid4()
        entity_id = uuid4()
        run_id = uuid4()

        event = await service.create_event(
            event_type=AuditEventType.APPROVAL_APPROVED,
            entity_type=AuditEntityType.APPROVAL_REQUEST,
            entity_id=entity_id,
            actor_id=actor_id,
            actor_username="procurement.demo",
            correlation_id=CORRELATION_ID,
            workflow_run_id=run_id,
            risk_id="RISK-001",
            before_summary={"status": "PENDING"},
            after_summary={"status": "APPROVED"},
            metadata={"action_type": "CREATE_PROCUREMENT_TASK"},
        )

        session.add.assert_called_once()
        session.flush.assert_awaited_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, AuditEvent)
        assert added.event_type == "APPROVAL_APPROVED"
        assert added.entity_type == "APPROVAL_REQUEST"
        assert added.entity_id == entity_id
        assert added.actor_id == actor_id
        assert added.actor_username == "procurement.demo"
        assert added.correlation_id == UUID(CORRELATION_ID)
        assert added.workflow_run_id == run_id
        assert added.risk_id == "RISK-001"
        assert added.before_summary == {"status": "PENDING"}
        assert added.after_summary == {"status": "APPROVED"}
        assert added.event_metadata == {"action_type": "CREATE_PROCUREMENT_TASK"}
        assert event is added

    async def test_redacts_secrets_in_structured_fields(self) -> None:
        session = _make_session()
        service = AuditService(session)
        await service.create_event(
            event_type=AuditEventType.APPROVAL_REJECTED,
            entity_type=AuditEntityType.APPROVAL_REQUEST,
            entity_id=uuid4(),
            before_summary={"status": "PENDING", "api_key": "sk-1"},
            after_summary={"status": "REJECTED"},
            metadata={"reason": "bad", "refresh_token": "rt-1"},
        )
        added = session.add.call_args[0][0]
        assert added.before_summary == {"status": "PENDING", "api_key": REDACTED}
        assert added.event_metadata == {"reason": "bad", "refresh_token": REDACTED}

    async def test_caller_mappings_are_not_mutated(self) -> None:
        session = _make_session()
        service = AuditService(session)
        before = {"api_key": "sk-original"}
        after = {"password": "p-original"}
        await service.create_event(
            event_type=AuditEventType.PROCUREMENT_TASK_CREATED,
            entity_type=AuditEntityType.PROCUREMENT_TASK,
            entity_id=uuid4(),
            before_summary=before,
            after_summary=after,
        )
        assert before == {"api_key": "sk-original"}
        assert after == {"password": "p-original"}

    async def test_invalid_event_type_fails_before_add(self) -> None:
        session = _make_session()
        service = AuditService(session)
        with pytest.raises(ValueError):
            await service.create_event(
                event_type="NOT_A_REAL_TYPE",  # type: ignore[arg-type]
                entity_type=AuditEntityType.APPROVAL_REQUEST,
                entity_id=uuid4(),
            )
        session.add.assert_not_called()

    async def test_invalid_entity_type_fails_before_add(self) -> None:
        session = _make_session()
        service = AuditService(session)
        with pytest.raises(ValueError):
            await service.create_event(
                event_type=AuditEventType.APPROVAL_APPROVED,
                entity_type="NOT_A_REAL_ENTITY",  # type: ignore[arg-type]
                entity_id=uuid4(),
            )
        session.add.assert_not_called()

    async def test_invalid_correlation_id_fails_before_add(self) -> None:
        session = _make_session()
        service = AuditService(session)
        with pytest.raises(ValueError):
            await service.create_event(
                event_type=AuditEventType.APPROVAL_APPROVED,
                entity_type=AuditEntityType.APPROVAL_REQUEST,
                entity_id=uuid4(),
                correlation_id="bad-correlation",
            )
        session.add.assert_not_called()

    async def test_non_dict_metadata_fails_before_add(self) -> None:
        session = _make_session()
        service = AuditService(session)
        with pytest.raises(TypeError):
            await service.create_event(
                event_type=AuditEventType.APPROVAL_APPROVED,
                entity_type=AuditEntityType.APPROVAL_REQUEST,
                entity_id=uuid4(),
                metadata=["not", "a", "dict"],  # type: ignore[arg-type]
            )
        session.add.assert_not_called()
