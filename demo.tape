# vhs demo.tape  -> demo.mp4 + demo.gif
# Records: one live triage run, then the replay verdicts from the two experiments.
Output demo.mp4
Output demo.gif

Set Shell zsh
Set FontSize 15
Set Width 1280
Set Height 760
Set Theme "Catppuccin Mocha"
Set TypingSpeed 35ms
Set Padding 24

Hide
Type "cd '/Volumes/Virtual Server/projects/kitaru-claude-agent-sdk' && export KITARU_AGENT_ID=01a06e22-387c-74b0-ad11-67f0894f3f85 && clear"
Enter
Show

Type "# A Claude Agent SDK agent, recorded by Kitaru's new adapter (merged today)."
Enter
Sleep 1.5s
Type "uv run kitaru status --output text | head -6"
Enter
Sleep 3s

Type "# 1. Record one real triage run. Three MCP tools; page_oncall is a real side effect."
Enter
Sleep 1s
Type "uv run python -m demo.agent 'INC-1046: billing-worker latency alert fired at 02:10. Triage it.'"
Enter
Sleep 45s

Type "clear"
Enter
Type "# 2. Six baselines are frozen in a cohort. Two experiments replayed them with page_oncall stubbed."
Enter
Sleep 1s
Type "uv run python scripts/report.py run-haiku-candidate.json"
Enter
Sleep 8s
Type "# Cheaper model: same six decisions, 28% cheaper. Ship it."
Enter
Sleep 3s

Type "clear"
Enter
Type "uv run python scripts/report.py run-eager-prompt.json"
Enter
Sleep 8s
Type "# 'Also page on recent deploys' sounded fine in review. It pages a human at 02:10 for a healthy batch job. Blocked."
Enter
Sleep 6s
