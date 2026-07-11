"""Logging subsystem: Rich console output plus rotating file logs."""

from __future__ import annotations

from claude_supervisor.logging.setup import configure_logging, get_logger

__all__ = ["configure_logging", "get_logger"]
