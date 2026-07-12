"""End-to-end tests for the Supervisor run loop (no real process, no real time)."""

from __future__ import annotations

from collections.abc import Sequence

from claude_supervisor.config.models import (
    CompletionMode,
    PermissionMode,
    SupervisorConfig,
    TaskDelivery,
)
from claude_supervisor.core import Supervisor
from claude_supervisor.resume import ManualClock
from claude_supervisor.state_machine import State
from claude_supervisor.terminal import TIMEOUT, ScriptedTerminal, TerminalManager


class FactoryStub:
    """Returns preset ScriptedTerminals in order and records each argv."""

    def __init__(self, terminals: Sequence[TerminalManager]) -> None:
        self._iter = iter(terminals)
        self.calls: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> TerminalManager:
        self.calls.append(list(command))
        return next(self._iter)


def _run(
    terminals: Sequence[TerminalManager],
    *,
    config: SupervisorConfig | None = None,
    clock: ManualClock | None = None,
) -> tuple[Supervisor, FactoryStub]:
    factory = FactoryStub(terminals)
    supervisor = Supervisor(
        config or SupervisorConfig(),
        factory,
        clock=clock or ManualClock(),
    )
    supervisor.run(["claude"])
    return supervisor, factory


def test_happy_path_completion() -> None:
    term = ScriptedTerminal(["thinking...\n", "Task completed\n"])
    sup, _ = _run([term])
    assert sup.machine.state is State.STOPPED
    assert sup.stats.completed is True
    assert sup.stats.stop_reason == "task completed"


def test_permission_approved_sends_configured_response() -> None:
    cfg = SupervisorConfig(auto_permissions=True, approve_response="1\r")
    term = ScriptedTerminal(["Do you want to proceed?\n", "Task completed\n"])
    sup, _ = _run([term], config=cfg)
    assert term.sent == ["1\r"]  # numbered-menu "Yes" + Enter, sent verbatim
    assert sup.stats.approvals == 1
    assert sup.stats.permission_prompts == 1
    assert sup.stats.completed is True


def test_permission_classic_yn_response_is_configurable() -> None:
    cfg = SupervisorConfig(auto_permissions=True, approve_response="y\r")
    term = ScriptedTerminal(["Proceed? (y/N)\n", "Task completed\n"])
    sup, _ = _run([term], config=cfg)
    assert term.sent == ["y\r"]
    assert sup.stats.approvals == 1


def test_permission_deferred_by_default() -> None:
    term = ScriptedTerminal(["Proceed? (y/N)\n", "Task completed\n"])
    sup, _ = _run([term])  # auto_permissions False by default
    assert term.sent == []
    assert sup.stats.approvals == 0
    assert sup.stats.permission_prompts == 1


def test_permission_deferred_when_never_mode() -> None:
    cfg = SupervisorConfig(auto_permissions=True, permission_mode=PermissionMode.NEVER)
    term = ScriptedTerminal(["Proceed? (y/N)\n", "Task completed\n"])
    _run([term], config=cfg)
    assert term.sent == []


def test_usage_limit_waits_then_resumes_and_completes() -> None:
    clock = ManualClock()
    term1 = ScriptedTerminal(["Usage limit reached. Try again in 1h\n"])
    term2 = ScriptedTerminal(["Resuming session\n", "Task completed\n"])
    sup, factory = _run([term1, term2], clock=clock)

    assert sup.stats.resumes == 1
    assert clock.sleeps == [3600.0]  # waited exactly one hour
    assert sup.stats.total_wait_seconds == 3600.0  # accrued as "hours saved"
    assert len(factory.calls) == 2
    assert factory.calls[0] == ["claude"]
    assert factory.calls[1] == ["claude", "--continue"]
    assert sup.machine.state is State.STOPPED
    assert sup.stats.completed is True
    # The FSM actually passed through the reset/resume states.
    visited = [t.target for t in sup.machine.history]
    assert State.WAITING_FOR_RESET in visited
    assert State.RESUMING in visited


def test_auto_resume_disabled_stops_on_limit() -> None:
    cfg = SupervisorConfig(auto_resume=False)
    clock = ManualClock()
    term = ScriptedTerminal(["Usage limit reached. Try again in 1h\n"])
    sup, _ = _run([term], config=cfg, clock=clock)
    assert sup.stats.resumes == 0
    assert clock.sleeps == []  # never waited
    assert "auto_resume is disabled" in sup.stats.stop_reason
    assert sup.machine.state is State.STOPPED


def test_max_resumes_cap_is_enforced() -> None:
    cfg = SupervisorConfig(max_resumes=1)
    term1 = ScriptedTerminal(["Try again in 1h\n"])
    term2 = ScriptedTerminal(["Usage limit reached. Try again in 1h\n"])
    sup, _ = _run([term1, term2], config=cfg)
    assert sup.stats.resumes == 1
    assert "max_resumes" in sup.stats.stop_reason
    assert sup.machine.state is State.STOPPED


def test_interrupt_during_reset_wait_stops() -> None:
    clock = ManualClock()
    clock.interrupt_on_sleep(1)  # first (only) sleep is interrupted
    term = ScriptedTerminal(["Try again in 1h\n"])
    sup, _ = _run([term], clock=clock)
    assert sup.stats.resumes == 0
    assert "interrupted" in sup.stats.stop_reason
    assert sup.machine.state is State.STOPPED


def test_fatal_error_stops() -> None:
    term = ScriptedTerminal(["fatal error: kaboom\n"])
    sup, _ = _run([term])
    assert sup.stats.error is not None
    assert "fatal" in sup.stats.error.lower()
    assert sup.machine.state is State.STOPPED
    assert sup.stats.completed is False


