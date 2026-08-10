"""Unit tests for the structured-output validator (WP-REC-03C).

Tests cover:
- Valid JSON with valid schema returns the typed model
- Malformed JSON produces the validator-level exception
- Valid JSON with invalid schema produces the same exception type with
  a different safe classification
- Missing required fields rejected
- Extra fields rejected
- Raw response content is absent from exception text
- Validation metadata is sanitized and bounded (no input-controlled
  field names, capped detail lists, full error_count retained)
- Validation performs no persistence
- Validation performs no state transition
- Validation creates no write action
- Existing state-machine contract independently permits
  AWAITING_VALIDATION → FAILED_VALIDATION
- Invalid transitions remain rejected by the existing state machine
- Prompt template interpolation injects runtime values correctly

The absence of side effects (no persistence, no state transition, no
write action) follows from the validator's pure design: it imports only
the Pydantic schema, the standard library, and the structured logger.
No database, ORM, ARQ, or workflow-engine code is imported. These tests
verify that design contract rather than mocking databases.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.ai.workflow.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT_TEMPLATE,
    build_system_prompt,
)
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
        """FAILED_VALIDATION is a terminal state for ordinary execution.

        WP-REC-03F D1 adds FAILED_VALIDATION → PENDING as a user-initiated
        retry transition. The state remains terminal for ordinary execution
        and polling (TERMINAL_STATES unchanged), but gains an outgoing
        transition for authorized retry.
        """
        from app.ai.workflow.state_machine import (
            TERMINAL_STATES,
            get_allowed_transitions,
        )

        assert WorkflowState.FAILED_VALIDATION in TERMINAL_STATES
        # D1: FAILED_VALIDATION → PENDING is now an allowed retry transition.
        allowed = get_allowed_transitions(WorkflowState.FAILED_VALIDATION)
        assert WorkflowState.PENDING in allowed

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


class TestMetadataSanitizationAndBounds:
    """Verify that validation metadata is sanitized and bounded.

    Finding 2 regression tests: input-controlled field names must not
    appear in field_locations, exception text, or logs. Detail lists
    must be capped. The total error_count must remain uncapped.
    """

    def test_secret_in_extra_field_value_absent_from_exception(self) -> None:
        """A secret placed in an extra-field value must not leak."""
        data = json.loads(_valid_recommendation_json())
        data["SECRET_EXTRA_FIELD"] = "SECRET_VALUE_789"
        raw = json.dumps(data)
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(raw)
        exc_str = str(exc_info.value)
        assert "SECRET_VALUE_789" not in exc_str

    def test_secret_in_extra_field_name_absent_from_field_locations(self) -> None:
        """A secret placed in an extra-field name must not appear in field_locations."""
        raw = json.dumps({
            "schema_version": "1.0",
            "SECRET_API_KEY_NAME": "value",
        })
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(raw)
        for loc in exc_info.value.field_locations:
            assert "SECRET_API_KEY_NAME" not in loc
        exc_str = str(exc_info.value)
        assert "SECRET_API_KEY_NAME" not in exc_str

    def test_unknown_location_component_replaced_by_marker(self) -> None:
        """Unknown location components are replaced with <extra>."""
        raw = json.dumps({
            "schema_version": "1.0",
            "unknown_field": "value",
        })
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(raw)
        for loc in exc_info.value.field_locations:
            assert "unknown_field" not in loc
        # Each unknown component should be <extra> or contain only known names
        for loc in exc_info.value.field_locations:
            for component in loc.split("."):
                allowed = {
                    "<extra>",
                    "schema_version",
                    "risks",
                    "run_id",
                    "plan_id",
                }
                assert component in allowed or component.isdigit()

    def test_detail_lists_never_exceed_cap(self) -> None:
        """field_locations and error_types never exceed the documented cap."""
        # Build a payload with many extra fields to generate many errors.
        data: dict[str, object] = {
            "schema_version": "1.0",
            "run_id": _RUN_ID,
            "plan_id": "PLAN-2026-W31",
            "risks": [],
        }
        for i in range(50):
            data[f"extra_field_{i}"] = "value"
        raw = json.dumps(data)
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(raw)
        assert len(exc_info.value.field_locations) <= 20
        assert len(exc_info.value.error_types) <= 20

    def test_total_error_count_reports_full_number(self) -> None:
        """error_count reports the full number of errors, not the capped count."""
        data: dict[str, object] = {
            "schema_version": "1.0",
            "run_id": _RUN_ID,
            "plan_id": "PLAN-2026-W31",
            "risks": [],
        }
        for i in range(30):
            data[f"extra_field_{i}"] = "value"
        raw = json.dumps(data)
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(raw)
        # error_count should be >= 30 (at least 30 extra_forbidden errors)
        assert exc_info.value.error_count >= 30

    def test_long_field_name_cannot_enlarge_output(self) -> None:
        """Very long input-controlled field names are replaced by marker."""
        long_name = "A" * 200
        raw = json.dumps({
            "schema_version": "1.0",
            long_name: "value",
        })
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(raw)
        exc_str = str(exc_info.value)
        assert long_name not in exc_str
        for loc in exc_info.value.field_locations:
            assert long_name not in loc

    def test_known_paths_remain_useful_after_sanitization(self) -> None:
        """Normal known paths such as risks.0.sources remain useful."""
        data = json.loads(_valid_recommendation_json())
        del data["risks"][0]["sources"]
        with pytest.raises(StructuredOutputValidationError) as exc_info:
            validate_structured_output(json.dumps(data))
        # At least one location should contain the known path
        locs_str = " ".join(exc_info.value.field_locations)
        assert "risks" in locs_str
        assert "sources" in locs_str


class TestPromptInterpolation:
    """Verify that build_system_prompt injects runtime values correctly.

    Finding 1 regression tests: the returned prompt must contain the
    supplied values, not literal {plan_id}, {run_id}, or {risk_data}
    placeholders. Literal JSON example braces must be rendered as
    single braces. Repeated calls must not mutate the template constant.
    """

    def test_plan_id_appears_in_built_prompt(self) -> None:
        prompt = build_system_prompt(
            plan_id="PLAN-2026-W31",
            run_id="test-run-id",
            risk_data="{}",
        )
        assert "PLAN-2026-W31" in prompt

    def test_run_id_appears_in_built_prompt(self) -> None:
        prompt = build_system_prompt(
            plan_id="PLAN-X",
            run_id="abc-123-def-456",
            risk_data="{}",
        )
        assert "abc-123-def-456" in prompt

    def test_risk_data_appears_in_built_prompt(self) -> None:
        risk_data = '{"risks": [{"risk_id": "RISK-001", "severity": "CRITICAL"}]}'
        prompt = build_system_prompt(
            plan_id="PLAN-X",
            run_id="test-run-id",
            risk_data=risk_data,
        )
        assert risk_data in prompt

    def test_unresolved_placeholders_do_not_remain(self) -> None:
        prompt = build_system_prompt(
            plan_id="PLAN-X",
            run_id="test-run-id",
            risk_data="{}",
        )
        assert "{plan_id}" not in prompt
        assert "{run_id}" not in prompt
        assert "{risk_data}" not in prompt

    def test_literal_json_braces_rendered_correctly(self) -> None:
        """Literal JSON example braces survive as single braces."""
        prompt = build_system_prompt(
            plan_id="PLAN-X",
            run_id="test-run-id",
            risk_data="{}",
        )
        # The JSON example structure should contain single braces
        assert '"schema_version": "1.0"' in prompt
        assert '"risks": [' in prompt
        # Double braces should not appear in the output
        assert "{{" not in prompt
        assert "}}" not in prompt

    def test_repeated_calls_do_not_mutate_template(self) -> None:
        """The template constant must not be mutated by repeated calls."""
        original = SYSTEM_PROMPT_TEMPLATE
        build_system_prompt(
            plan_id="FIRST_CALL",
            run_id="first",
            risk_data="{}",
        )
        build_system_prompt(
            plan_id="SECOND_CALL",
            run_id="second",
            risk_data="{}",
        )
        assert original == SYSTEM_PROMPT_TEMPLATE
        # Template should still contain the format fields
        assert "{plan_id}" in SYSTEM_PROMPT_TEMPLATE
        assert "{run_id}" in SYSTEM_PROMPT_TEMPLATE
        assert "{risk_data}" in SYSTEM_PROMPT_TEMPLATE

    def test_prompt_version_is_1_0(self) -> None:
        assert PROMPT_VERSION == "1.0"


class TestSanitizerBounds:
    """Verify explicit bounds on location depth, component size, rendered
    path size, numeric components, and error-type strings (Finding 1).

    These tests exercise the private sanitizer helpers directly to
    verify invariants that the fixed schema may not naturally trigger.
    Testing private helpers is acceptable for sanitizer invariants.
    """

    def test_normal_known_path_unchanged(self) -> None:
        """A normal known path such as risks.0.sources remains unchanged."""
        from app.ai.workflow.schema_validator import _sanitize_field_location

        result = _sanitize_field_location(("risks", 0, "sources"))
        assert result == "risks.0.sources"

    def test_deeply_nested_location_capped_at_max_depth(self) -> None:
        """A synthetic deeply nested location cannot exceed the documented depth."""
        from app.ai.workflow.schema_validator import (
            _MAX_LOC_DEPTH,
            _TRUNCATED_MARKER,
            _sanitize_field_location,
        )

        # Build a location deeper than _MAX_LOC_DEPTH using known field names.
        deep_loc = tuple(["risks"] * (_MAX_LOC_DEPTH + 5))
        result = _sanitize_field_location(deep_loc)
        # The result should contain the truncation marker, not all components.
        assert _TRUNCATED_MARKER in result
        # The number of components should not exceed _MAX_LOC_DEPTH.
        assert len(result.split(".")) <= _MAX_LOC_DEPTH

    def test_oversized_numeric_component_cannot_enlarge_output(self) -> None:
        """An oversized numeric component is bounded."""
        from app.ai.workflow.schema_validator import (
            _MAX_LOC_COMPONENT_LENGTH,
            _UNKNOWN_MARKER,
            _sanitize_location_component,
        )

        # A very large integer whose string representation exceeds the limit.
        huge_int = 10 ** (_MAX_LOC_COMPONENT_LENGTH + 1)
        result = _sanitize_location_component(huge_int)
        assert result == _UNKNOWN_MARKER

    def test_negative_index_neutralized(self) -> None:
        """Negative indices are replaced with the invalid-index marker."""
        from app.ai.workflow.schema_validator import (
            _INVALID_INDEX_MARKER,
            _sanitize_location_component,
        )

        assert _sanitize_location_component(-1) == _INVALID_INDEX_MARKER

    def test_non_integer_numeric_neutralized(self) -> None:
        """Float indices are replaced with the unknown marker."""
        from app.ai.workflow.schema_validator import (
            _UNKNOWN_MARKER,
            _sanitize_location_component,
        )

        assert _sanitize_location_component(1.5) == _UNKNOWN_MARKER

    def test_every_rendered_location_has_deterministic_max_length(self) -> None:
        """Every rendered location string is bounded by _MAX_RENDERED_LOC_LENGTH."""
        from app.ai.workflow.schema_validator import (
            _MAX_RENDERED_LOC_LENGTH,
            _sanitize_field_location,
        )

        # Test with a variety of inputs including long unknown strings.
        test_cases: list[tuple[Any, ...]] = [
            ("risks", 0, "sources"),
            tuple("A" * 40 for _ in range(15)),
            tuple("risks" for _ in range(20)),
            ("risks", 99999999999999999999999999999999999999999999999999),
        ]
        for loc in test_cases:
            result = _sanitize_field_location(loc)
            assert len(result) <= _MAX_RENDERED_LOC_LENGTH, (
                f"Location {loc!r} rendered as {result!r} exceeds max length"
            )

    def test_oversized_error_type_bounded(self) -> None:
        """An oversized or unexpected error-type representation is bounded."""
        from app.ai.workflow.schema_validator import (
            _ERROR_TYPE_OVERFLOW_MARKER,
            _MAX_ERROR_TYPE_LENGTH,
            _sanitize_error_type,
        )

        long_type = "A" * (_MAX_ERROR_TYPE_LENGTH + 1)
        assert _sanitize_error_type(long_type) == _ERROR_TYPE_OVERFLOW_MARKER

    def test_normal_error_type_unchanged(self) -> None:
        """Normal error types pass through unchanged."""
        from app.ai.workflow.schema_validator import _sanitize_error_type

        assert _sanitize_error_type("missing") == "missing"
        assert _sanitize_error_type("extra_forbidden") == "extra_forbidden"

    def test_extra_behavior_remains_intact(self) -> None:
        """Existing <extra> behavior for unknown string components is preserved."""
        from app.ai.workflow.schema_validator import (
            _UNKNOWN_MARKER,
            _sanitize_location_component,
        )

        assert _sanitize_location_component("unknown_field") == _UNKNOWN_MARKER
        assert _sanitize_location_component("SECRET_API_KEY") == _UNKNOWN_MARKER

    def test_true_boolean_neutralized(self) -> None:
        """True is not a valid list index and must be neutralized.

        bool is a subclass of int in Python, so isinstance(True, int)
        is True. The sanitizer must check bool before int to prevent
        True from being returned as the string "True".
        """
        from app.ai.workflow.schema_validator import (
            _UNKNOWN_MARKER,
            _sanitize_location_component,
        )

        assert _sanitize_location_component(True) == _UNKNOWN_MARKER

    def test_false_boolean_neutralized(self) -> None:
        """False is not a valid list index and must be neutralized."""
        from app.ai.workflow.schema_validator import (
            _UNKNOWN_MARKER,
            _sanitize_location_component,
        )

        assert _sanitize_location_component(False) == _UNKNOWN_MARKER

    def test_non_negative_integer_still_accepted_after_bool_fix(self) -> None:
        """Non-negative integer indices remain accepted after the bool fix."""
        from app.ai.workflow.schema_validator import _sanitize_location_component

        assert _sanitize_location_component(0) == "0"
        assert _sanitize_location_component(42) == "42"


class TestStructuredLogCapture:
    """Verify that structured logs are genuinely inspected (Finding 2).

    These tests capture the validator module's logger using unittest.mock
    and inspect the actual keyword arguments passed to the log calls.
    This verifies that raw model output, input-controlled field names,
    and input values cannot enter structured log fields.
    """

    @pytest.fixture
    def mock_logger(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        """Replace the validator module's logger with a Mock.

        Returns the Mock object whose ``call_args`` and ``call_args_list``
        can be inspected to verify the actual structured arguments.
        """
        from unittest.mock import MagicMock

        mock = MagicMock()
        monkeypatch.setattr(
            "app.ai.workflow.schema_validator._logger",
            mock,
        )
        return mock

    def test_secret_in_extra_field_value_absent_from_log_args(
        self,
        mock_logger: Any,
    ) -> None:
        """A secret in an extra-field value is absent from captured log fields."""
        data = json.loads(_valid_recommendation_json())
        data["SECRET_EXTRA_FIELD"] = "SECRET_LOG_VALUE_999"
        with pytest.raises(StructuredOutputValidationError):
            validate_structured_output(json.dumps(data))

        # Inspect all warning calls.
        for call in mock_logger.warning.call_args_list:
            call_str = str(call)
            assert "SECRET_LOG_VALUE_999" not in call_str
            assert "SECRET_EXTRA_FIELD" not in call_str

    def test_secret_in_extra_field_name_absent_from_log_args(
        self,
        mock_logger: Any,
    ) -> None:
        """A secret in an extra-field name is absent from captured log fields."""
        raw = json.dumps({
            "schema_version": "1.0",
            "SECRET_API_KEY_NAME": "value",
        })
        with pytest.raises(StructuredOutputValidationError):
            validate_structured_output(raw)

        for call in mock_logger.warning.call_args_list:
            call_str = str(call)
            assert "SECRET_API_KEY_NAME" not in call_str

    def test_long_field_name_absent_from_and_cannot_enlarge_log(
        self,
        mock_logger: Any,
    ) -> None:
        """A very long field name is absent from and cannot enlarge logged metadata."""
        long_name = "B" * 200
        raw = json.dumps({"schema_version": "1.0", long_name: "value"})
        with pytest.raises(StructuredOutputValidationError):
            validate_structured_output(raw)

        for call in mock_logger.warning.call_args_list:
            call_str = str(call)
            assert long_name not in call_str

    def test_logged_field_locations_obey_cap(
        self,
        mock_logger: Any,
    ) -> None:
        """Logged field_locations obey their cap."""
        data: dict[str, object] = {
            "schema_version": "1.0",
            "run_id": _RUN_ID,
            "plan_id": "PLAN-2026-W31",
            "risks": [],
        }
        for i in range(50):
            data[f"extra_field_{i}"] = "value"
        with pytest.raises(StructuredOutputValidationError):
            validate_structured_output(json.dumps(data))

        for call in mock_logger.warning.call_args_list:
            kwargs = call.kwargs
            if "field_locations" in kwargs:
                assert len(kwargs["field_locations"]) <= 20

    def test_logged_error_types_obey_cap(
        self,
        mock_logger: Any,
    ) -> None:
        """Logged error_types obey their cap."""
        data: dict[str, object] = {
            "schema_version": "1.0",
            "run_id": _RUN_ID,
            "plan_id": "PLAN-2026-W31",
            "risks": [],
        }
        for i in range(50):
            data[f"extra_field_{i}"] = "value"
        with pytest.raises(StructuredOutputValidationError):
            validate_structured_output(json.dumps(data))

        for call in mock_logger.warning.call_args_list:
            kwargs = call.kwargs
            if "error_types" in kwargs:
                assert len(kwargs["error_types"]) <= 20

    def test_logged_error_count_retains_full_count(
        self,
        mock_logger: Any,
    ) -> None:
        """Logged error_count retains the full uncapped count."""
        data: dict[str, object] = {
            "schema_version": "1.0",
            "run_id": _RUN_ID,
            "plan_id": "PLAN-2026-W31",
            "risks": [],
        }
        for i in range(30):
            data[f"extra_field_{i}"] = "value"
        with pytest.raises(StructuredOutputValidationError):
            validate_structured_output(json.dumps(data))

        for call in mock_logger.warning.call_args_list:
            kwargs = call.kwargs
            if "error_count" in kwargs:
                assert kwargs["error_count"] >= 30

    def test_malformed_json_log_contains_only_safe_classification(
        self,
        mock_logger: Any,
    ) -> None:
        """Malformed JSON logging contains only the safe failure classification."""
        with pytest.raises(StructuredOutputValidationError):
            validate_structured_output("{not valid json")

        # Should have exactly one warning call.
        assert mock_logger.warning.call_count == 1
        call = mock_logger.warning.call_args
        kwargs = call.kwargs
        assert kwargs.get("reason") == "INVALID_JSON"
        # No raw content in any argument.
        call_str = str(call)
        assert "not valid json" not in call_str

    def test_success_log_contains_only_permitted_metadata(
        self,
        mock_logger: Any,
    ) -> None:
        """Success logging contains only schema_version and risk_count."""
        validate_structured_output(_valid_recommendation_json())

        assert mock_logger.info.call_count == 1
        call = mock_logger.info.call_args
        kwargs = call.kwargs
        assert "schema_version" in kwargs
        assert "risk_count" in kwargs
        assert kwargs["schema_version"] == "1.0"
        assert kwargs["risk_count"] == 1
        # No raw content in any argument.
        call_str = str(call)
        assert "PLAN-2026-W31" not in call_str
        assert "RISK-001" not in call_str
        assert "Critical shortage" not in call_str

    def test_neither_raw_output_nor_pydantic_details_logged(
        self,
        mock_logger: Any,
    ) -> None:
        """Neither raw model output nor complete Pydantic error details are logged."""
        raw = json.dumps({
            "schema_version": "1.0",
            "run_id": _RUN_ID,
            "plan_id": "PLAN-2026-W31",
            "risks": [],
            "SECRET_FIELD": "SECRET_VALUE_LOG",
        })
        with pytest.raises(StructuredOutputValidationError):
            validate_structured_output(raw)

        for call in mock_logger.warning.call_args_list:
            call_str = str(call)
            assert "SECRET_VALUE_LOG" not in call_str
            assert "SECRET_FIELD" not in call_str
            # Pydantic's raw error details (which may echo input) should
            # not appear in the log call — only sanitized metadata.
            assert "msg=" not in call_str
            assert "input=" not in call_str
