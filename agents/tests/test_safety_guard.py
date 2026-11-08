"""Llama 3.1 Nemotron Safety Guard 8B v3 as the safety model: its own template in, Talon's policy on its verdict."""

from __future__ import annotations

import json

from talon_agents.agents.safety import GUARD_CATEGORIES, guard_prompt, parse_categories, run_safety
from talon_agents.cli import DEMO_OPENER
from talon_agents.config import Settings
from talon_agents.engine import TalonEngine
from talon_agents.llm import FakeLLM
from talon_agents.store import InMemoryStore, Tracer

GUARD = "nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3"
SCAM = "Pay the $6.85 toll today at ezpass-tollpay.example/pay or you will be arrested"
REPLY = "oh dear, ok. which card do i use for that?"


def verdict(**fields) -> str:
    return json.dumps(fields)


def check(llm: FakeLLM, text: str = REPLY, context: str | None = SCAM, tokens: list[str] | None = None) -> dict:
    return run_safety(llm=llm, text=text, tracer=Tracer(InMemoryStore(), "s1"), allowed_tokens=tokens or [],
                      guard=True, context=context)


def guard_calls(llm: FakeLLM) -> list[str]:
    return [c["messages"][-1]["content"] for c in llm.calls if c["agent"] == "safety"]


def test_prompt_matches_the_model_card_template():
    p = guard_prompt("Q", "R")
    assert p.startswith("Task: Check if there is unsafe content in the user or agent messages in the below "
                        "conversation in accordance with our safety policy with the below categories.")
    assert "<BEGIN UNSAFE CONTENT CATEGORIES>\nS1: Violence. \nS2: Sexual. \n" in p
    assert "S23: Immoral/Unethical. \n<END UNSAFE CONTENT CATEGORIES>\n\n<BEGIN CONVERSATION>\n\n" in p
    assert "user: Q\n\nresponse: agent: R\n\n<END CONVERSATION>\n\n" in p
    assert p.endswith('Omit if all safe.}\n\nDo not include anything other than the output JSON in your response.'
                      '\nOutput JSON: ')
    assert "user: Q\n\n<END CONVERSATION>" in guard_prompt("Q")  # no response block when there's no reply
    assert len(GUARD_CATEGORIES) == 23


def test_category_names_and_codes_are_normalized():
    assert parse_categories("S11: Threat, Fraud/Deception, S9") == ["Threat", "Fraud/Deception", "PII/Privacy"]
    assert parse_categories("violence;  pii/privacy.") == ["Violence", "PII/Privacy"]
    assert parse_categories(None) == []


def test_safe_reply_passes_and_the_scammers_message_is_rated_too():
    llm = FakeLLM().script("safety", verdict(**{"User Safety": "unsafe", "Response Safety": "safe",
                                                "Safety Categories": "Fraud/Deception, Threat"}))
    out = check(llm)
    assert out["passed"] and out["source"] == "rules+guard"
    assert out["scammer_message"] == "unsafe" and out["scammer_categories"] == ["Fraud/Deception", "Threat"]
    assert "Nemotron Safety Guard" in out["summary"] and "scammer's message unsafe" in out["summary"]
    # The guard got the official template, with the scammer as user and Talon's draft as the agent response.
    sent = guard_calls(llm)[0]
    assert f"user: {SCAM}\n\nresponse: agent: {REPLY}\n" in sent
    assert llm.calls[-1]["messages"][0]["role"] == "user" and len(llm.calls[-1]["messages"]) == 1


def test_deception_is_expected_for_a_decoy_and_does_not_block():
    llm = FakeLLM().script("safety", verdict(**{"User Safety": "safe", "Response Safety": "unsafe",
                                                "Safety Categories": "Fraud/Deception, Manipulation"}))
    out = check(llm, context="hi, is this Sam?")
    assert out["passed"] and "expected for a decoy" in out["note"]


def test_harmful_reply_is_blocked_with_the_guards_category():
    llm = FakeLLM().script("safety", verdict(**{"User Safety": "safe", "Response Safety": "unsafe",
                                                "Safety Categories": "S11: Threat"}))
    out = check(llm, context="hi, is this Sam?")
    assert not out["passed"] and out["source"] == "guard" and out["violations"] == ["safety guard: Threat"]


