"""Unit tests for the approval-request model and action-binding contract.

Verifies the bounded status enum, the database CHECK-constraint/enum
synchronization, the partial-unique-index invariant, the absence of
secret/vendor/financial columns, and the deterministic versioned
action-binding hash (canonical JSON serialization, numeric/UUID
normalization, delimiter-injection resistance, and fail-closed missing
fields). No database required.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from sqlalchemy import CheckConstraint

from app.database import Base
from app.models.approval import (
    ACTION_SNAPSHOT_FIELDS,
    BINDING_VERSION,
    ApprovalRequest,
    ApprovalStatus,
    canonical_action_serialization,
    compute_binding_hash,
)


def _snapshot(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "binding_version": BINDING_VERSION,
        "action_type": "CREATE_PROCUREMENT_TASK",
        "component_code": "CTRL-X4",
        "quantity": "8",
        "risk_id": "RISK-001",
        "workflow_run_id": "550e8400-e29b-41d4-a716-446655440000",
        "recommendation_id": "550e8400-e29b-41d4-a716-446655440001",
        "title": "Procure replacement component",
        "rationale": "Shortage detected by the risk engine",
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
    def test_binding_schema_is_versioned_and_covers_executable_params(self) -> None:
        assert BINDING_VERSION == 1
        assert set(ACTION_SNAPSHOT_FIELDS) == {
            "binding_version",
            "action_type",
            "component_code",
            "quantity",
            "risk_id",
            "workflow_run_id",
            "recommendation_id",
            "title",
            "rationale",
        }
        # Executable parameters are part of the canonical schema.
        assert "component_code" in ACTION_SNAPSHOT_FIELDS
        assert "quantity" in ACTION_SNAPSHOT_FIELDS

    def test_canonical_serialization_is_deterministic_json(self) -> None:
        snapshot = _snapshot()
        serialized = canonical_action_serialization(snapshot)
        parsed = json.loads(serialized)
        assert parsed == {
            "action_type": "CREATE_PROCUREMENT_TASK",
            "binding_version": 1,
            "component_code": "CTRL-X4",
            "quantity": "8",
            "rationale": "Shortage detected by the risk engine",
            "recommendation_id": "550e8400-e29b-41d4-a716-446655440001",
            "risk_id": "RISK-001",
            "title": "Procure replacement component",
            "workflow_run_id": "550e8400-e29b-41d4-a716-446655440000",
        }
        # Deterministic key ordering (sort_keys): re-serializing the same
        # mapping produces byte-identical output.
        assert canonical_action_serialization(snapshot) == serialized

    def test_hash_is_independent_of_insertion_order(self) -> None:
        forward = _snapshot()
        reverse = dict(reversed(list(forward.items())))
        assert compute_binding_hash(reverse) == compute_binding_hash(forward)

    def test_changed_parameter_changes_hash(self) -> None:
        base = _snapshot()
        changed_risk = _snapshot(risk_id="RISK-002")
        changed_component = _snapshot(component_code="MOTOR-M2")
        changed_quantity = _snapshot(quantity="9")
        changed_action = _snapshot(action_type="OTHER_ACTION")
        changed_run = _snapshot(
            workflow_run_id="550e8400-e29b-41d4-a716-446655449999"
        )
        changed_rec = _snapshot(
            recommendation_id="550e8400-e29b-41d4-a716-446655449998"
        )
        assert compute_binding_hash(changed_risk) != compute_binding_hash(base)
        assert compute_binding_hash(changed_component) != compute_binding_hash(base)
        assert compute_binding_hash(changed_quantity) != compute_binding_hash(base)
        assert compute_binding_hash(changed_action) != compute_binding_hash(base)
        assert compute_binding_hash(changed_run) != compute_binding_hash(base)
        assert compute_binding_hash(changed_rec) != compute_binding_hash(base)

    def test_equivalent_decimal_representations_normalize_identically(self) -> None:
        # Contractually equivalent quantity representations must bind to the
        # same hash (Decimal("8"), "8", "8.0", "8.00", int 8).
        equivalents = [
            _snapshot(quantity=Decimal("8")),
            _snapshot(quantity="8"),
            _snapshot(quantity="8.0"),
            _snapshot(quantity="8.00"),
            _snapshot(quantity=Decimal("8.0000")),
            _snapshot(quantity=8),
        ]
        digests = {compute_binding_hash(s) for s in equivalents}
        assert len(digests) == 1
        # A genuinely different quantity produces a different hash.
        assert compute_binding_hash(_snapshot(quantity="8.01")) != next(iter(digests))

    def test_uuid_case_variation_normalizes(self) -> None:
        lower = _snapshot(
            workflow_run_id="550e8400-e29b-41d4-a716-446655440000"
        )
        upper = _snapshot(
            workflow_run_id="550E8400-E29B-41D4-A716-446655440000"
        )
        assert compute_binding_hash(lower) == compute_binding_hash(upper)

    def test_newline_and_delimiter_text_cannot_forge_a_field(self) -> None:
        # A descriptive field embedding a newline + a fake "field=value"
        # fragment must not change the parsed structure, and must not be able
        # to impersonate a distinct snapshot whose real quantity differs.
        forged = _snapshot(
            title='Procure",\n"quantity":"999',
        )
        parsed = json.loads(canonical_action_serialization(forged))
        assert parsed["title"] == 'Procure",\n"quantity":"999'
        assert parsed["quantity"] == "8"  # the real quantity field is unchanged
        assert compute_binding_hash(forged) != compute_binding_hash(_snapshot(quantity="999"))
        # A snapshot whose title contains a literal newline serializes
        # distinctly from one whose title differs only by that newline.
        with_newline = _snapshot(title="Procure\nreplacement")
        without_newline = _snapshot(title="Procurereplacement")
        assert compute_binding_hash(with_newline) != compute_binding_hash(without_newline)

    def test_missing_field_fails_closed(self) -> None:
        snapshot = _snapshot()
        del snapshot["risk_id"]
        with pytest.raises(KeyError):
            compute_binding_hash(snapshot)

    @pytest.mark.parametrize("field", ["component_code", "quantity"])
    def test_missing_executable_field_fails_closed(self, field: str) -> None:
        snapshot = _snapshot()
        del snapshot[field]
        with pytest.raises(KeyError):
            compute_binding_hash(snapshot)

    def test_non_finite_quantity_fails_closed(self) -> None:
        for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")):
            with pytest.raises(ValueError):
                compute_binding_hash(_snapshot(quantity=bad))

    def test_non_numeric_quantity_fails_closed(self) -> None:
        with pytest.raises(ValueError):
            compute_binding_hash(_snapshot(quantity="not-a-number"))

    def test_binding_version_must_be_integer(self) -> None:
        with pytest.raises(ValueError):
            compute_binding_hash(_snapshot(binding_version="1"))
        with pytest.raises(ValueError):
            compute_binding_hash(_snapshot(binding_version=True))

    def test_hash_is_64_char_lowercase_hex(self) -> None:
        digest = compute_binding_hash(_snapshot())
        assert len(digest) == 64
        assert digest == digest.lower()
        int(digest, 16)  # valid hex
