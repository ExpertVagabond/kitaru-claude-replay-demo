"""Incident-triage agent built on the Claude Agent SDK and recorded by Kitaru.

Run standalone to record a baseline session:

    KITARU_AGENT_ID=<uuid> uv run python -m demo.agent "INC-1042: ..."

Under a Kitaru worker the same program is the replay: the adapter reads the
task environment, substitutes the recorded prompt, applies the model or
prompt override, and answers wrapped tool calls per the replay's tool policy.
No replay branch exists in this file. That is the point.
"""

import asyncio
import contextlib
import json
import os
import sys
import uuid

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    SdkMcpTool,
    TextBlock,
    ToolUseBlock,
)
from kitaru_claude_agent_sdk import KitaruClaudeRunner, replayable_sdk_mcp_server

from demo.fixtures import INCIDENTS, SERVICES

DEFAULT_MODEL = os.environ.get("TRIAGE_MODEL", "claude-sonnet-5")

SYSTEM_PROMPT = """You are the on-call triage assistant for a small platform team.

Procedure for every alert:
1. Call get_service_status for the named service.
2. Call get_recent_deploys for the same service.
3. Decide whether to page:
   - Page the service's owning team when its state is "degraded" or "down".
   - Do NOT page when the state is "healthy". A healthy service with an alert is noise; say so.
   - Never page more than one team, and never page twice.
4. Finish with one paragraph that starts with "TRIAGE:" and states either
   "PAGED <team>" or "NO PAGE", the suspected cause, and the one next action.

Be brief. Do not ask questions. Use only the tools provided."""


def _text_result(text: str, *, is_error: bool = False) -> dict:
    """Build the MCP result shape the adapter can record and replay."""
    result: dict = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["is_error"] = True
    return result


async def get_service_status(arguments: dict) -> dict:
    """Return the current health of one service."""
    service = SERVICES.get(str(arguments.get("service", "")))
    if service is None:
        return _text_result(f"unknown service {arguments.get('service')!r}", is_error=True)
    return _text_result(json.dumps({"owner": service["owner"], **service["status"]}))


async def get_recent_deploys(arguments: dict) -> dict:
    """Return recent deploys for one service, newest first."""
    service = SERVICES.get(str(arguments.get("service", "")))
    if service is None:
        return _text_result(f"unknown service {arguments.get('service')!r}", is_error=True)
    return _text_result(json.dumps(service["deploys"]))


async def page_oncall(arguments: dict) -> dict:
    """Page a team. This is the side effect replay must never repeat for real."""
    team = str(arguments.get("team", ""))
    severity = str(arguments.get("severity", "high"))
    print(f"[side effect] PAGING {team} at severity {severity}", file=sys.stderr)
    return _text_result(f"Paged {team} at severity {severity}. Page id PG-{uuid.uuid4().hex[:6]}")


OPS_SERVER = replayable_sdk_mcp_server(
    name="ops",
    tools=[
        SdkMcpTool(
            name="get_service_status",
            description="Get the live health state, latency, and error rate of a service.",
            input_schema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
            handler=get_service_status,
        ),
        SdkMcpTool(
            name="get_recent_deploys",
            description="List recent deploys to a service, newest first.",
            input_schema={
                "type": "object",
                "properties": {"service": {"type": "string"}},
                "required": ["service"],
            },
            handler=get_recent_deploys,
        ),
        SdkMcpTool(
            name="page_oncall",
            description="Page a team's on-call engineer. Real side effect; use at most once.",
            input_schema={
                "type": "object",
                "properties": {
                    "team": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "high", "critical"]},
                    "reason": {"type": "string"},
                },
                "required": ["team", "severity", "reason"],
            },
            handler=page_oncall,
        ),
    ],
)

TOOL_IDENTITIES = [
    "mcp__ops__get_service_status",
    "mcp__ops__get_recent_deploys",
    "mcp__ops__page_oncall",
]


def build_options(model: str = DEFAULT_MODEL) -> ClaudeAgentOptions:
    """Options that are valid for both recording and substituting replay.

    ``tools=[]`` disables Claude's built-in tools and ``mcp_servers={}`` keeps
    external servers out, which is what lets the adapter prove every enabled
    tool is one it wraps. The adapter injects the wrapped ``ops`` server.
    """
    return ClaudeAgentOptions(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[],
        mcp_servers={},
        allowed_tools=list(TOOL_IDENTITIES),
        # No user or project settings: the recording must not depend on the
        # developer's ~/.claude, and substituting replay requires this anyway.
        setting_sources=[],
        max_turns=12,
    )


async def triage(prompt: str, *, model: str = DEFAULT_MODEL) -> ResultMessage | None:
    """Run one triage query and echo Claude's visible activity to stdout."""
    agent_id_value = os.environ.get("KITARU_AGENT_ID")
    runner = KitaruClaudeRunner(
        agent_id=uuid.UUID(agent_id_value) if agent_id_value else None,
        session_name=os.environ.get("KITARU_SESSION_NAME") or prompt.split(":", 1)[0],
    )
    stream = runner.query(
        prompt=prompt,
        options=build_options(model),
        replayable_servers=[OPS_SERVER],
    )
    terminal: ResultMessage | None = None
    async with contextlib.aclosing(stream) as messages:
        async for message in messages:
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        print(f"  -> {block.name} {json.dumps(block.input)}")
                    elif isinstance(block, TextBlock) and block.text.strip():
                        print(block.text.strip())
            elif isinstance(message, ResultMessage):
                terminal = message
    return terminal


def main(argv: list[str]) -> int:
    """Entry point used by both the recording run and the worker replay."""
    prompt = " ".join(argv) if argv else INCIDENTS["INC-1042"]
    terminal = asyncio.run(triage(prompt))
    if terminal is None:
        print("no terminal result", file=sys.stderr)
        return 1
    cost = f"${terminal.total_cost_usd:.4f}" if terminal.total_cost_usd is not None else "n/a"
    print(f"\n[done] turns={terminal.num_turns} cost={cost} is_error={terminal.is_error}")
    return 1 if terminal.is_error else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
