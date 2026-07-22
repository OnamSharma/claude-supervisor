"""Attach mode: supervise your *live, interactive* Claude Code session.

A transparent proxy — your keystrokes go straight to Claude, Claude's output
goes straight to your screen — while the supervisor quietly watches the stream.
When a usage limit appears it parses the reset time, waits it out (you can walk
away), and then nudges the session to continue. If Claude exited in the
meantime, it relaunches with ``--continue``.

You stay in control the whole time; press Ctrl+] to detach.
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta

from claude_supervisor.config.models import SupervisorConfig
from claude_supervisor.core.stats import RunStats
from claude_supervisor.logging import get_logger
from claude_supervisor.parser import ClaudeOutputParser, EventType
from claude_supervisor.parser.parser import LineListener
from claude_supervisor.resume import Clock, RealClock, ResumePlanner
from claude_supervisor.terminal import TerminalError, TerminalManager
from claude_supervisor.terminal.factory import TerminalFactory
from claude_supervisor.terminal.host import Host

_logger = get_logger("attach")


class AttachSession:
    """Proxy a live interactive session and auto-continue after limit resets."""

    def __init__(
        self,
        config: SupervisorConfig,
        terminal_factory: TerminalFactory,
        host: Host,
        *,
        parser: ClaudeOutputParser | None = None,
        clock: Clock | None = None,
        planner: ResumePlanner | None = None,
        on_line: LineListener | None = None,
    ) -> None:
        """Wire up the session with its collaborators (all injectable)."""
        self.config = config
        self._factory = terminal_factory
        self._host = host
        self._on_line = on_line
        self.parser = parser or ClaudeOutputParser.from_rules(
            config.paths.pattern_rules, on_line=on_line
        )
        self.clock = clock or RealClock()
        self.planner = planner or ResumePlanner(default_hours=config.default_reset_hours)
        self.stats = RunStats()
        self._terminal: TerminalManager | None = None
        self._resume_at: datetime | None = None
        self._stop = False

    # -- public --------------------------------------------------------------
    def run(self) -> RunStats:
        """Attach until the user detaches or the session genuinely ends."""
        self._spawn(list(self.config.attach_command))
        self._host.start(self._on_input, self._on_detach)
        try:
            self._loop()
        finally:
            self._host.restore()
            self._terminate_terminal()
            self.stats.finished_at = self.clock.now()
            if not self.stats.stop_reason:
                self.stats.stop_reason = "detached"
            _logger.info("attach ended: %s", self.stats.as_dict())
        return self.stats

    # -- host callbacks (run on the input thread) -----------------------------
    def _on_input(self, data: str) -> None:
        terminal = self._terminal
        if terminal is None:
            return
        # If the child died a moment ago, the main loop will notice and handle it.
        with contextlib.suppress(TerminalError):
            terminal.send(data)

    def _on_detach(self) -> None:
        _logger.info("detach requested by user")
        self.stats.stop_reason = "detached"
        self._stop = True
        self.clock.interrupt()

    # -- main loop ------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop:
            terminal = self._terminal
            if terminal is None:  # pragma: no cover - defensive
                return
            chunk = terminal.read(0.15)

            if chunk is None:  # child exited
                if not self._handle_child_exit():
                    return
                continue
            if chunk:
                self._host.write(chunk)
                for event in self.parser.feed(chunk):
                    if event.type is EventType.USAGE_LIMIT:
                        self._handle_usage_limit(event.raw_line)
            self._maybe_nudge()

    def _handle_usage_limit(self, line: str) -> None:
        if not self.config.auto_resume:
            _logger.info("usage limit seen but auto_resume is disabled")
            return
        if self._resume_at is not None:
            return  # already waiting on this limit
        if self._cap_reached():
            _logger.warning("usage limit seen but max_resumes reached; not scheduling")
            return
        plan = self.planner.plan(line, now=self.clock.now())
        buffer = timedelta(seconds=self.config.attach_resume_buffer_seconds)
        self._resume_at = self.clock.now() + plan.delay + buffer
        self.stats.total_wait_seconds += plan.seconds
        _logger.info(
            "usage limit detected; will auto-continue at %s (%s + %ss buffer, %s)",
            self._resume_at.isoformat(),
            plan.delay,
            self.config.attach_resume_buffer_seconds,
            plan.source,
        )

    def _maybe_nudge(self) -> None:
        if self._resume_at is None or self.clock.now() < self._resume_at:
            return
        terminal = self._terminal
        self._resume_at = None
        if terminal is None or not terminal.is_alive():  # pragma: no cover - raced exit
            return
        _logger.info("reset passed; nudging the session to continue")
        try:
            terminal.send(self.config.nudge_message + "\r")
            self.stats.resumes += 1
        except TerminalError:  # pragma: no cover - child died at the same moment
            _logger.warning("could not nudge; session no longer accepts input")

    def _handle_child_exit(self) -> bool:
        """React to the child ending. Returns True to keep looping."""
        if self._resume_at is None:
            _logger.info("claude exited; ending attach")
            self.stats.stop_reason = "claude exited"
            return False
        # Claude died while a reset wait is pending: wait it out, then relaunch
        # the conversation with --continue.
        self._wait_until(self._resume_at)
        self._resume_at = None
        if self._stop:
            return False
        if self._cap_reached():
            self.stats.stop_reason = f"reached max_resumes ({self.config.max_resumes})"
            return False
        _logger.info("reset passed; relaunching with --continue")
        try:
            self._spawn([*self.config.attach_command, "--continue"])
        except TerminalError as exc:
            _logger.error("could not relaunch claude: %s", exc)
            self.stats.stop_reason = "relaunch failed"
            self.stats.error = str(exc)
            return False
        self.parser = ClaudeOutputParser(self.parser.pattern_set, on_line=self._on_line)
        self.stats.resumes += 1
        return True

    # -- helpers --------------------------------------------------------------
    def _wait_until(self, deadline: datetime) -> None:
        while not self._stop:
            remaining = (deadline - self.clock.now()).total_seconds()
            if remaining <= 0:
                return
            self.clock.sleep(min(remaining, 1.0))

    def _cap_reached(self) -> bool:
        cap = self.config.max_resumes
        return cap > 0 and self.stats.resumes >= cap

    def _spawn(self, argv: list[str]) -> None:
        _logger.info("launching: %s", " ".join(argv))
        terminal = self._factory(argv)
        terminal.start()
        self._terminal = terminal

    def _terminate_terminal(self) -> None:
        if self._terminal is not None and self._terminal.is_alive():
            self._terminal.terminate()
