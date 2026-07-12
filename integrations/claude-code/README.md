# Claude Code integration

Assets for surfacing Claude Supervisor inside the Claude Code UI. Full setup:
[../../docs/CLAUDE_CODE_INTEGRATION.md](../../docs/CLAUDE_CODE_INTEGRATION.md).

- **Status line** — add to `~/.claude/settings.json`:
  ```json
  { "statusLine": { "type": "command", "command": "claude-supervisor statusline" } }
  ```
- **Slash command** — copy [`commands/supervisor.md`](commands/supervisor.md) to
  `~/.claude/commands/` (global) or `.claude/commands/` (per-project), then run
  `/supervisor`.
