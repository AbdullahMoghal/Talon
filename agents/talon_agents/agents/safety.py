"""Safety reviewer: deterministic rules first, then the Nemotron safety model.

A rejection goes back to the persona with the reasons. The engine allows 2 retries, then
sends a canned safe line.
"""

from __future__ import annotations

import json

from .. import safety_rules
from ..llm import LLM, parse_json
from ..store import Tracer

SAFE_FALLBACK = "sorry dear, my phone is acting up, what was that?"

SYSTEM = """You are a content safety reviewer. Talon's decoy persona is about to send the reply below to a
suspected scammer. Decide whether it is safe to send: no real personal data, no threats or harassment,
no instructions for anything harmful, nothing that reveals it is an AI.
Answer with JSON only: {"safe": true|false, "reason": "<short reason>"}"""


def _model_verdict(content: str) -> tuple[bool, str]:
    """Accept our own {"safe": bool} format or a Nemotron safety-guard style {"Response Safety": "unsafe"}."""
    try:
        data = parse_json(content)
    except ValueError:
        return False, "safety model returned no verdict"
    if "safe" in data:
        return bool(data["safe"]), str(data.get("reason", ""))
    values = json.dumps(data).lower()
    if "unsafe" in values:
        return False, str(data.get("Safety Categories") or "flagged unsafe")
    return True, ""


def run_safety(*, llm: LLM, text: str, tracer: Tracer, allowed_tokens: list[str],
               forbidden_strings: list[str] | None = None) -> dict:
    violations = safety_rules.check(text, allowed_tokens=allowed_tokens, forbidden_strings=forbidden_strings)
    if violations:
        verdict = {"passed": False, "source": "rules", "violations": violations, "draft": text}
        tracer.step("safety", "rejection", verdict)
        return verdict
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]
    resp = llm.chat(agent="safety", messages=messages, max_tokens=100, temperature=0.0)
    safe, reason = _model_verdict(resp.content)
    if not safe:
        verdict = {"passed": False, "source": "model", "violations": [reason or "unsafe"], "draft": text}
        tracer.step("safety", "rejection", verdict, resp.latency_ms)
        return verdict
    verdict = {"passed": True, "source": "rules+model", "violations": []}
    tracer.step("safety", "output", verdict, resp.latency_ms)
    return verdict
