"""The streaming Claude output parser.

Terminal output arrives in arbitrary chunks, not tidy lines. This parser
buffers partial lines, splits on newlines, and applies a :class:`PatternSet`
to each complete line, emitting :class:`ParsedEvent` objects.
"""

from __future__ import annotations

from pathlib import Path

from claude_supervisor.parser.events import ParsedEvent
from claude_supervisor.parser.patterns import PatternSet, load_pattern_set

# Guard against a pathological producer that never emits a newline.
_MAX_BUFFER_CHARS = 64_000


class ClaudeOutputParser:
    """Incrementally parse Claude Code output into events.

    The parser is intentionally stateless with respect to *decisions* -- it only
    reports what it sees. Deciding what to do about an event is the job of the
    state machine and the permission/resume engines.
    """

    def __init__(self, pattern_set: PatternSet) -> None:
        """Initialize the parser with a compiled ``pattern_set``."""
        self._patterns = pattern_set
        self._buffer = ""

    @classmethod
    def from_rules(cls, path: str | Path | None = None) -> ClaudeOutputParser:
        """Construct a parser from a rules YAML file (defaults to the bundled one)."""
        return cls(load_pattern_set(path))

    @property
    def pattern_set(self) -> PatternSet:
        """The compiled patterns in use."""
        return self._patterns

    def feed(self, chunk: str) -> list[ParsedEvent]:
        """Feed a chunk of output and return events from any completed lines.

        A trailing partial line (no newline yet) is retained until more data or
        :meth:`flush` arrives, so a pattern is never missed by a chunk boundary.
        """
        if not chunk:
            return []

        self._buffer += chunk
        events: list[ParsedEvent] = []

        while True:
            newline_index = self._buffer.find("\n")
            if newline_index == -1:
                break
            line = self._buffer[:newline_index]
            self._buffer = self._buffer[newline_index + 1 :]
            events.extend(self._patterns.match_line(line))

        # If a single "line" grows unbounded, evaluate and reset the buffer so a
        # newline-less prompt (some TUIs do this) still triggers detection.
        if len(self._buffer) >= _MAX_BUFFER_CHARS:
            events.extend(self._patterns.match_line(self._buffer))
            self._buffer = ""

        return events

    def flush(self) -> list[ParsedEvent]:
        """Process and clear any buffered partial line.

        Call this on stream end (or when you know a prompt was printed without a
        trailing newline, e.g. an interactive ``(y/N)`` prompt).
        """
        if not self._buffer:
            return []
        line, self._buffer = self._buffer, ""
        return self._patterns.match_line(line)
