# Private Alpha — Testing Guide

Thanks for helping test Claude Supervisor. This is an early alpha: the machinery
is thoroughly tested (172 tests, real-PTY integration, 96% coverage) but it has
**not yet been validated against a live rate-limited Claude Code session**. Your
testing is exactly how we close that gap.

## Install

```bash
git clone <the private repo url>
cd claude-supervisor
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"          # dev pulls the right PTY backend for your OS
claude-supervisor doctor         # should report all OK
```

Requires Python 3.12+. You also need the `claude` CLI on your PATH.

## What to try first (the sweet spot today)

**Unattended task mode** is the flow that works end-to-end right now:

```bash
claude-supervisor start --task "your task here" --auto-approve
```

- It hands Claude the task, waits through any usage-limit reset and resumes,
  auto-answers the repetitive permission prompts, and stops when the task is
  done.
- Then inspect what happened:
  ```bash
  claude-supervisor status     # latest run + hours saved, resumes, approvals
  claude-supervisor logs -n 80 # recent log tail
  ```

`--auto-approve` is opt-in per run and only answers prompts while a task is
actively running. Start with a **low-stakes task in a throwaway directory** the
first few times.

## Known rough edges (please help us confirm these)

1. **Permission prompt answering is unverified against real Claude.** We default
   to the numbered menu ("1" = Yes, Esc = No). If auto-approve doesn't actually
   advance the prompt, tell us what the prompt looks like and try setting
   `approve_response` in your config (e.g. `"y\r"`, `"\r"`, or `"2\r"`).
2. **Usage-limit wording is a best guess.** If you hit a real limit, please copy
   the exact message — especially how it states the reset time.
3. **Completion detection.** In strict mode (default) it looks for a marker; if
   your runs don't stop when Claude finishes, try `completion_mode: heuristic`
   in config (stops after `idle_completion_seconds` of silence).
4. **No interactive passthrough yet.** The supervisor drives the terminal, so
   today's model is "hand it a task," not "sit alongside you while you type."
   That attach mode is the next major feature.

## Configuration

`claude-supervisor config` shows the effective settings and where the file
lives. See `examples/config.yaml` for every option with comments. Common ones:

- `claude_command` / `resume_command` — how Claude is launched/resumed on your
  setup (e.g. `["claude", "-p"]` for headless argument-style tasks).
- `task_delivery` — `argument` (append task to the command) or `input` (type it).
- `default_reset_hours` — fallback wait if Claude gives no reset time.

## Reporting issues

Please include: OS + Python version, the command you ran, `claude --version`,
the relevant `claude-supervisor logs` tail, and — for detection problems — the
**verbatim** Claude output line that wasn't handled. That last part is gold.
