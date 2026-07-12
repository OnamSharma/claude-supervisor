"""Tests for the CLI surface."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claude_supervisor import __version__
from claude_supervisor.cli.app import app
from claude_supervisor.terminal import ScriptedTerminal, TerminalError

# Resolve the real module object. `claude_supervisor.cli` re-exports the Typer
# instance as `app`, which shadows the `app` submodule for attribute-style
# lookups, so import_module (which reads sys.modules) is the reliable way in.
cli_app = importlib.import_module("claude_supervisor.cli.app")

runner = CliRunner()


@pytest.fixture
def _no_logging_side_effects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate the CLI: no global logging changes, and state under tmp_path."""
    monkeypatch.setattr(cli_app, "configure_logging", lambda *a, **k: None)
    monkeypatch.setenv("CLAUDE_SUPERVISOR_HOME", str(tmp_path))


def _scripted_factory(chunks: list[str]):
    def make_factory(**_kwargs: object):
        def factory(command):
            return ScriptedTerminal(chunks, command=command)

        return factory

    return make_factory


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code != 0  # no_args_is_help exits non-zero
    assert "Usage" in result.stdout


def test_config_shows_defaults() -> None:
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "auto_permissions" in result.stdout


def test_config_reports_error_for_bad_file(tmp_path: Path) -> None:
    bad = tmp_path / "config.yaml"
    bad.write_text("log_level: LOUD\n", encoding="utf-8")
    result = runner.invoke(app, ["config", "--config", str(bad)])
    assert result.exit_code == 1
    assert "Config error" in result.stdout


def test_doctor_passes_on_clean_environment() -> None:
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "Python" in result.stdout
    assert "Parser rules compile" in result.stdout


def test_doctor_fails_on_bad_config(tmp_path: Path) -> None:
    bad = tmp_path / "config.yaml"
    bad.write_text("nonsense_key: 1\n", encoding="utf-8")
    result = runner.invoke(app, ["doctor", "--config", str(bad)])
    assert result.exit_code == 1


def test_status_without_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_SUPERVISOR_HOME", str(tmp_path))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0
    assert "No sessions recorded yet" in result.stdout


def test_logs_without_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_SUPERVISOR_HOME", str(tmp_path))
    result = runner.invoke(app, ["logs"])
    assert result.exit_code == 0
    assert "No log file yet" in result.stdout


def test_start_then_status_and_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _no_logging_side_effects: None
) -> None:
    # _no_logging_side_effects points CLAUDE_SUPERVISOR_HOME at tmp_path.
    monkeypatch.setattr(cli_app, "terminal_factory", _scripted_factory(["Task completed\n"]))
    assert runner.invoke(app, ["start"]).exit_code == 0

    status_result = runner.invoke(app, ["status"])
    assert status_result.exit_code == 0
    assert "latest session" in status_result.stdout
    assert "statistics" in status_result.stdout

    # A log file exists because start() writes one (logging not stubbed for logs).
    (tmp_path / "supervisor.log").write_text("hello log line\n", encoding="utf-8")
    logs_result = runner.invoke(app, ["logs", "-n", "5"])
    assert logs_result.exit_code == 0
    assert "hello log line" in logs_result.stdout


def test_explicit_missing_config_errors(tmp_path: Path) -> None:
    # A typo'd --config path must error, not silently fall back to defaults.
    missing = tmp_path / "nope.yaml"
    for cmd in (["status"], ["logs"], ["config"], ["doctor"]):
        result = runner.invoke(app, [*cmd, "--config", str(missing)])
        assert result.exit_code == 1, cmd
        assert "file not found" in result.stdout, cmd


def test_default_missing_config_is_fine() -> None:
    # No --config given and no file at the default location -> defaults, no error.
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "auto_permissions" in result.stdout


def test_start_reports_config_error(tmp_path: Path) -> None:
    bad = tmp_path / "config.yaml"
    bad.write_text("nonsense_key: 1\n", encoding="utf-8")
    result = runner.invoke(app, ["start", "--config", str(bad)])
    assert result.exit_code == 1
    assert "Config error" in result.stdout


def test_start_runs_to_completion(
    monkeypatch: pytest.MonkeyPatch, _no_logging_side_effects: None
) -> None:
    monkeypatch.setattr(cli_app, "terminal_factory", _scripted_factory(["Task completed\n"]))
    result = runner.invoke(app, ["start"])
    assert result.exit_code == 0
    assert "run summary" in result.stdout
    assert "completed" in result.stdout


def test_resume_runs_to_completion(
    monkeypatch: pytest.MonkeyPatch, _no_logging_side_effects: None
) -> None:
    monkeypatch.setattr(
        cli_app, "terminal_factory", _scripted_factory(["Resuming session\n", "Task completed\n"])
    )
    result = runner.invoke(app, ["resume"])
    assert result.exit_code == 0
    assert "run summary" in result.stdout


def test_start_with_task_appends_argument(
    monkeypatch: pytest.MonkeyPatch, _no_logging_side_effects: None
) -> None:
    captured: dict[str, list[str]] = {}

    def make_factory(**_kwargs: object):
        def factory(command):
            captured["command"] = list(command)
            return ScriptedTerminal(["Task completed\n"], command=command)

        return factory

    monkeypatch.setattr(cli_app, "terminal_factory", make_factory)
    result = runner.invoke(app, ["start", "--task", "do X", "--auto-approve"])
    assert result.exit_code == 0
    # Default delivery is 'argument': the task is appended to claude_command.
    assert captured["command"] == ["claude", "do X"]


def test_start_capture_writes_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, _no_logging_side_effects: None
) -> None:
    monkeypatch.setattr(
        cli_app, "terminal_factory", _scripted_factory(["hello there\n", "Task completed\n"])
    )
    capture = tmp_path / "cap.txt"
    result = runner.invoke(app, ["start", "--capture", str(capture)])
    assert result.exit_code == 0
    text = capture.read_text(encoding="utf-8")
    assert "hello there" in text
    assert "Task completed  <= task_completed" in text


def test_start_handles_terminal_error(
    monkeypatch: pytest.MonkeyPatch, _no_logging_side_effects: None
) -> None:
    def make_factory(**_kwargs: object):
        def factory(command):
            raise TerminalError("no PTY backend available")

        return factory

    monkeypatch.setattr(cli_app, "terminal_factory", make_factory)
    result = runner.invoke(app, ["start"])
    assert result.exit_code == 1
    assert "Terminal error" in result.stdout
