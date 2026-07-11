r"""Load and compile parser rules from external YAML (the compatibility layer).

A rules file looks like::

    version: 1
    ignore_case: true
    patterns:
      usage_limit:
        - "Usage limit reached"
        - "Try again (after|in)"
      permission:
        - "\\(y/N\\)"
      completed:
        - "Task completed"

Section names may be either the canonical :class:`EventType` value
(``permission_prompt``) or a friendly alias from the specification
(``permission``). Unknown sections raise, so typos surface immediately.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from claude_supervisor.parser.events import EventType, ParsedEvent

# Path to the bundled default rules shipped with the package.
DEFAULT_RULES_PATH = Path(__file__).parent / "rules" / "claude.yaml"

# ANSI / VT escape sequences that a real PTY (and Claude's TUI) interleave with
# text: CSI (colors, cursor moves, private modes), OSC (title/hyperlinks), and
# single-character escapes -- plus stray C0 control chars (but not tab/CR/LF).
# Stripping these before matching keeps detection robust against formatting.
_ANSI_RE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]"  # CSI: ESC [ ... final-byte
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"  # OSC: ESC ] ... BEL/ST
    r"|\x1b[@-Z\\-_]"  # single-character escapes
    r"|[\x00-\x08\x0b\x0c\x0e-\x1f]"  # stray control chars (keep \t \n \r)
)


def strip_ansi(text: str) -> str:
    """Remove ANSI/VT escape sequences and stray control characters from ``text``."""
    return _ANSI_RE.sub("", text)


# Friendly section aliases -> canonical event type.
_SECTION_ALIASES: dict[str, EventType] = {
    "usage_limit": EventType.USAGE_LIMIT,
    "permission": EventType.PERMISSION_PROMPT,
    "permission_prompt": EventType.PERMISSION_PROMPT,
    "completed": EventType.TASK_COMPLETED,
    "task_completed": EventType.TASK_COMPLETED,
    "resume": EventType.RESUME_SUCCESS,
    "resume_success": EventType.RESUME_SUCCESS,
    "fatal": EventType.FATAL_ERROR,
    "fatal_error": EventType.FATAL_ERROR,
    "error": EventType.FATAL_ERROR,
    "unexpected_exit": EventType.UNEXPECTED_EXIT,
    "exit": EventType.UNEXPECTED_EXIT,
}


class PatternSetError(ValueError):
    """Raised when a rules file is structurally invalid or has a bad regex."""


@dataclass(frozen=True, slots=True)
class _CompiledRule:
    event: EventType
    source: str
    regex: re.Pattern[str]


class PatternSet:
    """An ordered collection of compiled detection rules.

    Matching preserves declaration order, and a single line may produce multiple
    events if it matches rules of different types (rare, but well-defined).
    """

    def __init__(self, rules: Iterable[_CompiledRule], *, version: int = 1) -> None:
        """Store compiled ``rules`` in declaration order with a ``version`` tag."""
        self._rules: tuple[_CompiledRule, ...] = tuple(rules)
        self.version = version

    def __len__(self) -> int:
        """Return the number of compiled rules."""
        return len(self._rules)

    def patterns_for(self, event: EventType) -> list[str]:
        """Return the source pattern strings registered for ``event``."""
        return [rule.source for rule in self._rules if rule.event is event]

    def match_line(self, line: str) -> list[ParsedEvent]:
        """Return the events found in ``line``, at most one per event type.

        Uses :meth:`re.Pattern.search` so patterns match anywhere in the line;
        rules should anchor themselves (``^``/``$``) when position matters. When
        several patterns of the *same* type match one line (e.g. a usage-limit
        line that contains both "usage limit reached" and "try again in"), only
        the first is reported, so a single line never triggers a duplicate
        reaction. Different event types on one line are all reported.
        """
        stripped = strip_ansi(line).rstrip("\r\n")
        events: list[ParsedEvent] = []
        seen: set[EventType] = set()
        for rule in self._rules:
            if rule.event in seen:
                continue
            match = rule.regex.search(stripped)
            if match is not None:
                seen.add(rule.event)
                events.append(
                    ParsedEvent(
                        type=rule.event,
                        raw_line=stripped,
                        pattern=rule.source,
                        groups=match.groupdict(),
                    )
                )
        return events


def _coerce_section(name: str) -> EventType:
    key = name.strip().lower()
    if key not in _SECTION_ALIASES:
        known = ", ".join(sorted(_SECTION_ALIASES))
        raise PatternSetError(f"Unknown pattern section {name!r}. Known sections: {known}.")
    return _SECTION_ALIASES[key]


def _build_rules(patterns: Mapping[str, Any], *, flags: int) -> list[_CompiledRule]:
    rules: list[_CompiledRule] = []
    for section, raw_list in patterns.items():
        event = _coerce_section(section)
        if not isinstance(raw_list, list):
            raise PatternSetError(
                f"Section {section!r} must map to a list of patterns, "
                f"got {type(raw_list).__name__}."
            )
        for entry in raw_list:
            if not isinstance(entry, str):
                raise PatternSetError(
                    f"Pattern in section {section!r} must be a string, "
                    f"got {type(entry).__name__}: {entry!r}."
                )
            try:
                compiled = re.compile(entry, flags)
            except re.error as exc:
                raise PatternSetError(
                    f"Invalid regex in section {section!r}: {entry!r} ({exc})."
                ) from exc
            rules.append(_CompiledRule(event=event, source=entry, regex=compiled))
    return rules


def load_pattern_set(path: str | Path | None = None) -> PatternSet:
    """Load and compile a :class:`PatternSet` from ``path``.

    Args:
        path: Rules YAML to load. Defaults to the bundled ``claude.yaml``.

    Raises:
        PatternSetError: If the file is missing, malformed, or contains a bad
            section name or regular expression.
    """
    resolved = Path(path) if path is not None else DEFAULT_RULES_PATH
    if not resolved.exists():
        raise PatternSetError(f"Pattern rules file not found: {resolved}")

    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise PatternSetError(f"Rules file {resolved} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise PatternSetError(f"Rules file {resolved} must contain a top-level mapping.")

    patterns = raw.get("patterns")
    if not isinstance(patterns, dict) or not patterns:
        raise PatternSetError(f"Rules file {resolved} must define a non-empty 'patterns' mapping.")

    ignore_case = bool(raw.get("ignore_case", True))
    flags = re.IGNORECASE if ignore_case else 0
    version = int(raw.get("version", 1))

    return PatternSet(_build_rules(patterns, flags=flags), version=version)
