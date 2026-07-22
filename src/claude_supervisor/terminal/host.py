"""The *host* side of attach mode: your real keyboard and screen.

``attach`` is a transparent proxy: keystrokes you type are forwarded to Claude's
PTY, and Claude's output is written to your screen. This module owns that host
side — putting your terminal into raw mode, translating Windows console keys
into the ANSI sequences a TUI expects, and restoring everything on exit.

A :class:`FakeHost` makes the attach loop fully testable without a console.
"""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from claude_supervisor.logging import get_logger

_logger = get_logger("host")

#: Ctrl+] — the detach key (same convention as telnet).
DETACH_KEY = "\x1d"

#: Called with each chunk of user input to forward to the child PTY.
type InputHandler = Callable[[str], None]
#: Called when the user presses the detach key.
type DetachHandler = Callable[[], None]

# Windows console special-key codes (after a '\x00'/'\xe0' prefix from getwch)
# mapped to the ANSI sequences an interactive TUI expects.
_WIN_KEY_TO_ANSI: dict[str, str] = {
    "H": "\x1b[A",  # up
    "P": "\x1b[B",  # down
    "M": "\x1b[C",  # right
    "K": "\x1b[D",  # left
    "G": "\x1b[H",  # home
    "O": "\x1b[F",  # end
    "R": "\x1b[2~",  # insert
    "S": "\x1b[3~",  # delete
    "I": "\x1b[5~",  # page up
    "Q": "\x1b[6~",  # page down
}


def translate_windows_key(prefix: str, code: str) -> str:
    r"""Translate a Windows console special-key pair into an ANSI sequence.

    ``getwch`` reports special keys as two reads: a prefix (``\x00`` or
    ``\xe0``) followed by a code. Unknown codes are dropped (empty string).
    """
    if prefix not in ("\x00", "\xe0"):
        return prefix + code
    return _WIN_KEY_TO_ANSI.get(code, "")


@runtime_checkable
class Host(Protocol):
    """The user's terminal: raw input in, child output out."""

    def start(self, on_input: InputHandler, on_detach: DetachHandler) -> None:
        """Enter raw mode and begin forwarding keystrokes to ``on_input``."""
        ...

    def write(self, data: str) -> None:
        """Render child output on the user's screen."""
        ...

    def restore(self) -> None:
        """Restore the terminal to its previous state."""
        ...


class FakeHost:
    """In-memory host for tests: records output, lets tests inject input."""

    def __init__(self) -> None:
        """Create an inactive fake host."""
        self.written: list[str] = []
        self._on_input: InputHandler | None = None
        self._on_detach: DetachHandler | None = None
        self.restored = False

    def start(self, on_input: InputHandler, on_detach: DetachHandler) -> None:
        """Record the callbacks; no real terminal involved."""
        self._on_input = on_input
        self._on_detach = on_detach

    def write(self, data: str) -> None:
        """Record what would have been rendered."""
        self.written.append(data)

    def restore(self) -> None:
        """Mark the fake as restored."""
        self.restored = True

    # test helpers ----------------------------------------------------------
    def type(self, data: str) -> None:
        """Simulate the user typing ``data``."""
        assert self._on_input is not None
        self._on_input(data)

    def press_detach(self) -> None:
        """Simulate the user pressing the detach key."""
        assert self._on_detach is not None
        self._on_detach()


class WindowsHost:
    """Real host terminal on Windows (msvcrt input + VT-enabled output)."""

    def __init__(self) -> None:
        """Prepare an inactive host; nothing changes until :meth:`start`."""
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self, on_input: InputHandler, on_detach: DetachHandler) -> None:
        """Enable VT output and start the keystroke-forwarding thread."""
        self._enable_vt_output()
        self._thread = threading.Thread(
            target=self._pump_keys,
            args=(on_input, on_detach),
            name="attach-host-input",
            daemon=True,
        )
        self._thread.start()

    @staticmethod
    def _enable_vt_output() -> None:  # pragma: no cover - console API
        """Turn on ANSI rendering for classic consoles (no-op elsewhere)."""
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)  # VT processing
        except Exception:
            pass

    def _pump_keys(
        self, on_input: InputHandler, on_detach: DetachHandler
    ) -> None:  # pragma: no cover - needs a live console
        import msvcrt

        while not self._stop.is_set():
            try:
                ch = msvcrt.getwch()
            except Exception:
                return  # no console (redirected stdin) -> input unavailable
            if ch == DETACH_KEY:
                on_detach()
                return
            if ch in ("\x00", "\xe0"):
                seq = translate_windows_key(ch, msvcrt.getwch())
                if seq:
                    on_input(seq)
            else:
                on_input(ch)

    def write(self, data: str) -> None:
        """Write child output straight to the console."""
        sys.stdout.write(data)
        sys.stdout.flush()

    def restore(self) -> None:
        """Stop the input pump (console modes were not altered)."""
        self._stop.set()


class PosixHost:  # pragma: no cover - exercised only on POSIX consoles
    """Real host terminal on POSIX (raw tty via termios)."""

    def __init__(self) -> None:
        """Prepare an inactive host; nothing changes until :meth:`start`."""
        self._stop = threading.Event()
        self._saved: Any = None  # opaque termios attribute blob
        self._fd = sys.stdin.fileno() if sys.stdin.isatty() else None

    def start(self, on_input: InputHandler, on_detach: DetachHandler) -> None:
        """Put the tty into raw mode and start forwarding keystrokes."""
        if self._fd is not None:
            import termios
            import tty

            self._saved = termios.tcgetattr(self._fd)
            tty.setraw(self._fd)
        thread = threading.Thread(
            target=self._pump_keys,
            args=(on_input, on_detach),
            name="attach-host-input",
            daemon=True,
        )
        thread.start()

    def _pump_keys(self, on_input: InputHandler, on_detach: DetachHandler) -> None:
        if self._fd is None:
            return
        while not self._stop.is_set():
            try:
                data = os.read(self._fd, 1024).decode("utf-8", "ignore")
            except OSError:
                return
            if not data:
                return
            if DETACH_KEY in data:
                on_detach()
                return
            on_input(data)

    def write(self, data: str) -> None:
        """Write child output straight to the terminal."""
        sys.stdout.write(data)
        sys.stdout.flush()

    def restore(self) -> None:
        """Restore the saved tty attributes."""
        self._stop.set()
        if self._fd is not None and self._saved is not None:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)


def create_host() -> Host:
    """Return the real host implementation for this platform."""
    if os.name == "nt":
        return WindowsHost()
    return PosixHost()  # pragma: no cover - platform dependent
