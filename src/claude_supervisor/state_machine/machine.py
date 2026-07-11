"""The :class:`StateMachine` that enforces the transition table."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from claude_supervisor.logging import get_logger
from claude_supervisor.state_machine.states import State, allowed_targets, is_valid_transition

_logger = get_logger("state_machine")


class InvalidTransitionError(RuntimeError):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, source: State, target: State) -> None:
        """Build the error, listing the transitions legal from ``source``."""
        legal = ", ".join(sorted(s.value for s in allowed_targets(source))) or "(none)"
        super().__init__(
            f"Illegal transition {source.value} -> {target.value}. "
            f"Allowed from {source.value}: {legal}."
        )
        self.source = source
        self.target = target


@dataclass(frozen=True, slots=True)
class Transition:
    """A record of one state change."""

    source: State
    target: State
    reason: str
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


#: A callback invoked after each successful transition.
type TransitionObserver = Callable[[Transition], None]


class StateMachine:
    """Guards and records the supervisor's lifecycle.

    Observers are notified *after* the state has changed. An observer that raises
    does not corrupt the machine's state or roll back the transition; the error
    is logged and other observers still run.
    """

    def __init__(self, initial: State = State.STARTING) -> None:
        """Start the machine in ``initial`` (``STARTING`` by default)."""
        self._state = initial
        self._history: list[Transition] = []
        self._observers: list[TransitionObserver] = []

    @property
    def state(self) -> State:
        """The current state."""
        return self._state

    @property
    def history(self) -> tuple[Transition, ...]:
        """An immutable view of all transitions so far, oldest first."""
        return tuple(self._history)

    @property
    def is_terminal(self) -> bool:
        """Whether the machine has reached a state with no exits."""
        return not allowed_targets(self._state)

    def add_observer(self, observer: TransitionObserver) -> None:
        """Register a callback fired after each successful transition."""
        self._observers.append(observer)

    def can_transition(self, target: State) -> bool:
        """Return whether transitioning to ``target`` is currently legal."""
        return is_valid_transition(self._state, target)

    def transition(self, target: State, reason: str = "") -> Transition:
        """Transition to ``target``.

        Args:
            target: Desired next state.
            reason: Human-readable justification, recorded in history and logs.

        Returns:
            The recorded :class:`Transition`.

        Raises:
            InvalidTransitionError: If the move is not permitted from the
                current state.
        """
        if not self.can_transition(target):
            raise InvalidTransitionError(self._state, target)

        record = Transition(source=self._state, target=target, reason=reason)
        self._state = target
        self._history.append(record)
        _logger.info(
            "state %s -> %s%s",
            record.source.value,
            record.target.value,
            f" ({reason})" if reason else "",
        )
        self._notify(record)
        return record

    def _notify(self, record: Transition) -> None:
        for observer in self._observers:
            try:
                observer(record)
            except Exception:
                _logger.exception("state transition observer failed")
