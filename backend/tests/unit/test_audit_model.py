"""Unit tests for the audit-event ORM model and event taxonomy (WP-REC-04B).

Verifies the bounded event/entity taxonomy and that the database CHECK
constraints stay in sync with the Python enums. No database required.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint

from app.database import Base
from app.models.audit import AuditEvent
from app.models.enums import AuditEntityType, AuditEventType


class TestEventTaxonomy:
    def test_event_type_taxonomy_is_bounded(self) -> None:
        expected = {
            "APPROVAL_REQUEST_CREATED",
            "APPROVAL_APPROVED",
            "APPROVAL_REJECTED",
            "PROCUREMENT_TASK_CREATION_ATTEMPTED",
            "PROCUREMENT_TASK_CREATED",
            "PROCUREMENT_TASK_CREATION_FAILED",
        }
        assert {member.value for member in AuditEventType} == expected

    def test_entity_type_taxonomy_is_bounded(self) -> None:
        expected = {"APPROVAL_REQUEST", "PROCUREMENT_TASK"}
        assert {member.value for member in AuditEntityType} == expected


class TestAuditEventModel:
    def test_table_name_and_registration(self) -> None:
        assert AuditEvent.__tablename__ == "audit_events"
        assert "audit_events" in Base.metadata.tables

    def test_event_type_check_constraint_matches_enum(self) -> None:
        table = Base.metadata.tables["audit_events"]
        check = next(
            c for c in table.constraints if c.name == "ck_audit_events_event_type"
        )
        assert isinstance(check, CheckConstraint)
        sql = str(check.sqltext).lower()
        for member in AuditEventType:
            assert member.value.lower() in sql

    def test_entity_type_check_constraint_matches_enum(self) -> None:
        table = Base.metadata.tables["audit_events"]
        check = next(
            c for c in table.constraints if c.name == "ck_audit_events_entity_type"
        )
        assert isinstance(check, CheckConstraint)
        sql = str(check.sqltext).lower()
        for member in AuditEntityType:
            assert member.value.lower() in sql

    def test_no_secret_or_financial_columns(self) -> None:
        columns = {col.name for col in AuditEvent.__table__.columns}
        forbidden = {
            "vendor",
            "amount",
            "currency",
            "payment",
            "provider",
            "prompt",
            "secret",
            "api_key",
            "token",
        }
        assert forbidden.isdisjoint(columns)
