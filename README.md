# Replay a Claude Agent SDK agent with Kitaru

Record a real Claude agent run, freeze the recordings into a regression suite, replay them against a cheaper model and against a prompt edit, and let an evaluator say which change is safe to ship.

Built on the [Kitaru](https://github.com/zenml-io/kitaru) Claude Agent SDK adapter the day it merged (`kitaru-claude-agent-sdk` 0.1.0rc0, [PR 940](https://github.com/zenml-io/kitaru/pull/940), 2026-09-04). It is not on PyPI yet, so this repo pins the merge commit.

## The agent

`demo/agent.py` is an on-call triage assistant. Given an alert it calls three in-process MCP tools:

| Tool | Kind | Replay policy |
| --- | --- | --- |
| `get_service_status` | read-only | answered from the baseline recording |
| `get_recent_deploys` | read-only | answered from the baseline recording |
| `page_oncall` | **side effect** | stubbed; a replay can never page a human |

The rule it must follow: page the owning team when the service is degraded or down, never when it is healthy. `demo/fixtures.py` holds six incidents, four that should page and two that should not.

The same file is both the recording program and the replay program. Under a Kitaru worker the adapter reads the task environment, substitutes the recorded prompt, applies the model or prompt override, and answers wrapped tool calls per the policy. There is no replay branch in the agent code.

## The evaluator

`evaluators/triage_quality.py` reads one recorded session and returns three verdicts: `paging_decision` (paged exactly the expected team, or correctly stayed quiet), `no_double_page`, and `summary_present`. Kitaru's built-in `kitaru/cost` evaluator runs alongside it.

## The two experiments

- **haiku-candidate**: same prompt, `claude-sonnet-5` swapped for `claude-haiku-4-5`. Question: can we cut cost without changing decisions?
- **loose-prompt**: same model, system prompt with the "never page a healthy service" rule deleted. Question: does the evaluator catch a prompt regression before it ships?

Both share one fail-closed tool policy (`scripts/create_experiments.py`): the default is an empty static policy with `on_miss: fail`, so any tool the policy does not name stops the replay instead of quietly running live.

## Results

Six baselines recorded with `claude-sonnet-5`, each replayed once per experiment by a local worker. Every replay completed; no live page was sent (the `page_oncall` node in each replay carries `replay: {live: false, policy: static}`).

**haiku-candidate: ship it.** Same six decisions, 28% cheaper.

```
incident   baseline  candidate   base $   cand $  note
INC-1042   pass      pass        0.0149   0.0113  paged payments exactly once
INC-1043   pass      pass        0.0137   0.0112  paged discovery exactly once
INC-1044   pass      pass        0.0110   0.0067  correctly did not page
INC-1045   pass      pass        0.0141   0.0108  paged identity exactly once
INC-1046   pass      pass        0.0120   0.0073  correctly did not page
INC-1047   pass      pass        0.0139   0.0099  paged platform exactly once
total      6/6       6/6         0.0796   0.0571  cost -28%
```

**eager-prompt: block it.** The added rule reads sensibly in review and it pages the payments team at 02:10 for a healthy nightly batch job.

```
incident   baseline  candidate   base $   cand $  note
INC-1042   pass      pass        0.0149   0.0150  paged payments exactly once
INC-1043   pass      pass        0.0137   0.0144  paged discovery exactly once
INC-1044   pass      pass        0.0110   0.0117  correctly did not page
INC-1045   pass      pass        0.0141   0.0145  paged identity exactly once
INC-1046   pass      FAIL        0.0120   0.0157  paged ['payments'] for a healthy service
INC-1047   pass      pass        0.0139   0.0140  paged platform exactly once
total      6/6       5/6         0.0796   0.0852  cost +7%
```

A first draft of that experiment simply deleted the "never page a healthy service" rule. Sonnet did not regress: the recorded status note said the check was flapping and it stayed quiet anyway. Replay against real recordings is what told me the deletion was harmless and the addition was not.

## Run it yourself

Requirements: `uv`, Docker, the `claude` CLI, and `ANTHROPIC_API_KEY` in your environment. Six baseline recordings cost about eight cents; each experiment run replays all six.

```bash
git clone https://github.com/ExpertVagabond/kitaru-claude-replay-demo.git
cd kitaru-claude-replay-demo
uv sync

# 1. Local Kitaru server (Docker) and a worker with your Anthropic key
uv run kitaru login --local
uv run kitaru worker start --name demo-worker --concurrency 4   # separate terminal

# 2. Register the agent and the evaluator
uv run kitaru agent register incident-triage \
  --command "uv run python -m demo.agent" --working-dir . --timeout-seconds 300 \
  --display-version sonnet-5-baseline \
  --tool mcp__ops__get_service_status --tool mcp__ops__get_recent_deploys --tool mcp__ops__page_oncall
uv run kitaru evaluator register triage-quality \
  --script evaluators/triage_quality.py --entrypoint evaluate --display-version v1

# 3. Record six baselines (prints the agent id above; export it)
export KITARU_AGENT_ID=<id from step 2>
uv run python scripts/record_baselines.py --label "baseline sonnet-5"

# 4. Create the experiments, freeze the cohort, run both, print the table
uv run python scripts/create_experiments.py
./scripts/run_suite.sh sessions.txt
```

`kitaru login --local` starts the server on `http://localhost:8000`; the dashboard is there too.

## Notes from building on the adapter on day one

- **Pin `setting_sources=[]` when recording.** Without it the Claude subprocess loaded my user-level `~/.claude` settings, an output style leaked into the agent's answer, and the first session cost 3x the clean ones (0.049 vs 0.015 USD) from the extra context. Substituting replay requires the empty list anyway, so set it once in the shared options.
- **`StaticCase` needs `match_mode`** even when `match` is `null`; the CLI rejects the case otherwise. The docs example omits it.
- **Per-call token counts are partial by design.** The adapter reconciles the terminal totals onto the root span, so read cost and tokens from the session, not from individual `llm_call` nodes.
- **Every hook and system message becomes a `span` node.** A four-turn run produced 36 nodes, 26 of them `HookEventMessage` and `SystemMessage` spans. Useful for forensics, noisy for reading a trace; a filter in the node listing would help.
- **Nested `--help` is thin.** `kitaru cohort create --help` prints only global options; the per-command flags come from `kitaru schema` or the source. The docs cover them.

## Layout

```
demo/agent.py                 the agent (recording and replay entrypoint)
demo/fixtures.py              services, incidents, expected decisions
evaluators/triage_quality.py  Kitaru evaluator
scripts/record_baselines.py   record one session per incident
scripts/create_experiments.py define both experiments and the tool policy
scripts/run_suite.sh          cohort, runs, report
scripts/report.py             baseline vs candidate table
```

Apache-2.0. Kitaru is a ZenML project; this demo is independent.
