"""Campaign Analyst: links a session to a campaign, decides whether to burn it, warns other customers,
and writes the customer's impact card.

Runs after the reply is sent, whenever new indicators were stored. Burning is guarded in code
(see AnalystToolbox): the model can ask, but weak evidence gets refused.
"""

from __future__ import annotations

import json
import re

from ..config import Settings
from ..text_style import no_dashes
from ..indicators import regex_extract
from ..llm import LLM, parse_json
from ..retrieval import ScamRetriever
from ..state import PAYMENT_KINDS, SessionState
from ..store import Store, Tracer, normalize_value
from ..taxonomy import Taxonomy, load_taxonomy
from ..tools import ANALYST_TOOLS, AnalystToolbox
from .base import tool_loop, user_payload

SYSTEM = """You are Talon's campaign analyst. New scam indicators were just extracted from a takeover session.
1. Call link_to_campaign to connect this session to a campaign.
2. If link_to_campaign returns burn_evidence_met: true, call burn_campaign now. Shutting the campaign down
   quickly protects other customers. If it is false, don't call it; wait for more evidence.
3. If the campaign is burned, call warn_customers.
Final answer, JSON only: {"decision": "<linked|burned|waiting>", "summary": "<one sentence>"}"""

INSIGHT_SYSTEM = """You write campaign summaries for T-Mobile fraud analysts watching Talon's dashboard. A scam
campaign was just shut down. In 2-3 plain sentences say what the scam is and who it impersonates, what the
scammer wanted and how they wanted to be paid, and how widely and how fast Talon contained it.
Use ONLY the facts given. Every number you write must appear in the facts. Quote links, phone numbers, emails
or payment handles exactly as they appear in the facts, or leave them out. No speculation, no advice to the
customer. Reply with the summary only."""

IMPACT_SYSTEM = """Write a short, warm note to a customer, often an older adult, after Talon stopped a scam that
was sent to them. Plain everyday words, no jargon, under 90 words, three short parts:
1. What happened: Talon caught a scam pretending to be <who> and dealt with it for them.
2. The red flags in that kind of text, in plain words (use the red_flags facts).
3. What to do next time (one or two of the what_to_do_next_time facts).
Use ONLY the facts given; every number you write must appear in the facts. Don't scold. Reply with the note only."""


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

    # The burn rule is policy, not a judgment call: if it's met and the model still waited, apply it.
    campaign_id = store.sessions[state.session_id].get("campaign_id")
    if campaign_id and store.campaigns[campaign_id]["status"] != "burned":
        met, rule = toolbox.evidence(campaign_id)
        if met:
            toolbox.run("burn_campaign", {"campaign_id": campaign_id, "reason": "evidence rule met"})
            warned = toolbox.run("warn_customers", {"campaign_id": campaign_id})
            out = {"decision": "burned", "source": "policy",
                   "summary": f"Evidence rule met ({rule}) so the campaign was burned by policy; "
                              f"{warned.get('customers_warned', 0)} other customer(s) warned."}
            tracer.step("analyst", "output", out)

    campaign = store.campaigns.get(store.sessions[state.session_id].get("campaign_id") or "")
    if campaign and campaign["status"] == "burned" and not campaign.get("insight_written"):
        campaign["insight_written"] = True
        write_insight(llm=llm, campaign=campaign, store=store, taxonomy=load_taxonomy(), tracer=tracer)
    return out


def insight_facts(campaign: dict, store: Store, taxonomy: Taxonomy) -> dict:
    indicators = [i for s in campaign["session_ids"] for i in store.indicators_for(s)]
    cat = taxonomy.category(campaign.get("category")) or {}
    seconds = (int((campaign["burned_at"] - campaign["first_seen"]) / 1000)
               if campaign.get("burned_at") and campaign.get("first_seen") else None)
    return {
        "scam_type": cat.get("name", "scam"),
        "impersonating": sorted({i["value"] for i in indicators if i["kind"] == "brand"}),
        "what_they_ask_for": cat.get("asks", []),
        "payment_methods": sorted({i["value"] for i in indicators if i["kind"] in PAYMENT_KINDS and i["kind"] != "giftcard_ask"}),
        "asked_for_gift_cards": any(i["kind"] == "giftcard_ask" for i in indicators),
        "scammer_links_and_numbers": sorted({i["value"] for i in indicators if i["kind"] in ("url", "phone", "email")})[:6],
        "sessions": len(campaign["session_ids"]),
        # Customers whose sessions are in the campaign, plus any warned later (warn_customers sets the larger count).
        "customers_targeted": max(int(campaign.get("customers_targeted") or 0),
                                  len({store.sessions[s]["customer_ref"] for s in campaign["session_ids"]})),
        "details_collected": len(indicators),
        "seconds_to_shut_down": seconds,
        "status": "shut down" if campaign["status"] == "burned" else "active",
    }


