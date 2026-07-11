"""A reusable base for real PTY backends built on a blocking reader thread.

Both supported PTY libraries (``pexpect`` on POSIX, ``pywinpty`` on Windows)
expose *blocking* reads. To give the orchestrator a uniform, timeout-capable
``read`` without busy-polling, this base runs the native blocking read on a
background thread that pushes chunks onto a queue. The main thread consumes the
queue with a timeout -- it blocks efficiently and stays responsive to shutdown.

Subclasses implement only the small ``_raw_*`` surface for their library.
"""

from __future__ import annotations

import abc
import queue
import threading
from collections.abc import Sequence

from claude_supervisor.logging import get_logger
from claude_supervisor.terminal.base import TerminalError, TerminalManager

_logger = get_logger("terminal")

# Sentinel placed on the queue when the reader thread observes EOF.
_EOF = object()


class ThreadedTerminal(TerminalManager):
    """PTY terminal whose blocking reads are pumped by a background thread."""

    def __init__(self, command: Sequence[str]) -> None:
        """Store ``command``; the process is not spawned until :meth:`start`."""
        if not command:
            raise TerminalError("command must not be empty")
        self._command = tuple(command)
        self._queue: queue.Queue[object] = queue.Queue()
        self._reader: threading.Thread | None = None
        self._eof_seen = False
        self._started = False

    @property
    def command(self) -> tuple[str, ...]:
        """The argv this terminal was created for."""
        return self._command

    # --- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        """Spawn the process and begin pumping its output."""
        if self._started:
            return
        self._raw_spawn()
        self._started = True
        self._reader = threading.Thread(
            target=self._pump, name=f"pty-reader:{self._command[0]}", daemon=True
        )
        self._reader.start()

    def _pump(self) -> None:
        try:
            while True:
                data = self._raw_read()
                if data:
                    self._queue.put(data)
        except EOFError:
            pass
        except Exception as exc:
            _logger.debug("reader thread error: %s", exc)
        finally:
            self._queue.put(_EOF)

    def read(self, timeout: float) -> str | None:
        """Return a chunk, ``""`` on timeout, or ``None`` once (at EOF)."""
        if not self._started:
            raise TerminalError("read() called before start()")
        if self._eof_seen:
            return None
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return ""
        if item is _EOF:
            self._eof_seen = True
            return None
        assert isinstance(item, str)
        return item

    def send(self, data: str) -> None:
        """Write ``data`` verbatim to the process input."""
        if not self._started:
            raise TerminalError("send() called before start()")
        self._raw_write(data)

    def is_alive(self) -> bool:
        """Whether the underlying process is still running."""
        return self._started and self._raw_is_alive()

    def exit_code(self) -> int | None:
        """The process exit code, or ``None`` while running."""
        return self._raw_exit_code()

    def terminate(self, *, force: bool = False) -> None:
        """Terminate the process and join the reader thread."""
        if not self._started:
            return
        try:
            self._raw_terminate(force=force)
        finally:
            if self._reader is not None:
                self._reader.join(timeout=2.0)

    # --- backend-specific surface -----------------------------------------
    @abc.abstractmethod
    def _raw_spawn(self) -> None:
        """Spawn the underlying process."""

    @abc.abstractmethod
    def _raw_read(self) -> str:
        """Blocking read of the next output; raise ``EOFError`` at end of stream."""

    @abc.abstractmethod
    def _raw_write(self, data: str) -> None:
        """Write ``data`` to the process input."""

    @abc.abstractmethod
    def _raw_is_alive(self) -> bool:
        """Whether the process is running."""

    @abc.abstractmethod
    def _raw_exit_code(self) -> int | None:
        """The process exit code, or ``None`` while running."""

    @abc.abstractmethod
    def _raw_terminate(self, *, force: bool) -> None:
        """Terminate the process."""
