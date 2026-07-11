"""Tests for the pattern-set compatibility layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_supervisor.parser.events import EventType
from claude_supervisor.parser.patterns import (
    DEFAULT_RULES_PATH,
    PatternSetError,
    load_pattern_set,
    strip_ansi,
)


def test_bundled_rules_load() -> None:
    ps = load_pattern_set()
    assert len(ps) > 0
    assert ps.version >= 1
    # Every canonical event type should have at least one bundled pattern.
    for event in EventType:
        assert ps.patterns_for(event), f"no default pattern for {event}"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_alias_sections_map_to_event_types(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "patterns:\n"
        "  usage_limit: ['limit hit']\n"
        "  permission: ['\\(y/N\\)']\n"
        "  completed: ['all done']\n",
    )
    ps = load_pattern_set(path)
    assert ps.patterns_for(EventType.PERMISSION_PROMPT) == ["\\(y/N\\)"]
    assert ps.match_line("please confirm (y/N)")[0].type is EventType.PERMISSION_PROMPT


def test_match_line_captures_named_groups(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "patterns:\n  usage_limit: ['reached limit for (?P<plan>\\w+) plan']\n",
    )
    ps = load_pattern_set(path)
    events = ps.match_line("You reached limit for pro plan today")
    assert events[0].groups["plan"] == "pro"


def test_ignore_case_default_true(tmp_path: Path) -> None:
    path = _write(tmp_path, "patterns:\n  completed: ['DONE']\n")
    ps = load_pattern_set(path)
    assert ps.match_line("we are done")  # matched case-insensitively


def test_ignore_case_can_be_disabled(tmp_path: Path) -> None:
    path = _write(tmp_path, "ignore_case: false\npatterns:\n  completed: ['DONE']\n")
    ps = load_pattern_set(path)
    assert not ps.match_line("we are done")
    assert ps.match_line("DONE")


def test_unknown_section_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "patterns:\n  wat: ['x']\n")
    with pytest.raises(PatternSetError, match="Unknown pattern section"):
        load_pattern_set(path)


def test_bad_regex_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "patterns:\n  completed: ['(unclosed']\n")
    with pytest.raises(PatternSetError, match="Invalid regex"):
        load_pattern_set(path)


def test_non_list_section_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "patterns:\n  completed: 'not a list'\n")
    with pytest.raises(PatternSetError, match="must map to a list"):
        load_pattern_set(path)


def test_non_string_pattern_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "patterns:\n  completed: [123]\n")
    with pytest.raises(PatternSetError, match="must be a string"):
        load_pattern_set(path)


def test_missing_patterns_key_raises(tmp_path: Path) -> None:
    path = _write(tmp_path, "version: 1\n")
    with pytest.raises(PatternSetError, match="non-empty 'patterns'"):
        load_pattern_set(path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(PatternSetError, match="not found"):
        load_pattern_set(tmp_path / "absent.yaml")


def test_default_rules_path_points_at_bundled_file() -> None:
    assert DEFAULT_RULES_PATH.exists()


def test_same_type_matched_once_per_line() -> None:
    # A real usage-limit line matches multiple usage_limit patterns; it must
    # still yield exactly one event so it never triggers a duplicate reaction.
    ps = load_pattern_set()
    events = ps.match_line("Usage limit reached. Try again in 4h 51m")
    usage = [e for e in events if e.type is EventType.USAGE_LIMIT]
    assert len(usage) == 1


def test_strip_ansi_removes_escapes_and_controls() -> None:
    assert strip_ansi("\x1b[31mred\x1b[0m") == "red"
    assert strip_ansi("\x1b[1t\x1b[?1004htext") == "text"
    assert strip_ansi("\x1b]0;title\x07body") == "body"
    assert strip_ansi("a\x07b") == "ab"  # BEL stripped
    assert strip_ansi("keep\ttab\r\n") == "keep\ttab\r\n"  # tab/CR/LF preserved


def test_detection_survives_ansi_formatting() -> None:
    # A real TUI colours and decorates its output; detection must see through it.
    ps = load_pattern_set()
    line = "\x1b[1m\x1b[32mTask completed\x1b[0m\x1b[?25h"
    events = ps.match_line(line)
    assert events
    assert events[0].type is EventType.TASK_COMPLETED
    assert events[0].raw_line == "Task completed"  # cleaned for logs


def test_ansi_wrapped_usage_limit_still_parses_reset() -> None:
    ps = load_pattern_set()
    line = "\x1b[33mUsage limit reached.\x1b[0m Try again in 2s"
    events = ps.match_line(line)
    assert any(e.type is EventType.USAGE_LIMIT for e in events)
    assert "Try again in 2s" in events[0].raw_line


def test_different_types_on_one_line_all_reported(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "patterns:\n  usage_limit: ['limit']\n  completed: ['done']\n",
    )
    ps = load_pattern_set(path)
    events = ps.match_line("limit reached but task is done")
    types = {e.type for e in events}
    assert types == {EventType.USAGE_LIMIT, EventType.TASK_COMPLETED}
