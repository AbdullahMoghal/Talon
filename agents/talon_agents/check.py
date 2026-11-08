"""Check that the configured model server works before running the engine on it.

    python -m talon_agents.check

For each endpoint: lists the models it serves, then for each agent's model checks a plain
reply, JSON output, and a tool call. Exits non-zero if anything fails.
"""

from __future__ import annotations

import sys
import time

from .config import AGENTS, Settings
from .llm import NemotronLLM, parse_json

TOOL = [{
    "type": "function",
    "function": {
        "name": "get_intel_gaps",
        "description": "Return which scam indicators are still missing.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}]


def main() -> int:
    settings = Settings.from_env()
    if settings.use_fake:
        print("No NEMOTRON_API_KEY or NVIDIA_API_KEY set (or TALON_FAKE_LLM=1), so the engine would use FakeLLM.")
        return 1
    llm = NemotronLLM(settings)
    failures = 0

    for url in sorted({settings.base_url_for(a) for a in AGENTS}):
        agent = next(a for a in AGENTS if settings.base_url_for(a) == url)
        try:
            served = [m.id for m in llm._client(agent).models.list().data]
            print(f"[ok]   {url} serves: {', '.join(served)}")
        except Exception as e:  # noqa: BLE001 - report any connection or auth error
            print(f"[FAIL] {url}: {e}")
            failures += 1
            continue
        wanted = {settings.model_for(a) for a in AGENTS if settings.base_url_for(a) == url}
        for model in sorted(wanted - set(served)):
            print(f"[FAIL] {model} is configured but {url} doesn't serve it")
            failures += 1

    checked: set[tuple[str, str]] = set()
    for agent in ("handler", "safety"):  # handler covers the shared default model; safety may differ
        key = (settings.base_url_for(agent), settings.model_for(agent))
        if key in checked:
            continue
        checked.add(key)
        model = key[1]
        failures += _check(f"{model}: plain reply", lambda: llm.chat(
            agent=agent, messages=[{"role": "user", "content": "Say hi in three words."}], max_tokens=32).content)
        if agent == "safety" and model != settings.model_for("handler"):
            continue  # guard models answer in their own format; the safety agent handles that
        failures += _check(f"{model}: JSON", lambda: parse_json(llm.chat(
            agent=agent, max_tokens=64, temperature=0,
            messages=[{"role": "user", "content": 'Reply with only this JSON: {"ok": true}'}]).content))
        failures += _check(f"{model}: tool call", lambda: _tool_call(llm, agent))
        failures += _check(f"{model}: /think reasoning", lambda: llm.chat(
            agent=agent, reasoning=True, max_tokens=256,
            messages=[{"role": "user", "content": "Is 17 prime? One word."}]).reasoning or "(no reasoning returned)")

    print("\nAll checks passed." if not failures else f"\n{failures} check(s) failed.")
    return 1 if failures else 0


def _tool_call(llm: NemotronLLM, agent: str) -> str:
    out = llm.chat(agent=agent, tools=TOOL, max_tokens=256, temperature=0, messages=[
        {"role": "system", "content": "You plan replies to a scammer. Use your tools."},
        {"role": "user", "content": "Find out which indicators we still need."}])
    if not out.tool_calls:
        raise RuntimeError(f"no tool call; replied {out.content[:120]!r}. Is the server's tool-call parser on?")
    return f"called {out.tool_calls[0].name}"


def _check(label: str, fn) -> int:
    start = time.perf_counter()
    try:
        result = fn()
    except Exception as e:  # noqa: BLE001
        print(f"[FAIL] {label}: {e}")
        return 1
    print(f"[ok]   {label} ({int((time.perf_counter() - start) * 1000)} ms): {str(result)[:100]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
