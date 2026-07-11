"""The supervisor's lifecycle states and the legal transitions between them.

The transition table is the single source of truth for control flow. Encoding
it explicitly (instead of scattering boolean flags) makes the safety rules
auditable -- most importantly: ``TASK_COMPLETED`` can only lead to ``STOPPED``,
so the supervisor can never resume work on its own after a task finishes.
"""

from __future__ import annotations

import enum


class State(enum.StrEnum):
    """A single lifecycle state."""

    STARTING = "starting"
    RUNNING = "running"
    WAITING_FOR_PERMISSION = "waiting_for_permission"
    WAITING_FOR_RESET = "waiting_for_reset"
    RESUMING = "resuming"
    TASK_COMPLETED = "task_completed"
    STOPPED = "stopped"


#: Terminal state with no outgoing transitions.
TERMINAL: frozenset[State] = frozenset({State.STOPPED})

#: Allowed transitions, excluding the universal "-> STOPPED" shutdown edge,
#: which :data:`STOPPABLE_FROM` grants from every non-terminal state.
_ALLOWED: dict[State, frozenset[State]] = {
    State.STARTING: frozenset({State.RUNNING}),
    State.RUNNING: frozenset(
        {
            State.WAITING_FOR_PERMISSION,
            State.WAITING_FOR_RESET,
            State.TASK_COMPLETED,
        }
    ),
    State.WAITING_FOR_PERMISSION: frozenset({State.RUNNING, State.WAITING_FOR_RESET}),
    State.WAITING_FOR_RESET: frozenset({State.RESUMING}),
    State.RESUMING: frozenset({State.RUNNING, State.WAITING_FOR_RESET}),
    # Deliberately NOT -> RUNNING: never continue work automatically once done.
    State.TASK_COMPLETED: frozenset(),
    State.STOPPED: frozenset(),
}

#: Every non-terminal state may be stopped (graceful shutdown, fatal error).
STOPPABLE_FROM: frozenset[State] = frozenset(s for s in State if s not in TERMINAL)


def allowed_targets(state: State) -> frozenset[State]:
    """Return the set of states reachable from ``state`` in one transition."""
    targets = _ALLOWED[state]
    if state in STOPPABLE_FROM:
        return targets | {State.STOPPED}
    return targets


def is_valid_transition(source: State, target: State) -> bool:
    """Return ``True`` if ``source -> target`` is a legal transition."""
    return target in allowed_targets(source)