def check_insight(text: str, facts: dict) -> list[str]:
    """Anything checkable in the draft must come from the facts: numbers, links, numbers, handles."""
    problems = []
    fact_blob = json.dumps(facts)
    allowed_numbers = set(re.findall(r"\d+", fact_blob))
    made_up = [n for n in re.findall(r"\d+", text) if n not in allowed_numbers]
    if made_up:
        problems.append(f"numbers not in the facts: {made_up}")
    known = {normalize_value(v) for v in re.findall(r'"([^"]+)"', fact_blob)}
    for ind in regex_extract(text):
        if ind["kind"] != "brand" and normalize_value(ind["value"]) not in known:
            problems.append(f"{ind['kind']} not in the facts: {ind['value']}")
    if not text or len(text) > 700:
        problems.append("empty or too long")
    return problems


def write_insight(*, llm: LLM, campaign: dict, store: Store, taxonomy: Taxonomy, tracer: Tracer) -> dict:
    facts = insight_facts(campaign, store, taxonomy)
    messages = [{"role": "system", "content": INSIGHT_SYSTEM}, user_payload({"task": "insight", "facts": facts})]
    resp = llm.chat(agent="analyst", messages=messages, max_tokens=220)
    text = no_dashes(re.sub(r"<think>.*?</think>", "", resp.content or "", flags=re.S).strip())
    problems = check_insight(text, facts)
    if problems:
        tracer.step("analyst", "rejection", {"why": "insight cited something not in the data", "violations": problems,
                                             "draft": text})
        who = f" impersonating {', '.join(facts['impersonating'])}" if facts["impersonating"] else ""
        pay = f", asking for payment via {', '.join(facts['payment_methods'])}" if facts["payment_methods"] else ""
        when = f" in {facts['seconds_to_shut_down']} seconds" if facts["seconds_to_shut_down"] is not None else ""
        text = (f"{facts['scam_type']} campaign{who}{pay}. Talon collected {facts['details_collected']} details "
                f"across {facts['sessions']} session(s) and shut it down{when}.")
    row = store.add_insight(campaign["id"], "summary", text, confidence=0.9 if not problems else 0.7)
    tracer.step("analyst", "output", {"insight": text, "facts": facts}, resp.latency_ms)
    return row


def write_impact_card(*, llm: LLM, state: SessionState, store: Store, taxonomy: Taxonomy, tracer: Tracer) -> dict:
    session = store.sessions[state.session_id]
    campaign = store.campaigns.get(session.get("campaign_id") or "")
    indicators = store.indicators_for(state.session_id)
    cat = taxonomy.category(state.category) or {}
    facts = {
        "scam_type": cat.get("name", "scam"),
        "pretending_to_be": sorted({i["value"] for i in indicators if i["kind"] == "brand"}),
        "what_they_wanted": cat.get("asks", []),
        "red_flags": cat.get("hooks", []),
        "what_to_do_next_time": taxonomy.next_steps(state.category)[:3],
        "details_extracted": len(indicators),
        "kinds_extracted": sorted({i["kind"] for i in indicators}),
        "campaign_shut_down": bool(campaign and campaign["status"] == "burned"),
        "customers_protected": campaign["customers_targeted"] if campaign else 0,
        "scammer_messages": state.turn_count,
    }
    messages = [{"role": "system", "content": IMPACT_SYSTEM}, user_payload({"task": "impact_card", "facts": facts})]
    resp = llm.chat(agent="analyst", messages=messages, max_tokens=200)
    text = no_dashes(re.sub(r"<think>.*?</think>", "", resp.content or "", flags=re.S).strip())

    # Numbers may come from the facts, including ones inside next steps (e.g. "forward it to 7726").
    allowed_numbers = set(re.findall(r"\d+", json.dumps(facts)))
    bad = [n for n in re.findall(r"\d+", text) if n not in allowed_numbers]
    if bad or not text or len(text) > 700:
        tracer.step("analyst", "rejection", {"why": "impact card cited numbers not in the facts", "numbers": bad,
                                             "draft": text})
        who = f" pretending to be {', '.join(facts['pretending_to_be'])}" if facts["pretending_to_be"] else ""
        flags = ", ".join(facts["red_flags"][:2])
        tip = facts["what_to_do_next_time"][0] if facts["what_to_do_next_time"] else ""
        kind = facts["scam_type"].lower()
        text = (f"Talon caught {'an' if kind[:1] in 'aeiou' else 'a'} {kind} scam{who} and handled it for you."
                + (f" Watch for texts about {flags}." if flags else "")
                + (f" Next time: {tip}" if tip else ""))
    card = store.add_impact_card(state.session_id, campaign["id"] if campaign else None, text,
                                 [i["id"] for i in indicators])
    tracer.step("analyst", "output", {"impact_card": text, "facts": facts}, resp.latency_ms)
    return card
