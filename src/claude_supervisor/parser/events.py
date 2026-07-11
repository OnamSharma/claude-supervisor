"""Event types produced by the parser."""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


class EventType(enum.StrEnum):
    """A meaningful thing detected in Claude Code's output.

    The set is deliberately small and stable; the *wording* that triggers each
    event lives in external YAML, not here.
    """

    USAGE_LIMIT = "usage_limit"
    PERMISSION_PROMPT = "permission_prompt"
    TASK_COMPLETED = "task_completed"
    RESUME_SUCCESS = "resume_success"
    FATAL_ERROR = "fatal_error"
    UNEXPECTED_EXIT = "unexpected_exit"


@dataclass(frozen=True, slots=True)
class ParsedEvent:
    """A single detection.

    Attributes:
        type: The kind of event.
        raw_line: The exact source line that matched.
        pattern: The regex string that matched (useful for debugging rules).
        groups: Named capture groups from the match (e.g. reset time parts).
    """

    type: EventType
    raw_line: str
    pattern: str
    groups: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        """Freeze ``groups`` so a frozen event is genuinely immutable."""
        if not isinstance(self.groups, MappingProxyType):
            object.__setattr__(self, "groups", MappingProxyType(dict(self.groups)))
