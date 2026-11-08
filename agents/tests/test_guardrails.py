"""Guardrails for problems seen in the first live demo on real Nemotron (talon-prod, room HACK).

1. The extractor labeled a Zelle email as a url and wrote "Zelle"/"Cash App" as payment handles.
   Validation dropped them, and the real email and $handle were lost. Code now recovers them.
2. The persona offered to "call that number you gave". Talon is text-only, so the safety rules
   reject any offer of a call or meeting, and the persona is sent back to rewrite.
"""

from __future__ import annotations

import json

import pytest

from talon_agents.agents.extractor import run_extractor
from talon_agents.config import Settings
from talon_agents.engine import TalonEngine
from talon_agents.llm import FakeLLM
from talon_agents.safety_rules import check
from talon_agents.store import InMemoryStore, Tracer
from talon_agents.taxonomy import load_taxonomy

ZELLE_TURN = "No problem ma'am. You can pay by Zelle to tollpay.desk@ntta-billing.example or Cash App $TollDeskPay"

# What the real model returned for ZELLE_TURN in the demo.
MISLABELED = json.dumps({"indicators": [
    {"kind": "payment_handle", "value": "Zelle", "confidence": 0.9},
    {"kind": "payment_handle", "value": "Cash App", "confidence": 0.9},
    {"kind": "url", "value": "tollpay.desk@ntta-billing.example", "confidence": 0.9},
]})


def run(llm: FakeLLM, text: str) -> tuple[list[dict], InMemoryStore]:
    store = InMemoryStore()
    tracer = Tracer(store, "s1")
    found = run_extractor(llm=llm, text=text, taxonomy=load_taxonomy(), store=store, tracer=tracer,
                          session_id="s1", turn_id="t1", category="toll_fee")
    return found, store


def test_extractor_recovers_mislabeled_payment_details():
    found, store = run(FakeLLM().script("extractor", MISLABELED), ZELLE_TURN)
    got = {(i["kind"], i["value"]) for i in found}
    assert ("email", "tollpay.desk@ntta-billing.example") in got
    assert ("payment_handle", "$TollDeskPay") in got
    # The wrong labels are still dropped, never stored.
    assert not any(v in ("Zelle", "Cash App") for _, v in got)
    assert not any(k == "url" and "@" in v for k, v in got)
    output = store.steps_for("s1", agent="extractor", kind="output")[-1].content
    assert {r["value"] for r in output["recovered_by_code"]} == {"tollpay.desk@ntta-billing.example", "$TollDeskPay"}


def test_extractor_recovers_what_the_model_missed_entirely():
    text = "Send it to bc1qar0srrr7xfkvy5l643lydnw9re59gtzzwf5mdq or text me at (469) 555-0182"
    found, _ = run(FakeLLM().script("extractor", '{"indicators": []}'), text)
    kinds = {i["kind"] for i in found}
    assert {"wallet", "phone"} <= kinds


def test_extractor_recovery_does_not_invent_or_duplicate():
    found, _ = run(FakeLLM().script("extractor", '{"indicators": []}'), "ok thanks ma'am, I'll wait for your text")
    assert found == []
    model_found = json.dumps({"indicators": [{"kind": "url", "value": "ntta-tollpay.example/tx", "confidence": 0.9}]})
    found, _ = run(FakeLLM().script("extractor", model_found), "Pay at ntta-tollpay.example/tx today")
    assert [(i["kind"], i["value"]) for i in found] == [("url", "ntta-tollpay.example/tx")]


CALL_OFFERS = [
    "Hmm, I can't access my payment app right now. Could you email me simple steps, or call that number you gave?",
    "can I just call you instead",
    "give me a call later dear",
    "maybe we could do a video call so you can show me",
    "is there a number I can call?",
    "I'd rather talk on the phone, I'm slow at typing",
]

FINE = [
    "I can only text right now, my phone is acting up",
    "what do you call that thing on the back of the card?",
    "my grandson calls me every sunday, he does computers",
    "is there another number I can text you at, or an email?",
]


@pytest.mark.parametrize("text", CALL_OFFERS)
def test_rules_reject_call_offers(text):
    assert "offers a phone call or meeting" in check(text)


@pytest.mark.parametrize("text", FINE)
def test_rules_allow_text_only_replies(text):
    assert "offers a phone call or meeting" not in check(text)


def test_engine_rewrites_a_call_offer_before_sending():
    llm = FakeLLM().script("persona", CALL_OFFERS[0], "oh dear, is there another number I can text you at instead?")
    engine = TalonEngine(llm=llm, settings=Settings(api_key=None))
    msg = engine.receive_message("cust_x", "+14695550144", "NTTA: unpaid toll $6.85. Pay now: ntta-tollpay.example/tx")
    session, reply = engine.request_takeover(msg["message_id"])
    assert reply == "oh dear, is there another number I can text you at instead?"
    rejections = engine.store.steps_for(session["id"], agent="safety", kind="rejection")
    assert any("offers a phone call or meeting" in r.content["violations"] for r in rejections)
