"""Tests for the run transcript writer."""

from __future__ import annotations

from pathlib import Path

from claude_supervisor.core import TranscriptWriter
from claude_supervisor.parser.events import EventType, ParsedEvent


def _event(kind: EventType, line: str) -> ParsedEvent:
    return ParsedEvent(type=kind, raw_line=line, pattern="x")


def test_writes_header_and_lines(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "run.txt"
    with TranscriptWriter(path) as t:
        t("hello world", [])
        t("Task completed", [_event(EventType.TASK_COMPLETED, "Task completed")])
    content = path.read_text(encoding="utf-8")
    assert content.startswith("# claude-supervisor transcript")
    assert "hello world\n" in content
    assert "Task completed  <= task_completed\n" in content


def test_skips_empty_noise_lines(tmp_path: Path) -> None:
    path = tmp_path / "run.txt"
    writer = TranscriptWriter(path)
    writer("", [])  # empty and no events -> skipped
    writer("real", [])
    writer.close()
    body = [ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.startswith("#")]
    assert "real" in body
    assert "" not in [ln for ln in body if ln]  # no stray empty content lines


def test_multiple_events_on_one_line(tmp_path: Path) -> None:
    path = tmp_path / "run.txt"
    with TranscriptWriter(path) as t:
        t(
            "limit and done",
            [
                _event(EventType.USAGE_LIMIT, "limit and done"),
                _event(EventType.TASK_COMPLETED, "limit and done"),
            ],
        )
    assert "<= usage_limit, task_completed" in path.read_text(encoding="utf-8")


def test_path_property(tmp_path: Path) -> None:
    path = tmp_path / "run.txt"
    writer = TranscriptWriter(path)
    assert writer.path == path
    writer.close()
