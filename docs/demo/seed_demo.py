"""Seed a demo database with impressive-looking stats for the `status` GIF.

Self-contained (only the standard library) so ANY Python 3 can run it — it
writes directly to the SQLite database Claude Supervisor reads. Set
CLAUDE_SUPERVISOR_HOME to a throwaway demo dir first so it doesn't touch your
real stats.
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

# Locate the database the app would use (mirrors effective_database()).
home = os.environ.get("CLAUDE_SUPERVISOR_HOME")
if home:
    state_dir = home
elif os.name == "nt":
    state_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "claude-supervisor")
else:
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    state_dir = os.path.join(base, "claude-supervisor")
os.makedirs(state_dir, exist_ok=True)
db_path = os.path.join(state_dir, "supervisor.db")

conn = sqlite3.connect(db_path)
conn.executescript(
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        command TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
        final_state TEXT, completed INTEGER NOT NULL DEFAULT 0,
        resumes INTEGER NOT NULL DEFAULT 0, approvals INTEGER NOT NULL DEFAULT 0,
        permission_prompts INTEGER NOT NULL DEFAULT 0,
        total_wait_seconds REAL NOT NULL DEFAULT 0, runtime_seconds REAL,
        stop_reason TEXT NOT NULL DEFAULT '', error TEXT
    );
    """
)

# (resumes, approvals, wait_hours, runtime_s, task)
runs = [
    (0, 3, 0.0, 42.0, "add type hints to api.py"),
    (1, 6, 5.0, 118.0, "refactor the auth module"),
    (0, 2, 0.0, 33.0, "write tests for parser.py"),
    (2, 9, 10.0, 240.0, "migrate config to pydantic v2"),
    (1, 4, 5.0, 96.0, "add docstrings across the package"),
]
now = datetime.now(timezone.utc)
for i, (resumes, approvals, wait_h, runtime_s, task) in enumerate(runs):
    started = now - timedelta(hours=6 * (len(runs) - i))
    conn.execute(
        """INSERT INTO sessions (command, started_at, finished_at, final_state,
               completed, resumes, approvals, permission_prompts,
               total_wait_seconds, runtime_seconds, stop_reason, error)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            json.dumps(["claude", "-p", task]),
            started.isoformat(),
            (started + timedelta(seconds=runtime_s)).isoformat(),
            "stopped",
            1,
            resumes,
            approvals,
            approvals,
            wait_h * 3600,
            runtime_s,
            "clean exit",
            None,
        ),
    )
conn.commit()
conn.close()
print(f"seeded {len(runs)} demo sessions into {db_path}")