def test_shared_category_list_is_resolved_by_asking_about_the_reply_alone():
    # Both flagged: "Threat" could be the scammer's ("or you will be arrested"). Ask about the reply on its own.
    llm = FakeLLM().script(
        "safety",
        verdict(**{"User Safety": "unsafe", "Response Safety": "unsafe", "Safety Categories": "Threat, Fraud/Deception"}),
        verdict(**{"User Safety": "unsafe", "Safety Categories": "Fraud/Deception"}),
    )
    out = check(llm)
    calls = guard_calls(llm)
    assert len(calls) == 2 and "response: agent:" not in calls[1] and f"user: {REPLY}" in calls[1]
    assert out["passed"] and out["reply_categories"] == ["Fraud/Deception"]


def test_reply_alone_with_a_real_harm_is_blocked():
    llm = FakeLLM().script(
        "safety",
        verdict(**{"User Safety": "unsafe", "Response Safety": "unsafe", "Safety Categories": "Fraud/Deception"}),
        verdict(**{"User Safety": "unsafe", "Safety Categories": "PII/Privacy"}),
    )
    out = check(llm)
    assert not out["passed"] and out["violations"] == ["safety guard: PII/Privacy"]


def test_reply_flagged_only_alongside_the_scam_passes():
    llm = FakeLLM().script(
        "safety",
        verdict(**{"User Safety": "unsafe", "Response Safety": "unsafe", "Safety Categories": "Threat"}),
        verdict(**{"User Safety": "safe"}),
    )
    out = check(llm)
    assert out["passed"] and "only alongside" in out["note"]


def test_unknown_or_missing_verdicts_fail_closed():
    assert not check(FakeLLM().script("safety", "I think it's fine"))["passed"]
    assert not check(FakeLLM().script("safety", verdict(**{"User Safety": "safe"})))["passed"]  # no reply rating
    unexplained = FakeLLM().script("safety", verdict(**{"User Safety": "safe", "Response Safety": "unsafe"}))
    assert not check(unexplained, context="hi")["passed"]
    novel = FakeLLM().script("safety", verdict(**{"User Safety": "safe", "Response Safety": "unsafe",
                                                  "Safety Categories": "Something New"}))
    assert check(novel, context="hi")["violations"] == ["safety guard: Something New"]


def test_tripwire_codes_are_masked_before_the_guard_sees_them():
    token = "TW-AB2C-DE3F-GH4J"
    llm = FakeLLM()
    out = check(llm, text=f"ok the code is {token}", tokens=[token])
    assert out["passed"]
    sent = guard_calls(llm)[0]
    assert token not in sent and "[FICTIONAL TRIPWIRE CODE]" in sent


def test_unreachable_guard_falls_back_to_the_nano_reviewer():
    def down(messages, tools):
        raise ConnectionError("guard on :8001 refused the connection")

    llm = FakeLLM(responders={"safety": down})
    out = check(llm)
    assert out["passed"] and out["source"] == "rules+model (guard unavailable)"
    assert [c["agent"] for c in llm.calls] == ["safety", "safety_review"]


def test_settings_detect_a_guard_model():
    assert Settings(models={"default": "nvidia/nvidia-nemotron-nano-9b-v2", "safety": GUARD}).safety_uses_guard
    assert not Settings(models={"default": "nvidia/nvidia-nemotron-nano-9b-v2"}).safety_uses_guard


def test_engine_uses_the_guard_on_every_reply_when_configured():
    settings = Settings(api_key=None, models={"default": "nvidia/nvidia-nemotron-nano-9b-v2", "safety": GUARD})
    llm = FakeLLM()
    engine = TalonEngine(llm=llm, settings=settings)
    warning = engine.receive_message("cust_a", "+12145550137", DEMO_OPENER)
    session, reply = engine.request_takeover(warning["message_id"])
    assert reply
    passed = engine.store.steps_for(session["id"], agent="safety", kind="output")
    assert passed and passed[-1].content["source"] == "rules+guard"
    # The guard saw the scammer's message as the user turn and Talon's draft as the agent response.
    sent = guard_calls(llm)[0]
    assert "<BEGIN CONVERSATION>" in sent and f"user: {DEMO_OPENER}" in sent and "response: agent: " in sent


def test_endpoint_check_reports_guard_verdicts_and_fails_on_an_unreadable_one():
    from talon_agents.check import GUARD_CASES, _check_guard

    assert _check_guard(FakeLLM(), GUARD) == 0  # a disagreement is a warning, not a failure
    broken = FakeLLM().script("safety", *["sure, looks fine to me"] * len(GUARD_CASES))
    assert _check_guard(broken, GUARD) == len(GUARD_CASES)
