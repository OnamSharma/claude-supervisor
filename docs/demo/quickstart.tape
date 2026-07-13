# VHS tape -> quickstart.gif  (pairs with tweet 1 / 6 — the hero demo)
# Generate:  vhs docs/demo/quickstart.tape   (run from the repo root)
Output docs/demo/quickstart.gif
Set Shell "bash"
Set FontSize 18
Set Width 1000
Set Height 640
Set Padding 20
Set Theme "Dracula"

Hide
Type "export CLAUDE_SUPERVISOR_HOME=$PWD/docs/demo/demo-home"
Enter
Show

Type "claude-supervisor start --task 'add a docstring to utils.py' --config docs/demo/config.yaml"
Sleep 800ms
Enter
Sleep 13s
