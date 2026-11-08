"""Heuristic stand-ins for each agent's model, used by FakeLLM.

They read the same JSON payloads and tool results a real model would, and answer in the
same formats, including tool calls. They're deliberately simple: enough to drive full
takeovers offline and in tests, not to be smart.
"""

from __future__ import annotations

import json
import re

from .indicators import regex_extract
from .llm import LLMResponse, ToolCall
from .retrieval import ScamRetriever
from .taxonomy import load_taxonomy

URGENCY = re.compile(r"\b(urgent|immediately|now|today|final|suspend|locked|expire|within \d+|asap|act fast|last chance)\b", re.I)
PAYMENT = re.compile(r"\b(pay|payment|fee|gift ?card|wallet|bitcoin|crypto|zelle|cash ?app|venmo|wire|deposit)\b", re.I)
LINK_OR_NUMBER = re.compile(r"https?://|\b[a-z0-9-]+\.[a-z]{2,}\b|\d{3}[\s.-]?\d{4}", re.I)


def _payload(messages: list[dict]) -> dict:
    for m in reversed(messages):
        if m["role"] == "user":
            try:
                return json.loads(m["content"])
            except (json.JSONDecodeError, TypeError):
                continue
    return {}


def _tool_results(messages: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for m in messages:
        if m["role"] == "tool":
            out.setdefault(m["name"], []).append(json.loads(m["content"]))
    return out


def _call(name: str, **args) -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(name=name, arguments=args)])


def _json(obj: dict, reasoning: str | None = None) -> LLMResponse:
    return LLMResponse(content=json.dumps(obj), reasoning=reasoning)


def triage(messages, tools):
    text = _payload(messages).get("message", "")
    tax = load_taxonomy()
    matches = _tool_results(messages).get("search_similar_scams")
    top = (matches[0]["matches"] if matches else ScamRetriever(tax).search(text, k=1)) or [{}]
    signals = sum(bool(p.search(text)) for p in (URGENCY, PAYMENT, LINK_OR_NUMBER))
    confidence = min(0.97, 0.2 + 0.2 * signals + top[0].get("score", 0))
    if tools and not matches and 0.4 <= confidence <= 0.8:
        return _call("search_similar_scams", query=text)
    if matches:
        confidence = min(0.97, confidence + 0.1)
    is_scam = confidence >= 0.5
    return _json({"is_scam": is_scam, "category": top[0].get("category") if is_scam else None,
                  "confidence": round(confidence, 2),
                  "reason": "Asks you to act fast and pay or click through an unofficial channel." if is_scam
                  else "No link, payment ask or pressure tactics."})


# The taxonomy lists brand types ("toll agencies"); a real model knows names. The fake gets a short list.
KNOWN_BRANDS = ["E-ZPass", "SunPass", "TxTag", "NTTA", "FasTrak", "USPS", "UPS", "FedEx", "DHL", "Amazon", "Walmart",
                "Target", "Costco", "Medicare", "IRS", "Social Security", "DMV", "T-Mobile", "AT&T", "Verizon", "Apple",
                "Microsoft", "Netflix", "Geek Squad", "Norton", "McAfee", "Chase", "Wells Fargo", "Bank of America",
                "Citi", "Capital One", "PayPal", "Coinbase", "Binance", "Red Cross"]


def extractor(messages, tools):
    p = _payload(messages)
    return _json({"indicators": regex_extract(p.get("message", ""), KNOWN_BRANDS)})


MISSING_TO_TACTIC = {
    "url": "ask_link_again", "phone": "ask_callback_number", "email": "ask_company_details",
    "payment_method": "ask_who_to_pay", "wallet": "ask_who_to_pay", "payment_handle": "ask_who_to_pay",
    "account": "ask_who_to_pay", "giftcard_ask": "ask_who_to_pay", "brand": "ask_company_details",
    "remote_access_id": "accept_next_step",
}


def handler(messages, tools):
    p = _payload(messages)
    done = _tool_results(messages)
    if not tools:  # budget used up: answer with whatever tactic was chosen
        return _handler_final(done)
    if "get_intel_gaps" not in done:
        return _call("get_intel_gaps")
    gaps = done["get_intel_gaps"][0]
    new = [i for i in p.get("new_indicators", []) if i["kind"] not in ("brand", "giftcard_ask")]
    if new and "lookup_indicator" not in done:
        return _call("lookup_indicator", value=new[0]["value"])
    asks_giftcards = re.search(r"gift ?card", p.get("scammer_message", ""), re.I)
    if p.get("turn", 0) >= 6 and not gaps["missing"] and not asks_giftcards and "end_takeover" not in done:
        return _call("end_takeover", reason="all intel goals met")
    if asks_giftcards and "issue_tripwire" not in done:
        return _call("issue_tripwire", kind="giftcard")
    if "choose_tactic" not in done:
        used = p.get("tactics_used_so_far", [])
        if asks_giftcards:
            tactic = "issue_tripwire"
        else:
            options = [MISSING_TO_TACTIC.get(m, "accept_next_step") for m in gaps["missing"]]
            options += [t for t in p.get("category_tactics", [])] + ["payment_trouble", "accept_next_step", "play_confused"]
            tactic = next((t for t in options if t not in used), None) or next(
                (t for t in options if used.count(t) < 2), "play_confused")
        need = ", ".join(gaps["missing"]) or "nothing; keep them talking"
        return _call("choose_tactic", tactic_id=tactic, note=f"have {gaps['collected'] or 'nothing'}; need {need}")
    return _handler_final(done)


