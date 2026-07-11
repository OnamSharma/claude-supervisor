"""Time abstraction so waits are interruptible and tests are deterministic.

The real clock waits on a :class:`threading.Event`, which blocks efficiently
(no busy-polling) and can be interrupted immediately on shutdown. The manual
clock records requested sleeps and advances a virtual time, so the reset/resume
flow can be tested without real delays.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """A source of time and interruptible sleep."""

    def now(self) -> datetime:
        """Return the current time (timezone-aware, UTC)."""
        ...

    def sleep(self, seconds: float) -> bool:
        """Sleep up to ``seconds``.

        Returns ``True`` if the full duration elapsed, or ``False`` if the sleep
        was interrupted (e.g. shutdown requested).
        """
        ...

    def interrupt(self) -> None:
        """Wake any in-progress :meth:`sleep` early."""
        ...


class RealClock:
    """Wall-clock time with an interruptible, event-driven sleep."""

    def __init__(self) -> None:
        """Create a clock with a fresh interrupt signal."""
        self._wake = threading.Event()

    def now(self) -> datetime:
        """Return the current UTC time."""
        return datetime.now(UTC)

    def sleep(self, seconds: float) -> bool:
        """Block up to ``seconds`` unless interrupted; return whether it elapsed."""
        if seconds <= 0:
            return not self._wake.is_set()
        interrupted = self._wake.wait(timeout=seconds)
        return not interrupted

    def interrupt(self) -> None:
        """Signal any active sleep to return immediately."""
        self._wake.set()

    def reset(self) -> None:
        """Clear a previous interrupt so the clock can sleep again."""
        self._wake.clear()


class ManualClock:
    """A deterministic clock for tests: virtual time, recorded sleeps."""

    def __init__(self, start: datetime | None = None) -> None:
        """Start virtual time at ``start`` (defaults to a fixed epoch)."""
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)
        self.sleeps: list[float] = []
        self._interrupt_after: int | None = None

    def now(self) -> datetime:
        """Return the current virtual time."""
        return self._now

    def sleep(self, seconds: float) -> bool:
        """Record the requested sleep and advance virtual time.

        If :meth:`interrupt_on_sleep` armed an interrupt, the corresponding
        sleep returns ``False`` without advancing, simulating shutdown.
        """
        self.sleeps.append(seconds)
        if self._interrupt_after is not None and len(self.sleeps) >= self._interrupt_after:
            return False
        self._now += timedelta(seconds=max(0.0, seconds))
        return True

    def interrupt(self) -> None:
        """Arm an interrupt for the next :meth:`sleep` call."""
        self._interrupt_after = len(self.sleeps) + 1

    def interrupt_on_sleep(self, n: int) -> None:
        """Make the ``n``-th (1-based) sleep return interrupted."""
        self._interrupt_after = n
