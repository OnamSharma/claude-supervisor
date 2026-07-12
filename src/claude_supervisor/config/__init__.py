"""Configuration subsystem: typed, validated settings loaded from YAML."""

from __future__ import annotations

from claude_supervisor.config.loader import (
    ConfigError,
    default_config_path,
    dump_config,
    effective_database,
    effective_log_file,
    effective_state_dir,
    load_config,
    starter_config,
)
from claude_supervisor.config.models import (
    CompletionMode,
    LoggingConfig,
    PathsConfig,
    PermissionMode,
    SupervisorConfig,
    TaskDelivery,
)

__all__ = [
    "CompletionMode",
    "ConfigError",
    "LoggingConfig",
    "PathsConfig",
    "PermissionMode",
    "SupervisorConfig",
    "TaskDelivery",
    "default_config_path",
    "dump_config",
    "effective_database",
    "effective_log_file",
    "effective_state_dir",
    "load_config",
    "starter_config",
]
