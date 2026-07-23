"""Tests for reset-time extraction."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from claude_supervisor.parser.reset_time import extract_reset_delay

NOW = datetime(2026, 7, 11, 10, 0, 0)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Try again in 4h 51m", timedelta(hours=4, minutes=51)),
        ("try again in 30m", timedelta(minutes=30)),
        ("Try again in 2 hours 5 minutes", timedelta(hours=2, minutes=5)),
        ("try again in 45s", timedelta(seconds=45)),
        ("Try again in 1h", timedelta(hours=1)),
    ],
)
def test_relative_durations(text: str, expected: timedelta) -> None:
    result = extract_reset_delay(text, now=NOW)
    assert result is not None
    assert result.kind == "relative"
    assert result.delay == expected


def test_absolute_time_later_today() -> None:
    result = extract_reset_delay("Try again after 15:30", now=NOW)
    assert result is not None
    assert result.kind == "absolute"
    assert result.delay == timedelta(hours=5, minutes=30)


def test_absolute_time_rolls_to_tomorrow() -> None:
    # 09:00 is already past 10:00 now -> should be tomorrow.
    result = extract_reset_delay("Try again after 09:00", now=NOW)
    assert result is not None
    assert result.delay == timedelta(hours=23)


def test_absolute_time_with_pm() -> None:
    result = extract_reset_delay("Try again at 3:30pm", now=NOW)
    assert result is not None
    assert result.delay == timedelta(hours=5, minutes=30)


def test_absolute_time_12am_is_midnight() -> None:
    result = extract_reset_delay("Try again after 12:00am", now=NOW)
    assert result is not None
    # midnight tonight -> 14 hours from 10:00
    assert result.delay == timedelta(hours=14)


def test_relative_preferred_over_absolute() -> None:
    result = extract_reset_delay("Try again in 1h (after 23:00)", now=NOW)
    assert result is not None
    assert result.kind == "relative"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Your limit will reset at 3:30pm", timedelta(hours=5, minutes=30)),
        ("5-hour limit reached. resets at 3pm", timedelta(hours=5)),
        ("resets 3:30pm", timedelta(hours=5, minutes=30)),
        ("limit resets at 15:30", timedelta(hours=5, minutes=30)),
    ],
)
def test_real_world_reset_phrasings(text: str, expected: timedelta) -> None:
    result = extract_reset_delay(text, now=NOW)  # NOW is 10:00
    assert result is not None
    assert result.kind == "absolute"
    assert result.delay == expected


def test_bare_hour_without_ampm_is_ambiguous() -> None:
    assert extract_reset_delay("resets 19", now=NOW) is None


def test_no_reset_info_returns_none() -> None:
    assert extract_reset_delay("Something unrelated happened", now=NOW) is None


def test_invalid_clock_time_returns_none() -> None:
    assert extract_reset_delay("Try again after 99:99", now=NOW) is None


def test_delay_is_never_negative() -> None:
    result = extract_reset_delay("Try again in 5m", now=NOW)
    assert result is not None
    assert result.delay >= timedelta(0)


def test_defaults_to_wallclock_now_when_now_omitted() -> None:
    # Just exercise the default-now branch; relative math is independent of now.
    result = extract_reset_delay("Try again in 10m")
    assert result is not None
    assert result.delay == timedelta(minutes=10)
