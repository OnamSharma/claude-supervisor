"""Typer application exposing the supervisor's commands.

Commands: ``version``, ``config``, ``doctor`` (diagnostics), ``start`` /
``resume`` (supervise a session), and ``status`` / ``logs`` (inspect recorded
sessions, statistics, and the log tail).
"""

from __future__ import annotations

import contextlib
import os
import platform
import shutil
import signal
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from claude_supervisor import __version__
from claude_supervisor.config import (
    ConfigError,
    PermissionMode,
    SupervisorConfig,
    default_config_path,
    effective_database,
    effective_log_file,
    load_config,
    starter_config,
)
from claude_supervisor.core import AttachSession, RunStats, Supervisor, TranscriptWriter
from claude_supervisor.logging import configure_logging
from claude_supervisor.parser.patterns import PatternSetError, load_pattern_set
from claude_supervisor.session import SessionManager
from claude_supervisor.state_machine import State
from claude_supervisor.storage import SqliteStorage
from claude_supervisor.terminal import TerminalError, terminal_factory
from claude_supervisor.terminal.host import create_host

app = typer.Typer(
    name="claude-supervisor",
    help="Safe, human-in-control companion for Claude Code.",
    no_args_is_help=True,
    add_completion=True,
)
_console = Console()

_MIN_PYTHON = (3, 12)


def _config_option() -> Any:
    """Return a reusable ``--config`` Typer option (an ``OptionInfo``)."""
    return typer.Option(
        None,
        "--config",
        "-c",
        help="Path to config.yaml (defaults to the per-user location).",
        show_default=False,
    )


def _require_config_exists(config_path: Path | None) -> None:
    """Error out if an *explicitly provided* config file does not exist.

    A missing default location is fine (defaults are used); a missing path the
    user typed is almost always a mistake, so we surface it instead of silently
    ignoring their config.
    """
    if config_path is not None and not config_path.exists():
        _console.print(f"[red]Config error:[/red] file not found: {config_path}")
        raise typer.Exit(code=1)


