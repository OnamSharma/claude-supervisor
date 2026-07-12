# Using Claude Supervisor inside Claude Code

Claude Supervisor **supervises** Claude Code from the outside — that's by design
(its job is to act while Claude is blocked on a usage limit, so it can't live
inside the session it's waiting on). But you can surface it **inside** the Claude
Code UI so it's visible and one keystroke away.

## Status line (see it in the Claude Code UI)

Show live supervisor stats in Claude Code's status bar. Add this to your Claude
Code settings (`~/.claude/settings.json`, or the project `.claude/settings.json`):

```json
{
  "statusLine": {
    "type": "command",
    "command": "claude-supervisor statusline"
  }
}
```

Claude Code will then render a line like:

```
🛡 3 runs · 1 resume · 2.1h saved
```

The command reads the local session database, prints one plain UTF-8 line, and
is fully defensive — it never errors or blocks, so it can't disrupt the UI. With
no history yet it prints `🛡 claude-supervisor · no runs yet`.

## Slash command (`/supervisor`)

Copy [`integrations/claude-code/commands/supervisor.md`](../integrations/claude-code/commands/supervisor.md)
into your commands directory:

- global: `~/.claude/commands/supervisor.md`
- or per-project: `.claude/commands/supervisor.md`

Then run `/supervisor` in a Claude Code session to print the latest supervised
run and aggregate statistics.

## What still runs outside

Actually *supervising* a session (waiting out a reset and resuming) is launched
from your shell, because it must keep running while Claude Code is rate-limited:

```bash
claude-supervisor start --task "..." --config cs.yaml
```

The status line and slash command above simply make that supervision **visible
and reviewable** from within Claude Code.

## Roadmap

- A live status file so the status line can show an in-progress wait
  (`🛡 waiting for reset · 3h20m left`), not just history.
- Packaging the status line + command as an installable Claude Code **plugin**,
  so it's a single install.
