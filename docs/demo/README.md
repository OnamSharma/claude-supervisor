# Demo kit — make GIFs for the launch thread

Everything here produces clean, deterministic demos (a fake `claude` and seeded
stats), so recordings look great, run in seconds, and burn **zero** real usage.

## Which GIF for which tweet

| GIF | Command shown | Pairs with |
| --- | --- | --- |
| `quickstart.gif` | `start --task …` running to completion | tweet **1** (hook) / **6** |
| `status.gif` | `status` with "20.0h saved" | tweet **3** |
| `statusline.gif` | `🛡 5 runs · 4 resumes · 20.0h saved` | tweet **4** |

## Option A — VHS (reproducible; best on macOS / Linux / WSL)

[VHS](https://github.com/charmbracelet/vhs) turns a script into a GIF. Install
it (`brew install vhs`, or see their repo), then from the **repo root**:

```bash
vhs docs/demo/quickstart.tape     # -> docs/demo/quickstart.gif
vhs docs/demo/status.tape         # -> docs/demo/status.gif
vhs docs/demo/statusline.tape     # -> docs/demo/statusline.gif
```

Each tape seeds the demo stats and points `claude-supervisor` at the fake claude
automatically. `claude-supervisor` must be on your PATH (`pipx install .`).

## Option B — ScreenToGif (easiest on Windows)

1. Install [ScreenToGif](https://www.screentogif.com/) (free).
2. One-time setup, from the repo root in PowerShell:
   ```powershell
   $env:CLAUDE_SUPERVISOR_HOME = "$PWD\docs\demo\demo-home"
   python docs\demo\seed_demo.py        # seed the "hours saved" stats
   ```
3. Open ScreenToGif → **Recorder** → drag the frame over your terminal.
4. Hit record, run **one** command, stop:
   - `claude-supervisor statusline`  → `statusline.gif`
   - `claude-supervisor status`      → `status.gif`
   - `claude-supervisor start --task "add a docstring to utils.py" --config docs\demo\config.yaml` → `quickstart.gif`
5. In the editor, trim dead frames and **File → Save as → GIF** (or MP4 — X
   prefers MP4 for longer clips).

## Tips

- Use a **big font** (18–24pt) and a dark theme — GIFs get downscaled on X.
- Keep each clip **under ~10s**; trim the start/end.
- The fake claude lives in `mock_claude.py`; tweak the printed lines to taste.
- Delete `docs/demo/demo-home/` afterward — it's just throwaway demo data.
