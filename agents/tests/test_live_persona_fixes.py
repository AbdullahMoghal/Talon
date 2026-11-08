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


# ---- From the talon-prod trace of the Chase scam (archive 20) ----

def test_never_hands_over_a_verification_code_or_login():
    for draft in ["here's the code: 345678, please send it to the number they gave", "the code is 472935",
                  "ok my pin is 4412", "my username is margaret52", "472935 is the code"]:
        assert any("verification code" in v or "username or password" in v for v in safety_rules.check(draft)), draft
    for draft in ["i didn't get a code, can you send it again?", "it was a $1249 purchase? i didn't buy that",
                  "i'm 72 and not good with these phones", "ok the code on the back is TW-AB2C-DE3F-GH4J"]:
        assert safety_rules.check(draft, allowed_tokens=["TW-AB2C-DE3F-GH4J"]) == [], draft


def test_ordinary_first_words_are_not_repetition():
    from talon_agents.agents.persona import style_issues
    from talon_agents.state import DEFAULT_PERSONA as P
    previous = ["the link didn't open, can you resend it?", "sure, where do i send it?", "got it, what's next?"]
    # Rejected live as repetitive; a person starts sentences with "the", "sure" and "got" all the time.
    assert style_issues("the code didn't come through, can you send another?", P, previous) == []
    assert style_issues("sure, what's the exact name on that account?", P, previous) == []
    # Still a tell: the same opening phrase, or the same filler opener again.
    assert any("the link didn't" in i for i in style_issues("the link didn't load either", P, previous))
    assert any('"ok"' in i for i in style_issues("ok and then?", P, ["ok so what now?"]))


def _handler_calls(llm: FakeLLM) -> list[dict]:
    return [c for c in llm.calls if c["agent"] == "handler"]


def test_handler_reasoning_modes():
    for mode, think, budget in [("full", True, None), ("budget", True, 384), ("off", False, None)]:
        llm = FakeLLM()
        engine = TalonEngine(llm=llm, settings=Settings(api_key=None, handler_reasoning=mode))
        warning = engine.receive_message("cust_a", "+12145550137", DEMO_OPENER)
        engine.request_takeover(warning["message_id"])
        first = _handler_calls(llm)[0]
        assert first["reasoning"] is think and first["reasoning_budget"] == budget, mode


def test_thinking_cut_short_hands_the_notes_back_and_acts_without_more_thinking():
    llm = FakeLLM()
    engine = TalonEngine(llm=llm, settings=Settings(api_key=None, handler_reasoning="budget"))
    llm.script("handler",
               LLMResponse(reasoning="They want a gift card. Plan: stall, then ask where to send it.",
                           thinking_cut_short=True),
               LLMResponse(tool_calls=[ToolCall("choose_tactic", {"tactic_id": "play_confused", "note": "stall"})]),
               '{"goal": "stall", "tactic": "play_confused", "instructions_for_persona": "Say you are confused."}')
    warning = engine.receive_message("cust_a", "+12145550137", DEMO_OPENER)
    session, _ = engine.request_takeover(warning["message_id"])
    calls = _handler_calls(llm)
    assert [c["reasoning"] for c in calls[:3]] == [True, False, False]
    notes = [m["content"] for m in calls[1]["messages"] if "planning notes so far" in str(m.get("content"))]
    assert notes and "Plan: stall" in notes[0]
    thought = engine.store.steps_for(session["id"], agent="handler", kind="thought")[0]
    assert thought.content.get("cut_short") is True


def test_ask_link_again_needs_a_link():
    llm = FakeLLM()
    engine = TalonEngine(llm=llm, settings=Settings(api_key=None))
    warning = engine.receive_message("cust_a", "+18885550142",
                                     "Chase Fraud Alert: did you attempt a $1,249.00 purchase? If NO call 1-888-555-0142")
    session, _ = engine.request_takeover(warning["message_id"])
    box = HandlerToolbox(state=engine.sessions[session["id"]], store=engine.store, taxonomy=load_taxonomy())
    assert "hasn't sent a link" in box.run("choose_tactic", {"tactic_id": "ask_link_again"})["error"]
    assert box.run("choose_tactic", {"tactic_id": "play_confused"})["ok"]
