"""Storage interface and the primitive records it exchanges."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


class StorageError(RuntimeError):
    """Raised when the storage backend cannot complete an operation."""


@dataclass(frozen=True, slots=True)
class SessionRecord:
    """A persisted supervised run."""

    id: int
    command: tuple[str, ...]
    started_at: str
    finished_at: str | None
    final_state: str | None
    completed: bool
    resumes: int
    approvals: int
    permission_prompts: int
    total_wait_seconds: float
    runtime_seconds: float | None
    stop_reason: str
    error: str | None


@dataclass(frozen=True, slots=True)
class EventRecord:
    """A notable event logged during a run (e.g. a state transition)."""

    id: int
    session_id: int
    at: str
    kind: str
    detail: str


@dataclass(frozen=True, slots=True)
class Statistics:
    """Aggregate statistics across all recorded sessions."""

    total_sessions: int = 0
    completed_sessions: int = 0
    resumes: int = 0
    approvals: int = 0
    permission_prompts: int = 0
    total_runtime_seconds: float = 0.0
    total_wait_seconds: float = 0.0

    @property
    def average_runtime_seconds(self) -> float:
        """Mean runtime per session, or 0 when there are none."""
        return self.total_runtime_seconds / self.total_sessions if self.total_sessions else 0.0

    @property
    def average_wait_seconds(self) -> float:
        """Mean automated wait per resume, or 0 when there are none."""
        return self.total_wait_seconds / self.resumes if self.resumes else 0.0

    @property
    def hours_saved(self) -> float:
        """Unattended waiting the supervisor absorbed, in hours."""
        return self.total_wait_seconds / 3600.0

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly summary including derived fields."""
        return {
            "total_sessions": self.total_sessions,
            "completed_sessions": self.completed_sessions,
            "resumes": self.resumes,
            "approvals": self.approvals,
            "permission_prompts": self.permission_prompts,
            "total_runtime_seconds": round(self.total_runtime_seconds, 3),
            "average_runtime_seconds": round(self.average_runtime_seconds, 3),
            "total_wait_seconds": round(self.total_wait_seconds, 3),
            "average_wait_seconds": round(self.average_wait_seconds, 3),
            "hours_saved": round(self.hours_saved, 3),
        }


@runtime_checkable
class Storage(Protocol):
    """Durable persistence for sessions, events, and statistics."""

    def create_session(self, *, command: Sequence[str], started_at: datetime) -> int:
        """Insert a new running session and return its id."""
        ...

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
        ...

    def add_event(self, session_id: int, *, kind: str, detail: str, at: datetime) -> None:
        """Append an event to a session."""
        ...

    def get_session(self, session_id: int) -> SessionRecord | None:
        """Return one session by id, or ``None``."""
        ...

    def list_sessions(self, *, limit: int = 20) -> list[SessionRecord]:
        """Return recent sessions, newest first."""
        ...

    def list_events(self, session_id: int, *, limit: int = 100) -> list[EventRecord]:
        """Return events for a session, oldest first."""
        ...

    def statistics(self) -> Statistics:
        """Return aggregate statistics across all sessions."""
        ...

    def close(self) -> None:
        """Release any underlying resources."""
        ...
