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
    reason_steps: int | None = None,
    reason_budget: int | None = None,
    max_tokens: int = 512,
    final_nudge: str = "You've used your tool budget. Give your final answer now, as JSON only.",
) -> tuple[LLMResponse, int]:
    """Call the model, run any tools it asks for, feed results back, repeat until it answers.

    Every thought, tool call and tool result is written to the trace. Returns the final
    response and the number of tool calls made.
    """
    calls = steps = 0
    while True:
        offer_tools = tools if calls < max_calls else None
        # reason_steps limits /think to the first N model calls: plan once, then act fast.
        think = reasoning and (reason_steps is None or steps < reason_steps)
        resp = llm.chat(agent=agent, messages=messages, tools=offer_tools, reasoning=think, max_tokens=max_tokens,
                        reasoning_budget=reason_budget if think else None)
        steps += 1
        if resp.reasoning:
            tracer.step(agent, "thought", {"text": resp.reasoning, **({"cut_short": True} if resp.thinking_cut_short
                                                                      else {})}, resp.latency_ms)
        if resp.thinking_cut_short:
            # Out of thinking budget before acting: hand the notes back and ask for action, without more reasoning.
            notes = (resp.reasoning or "")[-2000:]
            messages.append({"role": "user", "content": "Your planning notes so far (you hit the thinking limit):\n"
                             f"{notes}\nAct on them now: call your tools or give your final answer."})
            continue
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