def _load_config(config_path: Path | None) -> SupervisorConfig:
    """Load config, exiting with a clear message on a missing or invalid file."""
    _require_config_exists(config_path)
    try:
        return load_config(config_path)
    except ConfigError as exc:
        _console.print(f"[red]Config error:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command()
def version() -> None:
    """Print the installed version."""
    _console.print(f"claude-supervisor {__version__}")


@app.command()
def init(
    config_path: Path | None = _config_option(),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing config file."),
) -> None:
    """Write a starter config file with sensible, validated defaults."""
    target = Path(config_path) if config_path is not None else default_config_path()
    if target.exists() and not force:
        _console.print(
            f"[yellow]Config already exists at {target}[/yellow] — use --force to overwrite."
        )
        raise typer.Exit(code=1)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(starter_config(), encoding="utf-8")
    _console.print(f"[green]Wrote starter config to {target}[/green]")
    _console.print("Edit it if your Claude setup differs, then run: claude-supervisor doctor")


@app.command()
def config(config_path: Path | None = _config_option()) -> None:
    """Show the effective configuration (defaults merged with your file)."""
    cfg = _load_config(config_path)
    source = config_path or default_config_path()
    exists = Path(source).exists()
    _console.print(
        f"[bold]Source:[/bold] {source} {'' if exists else '(not found; using defaults)'}"
    )
    _console.print_json(cfg.model_dump_json(indent=2))


@app.command()
def doctor(config_path: Path | None = _config_option()) -> None:
    """Run environment and configuration health checks."""
    table = Table(title="claude-supervisor doctor", show_lines=False)
    table.add_column("Check", style="bold")
    table.add_column("Result")
    table.add_column("Detail", overflow="fold")

    ok = True
    _require_config_exists(config_path)

    py_ok = sys.version_info[:2] >= _MIN_PYTHON
    ok &= py_ok
    table.add_row(
        "Python >= 3.12",
        _status(py_ok),
        platform.python_version(),
    )

    # Config loads?
    try:
        cfg = load_config(config_path)
        table.add_row("Config loads", _status(True), str(config_path or default_config_path()))
    except ConfigError as exc:
        ok = False
        table.add_row("Config loads", _status(False), str(exc).splitlines()[0])
        cfg = None

    # Pattern rules compile?
    rules_path = None
    if cfg is not None and cfg.paths.pattern_rules is not None:
        rules_path = cfg.paths.pattern_rules
    try:
        pattern_set = load_pattern_set(rules_path)
        table.add_row(
            "Parser rules compile",
            _status(True),
            f"{len(pattern_set)} patterns (v{pattern_set.version})",
        )
    except PatternSetError as exc:
        ok = False
        table.add_row("Parser rules compile", _status(False), str(exc).splitlines()[0])

    # Claude CLI present? Informational — the tool itself is healthy without it,
    # but you need it to actually supervise anything.
    claude_exe = cfg.claude_command[0] if cfg is not None else "claude"
    resolved = shutil.which(claude_exe)
    if resolved:
        table.add_row("Claude CLI on PATH", _status(True), resolved)
    else:
        table.add_row(
            "Claude CLI on PATH",
            "[yellow]MISSING[/yellow]",
            f"'{claude_exe}' not found — install: npm install -g @anthropic-ai/claude-code",
        )

    _console.print(table)
    if not ok:
        raise typer.Exit(code=1)


def _render_stats(stats: RunStats) -> None:
    table = Table(title="run summary", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    for key, value in stats.as_dict().items():
        table.add_row(key, str(value))
    _console.print(table)


def _run_supervisor(
    config: SupervisorConfig,
    argv: Sequence[str],
    *,
    task: str | None = None,
    capture: Path | None = None,
) -> RunStats:
    """Set up logging + persistence + signals, run the supervisor, return stats."""
    configure_logging(config.logging, log_file=effective_log_file(config), force=True)
    factory = terminal_factory(cwd=os.getcwd())

    transcript = TranscriptWriter(capture) if capture is not None else None
    supervisor = Supervisor(config, factory, on_line=transcript)

    storage = SqliteStorage(effective_database(config))
    manager = SessionManager(storage)
    session_id = manager.begin(
        argv, started_at=supervisor.stats.started_at, machine=supervisor.machine
    )

    previous = signal.getsignal(signal.SIGINT)

    def _on_sigint(_signum: int, _frame: object) -> None:
        supervisor.request_stop("keyboard interrupt (SIGINT)")

    signal.signal(signal.SIGINT, _on_sigint)
    try:
        return supervisor.run(argv, task=task)
    finally:
        signal.signal(signal.SIGINT, previous)
        manager.end(session_id, supervisor.stats, supervisor.machine.state)
        storage.close()
        if transcript is not None:
            transcript.close()
            _console.print(f"[dim]Transcript written to {transcript.path}[/dim]")


@app.command()
def start(
    task: str | None = typer.Option(
        None, "--task", "-t", help="Task/prompt to run unattended.", show_default=False
    ),
    auto_approve: bool = typer.Option(
        False,
        "--auto-approve",
        help="Auto-answer permission prompts for this run (active-task scope).",
    ),
    capture: Path | None = typer.Option(
        None,
        "--capture",
        help="Write a transcript of Claude's output + detected events to this file.",
        show_default=False,
    ),
    extra_args: list[str] | None = typer.Argument(
        None, help="Extra arguments appended to the configured claude command."
    ),
    config_path: Path | None = _config_option(),
) -> None:
    """Launch and supervise a Claude Code session (optionally an unattended task)."""
    config = _load_config(config_path)

    if auto_approve:
        config = config.model_copy(
            update={
                "auto_permissions": True,
                "permission_mode": PermissionMode.ACTIVE_TASK_ONLY,
            }
        )

    argv = [*config.claude_command, *(extra_args or [])]
    try:
        stats = _run_supervisor(config, argv, task=task, capture=capture)
    except TerminalError as exc:
        _console.print(f"[red]Terminal error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    _render_stats(stats)


@app.command()
def attach(
    capture: Path | None = typer.Option(
        None,
        "--capture",
        help="Write a transcript of Claude's output + detected events to this file.",
        show_default=False,
    ),
    config_path: Path | None = _config_option(),
) -> None:
    """Supervise your LIVE interactive Claude session (experimental).

    Launches ``claude`` and forwards your keyboard and screen transparently —
    use Claude exactly as normal. When a usage limit appears, the supervisor
    parses the reset time, waits it out, and auto-continues the session (typing
    the configured nudge, or relaunching with --continue if Claude exited).

    Press Ctrl+] to detach.
    """
    config = _load_config(config_path)
    # Console logging would corrupt the live TUI: log to the file only.
    configure_logging(
        config.logging,
        log_file=effective_log_file(config),
        console_enabled=False,
        force=True,
    )
    factory = terminal_factory(cwd=os.getcwd())
    transcript = TranscriptWriter(capture) if capture is not None else None
    session = AttachSession(config, factory, create_host(), on_line=transcript)

    storage = SqliteStorage(effective_database(config))
    manager = SessionManager(storage)
    session_id = manager.begin(config.attach_command, started_at=session.stats.started_at)

    _console.print(
        "[bold green]Attached.[/bold green] Use Claude normally — on a usage "
        "limit I'll wait and auto-continue. Press [bold]Ctrl+][/bold] to detach."
    )
    try:
        stats = session.run()
    except TerminalError as exc:
        _console.print(f"[red]Terminal error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        manager.end(session_id, session.stats, State.STOPPED)
        storage.close()
        if transcript is not None:
            transcript.close()
            _console.print(f"[dim]Transcript written to {transcript.path}[/dim]")
    _render_stats(stats)


@app.command()
def resume(config_path: Path | None = _config_option()) -> None:
    """Resume an existing Claude Code session (waiting for a reset if needed)."""
    config = _load_config(config_path)
    try:
        stats = _run_supervisor(config, config.resume_command)
    except TerminalError as exc:
        _console.print(f"[red]Terminal error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    _render_stats(stats)


@app.command()
def status(config_path: Path | None = _config_option()) -> None:
    """Show the latest session and aggregate statistics."""
    config = _load_config(config_path)

    database = effective_database(config)
    if not database.exists():
        _console.print("No sessions recorded yet.")
        return

    with SqliteStorage(database) as storage:
        manager = SessionManager(storage)
        latest = manager.latest()
        stats = manager.statistics()

    if latest is None:
        _console.print("No sessions recorded yet.")
        return

    session_table = Table(title="latest session", show_header=False)
    session_table.add_column("Field", style="bold")
    session_table.add_column("Value", overflow="fold")
    session_table.add_row("id", str(latest.id))
    session_table.add_row("command", " ".join(latest.command))
    session_table.add_row("started_at", latest.started_at)
    session_table.add_row("final_state", latest.final_state or "(running)")
    session_table.add_row("completed", str(latest.completed))
    session_table.add_row("resumes", str(latest.resumes))
    session_table.add_row("approvals", str(latest.approvals))
    session_table.add_row("stop_reason", latest.stop_reason or "-")
    if latest.error:
        session_table.add_row("error", latest.error)
    _console.print(session_table)

    stats_table = Table(title="statistics (all sessions)", show_header=False)
    stats_table.add_column("Metric", style="bold")
    stats_table.add_column("Value")
    for key, value in stats.as_dict().items():
        stats_table.add_row(key, str(value))
    _console.print(stats_table)


@app.command()
def logs(
    lines: int = typer.Option(40, "--lines", "-n", help="Number of trailing log lines to show."),
    config_path: Path | None = _config_option(),
) -> None:
    """Show the tail of the supervisor log file."""
    config = _load_config(config_path)
    log_file = effective_log_file(config)
    if not log_file.exists():
        _console.print(f"No log file yet at {log_file}")
        return

    content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = content[-lines:] if lines > 0 else content
    _console.print("\n".join(tail))


@app.command()
def statusline() -> None:
    """Emit a one-line status summary for Claude Code's status line.

    Designed to be wired into Claude Code's ``statusLine`` setting. It reads the
    session database and prints a single plain-text line, and is deliberately
    defensive: any error yields a minimal line rather than a traceback, so it can
    never disrupt the Claude Code UI.
    """
    # The line renders inside another program's UI (often UTF-8), but may also be
    # printed to a legacy console (cp1252 on Windows). Force UTF-8 with replacement
    # so the emoji never raises UnicodeEncodeError.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        with contextlib.suppress(ValueError, OSError):
            reconfigure(encoding="utf-8", errors="replace")

    try:
        config = load_config(None)
        database = effective_database(config)
        if not database.exists():
            typer.echo("🛡 claude-supervisor · no runs yet")
            return
        with SqliteStorage(database) as storage:
            stats = storage.statistics()
        parts = [f"{stats.total_sessions} run" + ("s" if stats.total_sessions != 1 else "")]
        if stats.resumes:
            parts.append(f"{stats.resumes} resume" + ("s" if stats.resumes != 1 else ""))
        if stats.hours_saved >= 0.05:
            parts.append(f"{stats.hours_saved:.1f}h saved")
        typer.echo("🛡 " + " · ".join(parts))
    except Exception:  # pragma: no cover - never break the host UI
        typer.echo("🛡 claude-supervisor")


def _status(ok: bool) -> str:
    return "[green]OK[/green]" if ok else "[red]FAIL[/red]"


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
