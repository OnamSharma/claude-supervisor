"""Concrete PTY backends for POSIX (pexpect) and Windows (pywinpty).

Both libraries are optional dependencies, imported lazily so that importing
this module (and the whole package) never requires a PTY library to be present.
A clear :class:`TerminalError` explains which extra to install if it is missing.

The thin ``_raw_*`` methods that touch the external libraries are excluded from
coverage: they require a real interactive process and the platform's library,
which unit tests deliberately avoid. The shared, testable machinery lives in
:mod:`claude_supervisor.terminal.threaded`.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from claude_supervisor.terminal.base import TerminalError
from claude_supervisor.terminal.threaded import ThreadedTerminal

_READ_CHUNK = 1024


class PexpectTerminal(ThreadedTerminal):
    """POSIX PTY backend using :mod:`pexpect`."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        """Create a pexpect-backed terminal for ``command``."""
        super().__init__(command)
        self._cwd = Path(cwd) if cwd is not None else None
        self._env = dict(env) if env is not None else None
        self._child: Any = None  # pexpect.spawn, typed lazily

    def _raw_spawn(self) -> None:  # pragma: no cover - requires pexpect + a PTY
        try:
            import pexpect
        except ImportError as exc:
            raise TerminalError(
                "pexpect is required on POSIX. Install with: "
                "pip install 'claude-supervisor[pty-posix]'"
            ) from exc
        self._child = pexpect.spawn(
            self._command[0],
            list(self._command[1:]),
            cwd=str(self._cwd) if self._cwd else None,
            env=self._env,
            encoding="utf-8",
            codec_errors="replace",
            timeout=None,
            echo=False,
        )

    def _raw_read(self) -> str:  # pragma: no cover - requires a real PTY
        import pexpect

        try:
            chunk: str = self._child.read_nonblocking(size=_READ_CHUNK, timeout=None)
        except pexpect.EOF as exc:
            raise EOFError from exc
        return chunk

    def _raw_write(self, data: str) -> None:  # pragma: no cover - requires a real PTY
        self._child.send(data)

    def _raw_is_alive(self) -> bool:  # pragma: no cover - requires a real PTY
        return bool(self._child is not None and self._child.isalive())

    def _raw_exit_code(self) -> int | None:  # pragma: no cover - requires a real PTY
        if self._child is None:
            return None
        code: int | None = self._child.exitstatus
        return code

    def _raw_terminate(self, *, force: bool) -> None:  # pragma: no cover - requires a real PTY
        if self._child is not None:
            self._child.terminate(force=force)


class WinptyTerminal(ThreadedTerminal):
    """Windows PTY backend using :mod:`pywinpty` (imported as ``winpty``)."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        """Create a pywinpty-backed terminal for ``command``."""
        super().__init__(command)
        self._cwd = Path(cwd) if cwd is not None else None
        self._env = dict(env) if env is not None else None
        self._proc: Any = None  # winpty.PtyProcess, typed lazily

    def _raw_spawn(self) -> None:  # pragma: no cover - requires pywinpty + a console
        try:
            from winpty import PtyProcess
        except ImportError as exc:
            raise TerminalError(
                "pywinpty is required on Windows. Install with: "
                "pip install 'claude-supervisor[pty-windows]'"
            ) from exc
        self._proc = PtyProcess.spawn(
            list(self._command),
            cwd=str(self._cwd) if self._cwd else None,
            env=self._env,
        )

    def _raw_read(self) -> str:  # pragma: no cover - requires a real console
        data: str = self._proc.read(_READ_CHUNK)
        if not data:
            raise EOFError
        return data

    def _raw_write(self, data: str) -> None:  # pragma: no cover - requires a real console
        self._proc.write(data)

    def _raw_is_alive(self) -> bool:  # pragma: no cover - requires a real console
        return bool(self._proc is not None and self._proc.isalive())

    def _raw_exit_code(self) -> int | None:  # pragma: no cover - requires a real console
        if self._proc is None:
            return None
        code: int | None = self._proc.exitstatus
        return code

    def _raw_terminate(self, *, force: bool) -> None:  # pragma: no cover - requires a real console
        if self._proc is not None:
            self._proc.terminate(force=force)
