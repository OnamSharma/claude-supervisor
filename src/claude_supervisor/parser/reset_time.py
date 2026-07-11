"""Extract a usage-reset delay from Claude Code's wording.

Claude expresses resets in a few shapes:

* relative duration -- ``Try again in 4h 51m`` / ``in 30m`` / ``in 45s``
* absolute clock time -- ``Try again after 15:30`` / ``at 3:30pm``
* nothing usable -- caller must fall back to a configured default

This module turns the first two into a concrete :class:`datetime.timedelta`
without ever *shortening* the real wait (the human is never rushed past a
legitimate reset).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

# 4h 51m / 4 h / 51m / 30s / 2 hours 5 minutes ...
_RELATIVE_RE = re.compile(r"""(?ix)
    try\s+again\s+in\b   # anchor on Claude's phrasing to avoid false hits
    (?P<body>
      (?:\s+\d+\s*(?:h(?:ours?|rs?)?|m(?:in(?:ute)?s?)?|s(?:ec(?:ond)?s?)?)\b)+
    )
    """)
_RELATIVE_PART_RE = re.compile(
    r"(?i)(\d+)\s*(h(?:ours?|rs?)?|m(?:in(?:ute)?s?)?|s(?:ec(?:ond)?s?)?)\b"
)

# after 15:30 / after 3:30 pm / at 09:05
_ABSOLUTE_RE = re.compile(
    r"(?ix)try\s+again\s+(?:after|at)\s+" r"(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*(?P<ampm>am|pm)?"
)


@dataclass(frozen=True, slots=True)
class ResetDelay:
    """A parsed reset delay.

    Attributes:
        delay: How long to wait from ``now``. Never negative.
        kind: ``"relative"`` or ``"absolute"``.
        matched_text: The exact substring that produced this delay.
    """

    delay: timedelta
    kind: str
    matched_text: str


def _relative_seconds(body: str) -> int:
    total = 0
    for value, unit in _RELATIVE_PART_RE.findall(body):
        amount = int(value)
        u = unit.lower()
        if u.startswith("h"):
            total += amount * 3600
        elif u.startswith("m"):
            total += amount * 60
        else:
            total += amount
    return total


def _absolute_delay(match: re.Match[str], now: datetime) -> timedelta:
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    ampm = (match.group("ampm") or "").lower()

    if ampm == "pm" and hour != 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        # Nonsense clock time; treat as "no usable info".
        raise ValueError(f"invalid clock time {hour}:{minute}")

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)  # the reset is later today or tomorrow
    return target - now


def extract_reset_delay(text: str, *, now: datetime | None = None) -> ResetDelay | None:
    """Return a :class:`ResetDelay` from ``text`` or ``None`` if none is present.

    Relative durations are preferred over absolute times when both appear.

    Args:
        text: A line (or block) of Claude output.
        now: Reference time for absolute-time math. Defaults to ``datetime.now()``.
    """
    reference = now or datetime.now()

    relative = _RELATIVE_RE.search(text)
    if relative is not None:
        seconds = _relative_seconds(relative.group("body"))
        if seconds > 0:
            return ResetDelay(
                delay=timedelta(seconds=seconds),
                kind="relative",
                matched_text=relative.group(0).strip(),
            )

    absolute = _ABSOLUTE_RE.search(text)
    if absolute is not None:
        try:
            delay = _absolute_delay(absolute, reference)
        except ValueError:
            return None
        return ResetDelay(delay=delay, kind="absolute", matched_text=absolute.group(0).strip())

    return None
