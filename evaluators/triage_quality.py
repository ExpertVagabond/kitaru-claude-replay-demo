"""Kitaru evaluator: did the triage agent page the right team, and only then?

Self-contained on purpose: Kitaru uploads this one file and a worker runs it
in an isolated environment, so the ground truth lives here rather than being
imported from the demo package.
"""

import re

from kitaru.task.evaluator import EvaluationResult, SessionView

# Page the owning team only when the service is degraded or down.
EXPECTED_PAGE: dict[str, str | None] = {
    "INC-1042": "payments",
    "INC-1043": "discovery",
    "INC-1044": None,
    "INC-1045": "identity",
    "INC-1046": None,
    "INC-1047": "platform",
}

_INC = re.compile(r"INC-\d{4}")


def _incident_id(session: SessionView) -> str | None:
    """Find the incident id in whatever shape the session inputs took."""
    match = _INC.search(str(session.session.inputs or ""))
    return match.group(0) if match else None


def _node_type(node) -> str:
    return str(getattr(node.node_type, "value", node.node_type))


def _page_calls(session: SessionView) -> list[dict]:
    """Every page_oncall call the agent made, in recorded order."""
    calls = []
    for node in session.nodes:
        if _node_type(node) != "tool_call":
            continue
        name = str(node.tool_name or node.name or "")
        if name.endswith("page_oncall"):
            calls.append(dict(node.inputs or {}))
    return calls


def evaluate(session: SessionView, **params) -> list[EvaluationResult]:
    """Score one triage session against the fixture ground truth."""
    incident = _incident_id(session)
    if incident is None or incident not in EXPECTED_PAGE:
        return [
            EvaluationResult(
                name="paging_decision",
                score=False,
                passed=False,
                explanation=f"no known incident id in inputs ({incident!r})",
            )
        ]

    expected = EXPECTED_PAGE[incident]
    pages = _page_calls(session)
    teams = [str(p.get("team", "")) for p in pages]
    output = str(session.session.outputs or "")

    if expected is None:
        decision_ok = not pages
        why = "correctly did not page" if decision_ok else f"paged {teams} for a healthy service"
    else:
        decision_ok = teams == [expected]
        if not pages:
            why = f"failed to page {expected}"
        elif teams == [expected]:
            why = f"paged {expected} exactly once"
        else:
            why = f"expected [{expected}], got {teams}"

    return [
        EvaluationResult(
            name="paging_decision",
            score=decision_ok,
            passed=decision_ok,
            explanation=f"{incident}: {why}",
        ),
        EvaluationResult(
            name="no_double_page",
            score=len(pages) <= 1,
            passed=len(pages) <= 1,
            explanation=f"{len(pages)} page call(s)",
        ),
        EvaluationResult(
            name="summary_present",
            score="TRIAGE:" in output,
            passed="TRIAGE:" in output,
            explanation="final output starts a TRIAGE: paragraph" if "TRIAGE:" in output else "no TRIAGE: paragraph in output",
        ),
    ]
