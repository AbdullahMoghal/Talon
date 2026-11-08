"""Extractor agent: pulls indicators (links, numbers, wallets, payment asks) from a scammer turn.

The model proposes; code disposes. Each indicator must appear in the text and match its
format, or it's dropped and the rejection is traced.
"""

from __future__ import annotations

from ..indicators import validate
from ..llm import LLM, parse_json
from ..store import Store, Tracer, normalize_value
from ..taxonomy import Taxonomy
from .base import user_payload

SYSTEM = """You are Talon's extraction agent. From one scammer message, list every indicator the scammer revealed.

Indicator kinds: {kinds}
- url: links or bare domains. phone: callback numbers. email. wallet: crypto addresses.
- payment_handle: Cash App/Venmo/Zelle handles. account: bank account or routing numbers.
- giftcard_ask: the sentence asking for gift cards. remote_access_id: remote-support session codes.
- brand: the company, agency or service the scammer claims to be or to represent when it is named in the
  message (e.g. a toll agency, bank, carrier, retailer, delivery company or government office). Include it
  whenever one is named, even if it is the first word of the message.

Copy each value exactly as written in the message. Never invent or complete values.
Answer with JSON only: {{"indicators": [{{"kind": "<kind>", "value": "<exact text>", "confidence": <0..1>}}]}}"""


def run_extractor(*, llm: LLM, text: str, taxonomy: Taxonomy, store: Store, tracer: Tracer,
                  session_id: str, turn_id: str, category: str | None) -> list[dict]:
    cat = taxonomy.category(category) or {}
    messages = [
        {"role": "system", "content": SYSTEM.format(kinds=", ".join(taxonomy.indicator_types))},
        user_payload({"message": text, "likely_brands": cat.get("brands", [])}),
    ]
    resp = llm.chat(agent="extractor", messages=messages)
    try:
        proposed = parse_json(resp.content).get("indicators", [])
    except ValueError as e:
        tracer.step("extractor", "rejection", {"why": str(e), "raw": resp.content[:300]}, resp.latency_ms)
        return []

    known = {(i["kind"], normalize_value(i["value"])) for i in store.indicators_for(session_id)}
    stored, dropped = [], []
    for item in proposed:
        kind, value = str(item.get("kind", "")), str(item.get("value", "")).strip()
        why = validate(kind, value, text, taxonomy.indicator_types)
        if why:
            dropped.append({"kind": kind, "value": value, "why": why})
            continue
        if (kind, normalize_value(value)) in known:
            continue  # already have it from an earlier turn
        known.add((kind, normalize_value(value)))
        conf = max(0.0, min(1.0, float(item.get("confidence") or 0.8)))
        stored.append(store.add_indicator(session_id, turn_id, kind, value, conf))

    if dropped:
        tracer.step("extractor", "rejection", {"dropped": dropped})
    tracer.step("extractor", "output", {"new_indicators": [{"id": i["id"], "kind": i["kind"], "value": i["value"]}
                                                           for i in stored]}, resp.latency_ms)
    return stored
