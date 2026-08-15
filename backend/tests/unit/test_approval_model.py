"""Unit tests for the approval-request model and action-binding contract.

Verifies the bounded status enum, the database CHECK-constraint/enum
synchronization, the partial-unique-index invariant, the absence of
secret/vendor/financial columns, and the deterministic action-binding
hash. No database required.
"""

from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint

from app.database import Base
from app.models.approval import (
    ACTION_SNAPSHOT_FIELDS,
    ApprovalRequest,
    ApprovalStatus,
    canonical_action_serialization,
    compute_binding_hash,
)


def _snapshot(**overrides: str) -> dict[str, str]:
    base = {
        "action_type": "CREATE_PROCUREMENT_TASK",
        "risk_id": "RISK-001",
        "title": "Procure replacement component",
        "rationale": "Shortage detected by the risk engine",
        "workflow_run_id": "550e8400-e29b-41d4-a716-446655440000",
        "recommendation_id": "550e8400-e29b-41d4-a716-446655440001",
    }
    base.update(overrides)
    return base


class TestApprovalStatus:
    def test_status_values_are_bounded(self) -> None:
        assert {member.value for member in ApprovalStatus} == {
            "PENDING",
            "APPROVED",
            "REJECTED",
        }


class TestApprovalRequestModel:
    def test_table_name_and_registration(self) -> None:
        assert ApprovalRequest.__tablename__ == "approval_requests"
        assert "approval_requests" in Base.metadata.tables

    def test_status_check_constraint_matches_enum(self) -> None:
        table = Base.metadata.tables["approval_requests"]
        check = next(
            c for c in table.constraints if c.name == "ck_approval_requests_status"
        )
        assert isinstance(check, CheckConstraint)
        sql = str(check.sqltext).lower()
        for member in ApprovalStatus:
            assert member.value.lower() in sql

    def test_terminal_fields_check_constraint_exists(self) -> None:
        table = Base.metadata.tables["approval_requests"]
        names = {constraint.name for constraint in table.constraints}
        assert "ck_approval_requests_terminal_fields" in names

    def test_partial_unique_index_for_active_action(self) -> None:
        table = Base.metadata.tables["approval_requests"]
        index = next(
            ix for ix in table.indexes if ix.name == "uq_approval_requests_active_action"
        )
        assert index.unique is True
        assert index.dialect_options["postgresql"]["where"] is not None

    def test_no_secret_vendor_or_financial_columns(self) -> None:
        columns = {col.name for col in ApprovalRequest.__table__.columns}
        forbidden = {
            "vendor",
            "supplier",
            "price",
            "amount",
            "currency",
            "payment",
            "account",
            "bank",
            "prompt",
            "api_key",
            "token",
            "secret",
            "provider",
        }
        assert forbidden.isdisjoint(columns)


class TestBindingHash:
    def test_canonical_serialization_uses_fixed_field_order(self) -> None:
        snapshot = _snapshot()
        expected = "\n".join(f"{field}={snapshot[field]}" for field in ACTION_SNAPSHOT_FIELDS)
        assert canonical_action_serialization(snapshot) == expected

    def test_hash_is_independent_of_insertion_order(self) -> None:
        forward = _snapshot()
        reverse = dict(reversed(list(forward.items())))
        assert compute_binding_hash(reverse) == compute_binding_hash(forward)

    def test_changed_parameter_changes_hash(self) -> None:
        base = _snapshot()
        changed_risk = _snapshot(risk_id="RISK-002")
        changed_title = _snapshot(title="Different title")
        changed_run = _snapshot(
            workflow_run_id="550e8400-e29b-41d4-a716-446655449999"
        )
        assert compute_binding_hash(changed_risk) != compute_binding_hash(base)
        assert compute_binding_hash(changed_title) != compute_binding_hash(base)
        assert compute_binding_hash(changed_run) != compute_binding_hash(base)

    def test_missing_field_fails_closed(self) -> None:
        snapshot = _snapshot()
        del snapshot["risk_id"]
        with pytest.raises(KeyError):
            compute_binding_hash(snapshot)

    def test_hash_is_64_char_lowercase_hex(self) -> None:
        digest = compute_binding_hash(_snapshot())
        assert len(digest) == 64
        assert digest == digest.lower()
        int(digest, 16)  # valid hex
