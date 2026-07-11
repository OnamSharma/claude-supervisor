"""Tests for the configuration subsystem."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_supervisor.config import (
    ConfigError,
    PermissionMode,
    SupervisorConfig,
    dump_config,
    load_config,
)
from claude_supervisor.config.loader import default_config_dir, default_config_path


def test_defaults_are_safe() -> None:
    cfg = SupervisorConfig()
    # Safety-first defaults: auto_permissions is opt-in.
    assert cfg.auto_permissions is False
    assert cfg.auto_resume is True
    assert cfg.permission_mode is PermissionMode.ACTIVE_TASK_ONLY
    assert cfg.default_reset_hours == 5.0
    assert cfg.log_level == "INFO"


def test_missing_file_yields_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nope.yaml")
    assert cfg == SupervisorConfig()


def test_flat_spec_keys_are_migrated(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "auto_resume: true\n"
        "auto_permissions: true\n"
        "permission_mode: active_task_only\n"
        "default_reset_hours: 3\n"
        "log_level: DEBUG\n"
        "notify_on_finish: false\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.auto_permissions is True
    assert cfg.default_reset_hours == 3
    assert cfg.logging.level == "DEBUG"  # flat log_level folded into nested section
    assert cfg.log_level == "DEBUG"


def test_explicit_nested_wins_over_flat(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "log_level: DEBUG\nlogging:\n  level: WARNING\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.logging.level == "WARNING"


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("this: : : not yaml\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(path)


def test_non_mapping_top_level_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="top-level mapping"):
        load_config(path)


def test_unknown_key_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("bogus_key: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="failed validation"):
        load_config(path)


def test_bad_log_level_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text("log_level: LOUD\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="failed validation"):
        load_config(path)


@pytest.mark.parametrize("hours", [0, -1, 100])
def test_reset_hours_bounds(hours: float) -> None:
    with pytest.raises(ValueError):
        SupervisorConfig(default_reset_hours=hours)


def test_empty_resume_command_rejected() -> None:
    with pytest.raises(ValueError, match="command"):
        SupervisorConfig(resume_command=[])


def test_empty_claude_command_rejected() -> None:
    with pytest.raises(ValueError, match="command"):
        SupervisorConfig(claude_command=[""])


def test_with_log_level_is_immutable() -> None:
    cfg = SupervisorConfig()
    louder = cfg.with_log_level("DEBUG")
    assert louder.log_level == "DEBUG"
    assert cfg.log_level == "INFO"  # original untouched


def test_dump_and_reload_roundtrip(tmp_path: Path) -> None:
    cfg = SupervisorConfig(auto_permissions=True, default_reset_hours=2.5)
    path = dump_config(cfg, tmp_path / "sub" / "config.yaml")
    assert path.exists()
    reloaded = load_config(path)
    assert reloaded.auto_permissions is True
    assert reloaded.default_reset_hours == 2.5


def test_default_paths_respect_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CLAUDE_SUPERVISOR_HOME", str(tmp_path))
    assert default_config_dir() == tmp_path
    assert default_config_path() == tmp_path / "config.yaml"
