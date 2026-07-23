"""The streaming Claude output parser.

Terminal output arrives in arbitrary chunks, not tidy lines. This parser
buffers partial lines, splits on newlines, and applies a :class:`PatternSet`
to each complete line, emitting :class:`ParsedEvent` objects.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from claude_supervisor.parser.events import ParsedEvent
from claude_supervisor.parser.patterns import PatternSet, load_pattern_set, strip_ansi

# Guard against a pathological producer that never emits a newline.
_MAX_BUFFER_CHARS = 64_000

#: Called for each complete output line with its (ANSI-stripped) text and the
#: events it produced. Used for transcripts / observability.
type LineListener = Callable[[str, list[ParsedEvent]], None]


class ClaudeOutputParser:
    """Incrementally parse Claude Code output into events.

    The parser is intentionally stateless with respect to *decisions* -- it only
    reports what it sees. Deciding what to do about an event is the job of the
    state machine and the permission/resume engines.
    """

    def __init__(self, pattern_set: PatternSet, *, on_line: LineListener | None = None) -> None:
        """Initialize the parser with a compiled ``pattern_set``.

        Args:
            pattern_set: The compiled detection rules.
            on_line: Optional callback invoked for every complete line with the
                cleaned line text and the events it produced (for transcripts).
        """
        self._patterns = pattern_set
        self._on_line = on_line
        self._buffer = ""

    @classmethod
    def from_rules(
        cls, path: str | Path | None = None, *, on_line: LineListener | None = None
    ) -> ClaudeOutputParser:
        """Construct a parser from a rules YAML file (defaults to the bundled one)."""
        return cls(load_pattern_set(path), on_line=on_line)

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

        # Split on LF *or* CR: interactive TUIs frequently end visual lines with
        # a bare carriage return (cursor repositioning) and never send "\n".
        while True:
            index = -1
            for terminator in ("\n", "\r"):
                found = self._buffer.find(terminator)
                if found != -1 and (index == -1 or found < index):
                    index = found
            if index == -1:
                break
            line = self._buffer[:index]
            self._buffer = self._buffer[index + 1 :]
            if line:
                events.extend(self._process_line(line))

        # If a single "line" grows unbounded, evaluate and reset the buffer so a
        # newline-less prompt (some TUIs do this) still triggers detection.
        if len(self._buffer) >= _MAX_BUFFER_CHARS:
            events.extend(self._process_line(self._buffer))
            self._buffer = ""

        return events

    def _process_line(self, line: str) -> list[ParsedEvent]:
        line_events = self._patterns.match_line(line)
        if self._on_line is not None:
            self._on_line(strip_ansi(line).rstrip("\r\n"), line_events)
        return line_events

    def flush(self) -> list[ParsedEvent]:
        """Process and clear any buffered partial line.

        Call this on stream end (or when you know a prompt was printed without a
        trailing newline, e.g. an interactive ``(y/N)`` prompt).
        """
        if not self._buffer:
            return []
        line, self._buffer = self._buffer, ""
        return self._process_line(line)
