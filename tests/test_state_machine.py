"""Tests for the state machine."""

from __future__ import annotations

import pytest

from claude_supervisor.state_machine import (
    InvalidTransitionError,
    State,
    StateMachine,
    Transition,
)
from claude_supervisor.state_machine.states import allowed_targets, is_valid_transition


def test_starts_in_starting_by_default() -> None:
    assert StateMachine().state is State.STARTING


def test_happy_path_full_cycle() -> None:
    sm = StateMachine()
    sm.transition(State.RUNNING, "launched")
    sm.transition(State.WAITING_FOR_RESET, "usage limit")
    sm.transition(State.RESUMING, "reset elapsed")
    sm.transition(State.RUNNING, "resumed")
    sm.transition(State.TASK_COMPLETED, "done")
    sm.transition(State.STOPPED, "shutdown")
    assert sm.state is State.STOPPED
    assert len(sm.history) == 6


def test_permission_wait_returns_to_running() -> None:
    sm = StateMachine(State.RUNNING)
    sm.transition(State.WAITING_FOR_PERMISSION, "prompt")
    sm.transition(State.RUNNING, "answered")
    assert sm.state is State.RUNNING


def test_task_completed_cannot_resume_work() -> None:
    """The core safety guarantee: no automatic work after completion."""
    sm = StateMachine(State.TASK_COMPLETED)
    assert not sm.can_transition(State.RUNNING)
    with pytest.raises(InvalidTransitionError):
        sm.transition(State.RUNNING, "should be illegal")
    # Only STOPPED is reachable.
    assert allowed_targets(State.TASK_COMPLETED) == frozenset({State.STOPPED})


def test_stopped_is_terminal() -> None:
    sm = StateMachine(State.STOPPED)
    assert sm.is_terminal
    assert allowed_targets(State.STOPPED) == frozenset()
    with pytest.raises(InvalidTransitionError):
        sm.transition(State.RUNNING)


def test_any_active_state_can_stop() -> None:
    for state in State:
        if state is State.STOPPED:
            continue
        assert is_valid_transition(state, State.STOPPED)


def test_invalid_transition_message_lists_allowed() -> None:
    sm = StateMachine(State.STARTING)
    with pytest.raises(InvalidTransitionError) as exc:
        sm.transition(State.RESUMING)
    assert "running" in str(exc.value)


def test_history_is_immutable_view() -> None:
    sm = StateMachine()
    sm.transition(State.RUNNING)
    history = sm.history
    assert isinstance(history, tuple)
    assert isinstance(history[0], Transition)
    assert history[0].source is State.STARTING


def test_observer_is_notified() -> None:
    sm = StateMachine()
    seen: list[Transition] = []
    sm.add_observer(seen.append)
    sm.transition(State.RUNNING, "go")
    assert len(seen) == 1
    assert seen[0].target is State.RUNNING
    assert seen[0].reason == "go"


def test_observer_exception_does_not_break_machine() -> None:
    sm = StateMachine()

    def boom(_: Transition) -> None:
        raise RuntimeError("observer failure")

    calm: list[Transition] = []
    sm.add_observer(boom)
    sm.add_observer(calm.append)  # still runs despite the earlier failure
    sm.transition(State.RUNNING)
    assert sm.state is State.RUNNING
    assert len(calm) == 1


def test_resume_can_fall_back_to_waiting() -> None:
    sm = StateMachine(State.RESUMING)
    sm.transition(State.WAITING_FOR_RESET, "resume failed, wait again")
    assert sm.state is State.WAITING_FOR_RESET
