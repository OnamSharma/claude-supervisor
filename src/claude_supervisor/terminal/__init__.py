"""Terminal subsystem: launch Claude Code in a PTY and stream its I/O.

The :class:`TerminalManager` interface abstracts over platform PTY backends so
the orchestrator never depends on ``pexpect`` or ``pywinpty`` directly. A
:class:`ScriptedTerminal` provides a deterministic, process-free implementation
for tests and dry runs.
"""

from __future__ import annotations

from claude_supervisor.terminal.base import (
    TIMEOUT,
    ScriptedTerminal,
    TerminalError,
    TerminalManager,
)
from claude_supervisor.terminal.factory import create_terminal, terminal_factory

__all__ = [
    "TIMEOUT",
    "ScriptedTerminal",
    "TerminalError",
    "TerminalManager",
    "create_terminal",
    "terminal_factory",
]
