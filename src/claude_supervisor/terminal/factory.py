"""Platform-aware construction of terminal backends."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence

from claude_supervisor.terminal.base import TerminalManager

#: A callable that builds a (not-yet-started) terminal for a given argv.
type TerminalFactory = Callable[[Sequence[str]], TerminalManager]


def create_terminal(
    command: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    dimensions: tuple[int, int] | None = None,
) -> TerminalManager:
    """Create the appropriate PTY backend for the current platform.

    The concrete backend classes are imported lazily so that a missing optional
    PTY dependency only fails when a terminal is actually created, with a clear
    message pointing at the right extra. ``dimensions`` is ``(rows, cols)``.
    """
    if os.name == "nt":
        from claude_supervisor.terminal.backends import WinptyTerminal

        return WinptyTerminal(command, cwd=cwd, env=env, dimensions=dimensions)

    from claude_supervisor.terminal.backends import PexpectTerminal

    return PexpectTerminal(command, cwd=cwd, env=env, dimensions=dimensions)


def terminal_factory(
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    dimensions: tuple[int, int] | None = None,
) -> TerminalFactory:
    """Return a :data:`TerminalFactory` bound to ``cwd``/``env``/``dimensions``."""

    def factory(command: Sequence[str]) -> TerminalManager:
        return create_terminal(command, cwd=cwd, env=env, dimensions=dimensions)

    return factory
