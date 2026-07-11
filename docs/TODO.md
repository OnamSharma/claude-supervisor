# Running TODO / iteration plan

Maintained across development. Each iteration ends at a review gate.

## Iteration 1 — Foundation ✅ (this iteration)

- [x] Project scaffolding, `pyproject.toml`, tooling (ruff/black/mypy/pytest)
- [x] `config/` — pydantic models + YAML loader (flat spec-key compatibility)
- [x] `logging/` — Rich console + rotating file logs
- [x] `parser/` — events, pattern-set (external YAML), streaming parser
- [x] `parser/reset_time.py` — relative/absolute reset extraction
- [x] `state_machine/` — states, transition table, observers
- [x] `cli/` — `version`, `config`, `doctor` (+ stubbed action commands)
- [x] Tests for config, patterns, parser, reset-time, state machine, CLI
- [x] Docs: README, ARCHITECTURE, ROADMAP, SECURITY, CoC, CONTRIBUTING

## Iteration 2 — Terminal + Permission + Resume engines ✅

- [x] `terminal/` — `TerminalManager` ABC + timeout-capable `read`
  - [x] `ScriptedTerminal` (process-free, for tests/dry runs)
  - [x] `ThreadedTerminal` base (blocking reader thread + queue; event-driven)
  - [x] POSIX backend (`pexpect`) and Windows backend (`pywinpty`), lazy-imported
  - [x] Platform-aware `create_terminal` / `terminal_factory`
- [x] `permissions/` — `PermissionDecision`, `PermissionEngine` protocol,
      `ActiveTaskPermissionEngine` (v1: approve while active task, opt-in)
- [x] `resume/` — `Clock` (interruptible `RealClock` + `ManualClock`) and
      `ResumePlanner` (parsed → last-interval → default fallback)
- [x] `core/` — `Supervisor` run loop + `RunStats`
- [x] Wire `start` / `resume` CLI commands (with SIGINT-safe shutdown)
- [x] Parser fix: at most one event per type per line (no duplicate reactions)
- [x] Full flow tests via `ScriptedTerminal` + `ManualClock` (no real process/time)

## Iteration 3 — Session + Storage + Statistics ✅

- [x] `storage/` — `Storage` protocol + `SqliteStorage` (sessions + events),
      primitive-only (no dependency on the core layer)
- [x] `session/` — `SessionManager` bridge: persists `RunStats`, logs FSM
      transitions as events, exposes latest/recent/statistics
- [x] Statistics — hours saved, resumes, approvals, completed sessions,
      average runtime, average wait (`total_wait_seconds` added to `RunStats`)
- [x] `status` (latest session + aggregate statistics) and `logs` (log tail)
      CLI commands, wired through `_run_supervisor`
- [x] Tests for storage, session manager, and the new CLI commands

## Real-PTY validation ✅ (between it3 and it4)

- [x] Installed `pywinpty`; validated the real Windows ConPTY path end-to-end
- [x] Fixed two bugs the real PTY exposed: ANSI escape stripping in the parser,
      and `send_line` using `\r` (Enter) instead of `\n`
- [x] Added `tests/integration/` real-PTY tests (skip if no backend)
- [x] Established real prompt shape: Claude Code uses a **numbered menu**, not
      `(y/N)`. Made responses configurable (`approve_response`/`reject_response`,
      raw `send`), defaulted to the menu, and added menu detection patterns.
- [x] Idle / prompt-return completion detection (heuristic mode): a live-but-
      silent session is treated as a finished turn → stop and hand back.
      Validated against a real live PTY process.
- [ ] **Still needed (needs a real session):** confirm the exact usage-limit /
      reset wording, and verify `approve_response` "1\r" actually selects Yes on
      the live menu (may need Enter-only or arrows); tune `idle_completion_seconds`
      to real Claude pacing
- [ ] Consider a "human passthrough" mode (forward the PTY to the user; only
      auto-answer the repetitive prompts) — the current model owns the terminal

## Interaction model — unattended first, then attach

- [x] **Unattended task mode** (chosen direction): `start --task` runs a task
      without a human attached; `task_delivery` = argument (headless `-p`) or
      input (typed). `--auto-approve` opts a run into answering prompts.
      Validated on a real PTY (argument + input delivery).
- [ ] **Attach / passthrough mode** (Option B, later): transparent proxy so the
      human uses Claude normally while the supervisor handles resets in the
      background. Hard part: cross-platform raw-terminal proxying + resize.

## Iteration 4+ — Dashboard, Notifier, Plugins

- [ ] `dashboard/` — Textual TUI (read-only live view)
- [ ] `notifier/` — Telegram/Discord/Slack/email/desktop backends
- [ ] `plugins/` — parser plugins for cursor/codex/gemini
- [ ] Optional read-only FastAPI web dashboard

## Cross-cutting (ongoing)

- [ ] Keep coverage ≥ 90%
- [ ] CI (GitHub Actions): lint, type-check, test matrix (3.12/3.13/3.14)
- [ ] `CHANGELOG.md` updated per iteration
