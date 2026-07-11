"""SQLite-backed :class:`Storage` implementation."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from types import TracebackType

from claude_supervisor.logging import get_logger
from claude_supervisor.storage.base import (
    EventRecord,
    SessionRecord,
    Statistics,
    StorageError,
)

_logger = get_logger("storage")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    command             TEXT    NOT NULL,
    started_at          TEXT    NOT NULL,
    finished_at         TEXT,
    final_state         TEXT,
    completed           INTEGER NOT NULL DEFAULT 0,
    resumes             INTEGER NOT NULL DEFAULT 0,
    approvals           INTEGER NOT NULL DEFAULT 0,
    permission_prompts  INTEGER NOT NULL DEFAULT 0,
    total_wait_seconds  REAL    NOT NULL DEFAULT 0,
    runtime_seconds     REAL,
    stop_reason         TEXT    NOT NULL DEFAULT '',
    error               TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    at          TEXT    NOT NULL,
    kind        TEXT    NOT NULL,
    detail      TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
"""


class SqliteStorage:
    """Persist sessions and events in a SQLite database.

    The connection is opened once and kept for the life of the instance so that
    an in-memory database (``":memory:"``) works for tests. Use as a context
    manager, or call :meth:`close` when done.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        """Open (or create) the database at ``path`` and ensure the schema."""
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._conn = sqlite3.connect(self._path)
        except sqlite3.Error as exc:  # pragma: no cover - platform/permission dependent
            raise StorageError(f"could not open database {self._path}: {exc}") from exc
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # --- context manager ---------------------------------------------------
    def __enter__(self) -> SqliteStorage:
        """Return self for use in a ``with`` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the connection on exit."""
        self.close()

    def close(self) -> None:
        """Close the underlying connection."""
        self._conn.close()

    # --- writes ------------------------------------------------------------
    def create_session(self, *, command: Sequence[str], started_at: datetime) -> int:
        """Insert a new running session and return its id."""
        cur = self._conn.execute(
            "INSERT INTO sessions (command, started_at) VALUES (?, ?)",
            (json.dumps(list(command)), started_at.isoformat()),
        )
        self._conn.commit()
        session_id = cur.lastrowid
        if session_id is None:  # pragma: no cover - sqlite always returns a rowid here
            raise StorageError("failed to obtain new session id")
        return session_id

    def complete_session(
        self,
        session_id: int,
        *,
        finished_at: datetime,
        final_state: str,
        completed: bool,
        resumes: int,
        approvals: int,
        permission_prompts: int,
        total_wait_seconds: float,
        runtime_seconds: float,
        stop_reason: str,
        error: str | None,
    ) -> None:
        """Finalize a session row with its outcome."""
        self._conn.execute(
            """
            UPDATE sessions SET
                finished_at = ?, final_state = ?, completed = ?, resumes = ?,
                approvals = ?, permission_prompts = ?, total_wait_seconds = ?,
                runtime_seconds = ?, stop_reason = ?, error = ?
            WHERE id = ?
            """,
            (
                finished_at.isoformat(),
                final_state,
                int(completed),
                resumes,
                approvals,
                permission_prompts,
                total_wait_seconds,
                runtime_seconds,
                stop_reason,
                error,
                session_id,
            ),
        )
        self._conn.commit()

    def add_event(self, session_id: int, *, kind: str, detail: str, at: datetime) -> None:
        """Append an event to a session."""
        self._conn.execute(
            "INSERT INTO events (session_id, at, kind, detail) VALUES (?, ?, ?, ?)",
            (session_id, at.isoformat(), kind, detail),
        )
        self._conn.commit()

    # --- reads -------------------------------------------------------------
    def get_session(self, session_id: int) -> SessionRecord | None:
        """Return one session by id, or ``None``."""
        row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return self._to_session(row) if row is not None else None

    def list_sessions(self, *, limit: int = 20) -> list[SessionRecord]:
        """Return recent sessions, newest first."""
        rows = self._conn.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [self._to_session(row) for row in rows]

    def list_events(self, session_id: int, *, limit: int = 100) -> list[EventRecord]:
        """Return events for a session, oldest first."""
        rows = self._conn.execute(
            "SELECT * FROM events WHERE session_id = ? ORDER BY id ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [
            EventRecord(
                id=row["id"],
                session_id=row["session_id"],
                at=row["at"],
                kind=row["kind"],
                detail=row["detail"],
            )
            for row in rows
        ]

    def statistics(self) -> Statistics:
        """Return aggregate statistics across all sessions."""
        row = self._conn.execute("""
            SELECT
                COUNT(*)                        AS total_sessions,
                COALESCE(SUM(completed), 0)     AS completed_sessions,
                COALESCE(SUM(resumes), 0)       AS resumes,
                COALESCE(SUM(approvals), 0)     AS approvals,
                COALESCE(SUM(permission_prompts), 0) AS permission_prompts,
                COALESCE(SUM(runtime_seconds), 0)    AS total_runtime_seconds,
                COALESCE(SUM(total_wait_seconds), 0) AS total_wait_seconds
            FROM sessions
            """).fetchone()
        return Statistics(
            total_sessions=row["total_sessions"],
            completed_sessions=row["completed_sessions"],
            resumes=row["resumes"],
            approvals=row["approvals"],
            permission_prompts=row["permission_prompts"],
            total_runtime_seconds=float(row["total_runtime_seconds"]),
            total_wait_seconds=float(row["total_wait_seconds"]),
        )

    # --- helpers -----------------------------------------------------------
    @staticmethod
    def _to_session(row: sqlite3.Row) -> SessionRecord:
        return SessionRecord(
            id=row["id"],
            command=tuple(json.loads(row["command"])),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            final_state=row["final_state"],
            completed=bool(row["completed"]),
            resumes=row["resumes"],
            approvals=row["approvals"],
            permission_prompts=row["permission_prompts"],
            total_wait_seconds=float(row["total_wait_seconds"]),
            runtime_seconds=(
                float(row["runtime_seconds"]) if row["runtime_seconds"] is not None else None
            ),
            stop_reason=row["stop_reason"],
            error=row["error"],
        )
