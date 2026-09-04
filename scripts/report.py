"""Print a baseline-vs-candidate table for each experiment run in run-*.json.

Usage:
    uv run python scripts/report.py [run-haiku-candidate.json ...]
"""

import asyncio
import glob
import json
import sys
from decimal import Decimal

from kitaru.api_models.v1.evaluation import EvaluationListParams
from kitaru.api_models.v1.filter import FilterCondition, FilterOp
from kitaru.api_models.v1.replay import ReplayListParams
from kitaru.client import KitaruAPIClient

CHECK = "pass"
CROSS = "FAIL"


def _run_id(path: str) -> str | None:
    payload = json.load(open(path, encoding="utf-8"))
    item = payload.get("item") or {}
    run = item.get("run") or item
    return run.get("id")


async def _evaluations(client: KitaruAPIClient, session_id) -> dict[str, tuple[bool | None, str | None]]:
    """Map evaluation name to (passed, explanation) for one session."""
    found: dict[str, tuple[bool | None, str | None]] = {}
    async for evaluation in client.evaluations.iter(
        EvaluationListParams(
            filter=FilterCondition(field="session_id", op=FilterOp.EQ, value=str(session_id))
        )
    ):
        found[evaluation.name] = (evaluation.passed, evaluation.explanation)
    return found


def _cost(session) -> Decimal | None:
    for attr in ("cost", "total_cost", "total_cost_usd"):
        value = getattr(session, attr, None)
        if value is not None:
            return Decimal(str(value))
    rollups = getattr(session, "rollups", None)
    if rollups is not None:
        value = getattr(rollups, "cost", None)
        if value is not None:
            return Decimal(str(value))
    return None


async def report(path: str) -> None:
    run_id = _run_id(path)
    if run_id is None:
        print(f"{path}: no run id")
        return
    client = KitaruAPIClient()
    try:
        replays = [
            replay
            async for replay in client.replays.iter(
                ReplayListParams(
                    filter=FilterCondition(field="experiment_run_id", op=FilterOp.EQ, value=run_id)
                )
            )
        ]
        rows = []
        for replay in replays:
            baseline = await client.sessions.get(replay.baseline_session_id)
            result = (
                await client.sessions.get(replay.result_session_id)
                if replay.result_session_id
                else None
            )
            base_eval = await _evaluations(client, replay.baseline_session_id)
            cand_eval = (
                await _evaluations(client, replay.result_session_id)
                if replay.result_session_id
                else {}
            )
            rows.append(
                {
                    "incident": (baseline.name or "").split(" ")[0],
                    "baseline": base_eval.get("paging_decision", (None, None)),
                    "candidate": cand_eval.get("paging_decision", (None, None)),
                    "base_cost": _cost(baseline),
                    "cand_cost": _cost(result) if result else None,
                    "status": str(getattr(replay, "status", "")),
                }
            )
    finally:
        await client.close()

    rows.sort(key=lambda r: r["incident"])
    print(f"\n{path}  (run {run_id})")
    print(f"{'incident':<10} {'baseline':<9} {'candidate':<9} {'base $':>8} {'cand $':>8}  note")
    base_pass = cand_pass = 0
    base_total = cand_total = Decimal(0)
    for row in rows:
        b_ok, _ = row["baseline"]
        c_ok, c_why = row["candidate"]
        base_pass += bool(b_ok)
        cand_pass += bool(c_ok)
        base_total += row["base_cost"] or 0
        cand_total += row["cand_cost"] or 0
        b_txt = CHECK if b_ok else (CROSS if b_ok is False else "?")
        c_txt = CHECK if c_ok else (CROSS if c_ok is False else "?")
        b_cost = f"{row['base_cost']:.4f}" if row["base_cost"] is not None else "-"
        c_cost = f"{row['cand_cost']:.4f}" if row["cand_cost"] is not None else "-"
        note = c_why or row["status"]
        print(f"{row['incident']:<10} {b_txt:<9} {c_txt:<9} {b_cost:>8} {c_cost:>8}  {note}")
    n = len(rows)
    delta = (cand_total - base_total) / base_total * 100 if base_total else Decimal(0)
    print(f"{'total':<10} {base_pass}/{n:<7} {cand_pass}/{n:<7} {base_total:>8.4f} {cand_total:>8.4f}  cost {delta:+.0f}%")


async def main(paths: list[str]) -> None:
    for path in paths:
        await report(path)


if __name__ == "__main__":
    targets = sys.argv[1:] or sorted(glob.glob("run-*.json"))
    asyncio.run(main(targets))
