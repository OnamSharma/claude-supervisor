"""Permission subsystem: decide how to answer Claude's permission prompts."""

from __future__ import annotations

from claude_supervisor.permissions.engine import (
    ActiveTaskPermissionEngine,
    PermissionDecision,
    PermissionEngine,
)

__all__ = [
    "ActiveTaskPermissionEngine",
    "PermissionDecision",
    "PermissionEngine",
]
