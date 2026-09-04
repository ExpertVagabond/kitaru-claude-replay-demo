#!/usr/bin/env bash
# Freeze the recorded baselines into a cohort, then run both experiments
# against it and print the pass table.
#
#   ./scripts/run_suite.sh sessions.txt
#
# Requires: a selected Kitaru server (kitaru status), the incident-triage
# agent registered, both experiments created, and a worker running with
# Anthropic credentials in its environment.
set -euo pipefail

SESSIONS_FILE="${1:-sessions.txt}"
COHORT_NAME="${COHORT_NAME:-triage-baseline}"
AGENT_REF="${AGENT_REF:-incident-triage@1}"

if [[ -z "${COHORT_VERSION_ID:-}" ]]; then
  echo "== cohort"
  COHORT_JSON=$(uv run kitaru cohort create "$COHORT_NAME" \
    --agent incident-triage \
    --sessions-file "$SESSIONS_FILE" \
    --display-version "$(date +%Y-%m-%d)" \
    --output json)
  COHORT_VERSION_ID=$(printf '%s' "$COHORT_JSON" | python3 -c 'import sys,json; d=json.load(sys.stdin)["item"]; v=d.get("version") or d.get("cohort_version"); print(v["id"])')
fi
echo "cohort version: $COHORT_VERSION_ID"

for EXPERIMENT in ${EXPERIMENTS:-haiku-candidate eager-prompt}; do
  echo "== run $EXPERIMENT"
  uv run kitaru experiment run start "$EXPERIMENT" \
    --cohort-version "$COHORT_VERSION_ID" \
    --agent "$AGENT_REF" \
    --baseline-evaluation-mode if_missing \
    --wait --timeout 1800 --output json > "run-$EXPERIMENT.json" || true
  python3 -c 'import sys,json; d=json.load(open(sys.argv[1])); i=d.get("item",{}); r=i.get("run") or i; print("status:", r.get("status"), "| progress:", r.get("progress"), "| run id:", r.get("id"))' "run-$EXPERIMENT.json"
done

echo "== report"
uv run python scripts/report.py
