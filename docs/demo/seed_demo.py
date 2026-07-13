"""Seed a demo database with impressive-looking stats for the `status` GIF.

Writes into CLAUDE_SUPERVISOR_HOME (set it to a throwaway demo dir first).
"""

from datetime import UTC, datetime, timedelta

from claude_supervisor.config import effective_database, load_config
from claude_supervisor.storage import SqliteStorage

runs = [
    # (resumes, approvals, wait_hours, runtime_s, task)
    (0, 3, 0.0, 42.0, "add type hints to api.py"),
    (1, 6, 5.0, 118.0, "refactor the auth module"),
    (0, 2, 0.0, 33.0, "write tests for parser.py"),
    (2, 9, 10.0, 240.0, "migrate config to pydantic v2"),
    (1, 4, 5.0, 96.0, "add docstrings across the package"),
]

storage = SqliteStorage(effective_database(load_config(None)))
now = datetime.now(UTC)
for i, (resumes, approvals, wait_h, runtime_s, task) in enumerate(runs):
    started = now - timedelta(hours=6 * (len(runs) - i))
    sid = storage.create_session(command=["claude", "-p", task], started_at=started)
    storage.complete_session(
        sid,
        finished_at=started + timedelta(seconds=runtime_s),
        final_state="stopped",
        completed=True,
        resumes=resumes,
        approvals=approvals,
        permission_prompts=approvals,
        total_wait_seconds=wait_h * 3600,
        runtime_seconds=runtime_s,
        stop_reason="clean exit",
        error=None,
    )
storage.close()
print(f"seeded {len(runs)} demo sessions")
