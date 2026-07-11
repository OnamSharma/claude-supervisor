"""Tests for the logging subsystem."""

from __future__ import annotations

import logging
from pathlib import Path

from claude_supervisor.config.models import LoggingConfig
from claude_supervisor.logging import configure_logging, get_logger


def test_get_logger_namespacing() -> None:
    assert get_logger().name == "claude_supervisor"
    assert get_logger("parser").name == "claude_supervisor.parser"


def test_configure_sets_level_and_console() -> None:
    logger = configure_logging(LoggingConfig(level="DEBUG"), force=True)
    assert logger.level == logging.DEBUG
    assert logger.handlers  # at least the console handler
    assert logger.propagate is False


def test_configure_plain_console_when_rich_disabled() -> None:
    logger = configure_logging(LoggingConfig(rich_console=False), force=True)
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


def test_configure_adds_rotating_file_handler(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "supervisor.log"
    logger = configure_logging(
        LoggingConfig(level="INFO"),
        log_file=log_file,
        force=True,
    )
    logger.info("hello file")
    for handler in logger.handlers:
        handler.flush()
    assert log_file.exists()
    assert "hello file" in log_file.read_text(encoding="utf-8")


def test_configure_is_idempotent_without_force() -> None:
    first = configure_logging(LoggingConfig(), force=True)
    count = len(first.handlers)
    second = configure_logging(LoggingConfig(level="ERROR"))  # no force -> no-op
    assert second is first
    assert len(second.handlers) == count
