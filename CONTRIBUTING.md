# Contributing to Claude Supervisor

Thanks for your interest! This project aims to be a clean, well-tested,
production-quality tool. Contributions of all sizes are welcome.

## Ground rules

1. **Stay within scope.** Contributions must not bypass usage limits,
   authentication, or subscriptions, or modify/patch/impersonate Claude. See
   [ROADMAP.md](ROADMAP.md) non-goals and [SECURITY.md](SECURITY.md).
2. **Safety over automation.** When behavior is uncertain, choose the safest
   option and make the riskier one opt-in and logged.
3. **State-driven.** Lifecycle logic goes through the state machine, not ad-hoc
   boolean flags.

## Development setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

Requires Python 3.12+.

## Before you open a PR

Run the full local check suite:

```bash
ruff check .
black --check .
mypy src
pytest
```

- **Tests are required** for new behavior. Keep total coverage ≥ 90%.
- **Type hints and docstrings** on all public functions/classes (Google style).
- Keep modules single-responsibility and independently testable.
- Update [docs/TODO.md](docs/TODO.md), `CHANGELOG.md`, and relevant docs.

## Detection rules

Parser wording changes usually belong in
`src/claude_supervisor/parser/rules/claude.yaml`, **not** in Python. Prefer
under-matching over over-matching, especially for `permission` patterns — a
false permission match could auto-answer something.

## Commit / PR style

- Small, focused PRs aligned with a roadmap iteration are easiest to review.
- Describe the *why*, not just the *what*.
- Reference the iteration/issue you're addressing.

## Code of Conduct

Participation is governed by our [Code of Conduct](CODE_OF_CONDUCT.md).
