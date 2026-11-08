"""Model clients: an OpenAI-compatible Nemotron client and a FakeLLM for tests and offline work.

Every agent calls `llm.chat(agent=..., messages=..., tools=..., reasoning=...)` and gets an
LLMResponse back, so swapping FakeLLM for Nemotron changes no agent code.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable, Protocol

from .config import Settings


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str = field(default_factory=lambda: f"call_{uuid.uuid4().hex[:12]}")


@dataclass
class LLMResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str | None = None
    latency_ms: int = 0
    model: str = ""


class LLM(Protocol):
    def chat(
        self,
        *,
        agent: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        reasoning: bool = False,
        max_tokens: int = 512,
        temperature: float = 0.6,
    ) -> LLMResponse: ...


def parse_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (models sometimes wrap it in prose or fences)."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start : i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    raise ValueError(f"no JSON object in model output: {text[:200]!r}")


def assistant_message(resp: LLMResponse) -> dict:
    """The assistant turn to append to the history after a tool-calling response."""
    msg: dict = {"role": "assistant", "content": resp.content or ""}
    if resp.tool_calls:
        msg["tool_calls"] = [
            {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
            for tc in resp.tool_calls
        ]
    return msg


def tool_message(call: ToolCall, result: object) -> dict:
    return {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": json.dumps(result)}


class NemotronLLM:
    """Any OpenAI-compatible endpoint: build.nvidia.com, OpenRouter, or vLLM/NIM on Brev.

    Reasoning is toggled with the `/think` / `/no_think` system-prompt switch used by
    Nemotron Nano 9B v2. Check this against the model we settle on: newer Nemotron
    models may use a different switch.
    """

    def __init__(self, settings: Settings):
        from openai import OpenAI

        self.settings = settings
        self.client = OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=60)

    def chat(self, *, agent, messages, tools=None, reasoning=False, max_tokens=512, temperature=0.6):
        model = self.settings.model_for(agent)
        switch = {"role": "system", "content": "/think" if reasoning else "/no_think"}
        kwargs: dict = dict(
            model=model,
            messages=[switch, *messages],
            max_tokens=max_tokens if not reasoning else max(max_tokens, 2048),
            temperature=temperature,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        start = time.perf_counter()
        out = self.client.chat.completions.create(**kwargs)
        latency = int((time.perf_counter() - start) * 1000)
        msg = out.choices[0].message
        content = msg.content or ""
        reasoning_text = getattr(msg, "reasoning_content", None)
        m = re.search(r"<think>(.*?)</think>", content, flags=re.S)
        if m:
            reasoning_text = reasoning_text or m.group(1).strip()
            content = content.replace(m.group(0), "").strip()
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": tc.function.arguments}
            calls.append(ToolCall(name=tc.function.name, arguments=args, id=tc.id))
        return LLMResponse(content=content, tool_calls=calls, reasoning=reasoning_text, latency_ms=latency, model=model)


Responder = Callable[[list[dict], list[dict] | None], LLMResponse]


class FakeLLM:
    """Deterministic stand-in for Nemotron.

    Each agent gets a responder: by default a heuristic one from `fake_responders`, which
    behaves plausibly enough to run full takeovers offline. Tests can queue exact replies
    per agent with `script(agent, *replies)`; queued replies are used first.
    """

    def __init__(self, responders: dict[str, Responder] | None = None):
        from .fake_responders import DEFAULT_RESPONDERS

        self.responders = {**DEFAULT_RESPONDERS, **(responders or {})}
        self.queues: dict[str, deque] = defaultdict(deque)
        self.calls: list[dict] = []

    def script(self, agent: str, *replies: str | LLMResponse) -> "FakeLLM":
        for r in replies:
            self.queues[agent].append(r if isinstance(r, LLMResponse) else LLMResponse(content=r))
        return self

    def chat(self, *, agent, messages, tools=None, reasoning=False, max_tokens=512, temperature=0.6):
        self.calls.append({"agent": agent, "messages": messages, "tools": tools})
        if self.queues[agent]:
            resp = self.queues[agent].popleft()
        elif agent in self.responders:
            resp = self.responders[agent](messages, tools)
        else:
            raise KeyError(f"FakeLLM has no responder for agent {agent!r}")
        resp.model = resp.model or "fake"
        return resp


def make_llm(settings: Settings) -> LLM:
    return FakeLLM() if settings.use_fake else NemotronLLM(settings)
