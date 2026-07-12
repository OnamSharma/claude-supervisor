# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- A failed process launch (e.g. `claude` not on PATH, or a wrong
  `claude_command`) now raises a clear `TerminalError` with an actionable hint
  and exits non-zero, instead of dumping a `FileNotFoundError` traceback.
- An explicitly provided `--config` path that does not exist now errors clearly
  instead of being silently ignored (a typo'd path used to fall back to
  defaults). A missing *default* location still uses defaults, as before.

### Added

- **Release automation** (`.github/workflows/release.yml`): tag `vX.Y.Z` builds,
  `twine check`s, and publishes to PyPI via Trusted Publishing. See
  [docs/RELEASING.md](docs/RELEASING.md).
- **Contributor tooling:** `.pre-commit-config.yaml` (ruff/black/basic hooks)
  and Dependabot for pip + GitHub Actions updates.
- **Public-readiness:** README badges (CI/license/Python/status), an honest
  "Project status" section (alpha; not yet validated against live Claude),
  a `status` demo, GitHub issue forms (bug report asks for a `--capture`
  transcript) and a PR template, and CI stabilization (auto-retry the
  timing-sensitive real-PTY tests).
- **Run capture / transcript** (`start --capture <file>`). Writes every
  (ANSI-stripped) line Claude prints to a file, tagging the ones that triggered
  a detected event. Makes a real run self-document exactly what Claude output
  and what the supervisor saw — the fastest way to reconcile parser rules
  against real Claude Code wording. Backed by a `LineListener` hook on the
  parser and a `TranscriptWriter`; survives resumes.
- **Unattended task mode.** `claude-supervisor start --task "<task>"` runs a
  task without you attached: it survives usage-limit resets, auto-answers the
  repetitive prompts, detects completion, and reports. Task delivery is
  configurable (`task_delivery`): `argument` appends it to the command
  (`claude -p "<task>"` style, default) or `input` types it into an interactive
  session. `--auto-approve` opts a single run into answering prompts
  (active-task scope). Validated end-to-end on a real PTY for both modes.
- **Idle / prompt-return completion detection.** In heuristic completion mode,
  a live-but-silent session (no output for `idle_completion_seconds`, default
  30s) is treated as a finished turn — Claude idling at the prompt — so the
  supervisor stops and hands control back. This covers the common case where
  there is no literal "completed" marker. Strict mode (the default) is
  unchanged. Idle time is accrued from read intervals (deterministic, no
  busy-poll), and `ScriptedTerminal` gained a `TIMEOUT` marker to test it.

- **Storage** (`storage/`): a `Storage` protocol and `SqliteStorage` backend
  persisting sessions and per-run events, plus a `Statistics` aggregate
  (completed sessions, resumes, approvals, average runtime/wait, hours saved).
  The layer speaks only primitives — it never imports the orchestration layer.
- **Session** (`session/`): `SessionManager` bridges a run onto storage —
  records `RunStats`, logs every state transition as an event, and exposes
  latest/recent sessions plus statistics.
- **CLI**: `status` (latest session + aggregate statistics) and `logs` (tail of
  the log file) are now live. `start`/`resume` persist each run automatically.
- `RunStats` gained `total_wait_seconds` (unattended waiting absorbed), the
  basis for the "hours saved" statistic.

- **Terminal** (`terminal/`): `TerminalManager` abstraction with a
  timeout-capable `read`; a process-free `ScriptedTerminal`; a `ThreadedTerminal`
  base that pumps blocking PTY reads on a background thread (event-driven, no
  busy-polling); `pexpect` (POSIX) and `pywinpty` (Windows) backends, lazily
  imported with a clear install hint; platform-aware `create_terminal` /
  `terminal_factory`.
- **Permissions** (`permissions/`): `PermissionDecision`, a `PermissionEngine`
  protocol, and `ActiveTaskPermissionEngine` — v1 approves repetitive prompts
  only when the user opted in *and* a task is active; it never auto-rejects.
- **Resume** (`resume/`): an interruptible `Clock` (`RealClock` waits on an
  event; `ManualClock` for deterministic tests) and a `ResumePlanner` that
  prefers a parsed reset delay, then the last-known interval, then the default.
- **Core** (`core/`): the `Supervisor` run loop tying the subsystems together,
  plus `RunStats`. Enforces the safety invariants structurally (completion is
  terminal; waits are interruptible; auto-answer is scoped).
- **CLI**: `start` and `resume` are now live, with SIGINT-safe shutdown and a
  run-summary table.

### Fixed

- Parser now emits at most one event per event type per line, so a single
  usage-limit line can never trigger a duplicate resume.
- **Real-PTY hardening (found by integration testing against a live pseudo-
  terminal):**
  - The parser now strips ANSI/VT escape sequences before matching, so
    detection is robust against Claude's coloured TUI output (`strip_ansi`).
  - `send_line` now terminates input with a carriage return (`\r`), the actual
    "Enter" key on a terminal. Previously it sent `\n`, which a Windows ConPTY
    does not treat as Enter, leaving a child blocked on input forever.

### Changed

- **Permission answers are now configurable and menu-aware.** Real Claude Code
  shows a numbered menu ("Do you want to proceed? / 1. Yes / …"), not a `(y/N)`
  prompt. Terminals gained a raw `send(data)` (send arbitrary key sequences;
  `send_line` is now `send(line + "\r")`), and `approve_response` /
  `reject_response` config controls what is sent — defaulting to `"1\r"`
  (select "Yes") and `"\x1b"` (Escape). Default detection patterns now match the
  menu wording, keeping `(y/N)` support for classic prompts.

### Tests

- Added real-PTY integration tests (`tests/integration/`) that spawn an actual
  subprocess in a pseudo-terminal via the platform backend, covering the full
  usage-limit → wait → resume → permission → completion flow. Skipped cleanly
  when no PTY backend is installed.

## [0.1.0] — Foundation

Initial iteration: the tested, dependency-light core.

### Added

- **Configuration** (`config/`): pydantic-validated `SupervisorConfig` loaded
  from YAML, with backward-compatible flat spec keys (`log_level`, etc.) and
  safe defaults (`auto_permissions` defaults to `false`).
- **Logging** (`logging/`): Rich console handler plus an optional rotating file
  handler, behind an idempotent `configure_logging`.
- **Parser** (`parser/`): a streaming `ClaudeOutputParser` driven by an external
  YAML **compatibility layer** (`PatternSet`), a small stable `EventType` set,
  and reset-time extraction (relative `Try again in 4h 51m` and absolute
  `Try again after 15:30`).
- **State machine** (`state_machine/`): explicit states and a validated
  transition table with observers. Enforces the safety rule that
  `TASK_COMPLETED` can only lead to `STOPPED`.
- **CLI** (`cli/`): `version`, `config`, and `doctor` commands; `start`,
  `resume`, `status`, `logs` are declared as clear "not yet implemented" stubs.
- Test suite across all modules and project docs (README, ARCHITECTURE,
  ROADMAP, SECURITY, CONTRIBUTING, CODE_OF_CONDUCT).

[Unreleased]: https://github.com/claude-supervisor/claude-supervisor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/claude-supervisor/claude-supervisor/releases/tag/v0.1.0
