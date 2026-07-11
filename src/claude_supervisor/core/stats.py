"""Lightweight in-memory run statistics.

A minimal tally for a single supervised run. Durable, cross-run statistics
(hours saved, averages) belong to the storage subsystem in a later iteration;
this keeps the orchestrator self-contained for now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(slots=True)
class RunStats:
    """Counters and outcome for one supervised run."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    resumes: int = 0
    approvals: int = 0
    permission_prompts: int = 0
    total_wait_seconds: float = 0.0
    completed: bool = False
    stop_reason: str = ""
    error: str | None = None

    @property
    def elapsed_seconds(self) -> float:
        """Seconds between start and finish (or now, if still running)."""
        end = self.finished_at or datetime.now(UTC)
        return (end - self.started_at).total_seconds()

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-friendly summary."""
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "resumes": self.resumes,
            "approvals": self.approvals,
            "permission_prompts": self.permission_prompts,
            "total_wait_seconds": round(self.total_wait_seconds, 3),
            "completed": self.completed,
            "stop_reason": self.stop_reason,
            "error": self.error,
        }
