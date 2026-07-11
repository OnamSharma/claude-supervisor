"""Load and persist :class:`SupervisorConfig` from YAML.

The loader is tolerant of the flat, spec-style config shown in the project
specification (``log_level: INFO``) and transparently maps such keys onto the
richer nested model, so users never have to migrate their file by hand.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from claude_supervisor.config.models import SupervisorConfig

_APP_NAME = "claude-supervisor"

# Flat spec-style keys that live under a nested section in the model.
_FLAT_TO_NESTED: dict[str, tuple[str, str]] = {
    "log_level": ("logging", "level"),
}


class ConfigError(RuntimeError):
    """Raised when a configuration file cannot be read, parsed, or validated."""


def default_config_dir() -> Path:
    """Return the platform-appropriate config directory.

    Honors ``CLAUDE_SUPERVISOR_HOME`` when set, else ``XDG_CONFIG_HOME`` on
    POSIX and ``%APPDATA%`` on Windows, falling back to ``~/.config``.
    """
    override = os.environ.get("CLAUDE_SUPERVISOR_HOME")
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / _APP_NAME
        return Path.home() / "AppData" / "Roaming" / _APP_NAME

    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / _APP_NAME
    return Path.home() / ".config" / _APP_NAME


def default_config_path() -> Path:
    """Return the default ``config.yaml`` path."""
    return default_config_dir() / "config.yaml"


def _migrate_flat_keys(raw: dict[str, Any]) -> dict[str, Any]:
    """Fold flat spec-style keys into their nested homes without clobbering."""
    data = dict(raw)
    for flat_key, (section, field) in _FLAT_TO_NESTED.items():
        if flat_key not in data:
            continue
        value = data.pop(flat_key)
        section_data = dict(data.get(section) or {})
        section_data.setdefault(field, value)
        data[section] = section_data
    return data


def load_config(path: str | os.PathLike[str] | None = None) -> SupervisorConfig:
    """Load configuration from ``path`` (or the default location).

    A missing file yields a fully-defaulted config; that is a valid, supported
    state rather than an error. Malformed YAML or values that fail validation
    raise :class:`ConfigError` with a human-readable message.
    """
    resolved = Path(path) if path is not None else default_config_path()

    if not resolved.exists():
        return SupervisorConfig()

    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - platform/permission dependent
        raise ConfigError(f"Could not read config file {resolved}: {exc}") from exc

    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config file {resolved} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            f"Config file {resolved} must contain a top-level mapping, got {type(raw).__name__}."
        )

    try:
        return SupervisorConfig.model_validate(_migrate_flat_keys(raw))
    except ValidationError as exc:
        raise ConfigError(f"Config file {resolved} failed validation:\n{exc}") from exc


def effective_state_dir(config: SupervisorConfig) -> Path:
    """Return the runtime state directory (``paths.state_dir`` or the default)."""
    return config.paths.state_dir or default_config_dir()


def effective_log_file(config: SupervisorConfig) -> Path:
    """Return the resolved log-file path (``paths.log_file`` or a derived default)."""
    return config.paths.log_file or (effective_state_dir(config) / "supervisor.log")


def effective_database(config: SupervisorConfig) -> Path:
    """Return the resolved SQLite path (``paths.database`` or a derived default)."""
    return config.paths.database or (effective_state_dir(config) / "supervisor.db")


def dump_config(config: SupervisorConfig, path: str | os.PathLike[str]) -> Path:
    """Serialize ``config`` to ``path`` as YAML, creating parent dirs as needed.

    Returns the path written to.
    """
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump(mode="json", exclude_none=True)
    resolved.write_text(
        yaml.safe_dump(payload, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return resolved
