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
PERSONAL_INFO = re.compile(r"\b(ssn|social security|password|passcode|pin|verification code|one[- ]time code|"
                           r"bank account|routing number|account number|date of birth|mother'?s maiden)\b", re.I)
FAMILY = re.compile(r"\b(grandma|grandpa|grandson|granddaughter|it'?s (?:me|your) (?:son|daughter|mom|dad))\b", re.I)
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
    p = _payload(messages)
    # Judge the newest message; earlier ones only add context (e.g. who the sender claims to be).
    newest = p.get("message", "")
    text = " ".join([*p.get("earlier_messages_from_this_sender", []), newest])
    tax = load_taxonomy()
    matches = _tool_results(messages).get("search_similar_scams")
    top = ScamRetriever(tax).search(text, k=1) or [{}]
    signals = sum(bool(p.search(newest)) for p in (URGENCY, PAYMENT, LINK_OR_NUMBER))
    # Short small talk with no ask ("hey", "ok thanks") isn't a scam, whatever came before it.
    small_talk = signals == 0 and not PERSONAL_INFO.search(newest) and len(newest.split()) <= 4
    confidence = min(0.97, 0.2 + 0.2 * signals + (0 if small_talk else top[0].get("score", 0)))
    if PERSONAL_INFO.search(newest):  # asking for an SSN, codes or account details is a scam on its own
        confidence = max(confidence, 0.85)
    if tools and not matches and 0.4 <= confidence <= 0.8:
        return _call("search_similar_scams", query=text)
    if matches:
        confidence = min(0.97, confidence + 0.1)
    is_scam = confidence >= 0.5
    category = top[0].get("category")
    reason = "Asks you to act fast and pay or click through an unofficial channel."
    if PERSONAL_INFO.search(newest):
        reason = "Asks for personal information like an SSN or account details, which real people and companies don't request by text."
    if FAMILY.search(text):
        category = "family_emergency"
        reason = "Claims to be family and asks for personal information or money. Call them on a number you know."
    return _json({"scam_probability": round(confidence, 2),
                  "category": category if is_scam else None,
                  "reason": reason if is_scam else "No link, payment ask or pressure tactics."})


# The taxonomy lists brand types ("toll agencies"); a real model knows names. The fake gets a short list.
KNOWN_BRANDS = ["E-ZPass", "SunPass", "TxTag", "NTTA", "FasTrak", "USPS", "UPS", "FedEx", "DHL", "Amazon", "Walmart",
                "Target", "Costco", "Medicare", "IRS", "Social Security", "DMV", "T-Mobile", "AT&T", "Verizon", "Apple",
                "Microsoft", "Netflix", "Geek Squad", "Norton", "McAfee", "Chase", "Wells Fargo", "Bank of America",
                "Citi", "Capital One", "PayPal", "Coinbase", "Binance", "Red Cross"]


def extractor(messages, tools):
    p = _payload(messages)
    return _json({"indicators": regex_extract(p.get("message", ""), KNOWN_BRANDS)})


