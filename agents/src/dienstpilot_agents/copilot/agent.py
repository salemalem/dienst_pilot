"""The C8 agent: a LangGraph loop of model turns and MCP tool calls, then a grounding check.

    think  -> (tool calls) -> act -> think ... -> final_answer -> ground -> end

Nothing here decides an assignment or touches data except through the user's MCP tools. Before a
request leaves, ``Aliases.findings`` scans the text that is new in it; a finding stops the run
instead of sending. The answer is shown only if every number in it is grounded (see
``grounding``); otherwise the deterministic fallback, built from the tool calls alone, is shown and
labelled. The model, the prompt and the limits (8 turns, 1,200 output tokens) are fixed in
``RELEASE_GATES.md``.
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from dienstpilot_agents.copilot.grounding import Pool
from dienstpilot_agents.copilot.guard import Aliases, Finding, delimit_free_text
from dienstpilot_agents.copilot.prompt import MAX_TURNS, request_for, tools_for
from dienstpilot_agents.copilot.tools import (
    FINAL,
    LOCAL,
    Toolbox,
    ToolResult,
    calculate,
    compact,
)
from dienstpilot_agents.llm.types import LlmClient, LlmError, LlmResponse

MAX_RESULT_CHARS = 200_000
PERSONA_KEYS = (
    "kaya",
    "mehta",
    "weber",
    "alvarez",
    "nowak",
    "lorenz",
    "schulz",
    "brandt",
    "hoffmann",
    "vogel",
)

FALLBACK = {
    "de": (
        "Die KI-Antwort konnte nicht gegen die Daten abgesichert werden und wird deshalb "
        "nicht angezeigt. Abgefragte Quellen: "
    ),
    "en": (
        "The AI answer could not be checked against the data and is therefore not shown. "
        "Sources queried: "
    ),
}
EMPTY = {"de": "keine", "en": "none"}


@dataclass
class ToolCall:
    """One tool call of a run, as the model made it (aliases, not ids)."""

    name: str
    args: dict[str, Any]
    is_error: bool
    result_chars: int = 0


@dataclass
class Turn:
    """One model call and what came back from the tools it asked for."""

    request_key: str
    blocks: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    usage: dict[str, int]
    latency_s: float | None
    model: str
    new_text: str  # what was new in the request: the text the privacy scan looked at


@dataclass
class RunResult:
    """Everything one question produced."""

    question: str
    final: dict[str, Any] | None
    served: str  # shown to the user: names restored, or the labelled fallback
    fallback: bool
    fallback_reason: str | None
    ungrounded: list[str]
    turns: list[Turn]
    calls: list[ToolCall]
    findings: list[Finding]
    aborted: str | None
    value_id: Any = None  # ``final.value`` with a person alias resolved to the id
    meta: dict[str, Any] = field(default_factory=dict)


class State(TypedDict):
    """The graph state."""

    messages: list[dict[str, Any]]
    turns: list[Turn]
    calls: list[ToolCall]
    final: dict[str, Any] | None
    aborted: str | None
    findings: list[Finding]
    served: str
    fallback: bool
    fallback_reason: str | None
    ungrounded: list[str]


def _texts(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for b in content:
        if b.get("type") == "tool_result":
            parts.append(_texts(b.get("content", "")))
        elif b.get("type") == "text":
            parts.append(b["text"])
    return "\n".join(parts)


def fallback_text(language: str, calls: list[ToolCall]) -> str:
    """Build the labelled fallback from the tool calls alone (no model text in it)."""
    lang = "de" if language == "de" else "en"
    seen: list[str] = []
    for c in calls:
        if c.is_error or c.name == LOCAL:
            continue
        args = ", ".join(f"{k}={v}" for k, v in c.args.items() if not isinstance(v, (list, dict)))
        label = f"{c.name}({args})"
        if label not in seen:
            seen.append(label)
    return FALLBACK[lang] + (", ".join(seen) if seen else EMPTY[lang]) + "."


async def run(
    *,
    question: str,
    language: str,
    role: str,
    today: str,
    model: str,
    client: LlmClient,
    toolbox: Toolbox,
    aliases: Aliases,
) -> RunResult:
    """Answer one question. Never raises for model or tool trouble: it returns what happened."""
    mcp_tools = await toolbox.tools()
    tools = tools_for(mcp_tools)
    pool = Pool(question, today)
    asked = aliases.to_model(question)
    first = (
        f"Today (demo clock): {today}. User role: {role}. Language: {language}.\nQuestion:\n{asked}"
    )

    async def think(state: State) -> dict[str, Any]:
        new_text = _texts(state["messages"][-1]["content"])
        findings = aliases.findings(new_text, PERSONA_KEYS)
        if len(state["messages"]) == 1:
            from dienstpilot_agents.copilot.prompt import SYSTEM

            findings += aliases.findings(SYSTEM, PERSONA_KEYS, health=False)
        if findings:
            return {"aborted": "privacy", "findings": [*state["findings"], *findings]}
        request = request_for(model, state["messages"], tools)
        try:
            resp: LlmResponse = await asyncio.to_thread(client.complete, request)
        except LlmError as e:
            return {"aborted": f"llm_error: {e}"}
        turn = Turn(
            request_key=resp.request_key,
            blocks=resp.blocks,
            tool_results=[],
            usage=dict(resp.usage.__dict__),
            latency_s=resp.latency_s,
            model=resp.model,
            new_text=new_text,
        )
        update: dict[str, Any] = {
            "messages": [*state["messages"], {"role": "assistant", "content": resp.blocks}],
            "turns": [*state["turns"], turn],
        }
        uses = [b for b in resp.blocks if b["type"] == "tool_use"]
        finals = [b for b in uses if b["name"] == FINAL]
        if len(uses) == 1 and finals:
            update["final"] = dict(finals[0]["input"])
        elif not uses:
            update["final"] = {"answer": resp.text, "value": None}
        elif len(state["turns"]) + 1 >= MAX_TURNS:
            update["aborted"] = "max_turns"
        return update

    async def run_tool(block: dict[str, Any]) -> tuple[dict[str, Any], ToolCall]:
        name, args = block["name"], dict(block["input"])
        if name == FINAL:
            result = ToolResult("call final_answer alone, after the other tools", True)
        elif name == LOCAL:
            result = calculate(args, pool)
        else:
            result = await toolbox.call(name, aliases.ids_in(args))
        if result.is_error:
            content = str(result.data)
        else:
            shown = delimit_free_text(aliases.alias_json(result.data))
            pool.add_result(shown)
            content = compact(shown)
            if len(content) > MAX_RESULT_CHARS:
                result = ToolResult("result too large", True)
                content = "result too large: ask for a narrower month or person"
        if result.is_error:
            content = aliases.to_model(content)
        block_out = {
            "type": "tool_result",
            "tool_use_id": block["id"],
            "content": content,
            "is_error": result.is_error,
        }
        return block_out, ToolCall(name, args, result.is_error, len(content))

    async def act(state: State) -> dict[str, Any]:
        uses = [b for b in state["turns"][-1].blocks if b["type"] == "tool_use"]
        done = [await run_tool(b) for b in uses]  # one after the other: deterministic
        results = [r for r, _ in done]
        calls = [c for _, c in done]
        state["turns"][-1].tool_results = results
        update: dict[str, Any] = {
            "messages": [*state["messages"], {"role": "user", "content": results}],
            "calls": [*state["calls"], *calls],
        }
        for r, c in done:
            if c.name == "search_rules" and not c.is_error:
                try:
                    data = json.loads(r["content"])
                except ValueError:
                    data = {}
                if data.get("fallback"):
                    update["aborted"] = "search_fallback"
        return update

    async def ground(state: State) -> dict[str, Any]:
        final = state["final"] or {}
        text = str(final.get("answer", ""))
        bad = pool.ungrounded(text)
        value = final.get("value")
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and not pool.knows(float(value))
        ):
            bad.append(float(value))
        if bad:
            return {
                "ungrounded": list(dict.fromkeys(str(b) for b in bad)),
                "fallback": True,
                "fallback_reason": "ungrounded numbers",
                "served": fallback_text(language, state["calls"]),
            }
        return {"served": aliases.from_model(text)}

    def after_think(state: State) -> str:
        if state["aborted"]:
            return "end"
        return "ground" if state["final"] is not None else "act"

    def after_act(state: State) -> str:
        return "end" if state["aborted"] else "think"

    graph = StateGraph(State)
    graph.add_node("think", think)
    graph.add_node("act", act)
    graph.add_node("ground", ground)
    graph.set_entry_point("think")
    graph.add_conditional_edges(
        "think", after_think, {"end": END, "ground": "ground", "act": "act"}
    )
    graph.add_conditional_edges("act", after_act, {"end": END, "think": "think"})
    graph.add_edge("ground", END)
    state: State = await graph.compile().ainvoke(  # type: ignore[assignment]
        {
            "messages": [{"role": "user", "content": first}],
            "turns": [],
            "calls": [],
            "final": None,
            "aborted": None,
            "findings": [],
            "served": "",
            "fallback": False,
            "fallback_reason": None,
            "ungrounded": [],
        },
        {"recursion_limit": 60},
    )
    served, fallback, reason = state["served"], state["fallback"], state["fallback_reason"]
    if state["aborted"] or state["final"] is None:
        served = fallback_text(language, state["calls"])
        fallback, reason = True, state["aborted"] or "no answer"
    final = state["final"]
    value = None if final is None else final.get("value")
    return RunResult(
        question=question,
        final=final,
        served=served,
        fallback=fallback,
        fallback_reason=reason,
        ungrounded=state["ungrounded"],
        turns=state["turns"],
        calls=state["calls"],
        findings=state["findings"],
        aborted=state["aborted"],
        value_id=aliases.id_of.get(value, value) if isinstance(value, str) else value,
    )
