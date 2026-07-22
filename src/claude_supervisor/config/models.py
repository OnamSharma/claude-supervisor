"""Pydantic models describing the Claude Supervisor configuration.

The configuration is intentionally conservative. Where a setting trades safety
for automation, the default favors safety (the human stays in control). Users
opt in to more automation explicitly.
"""

from __future__ import annotations

import enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

_LOG_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"})


class PermissionMode(enum.StrEnum):
    """When the permission engine is allowed to auto-answer prompts.

    Attributes:
        ACTIVE_TASK_ONLY: Auto-answer only while a task is actively running.
            This is the safe default: once Claude finishes, automation stops.
        ALWAYS: Auto-answer whenever a prompt appears (more automated, less safe).
        NEVER: Never auto-answer; always defer to the human.
    """

    ACTIVE_TASK_ONLY = "active_task_only"
    ALWAYS = "always"
    NEVER = "never"


class CompletionMode(enum.StrEnum):
    """How aggressively task completion is inferred.

    A completion marker or a clean process exit (code 0) always counts as done
    -- headless ``claude -p`` prints its answer and exits 0 with no marker. The
    modes differ only in whether *idle* (still running, but silent) is treated
    as completion.

    Attributes:
        STRICT: Only a completion marker or a clean exit.
        HEURISTIC: The above, plus sustained idle (Claude waiting at the prompt).
    """

    STRICT = "strict"
    HEURISTIC = "heuristic"


class TaskDelivery(enum.StrEnum):
    """How an unattended task is handed to Claude.

    Attributes:
        ARGUMENT: Append the task to the launch command as an argument (the
            headless ``claude -p "<task>"`` style).
        INPUT: Launch the interactive command, then type the task as input.
    """

    ARGUMENT = "argument"
    INPUT = "input"


class PathsConfig(BaseModel):
    """Filesystem locations used by the supervisor.

    ``None`` means "derive a sensible per-user default at runtime" so that the
    serialized config stays portable across machines.
    """

    model_config = ConfigDict(extra="forbid")

    state_dir: Path | None = Field(
        default=None,
        description="Base directory for logs, database, and runtime state.",
    )
    log_file: Path | None = Field(
        default=None,
        description="Explicit log file path. Defaults to <state_dir>/supervisor.log.",
    )
    database: Path | None = Field(
        default=None,
        description="SQLite database path. Defaults to <state_dir>/supervisor.db.",
    )
    pattern_rules: Path | None = Field(
        default=None,
        description="Override path to the parser rules YAML (compatibility layer).",
    )


class LoggingConfig(BaseModel):
    """Logging behavior."""

    model_config = ConfigDict(extra="forbid")

    level: str = Field(default="INFO", description="Root log level.")
    rich_console: bool = Field(
        default=True, description="Render console logs with Rich formatting."
    )
    rotate_max_bytes: int = Field(
        default=5_000_000, ge=1024, description="Rotate the log file after this many bytes."
    )
    rotate_backups: int = Field(
        default=5, ge=0, description="Number of rotated log files to retain."
    )

    @field_validator("level")
    @classmethod
    def _normalize_level(cls, value: str) -> str:
        candidate = value.strip().upper()
        if candidate not in _LOG_LEVELS:
            allowed = ", ".join(sorted(_LOG_LEVELS))
            raise ValueError(f"log level {value!r} is invalid; expected one of: {allowed}")
        return candidate


class SupervisorConfig(BaseModel):
    """Top-level configuration for Claude Supervisor.

    The flat, spec-compatible keys (``auto_resume``, ``auto_permissions``,
    ``permission_mode``, ``default_reset_hours``, ``log_level``,
    ``notify_on_finish``) are all preserved as first-class fields so an existing
    minimal YAML file keeps working, while richer nested config is available for
    advanced users.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    # --- spec-compatible top-level knobs -----------------------------------
    auto_resume: bool = Field(
        default=True,
        description="Automatically resume the session after a usage reset.",
    )
    auto_permissions: bool = Field(
        default=False,
        description=(
            "Automatically answer repetitive permission prompts. Defaults to "
            "False for safety: the user opts in explicitly."
        ),
    )
    permission_mode: PermissionMode = Field(
        default=PermissionMode.ACTIVE_TASK_ONLY,
        description="Scope in which auto-permission answering is allowed.",
    )
    approve_response: str = Field(
        default="1\r",
        description=(
            "Raw input sent to approve a prompt. Default targets Claude Code's "
            "numbered menu (press '1' = Yes, then Enter). For a classic (y/N) "
            "prompt use 'y\\r'. Sent verbatim, so escape sequences work."
        ),
    )
    reject_response: str = Field(
        default="\x1b",
        description=(
            "Raw input sent to reject a prompt. Default is Escape (the menu's "
            "'No' shortcut). For a classic (y/N) prompt use 'n\\r'."
        ),
    )
    default_reset_hours: float = Field(
        default=5.0,
        gt=0,
        le=48,
        description="Fallback wait time when Claude reports no reset information.",
    )
    notify_on_finish: bool = Field(
        default=False,
        description="Emit a notification when the supervised task completes.",
    )

    # --- richer nested config ----------------------------------------------
    completion_mode: CompletionMode = Field(
        default=CompletionMode.STRICT,
        description="How task completion is inferred from Claude's output.",
    )
    task_delivery: TaskDelivery = Field(
        default=TaskDelivery.ARGUMENT,
        description="How an unattended task is handed to Claude (argument vs typed input).",
    )
    idle_completion_seconds: float = Field(
        default=30.0,
        gt=0,
        description=(
            "Heuristic mode only: treat the task as complete after this many "
            "seconds with no output while Claude is still running (idle at the "
            "prompt, awaiting input). Ignored in strict mode."
        ),
    )
    claude_command: list[str] = Field(
        default_factory=lambda: ["claude"],
        description="Argv used to launch a new Claude Code session.",
    )
    resume_command: list[str] = Field(
        default_factory=lambda: ["claude", "--continue"],
        description="Argv used to resume a Claude Code session (continues the latest).",
    )
    attach_command: list[str] = Field(
        default_factory=lambda: ["claude"],
        description="Argv used by `attach` to launch the interactive session.",
    )
    nudge_message: str = Field(
        default="continue",
        description=(
            "What `attach` types into the session after a usage-limit reset "
            "passes, so Claude picks the task back up."
        ),
    )
    attach_resume_buffer_seconds: float = Field(
        default=30.0,
        ge=0,
        description=(
            "Extra seconds added after the parsed reset time before nudging, "
            "to avoid racing the exact reset minute."
        ),
    )
    read_timeout_seconds: float = Field(
        default=0.5,
        gt=0,
        le=60,
        description=(
            "Max seconds a single output read blocks before the loop re-checks "
            "its stop flag. The read itself is event-driven, not a busy poll."
        ),
    )
    max_resumes: int = Field(
        default=100,
        ge=0,
        description="Safety cap on automatic resumes for a single run (0 = unlimited).",
    )
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @field_validator("resume_command", "claude_command")
    @classmethod
    def _non_empty_command(cls, value: list[str]) -> list[str]:
        if not value or not value[0].strip():
            raise ValueError("command must contain at least the executable name")
        return value

    @property
    def log_level(self) -> str:
        """Spec-compatible accessor mirroring ``logging.level``."""
        return self.logging.level

    def with_log_level(self, level: str) -> SupervisorConfig:
        """Return a copy with the logging level overridden (e.g. from ``--verbose``)."""
        return self.model_copy(update={"logging": self.logging.model_copy(update={"level": level})})
