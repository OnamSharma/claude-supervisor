"""A self-documenting run transcript.

Writes each line Claude prints (ANSI stripped) to a file, annotating the lines
that triggered a detection. This turns a real run into the exact data needed to
reconcile the parser rules against real Claude Code output -- testers just send
the file instead of hand-copying lines.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType

from claude_supervisor.parser.events import ParsedEvent


class TranscriptWriter:
    """Append cleaned output lines (with event tags) to a file.

    Usable as a :data:`LineListener` (it is callable) and as a context manager.
    Lines that are empty *and* produced no events are skipped to reduce noise.
    """

    def __init__(self, path: str | Path) -> None:
        """Open ``path`` for writing and emit a header."""
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self._path.open("w", encoding="utf-8")
        self._fh.write(f"# claude-supervisor transcript — {datetime.now(UTC).isoformat()}\n")
        self._fh.write("# lines are ANSI-stripped; '<= type' marks a detected event\n\n")
        self._fh.flush()

    @property
    def path(self) -> Path:
        """The file being written."""
        return self._path

    def __call__(self, line: str, events: list[ParsedEvent]) -> None:
        """Write ``line``, tagging any events it produced."""
        if not line and not events:
            return
        tag = "  <= " + ", ".join(event.type.value for event in events) if events else ""
        self._fh.write(f"{line}{tag}\n")
        self._fh.flush()

    def close(self) -> None:
        """Close the underlying file."""
        self._fh.close()

    def __enter__(self) -> TranscriptWriter:
        """Return self for use in a ``with`` block."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the file on exit."""
        self.close()
