"""Tests for the clock abstraction."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from claude_supervisor.resume import Clock, ManualClock, RealClock


def test_real_and_manual_satisfy_protocol() -> None:
    assert isinstance(RealClock(), Clock)
    assert isinstance(ManualClock(), Clock)


def test_real_clock_now_is_utc() -> None:
    assert RealClock().now().tzinfo is UTC


def test_real_clock_sleep_elapses() -> None:
    clock = RealClock()
    start = time.monotonic()
    assert clock.sleep(0.05) is True
    assert time.monotonic() - start >= 0.04


def test_real_clock_interrupt_returns_early() -> None:
    clock = RealClock()
    clock.interrupt()  # pre-arm
    start = time.monotonic()
    assert clock.sleep(5.0) is False  # returns immediately
    assert time.monotonic() - start < 1.0


def test_real_clock_reset_rearms_sleep() -> None:
    clock = RealClock()
    clock.interrupt()
    assert clock.sleep(5.0) is False
    clock.reset()
    assert clock.sleep(0.01) is True


def test_real_clock_nonpositive_sleep() -> None:
    clock = RealClock()
    assert clock.sleep(0) is True
    clock.interrupt()
    assert clock.sleep(0) is False


def test_manual_clock_records_and_advances() -> None:
    clock = ManualClock(datetime(2026, 1, 1, tzinfo=UTC))
    assert clock.sleep(3600) is True
    assert clock.sleeps == [3600]
    assert clock.now() == datetime(2026, 1, 1, 1, 0, tzinfo=UTC)


def test_manual_clock_interrupt_on_next_sleep() -> None:
    clock = ManualClock()
    clock.interrupt()
    assert clock.sleep(100) is False
    # time does not advance on an interrupted sleep
    assert clock.now() == ManualClock().now()


def test_manual_clock_interrupt_on_specific_sleep() -> None:
    clock = ManualClock()
    clock.interrupt_on_sleep(2)
    assert clock.sleep(10) is True
    assert clock.sleep(10) is False
