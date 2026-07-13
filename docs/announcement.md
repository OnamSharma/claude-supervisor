# Launch announcement (X / Twitter thread)

Copy-paste each block as one tweet. Swap in a short demo GIF/screenshot on
tweet 1 or 3 if you have one — it dramatically boosts reach.

---

**1/**
You start a big task in Claude Code, hit your usage limit halfway through, and it
just… stops. Hours later you come back and manually resume.

I built **Claude Supervisor** — point it at a task and walk away. It waits out
the reset, resumes, and tells you when it's done. 🧵

**2/**
It's a safe, human-in-control companion for Claude Code:

• detects your usage-limit reset and waits for it
• resumes your session automatically
• optionally auto-answers the repetitive permission prompts
• stops the moment the task is done

It never bypasses limits — it *waits* for legitimate resets.

**3/**
Under the hood it runs `claude` in a pseudo-terminal and watches the output with
an explicit state machine, doing the boring wait-and-resume for you.

`claude-supervisor status` even tracks "hours saved" — the babysitting it did
while you were away. 🛡

**4/**
It also lives *inside* Claude Code: a status line and a `/supervisor` command
show your stats without leaving the session.

**5/**
It's an early alpha — but a serious one:

• 189 tests, 97% coverage
• validated end-to-end against real Claude Code
• CI on Windows + Linux, Python 3.12–3.14
• MIT licensed, published on PyPI

**6/**
Try it (Python 3.12+):

  pipx install claude-supervisor
  claude-supervisor init
  claude-supervisor start --task "your task here"

⭐ github.com/OnamSharma/claude-supervisor

**7/**
It's open source and I'd love feedback — especially a real Claude usage-limit
message to sharpen detection (run with `--capture` and open an issue).

Star it, break it, tell me what's missing. 🙏
github.com/OnamSharma/claude-supervisor
