"""Explicit application-owned workflow state machine (DEC-013, WP-REC-03B).

This module defines the canonical workflow states and a static,
immutable transition table. The state machine is pure Python with no
LangGraph dependency and no persistence side effects. Transition
validation is separated from persistence: :func:`validate_transition`
only checks whether a transition is allowed; the engine is responsible
for persisting the state change.

States (DEC-013):
    PENDING             — run created, not yet executing.
    RUNNING             — execution in progress (provider call active).
    AWAITING_VALIDATION — provider call succeeded, awaiting output
                           validation (validation itself is WP-REC-03C).
    COMPLETED           — run finished successfully.
    FAILED_VALIDATION   — output validation failed (03C owns validation).
    FAILED_PROVIDER     — provider call failed (transient or permanent).
    FAILED_INTERNAL     — internal error or invalid transition.

Terminal states: COMPLETED, FAILED_VALIDATION, FAILED_PROVIDER,
FAILED_INTERNAL. No transitions originate from a terminal state.

Transition table:
    PENDING             → RUNNING
    RUNNING             → AWAITING_VALIDATION
    RUNNING             → FAILED_PROVIDER
    RUNNING             → FAILED_INTERNAL
    AWAITING_VALIDATION → COMPLETED
    AWAITING_VALIDATION → FAILED_VALIDATION
    AWAITING_VALIDATION → FAILED_INTERNAL

Self-transitions are not permitted: transitioning to the same state
raises StateMachineError. This prevents no-op transitions from
appearing in the audit trail.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType


class WorkflowState(StrEnum):
    """Canonical workflow states (DEC-013)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    AWAITING_VALIDATION = "AWAITING_VALIDATION"
    COMPLETED = "COMPLETED"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    FAILED_PROVIDER = "FAILED_PROVIDER"
    FAILED_INTERNAL = "FAILED_INTERNAL"


class StateMachineError(Exception):
    """Raised when an invalid state transition is attempted.

    This exception is raised by the pure transition-validation
    function. It has no persistence side effects. The engine may
    catch this exception and transition the run to FAILED_INTERNAL,
    but that is an engine-level decision, not a state-machine side
    effect.
    """


class TransitionConflictError(StateMachineError):
    """Raised when a conditional UPDATE transition loses a race.

    This indicates that the database row's ``state`` no longer matched
    the expected source state when the conditional ``UPDATE ... WHERE
    state = :expected RETURNING id`` was executed. Another contender
    won the transition race, or the row was modified by a different
    path.

    The ORM instance has been refreshed to reflect the actual database
    state. The caller should NOT retry the same transition without
    re-reading the current state and re-validating.

    This error has no partial persistence side effects: the conditional
    UPDATE either updates exactly one row (success) or zero rows
    (conflict). No partial state is written.
    """


# Terminal states — no outgoing transitions.
TERMINAL_STATES: frozenset[WorkflowState] = frozenset({
    WorkflowState.COMPLETED,
    WorkflowState.FAILED_VALIDATION,
    WorkflowState.FAILED_PROVIDER,
    WorkflowState.FAILED_INTERNAL,
})

# Immutable transition table.
# Maps each source state to the set of states it may transition to.
_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.PENDING: frozenset({WorkflowState.RUNNING}),
    WorkflowState.RUNNING: frozenset({
        WorkflowState.AWAITING_VALIDATION,
        WorkflowState.FAILED_PROVIDER,
        WorkflowState.FAILED_INTERNAL,
    }),
    WorkflowState.AWAITING_VALIDATION: frozenset({
        WorkflowState.COMPLETED,
        WorkflowState.FAILED_VALIDATION,
        WorkflowState.FAILED_INTERNAL,
    }),
    # Terminal states have empty transition sets.
    WorkflowState.COMPLETED: frozenset(),
    WorkflowState.FAILED_VALIDATION: frozenset(),
    WorkflowState.FAILED_PROVIDER: frozenset(),
    WorkflowState.FAILED_INTERNAL: frozenset(),
}

# Public read-only view of the transition table.
TRANSITIONS: MappingProxyType[WorkflowState, frozenset[WorkflowState]] = (
    MappingProxyType(_TRANSITIONS)
)


def validate_transition(
    from_state: WorkflowState,
    to_state: WorkflowState,
) -> None:
    """Validate that a transition from ``from_state`` to ``to_state`` is allowed.

    This is a pure function with no side effects. It does not modify any
    database state, in-memory state, or logging context. The caller is
    responsible for persisting the transition if validation succeeds.

    Args:
        from_state: The current workflow state.
        to_state: The target workflow state.

    Raises:
        StateMachineError: If the transition is not permitted. This
            includes:
            - Self-transitions (from_state == to_state).
            - Transitions from a terminal state.
            - Transitions not in the transition table.
    """
    if from_state == to_state:
        raise StateMachineError(
            f"Self-transition not permitted: {from_state.value} → {to_state.value}"
        )

    allowed = _TRANSITIONS.get(from_state)
    if allowed is None:
        raise StateMachineError(
            f"Unknown source state: {from_state.value!r}"
        )

    if to_state not in allowed:
        if from_state in TERMINAL_STATES:
            raise StateMachineError(
                f"Cannot transition from terminal state "
                f"{from_state.value} → {to_state.value}"
            )
        raise StateMachineError(
            f"Invalid transition: {from_state.value} → {to_state.value}"
        )


def is_terminal(state: WorkflowState) -> bool:
    """Return True if ``state`` is a terminal state."""
    return state in TERMINAL_STATES


def can_transition(
    from_state: WorkflowState,
    to_state: WorkflowState,
) -> bool:
    """Return True if a transition is valid, without raising.

    This is a convenience wrapper around :func:`validate_transition`
    for callers that prefer a boolean result.
    """
    try:
        validate_transition(from_state, to_state)
    except StateMachineError:
        return False
    return True


def get_allowed_transitions(state: WorkflowState) -> frozenset[WorkflowState]:
    """Return the set of states that ``state`` may transition to.

    Returns an empty frozenset for terminal states.
    """
    return _TRANSITIONS.get(state, frozenset())
