---
title: "Claude Supervisor: wait out Claude Code usage limits, then auto-resume"
published: false
tags: ai, python, opensource, cli
canonical_url: https://github.com/OnamSharma/claude-supervisor
---

If you use [Claude Code](https://claude.com/claude-code) for long, agentic tasks,
you know the moment: you're mid-refactor, the agent is cooking, and then — usage
limit. It stops. You come back an hour or two later, the reset has passed, and
you manually pick up where you left off.

I wanted to just… walk away and have it resume itself. So I built
**[Claude Supervisor](https://github.com/OnamSharma/claude-supervisor)** — a
small, human-in-control companion that watches a Claude Code session, waits for
the *legitimate* usage-limit reset, resumes, optionally answers the repetitive
permission prompts, and stops the moment the task is done.

Important framing up front: it is **not a bypass**. It never touches
authentication, subscriptions, or rate limits. It *waits* for real resets and
respects every limit. That constraint shaped the entire design.

## What it looks like

```bash
pipx install claude-supervisor
claude-supervisor init
claude-supervisor start --task "add type hints across the package"
```

Walk away. It runs the task, and if you hit a limit it waits out the reset and
continues. When you're back:

```text
$ claude-supervisor status
 total_sessions   5
 resumes          4
 hours_saved      20.0
```

It even tracks "hours saved" — the unattended waiting it did on your behalf.

## How it works

Claude Supervisor launches the `claude` CLI inside a pseudo-terminal (PTY) and
reads its output stream. A small set of regex rules — living in **external
YAML**, not code — recognize four things: a usage limit, a permission prompt,
task completion, and an unexpected exit. Those events drive an explicit **state
machine**:

```
STARTING → RUNNING ⇄ WAITING_FOR_PERMISSION
              │
              ├→ WAITING_FOR_RESET → RESUMING → RUNNING
              │
              └→ TASK_COMPLETED → STOPPED
```

Two design choices I'm happy with:

- **Detection lives in YAML.** When Claude Code changes its wording, you edit a
  rules file (or point at your own) — no code release needed. A compatibility
  layer from day one.
- **The safety rule is structural.** `TASK_COMPLETED` has exactly one exit:
  `STOPPED`. There is no transition back to `RUNNING`, so the supervisor *cannot*
  start new work on its own. It's enforced by the transition table and a test —
  not by a comment.

## The bugs only a real terminal could find

I built the whole thing test-first with a scripted fake terminal: 180+ tests,
high coverage, all green. Feeling good, I ran it against a *real* Windows
pseudo-console for the first time. Two bugs surfaced within minutes that no unit
test had caught:

1. **ANSI escape sequences.** A real PTY (and Claude's TUI) interleaves colour
   and cursor codes into the stream — `\x1b[32m…\x1b[0m`. My patterns matched raw
   lines, so coloured output could dodge detection. Fix: strip ANSI before
   matching.

2. **Carriage return vs. line feed.** To answer a prompt I sent `"y\n"`. On a
   Windows ConPTY, `\n` is *not* the Enter key — so the child process sat blocked
   on input forever and the whole run hung. The Enter key is `\r`. One character.

That was the lesson of the project: **a green test suite is necessary, not
sufficient.** The real terminal is the source of truth. I turned that first real
run into permanent integration tests that spawn an actual subprocess in a PTY.

## It also lives inside Claude Code

Because the supervising runs from your shell, I surfaced its status *inside* the
Claude Code UI two ways: a **status line** (`🛡 3 runs · 1 resume · 2.1h saved`)
and a `/supervisor` slash command. Both read the same local SQLite history.

## Status & try it

It's an early alpha — but a serious one: validated end-to-end against real Claude
Code, CI on Windows + Linux across Python 3.12–3.14, MIT licensed, published on
PyPI.

```bash
pipx install claude-supervisor
```

- **GitHub:** https://github.com/OnamSharma/claude-supervisor
- The single most useful thing you can send: a real Claude usage-limit message so
  I can sharpen detection. Run with `--capture run.txt` and open an issue.

If you've ever lost momentum to a usage limit, I'd genuinely love your feedback.
Stars, issues, and "here's what broke for me" all welcome. ⭐
