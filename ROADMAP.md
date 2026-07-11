# Roadmap

Claude Supervisor is built **incrementally**, each milestone ending at a review
gate. Detailed task tracking lives in [docs/TODO.md](docs/TODO.md).

## v0.1 — Foundation (current)

Configuration, logging, the external-YAML parser (compatibility layer), reset
extraction, the state machine, and a diagnostic CLU (`version`/`config`/
`doctor`). Fully tested, no live Claude process required.

## v0.2 — Supervise a live session

- Terminal Manager over a PTY abstraction (POSIX + Windows backends).
- Permission Engine v1: approve repetitive prompts **only while a task is
  active**; stop the moment it completes.
- Resume Engine: detect resets, wait event-driven (no busy polling), resume.
- `start` / `resume` become real commands.

## v0.3 — Memory & insight ✅ (delivered on `main`)

- Session Manager and SQLite storage.
- `status` and `logs` commands.
- Statistics: hours saved, resume count, approvals, completed sessions,
  average runtime and wait.

## v0.4 — Policy & visibility

- Permission Engine v2: a policy engine (allow safe edits/reads/creates; ask a
  human for destructive or out-of-project operations).
- Textual dashboard (read-only live view).

## v0.5 — Reach

- Notifier backends: Telegram, Discord, Slack, email, desktop.
- Plugin system for other tools (Cursor, Codex, Gemini) via swappable parsers.

## Later

- Optional read-only FastAPI web dashboard (no remote execution).

## Non-goals (permanent)

Bypassing usage limits, subscriptions, or authentication; reverse-engineering
Anthropic services; modifying, patching, injecting into, or impersonating
Claude; running unattended forever or inventing tasks. These are out of scope by
design, not "not yet."
