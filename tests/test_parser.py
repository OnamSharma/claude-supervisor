"""Tests for the streaming ClaudeOutputParser."""

from __future__ import annotations

import re

from claude_supervisor.parser import ClaudeOutputParser, EventType
from claude_supervisor.parser.parser import _MAX_BUFFER_CHARS
from claude_supervisor.parser.patterns import PatternSet, load_pattern_set


def _parser() -> ClaudeOutputParser:
    return ClaudeOutputParser.from_rules()


def test_from_rules_uses_bundled_patterns() -> None:
    p = _parser()
    assert isinstance(p.pattern_set, PatternSet)
    assert len(p.pattern_set) > 0


def test_complete_line_emits_event() -> None:
    p = _parser()
    events = p.feed("Usage limit reached\n")
    assert any(e.type is EventType.USAGE_LIMIT for e in events)


def test_partial_line_is_buffered_until_newline() -> None:
    p = _parser()
    assert p.feed("Usage limit ") == []  # nothing yet
    events = p.feed("reached\n")
    assert any(e.type is EventType.USAGE_LIMIT for e in events)


def test_split_across_many_chunks() -> None:
    p = _parser()
    collected = []
    for ch in "Task completed\n":
        collected.extend(p.feed(ch))
    assert any(e.type is EventType.TASK_COMPLETED for e in collected)


def test_multiple_lines_in_one_chunk() -> None:
    p = _parser()
    events = p.feed("hello world\nUsage limit reached\nall done\n")
    types = {e.type for e in events}
    assert EventType.USAGE_LIMIT in types
    assert EventType.TASK_COMPLETED in types


def test_flush_processes_trailing_prompt_without_newline() -> None:
    p = _parser()
    # Interactive prompts often lack a trailing newline.
    assert p.feed("Proceed? (y/N) ") == []
    events = p.flush()
    assert any(e.type is EventType.PERMISSION_PROMPT for e in events)
    assert p.flush() == []  # buffer cleared


def test_empty_feed_is_noop() -> None:
    assert _parser().feed("") == []


def test_oversized_buffer_is_evaluated_and_reset() -> None:
    # A degenerate producer that never emits a newline but eventually prints a
    # recognizable prompt should still trigger once the buffer cap is hit.
    ps = load_pattern_set()
    p = ClaudeOutputParser(ps)
    filler = "x" * (_MAX_BUFFER_CHARS - 10)
    assert p.feed(filler) == []
    events = p.feed("(y/N)" + "y" * 20)
    assert any(e.type is EventType.PERMISSION_PROMPT for e in events)


def test_carriage_returns_are_stripped() -> None:
    p = _parser()
    events = p.feed("Task completed\r\n")
    assert events
    assert "\r" not in events[0].raw_line


def test_custom_pattern_set_can_be_injected() -> None:
    ps = PatternSet([])  # no rules -> matches nothing
    p = ClaudeOutputParser(ps)
    assert p.feed("anything at all\n") == []


def test_event_groups_are_immutable() -> None:
    p = _parser()
    events = p.feed("Usage limit reached\n")
    event = events[0]
    try:
        event.groups["x"] = "y"  # type: ignore[index]
    except TypeError:
        pass
    else:  # pragma: no cover - MappingProxyType must reject mutation
        raise AssertionError("groups mapping should be read-only")


def test_on_line_listener_receives_every_line_and_events() -> None:
    seen: list[tuple[str, list[str]]] = []

    def listener(line: str, events: list) -> None:
        seen.append((line, [e.type.value for e in events]))

    p = ClaudeOutputParser.from_rules(on_line=listener)
    p.feed("just chatting\n\x1b[32mTask completed\x1b[0m\n")
    assert seen[0] == ("just chatting", [])
    assert seen[1] == ("Task completed", ["task_completed"])  # ANSI stripped, event tagged


def test_on_line_listener_fires_on_flush() -> None:
    seen: list[str] = []
    p = ClaudeOutputParser.from_rules(on_line=lambda line, _events: seen.append(line))
    p.feed("Proceed? (y/N)")  # no newline
    assert seen == []
    p.flush()
    assert seen == ["Proceed? (y/N)"]


def test_bundled_patterns_are_valid_regex() -> None:
    for event in EventType:
        for pat in load_pattern_set().patterns_for(event):
            re.compile(pat)  # must not raise
