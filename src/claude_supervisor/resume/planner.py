"""Plan how long to wait after a usage limit before resuming.

Preference order, safest-last:

1. **parsed** -- a concrete delay extracted from Claude's wording.
2. **last_interval** -- the most recently observed reset interval, if any.
3. **default** -- the configured ``default_reset_hours`` fallback.

The planner never shortens a parsed delay; it only supplies a wait when Claude
gives no usable reset information.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from claude_supervisor.logging import get_logger
from claude_supervisor.parser.reset_time import extract_reset_delay

_logger = get_logger("resume")


@dataclass(frozen=True, slots=True)
class ResetPlan:
    """The decided wait before a resume.

    Attributes:
        delay: How long to wait.
        source: ``"parsed"``, ``"last_interval"``, or ``"default"``.
        detail: Human-readable explanation (e.g. the matched phrase).
    """

    delay: timedelta
    source: str
    detail: str

    @property
    def seconds(self) -> float:
        """The delay expressed in seconds."""
        return self.delay.total_seconds()


class ResumePlanner:
    """Compute a :class:`ResetPlan` from a usage-limit line."""

    def __init__(self, *, default_hours: float, last_interval: timedelta | None = None) -> None:
        """Configure the fallback default and an optional last-known interval."""
        if default_hours <= 0:
            raise ValueError("default_hours must be positive")
        self._default = timedelta(hours=default_hours)
        self._last_interval = last_interval

    @property
    def last_interval(self) -> timedelta | None:
        """The most recently learned reset interval, if any."""
        return self._last_interval

    def plan(self, text: str, *, now: datetime | None = None) -> ResetPlan:
        """Return the wait plan for the usage-limit ``text``."""
        parsed = extract_reset_delay(text, now=now)
        if parsed is not None:
            # Learn the interval for future fallbacks.
            self._last_interval = parsed.delay
            plan = ResetPlan(parsed.delay, "parsed", parsed.matched_text)
        elif self._last_interval is not None:
            plan = ResetPlan(self._last_interval, "last_interval", "reusing last known interval")
        else:
            plan = ResetPlan(self._default, "default", "no reset info; using configured default")
        _logger.info("reset plan: wait %s (%s: %s)", plan.delay, plan.source, plan.detail)
        return plan
