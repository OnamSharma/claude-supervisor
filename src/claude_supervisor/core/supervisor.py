"""The Supervisor: a safe, human-in-control run loop over a Claude Code session.

The loop reads Claude's output, detects events, and reacts:

* **permission prompt** -> ask the permission engine; auto-answer only if allowed.
* **usage limit** -> wait for the legitimate reset, then resume the session.
* **task completed** -> stop and hand control back to the human.
* **fatal error / unexpected exit** -> stop safely.

Safety invariants, enforced structurally:

* Once a task completes the machine reaches ``TASK_COMPLETED`` -> ``STOPPED`` and
  never resumes work on its own.
* Auto-answering requires explicit opt-in and (by default) an active task.
* Waits are interruptible; a stop request always wins.
"""

from __future__ import annotations

from collections.abc import Sequence

from claude_supervisor.config.models import CompletionMode, SupervisorConfig, TaskDelivery
from claude_supervisor.core.stats import RunStats
from claude_supervisor.logging import get_logger
from claude_supervisor.parser import ClaudeOutputParser, EventType, ParsedEvent
from claude_supervisor.parser.parser import LineListener
from claude_supervisor.permissions import (
    ActiveTaskPermissionEngine,
    PermissionDecision,
    PermissionEngine,
)
from claude_supervisor.resume import Clock, RealClock, ResumePlanner
from claude_supervisor.state_machine import State, StateMachine
from claude_supervisor.terminal import TerminalManager
from claude_supervisor.terminal.factory import TerminalFactory

_logger = get_logger("supervisor")


