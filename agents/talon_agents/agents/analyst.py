"""Campaign Analyst: links a session to a campaign, decides whether to burn it, warns other customers,
and writes the customer's impact card.

Runs after the reply is sent, whenever new indicators were stored. Burning is guarded in code
(see AnalystToolbox): the model can ask, but weak evidence gets refused.
"""

from __future__ import annotations

import re

from ..config import Settings
from ..llm import LLM, parse_json
from ..retrieval import ScamRetriever
from ..state import SessionState
from ..store import Store, Tracer
from ..taxonomy import Taxonomy
from ..tools import ANALYST_TOOLS, AnalystToolbox
from .base import tool_loop, user_payload

SYSTEM = """You are Talon's campaign analyst. New scam indicators were just extracted from a takeover session.
1. Call link_to_campaign to connect this session to a campaign.
2. If the evidence is strong (indicators shared with other sessions, or a payment method from a high-confidence
   scam), call burn_campaign. The tool refuses weak evidence; accept that and wait for more.
3. If the campaign is burned, call warn_customers.
Final answer, JSON only: {"decision": "<linked|burned|waiting>", "summary": "<one sentence>"}"""

IMPACT_SYSTEM = """Write a short, warm message (2-3 sentences) to a customer who handed a scam text to Talon,
telling them what their tap achieved. Use ONLY the facts given; every number you write must appear in the facts.
Explain in plain words what the scammer was after, so the customer recognizes it next time.
Reply with the message text only."""


def run_analyst(*, llm: LLM, state: SessionState, store: Store, tracer: Tracer, settings: Settings,
                retriever: ScamRetriever | None = None) -> dict:
    toolbox = AnalystToolbox(state=state, store=store, retriever=retriever)
    payload = {"session_id": state.session_id, "category": state.category, "triage_confidence": state.confidence,
               "indicators": [{"kind": i["kind"], "value": i["value"]} for i in store.indicators_for(state.session_id)]}
    messages = [{"role": "system", "content": SYSTEM}, user_payload(payload)]
    resp, _ = tool_loop(llm=llm, agent="analyst", messages=messages, tools=ANALYST_TOOLS, run_tool=toolbox.run,
                        tracer=tracer, max_calls=4)
    try:
        out = parse_json(resp.content)
    except ValueError:
        out = {"decision": "unknown", "summary": resp.content[:200]}
    tracer.step("analyst", "output", out, resp.latency_ms)
    return out


def write_impact_card(*, llm: LLM, state: SessionState, store: Store, taxonomy: Taxonomy, tracer: Tracer) -> dict:
    session = store.sessions[state.session_id]
    campaign = store.campaigns.get(session.get("campaign_id") or "")
    indicators = store.indicators_for(state.session_id)
    cat = taxonomy.category(state.category) or {}
    facts = {
        "scam_type": cat.get("name", "scam"),
        "what_they_wanted": cat.get("asks", []),
        "details_extracted": len(indicators),
        "kinds_extracted": sorted({i["kind"] for i in indicators}),
        "campaign_shut_down": bool(campaign and campaign["status"] == "burned"),
        "customers_protected": campaign["customers_targeted"] if campaign else 0,
        "scammer_messages": state.turn_count,
    }
    messages = [{"role": "system", "content": IMPACT_SYSTEM}, user_payload({"task": "impact_card", "facts": facts})]
    resp = llm.chat(agent="analyst", messages=messages, max_tokens=200)
    text = (resp.content or "").strip()

    allowed_numbers = {str(v) for v in facts.values() if isinstance(v, int) and not isinstance(v, bool)}
    bad = [n for n in re.findall(r"\d+", text) if n not in allowed_numbers]
    if bad or not text:
        tracer.step("analyst", "rejection", {"why": "impact card cited numbers not in the facts", "numbers": bad,
                                             "draft": text})
        text = (f"Thanks for handing that {facts['scam_type'].lower()} text to Talon. We pulled "
                f"{facts['details_extracted']} details from the scammer"
                + (f" and shut the campaign down, protecting {facts['customers_protected']} customers." if
                   facts["campaign_shut_down"] else ", and we're watching for the rest of their campaign."))
    card = store.add_impact_card(state.session_id, campaign["id"] if campaign else None, text,
                                 [i["id"] for i in indicators])
    tracer.step("analyst", "output", {"impact_card": text, "facts": facts}, resp.latency_ms)
    return card
