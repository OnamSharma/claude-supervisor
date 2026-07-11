"""Tests for the SQLite storage backend."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from claude_supervisor.storage import SessionRecord, SqliteStorage, Statistics, Storage

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _complete(storage: SqliteStorage, session_id: int, **overrides: object) -> None:
    defaults: dict[str, object] = {
        "finished_at": START + timedelta(seconds=100),
        "final_state": "stopped",
        "completed": True,
        "resumes": 1,
        "approvals": 2,
        "permission_prompts": 3,
        "total_wait_seconds": 3600.0,
        "runtime_seconds": 100.0,
        "stop_reason": "task completed",
        "error": None,
    }
    defaults.update(overrides)
    storage.complete_session(session_id, **defaults)  # type: ignore[arg-type]


def test_sqlite_satisfies_storage_protocol() -> None:
    with SqliteStorage() as storage:
        assert isinstance(storage, Storage)


def test_create_and_get_roundtrip() -> None:
    with SqliteStorage() as storage:
        sid = storage.create_session(command=["claude", "--flag"], started_at=START)
        record = storage.get_session(sid)
        assert isinstance(record, SessionRecord)
        assert record.command == ("claude", "--flag")
        assert record.finished_at is None  # not completed yet
        assert record.completed is False


def test_complete_session_updates_row() -> None:
    with SqliteStorage() as storage:
        sid = storage.create_session(command=["claude"], started_at=START)
        _complete(storage, sid)
        record = storage.get_session(sid)
        assert record is not None
        assert record.completed is True
        assert record.resumes == 1
        assert record.runtime_seconds == 100.0
        assert record.final_state == "stopped"


def test_get_missing_session_returns_none() -> None:
    with SqliteStorage() as storage:
        assert storage.get_session(999) is None


def test_list_sessions_newest_first() -> None:
    with SqliteStorage() as storage:
        first = storage.create_session(command=["a"], started_at=START)
        second = storage.create_session(command=["b"], started_at=START)
        ids = [s.id for s in storage.list_sessions()]
        assert ids == [second, first]
        assert [s.id for s in storage.list_sessions(limit=1)] == [second]


def test_events_are_ordered_oldest_first() -> None:
    with SqliteStorage() as storage:
        sid = storage.create_session(command=["a"], started_at=START)
        storage.add_event(sid, kind="transition", detail="starting -> running", at=START)
        storage.add_event(
            sid, kind="transition", detail="running -> stopped", at=START + timedelta(seconds=5)
        )
        events = storage.list_events(sid)
        assert [e.detail for e in events] == ["starting -> running", "running -> stopped"]


def test_statistics_empty_database() -> None:
    with SqliteStorage() as storage:
        stats = storage.statistics()
        assert stats == Statistics()
        assert stats.average_runtime_seconds == 0.0
        assert stats.hours_saved == 0.0


def test_statistics_aggregate_and_averages() -> None:
    with SqliteStorage() as storage:
        s1 = storage.create_session(command=["a"], started_at=START)
        _complete(storage, s1, runtime_seconds=100.0, total_wait_seconds=3600.0, resumes=1)
        s2 = storage.create_session(command=["b"], started_at=START)
        _complete(
            storage,
            s2,
            runtime_seconds=300.0,
            total_wait_seconds=7200.0,
            resumes=1,
            completed=False,
        )
        stats = storage.statistics()
        assert stats.total_sessions == 2
        assert stats.completed_sessions == 1
        assert stats.resumes == 2
        assert stats.total_runtime_seconds == 400.0
        assert stats.average_runtime_seconds == 200.0
        assert stats.total_wait_seconds == 10800.0
        assert stats.average_wait_seconds == 5400.0
        assert stats.hours_saved == 3.0


def test_persists_to_disk(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "supervisor.db"
    storage = SqliteStorage(db)
    sid = storage.create_session(command=["claude"], started_at=START)
    storage.close()
    assert db.exists()
    # Reopen and confirm the row survived.
    with SqliteStorage(db) as reopened:
        assert reopened.get_session(sid) is not None


def test_statistics_as_dict_has_derived_fields() -> None:
    with SqliteStorage() as storage:
        data = storage.statistics().as_dict()
        assert "hours_saved" in data
        assert "average_runtime_seconds" in data
