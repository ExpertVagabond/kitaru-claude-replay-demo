"""Record one baseline session per fixture incident and print their ids.

Usage:
    KITARU_AGENT_ID=<uuid> uv run python scripts/record_baselines.py [--out sessions.txt]
"""

import argparse
import os
import subprocess
import sys

from demo.fixtures import INCIDENTS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="sessions.txt", help="file to write session ids to")
    parser.add_argument("--label", default="baseline", help="session name suffix")
    args = parser.parse_args()

    if "KITARU_AGENT_ID" not in os.environ:
        print("KITARU_AGENT_ID is required", file=sys.stderr)
        return 2

    session_ids: list[str] = []
    for incident, prompt in INCIDENTS.items():
        env = dict(os.environ, KITARU_SESSION_NAME=f"{incident} {args.label}")
        print(f"=== {incident}", flush=True)
        run = subprocess.run(
            [sys.executable, "-m", "demo.agent", prompt],
            env=env,
            capture_output=True,
            text=True,
        )
        print("\n".join(run.stdout.strip().splitlines()[-2:]), flush=True)
        if run.returncode:
            print(run.stderr[-800:], file=sys.stderr)
            return run.returncode
        session_ids.append(_newest_session_id(incident, args.label))

    with open(args.out, "w", encoding="utf-8") as handle:
        handle.write("\n".join(session_ids) + "\n")
    print(f"=== wrote {len(session_ids)} session ids to {args.out}")
    return 0


def _newest_session_id(incident: str, label: str) -> str:
    """Look the session up by the name the run was recorded under."""
    import json

    listing = subprocess.run(
        [
            "uv", "run", "kitaru", "session", "list",
            "--agent", "incident-triage", "--size", "50", "--output", "json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    items = json.loads(listing.stdout)["items"]
    wanted = f"{incident} {label}"
    matches = [s for s in items if s.get("name") == wanted]
    if not matches:
        raise RuntimeError(f"no session named {wanted!r}")
    matches.sort(key=lambda s: s.get("started_at") or "", reverse=True)
    return matches[0]["id"]


if __name__ == "__main__":
    raise SystemExit(main())
