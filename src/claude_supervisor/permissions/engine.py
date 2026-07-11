"""Permission decision engine.

The engine turns a detected permission prompt into one of three decisions. It is
deliberately small and replaceable (a future policy engine will implement the
same :class:`PermissionEngine` protocol). The default engine encodes the safe
rule from the specification: auto-answer only when the user has opted in *and*
a task is actively running.
"""

from __future__ import annotations

import enum
from typing import Protocol, runtime_checkable

from claude_supervisor.config.models import PermissionMode, SupervisorConfig
from claude_supervisor.logging import get_logger
from claude_supervisor.parser.events import ParsedEvent

_logger = get_logger("permissions")


class PermissionDecision(enum.StrEnum):
    """What to do about a permission prompt.

    Attributes:
        APPROVE: Auto-answer affirmatively.
        REJECT: Auto-answer negatively.
        ASK_HUMAN: Do not answer; leave the prompt for the human.
    """

    APPROVE = "approve"
    REJECT = "reject"
    ASK_HUMAN = "ask_human"


@runtime_checkable
class PermissionEngine(Protocol):
    """Decides how to answer a permission prompt."""

    def decide(self, event: ParsedEvent, *, task_active: bool) -> PermissionDecision:
        """Return the decision for ``event``.

        Args:
            event: The detected permission-prompt event.
            task_active: Whether a task is currently running (state ``RUNNING``).
        """
        ...


class ActiveTaskPermissionEngine:
    """Version 1 engine: approve repetitive prompts, scoped for safety.

    Decision table (given the user's config):

    * ``auto_permissions`` is ``False`` -> always ``ASK_HUMAN``.
    * ``permission_mode == NEVER`` -> always ``ASK_HUMAN``.
    * ``permission_mode == ALWAYS`` -> ``APPROVE``.
    * ``permission_mode == ACTIVE_TASK_ONLY`` -> ``APPROVE`` iff a task is
      active, else ``ASK_HUMAN``.

    It never returns ``REJECT`` itself; rejection is reserved for a future policy
    engine that can classify dangerous operations.
    """

    def __init__(self, config: SupervisorConfig) -> None:
        """Bind the engine to ``config``."""
        self._config = config

    def decide(self, event: ParsedEvent, *, task_active: bool) -> PermissionDecision:
        """Apply the decision table above to ``event``."""
        if not self._config.auto_permissions:
            return self._defer("auto_permissions is disabled")

        mode = self._config.permission_mode
        if mode is PermissionMode.NEVER:
            return self._defer("permission_mode is 'never'")
        if mode is PermissionMode.ALWAYS:
            return self._approve(event)
        # ACTIVE_TASK_ONLY
        if task_active:
            return self._approve(event)
        return self._defer("no task is active")

    def _approve(self, event: ParsedEvent) -> PermissionDecision:
        _logger.info("auto-approving permission prompt: %s", event.raw_line.strip())
        return PermissionDecision.APPROVE

    def _defer(self, why: str) -> PermissionDecision:
        _logger.debug("deferring permission prompt to human (%s)", why)
        return PermissionDecision.ASK_HUMAN
