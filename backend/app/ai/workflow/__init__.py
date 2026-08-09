"""Workflow engine package (WP-REC-03B).

Provides the explicit state machine, the WorkflowEngine foundation,
and re-exports the canonical states and transition API.
"""

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

__all__ = [
    "StateMachineError",
    "TERMINAL_STATES",
    "TRANSITIONS",
    "WorkflowState",
    "can_transition",
    "get_allowed_transitions",
    "is_terminal",
    "validate_transition",
]
