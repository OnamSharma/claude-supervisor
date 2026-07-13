# Claude Supervisor

[![PyPI](https://img.shields.io/pypi/v/claude-supervisor.svg)](https://pypi.org/project/claude-supervisor/)
[![CI](https://github.com/OnamSharma/claude-supervisor/actions/workflows/ci.yml/badge.svg)](https://github.com/OnamSharma/claude-supervisor/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](pyproject.toml)
[![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#project-status)

> A safe, human-in-control companion for [Claude Code](https://claude.com/claude-code).

Claude Supervisor watches your existing Claude Code session. When you hit a
**legitimate usage-limit reset**, it waits for the reset, resumes your session
exactly where Claude stopped, and — if you opt in — answers the repetitive
permission prompts for the **currently active task**. The moment the task
finishes, it hands full control back to you and stops.

**It is not a bypass.** Claude Supervisor never circumvents authentication,
subscriptions, or rate limits. It *waits* for real resets and *respects* every
limit. It never starts new work on its own.

**[Install](#install) · [Quickstart](#quickstart) · [Configuration](#configuration) · [Get the most out of it](#getting-the-most-out-of-it) · [Inside Claude Code](#inside-claude-code) · [How it works](#how-it-works)**

---

## Why

You kick off a big refactor or a long agentic task in Claude Code, hit your usage
limit halfway through, and… it stops. Hours later you come back, notice the reset
already passed, and manually pick up where you left off.

Claude Supervisor removes that babysitting: point it at a task and walk away. It
waits out the reset, resumes your session, optionally answers the repetitive
permission prompts, stops the moment the task is done, and tells you how many
hours of waiting it handled for you.

## What it does (and does not do)

| Claude Supervisor **does** | Claude Supervisor **never** |
| --- | --- |
| Detect usage limits from Claude's output | Bypass usage limits or subscriptions |
| Wait for the legitimate reset, then resume | Reverse-engineer or patch Claude |
| Continue exactly where Claude stopped | Inject code into or impersonate Claude |
| Optionally auto-answer prompts for the active task | Start new work or invent tasks |
| Stop and return control when the task completes | Run indefinitely on its own |

## Project status

**Alpha — the unattended flow is validated against real Claude Code; the
usage-limit path is not yet exercised on a live rate limit.** Please read this
before relying on it.

- ✅ **Validated against real Claude Code** (CLI 2.x, headless `claude -p`):
  the supervisor launches Claude, runs a task, detects the clean-exit
  completion, and records the run — confirmed end-to-end on Windows.
- ✅ **Thoroughly tested:** 184 tests, 97% coverage, strict type-checking, CI on
  Windows + Linux across Python 3.12–3.14, including real-PTY integration tests.
- ⚠️ **Usage-limit detection not yet confirmed on a live limit.** The wording of
  the reset message is driven by external YAML; if it differs on your account,
  run with `--capture` and tune — see [docs/ALPHA_TESTING.md](docs/ALPHA_TESTING.md).
- 🔜 **No interactive passthrough yet.** Today's model is *unattended* (hand it a
  task via headless `claude -p`); an `attach` mode that rides along an
  interactive session is planned.

Sending real Claude output samples (a `--capture` transcript) is the single most
valuable contribution right now. See [ROADMAP.md](ROADMAP.md) for what's next.

> On Windows the PTY backend needs `pywinpty`; on POSIX, `pexpect`. Installing
> with `[dev]` or the platform extra pulls the right one. Without it,
> `start`/`resume` fail with a clear message instead of crashing.

## Install

### 1. Get the Claude Code CLI

The supervisor drives the `claude` command-line tool (separate from the desktop app):

```bash
npm install -g @anthropic-ai/claude-code   # then reopen your terminal
claude --version
```

### 2. Install the supervisor

Requires **Python 3.12+**. The recommended install is [pipx](https://pipx.pypa.io)
(isolated global CLI):

```bash
pipx install claude-supervisor          # then: pipx inject claude-supervisor pywinpty   (Windows)
```

Or with pip into a 3.12+ environment:

```bash
pip install "claude-supervisor[pty-windows]"   # Windows
pip install "claude-supervisor[pty-posix]"     # macOS/Linux
```

> If `pip install` reports *"Requires-Python >=3.12 … no matching distribution"*,
> your `pip` is running on an older Python — use `py -3.12 -m pip install …`
> (or pipx, which picks a recent Python for you).

<details><summary>From source (contributors)</summary>

```bash
git clone https://github.com/OnamSharma/claude-supervisor
cd claude-supervisor
python -m venv .venv    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```
</details>

## Quickstart

```bash
claude-supervisor init          # write a starter config with sensible defaults
claude-supervisor doctor        # checks Python, config, parser rules, and the claude CLI

# from a directory you want Claude to work in:
claude-supervisor start --task "add a docstring to utils.py"
claude-supervisor status        # what happened: resumes, approvals, hours saved
```

`init` writes a config that launches Claude headless with tools pre-authorized
(`claude -p --permission-mode acceptEdits`) — the validated recipe. Edit it if
your setup differs.

## All commands

```bash
claude-supervisor version
claude-supervisor init        # write a starter config
claude-supervisor doctor      # environment + config + parser rules + claude CLI check
claude-supervisor config      # show effective configuration
claude-supervisor start       # supervise a Claude session (add --task for unattended)
claude-supervisor resume      # resume the latest session (waiting for a reset)
claude-supervisor status      # latest session + aggregate statistics
claude-supervisor logs -n 50  # tail the supervisor log file
claude-supervisor statusline  # one-line summary for Claude Code's status bar
```

### Inside Claude Code

Surface it in the Claude Code UI — a status line (`🛡 3 runs · 1 resume · 2.1h
saved`) and a `/supervisor` slash command. See
[docs/CLAUDE_CODE_INTEGRATION.md](docs/CLAUDE_CODE_INTEGRATION.md). (The
supervising itself runs from your shell — it has to keep going while Claude is
rate-limited — but its status is visible from within Claude Code.)

**Unattended runs:** `--task/-t` hands Claude a task up front; the supervisor
babysits it across usage-limit resets and reports when done. `--auto-approve`
answers the repetitive permission prompts for that run only (you're opting in,
per run). How the task reaches Claude is set by `task_delivery` (append as an
argument for headless `claude -p`, or type it into an interactive session).

Press `Ctrl+C` to stop supervising and hand control back to yourself. Every run
is recorded to a local SQLite database, so `status` reports resumes, approvals,
and "hours saved" (unattended waiting the supervisor absorbed for you):

```text
$ claude-supervisor status
      statistics (all sessions)
  total_sessions           1
  completed_sessions       1
  resumes                  1
  approvals                4
  average_wait_seconds     3600.0
  hours_saved              1.0
```

## Configuration

Configuration is YAML, loaded from a per-user path (`claude-supervisor config`
shows the exact location) or `--config path.yaml`. Every key is optional; the
defaults are safe. See [examples/config.yaml](examples/config.yaml) for all keys.

```yaml
auto_resume: true             # resume automatically after a reset
auto_permissions: false       # OFF by default — you opt in to auto-answering
permission_mode: active_task_only
default_reset_hours: 5        # fallback wait when Claude reports no reset time
approve_response: "1\r"       # how to answer a prompt (numbered-menu "Yes")
completion_mode: strict       # 'heuristic' also stops when Claude goes idle
notify_on_finish: false
```

Claude Code's permission prompt is a numbered menu, and a finished turn usually
has no "done" marker — Claude just idles at the prompt. So `approve_response`
defaults to selecting menu option `1`, and `heuristic` completion mode treats
sustained idle as "turn finished, hand control back."

> **Why `auto_permissions` defaults to `false`.** Auto-answering permission
> prompts removes a human safety checkpoint. Per this project's guiding rule —
> *when uncertain, choose the safest behavior* — you turn it on deliberately,
> and every auto-answer is logged.

## Getting the most out of it

- **Give it a long, well-scoped task and walk away.** The sweet spot is work
  you'd otherwise babysit — a big refactor, a batch of edits, a test-writing
  pass: `claude-supervisor start --task "…" --auto-approve`.
- **Run it in a directory you can review** — a git repo (so you can diff and
  revert what Claude did) or a throwaway sandbox for your first runs.
- **Pre-authorize tools for headless runs.** `init` sets
  `--permission-mode acceptEdits` so Claude can edit files without prompting; use
  `--dangerously-skip-permissions` for full autonomy where you trust the task.
- **Let it run across a reset.** That's the whole point — start a long task,
  hit your limit, and it waits and resumes on its own. The `hours_saved` stat in
  `status` is the babysitting it did for you.
- **Switch to `completion_mode: heuristic`** if a run doesn't stop on its own —
  it then also treats sustained idle (Claude waiting at the prompt) as "done."
- **Capture what Claude prints** with `--capture run.txt` — handy for debugging,
  and the best way to help improve detection (attach it to a GitHub issue).
- **Keep it in view** inside Claude Code via the status line or the `/supervisor`
  command ([below](#inside-claude-code)).

### The compatibility layer

Detection rules live in **external YAML**, not in code, so wording changes in
Claude Code don't require a new release. The bundled defaults are in
[`src/claude_supervisor/parser/rules/claude.yaml`](src/claude_supervisor/parser/rules/claude.yaml).
Point `paths.pattern_rules` at your own copy to customize:

```yaml
version: 1
ignore_case: true
patterns:
  usage_limit:
    - "usage limit reached"
    - "try again (?:in|after|at)\\b"
  permission:
    - "\\(y/N\\)"
  completed:
    - "task completed"
```

## How it works

Claude Supervisor launches the `claude` CLI inside a pseudo-terminal and watches
its output. Detection rules (in external YAML) recognize four things — a usage
limit, a permission prompt, task completion, and unexpected exit — and drive an
explicit **state machine**:

```
STARTING → RUNNING ⇄ WAITING_FOR_PERMISSION
              │
              ├→ WAITING_FOR_RESET → RESUMING → RUNNING
              │
              └→ TASK_COMPLETED → STOPPED     (never back to RUNNING)
```

On a usage limit it parses the reset time, waits (event-driven, no busy-polling),
and resumes. On a prompt it optionally sends your configured answer. On
completion — a marker, a clean exit, or sustained idle — it stops and hands
control back. The one-way `TASK_COMPLETED → STOPPED` edge is why it can *never*
start new work on its own.

Clean architecture, one responsibility per module, everything independently
testable and swappable (parser, permission engine, storage, notifier, plugins).
Details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Development

```bash
pytest              # run tests with coverage
ruff check .        # lint
black --check .     # format check
mypy src            # type check
```

## Testing the alpha

Trying it out? Start with [docs/ALPHA_TESTING.md](docs/ALPHA_TESTING.md) — it
covers the flow that works end-to-end today and the rough edges to watch for.
The best way to help: run with `--capture run.txt` and open an issue with that
file so we can tune detection against real Claude output.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md). Security issues: [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE).

---

*Claude Supervisor is an independent, unofficial tool and is not affiliated with
or endorsed by Anthropic. "Claude" and "Claude Code" are products of Anthropic.*
