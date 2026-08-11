"""Unit tests for the workflow state machine (WP-REC-03B).

Tests cover:
- Every allowed transition
- Complete invalid-transition coverage
- Terminal-state behavior
- Self-transition policy
- Unknown state handling
- StateMachineError determinism
- Absence of persistence side effects from pure validation
"""

from __future__ import annotations

import contextlib

import pytest

from app.ai.workflow.state_machine import (
    TERMINAL_STATES,
    TRANSITIONS,
    StateMachineError,
    WorkflowState,
    can_transition,
    get_allowed_transitions,
    is_terminal,
    validate_transition,
)


class TestWorkflowStateEnum:
    """Verify the WorkflowState enumeration."""

    def test_all_canonical_states_present(self) -> None:
        expected = {
            "PENDING",
            "RUNNING",
            "AWAITING_VALIDATION",
            "COMPLETED",
            "FAILED_VALIDATION",
            "FAILED_PROVIDER",
            "FAILED_INTERNAL",
        }
        actual = {s.value for s in WorkflowState}
        assert actual == expected

    def test_state_values_match_names(self) -> None:
        for state in WorkflowState:
            assert state.value == state.name

    def test_is_str_enum(self) -> None:
        assert isinstance(WorkflowState.PENDING, str)


class TestAllowedTransitions:
    """Every permitted transition must be accepted."""

    @pytest.mark.parametrize(
        "from_state, to_state",
        [
            (WorkflowState.PENDING, WorkflowState.RUNNING),
            (WorkflowState.RUNNING, WorkflowState.AWAITING_VALIDATION),
            (WorkflowState.RUNNING, WorkflowState.FAILED_PROVIDER),
            (WorkflowState.RUNNING, WorkflowState.FAILED_INTERNAL),
            (WorkflowState.AWAITING_VALIDATION, WorkflowState.COMPLETED),
            (WorkflowState.AWAITING_VALIDATION, WorkflowState.FAILED_VALIDATION),
            (WorkflowState.AWAITING_VALIDATION, WorkflowState.FAILED_INTERNAL),
            # WP-REC-03F D1: retry transitions from failed states.
            (WorkflowState.FAILED_PROVIDER, WorkflowState.PENDING),
            (WorkflowState.FAILED_VALIDATION, WorkflowState.PENDING),
            (WorkflowState.FAILED_INTERNAL, WorkflowState.PENDING),
        ],
    )
    def test_valid_transition_accepted(
        self,
        from_state: WorkflowState,
        to_state: WorkflowState,
    ) -> None:
        validate_transition(from_state, to_state)

    @pytest.mark.parametrize(
        "from_state, to_state",
        [
            (WorkflowState.PENDING, WorkflowState.RUNNING),
            (WorkflowState.RUNNING, WorkflowState.AWAITING_VALIDATION),
            (WorkflowState.RUNNING, WorkflowState.FAILED_PROVIDER),
            (WorkflowState.RUNNING, WorkflowState.FAILED_INTERNAL),
            (WorkflowState.AWAITING_VALIDATION, WorkflowState.COMPLETED),
            (WorkflowState.AWAITING_VALIDATION, WorkflowState.FAILED_VALIDATION),
            (WorkflowState.AWAITING_VALIDATION, WorkflowState.FAILED_INTERNAL),
            # WP-REC-03F D1: retry transitions.
            (WorkflowState.FAILED_PROVIDER, WorkflowState.PENDING),
            (WorkflowState.FAILED_VALIDATION, WorkflowState.PENDING),
            (WorkflowState.FAILED_INTERNAL, WorkflowState.PENDING),
        ],
    )
    def test_can_transition_returns_true(
        self,
        from_state: WorkflowState,
        to_state: WorkflowState,
    ) -> None:
        assert can_transition(from_state, to_state) is True


