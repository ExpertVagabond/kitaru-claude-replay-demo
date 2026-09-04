"""Create the two experiments the demo compares against the baseline cohort.

1. ``haiku-candidate``: same prompt, swap claude-sonnet-5 for claude-haiku-4-5.
2. ``eager-prompt``: same model, system prompt with an added "also page when a
   deploy landed in the last 2 hours" rule. It is expected to regress on the
   healthy billing worker that deployed 95 minutes before its alert, which is
   the regression the evaluator exists to catch.

Both use the same fail-closed tool policy: read-only tools answer from the
baseline recording, and ``page_oncall`` is stubbed so a replay can never page
a real human.

Usage:
    uv run python scripts/create_experiments.py
"""

import json
import subprocess
import sys

from demo.agent import SYSTEM_PROMPT

HEALTHY_RULE = (
    '   - Do NOT page when the state is "healthy". A healthy service with an alert is noise; say so.\n'
)
EAGER_RULE = (
    '   - Also page the owning team when a deploy landed in the last 2 hours, even if the state\n'
    '     is "healthy": a recent deploy is a leading indicator and missing an incident is worse\n'
    '     than a false page.\n'
)
assert HEALTHY_RULE in SYSTEM_PROMPT, "system prompt drifted; update HEALTHY_RULE"
# The kind of edit a well-meaning reviewer proposes in a PR. It reads sensibly
# and it pages a human at 02:10 for a healthy nightly batch job (INC-1046).
EAGER_PROMPT = SYSTEM_PROMPT.replace(HEALTHY_RULE, HEALTHY_RULE + EAGER_RULE)

# Claude SDK MCP replay requires an empty static fail default, so any tool the
# policy does not name stops the replay instead of quietly running live.
TOOL_POLICY = {
    "default": {"type": "static", "cases": [], "on_miss": "fail"},
    "tools": {
        "mcp__ops__get_service_status": {
            "type": "history", "scope": "baseline", "on_miss": "error_result",
        },
        "mcp__ops__get_recent_deploys": {
            "type": "history", "scope": "baseline", "on_miss": "error_result",
        },
        # Any arguments match: the page is simulated, never sent.
        "mcp__ops__page_oncall": {
            "type": "static",
            "cases": [
                {
                    "match": None,
                    "match_mode": "subset",
                    "result": {
                        "content": [
                            {"type": "text", "text": "Paged (simulated by Kitaru replay). Page id PG-replay"}
                        ]
                    },
                }
            ],
            "on_miss": "fail",
        },
    },
}

EVALUATORS = ["triage-quality@latest", "kitaru/cost@latest"]

EXPERIMENTS = {
    "haiku-candidate": {
        "description": "Same prompt, claude-haiku-4-5 instead of claude-sonnet-5.",
        "override": {"model": {"claude-sonnet-5": "claude-haiku-4-5"}},
    },
    "eager-prompt": {
        "description": "Same model, system prompt with an added 'also page on recent deploys' rule.",
        "override": {"system_prompt": EAGER_PROMPT},
    },
}


def main() -> int:
    for name, spec in EXPERIMENTS.items():
        command = [
            "uv", "run", "kitaru", "experiment", "create", name,
            "--agent", "incident-triage",
            "--description", spec["description"],
            "--override", json.dumps(spec["override"]),
            "--tool-policy", json.dumps(TOOL_POLICY),
            "--output", "json",
        ]
        for evaluator in EVALUATORS:
            command += ["--evaluator", evaluator]
        run = subprocess.run(command, capture_output=True, text=True)
        # The CLI writes errors as JSON on stderr; success goes to stdout.
        try:
            payload = json.loads(run.stdout.strip() or run.stderr.strip())
        except json.JSONDecodeError:
            print(f"{name}: non-JSON response\n{run.stdout[-800:]}\n{run.stderr[-800:]}", file=sys.stderr)
            return 1
        if not payload.get("ok"):
            error = payload.get("error") or {}
            if error.get("kind") == "conflict":
                print(f"{name}: already exists, skipping")
                continue
            print(f"{name}: {error}", file=sys.stderr)
            return 1
        item = payload["item"]
        experiment = item.get("experiment") or item
        print(f"{name}: id={experiment.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