MISSING_TO_TACTIC = {
    "url": "ask_link_again", "phone": "ask_contact_details", "email": "ask_company_details",
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
        "ask_contact_details": "Say texts from this number keep getting lost and ask for another number to text or an email.",
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
    "ask_contact_details": "my phone keeps losing your texts, is there another number I can text you at, or an email?",
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


HARMFUL = re.compile(r"\b(?:kill|hurt you|shoot|bomb|stupid idiot)\b", re.I)
SCAMMY = re.compile(r"\b(?:pay|gift card|verify|fee|account|link|wire|crypto|code)\b", re.I)


def safety(messages, tools):
    content = messages[-1]["content"]
    if "<BEGIN CONVERSATION>" not in content:
        return _json({"safe": True, "reason": "plain conversational text"})
    # Stands in for the Nemotron safety guard: same template in, same JSON out.
    convo = content.split("<BEGIN CONVERSATION>", 1)[1].split("<END CONVERSATION>", 1)[0]
    user, _, response = convo.partition("\nresponse: agent: ")
    user = user.strip().removeprefix("user: ").strip()
    response = response.strip() if _ else None
    cats, out = [], {"User Safety": "safe"}
    if HARMFUL.search(user) or SCAMMY.search(user):
        out["User Safety"] = "unsafe"
        cats.append("Threat" if HARMFUL.search(user) else "Fraud/Deception")
    if response is not None:
        out["Response Safety"] = "unsafe" if HARMFUL.search(response) else "safe"
        if HARMFUL.search(response):
            cats.append("Violence")
    if cats:
        out["Safety Categories"] = ", ".join(dict.fromkeys(cats))
    return _json(out)


def analyst(messages, tools):
    p = _payload(messages)
    if p.get("task") == "insight":
        f = p["facts"]
        who = f" impersonating {', '.join(f['impersonating'])}" if f["impersonating"] else ""
        when = f" in {f['seconds_to_shut_down']} seconds" if f["seconds_to_shut_down"] is not None else ""
        return LLMResponse(content=f"{f['scam_type']} campaign{who}. Talon collected {f['details_collected']} details "
                                   f"across {f['sessions']} session(s) and shut it down{when}.")
    if p.get("task") == "impact_card":
        f = p["facts"]
        n = f["customers_protected"]
        burned = (f" and helped shut down a campaign that targeted {n} customer{'s' if n != 1 else ''}"
                  if f["campaign_shut_down"] else "")
        who = f" pretending to be {', '.join(f['pretending_to_be'])}" if f.get("pretending_to_be") else ""
        flags = ", ".join(f.get("red_flags", [])[:2])
        tip = (f.get("what_to_do_next_time") or [""])[0]
        kind = f["scam_type"].lower()
        return LLMResponse(content=f"Talon caught {'an' if kind[:1] in 'aeiou' else 'a'} {kind} scam{who} and handled it for you{burned}. "
                                   f"They were after your {', '.join(f['what_they_wanted'][:2]) or 'money'}."
                                   + (f" Watch for texts about {flags}." if flags else "")
                                   + (f" Next time: {tip}" if tip else ""))
    done = _tool_results(messages)
    if not tools:
        return _json({"decision": "waiting", "summary": "tool budget used"})
    if "link_to_campaign" not in done:
        return _call("link_to_campaign")
    link = done["link_to_campaign"][0]
    strong = link.get("burn_evidence_met", False)  # the rule lives in AnalystToolbox.evidence
    if link["status"] != "burned" and strong and "burn_campaign" not in done:
        return _call("burn_campaign", campaign_id=link["campaign_id"],
                     reason=f"{link['sessions']} sessions share indicators" if link["sessions"] >= 2
                     else "payment method in a confirmed scam")
    if link["status"] == "burned":
        return _json({"decision": "burned", "summary": f"Campaign {link['campaign_id']} was already burned; "
                      "new indicators added to its blocklist."})
    burn = done.get("burn_campaign", [{}])[-1]
    if burn.get("ok") and "warn_customers" not in done:
        return _call("warn_customers", campaign_id=link["campaign_id"])
    if burn.get("ok"):
        return _json({"decision": "burned", "summary": f"Campaign {link['campaign_id']} burned."})
    return _json({"decision": "linked", "summary": f"Linked to {link['campaign_id']}; waiting for more evidence."})


def scammer(messages: list[dict], tools: list[dict] | None) -> LLMResponse:
    """Plays the scam simulator offline: the same text with a new opening, every indicator intact."""
    return LLMResponse(content=f"Reminder, last chance: {messages[-1]['content']}")


DEFAULT_RESPONDERS = {"triage": triage, "extractor": extractor, "handler": handler, "persona": persona,
                      "safety": safety, "safety_review": safety, "analyst": analyst, "scammer": scammer}