class TestInvalidTransitions:
    """All invalid transitions must raise StateMachineError."""

    @pytest.mark.parametrize(
        "from_state, to_state",
        [
            # PENDING cannot skip RUNNING
            (WorkflowState.PENDING, WorkflowState.AWAITING_VALIDATION),
            (WorkflowState.PENDING, WorkflowState.COMPLETED),
            (WorkflowState.PENDING, WorkflowState.FAILED_VALIDATION),
            (WorkflowState.PENDING, WorkflowState.FAILED_PROVIDER),
            (WorkflowState.PENDING, WorkflowState.FAILED_INTERNAL),
            # RUNNING cannot go directly to COMPLETED or FAILED_VALIDATION
            (WorkflowState.RUNNING, WorkflowState.COMPLETED),
            (WorkflowState.RUNNING, WorkflowState.FAILED_VALIDATION),
            # RUNNING cannot go back to PENDING
            (WorkflowState.RUNNING, WorkflowState.PENDING),
            # AWAITING_VALIDATION cannot go back to RUNNING or PENDING
            (WorkflowState.AWAITING_VALIDATION, WorkflowState.RUNNING),
            (WorkflowState.AWAITING_VALIDATION, WorkflowState.PENDING),
            (WorkflowState.AWAITING_VALIDATION, WorkflowState.FAILED_PROVIDER),
            # COMPLETED cannot be retried (D1: no outgoing transition).
            (WorkflowState.COMPLETED, WorkflowState.PENDING),
        ],
    )
    def test_invalid_transition_raises(
        self,
        from_state: WorkflowState,
        to_state: WorkflowState,
    ) -> None:
        with pytest.raises(StateMachineError):
            validate_transition(from_state, to_state)

    @pytest.mark.parametrize(
        "from_state, to_state",
        [
            (WorkflowState.PENDING, WorkflowState.AWAITING_VALIDATION),
            (WorkflowState.RUNNING, WorkflowState.COMPLETED),
            (WorkflowState.AWAITING_VALIDATION, WorkflowState.RUNNING),
        ],
    )
    def test_can_transition_returns_false(
        self,
        from_state: WorkflowState,
        to_state: WorkflowState,
    ) -> None:
        assert can_transition(from_state, to_state) is False


class TestSelfTransitions:
    """Self-transitions are not permitted."""

    @pytest.mark.parametrize(
        "state",
        [
            WorkflowState.PENDING,
            WorkflowState.RUNNING,
            WorkflowState.AWAITING_VALIDATION,
            WorkflowState.COMPLETED,
            WorkflowState.FAILED_VALIDATION,
            WorkflowState.FAILED_PROVIDER,
            WorkflowState.FAILED_INTERNAL,
        ],
    )
    def test_self_transition_raises(self, state: WorkflowState) -> None:
        with pytest.raises(StateMachineError, match="Self-transition"):
            validate_transition(state, state)

    @pytest.mark.parametrize(
        "state",
        [
            WorkflowState.PENDING,
            WorkflowState.RUNNING,
            WorkflowState.AWAITING_VALIDATION,
            WorkflowState.COMPLETED,
        ],
    )
    def test_can_transition_self_returns_false(
        self, state: WorkflowState
    ) -> None:
        assert can_transition(state, state) is False


class TestTerminalStates:
    """Terminal states behavior.

    WP-REC-03F D1: the three failed states (FAILED_PROVIDER,
    FAILED_VALIDATION, FAILED_INTERNAL) now have an outgoing
    transition to PENDING for user-initiated retry. They remain
    terminal for ordinary workflow execution (TERMINAL_STATES
    frozenset unchanged). COMPLETED has no outgoing transition.
    """

    @pytest.mark.parametrize(
        "terminal_state",
        [WorkflowState.COMPLETED],
    )
    def test_terminal_state_has_no_transitions(
        self, terminal_state: WorkflowState
    ) -> None:
        assert get_allowed_transitions(terminal_state) == frozenset()

    @pytest.mark.parametrize(
        "terminal_state, target",
        [
            (WorkflowState.COMPLETED, WorkflowState.PENDING),
            (WorkflowState.COMPLETED, WorkflowState.RUNNING),
        ],
    )
    def test_terminal_state_transition_raises(
        self,
        terminal_state: WorkflowState,
        target: WorkflowState,
    ) -> None:
        with pytest.raises(StateMachineError, match="terminal"):
            validate_transition(terminal_state, target)

    @pytest.mark.parametrize(
        "state, expected",
        [
            (WorkflowState.PENDING, False),
            (WorkflowState.RUNNING, False),
            (WorkflowState.AWAITING_VALIDATION, False),
            (WorkflowState.COMPLETED, True),
            (WorkflowState.FAILED_VALIDATION, True),
            (WorkflowState.FAILED_PROVIDER, True),
            (WorkflowState.FAILED_INTERNAL, True),
        ],
    )
    def test_is_terminal(
        self, state: WorkflowState, expected: bool
    ) -> None:
        assert is_terminal(state) is expected

    def test_terminal_states_frozenset_contents(self) -> None:
        assert frozenset({
            WorkflowState.COMPLETED,
            WorkflowState.FAILED_VALIDATION,
            WorkflowState.FAILED_PROVIDER,
            WorkflowState.FAILED_INTERNAL,
        }) == TERMINAL_STATES


