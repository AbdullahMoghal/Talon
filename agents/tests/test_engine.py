"""End-to-end engine tests on FakeLLM. No network, no API key."""

from __future__ import annotations

import json

import pytest

from talon_agents.agents.safety import SAFE_FALLBACK
from talon_agents.cli import DEMO_OPENER, DEMO_TURNS, SECOND_CUSTOMER_TEXT
from talon_agents.config import Settings
from talon_agents.engine import TalonEngine
from talon_agents.llm import FakeLLM, LLMResponse, ToolCall


def make_engine(llm: FakeLLM | None = None) -> TalonEngine:
    return TalonEngine(llm=llm or FakeLLM(), settings=Settings(api_key=None))


def start(engine: TalonEngine, opener: str = DEMO_OPENER, customer: str = "cust_a", sender: str = "+12145550137"):
    warning = engine.receive_message(customer, sender, opener)
    assert warning["status"] == "warned"
    session, reply = engine.request_takeover(warning["message_id"])
    return session["id"], reply


def test_six_turn_takeover_end_to_end():
    engine = make_engine()
    sid, first_reply = start(engine)
    assert first_reply
    replies = [engine.handle_scammer_message(sid, t) for t in DEMO_TURNS[:5]]
    assert all(replies), replies
    assert engine.store.sessions[sid]["status"] == "active"
    assert engine.store.sessions[sid]["turn_count"] == 6

    kinds = {i["kind"] for i in engine.store.indicators_for(sid)}
    assert {"url", "phone", "email", "payment_handle", "giftcard_ask", "brand"} <= kinds

    agents = {s.agent for s in engine.store.steps_for(sid)}
    assert {"extractor", "handler", "persona", "safety", "analyst"} <= agents
    # The handler calls at least one tool every turn.
    for turn in [t for t in engine.store.turns_for(sid) if t["sender"] == "scammer"]:
        calls = [s for s in engine.store.steps if s.turn_id == turn["id"] and s.agent == "handler" and s.kind == "tool_call"]
        assert calls, f"no handler tool call on turn {turn['text']!r}"
    assert len(engine.store.handler_plans) == 6
    assert engine.store.tripwires  # the gift card ask got a fictional tripwire code

    # Turn 7: every goal is met, so the handler ends the takeover itself.
    assert engine.handle_scammer_message(sid, DEMO_TURNS[5]) is None
    assert engine.store.sessions[sid]["ended_reason"] == "handler: all intel goals met"
    assert engine.store.impact_cards[-1]["session_id"] == sid


def test_takeover_only_on_customer_tap():
    engine = make_engine()
    warning = engine.receive_message("cust_a", "+12145550137", DEMO_OPENER)
    assert warning["buttons"] == ["delete", "report", "let_talon_handle_it"]
    assert not engine.store.sessions  # nothing happens until the tap


def test_legit_message_gets_no_takeover_button():
    engine = make_engine()
    result = engine.receive_message("cust_a", "+12145550100", "Hey are we still on for dinner Sunday?")
    assert result["status"] == "delivered"
    assert result["buttons"] == []


def test_safety_rejection_then_retry():
    llm = FakeLLM().script("persona", "sure, go to refund-help.example and I'll pay there",
                           "oh dear, which company did you say this was?")
    engine = make_engine(llm)
    sid, reply = start(engine)
    assert reply == "oh dear, which company did you say this was?"
    rejections = engine.store.steps_for(sid, agent="safety", kind="rejection")
    assert len(rejections) == 1
    assert "contains a link" in rejections[0].content["violations"]
    drafts = engine.store.steps_for(sid, agent="persona", kind="output")
    assert drafts[1].content["retry"] is True
    talon_turns = [t["text"] for t in engine.store.turns_for(sid) if t["sender"] == "talon"]
    assert talon_turns == [reply]  # the rejected draft never went out


def test_persona_gets_rejection_reasons_on_retry():
    llm = FakeLLM().script("persona", "I'm an AI assistant, how can I help?", "what was that dear?")
    engine = make_engine(llm)
    start(engine)
    retry_call = [c for c in llm.calls if c["agent"] == "persona"][1]
    payload = json.loads(retry_call["messages"][-1]["content"])
    assert "reveals it's an AI or Talon" in payload["your_last_draft_was_rejected_because"]


def test_fallback_after_retries_exhausted():
    llm = FakeLLM().script("persona", "call me at 214-555-0100", "call me at 214-555-0100", "call me at 214-555-0100")
    engine = make_engine(llm)
    sid, reply = start(engine)
    assert reply == SAFE_FALLBACK
    assert len(engine.store.steps_for(sid, agent="safety", kind="rejection")) == 3


