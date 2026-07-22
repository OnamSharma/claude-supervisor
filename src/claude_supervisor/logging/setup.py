"""Central logging configuration.

Provides a single :func:`configure_logging` entry point that wires up a Rich
console handler and an optional rotating file handler, plus a :func:`get_logger`
helper so modules never touch the stdlib ``logging`` root directly.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from claude_supervisor.config.models import LoggingConfig

_LOGGER_NAMESPACE = "claude_supervisor"
_configured = False


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a namespaced logger.

    Args:
        name: Optional dotted suffix, e.g. ``"parser"``. When omitted the
            package root logger is returned.
    """
    if not name:
        return logging.getLogger(_LOGGER_NAMESPACE)
    return logging.getLogger(f"{_LOGGER_NAMESPACE}.{name}")


def configure_logging(
    config: LoggingConfig,
    *,
    log_file: Path | None = None,
    console: Console | None = None,
    console_enabled: bool = True,
    force: bool = False,
) -> logging.Logger:
    """Configure the package logger and return it.

    Idempotent by default: repeated calls are no-ops unless ``force`` is set,
    which is important because the CLI and library entry points may both try to
    initialize logging.

    Args:
        config: Logging configuration (level, rotation policy, console style).
        log_file: Optional file to also write logs to, with rotation.
        console: Optional Rich console (useful for tests / custom sinks).
        console_enabled: Set to ``False`` to log to the file only — used by
            ``attach``, where console logging would corrupt the live TUI.
        force: Re-configure even if logging was already set up.
    """
    global _configured

    root = get_logger()
    if _configured and not force:
        return root

    # Clear our own handlers only; never touch other libraries' loggers.
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    root.setLevel(config.level)
    root.propagate = False

    if console_enabled:
        if config.rich_console:
            console_handler: logging.Handler = RichHandler(
                console=console or Console(stderr=True),
                rich_tracebacks=True,
                show_path=False,
                markup=False,
            )
            console_handler.setFormatter(logging.Formatter("%(message)s", datefmt="[%X]"))
        else:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(
                logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
            )
        root.addHandler(console_handler)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=config.rotate_max_bytes,
            backupCount=config.rotate_backups,
            encoding="utf-8",
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
        )
        root.addHandler(file_handler)

    _configured = True
    return root
