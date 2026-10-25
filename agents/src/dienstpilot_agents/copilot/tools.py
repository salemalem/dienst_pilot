# ruff: noqa: E501
"""The agent's tools: the signed-in user's MCP tools, one local calculator, and ``final_answer``.

All access to the system goes through MCP (no SQL, no imports of backend code). The list of tools
is whatever the servers list for the user's token, so an Oversight user gets read-only tools and
nobody gets a publish or approve tool: none exists. ``calculate`` only does arithmetic on numbers
that already appear in the question or in earlier results of the same run.
"""

import json
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Protocol

from dienstpilot_agents.copilot.grounding import Pool
from dienstpilot_agents.llm.types import Tool

SERVERS = ("roster", "planning", "rules", "forecast", "notify")
WRITE_TOOLS = ("create_proposal", "draft_announcement")
LOCAL = "calculate"
FINAL = "final_answer"

CALCULATE = Tool(
    LOCAL,
    "Arithmetic on numbers that already appear in the question or in earlier tool results: "
    "sum, difference (first minus second), count, count_greater_than (needs threshold), max, "
    "min. Use it instead of counting or adding by hand. Operands you invent are refused.",
    {
        "type": "object",
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["sum", "difference", "count", "count_greater_than", "max", "min"],
            },
            "values": {"type": "array", "items": {"type": "number"}, "minItems": 1},
            "threshold": {"type": "number"},
        },
        "required": ["operation", "values"],
    },
)

FINAL_ANSWER = Tool(
    FINAL,
    "End the run with your answer. Call it alone, once, after you have what you need.",
    {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "maxLength": 1200,
                "description": "The reply to the user, in the user's language. Use the aliases (P1, P2 ...) for people.",
            },
            "value": {
                "anyOf": [{"type": "number"}, {"type": "string"}, {"type": "null"}],
                "description": "The single figure that answers the question: a number (a count, hours, a mean), an ISO date (YYYY-MM-DD), or a person alias only when the question asks WHO. A question about a person (\"how many ... has P3\") is answered with the number, never with the alias. null when no single figure is asked for.",
            },
            "valid": {
                "anyOf": [{"type": "boolean"}, {"type": "null"}],
                "description": "For a what-if: whether the validator found no violation; otherwise null.",
            },
            "violations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "For a what-if: the rule codes of the violations the validator reported.",
            },
            "citations": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ids of rule passages (for example arbzg:§5:1) that your answer rests on and that a rule tool returned in this run.",
            },
            "no_source": {
                "type": "boolean",
                "description": "True if the question is about a rule and the rulebook has no passage that answers it.",
            },
            "refused": {
                "type": "boolean",
                "description": "True if you cannot do what was asked because no tool allows it (publishing, approving, deciding, sending, closing).",
            },
        },
        "required": ["answer"],
    },
)


@dataclass(frozen=True)
class ToolResult:
    """What a tool call gave back: JSON data, or an error text the model can read."""

    data: Any
    is_error: bool = False


class Toolbox(Protocol):
    """The tools of one run."""

    async def tools(self) -> list[Tool]:
        """List the tools this user may use (MCP tools only)."""

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Call one MCP tool as this user."""


Connect = Callable[[str], AbstractAsyncContextManager[Any]]


class McpToolbox:
    """MCP tools over Streamable HTTP; ``connect(server)`` opens a client with the user's token."""

    def __init__(self, connect: Connect) -> None:
        """Remember how to reach the servers."""
        self._connect = connect
        self._server_of: dict[str, str] = {}
        self._listed: list[Tool] | None = None

    async def tools(self) -> list[Tool]:
        """List tools server by server; a server the role may not use is skipped."""
        if self._listed is not None:
            return self._listed
        out: list[Tool] = []
        for server in SERVERS:
            try:
                async with self._connect(server) as client:
                    listed = (await client.list_tools()).tools
            except Exception:  # the role has no tools on this server (403) or it is down
                continue
            for t in listed:
                self._server_of[t.name] = server
                out.append(Tool(t.name, t.description or "", dict(t.input_schema)))
        self._listed = sorted(out, key=lambda t: t.name)
        return self._listed

    async def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Call a tool; API and validation errors come back as readable errors."""
        await self.tools()
        server = self._server_of.get(name)
        if server is None:
            return ToolResult(f"unknown tool {name}", True)
        try:
            async with self._connect(server) as client:
                r = await client.call_tool(name, args)
        except Exception as e:
            return ToolResult(f"{type(e).__name__}: {e}", True)
        if r.is_error:
            text = " ".join(getattr(c, "text", "") for c in r.content)
            return ToolResult(text or "tool error", True)
        if r.structured_content is not None:
            return ToolResult(r.structured_content)
        return ToolResult(" ".join(getattr(c, "text", "") for c in r.content))


def calculate(args: dict[str, Any], pool: Pool) -> ToolResult:
    """Do the arithmetic if every operand is grounded; the result becomes grounded too."""
    op = args.get("operation")
    values = args.get("values")
    if (
        not isinstance(values, list)
        or not values
        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)
    ):
        return ToolResult("values must be a non-empty list of numbers", True)
    for v in values:
        if not pool.knows(float(v)):
            return ToolResult(
                f"operand {v} does not appear in the question or in earlier tool results", True
            )
    nums = [float(v) for v in values]
    result: float
    if op == "sum":
        result = sum(nums)
    elif op == "difference":
        if len(nums) != 2:
            return ToolResult("difference needs exactly two values", True)
        result = nums[0] - nums[1]
    elif op == "count":
        result = float(len(nums))
    elif op == "count_greater_than":
        threshold = args.get("threshold")
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            return ToolResult("count_greater_than needs a threshold", True)
        if not pool.knows(float(threshold)):
            return ToolResult(f"threshold {threshold} is not in the question", True)
        result = float(sum(1 for v in nums if v > float(threshold)))
    elif op == "max":
        result = max(nums)
    elif op == "min":
        result = min(nums)
    else:
        return ToolResult(f"unknown operation {op}", True)
    pool.add([result])
    return ToolResult({"operation": op, "result": int(result) if result == int(result) else result})


def compact(data: Any) -> str:
    """Serialize a tool result the way the model sees it (compact JSON, no ASCII escapes)."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))
