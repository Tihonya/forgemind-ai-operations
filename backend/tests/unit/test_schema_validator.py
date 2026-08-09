"""Unit tests for the structured-output validator (WP-REC-03C).

Tests cover:
- Valid JSON with valid schema returns the typed model
- Malformed JSON produces the validator-level exception
- Valid JSON with invalid schema produces the same exception type with
  a different safe classification
- Missing required fields rejected
- Extra fields rejected
- Raw response content is absent from exception text
- Validation performs no persistence
- Validation performs no state transition
- Validation creates no write action
- Existing state-machine contract independently permits
  AWAITING_VALIDATION → FAILED_VALIDATION
- Invalid transitions remain rejected by the existing state machine

The absence of side effects (no persistence, no state transition, no
write action) follows from the validator's pure design: it imports only
the Pydantic schema, the standard library, and the structured logger.
No database, ORM, ARQ, or workflow-engine code is imported. These tests
verify that design contract rather than mocking databases.
"""

from __future__ import annotations

import json

import pytest

from app.ai.workflow.schema_validator import (
    StructuredOutputValidationError,
    ValidationFailureReason,
    validate_structured_output,
)
from app.ai.workflow.state_machine import (
    StateMachineError,
    WorkflowState,
    can_transition,
    validate_transition,
)
from app.schemas.recommendation import RecommendationData

# Canonical valid UUIDs for test fixtures.
_RUN_ID = "12345678-1234-4000-8000-000000000001"
_CHUNK_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _valid_recommendation_json() -> str:
    """Return a valid recommendation as a JSON string."""
    return json.dumps({
        "schema_version": "1.0",
        "run_id": _RUN_ID,
        "plan_id": "PLAN-2026-W31",
        "risks": [
            {
                "risk_id": "RISK-001",
                "summary": "Critical shortage of CTRL-X4",
                "business_impact": "Production line stoppage",
                "recommended_actions": [
                    {
                        "action_type": "CREATE_PROCUREMENT_TASK",
                        "title": "Emergency procurement",
                        "rationale": "8-unit shortage",
                        "requires_approval": True,
                    },
                ],
                "sources": [
                    {
                        "document_id": "DOC-001",
                        "version": "2.1",
                        "chunk_id": _CHUNK_ID,
                    },
                ],
            },
        ],
    })


class TestValidOutputAccepted:
    """Verify that valid model output is accepted and returns the typed model."""

    def test_valid_json_returns_typed_model(self) -> None:
        result = validate_structured_output(_valid_recommendation_json())
        assert isinstance(result, RecommendationData)
        assert result.schema_version == "1.0"
        assert str(result.run_id) == _RUN_ID
        assert result.plan_id == "PLAN-2026-W31"
        assert len(result.risks) == 1
        assert result.risks[0].risk_id == "RISK-001"

    def test_valid_json_with_empty_sources_accepted(self) -> None:
        """Empty sources are structurally valid."""
        data = json.loads(_valid_recommendation_json())
        data["risks"][0]["sources"] = []
        result = validate_structured_output(json.dumps(data))
        assert isinstance(result, RecommendationData)
        assert result.risks[0].sources == []


class TestMalformedJsonRejected:
    """Verify that malformed JSON produces the validator-level exception."""

    def test_malformed_json_raises_exception(self) -> None:
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output("{not valid json")
        assert exc_info.value.reason == ValidationFailureReason.INVALID_JSON

    def test_empty_string_raises_exception(self) -> None:
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output("")
        assert exc_info.value.reason == ValidationFailureReason.INVALID_JSON

    def test_non_json_string_raises_exception(self) -> None:
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output("This is not JSON at all")
        assert exc_info.value.reason == ValidationFailureReason.INVALID_JSON

    def test_trailing_comma_json_raises_exception(self) -> None:
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output('{"key": "value",}')
        assert exc_info.value.reason == ValidationFailureReason.INVALID_JSON


class TestInvalidSchemaRejected:
    """Verify that valid JSON with invalid schema produces the same exception type."""

    def test_invalid_schema_raises_exception(self) -> None:
        """Valid JSON but wrong structure → INVALID_SCHEMA."""
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output('{"key": "value"}')
        assert exc_info.value.reason == ValidationFailureReason.INVALID_SCHEMA

    def test_missing_required_fields_rejected(self) -> None:
        data = json.loads(_valid_recommendation_json())
        del data["run_id"]
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(json.dumps(data))
        assert exc_info.value.reason == ValidationFailureReason.INVALID_SCHEMA
        assert exc_info.value.error_count > 0

    def test_extra_fields_rejected(self) -> None:
        data = json.loads(_valid_recommendation_json())
        data["unexpected"] = "surprise"
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(json.dumps(data))
        assert exc_info.value.reason == ValidationFailureReason.INVALID_SCHEMA

    def test_unsupported_schema_version_rejected(self) -> None:
        data = json.loads(_valid_recommendation_json())
        data["schema_version"] = "2.0"
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(json.dumps(data))
        assert exc_info.value.reason == ValidationFailureReason.INVALID_SCHEMA

    def test_wrong_type_rejected(self) -> None:
        data = json.loads(_valid_recommendation_json())
        data["run_id"] = "not-a-uuid"
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(json.dumps(data))
        assert exc_info.value.reason == ValidationFailureReason.INVALID_SCHEMA

    def test_empty_risks_rejected(self) -> None:
        data = json.loads(_valid_recommendation_json())
        data["risks"] = []
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(json.dumps(data))
        assert exc_info.value.reason == ValidationFailureReason.INVALID_SCHEMA