def test_safety_model_can_reject_what_rules_pass():
    llm = FakeLLM().script("safety", '{"safe": false, "reason": "threatening"}')
    engine = make_engine(llm)
    sid, _ = start(engine)
    rejection = engine.store.steps_for(sid, agent="safety", kind="rejection")[0]
    assert rejection.content["source"] == "model"


def test_three_fallback_turns_end_the_session():
    llm = FakeLLM().script("persona", *["visit scam.example"] * 9)
    engine = make_engine(llm)
    sid, _ = start(engine)
    engine.handle_scammer_message(sid, "hello?")
    engine.handle_scammer_message(sid, "are you there")
    assert engine.store.sessions[sid]["ended_reason"] == "safety_risk"


def test_stop_ends_session_and_blocks_further_replies():
    engine = make_engine()
    sid, _ = start(engine)
    card = engine.stop_takeover(sid)
    assert card and card["session_id"] == sid
    assert engine.handle_scammer_message(sid, "hello??") is None
    with pytest.raises(PermissionError):
        engine.store.add_turn(sid, "talon", "late reply")


def test_handler_cannot_choose_unknown_tactic():
    bad = LLMResponse(tool_calls=[ToolCall("choose_tactic", {"tactic_id": "threaten_them", "note": "x"})])
    llm = FakeLLM().script("handler", bad, '{"goal": "g", "tactic": "threaten_them", "instructions_for_persona": "x"}')
    engine = make_engine(llm)
    sid, _ = start(engine)
    result = [s for s in engine.store.steps_for(sid, agent="handler", kind="tool_result")][0]
    assert "error" in result.content["result"]
    plan = engine.store.handler_plans[0]
    assert plan["tactic"] in engine.taxonomy.tactics  # fell back to a real tactic


def test_handler_end_takeover_stops_session():
    end = LLMResponse(tool_calls=[ToolCall("end_takeover", {"reason": "scammer gone"})])
    llm = FakeLLM().script("handler", end, '{"goal": "end"}')
    engine = make_engine(llm)
    sid, reply = start(engine)
    assert reply is None
    assert engine.store.sessions[sid]["status"] == "ended"
    assert "scammer gone" in engine.store.sessions[sid]["ended_reason"]


def test_extractor_drops_hallucinated_indicators():
    llm = FakeLLM().script("extractor", json.dumps({"indicators": [
        {"kind": "url", "value": "ezpass-tollpay.example/pay"},
        {"kind": "phone", "value": "(800) 555-0199"},  # not in the message
        {"kind": "wallet", "value": "ezpass"},  # wrong format
    ]}))
    engine = make_engine(llm)
    sid, _ = start(engine)
    values = [i["value"] for i in engine.store.indicators_for(sid)]
    assert values == ["ezpass-tollpay.example/pay"]
    dropped = engine.store.steps_for(sid, agent="extractor", kind="rejection")[0].content["dropped"]
    assert {d["value"] for d in dropped} == {"(800) 555-0199", "ezpass"}


def test_triage_retrieves_only_when_unsure():
    engine = make_engine()
    confident = engine.receive_message("c1", "+12145550111", DEMO_OPENER)
    assert confident["triage"]["retrieved"] is False
    unsure = engine.receive_message("c2", "+12145550112", "Your package is waiting, reschedule delivery")
    assert unsure["triage"]["retrieved"] is True
    steps = engine.store.steps_for(unsure["message_id"], agent="triage", kind="tool_call")
    assert steps and steps[0].content["tool"] == "search_similar_scams"


def test_burned_campaign_blocks_second_customer():
    engine = make_engine()
    sid, _ = start(engine)
    for t in DEMO_TURNS[:3]:
        engine.handle_scammer_message(sid, t)
    campaign = engine.store.campaigns[engine.store.sessions[sid]["campaign_id"]]
    assert campaign["status"] == "burned"
    second = engine.receive_message("cust_b", "+12145550199", SECOND_CUSTOMER_TEXT)
    assert second["status"] == "blocked"
    assert any(a["customer_ref"] == "cust_b" and a["kind"] == "blocked" for a in engine.store.customer_alerts)


def test_burn_refused_on_weak_evidence():
    engine = make_engine()
    sid, _ = start(engine)  # only a link so far, no payment method, single session
    campaign = engine.store.campaigns[engine.store.sessions[sid]["campaign_id"]]
    assert campaign["status"] == "active"
    from talon_agents.tools import AnalystToolbox
    out = AnalystToolbox(engine.sessions[sid], engine.store).run("burn_campaign", {"campaign_id": campaign["id"]})
    assert out.get("refused")


