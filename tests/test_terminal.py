"""Tests for the terminal abstraction, threaded base, and factory."""

from __future__ import annotations

import queue

import pytest

from claude_supervisor.terminal import (
    TIMEOUT,
    ScriptedTerminal,
    TerminalError,
    TerminalManager,
    create_terminal,
    terminal_factory,
)
from claude_supervisor.terminal import factory as factory_mod
from claude_supervisor.terminal.threaded import ThreadedTerminal

# --- ScriptedTerminal ------------------------------------------------------


def test_scripted_replays_then_eof() -> None:
    term = ScriptedTerminal(["a", "b"])
    term.start()
    assert term.read(0) == "a"
    assert term.read(0) == "b"
    assert term.read(0) is None  # EOF
    assert term.read(0) is None  # stays EOF


def test_scripted_records_sent_input() -> None:
    term = ScriptedTerminal(["x"])
    term.start()
    term.send_line("y")  # convenience: appends the terminal Enter (CR)
    term.send("\x1b")  # raw: e.g. Escape, recorded verbatim
    assert term.sent == ["y\r", "\x1b"]


def test_scripted_read_before_start_raises() -> None:
    with pytest.raises(TerminalError, match="before start"):
        ScriptedTerminal(["x"]).read(0)


def test_scripted_timeout_marker_returns_empty_and_stays_alive() -> None:
    term = ScriptedTerminal(["a", TIMEOUT, "b"])
    term.start()
    assert term.read(0) == "a"
    assert term.read(0) == ""  # TIMEOUT -> empty, not EOF
    assert term.is_alive() is True
    assert term.read(0) == "b"
    assert term.read(0) is None  # now EOF


def test_scripted_alive_and_exit_code() -> None:
    term = ScriptedTerminal(["x"], exit_code=3)
    term.start()
    assert term.is_alive() is True
    assert term.exit_code() is None
    term.terminate()
    assert term.is_alive() is False
    assert term.exit_code() == 3


def test_scripted_send_after_eof_raises() -> None:
    term = ScriptedTerminal([])
    term.start()
    assert term.read(0) is None
    with pytest.raises(TerminalError, match="after EOF"):
        term.send_line("nope")


def test_scripted_context_manager() -> None:
    with ScriptedTerminal(["x"]) as term:
        assert term.is_alive()
    assert term.is_alive() is False


def test_scripted_is_a_terminal_manager() -> None:
    assert isinstance(ScriptedTerminal(["x"]), TerminalManager)


# --- ThreadedTerminal via a fake raw source --------------------------------


class _FakeRawTerminal(ThreadedTerminal):
    """Drives ThreadedTerminal from an in-memory source (no real process)."""

    def __init__(self, chunks: list[str]) -> None:
        super().__init__(["fake"])
        self._src: queue.Queue[str | None] = queue.Queue()
        for chunk in chunks:
            self._src.put(chunk)
        self._alive = True
        self.written: list[str] = []

    def finish(self) -> None:
        self._src.put(None)  # sentinel -> EOF

    def _raw_spawn(self) -> None:
        pass

    def _raw_read(self) -> str:
        item = self._src.get()
        if item is None:
            raise EOFError
        return item

    def _raw_write(self, data: str) -> None:
        self.written.append(data)

    def _raw_is_alive(self) -> bool:
        return self._alive

    def _raw_exit_code(self) -> int | None:
        return None if self._alive else 0

    def _raw_terminate(self, *, force: bool) -> None:
        self._alive = False
        self._src.put(None)


def test_threaded_reads_chunks_then_eof() -> None:
    term = _FakeRawTerminal(["hello", "world"])
    term.start()
    assert term.read(1.0) == "hello"
    assert term.read(1.0) == "world"
    term.finish()
    assert term.read(1.0) is None
    assert term.read(1.0) is None
    term.terminate()


def test_threaded_timeout_returns_empty_string() -> None:
    term = _FakeRawTerminal([])
    term.start()
    # Nothing queued and no EOF yet -> timeout yields "".
    assert term.read(0.05) == ""
    term.terminate()


def test_threaded_send_line_writes_carriage_return() -> None:
    # A PTY's Enter key is a carriage return, not a line feed.
    term = _FakeRawTerminal([])
    term.start()
    term.send_line("go")
    assert term.written == ["go\r"]
    term.terminate()


def test_threaded_send_raw_writes_verbatim() -> None:
    term = _FakeRawTerminal([])
    term.start()
    term.send("1")  # menu selection, no terminator
    term.send("\x1b")  # Escape
    assert term.written == ["1", "\x1b"]
    term.terminate()


def test_threaded_read_before_start_raises() -> None:
    with pytest.raises(TerminalError, match="before start"):
        _FakeRawTerminal([]).read(0.01)


def test_threaded_send_before_start_raises() -> None:
    with pytest.raises(TerminalError, match="before start"):
        _FakeRawTerminal([]).send_line("x")


def test_threaded_empty_command_rejected() -> None:
    class _Empty(_FakeRawTerminal):
        def __init__(self) -> None:
            ThreadedTerminal.__init__(self, [])  # empty argv should be rejected

    with pytest.raises(TerminalError, match="must not be empty"):
        _Empty()


def test_threaded_start_is_idempotent() -> None:
    term = _FakeRawTerminal(["a"])
    term.start()
    term.start()  # no-op, no second thread/spawn
    assert term.read(1.0) == "a"
    term.terminate()


def test_threaded_terminate_before_start_is_noop() -> None:
    _FakeRawTerminal([]).terminate()  # must not raise


# --- factory ---------------------------------------------------------------


def test_create_terminal_selects_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory_mod.os, "name", "nt")
    from claude_supervisor.terminal.backends import WinptyTerminal

    assert isinstance(create_terminal(["x"]), WinptyTerminal)


def test_create_terminal_selects_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory_mod.os, "name", "posix")
    from claude_supervisor.terminal.backends import PexpectTerminal

    term = create_terminal(["x"], cwd=".")
    assert isinstance(term, PexpectTerminal)
    assert term.command == ("x",)


def test_terminal_factory_builds_managers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(factory_mod.os, "name", "posix")
    factory = terminal_factory(cwd=".")
    assert isinstance(factory(["a", "b"]), TerminalManager)


def test_launch_error_message_is_actionable() -> None:
    from claude_supervisor.terminal.backends import _launch_error

    msg = _launch_error(["claude"], FileNotFoundError("not found"))
    assert "claude" in msg
    assert "PATH" in msg
    assert "claude_command" in msg
