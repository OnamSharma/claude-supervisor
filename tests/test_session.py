"""Tests for the session manager bridge."""

from __future__ import annotations

from datetime import UTC, datetime

from claude_supervisor.core.stats import RunStats
from claude_supervisor.session import SessionManager
from claude_supervisor.state_machine import State, StateMachine
from claude_supervisor.storage import SqliteStorage

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _stats(**overrides: object) -> RunStats:
    stats = RunStats(started_at=START)
    stats.finished_at = START
    for key, value in overrides.items():
        setattr(stats, key, value)
    return stats


def test_begin_creates_session() -> None:
    with SqliteStorage() as storage:
        manager = SessionManager(storage)
        sid = manager.begin(["claude"], started_at=START)
        record = storage.get_session(sid)
        assert record is not None
        assert record.command == ("claude",)


def test_end_persists_stats() -> None:
    with SqliteStorage() as storage:
        manager = SessionManager(storage)
        sid = manager.begin(["claude"], started_at=START)
        manager.end(sid, _stats(completed=True, resumes=2, approvals=1), State.STOPPED)
        record = storage.get_session(sid)
        assert record is not None
        assert record.completed is True
        assert record.resumes == 2
        assert record.final_state == "stopped"


def test_transitions_are_logged_as_events() -> None:
    with SqliteStorage() as storage:
        manager = SessionManager(storage)
        machine = StateMachine()
        sid = manager.begin(["claude"], started_at=START, machine=machine)
        machine.transition(State.RUNNING, "launched")
        machine.transition(State.TASK_COMPLETED, "done")
        events = manager.events(sid)
        assert [e.kind for e in events] == ["transition", "transition"]
        assert "starting -> running: launched" in events[0].detail
        assert "running -> task_completed: done" in events[1].detail


def test_latest_and_recent() -> None:
    with SqliteStorage() as storage:
        manager = SessionManager(storage)
        assert manager.latest() is None
        first = manager.begin(["a"], started_at=START)
        second = manager.begin(["b"], started_at=START)
        latest = manager.latest()
        assert latest is not None and latest.id == second
        assert [s.id for s in manager.recent()] == [second, first]


def test_statistics_delegates_to_storage() -> None:
    with SqliteStorage() as storage:
        manager = SessionManager(storage)
        sid = manager.begin(["claude"], started_at=START)
        stats_in = _stats(completed=True, total_wait_seconds=3600.0, resumes=1)
        manager.end(sid, stats_in, State.STOPPED)
        stats = manager.statistics()
        assert stats.total_sessions == 1
        assert stats.hours_saved == 1.0
