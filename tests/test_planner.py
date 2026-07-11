"""Tests for the resume planner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from claude_supervisor.resume import ResumePlanner

NOW = datetime(2026, 7, 11, 10, 0, tzinfo=UTC)


def test_parsed_delay_is_used_and_learned() -> None:
    planner = ResumePlanner(default_hours=5)
    plan = planner.plan("Usage limit reached. Try again in 2h 30m", now=NOW)
    assert plan.source == "parsed"
    assert plan.delay == timedelta(hours=2, minutes=30)
    assert plan.seconds == 9000
    # The parsed interval is remembered for later fallbacks.
    assert planner.last_interval == timedelta(hours=2, minutes=30)


def test_falls_back_to_last_interval() -> None:
    planner = ResumePlanner(default_hours=5, last_interval=timedelta(hours=1))
    plan = planner.plan("Usage limit reached (no time given)", now=NOW)
    assert plan.source == "last_interval"
    assert plan.delay == timedelta(hours=1)


def test_falls_back_to_default() -> None:
    planner = ResumePlanner(default_hours=4)
    plan = planner.plan("Usage limit reached with no info", now=NOW)
    assert plan.source == "default"
    assert plan.delay == timedelta(hours=4)


def test_learned_interval_survives_a_missing_one() -> None:
    planner = ResumePlanner(default_hours=5)
    planner.plan("Try again in 3h", now=NOW)  # learns 3h
    plan = planner.plan("limit, no info", now=NOW)  # should reuse 3h, not default
    assert plan.source == "last_interval"
    assert plan.delay == timedelta(hours=3)


def test_default_hours_must_be_positive() -> None:
    with pytest.raises(ValueError, match="default_hours"):
        ResumePlanner(default_hours=0)
