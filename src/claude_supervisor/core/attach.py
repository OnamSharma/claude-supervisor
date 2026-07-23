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
import shutil
from datetime import datetime, timedelta

from claude_supervisor.config.models import SupervisorConfig
from claude_supervisor.core.stats import RunStats
from claude_supervisor.logging import get_logger
from claude_supervisor.parser import ClaudeOutputParser, EventType, ParsedEvent
from claude_supervisor.parser.parser import LineListener
from claude_supervisor.resume import Clock, RealClock, ResumePlanner
from claude_supervisor.terminal import TerminalError, TerminalManager
from claude_supervisor.terminal.factory import TerminalFactory
from claude_supervisor.terminal.host import Host

_logger = get_logger("attach")

# After a nudge/relaunch, ignore further usage-limit detections for this long:
# a TUI may keep redrawing the stale limit banner for a while.
_LIMIT_COOLDOWN_SECONDS = 120.0

# Check the host terminal size roughly every N loop iterations (~1s).
_RESIZE_CHECK_EVERY = 8


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
        self._limit_cooldown_until: datetime | None = None
        self._resize_counter = 0
        self._last_size: tuple[int, int] | None = None
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

    def send_interrupt(self) -> None:
        """Forward Ctrl+C to Claude (cancel its current action, not ours)."""
        terminal = self._terminal
        if terminal is not None:
            with contextlib.suppress(TerminalError):
                terminal.send("\x03")

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
                self._handle_events(self.parser.feed(chunk))
            else:
                # The stream went quiet: process whatever is buffered. TUIs often
                # never send a newline, so this is how banner text gets parsed.
                self._handle_events(self.parser.flush())
            self._maybe_nudge()
            self._maybe_resize()

    def _handle_events(self, events: list[ParsedEvent]) -> None:
        for event in events:
            if event.type is EventType.USAGE_LIMIT:
                self._handle_usage_limit(event.raw_line)

    def _handle_usage_limit(self, line: str) -> None:
        if not self.config.auto_resume:
            _logger.info("usage limit seen but auto_resume is disabled")
            return
        if self._resume_at is not None:
            return  # already waiting on this limit
        now = self.clock.now()
        if self._limit_cooldown_until is not None and now < self._limit_cooldown_until:
            return  # stale banner redraw right after a nudge/relaunch
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
            self._limit_cooldown_until = self.clock.now() + timedelta(
                seconds=_LIMIT_COOLDOWN_SECONDS
            )
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
        self._limit_cooldown_until = self.clock.now() + timedelta(seconds=_LIMIT_COOLDOWN_SECONDS)
        return True

    def _maybe_resize(self) -> None:
        """Keep the child PTY sized to the host terminal (checked ~1/second)."""
        self._resize_counter += 1
        if self._resize_counter < _RESIZE_CHECK_EVERY:
            return
        self._resize_counter = 0
        try:
            size = shutil.get_terminal_size()
        except OSError:  # pragma: no cover - no console
            return
        current = (size.lines, size.columns)
        if current == self._last_size:
            return
        self._last_size = current
        terminal = self._terminal
        if terminal is not None:
            with contextlib.suppress(Exception):
                terminal.resize(size.lines, size.columns)

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
