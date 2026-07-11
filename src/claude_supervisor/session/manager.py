"""Session lifecycle bookkeeping, backed by a :class:`Storage`."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from claude_supervisor.core.stats import RunStats
from claude_supervisor.logging import get_logger
from claude_supervisor.state_machine import (
    State,
    StateMachine,
    Transition,
    TransitionObserver,
)
from claude_supervisor.storage.base import EventRecord, SessionRecord, Statistics, Storage

_logger = get_logger("session")


class SessionManager:
    """Record supervised runs and expose their history and statistics.

    A run is bracketed by :meth:`begin` (before the loop starts) and :meth:`end`
    (after it finishes, even on error). Optionally, :meth:`begin` attaches an
    observer to the state machine so every transition is stored as an event.
    """

    def __init__(self, storage: Storage) -> None:
        """Bind the manager to a ``storage`` backend."""
        self._storage = storage

    def begin(
        self,
        command: Sequence[str],
        *,
        started_at: datetime | None = None,
        machine: StateMachine | None = None,
    ) -> int:
        """Create a session row and return its id.

        If ``machine`` is provided, transitions are logged as events for later
        inspection via :meth:`events`.
        """
        session_id = self._storage.create_session(
            command=command, started_at=started_at or datetime.now(UTC)
        )
        if machine is not None:
            machine.add_observer(self._make_transition_observer(session_id))
        _logger.debug("session %s started for %s", session_id, " ".join(command))
        return session_id

    def end(self, session_id: int, stats: RunStats, final_state: State) -> None:
        """Finalize a session row from ``stats`` and the final state."""
        finished = stats.finished_at or datetime.now(UTC)
        self._storage.complete_session(
            session_id,
            finished_at=finished,
            final_state=final_state.value,
            completed=stats.completed,
            resumes=stats.resumes,
            approvals=stats.approvals,
            permission_prompts=stats.permission_prompts,
            total_wait_seconds=stats.total_wait_seconds,
            runtime_seconds=stats.elapsed_seconds,
            stop_reason=stats.stop_reason,
            error=stats.error,
        )
        _logger.debug("session %s ended (%s)", session_id, final_state.value)

    def latest(self) -> SessionRecord | None:
        """Return the most recent session, or ``None``."""
        sessions = self._storage.list_sessions(limit=1)
        return sessions[0] if sessions else None

    def recent(self, limit: int = 20) -> list[SessionRecord]:
        """Return recent sessions, newest first."""
        return self._storage.list_sessions(limit=limit)

    def events(self, session_id: int, limit: int = 100) -> list[EventRecord]:
        """Return events for a session, oldest first."""
        return self._storage.list_events(session_id, limit=limit)

    def statistics(self) -> Statistics:
        """Return aggregate statistics across all sessions."""
        return self._storage.statistics()

    def _make_transition_observer(self, session_id: int) -> TransitionObserver:
        def observe(transition: Transition) -> None:
            detail = f"{transition.source.value} -> {transition.target.value}"
            if transition.reason:
                detail += f": {transition.reason}"
            self._storage.add_event(session_id, kind="transition", detail=detail, at=transition.at)

        return observe
