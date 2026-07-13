"""A fake `claude` for recording demos: prints a realistic short run, then exits.

Deterministic and fast (~4s) so demo GIFs are clean and burn no real usage.
Point `claude_command` at it (see config.yaml in this folder).
"""

import sys
import time

task = sys.argv[-1] if len(sys.argv) > 1 else "the task"

lines = [
    "\x1b[2mReading project files…\x1b[0m",
    "\x1b[36m●\x1b[0m Opening utils.py",
    "\x1b[36m●\x1b[0m Adding a docstring to `parse_config()`",
    "\x1b[32m✔\x1b[0m Updated utils.py (+7 lines)",
    f"\x1b[1mDone\x1b[0m — {task}",
]
for line in lines:
    print(line, flush=True)
    time.sleep(0.6)
time.sleep(0.3)