class TestRawContentAbsentFromException:
    """Verify that raw model output is absent from exception text."""

    def test_raw_content_not_in_exception_str(self) -> None:
        """Raw input values must not appear in the exception text.

        Field names (locations) are safe metadata and may appear. The
        actual field values from the rejected input must not appear.
        """
        raw = '{"schema_version": "1.0", "secret_field": "LEAKED_DATA_12345"}'
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(raw)
        exc_str = str(exc_info.value)
        assert "LEAKED_DATA_12345" not in exc_str

    def test_raw_json_not_in_exception_message(self) -> None:
        """Raw input values must not appear in the exception message."""
        raw = json.dumps({
            "schema_version": "1.0",
            "run_id": _RUN_ID,
            "plan_id": "PLAN-2026-W31",
            "risks": [],
            "sensitive_data": "MUST_NOT_APPEAR",
        })
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(raw)
        exc_str = str(exc_info.value)
        assert "MUST_NOT_APPEAR" not in exc_str

    def test_field_locations_contain_only_paths(self) -> None:
        """field_locations contain only field paths, not input values."""
        data = json.loads(_valid_recommendation_json())
        data["extra_field"] = "VALUE_TO_HIDE"
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(json.dumps(data))
        for loc in exc_info.value.field_locations:
            assert "VALUE_TO_HIDE" not in loc


class TestNoSideEffects:
    """Verify that the validator has no persistence, state, or write side effects.

    The absence of side effects follows from the validator's pure design:
    it imports only the Pydantic schema, the standard library, and the
    structured logger. No database, ORM, ARQ, or workflow-engine code is
    imported. These tests verify the import-level purity contract.
    """

    def test_validator_module_does_not_import_database(self) -> None:
        """The validator module must not import database or ORM modules."""
        import app.ai.workflow.schema_validator as sv_module

        module_source = open(sv_module.__file__).read()  # noqa: SIM115
        forbidden_imports = [
            "from app.database",
            "from app.models",
            "from sqlalchemy",
            "from app.worker",
            "import arq",
            "from app.ai.workflow.engine",
        ]
        for forbidden in forbidden_imports:
            assert forbidden not in module_source, (
                f"Validator module must not import: {forbidden}"
            )

    def test_validator_does_not_mutate_workflow_state(self) -> None:
        """The validator function does not transition workflow state.

        This is verified by the import-level purity check above: the
        validator does not import the engine or call any transition
        function. A successful validation returns the typed model; it
        does not return a state or call a state machine.
        """
        result = validate_structured_output(_valid_recommendation_json())
        # The result is a RecommendationData, not a state transition.
        assert isinstance(result, RecommendationData)
        # No WorkflowState is imported or returned.
        assert not hasattr(result, "state")

    def test_validator_does_not_create_write_actions(self) -> None:
        """The validator creates no write actions (DEC-005).

        The validator returns a pure data object. No side effects.
        """
        result = validate_structured_output(_valid_recommendation_json())
        # The result is a data object with no persistence path.
        assert not hasattr(result, "save")
        assert not hasattr(result, "commit")
        assert not hasattr(result, "persist")


class TestStateMachineContract:
    """Verify the existing state-machine contract for FAILED_VALIDATION.

    These tests verify the existing pure state-machine contract in
    isolation. WP-REC-03C does not perform or persist the transition —
    it only verifies that the contract exists and permits the transition
    that the future 03F caller will use.
    """

    def test_awaiting_validation_to_failed_validation_permitted(self) -> None:
        """The state machine permits AWAITING_VALIDATION → FAILED_VALIDATION."""
        validate_transition(
            WorkflowState.AWAITING_VALIDATION,
            WorkflowState.FAILED_VALIDATION,
        )

    def test_awaiting_validation_to_failed_validation_can_transition(self) -> None:
        assert can_transition(
            WorkflowState.AWAITING_VALIDATION,
            WorkflowState.FAILED_VALIDATION,
        )

    def test_failed_validation_is_terminal(self) -> None:
        """FAILED_VALIDATION is a terminal state — no outgoing transitions."""
        from app.ai.workflow.state_machine import (
            TERMINAL_STATES,
            get_allowed_transitions,
        )

        assert WorkflowState.FAILED_VALIDATION in TERMINAL_STATES
        assert get_allowed_transitions(WorkflowState.FAILED_VALIDATION) == frozenset()

    def test_invalid_transitions_rejected(self) -> None:
        """Transitions that skip AWAITING_VALIDATION are rejected."""
        # PENDING → FAILED_VALIDATION is not a valid transition.
        with pytest.raises(StateMachineError):
            validate_transition(
                WorkflowState.PENDING,
                WorkflowState.FAILED_VALIDATION,
            )

        # RUNNING → FAILED_VALIDATION is not valid (must go through AWAITING_VALIDATION).
        with pytest.raises(StateMachineError):
            validate_transition(
                WorkflowState.RUNNING,
                WorkflowState.FAILED_VALIDATION,
            )

    def test_terminal_to_failed_validation_rejected(self) -> None:
        """Cannot transition from a terminal state to FAILED_VALIDATION."""
        with pytest.raises(StateMachineError):
            validate_transition(
                WorkflowState.COMPLETED,
                WorkflowState.FAILED_VALIDATION,
            )

        with pytest.raises(StateMachineError):
            validate_transition(
                WorkflowState.FAILED_PROVIDER,
                WorkflowState.FAILED_VALIDATION,
            )
