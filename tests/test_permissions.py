"""Tests for the permission decision engine."""

from __future__ import annotations

import pytest

from claude_supervisor.config.models import PermissionMode, SupervisorConfig
from claude_supervisor.parser.events import EventType, ParsedEvent
from claude_supervisor.permissions import (
    ActiveTaskPermissionEngine,
    PermissionDecision,
    PermissionEngine,
)

PROMPT = ParsedEvent(type=EventType.PERMISSION_PROMPT, raw_line="Proceed? (y/N)", pattern="(y/N)")


def _engine(**overrides: object) -> ActiveTaskPermissionEngine:
    return ActiveTaskPermissionEngine(SupervisorConfig(**overrides))


def test_engine_satisfies_protocol() -> None:
    assert isinstance(_engine(), PermissionEngine)


def test_auto_permissions_off_always_defers() -> None:
    engine = _engine(auto_permissions=False)
    assert engine.decide(PROMPT, task_active=True) is PermissionDecision.ASK_HUMAN
    assert engine.decide(PROMPT, task_active=False) is PermissionDecision.ASK_HUMAN


def test_active_task_only_approves_when_active() -> None:
    engine = _engine(auto_permissions=True, permission_mode=PermissionMode.ACTIVE_TASK_ONLY)
    assert engine.decide(PROMPT, task_active=True) is PermissionDecision.APPROVE


def test_active_task_only_defers_when_inactive() -> None:
    engine = _engine(auto_permissions=True, permission_mode=PermissionMode.ACTIVE_TASK_ONLY)
    assert engine.decide(PROMPT, task_active=False) is PermissionDecision.ASK_HUMAN


def test_always_mode_approves_regardless() -> None:
    engine = _engine(auto_permissions=True, permission_mode=PermissionMode.ALWAYS)
    assert engine.decide(PROMPT, task_active=False) is PermissionDecision.APPROVE


def test_never_mode_defers_even_when_active() -> None:
    engine = _engine(auto_permissions=True, permission_mode=PermissionMode.NEVER)
    assert engine.decide(PROMPT, task_active=True) is PermissionDecision.ASK_HUMAN


@pytest.mark.parametrize("active", [True, False])
def test_engine_never_rejects(active: bool) -> None:
    # v1 engine only approves or defers; it never auto-rejects.
    for mode in PermissionMode:
        engine = _engine(auto_permissions=True, permission_mode=mode)
        assert engine.decide(PROMPT, task_active=active) is not PermissionDecision.REJECT
