"""The terminal abstraction and a deterministic in-memory implementation."""

from __future__ import annotations

import abc
from collections import deque
from collections.abc import Iterable, Sequence
from types import TracebackType


class TerminalError(RuntimeError):
    """Raised when a terminal cannot be started or driven."""


# The "Enter" key on a terminal is a carriage return. On a Windows ConPTY, "\n"
# is NOT interpreted as Enter, so a child blocked on input never wakes; on POSIX
# PTYs the line discipline (ICRNL) maps an input "\r" to "\n" for the child. So
# "\r" is the correct, cross-platform line terminator for terminal *input*.
INPUT_NEWLINE = "\r"

#: Marker a :class:`ScriptedTerminal` script can contain to simulate a read
#: timeout (``read`` returns ``""`` without consuming the stream), so idle
#: behavior can be tested deterministically.
TIMEOUT = object()


class TerminalManager(abc.ABC):
    """Launch a subprocess in a PTY and stream its output.

    ``read`` is *timeout-capable* and non-committal: it returns a chunk of
    output when available, an empty string when the timeout elapses with no
    output (so the caller can re-check control flags), and ``None`` exactly once
    when the stream reaches end-of-file. Implementations must never busy-poll;
    they block efficiently until data, timeout, or EOF.
    """

    @property
    @abc.abstractmethod
    def command(self) -> tuple[str, ...]:
        """The argv this terminal was created for."""

    @abc.abstractmethod
    def start(self) -> None:
        """Spawn the process. Idempotent implementations should guard re-entry."""

    @abc.abstractmethod
    def read(self, timeout: float) -> str | None:
        """Return the next output chunk, ``""`` on timeout, or ``None`` at EOF."""

    @abc.abstractmethod
    def send(self, data: str) -> None:
        r"""Write ``data`` verbatim to the process's input (no terminator added).

        Use this to send key sequences a TUI expects — a digit to pick a menu
        item, ``"\r"`` for Enter, ``"\x1b"`` for Escape, arrow-key sequences,
        and so on.
        """

    def send_line(self, line: str) -> None:
        """Send ``line`` followed by a carriage return (the terminal's Enter)."""
        self.send(line + INPUT_NEWLINE)

    @abc.abstractmethod
    def is_alive(self) -> bool:
        """Whether the process is currently running."""

    @abc.abstractmethod
    def exit_code(self) -> int | None:
        """The process exit code, or ``None`` while it is still running."""

    @abc.abstractmethod
    def terminate(self, *, force: bool = False) -> None:
        """Stop the process (gracefully unless ``force`` is set)."""

    def __enter__(self) -> TerminalManager:
        """Start the process on context entry."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Terminate the process on context exit."""
        self.terminate()


class ScriptedTerminal(TerminalManager):
    """A process-free terminal that replays a fixed sequence of output chunks.

    Useful for tests and dry runs: ``read`` yields the scripted chunks in order,
    then returns ``None`` (EOF). A :data:`TIMEOUT` marker in the script makes
    ``read`` return ``""`` (a read timeout) without consuming the stream, so
    idle behavior is testable. Everything written with :meth:`send` (and
    therefore :meth:`send_line`) is recorded verbatim in :attr:`sent`.
    """

    def __init__(
        self,
        chunks: Iterable[str | object],
        *,
        command: Sequence[str] = ("scripted",),
        exit_code: int = 0,
    ) -> None:
        """Create a terminal that will emit ``chunks`` then reach EOF."""
        self._chunks: deque[str | object] = deque(chunks)
        self._command = tuple(command)
        self._configured_exit = exit_code
        self.sent: list[str] = []
        self._started = False
        self._eof = False

    @property
    def command(self) -> tuple[str, ...]:
        """The argv this terminal was created for."""
        return self._command

    def start(self) -> None:
        """Mark the scripted process as running."""
        self._started = True

    def read(self, timeout: float) -> str | None:
        """Return the next scripted chunk, ``""`` for a TIMEOUT, or ``None`` at EOF."""
        if not self._started:
            raise TerminalError("read() called before start()")
        if self._chunks:
            item = self._chunks.popleft()
            if item is TIMEOUT:
                return ""
            assert isinstance(item, str)
            return item
        self._eof = True
        return None

    def send(self, data: str) -> None:
        """Record ``data`` as if it were written to the process."""
        if self._eof:
            raise TerminalError("send() called after EOF")
        self.sent.append(data)

    def is_alive(self) -> bool:
        """Whether the scripted process is still 'running'."""
        return self._started and not self._eof

    def exit_code(self) -> int | None:
        """The configured exit code once EOF has been reached."""
        return None if self.is_alive() else self._configured_exit

    def terminate(self, *, force: bool = False) -> None:
        """Mark the scripted process as finished."""
        self._eof = True