def test_nonzero_exit_is_unexpected() -> None:
    # A non-zero exit is a genuine unexpected exit (crash / killed), not success.
    term = ScriptedTerminal(["just some output\n"], exit_code=1)
    sup, _ = _run([term])
    assert sup.stats.completed is False
    assert "unexpected exit" in sup.stats.stop_reason
    assert sup.machine.state is State.STOPPED


def test_idle_completes_in_heuristic_mode() -> None:
    # After sustained silence while alive, heuristic mode concludes the turn is
    # done and hands control back.
    cfg = SupervisorConfig(
        completion_mode=CompletionMode.HEURISTIC,
        idle_completion_seconds=1.0,
        read_timeout_seconds=0.5,
    )
    term = ScriptedTerminal(["thinking about it...\n", TIMEOUT, TIMEOUT, TIMEOUT])
    sup, _ = _run([term], config=cfg)
    assert sup.stats.completed is True
    assert "idle" in sup.stats.stop_reason
    assert sup.machine.state is State.STOPPED


def test_idle_does_not_complete_in_strict_mode() -> None:
    # Strict mode never completes on idle (that's heuristic-only); here the run
    # ends via the eventual clean exit, not idle.
    cfg = SupervisorConfig(idle_completion_seconds=1.0, read_timeout_seconds=0.5)
    term = ScriptedTerminal(["working...\n", TIMEOUT, TIMEOUT, TIMEOUT])
    sup, _ = _run([term], config=cfg)
    assert sup.stats.stop_reason == "clean exit"
    assert not any("idle" in t.reason for t in sup.machine.history)


def test_idle_resets_when_output_resumes() -> None:
    # A pause shorter than the threshold, then output, must not complete.
    cfg = SupervisorConfig(
        completion_mode=CompletionMode.HEURISTIC,
        idle_completion_seconds=1.0,
        read_timeout_seconds=0.5,
    )
    # one timeout (0.5s) < 1.0s, then output resets the counter, then complete.
    term = ScriptedTerminal(["step 1\n", TIMEOUT, "step 2\n", "Task completed\n"])
    sup, _ = _run([term], config=cfg)
    assert sup.stats.completed is True
    assert sup.stats.stop_reason == "task completed"  # explicit marker, not idle


def test_clean_exit_is_completion_in_strict_mode() -> None:
    # Real `claude -p` exits 0 with no completion marker; a clean exit counts as
    # completion even in strict mode (only idle detection is heuristic-only).
    term = ScriptedTerminal(["Created hello.txt containing hi\n"], exit_code=0)
    sup, _ = _run([term])  # strict mode (default)
    assert sup.stats.completed is True
    assert sup.stats.stop_reason == "clean exit"
    assert sup.machine.state is State.STOPPED


def test_unexpected_exit_signal_is_logged_not_fatal() -> None:
    # An in-output "process exited" signal is informational; the run continues
    # and still completes normally.
    term = ScriptedTerminal(["process exited with code 1\n", "Task completed\n"])
    sup, _ = _run([term])
    assert sup.stats.completed is True
    assert sup.machine.state is State.STOPPED


def test_run_uses_configured_command_by_default() -> None:
    cfg = SupervisorConfig(claude_command=["claude", "--flag"])
    factory = FactoryStub([ScriptedTerminal(["Task completed\n"])])
    sup = Supervisor(cfg, factory, clock=ManualClock())
    sup.run()  # no explicit command
    assert factory.calls[0] == ["claude", "--flag"]
    assert sup.stats.completed is True


def test_task_delivered_as_argument() -> None:
    cfg = SupervisorConfig()  # task_delivery ARGUMENT by default
    factory = FactoryStub([ScriptedTerminal(["Task completed\n"])])
    sup = Supervisor(cfg, factory, clock=ManualClock())
    sup.run(["claude", "-p"], task="do the thing")
    assert factory.calls[0] == ["claude", "-p", "do the thing"]
    assert sup.stats.completed is True


def test_task_delivered_as_input() -> None:
    cfg = SupervisorConfig(task_delivery=TaskDelivery.INPUT)
    term = ScriptedTerminal(["Task completed\n"])
    factory = FactoryStub([term])
    sup = Supervisor(cfg, factory, clock=ManualClock())
    sup.run(["claude"], task="do X")
    assert factory.calls[0] == ["claude"]  # task not in argv
    assert term.sent == ["do X\r"]  # typed into the session instead
    assert sup.stats.completed is True


def test_no_task_leaves_command_untouched() -> None:
    factory = FactoryStub([ScriptedTerminal(["Task completed\n"])])
    sup = Supervisor(SupervisorConfig(), factory, clock=ManualClock())
    sup.run(["claude"])
    assert factory.calls[0] == ["claude"]


def test_on_line_forwarded_including_across_resume() -> None:
    lines: list[str] = []
    term1 = ScriptedTerminal(["Usage limit reached. Try again in 1h\n"])
    term2 = ScriptedTerminal(["Resuming session\n", "Task completed\n"])
    factory = FactoryStub([term1, term2])
    sup = Supervisor(
        SupervisorConfig(),
        factory,
        clock=ManualClock(),
        on_line=lambda line, _events: lines.append(line),
    )
    sup.run(["claude"])
    assert "Usage limit reached. Try again in 1h" in lines  # first session
    assert "Resuming session" in lines  # listener survived the resume
    assert "Task completed" in lines


def test_stats_as_dict_is_serializable() -> None:
    term = ScriptedTerminal(["Task completed\n"])
    sup, _ = _run([term])
    data = sup.stats.as_dict()
    assert data["completed"] is True
    assert data["resumes"] == 0
    assert isinstance(data["elapsed_seconds"], float)
