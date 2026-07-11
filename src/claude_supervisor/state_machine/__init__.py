"""State machine subsystem: explicit states and validated transitions."""

from __future__ import annotations

from claude_supervisor.state_machine.machine import (
    InvalidTransitionError,
    StateMachine,
    Transition,
    TransitionObserver,
)
from claude_supervisor.state_machine.states import State

__all__ = [
    "InvalidTransitionError",
    "State",
    "StateMachine",
    "Transition",
    "TransitionObserver",
]
