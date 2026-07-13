# VHS tape -> status.gif  (pairs with tweet 3 — the "hours saved" money shot)
# Generate:  vhs docs/demo/status.tape   (run from the repo root)
Output docs/demo/status.gif
Set Shell "bash"
Set FontSize 18
Set Width 900
Set Height 720
Set Padding 20
Set Theme "Dracula"

Hide
Type "export CLAUDE_SUPERVISOR_HOME=$PWD/docs/demo/demo-home && python docs/demo/seed_demo.py >/dev/null 2>&1"
Enter
Show

Type "claude-supervisor status"
Sleep 800ms
Enter
Sleep 5s
