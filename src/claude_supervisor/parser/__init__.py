"""Parser subsystem.

Detects meaningful events in Claude Code's output stream (usage limits,
permission prompts, task completion, resume success, fatal errors) using regex
rules that are loaded from *external YAML* — the compatibility layer. This lets
the project adapt to changes in Claude Code's wording without a code release.
"""

from __future__ import annotations

from claude_supervisor.parser.events import EventType, ParsedEvent
from claude_supervisor.parser.parser import ClaudeOutputParser
from claude_supervisor.parser.patterns import (
    PatternSet,
    PatternSetError,
    load_pattern_set,
    strip_ansi,
)
from claude_supervisor.parser.reset_time import ResetDelay, extract_reset_delay

__all__ = [
    "ClaudeOutputParser",
    "EventType",
    "ParsedEvent",
    "PatternSet",
    "PatternSetError",
    "ResetDelay",
    "extract_reset_delay",
    "load_pattern_set",
    "strip_ansi",
]
