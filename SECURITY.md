# Security Policy

## Reporting a vulnerability

Please report security issues **privately**. Open a
[GitHub Security Advisory](https://github.com/claude-supervisor/claude-supervisor/security/advisories/new)
or email the maintainers rather than filing a public issue. We aim to acknowledge
reports within 72 hours.

Please include reproduction steps, affected versions, and impact. We will
coordinate a fix and disclosure timeline with you.

## Supported versions

During `0.x` development, only the latest released minor version receives
security fixes.

## Security model & design commitments

Claude Supervisor is a *supervisor*, not a bypass. These are hard commitments,
enforced in code and tests:

- **No limit bypass.** The tool waits for legitimate resets. It never
  circumvents authentication, subscriptions, or rate limits.
- **No tampering.** It does not modify, patch, inject into, or impersonate
  Claude Code.
- **Human in control.** Automation is scoped to the active task, opt-in, and
  logged. `TASK_COMPLETED` can only transition to `STOPPED` — the supervisor
  cannot resume work on its own after a task finishes.
- **Safe defaults.** `auto_permissions` is `false` by default. Auto-answering
  permission prompts is a deliberate, logged opt-in.

## Handling of sensitive data

- The supervisor streams Claude Code's terminal output to detect events and may
  write it to local log files. **Logs can therefore contain whatever Claude
  prints**, including code and paths. Logs are local-only and rotate.
- No output is transmitted anywhere. Future notifier backends will send only
  minimal status metadata, never raw session content, and will be opt-in.
- Never paste secrets into a supervised session expecting the supervisor to
  redact them; it does not.

## Responsible use

Auto-answering permission prompts removes a human checkpoint. Enable
`auto_permissions` only for sessions and directories you trust, and prefer the
forthcoming policy engine (v0.4) which asks a human for destructive or
out-of-project operations.
