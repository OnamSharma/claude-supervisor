# VHS tape -> statusline.gif  (pairs with tweet 4)
# Generate:  vhs docs/demo/statusline.tape   (run from the repo root)
Output docs/demo/statusline.gif
Set Shell "bash"
Set FontSize 24
Set Width 820
Set Height 200
Set Padding 24
Set Theme "Dracula"

Hide
Type "export CLAUDE_SUPERVISOR_HOME=$PWD/docs/demo/demo-home && python docs/demo/seed_demo.py >/dev/null 2>&1"
Enter
Show

Type "claude-supervisor statusline"
Sleep 800ms
Enter
Sleep 3s
