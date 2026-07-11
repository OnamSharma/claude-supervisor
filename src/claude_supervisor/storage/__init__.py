"""Storage subsystem: durable session history and statistics (SQLite).

The storage layer speaks only primitives -- it never imports the orchestration
layer -- so it can be swapped for another backend behind the :class:`Storage`
protocol. The :mod:`claude_supervisor.session` bridge maps run results onto it.
"""

from __future__ import annotations

from claude_supervisor.storage.base import (
    EventRecord,
    SessionRecord,
    Statistics,
    Storage,
    StorageError,
)
from claude_supervisor.storage.sqlite import SqliteStorage

__all__ = [
    "EventRecord",
    "SessionRecord",
    "SqliteStorage",
    "Statistics",
    "Storage",
    "StorageError",
]
