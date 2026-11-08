"""Talon must not read like an AI agent.

Covers the common ways people spot a bot in a chat: assistant phrasing, em dashes, formatting and
paragraphs, data dumps, essay transitions, tool talk, policy refusals, "I don't have a body",
hedging on taste questions, formal apologies, and instant replies. Tells that code can't detect
(sarcasm, idioms, anecdotes, fatigue, timeline) are covered by the persona prompt.
"""

from __future__ import annotations

import json

import pytest

from talon_agents.agents.triage import run_triage
from talon_agents.config import Settings
from talon_agents.engine import TalonEngine
from talon_agents.llm import FakeLLM
from talon_agents.retrieval import ScamRetriever
from talon_agents.safety_rules import check
from talon_agents.store import InMemoryStore, Tracer
from talon_agents.taxonomy import load_taxonomy
from talon_agents.text_style import no_dashes, typing_seconds

SCAM = "NTTA: unpaid toll $6.85. Pay now: ntta-tollpay.example/tx"


# ---- em dashes ----------------------------------------------------------------

@pytest.mark.parametrize("raw,clean", [
    ("Oh, that link’s broken again—can you tell me what to do?",
     "Oh, that link’s broken again, can you tell me what to do?"),
    ("Sure — who should I pay?", "Sure, who should I pay?"),
    ("it was 10–20 dollars", "it was 10-20 dollars"),
    ("wait -- what?", "wait, what?"),
    ("ok—", "ok"),
    ("no dashes here", "no dashes here"),
])
def test_no_dashes(raw, clean):
    assert no_dashes(raw) == clean


def test_persona_reply_never_has_an_em_dash():
    llm = FakeLLM().script("persona", "sure—where do I send it?")
    engine = TalonEngine(llm=llm, settings=Settings(api_key=None))
    msg = engine.receive_message("cust_x", "+14695550144", SCAM)
    _, reply = engine.request_takeover(msg["message_id"])
    assert reply == "sure, where do I send it?"


def test_triage_reason_never_has_an_em_dash():
    llm = FakeLLM().script("triage", json.dumps(
        {"scam_probability": 0.95, "category": "toll_fee", "reason": "Fake toll notice—real tolls never text links."}))
    taxonomy = load_taxonomy()
    out = run_triage(llm=llm, text=SCAM, taxonomy=taxonomy, retriever=ScamRetriever(taxonomy),
                     tracer=Tracer(InMemoryStore(), "m1"), settings=Settings(api_key=None))
    assert "—" not in out["reason"] and out["reason"].startswith("Fake toll notice, real tolls")


# ---- AI tells the safety rules reject ----------------------------------------------

AI_TELLS = {
    "sounds like an AI assistant": [
        "Certainly! Where should I send the payment?",
        "I'd be happy to help you with that payment.",
        "Great question, I think it was the blue card.",
        "I understand your concern about the late fee.",
        "I apologize for the confusion, it was Tuesday.",
        "You're absolutely right, I made a mistake there.",
        "Is there anything else you need from me?",
    ],
    "uses essay transitions": [
        "Furthermore, my card was declined.",
        "It is important to note that the link did not open.",
        "In conclusion I will pay tomorrow.",
    ],
    "mentions tools, systems or looking things up": [
        "Let me check the database for that order.",
        "I'm searching the web for the toll site now.",
        "That's not in my training data.",
    ],
    "refuses like a policy bot": [
        "I can't fulfill that request right now.",
        "I'm not able to share that information.",
        "That's against my guidelines.",
    ],
    "says it has no body or life": [
        "I don't have personal experiences like that.",
        "I don't have a physical body so I can't go to the store.",
        "I'm not a real person.",
    ],
    "hedges instead of picking a side": [
        "That's a matter of personal preference!",
        "Some people love ketchup on hot dogs, while others hate it.",
        "There's no right or wrong answer to that.",
    ],
    "uses an em dash": ["ok—what do I do next"],
    "writes in more than one paragraph": ["ok I tried it.\nIt didn't work."],
    "uses formatting": ["### Steps", "1. open the app", "- the blue card"],
}


@pytest.mark.parametrize("reason,text", [(r, t) for r, ts in AI_TELLS.items() for t in ts])
def test_rejects_ai_tells(reason, text):
    assert any(reason in v for v in check(text)), check(text)


def test_rejects_a_data_dump():
    text = "I tried the link. It said error. Then I tried again. Then my card got declined. What now?"
    assert any("sentences" in v for v in check(text))


HUMAN = [
    "ok where do I send it",
    "lol why are you asking me how many r's are in strawberry",
    "ketchup on a hot dog is a crime, I said what I said",
    "huh, I thought it was Tuesday",
    "my card got declined again, is there another way to pay?",
    "of all the days for my phone to act up",
    "I absolutely hate when that happens",
    "I tried it twice. still nothing.",
    "let me check my purse for the other card",
    "oh ok, thats fine",
]


@pytest.mark.parametrize("text", HUMAN)
def test_allows_casual_human_texts(text):
    assert check(text) == [], check(text)


def test_engine_rewrites_an_assistant_sounding_reply():
    llm = FakeLLM().script("persona", "Certainly! I'd be happy to help with that payment.", "ok where do I pay it")
    engine = TalonEngine(llm=llm, settings=Settings(api_key=None))
    msg = engine.receive_message("cust_x", "+14695550144", SCAM)
    session, reply = engine.request_takeover(msg["message_id"])
    assert reply == "ok where do I pay it"
    rejections = engine.store.steps_for(session["id"], agent="safety", kind="rejection")
    assert any("sounds like an AI assistant" in r.content["violations"] for r in rejections)


# ---- typing pause -----------------------------------------------------------------

def test_typing_pause_scales_with_length():
    assert typing_seconds("ok") < typing_seconds("my card got declined again, is there another way to pay?")
    assert typing_seconds("x" * 1000) == 12.0


def test_live_replies_wait_like_a_person_typing(monkeypatch):
    slept = []
    monkeypatch.setattr("talon_agents.engine.time.sleep", lambda s: slept.append(s))
    settings = Settings(api_key=None, typing_delay=True)
    engine = TalonEngine(llm=FakeLLM().script("persona", "ok where do I send it"), settings=settings)
    msg = engine.receive_message("cust_x", "+14695550144", SCAM)
    _, reply = engine.request_takeover(msg["message_id"])
    assert reply and slept and 0 < slept[-1] <= typing_seconds(reply)


def test_no_typing_pause_by_default(monkeypatch):
    slept = []
    monkeypatch.setattr("talon_agents.engine.time.sleep", lambda s: slept.append(s))
    engine = TalonEngine(llm=FakeLLM(), settings=Settings(api_key=None))
    msg = engine.receive_message("cust_x", "+14695550144", SCAM)
    engine.request_takeover(msg["message_id"])
    assert slept == []
