"""The reason -> act -> observe loop shared by tool-using agents (Triage, Handler, Analyst)."""

from __future__ import annotations

import json
from typing import Callable

from ..llm import LLM, LLMResponse, assistant_message, tool_message
from ..store import Tracer


def user_payload(payload: dict) -> dict:
    """Agents receive their input as a JSON user message; the system prompt explains the fields."""
    return {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}


def tool_loop(
    *,
    llm: LLM,
    agent: str,
    messages: list[dict],
    tools: list[dict],
    run_tool: Callable[[str, dict], dict],
    tracer: Tracer,
    max_calls: int,
    reasoning: bool = False,
    max_tokens: int = 512,
    final_nudge: str = "You've used your tool budget. Give your final answer now, as JSON only.",
) -> tuple[LLMResponse, int]:
    """Call the model, run any tools it asks for, feed results back, repeat until it answers.

    Every thought, tool call and tool result is written to the trace. Returns the final
    response and the number of tool calls made.
    """
    calls = 0
    while True:
        offer_tools = tools if calls < max_calls else None
        resp = llm.chat(agent=agent, messages=messages, tools=offer_tools, reasoning=reasoning, max_tokens=max_tokens)
        if resp.reasoning:
            tracer.step(agent, "thought", {"text": resp.reasoning}, resp.latency_ms)
        if not resp.tool_calls:
            return resp, calls
        messages.append(assistant_message(resp))
        for call in resp.tool_calls:
            if calls >= max_calls:
                result = {"error": "tool budget used up"}
            else:
                tracer.step(agent, "tool_call", {"tool": call.name, "args": call.arguments}, resp.latency_ms)
                result = run_tool(call.name, call.arguments)
                tracer.step(agent, "tool_result", {"tool": call.name, "result": result})
                calls += 1
            messages.append(tool_message(call, result))
        if calls >= max_calls:
            messages.append({"role": "user", "content": final_nudge})
