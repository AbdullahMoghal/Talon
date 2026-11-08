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

CATEGORY_SEP = chr(10)

SYSTEM = """You are Talon's triage agent. You read one text message a mobile customer received and decide
whether it is a scam.

Common scam types (id: description):
{categories}

Scam texts usually impersonate a known brand or agency and push the reader to act through the message
itself: pay a fee, click a link, call a number, reply, or share personal details, often with a deadline
or a threat. Real companies do send texts too (one-time codes the customer requested, delivery updates,
appointment reminders, fraud alerts that ask you to call the number on your card), so be honest about
uncertainty. If you are unsure, call search_similar_scams first. If you are confident, answer directly.
Scammers often warm up first ("hi", "is this Sam?") and ask later. Judge the newest message in light of any
earlier messages from the same sender: asking for an SSN, passwords, codes, account numbers or money from
someone claiming to be family or a company is a scam even without a link.

Answer with JSON only:
{{"scam_probability": <0..1: the chance this message is a scam; near 1 = surely a scam, near 0 = surely legitimate>,
  "category": "<category id if it is a scam, else null>",
  "reason": "<one plain-language sentence a customer would understand>"}}"""


def run_triage(*, llm: LLM, text: str, taxonomy: Taxonomy, retriever: ScamRetriever, tracer: Tracer,
               settings: Settings, context: list[str] | None = None) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM.format(categories=CATEGORY_SEP.join(
            f"- {c['id']}: {c['description']}" for c in taxonomy.categories.values()))},
        user_payload({"message": text, **({"earlier_messages_from_this_sender": context} if context else {})}),
    ]

    def run_tool(name: str, args: dict) -> dict:
        if name != "search_similar_scams":
            return {"error": f"unknown tool {name!r}"}
        matches = retriever.search(args.get("query") or text)
        # Show overlap as a word count, not a 0..1 score: models copy decimals into their own probability.
        return {"matches": [{"category": m["category"],
                             "description": (taxonomy.category(m["category"]) or {}).get("description", ""),
                             "shared_words": m["matched"]} for m in matches],
                "note": "Matches are keyword overlaps with known scam patterns, not probabilities."}

    resp, calls = tool_loop(llm=llm, agent="triage", messages=messages, tools=TRIAGE_TOOLS, run_tool=run_tool,
                            tracer=tracer, max_calls=1)
    try:
        out = parse_json(resp.content)
    except ValueError as e:
        tracer.step("triage", "rejection", {"why": str(e), "raw": resp.content[:300]})
        out = {"is_scam": False, "category": None, "confidence": 0.5, "reason": "Talon couldn't classify this message."}

    prob = out.get("scam_probability", out.get("confidence"))
    try:
        confidence = max(0.0, min(1.0, float(prob)))
    except (TypeError, ValueError):
        confidence = 0.5
    category = out.get("category") if out.get("category") in taxonomy.categories else None
    is_scam = confidence >= 0.5
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