def test_two_sessions_sharing_a_wallet_merge_and_burn():
    engine = make_engine()
    wallet = "0x9f2c4a1b7e3d5f60a8b2c4d6e8f0a1b3c5d7e9f1"
    sid1, _ = start(engine, "Crypto desk: your account earned 2.1 ETH. Verify now to withdraw", "c1", "+12145550121")
    engine.handle_scammer_message(sid1, f"send the 0.05 ETH gas fee to {wallet} to release it")
    sid2, _ = start(engine, "Crypto desk: your account earned 3.4 ETH. Verify now to withdraw", "c2", "+12145550122")
    engine.handle_scammer_message(sid2, f"the unlock fee goes to {wallet}")
    c1 = engine.store.sessions[sid1]["campaign_id"]
    assert c1 == engine.store.sessions[sid2]["campaign_id"]
    assert engine.store.campaigns[c1]["status"] == "burned"
    assert len(engine.store.campaigns[c1]["session_ids"]) == 2


def test_impact_card_cites_real_indicators_and_true_numbers():
    engine = make_engine()
    sid, _ = start(engine)
    for t in DEMO_TURNS[:4]:
        engine.handle_scammer_message(sid, t)
    card = engine.stop_takeover(sid)
    ids = {i["id"] for i in engine.store.indicators}
    assert card["cited_indicator_ids"] and set(card["cited_indicator_ids"]) <= ids


def test_impact_card_with_made_up_numbers_is_replaced():
    llm = FakeLLM()
    engine = make_engine(llm)
    sid, _ = start(engine)
    llm.script("analyst", "You protected 50000 customers!")
    card = engine.stop_takeover(sid)
    assert "50000" not in card["text"]
    assert engine.store.steps_for(sid, agent="analyst", kind="rejection")


def test_turn_cap_ends_session():
    engine = TalonEngine(llm=FakeLLM(), settings=Settings(api_key=None, max_turns=3))
    sid, _ = start(engine)
    engine.handle_scammer_message(sid, "hello")
    engine.handle_scammer_message(sid, "pay now")
    assert engine.store.sessions[sid]["ended_reason"] == "turn_cap"


def test_warm_up_then_personal_info_ask_is_flagged_with_context():
    llm = FakeLLM()
    engine = make_engine(llm)
    first = engine.receive_message("cust_a", "+14695550182", "Hello")
    assert first["status"] == "delivered"
    second = engine.receive_message("cust_a", "+14695550182", "Hey buddy, its your grandma... I need your SSN.")
    assert second["status"] == "warned"
    payload = json.loads([c for c in llm.calls if c["agent"] == "triage"][-1]["messages"][-1]["content"])
    assert payload["earlier_messages_from_this_sender"] == ["Hello"]


def test_burn_policy_applies_when_the_analyst_model_waits():
    llm = FakeLLM()
    engine = make_engine(llm)
    sid, _ = start(engine)
    # The analyst model links but refuses to burn, as real Nemotron did; the evidence rule is met
    # (payment handle + 0.97 triage), so the engine burns by policy and says so in the trace.
    llm.script("analyst", LLMResponse(tool_calls=[ToolCall("link_to_campaign", {})]),
               '{"decision": "waiting", "summary": "not sure yet"}')
    engine.handle_scammer_message(sid, "pay with Cash App $TollDeskPay right now")
    campaign = engine.store.campaigns[engine.store.sessions[sid]["campaign_id"]]
    assert campaign["status"] == "burned"
    policy = [s for s in engine.store.steps_for(sid, agent="analyst", kind="output") if s.content.get("source") == "policy"]
    assert policy and policy[-1].content["decision"] == "burned"


def test_spelled_out_tripwire_code_is_rejected_and_model_never_sees_the_code():
    from talon_agents.agents.safety import run_safety
    from talon_agents.store import InMemoryStore, Tracer
    llm = FakeLLM()
    tracer = Tracer(InMemoryStore(), "s1")
    token = "TW-AB2C-DE3F-GH4J"
    spelled = run_safety(llm=llm, text="the code is T-W-A-B-two-C", tracer=tracer, allowed_tokens=[token],
                         required_tokens=[token])
    assert not spelled["passed"] and "tripwire" in spelled["violations"][0]
    exact = run_safety(llm=llm, text=f"ok the code is {token}", tracer=tracer, allowed_tokens=[token],
                       required_tokens=[token])
    assert exact["passed"]
    seen = llm.calls[-1]["messages"][-1]["content"]
    assert token not in seen and "[FICTIONAL TRIPWIRE CODE]" in seen


def test_normal_reply_after_a_scam_is_not_flagged():
    engine = make_engine()
    first = engine.receive_message("cust_a", "+14695550182", "Hey buddy, its your grandma... I need your SSN.")
    assert first["status"] == "warned"
    second = engine.receive_message("cust_a", "+14695550182", "Hey")
    assert second["status"] == "delivered"


def test_normal_conversation_goes_through_untouched():
    engine = make_engine()
    for text in ["hey are we still on for dinner sunday?", "cool, 7pm works", "see you then"]:
        assert engine.receive_message("cust_a", "+14695550100", text)["status"] == "delivered"
    assert not engine.store.sessions
