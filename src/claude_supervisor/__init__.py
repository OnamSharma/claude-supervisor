"""Claude Supervisor.

A safe, human-in-control companion for Claude Code. It waits for legitimate
usage resets, resumes the user's existing session, and can optionally automate
repetitive permission prompts for the *currently active* task only.

It never bypasses usage limits, authentication, or subscription requirements,
and it never starts new work on its own.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__"]
