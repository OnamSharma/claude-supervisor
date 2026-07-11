# Architecture

Claude Supervisor follows **clean architecture**: dependencies point inward,
each subsystem has a single responsibility, and every subsystem is replaceable
behind an interface. Control flow is modeled as an explicit **state machine**
rather than boolean flags, which makes the safety guarantees auditable.

## Guiding principles

1. **Human in control.** Automation is scoped, opt-in, and always logged.
2. **Never bypass.** The tool waits for legitimate resets; it never circumvents
   auth, subscriptions, or rate limits.
3. **Safe by default.** When behavior is uncertain, choose the safest option.
4. **State-driven.** All lifecycle logic goes through the transition table.
5. **Compatibility layer.** Detection wording lives in external YAML, not code.

## Module map

```
src/claude_supervisor/
├── config/          Typed settings (pydantic) loaded from YAML
├── logging/         Rich console + rotating file logs
├── parser/          Regex event detection driven by external YAML rules
│   └── rules/       Bundled compatibility-layer patterns (claude.yaml)
├── state_machine/   States + validated transitions + observers
├── cli/             Typer application (command surface)
├── terminal/        PTY launch/stream/input (ABC + scripted + pexpect/pywinpty)
├── permissions/     Approve / reject / ask-human decision engine
├── resume/          Interruptible clock + reset planner
├── core/            Supervisor run loop + run stats
├── session/         SessionManager: bridge runs onto storage, log events
├── storage/         Storage protocol + SqliteStorage (sessions + statistics)
├── notifier/        [future] Telegram/Discord/Slack/email/desktop
├── dashboard/       [future] Textual TUI
└── plugins/         [future] Per-tool parser plugins (cursor/codex/gemini)
```

Brackets mark modules scheduled for later iterations; the interfaces they plug
into are being designed from the start.

## Layered dependencies

```
        cli
         │  depends on
         ▼
  ┌──────────────────────────────────────────┐
  │ orchestration (state_machine, session)    │
  └──────────────────────────────────────────┘
         │
         ▼
  ┌──────────────────────────────────────────┐
  │ engines (terminal, parser, permissions,   │
  │          resume, notifier)                │
  └──────────────────────────────────────────┘
         │
         ▼
  ┌──────────────────────────────────────────┐
  │ foundation (config, logging, storage)     │
  └──────────────────────────────────────────┘
```

Inner layers never import outer layers. The parser, for example, reports events
but makes no decisions; deciding what to do about an event belongs to the state
machine and the permission/resume engines.

## The state machine

States: `STARTING`, `RUNNING`, `WAITING_FOR_PERMISSION`, `WAITING_FOR_RESET`,
`RESUMING`, `TASK_COMPLETED`, `STOPPED`.

The transition table (`state_machine/states.py`) is the single source of truth.
Two properties encode the core safety rules:

- **`TASK_COMPLETED` has exactly one exit: `STOPPED`.** Once a task finishes the
  supervisor cannot resume work automatically. This is enforced by the table and
  covered by a dedicated test.
- **Every non-terminal state can reach `STOPPED`.** Graceful shutdown and fatal
  errors can always halt the machine.

## The parser and the compatibility layer

`ClaudeOutputParser` buffers streamed output, splits on newlines (retaining a
partial trailing line so a chunk boundary never hides a match), and applies a
`PatternSet`. A `PatternSet` is compiled from a YAML rules file: section names
map to a small, stable set of `EventType`s, while the *wording* that triggers
each event is pure data. Reset-time phrases (`Try again in 4h 51m`,
`Try again after 15:30`) are parsed into a concrete `timedelta` by
`parser/reset_time.py` — and the delay is never shortened below the real reset.

## The run loop

`core/supervisor.py` owns the loop. It reads output through the terminal's
timeout-capable `read`, feeds each chunk to the parser, and dispatches events:

* **permission prompt** -> `PermissionEngine.decide`; auto-answer only if allowed
  (models `RUNNING -> WAITING_FOR_PERMISSION -> RUNNING` when it does).
* **usage limit** -> `ResumePlanner` computes the wait; the machine moves to
  `WAITING_FOR_RESET`, the interruptible `Clock` sleeps, then `RESUMING ->
  RUNNING` respawns via `resume_command`.
* **task completed / clean exit (heuristic)** -> `TASK_COMPLETED -> STOPPED`.
* **fatal error / unexpected exit** -> stop safely.

Every collaborator (terminal factory, clock, permission engine, planner,
machine) is injected, so the entire loop is tested with a `ScriptedTerminal` and
a `ManualClock` — no real process, no real waiting.

## Extension points (interfaces)

| Concern | Swap by |
| --- | --- |
| Detection wording | Editing/replacing the rules YAML |
| Permission decisions | Implementing the permission engine protocol (it2) |
| Notifications | Implementing a notifier backend (future) |
| Storage | Implementing the `Storage` protocol (SQLite ships by default) |
| Other tools (Cursor/Codex/Gemini) | Dropping a parser plugin (future) |

## Testing strategy

Each subsystem is tested in isolation with no real Claude process required:
config round-trips and validation, pattern compilation and matching, streaming
parser chunking, reset-time math (with an injected `now`), state-machine
legality and observers, and CLI commands via Typer's `CliRunner`. Target
coverage is ≥ 90%.
