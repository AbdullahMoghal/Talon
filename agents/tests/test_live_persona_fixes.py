"""Fixes for problems seen in the live run on Nemotron Nano with the safety guard (Nov 8):

1. The persona suggested gift cards before the scammer ever mentioned one ("can you try gift card instead?").
2. When the scammer asked for a gift card, the handler issued a tripwire code but picked "play_confused",
   so the code never reached the scammer.
3. The extractor missed the brand, so "brand" stayed missing and the handler kept asking who they were.
"""

from __future__ import annotations

from talon_agents import safety_rules
from talon_agents.cli import DEMO_OPENER
from talon_agents.config import Settings
from talon_agents.engine import TalonEngine
from talon_agents.llm import FakeLLM, LLMResponse, ToolCall
from talon_agents.taxonomy import load_taxonomy
from talon_agents.tools import HandlerToolbox

GIFT_CARD_ASK = "Ok then buy a $100 Apple gift card and send me the code on the back"


def start(llm: FakeLLM) -> tuple[TalonEngine, str]:
    engine = TalonEngine(llm=llm, settings=Settings(api_key=None))
    warning = engine.receive_message("cust_a", "+12145550137", DEMO_OPENER)
    session, _ = engine.request_takeover(warning["message_id"])
    return engine, session["id"]


def test_naming_a_payment_method_first_is_rejected():
    history = "E-ZPass: unpaid toll. Pay today at ezpass-tollpay.example/pay"
    assert safety_rules.leading_payment("the link seems broken, can you try gift card instead?", history)
    assert safety_rules.leading_payment("could i just zelle it to you?", history)
    assert safety_rules.leading_payment("can we try a bank transfer or something else?", history)  # live Nano
    assert not safety_rules.leading_payment("the link is broken, is there another way to pay?", history)
    # Once the scammer brings it up, the persona can talk about it.
    assert not safety_rules.leading_payment("ok i got the gift card, what now?", history + " " + GIFT_CARD_ASK)
    assert not safety_rules.leading_payment("my apple card got declined", history)  # a credit card, not a gift card


def test_persona_suggesting_gift_cards_is_sent_back_to_rewrite():
    llm = FakeLLM().script("persona", "the link seems broken, can you try gift card instead?")
    engine, sid = start(llm)
    rejection = engine.store.steps_for(sid, agent="safety", kind="rejection")[0]
    assert any("payment method the scammer hasn't mentioned (gift card)" in v for v in rejection.content["violations"])
    sent = [t["text"] for t in engine.store.turns_for(sid) if t["sender"] == "talon"]
    assert sent and "gift card" not in sent[0].lower()


def test_tripwire_code_is_read_out_even_when_the_handler_picks_another_tactic():
    llm = FakeLLM()
    engine, sid = start(llm)
    # What live Nano did: issue the code, then choose "play_confused" with instructions that drop the code.
    llm.script("handler",
               LLMResponse(tool_calls=[ToolCall("issue_tripwire", {"kind": "giftcard"})]),
               LLMResponse(tool_calls=[ToolCall("choose_tactic", {"tactic_id": "play_confused", "note": "stall"})]),
               '{"goal": "find out the brand", "tactic": "play_confused", '
               '"instructions_for_persona": "Act confused about the gift card and ask what TollDesk is."}')
    reply = engine.handle_scammer_message(sid, GIFT_CARD_ASK)
    token = engine.sessions[sid].tripwire_tokens[-1]
    plan = [s for s in engine.store.steps_for(sid, agent="handler", kind="output")][-1].content
    assert plan["tactic"] == "issue_tripwire" and token in plan["instructions_for_persona"]
    assert token in reply


def test_gift_card_ask_gets_a_tripwire_even_if_the_handler_never_issues_one():
    llm = FakeLLM()
    engine, sid = start(llm)
    llm.script("handler",
               LLMResponse(tool_calls=[ToolCall("choose_tactic", {"tactic_id": "play_confused", "note": "stall"})]),
               '{"goal": "stall", "tactic": "play_confused", "instructions_for_persona": "Say you are confused."}')
    reply = engine.handle_scammer_message(sid, GIFT_CARD_ASK)
    state = engine.sessions[sid]
    assert len(state.tripwire_tokens) == 1 and state.tripwire_tokens[0] in reply
    calls = engine.store.steps_for(sid, agent="handler", kind="tool_call")
    assert any(c.content.get("by") == "policy" and c.content["tool"] == "issue_tripwire" for c in calls)


def test_a_missing_brand_is_not_something_the_handler_chases():
    engine, sid = start(FakeLLM())
    gaps = HandlerToolbox(state=engine.sessions[sid], store=engine.store, taxonomy=load_taxonomy()).run(
        "get_intel_gaps", {})
    assert "brand" not in gaps["missing"] and "brand" not in gaps["wanted"]


def test_lowercase_tripwire_code_is_restored_and_sent_exactly():
    # Live Nano texts in lowercase and wrote "tw-5avg-c9c4-car7"; the exact-code check rejected it three times.
    llm = FakeLLM()
    engine, sid = start(llm)
    llm.script("handler",
               LLMResponse(tool_calls=[ToolCall("issue_tripwire", {"kind": "giftcard"})]),
               '{"goal": "g", "tactic": "issue_tripwire", "instructions_for_persona": "read the code"}')
    token_holder = {}

    def persona(messages, tools):
        token = engine.sessions[sid].tripwire_tokens[-1]
        token_holder["t"] = token
        return LLMResponse(content=f"ok i bought it, the code is {token.lower()}. did that work?")

    llm.responders["persona"] = persona
    reply = engine.handle_scammer_message(sid, GIFT_CARD_ASK)
    assert token_holder["t"] in reply
    assert not engine.store.steps_for(sid, agent="safety", kind="rejection")


def test_a_changed_code_is_still_rejected():
    from talon_agents.agents.safety import restore_tokens
    token = "TW-5AVG-C9C4-CAR7"
    assert restore_tokens("code is tw-5avg-c9c4-car7", [token]) == f"code is {token}"
    assert token not in restore_tokens("code is tw 5avg c9c4 car7", [token])
    assert token not in restore_tokens("code is TW-5AVG-C9C4-CAR8", [token])
