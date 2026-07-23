"""Tests for attach mode (live-session supervision) using fakes throughout."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from claude_supervisor.config.models import SupervisorConfig
from claude_supervisor.core import AttachSession
from claude_supervisor.resume import ManualClock
from claude_supervisor.terminal import TIMEOUT, ScriptedTerminal, TerminalManager
from claude_supervisor.terminal.host import FakeHost, translate_windows_key

LIMIT = "Usage limit reached. Try again in 1s\n"


class HookedTerminal(ScriptedTerminal):
    """ScriptedTerminal that fires callbacks on specific read numbers."""

    def __init__(self, chunks, hooks: dict[int, Callable[[], None]] | None = None, **kw) -> None:
        super().__init__(chunks, **kw)
        self._hooks = hooks or {}
        self._reads = 0

    def read(self, timeout: float):
        self._reads += 1
        hook = self._hooks.get(self._reads)
        if hook is not None:
            hook()
        return super().read(timeout)


class FactoryStub:
    def __init__(self, terminals: Sequence[TerminalManager]) -> None:
        self._iter = iter(terminals)
        self.calls: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> TerminalManager:
        self.calls.append(list(command))
        return next(self._iter)


def _config(**overrides: object) -> SupervisorConfig:
    defaults: dict[str, object] = {"attach_resume_buffer_seconds": 0.0}
    defaults.update(overrides)
    return SupervisorConfig(**defaults)


def _session(terminals, *, config=None, clock=None, host=None):
    host = host or FakeHost()
    factory = FactoryStub(terminals)
    session = AttachSession(
        config or _config(),
        factory,
        host,
        clock=clock or ManualClock(),
    )
    return session, factory, host


def test_output_is_forwarded_to_host() -> None:
    term = ScriptedTerminal(["hello from claude\n", "more output\n"])
    session, _, host = _session([term])
    session.run()
    assert "hello from claude\n" in host.written
    assert "more output\n" in host.written
    assert host.restored is True
    assert session.stats.stop_reason == "claude exited"


def test_user_input_is_forwarded_to_claude() -> None:
    host = FakeHost()
    term = HookedTerminal(
        ["welcome\n"],
        hooks={1: lambda: host.type("fix the tests\r")},
    )
    session, _, _ = _session([term], host=host)
    session.run()
    assert "fix the tests\r" in term.sent  # raw passthrough, no rewriting


def test_limit_then_nudge_while_session_alive() -> None:
    # Clock auto-ticks on every now() so the deadline passes while the (silent)
    # session is still alive; the supervisor must type the nudge.
    clock = ManualClock(auto_tick=0.5)
    term = ScriptedTerminal([LIMIT, TIMEOUT, TIMEOUT, TIMEOUT, TIMEOUT, TIMEOUT, TIMEOUT])
    session, _, _ = _session([term], clock=clock)
    session.run()
    assert "continue\r" in term.sent
    assert session.stats.resumes == 1


def test_limit_then_child_death_relaunches_with_continue() -> None:
    term1 = ScriptedTerminal([LIMIT])  # limit, then the process dies
    term2 = ScriptedTerminal(["welcome back\n"])
    session, factory, host = _session([term1, term2])
    session.run()
    assert factory.calls == [["claude"], ["claude", "--continue"]]
    assert session.stats.resumes == 1
    assert "welcome back\n" in host.written
    assert session.stats.stop_reason == "claude exited"


def test_clean_exit_without_pending_limit_just_ends() -> None:
    term = ScriptedTerminal(["bye\n"])
    session, factory, _ = _session([term])
    session.run()
    assert len(factory.calls) == 1  # no relaunch
    assert session.stats.resumes == 0
    assert session.stats.stop_reason == "claude exited"


def test_detach_key_stops_and_restores() -> None:
    host = FakeHost()
    term = HookedTerminal(
        ["output\n", TIMEOUT, TIMEOUT],
        hooks={2: host.press_detach},
    )
    session, _, _ = _session([term], host=host)
    session.run()
    assert session.stats.stop_reason == "detached"
    assert host.restored is True


def test_max_resumes_cap_stops_relaunching() -> None:
    cfg = _config(max_resumes=1)
    term1 = ScriptedTerminal([LIMIT])
    term2 = ScriptedTerminal([LIMIT])
    session, factory, _ = _session([term1, term2], config=cfg)
    session.run()
    assert len(factory.calls) == 2  # initial + one relaunch, then capped
    assert session.stats.resumes == 1  # the second limit was not scheduled


def test_auto_resume_disabled_never_schedules() -> None:
    cfg = _config(auto_resume=False)
    term = ScriptedTerminal([LIMIT, "still here\n"])
    session, factory, _ = _session([term], config=cfg)
    session.run()
    assert session.stats.resumes == 0
    assert len(factory.calls) == 1
    assert not any("continue" in s for s in term.sent)


def test_limit_without_newline_is_detected_via_idle_flush() -> None:
    # TUIs may show the limit banner with no line terminator at all; the quiet
    # stream must be flushed and parsed anyway.
    clock = ManualClock(auto_tick=0.5)
    banner = "Usage limit reached. Try again in 1s"  # no \n, no \r
    term = ScriptedTerminal([banner, TIMEOUT, TIMEOUT, TIMEOUT, TIMEOUT, TIMEOUT, TIMEOUT])
    session, _, _ = _session([term], clock=clock)
    session.run()
    assert "continue\r" in term.sent
    assert session.stats.resumes == 1


def test_stale_banner_redraw_after_nudge_is_ignored() -> None:
    # Right after a nudge, the TUI may still redraw the old limit banner; the
    # cooldown must prevent re-scheduling.
    clock = ManualClock(auto_tick=0.5)
    term = ScriptedTerminal(
        [LIMIT, TIMEOUT, TIMEOUT, TIMEOUT, TIMEOUT, TIMEOUT, LIMIT, TIMEOUT, TIMEOUT]
    )
    session, factory, _ = _session([term], clock=clock)
    session.run()
    assert session.stats.resumes == 1
    assert term.sent.count("continue\r") == 1
    assert len(factory.calls) == 1


def test_child_pty_follows_host_terminal_size(monkeypatch) -> None:
    import os as _os

    import claude_supervisor.core.attach as attach_mod

    monkeypatch.setattr(
        attach_mod.shutil, "get_terminal_size", lambda: _os.terminal_size((100, 30))
    )

    class ResizingTerminal(ScriptedTerminal):
        def __init__(self, chunks, **kw):
            super().__init__(chunks, **kw)
            self.resizes: list[tuple[int, int]] = []

        def resize(self, rows: int, cols: int) -> None:
            self.resizes.append((rows, cols))

    term = ResizingTerminal([TIMEOUT] * 10)
    session, _, _ = _session([term])
    session.run()
    assert (30, 100) in term.resizes  # (rows, cols) from the host console


def test_send_interrupt_forwards_ctrl_c() -> None:
    holder: dict = {}
    term = HookedTerminal(
        ["hi\n", TIMEOUT],
        hooks={2: lambda: holder["s"].send_interrupt()},
    )
    session, _, _ = _session([term])
    holder["s"] = session
    session.run()
    assert "\x03" in term.sent


def test_windows_key_translation() -> None:
    assert translate_windows_key("\xe0", "H") == "\x1b[A"  # up arrow
    assert translate_windows_key("\x00", "P") == "\x1b[B"  # down arrow
    assert translate_windows_key("\xe0", "S") == "\x1b[3~"  # delete
    assert translate_windows_key("\xe0", "?") == ""  # unknown -> dropped
    assert translate_windows_key("a", "b") == "ab"  # not a special prefix