class Supervisor:
    """Orchestrates one supervised Claude Code run.

    All collaborators are injectable so the whole loop is testable without a
    real process or real delays. Defaults wire up the production implementations.
    """

    def __init__(
        self,
        config: SupervisorConfig,
        terminal_factory: TerminalFactory,
        *,
        parser: ClaudeOutputParser | None = None,
        clock: Clock | None = None,
        permission_engine: PermissionEngine | None = None,
        planner: ResumePlanner | None = None,
        machine: StateMachine | None = None,
        on_line: LineListener | None = None,
    ) -> None:
        """Wire up the supervisor with ``config`` and a ``terminal_factory``."""
        self.config = config
        self._factory = terminal_factory
        self._on_line = on_line
        self.parser = parser or ClaudeOutputParser.from_rules(
            config.paths.pattern_rules, on_line=on_line
        )
        self.clock = clock or RealClock()
        self.permissions = permission_engine or ActiveTaskPermissionEngine(config)
        self.planner = planner or ResumePlanner(default_hours=config.default_reset_hours)
        self.machine = machine or StateMachine()
        self.stats = RunStats()
        self._terminal: TerminalManager | None = None
        self._stop_requested = False
        self._idle_seconds = 0.0

    # --- public API --------------------------------------------------------
    def run(self, command: Sequence[str] | None = None, *, task: str | None = None) -> RunStats:
        """Run the supervised session to completion (or safe stop).

        Args:
            command: Argv to launch. Defaults to ``config.claude_command``.
            task: Optional task to hand to Claude for an unattended run. Delivered
                per ``config.task_delivery`` -- appended as an argument, or typed
                as input once the session is running.

        Returns:
            The :class:`RunStats` for the run.
        """
        argv = list(command) if command is not None else list(self.config.claude_command)
        if task and self.config.task_delivery is TaskDelivery.ARGUMENT:
            argv.append(task)

        self._spawn(argv)
        self.machine.transition(State.RUNNING, "claude started")
        if task and self.config.task_delivery is TaskDelivery.INPUT:
            self._deliver_task_as_input(task)
        try:
            self._loop()
        finally:
            self._shutdown()
        return self.stats

    def _deliver_task_as_input(self, task: str) -> None:
        """Type the task into a freshly started interactive session."""
        assert self._terminal is not None
        _logger.info("delivering task as input (%d chars)", len(task))
        self._terminal.send_line(task)

    def request_stop(self, reason: str = "stop requested") -> None:
        """Ask the loop to stop at the next opportunity (e.g. from a signal)."""
        _logger.info("stop requested: %s", reason)
        self._stop_requested = True
        if not self.stats.stop_reason:
            self.stats.stop_reason = reason
        self.clock.interrupt()

    # --- loop --------------------------------------------------------------
    def _loop(self) -> None:
        while not self._should_stop():
            terminal = self._terminal
            if terminal is None:  # pragma: no cover - defensive
                break
            chunk = terminal.read(self.config.read_timeout_seconds)
            if chunk is None:
                self._handle_eof()
                continue
            if not chunk:
                self._note_idle_tick()  # timeout: no output this interval
                continue
            self._idle_seconds = 0.0  # output arrived: not idle
            for event in self.parser.feed(chunk):
                self._handle_event(event)
                if self._should_stop():
                    return

    def _should_stop(self) -> bool:
        return self._stop_requested or self.machine.is_terminal

    def _note_idle_tick(self) -> None:
        """Accrue idle time; in heuristic mode, complete after sustained silence.

        A live process that has stopped producing output is Claude idling at the
        prompt, waiting for the human -- i.e. the turn is done. Concluding
        "completed" here only hands control back (a safe, non-destructive act),
        so it is gated to heuristic mode and never fires in strict mode.
        """
        if self.config.completion_mode is not CompletionMode.HEURISTIC:
            return
        if self.machine.state is not State.RUNNING:
            return
        self._idle_seconds += self.config.read_timeout_seconds
        if self._idle_seconds < self.config.idle_completion_seconds:
            return
        if self._terminal is None or not self._terminal.is_alive():
            return  # a dead process is handled by the EOF path, not idle
        _logger.info(
            "no output for %.1fs while running; treating as completed (idle at prompt)",
            self._idle_seconds,
        )
        self.machine.transition(State.TASK_COMPLETED, "idle (awaiting input)")
        self.stats.completed = True
        self.stats.stop_reason = "idle (awaiting input)"
        self._stop_requested = True

    # --- event handling ----------------------------------------------------
    def _handle_event(self, event: ParsedEvent) -> None:
        match event.type:
            case EventType.PERMISSION_PROMPT:
                self._handle_permission(event)
            case EventType.USAGE_LIMIT:
                self._handle_usage_limit(event)
            case EventType.TASK_COMPLETED:
                self._handle_completion(event)
            case EventType.FATAL_ERROR:
                self._handle_fatal(event)
            case EventType.RESUME_SUCCESS:
                _logger.info("resume confirmed by Claude output")
            case EventType.UNEXPECTED_EXIT:
                _logger.warning("unexpected-exit signal in output: %s", event.raw_line.strip())

    def _handle_permission(self, event: ParsedEvent) -> None:
        self.stats.permission_prompts += 1
        task_active = self.machine.state is State.RUNNING
        decision = self.permissions.decide(event, task_active=task_active)

        if decision is PermissionDecision.ASK_HUMAN:
            _logger.info("leaving permission prompt for the human to answer")
            return

        approving = decision is PermissionDecision.APPROVE
        response = self.config.approve_response if approving else self.config.reject_response
        assert self._terminal is not None
        # Model the prompt explicitly in the state machine: RUNNING -> waiting -> RUNNING.
        if self.machine.state is State.RUNNING:
            self.machine.transition(State.WAITING_FOR_PERMISSION, "permission prompt")
        self._terminal.send(response)
        if approving:
            self.stats.approvals += 1
        if self.machine.state is State.WAITING_FOR_PERMISSION:
            self.machine.transition(State.RUNNING, "approved" if approving else "rejected")

    def _handle_usage_limit(self, event: ParsedEvent) -> None:
        if not self.config.auto_resume:
            self.request_stop("usage limit reached and auto_resume is disabled")
            return
        if self._resume_cap_reached():
            self.request_stop(f"reached max_resumes ({self.config.max_resumes})")
            return

        plan = self.planner.plan(event.raw_line, now=self.clock.now())
        self.machine.transition(
            State.WAITING_FOR_RESET, f"usage limit; waiting {plan.delay} ({plan.source})"
        )
        # The current session is done producing; let it go before we wait.
        self._terminate_terminal()

        elapsed = self.clock.sleep(plan.seconds)
        if not elapsed or self._stop_requested:
            self.request_stop("interrupted while waiting for reset")
            return

        # The wait completed unattended -- time the user did not have to spend
        # watching for the reset and manually resuming.
        self.stats.total_wait_seconds += plan.seconds
        self._resume()

    def _handle_completion(self, event: ParsedEvent) -> None:
        _logger.info("task completed: %s", event.raw_line.strip())
        self.machine.transition(State.TASK_COMPLETED, "completion detected")
        self.stats.completed = True
        self.stats.stop_reason = "task completed"
        self._stop_requested = True

    def _handle_fatal(self, event: ParsedEvent) -> None:
        _logger.error("fatal error detected: %s", event.raw_line.strip())
        self.stats.error = event.raw_line.strip()
        self.request_stop("fatal error detected")

    def _handle_eof(self) -> None:
        exit_code = self._terminal.exit_code() if self._terminal else None
        if self.machine.state is not State.RUNNING:
            # EOF outside RUNNING (e.g. we already terminated during a reset).
            return
        # A clean exit (code 0, or unknown) means the program finished normally.
        # Real `claude -p` prints its answer and exits 0 with no textual "done"
        # marker, so a clean exit *is* completion -- in both strict and heuristic
        # modes. The strict/heuristic distinction governs only idle detection.
        if exit_code in (0, None):
            _logger.info("process exited cleanly (code=%s); treating as completed", exit_code)
            self.machine.transition(State.TASK_COMPLETED, "clean exit")
            self.stats.completed = True
            self.stats.stop_reason = "clean exit"
        else:
            _logger.warning("Claude exited unexpectedly (code=%s)", exit_code)
            self.stats.stop_reason = self.stats.stop_reason or f"unexpected exit (code={exit_code})"
        self._stop_requested = True

    # --- resume / lifecycle helpers ---------------------------------------
    def _resume(self) -> None:
        self.machine.transition(State.RESUMING, "reset elapsed")
        self.stats.resumes += 1
        self._spawn(tuple(self.config.resume_command))
        # Fresh parser buffer for the new stream; keep the compiled patterns.
        self.parser = ClaudeOutputParser(self.parser.pattern_set, on_line=self._on_line)
        self._idle_seconds = 0.0  # the resumed session is producing output again
        self.machine.transition(State.RUNNING, "resumed session")

    def _resume_cap_reached(self) -> bool:
        cap = self.config.max_resumes
        return cap > 0 and self.stats.resumes >= cap

    def _spawn(self, argv: Sequence[str]) -> None:
        _logger.info("launching: %s", " ".join(argv))
        terminal = self._factory(argv)
        terminal.start()
        self._terminal = terminal

    def _terminate_terminal(self) -> None:
        if self._terminal is not None and self._terminal.is_alive():
            self._terminal.terminate()

    def _shutdown(self) -> None:
        self._terminate_terminal()
        if not self.stats.stop_reason:
            self.stats.stop_reason = "loop ended"
        if self.machine.can_transition(State.STOPPED):
            self.machine.transition(State.STOPPED, self.stats.stop_reason)
        self.stats.finished_at = self.clock.now()
        _logger.info("supervisor stopped: %s", self.stats.as_dict())
