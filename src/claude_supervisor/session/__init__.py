"""Session subsystem: bridge run outcomes onto durable storage.

This layer is allowed to depend on both the orchestration layer (``RunStats``,
the state machine) and the storage layer, keeping storage itself free of any
knowledge of the core.
"""

from __future__ import annotations

from claude_supervisor.session.manager import SessionManager

__all__ = ["SessionManager"]