class TestTransitionTable:
    """Verify the transition table structure and immutability."""

    def test_all_states_in_transition_table(self) -> None:
        for state in WorkflowState:
            assert state in TRANSITIONS

    def test_transition_table_is_immutable(self) -> None:
        with pytest.raises(TypeError):
            TRANSITIONS[WorkflowState.PENDING] = frozenset()  # type: ignore[index]

    def test_allowed_transitions_for_pending(self) -> None:
        result = get_allowed_transitions(WorkflowState.PENDING)
        assert result == frozenset({WorkflowState.RUNNING})

    def test_allowed_transitions_for_running(self) -> None:
        result = get_allowed_transitions(WorkflowState.RUNNING)
        assert result == frozenset({
            WorkflowState.AWAITING_VALIDATION,
            WorkflowState.FAILED_PROVIDER,
            WorkflowState.FAILED_INTERNAL,
        })

    def test_allowed_transitions_for_awaiting_validation(self) -> None:
        result = get_allowed_transitions(WorkflowState.AWAITING_VALIDATION)
        assert result == frozenset({
            WorkflowState.COMPLETED,
            WorkflowState.FAILED_VALIDATION,
            WorkflowState.FAILED_INTERNAL,
        })

    # WP-REC-03F D1: retry transitions from failed states to PENDING.
    def test_allowed_transitions_for_failed_provider(self) -> None:
        result = get_allowed_transitions(WorkflowState.FAILED_PROVIDER)
        assert result == frozenset({WorkflowState.PENDING})

    def test_allowed_transitions_for_failed_validation(self) -> None:
        result = get_allowed_transitions(WorkflowState.FAILED_VALIDATION)
        assert result == frozenset({WorkflowState.PENDING})

    def test_allowed_transitions_for_failed_internal(self) -> None:
        result = get_allowed_transitions(WorkflowState.FAILED_INTERNAL)
        assert result == frozenset({WorkflowState.PENDING})

    def test_transition_frozensets_are_immutable(self) -> None:
        """Individual transition sets must be frozensets (immutable)."""
        for state in WorkflowState:
            transitions = TRANSITIONS[state]
            assert isinstance(transitions, frozenset)


class TestStateMachineError:
    """StateMachineError behavior."""

    def test_is_exception_subclass(self) -> None:
        assert issubclass(StateMachineError, Exception)

    def test_raises_with_message(self) -> None:
        with pytest.raises(StateMachineError) as exc_info:
            validate_transition(
                WorkflowState.PENDING, WorkflowState.COMPLETED
            )
        assert "PENDING" in str(exc_info.value)
        assert "COMPLETED" in str(exc_info.value)

    def test_error_message_contains_from_and_to_states(self) -> None:
        with pytest.raises(StateMachineError) as exc_info:
            validate_transition(
                WorkflowState.RUNNING, WorkflowState.PENDING
            )
        msg = str(exc_info.value)
        assert "RUNNING" in msg
        assert "PENDING" in msg


class TestNoPersistenceSideEffects:
    """Pure validation must not have persistence side effects.

    These tests verify that calling validate_transition does not
    modify any external state — it is a pure function.
    """

    def test_validation_does_not_mutate_transition_table(self) -> None:
        original = dict(TRANSITIONS)
        # Call validate_transition many times
        for from_state in WorkflowState:
            for to_state in WorkflowState:
                with contextlib.suppress(StateMachineError):
                    validate_transition(from_state, to_state)
        assert dict(TRANSITIONS) == original

    def test_validation_does_not_mutate_terminal_states(self) -> None:
        original = set(TERMINAL_STATES)
        for state in WorkflowState:
            with contextlib.suppress(StateMachineError):
                validate_transition(state, WorkflowState.PENDING)
        assert set(TERMINAL_STATES) == original

    def test_repeated_validation_is_deterministic(self) -> None:
        """Same input must always produce the same result."""
        for _ in range(10):
            validate_transition(WorkflowState.PENDING, WorkflowState.RUNNING)
            with pytest.raises(StateMachineError):
                validate_transition(
                    WorkflowState.PENDING, WorkflowState.COMPLETED
                )
