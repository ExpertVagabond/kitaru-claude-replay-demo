"""Deterministic fixture data for the incident-triage agent.

Every tool result the agent can see comes from here, so a recorded baseline
and a replayed candidate see identical facts. The only thing that changes
between runs is the model or the prompt, which is what Kitaru replay isolates.
"""

SERVICES: dict[str, dict] = {
    "checkout-api": {
        "owner": "payments",
        "status": {
            "state": "degraded",
            "p99_latency_ms": 4200,
            "error_rate_pct": 0.4,
            "note": "latency SLO breached for 11 minutes",
        },
        "deploys": [
            {"id": "d-8831", "minutes_ago": 14, "by": "payments", "change": "enable new fraud scoring call in checkout path"},
            {"id": "d-8790", "minutes_ago": 1440, "by": "payments", "change": "bump dependency versions"},
        ],
    },
    "search-api": {
        "owner": "discovery",
        "status": {
            "state": "down",
            "p99_latency_ms": None,
            "error_rate_pct": 100.0,
            "note": "all pods CrashLoopBackOff since 09:41",
        },
        "deploys": [
            {"id": "d-8829", "minutes_ago": 22, "by": "discovery", "change": "migrate to elasticsearch 9 client"},
        ],
    },
    "notifications": {
        "owner": "growth",
        "status": {
            "state": "healthy",
            "p99_latency_ms": 180,
            "error_rate_pct": 0.01,
            "note": "no anomalies; alert source is a known flapping synthetic check",
        },
        "deploys": [],
    },
    "auth-service": {
        "owner": "identity",
        "status": {
            "state": "degraded",
            "p99_latency_ms": 900,
            "error_rate_pct": 6.5,
            "note": "token refresh failures rising; upstream KMS throttling",
        },
        "deploys": [
            {"id": "d-8802", "minutes_ago": 300, "by": "identity", "change": "rotate signing keys"},
        ],
    },
    "billing-worker": {
        "owner": "payments",
        "status": {
            "state": "healthy",
            "p99_latency_ms": 2100,
            "error_rate_pct": 0.0,
            "note": "queue drained; latency is nightly batch and inside SLO",
        },
        "deploys": [
            {"id": "d-8811", "minutes_ago": 95, "by": "payments", "change": "increase batch size"},
        ],
    },
    "media-cdn": {
        "owner": "platform",
        "status": {
            "state": "down",
            "p99_latency_ms": None,
            "error_rate_pct": 100.0,
            "note": "origin unreachable from all edge regions",
        },
        "deploys": [],
    },
}

# One prompt per incident. The INC id is what the evaluator keys on.
INCIDENTS: dict[str, str] = {
    "INC-1042": "INC-1042: PagerDuty alert. checkout-api p99 latency above 4s for 10 minutes. Triage it.",
    "INC-1043": "INC-1043: search-api returning HTTP 503 on every request. Customers cannot search. Triage it.",
    "INC-1044": "INC-1044: synthetic check for notifications reported a timeout twice in the last hour. Triage it.",
    "INC-1045": "INC-1045: auth-service error rate climbing, users report intermittent logouts. Triage it.",
    "INC-1046": "INC-1046: billing-worker latency alert fired at 02:10. Triage it.",
    "INC-1047": "INC-1047: media-cdn origin health check failing from every region. Triage it.",
}

# Ground truth the evaluator scores against: page the owning team only when the
# service is degraded or down; never page for a healthy service.
EXPECTED_PAGE: dict[str, str | None] = {
    "INC-1042": "payments",
    "INC-1043": "discovery",
    "INC-1044": None,
    "INC-1045": "identity",
    "INC-1046": None,
    "INC-1047": "platform",
}