def _handler_final(done: dict) -> LLMResponse:
    tactic = done.get("choose_tactic", [{}])[-1].get("tactic", "play_confused")
    gaps = done.get("get_intel_gaps", [{"collected": [], "missing": []}])[0]
    trip = done.get("issue_tripwire", [{}])[-1].get("code_for_persona")
    instructions = {
        "ask_link_again": "Say the link won't open on your phone and ask them to send it again or another site.",
        "ask_callback_number": "Say you'd feel better talking on the phone and ask what number to call.",
        "ask_who_to_pay": "Agree to pay and ask exactly where to send it and who to make it out to.",
        "payment_trouble": "Say your card got declined and ask if there's another way to pay.",
        "ask_company_details": "Ask which company and department they're with and for a case number.",
        "accept_next_step": "Go along with it and ask what you should do next.",
        "play_confused": "Get mixed up and ask them to explain it again slowly.",
        "issue_tripwire": f"Say you bought the gift card and read them the code {trip}.",
    }[tactic]
    return _json({"goal": f"get them to use tactic {tactic}", "tactic": tactic, "instructions_for_persona": instructions},
                 reasoning=f"Collected {gaps['collected']}; missing {gaps['missing']}. Going with {tactic}.")


PERSONA_LINES = {
    "ask_link_again": "oh dear the link just shows a blank page on my phone. can you send it again or is there another site?",
    "ask_callback_number": "I'm not very good with texting, is there a number I can call you at instead?",
    "ask_who_to_pay": "ok I can pay that, where exactly do I send it and who do I make it out to?",
    "payment_trouble": "my card got declined, the bank does that sometimes. is there another way I can pay?",
    "ask_company_details": "which company did you say you're with? my grandson says to always get a case number",
    "accept_next_step": "alright, I think I did that part. what do I do next?",
    "play_confused": "I'm sorry I don't follow, can you explain that again slowly?",
}


def persona(messages, tools):
    plan = _payload(messages).get("handler_plan", {})
    tactic = plan.get("tactic", "play_confused")
    if tactic == "issue_tripwire":
        codes = _payload(messages).get("tripwire_codes_you_may_use") or []
        return LLMResponse(content=f"ok I got the card, the code on the back is {codes[-1]}" if codes
                           else PERSONA_LINES["play_confused"])
    return LLMResponse(content=PERSONA_LINES.get(tactic, PERSONA_LINES["play_confused"]))


def safety(messages, tools):
    return _json({"safe": True, "reason": "plain conversational text"})


def analyst(messages, tools):
    p = _payload(messages)
    if p.get("task") == "impact_card":
        f = p["facts"]
        n = f["customers_protected"]
        burned = (f" and helped shut down a campaign that targeted {n} customer{'s' if n != 1 else ''}"
                  if f["campaign_shut_down"] else "")
        return LLMResponse(content=f"You turned a scam around ({f['scam_type'].lower()}). Talon pulled "
                                   f"{f['details_extracted']} details from the scammer{burned}. "
                                   f"They were after your {', '.join(f['what_they_wanted'][:2]) or 'money'}, "
                                   f"so watch for that ask next time.")
    done = _tool_results(messages)
    if not tools:
        return _json({"decision": "waiting", "summary": "tool budget used"})
    if "link_to_campaign" not in done:
        return _call("link_to_campaign")
    link = done["link_to_campaign"][0]
    strong = link["sessions"] >= 2 or (link["payment_indicators"] and link["triage_confidence"] >= 0.9)
    if link["status"] != "burned" and strong and "burn_campaign" not in done:
        return _call("burn_campaign", campaign_id=link["campaign_id"],
                     reason=f"{link['sessions']} sessions share indicators" if link["sessions"] >= 2
                     else "payment method from a high-confidence scam")
    if link["status"] == "burned":
        return _json({"decision": "burned", "summary": f"Campaign {link['campaign_id']} was already burned; "
                      "new indicators added to its blocklist."})
    burn = done.get("burn_campaign", [{}])[-1]
    if burn.get("ok") and "warn_customers" not in done:
        return _call("warn_customers", campaign_id=link["campaign_id"])
    if burn.get("ok"):
        return _json({"decision": "burned", "summary": f"Campaign {link['campaign_id']} burned."})
    return _json({"decision": "linked", "summary": f"Linked to {link['campaign_id']}; waiting for more evidence."})


DEFAULT_RESPONDERS = {"triage": triage, "extractor": extractor, "handler": handler, "persona": persona,
                      "safety": safety, "analyst": analyst}
