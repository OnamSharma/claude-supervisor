"""Real-PTY end-to-end tests.

These spawn an actual Python subprocess inside a real pseudo-terminal via the
platform backend (pywinpty on Windows, pexpect on POSIX), exercising the code
paths that unit tests deliberately stub. They are skipped cleanly when no PTY
backend is installed.

They guard against regressions in two things a real PTY exposed that scripted
tests could not: ANSI/VT escape sequences in the stream, and the fact that a
terminal's "Enter" is a carriage return, not a line feed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from claude_supervisor.config.models import (
    CompletionMode,
    PermissionMode,
    SupervisorConfig,
    TaskDelivery,
)
from claude_supervisor.core import AttachSession, Supervisor, TranscriptWriter
from claude_supervisor.state_machine import State
from claude_supervisor.terminal import terminal_factory
from claude_supervisor.terminal.host import FakeHost

# These drive real subprocesses in a PTY, so they are timing-sensitive on loaded
# CI runners. Auto-retry them a couple of times: a genuine failure fails every
# attempt, while a scheduling flake passes on retry. Grace pauses before a mock
# exits (below) give the pseudo-console time to flush its final output.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.flaky(reruns=2, reruns_delay=2),
]


def _require_backend() -> None:
    pytest.importorskip("winpty" if os.name == "nt" else "pexpect")


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_real_pty_detects_completion(tmp_path: Path) -> None:
    _require_backend()
    mock = _write(
        tmp_path / "mock.py",
        # Colour codes verify ANSI stripping on a real stream. The brief pause
        # before exit mirrors real Claude (which idles at the prompt, not exits
        # instantly) and avoids a ConPTY fast-exit output-flush race.
        "import sys, time\n"
        "print('\\x1b[32mTask completed\\x1b[0m', flush=True)\n"
        "time.sleep(1.0)\n"
        "sys.exit(0)\n",
    )
    config = SupervisorConfig(
        claude_command=[sys.executable, "-u", str(mock)],
        read_timeout_seconds=0.2,
    )
    supervisor = Supervisor(config, terminal_factory())
    stats = supervisor.run()
    assert stats.completed is True
    assert supervisor.machine.state is State.STOPPED


def test_real_pty_full_flow_wait_resume_permission(tmp_path: Path) -> None:
    _require_backend()
    claude = _write(
        tmp_path / "claude.py",
        "import sys\n"
        "print('\\x1b[33mUsage limit reached.\\x1b[0m Try again in 1s', flush=True)\n"
        "sys.exit(0)\n",
    )
    resume = _write(
        tmp_path / "resume.py",
        # Prompt, then block on input: the run only proceeds if send_line's
        # carriage return actually reaches the child's stdin.
        "import sys, time\n"
        "print('Resuming session', flush=True)\n"
        "print('Do you want to proceed?', flush=True)\n"
        "sys.stdin.readline()\n"
        "print('\\x1b[1mTask completed\\x1b[0m', flush=True)\n"
        "time.sleep(1.0)\n"
        "sys.exit(0)\n",
    )
    config = SupervisorConfig(
        auto_resume=True,
        auto_permissions=True,
        permission_mode=PermissionMode.ACTIVE_TASK_ONLY,
        claude_command=[sys.executable, "-u", str(claude)],
        resume_command=[sys.executable, "-u", str(resume)],
        read_timeout_seconds=0.2,
    )
    supervisor = Supervisor(config, terminal_factory())
    stats = supervisor.run()

    assert stats.completed is True
    assert stats.resumes == 1
    assert stats.approvals == 1
    assert stats.permission_prompts == 1
    assert supervisor.machine.state is State.STOPPED


def test_real_pty_task_as_argument(tmp_path: Path) -> None:
    _require_backend()
    # The mock echoes its argv task, proving argument delivery reaches the child.
    mock = _write(
        tmp_path / "mock.py",
        "import sys, time\n"
        "task = sys.argv[1] if len(sys.argv) > 1 else '(none)'\n"
        "print('running:', task, flush=True)\n"
        "assert task == 'ship it'\n"
        "print('Task completed', flush=True)\n"
        "time.sleep(1.0)\n",
    )
    config = SupervisorConfig(
        claude_command=[sys.executable, "-u", str(mock)],
        read_timeout_seconds=0.2,
    )
    supervisor = Supervisor(config, terminal_factory())
    stats = supervisor.run(task="ship it")
    assert stats.completed is True  # the assert in the child would fail the turn otherwise
    assert supervisor.machine.state is State.STOPPED


def test_real_pty_task_as_input(tmp_path: Path) -> None:
    _require_backend()
    # The mock reads its task from stdin, proving input delivery works on a PTY.
    mock = _write(
        tmp_path / "mock.py",
        "import sys, time\n"
        "print('ready', flush=True)\n"
        "task = sys.stdin.readline().strip()\n"
        "print('got:', task, flush=True)\n"
        "print('Task completed' if task == 'ship it' else 'wrong', flush=True)\n"
        "time.sleep(1.0)\n",
    )
    config = SupervisorConfig(
        task_delivery=TaskDelivery.INPUT,
        claude_command=[sys.executable, "-u", str(mock)],
        read_timeout_seconds=0.2,
    )
    supervisor = Supervisor(config, terminal_factory())
    stats = supervisor.run(task="ship it")
    assert stats.completed is True
    assert supervisor.machine.state is State.STOPPED


def test_real_pty_transcript_capture(tmp_path: Path) -> None:
    _require_backend()
    mock = _write(
        tmp_path / "mock.py",
        "import sys, time\n"
        "print('\\x1b[36mworking on it\\x1b[0m', flush=True)\n"
        "print('Task completed', flush=True)\n"
        "time.sleep(1.0)\n",
    )
    capture = tmp_path / "cap.txt"
    config = SupervisorConfig(
        claude_command=[sys.executable, "-u", str(mock)],
        read_timeout_seconds=0.2,
    )
    writer = TranscriptWriter(capture)
    supervisor = Supervisor(config, terminal_factory(), on_line=writer)
    supervisor.run()
    writer.close()

    text = capture.read_text(encoding="utf-8")
    assert "working on it" in text  # ANSI stripped from a real PTY stream
    assert "Task completed  <= task_completed" in text  # event tagged


def test_real_pty_attach_detects_tui_banner_and_nudges(tmp_path: Path) -> None:
    """The attach flow against a TUI-style child on a real PTY.

    The mock behaves like a real TUI: clears the screen and prints the limit
    banner with NO newline, then blocks waiting for input. The supervisor must
    flush-parse the quiet stream, wait out the (1s) reset, and type the nudge —
    which only works end-to-end if the carriage return actually reaches stdin.
    """
    _require_backend()
    mock = _write(
        tmp_path / "tui.py",
        "import sys, time\n"
        "sys.stdout.write('\\x1b[2J\\x1b[H')  # clear screen like a TUI\n"
        "sys.stdout.write('\\x1b[33mUsage limit reached.\\x1b[0m Try again in 1s')\n"
        "sys.stdout.flush()  # note: NO newline after the banner\n"
        "line = sys.stdin.readline()\n"
        "print('got:', line.strip(), '- resuming work', flush=True)\n"
        "time.sleep(1.0)\n",
    )
    config = SupervisorConfig(
        attach_command=[sys.executable, "-u", str(mock)],
        attach_resume_buffer_seconds=0.0,
    )
    host = FakeHost()
    session = AttachSession(config, terminal_factory(), host)
    stats = session.run()

    assert stats.resumes == 1  # the nudge was sent and counted
    blob = "".join(host.written)
    assert "resuming work" in blob  # the child actually received the nudge
    assert stats.stop_reason == "claude exited"


def test_real_pty_idle_completion(tmp_path: Path) -> None:
    _require_backend()
    # Prints once, then stays alive but silent (idle at the "prompt"). Heuristic
    # mode should conclude the turn is done and hand control back while the
    # process is still running.
    mock = _write(
        tmp_path / "idle.py",
        "import sys, time\nprint('doing work', flush=True)\ntime.sleep(30)\n",
    )
    config = SupervisorConfig(
        completion_mode=CompletionMode.HEURISTIC,
        idle_completion_seconds=1.0,
        read_timeout_seconds=0.3,
        claude_command=[sys.executable, "-u", str(mock)],
    )
    supervisor = Supervisor(config, terminal_factory())
    stats = supervisor.run()
    assert stats.completed is True
    assert "idle" in stats.stop_reason
    assert supervisor.machine.state is State.STOPPED
