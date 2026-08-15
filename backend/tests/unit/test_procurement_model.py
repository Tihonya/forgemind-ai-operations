"""Unit tests for the procurement-task model (WP-REC-04C).

Verifies the table registration, the bounded ``ProcurementTaskState`` enum,
the database CHECK/UNIQUE constraint definitions, the exactly-one-task-per-
approval invariant, the index set, and the absence of secret/vendor/
financial columns. No database required.
"""

from __future__ import annotations

from sqlalchemy import CheckConstraint, UniqueConstraint

from app.database import Base
from app.models.procurement import ProcurementTask, ProcurementTaskState


class TestProcurementTaskState:
    def test_state_values_are_bounded(self) -> None:
        assert {member.value for member in ProcurementTaskState} == {"CREATED"}


class TestProcurementTaskModel:
    def test_table_name_and_registration(self) -> None:
        assert ProcurementTask.__tablename__ == "procurement_tasks"
        assert "procurement_tasks" in Base.metadata.tables

    def test_columns(self) -> None:
        columns = {col.name for col in ProcurementTask.__table__.columns}
        assert columns == {
            "id",
            "correlation_id",
            "approval_request_id",
            "recommendation_id",
            "workflow_run_id",
            "risk_id",
            "action_type",
            "component_code",
            "quantity",
            "binding_hash",
            "task_state",
            "requested_by",
            "requested_by_username",
            "approved_by",
            "approved_by_username",
            "created_at",
        }

    def test_check_constraints(self) -> None:
        table = Base.metadata.tables["procurement_tasks"]
        names = {c.name for c in table.constraints if isinstance(c, CheckConstraint)}
        assert names == {
            "ck_procurement_tasks_action_type",
            "ck_procurement_tasks_task_state",
            "ck_procurement_tasks_quantity_positive",
        }

    def test_action_type_check_constraint_matches_allow_list(self) -> None:
        table = Base.metadata.tables["procurement_tasks"]
        check = next(
            c for c in table.constraints if c.name == "ck_procurement_tasks_action_type"
        )
        assert isinstance(check, CheckConstraint)
        assert "CREATE_PROCUREMENT_TASK" in str(check.sqltext)

    def test_unique_constraint_one_task_per_approval(self) -> None:
        table = Base.metadata.tables["procurement_tasks"]
        constraint = next(
            c
            for c in table.constraints
            if isinstance(c, UniqueConstraint)
            and c.name == "uq_procurement_tasks_approval_request_id"
        )
        assert [col.name for col in constraint.columns] == ["approval_request_id"]

    def test_indexes(self) -> None:
        table = Base.metadata.tables["procurement_tasks"]
        names = {ix.name for ix in table.indexes}
        assert {
            "idx_procurement_tasks_correlation_id",
            "idx_procurement_tasks_recommendation_id",
            "idx_procurement_tasks_workflow_run_id",
            "idx_procurement_tasks_risk_id",
            "idx_procurement_tasks_requested_by",
            "idx_procurement_tasks_approved_by",
            "idx_procurement_tasks_created_at",
        } <= names

    def test_no_secret_vendor_or_financial_columns(self) -> None:
        columns = {col.name for col in ProcurementTask.__table__.columns}
        forbidden = {
            "vendor",
            "supplier",
            "price",
            "amount",
            "currency",
            "payment",
            "account",
            "bank",
            "erp",
            "prompt",
            "api_key",
            "token",
            "secret",
            "provider",
        }
        assert forbidden.isdisjoint(columns)
