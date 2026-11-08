"""Triage agent: scam or not, category, confidence, reason.

Agentic RAG: the model decides whether to retrieve. A confident verdict is returned straight
away; an unsure one calls search_similar_scams first. Either way the decision is traced.
Next steps for the customer come from the taxonomy, never from the model.
"""

from __future__ import annotations

from ..config import Settings
from ..llm import LLM, parse_json
from ..retrieval import ScamRetriever
from ..store import Tracer
from ..taxonomy import Taxonomy
from ..tools import TRIAGE_TOOLS
from .base import tool_loop, user_payload

SYSTEM = """You are Talon's triage agent. You read one text message a mobile customer received and decide
whether it is a scam.

Scam categories (use these ids exactly): {categories}

Legitimate messages exist that look scammy (real one-time codes, real delivery notices, real fraud alerts):
be honest about uncertainty. If you are unsure of the verdict or category, call search_similar_scams
first. If you are confident, answer directly without searching.

Answer with JSON only:
{{"is_scam": true|false, "category": "<category id or null>", "confidence": <0..1, your probability it is a scam>,
  "reason": "<one plain-language sentence a customer would understand>"}}"""


def run_triage(*, llm: LLM, text: str, taxonomy: Taxonomy, retriever: ScamRetriever, tracer: Tracer,
               settings: Settings) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM.format(categories=", ".join(taxonomy.categories))},
        user_payload({"message": text}),
    ]

    def run_tool(name: str, args: dict) -> dict:
        if name != "search_similar_scams":
            return {"error": f"unknown tool {name!r}"}
        return {"matches": retriever.search(args.get("query") or text)}

    resp, calls = tool_loop(llm=llm, agent="triage", messages=messages, tools=TRIAGE_TOOLS, run_tool=run_tool,
                            tracer=tracer, max_calls=1)
    try:
        out = parse_json(resp.content)
    except ValueError as e:
        tracer.step("triage", "rejection", {"why": str(e), "raw": resp.content[:300]})
        out = {"is_scam": False, "category": None, "confidence": 0.5, "reason": "Talon couldn't classify this message."}

    confidence = max(0.0, min(1.0, float(out.get("confidence") or 0)))
    category = out.get("category") if out.get("category") in taxonomy.categories else None
    is_scam = bool(out.get("is_scam")) and confidence >= 0.5
    result = {
        "is_scam": is_scam,
        "category": category if is_scam else None,
        "confidence": round(confidence, 3),
        "reason": str(out.get("reason") or "")[:300],
        "next_steps": taxonomy.next_steps(category) if is_scam else [],
        "retrieved": calls > 0,
    }
    if calls == 0:
        tracer.step("triage", "retrieval_skipped", {"why": "confident without retrieval", "confidence": result["confidence"]})
    tracer.step("triage", "output", result, resp.latency_ms)
    return result
