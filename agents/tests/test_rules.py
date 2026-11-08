"""Deterministic guardrails: outbound safety rules and indicator validation."""

from __future__ import annotations

import pytest

from talon_agents import safety_rules
from talon_agents.indicators import regex_extract, validate
from talon_agents.llm import parse_json

KINDS = ["url", "phone", "email", "wallet", "payment_handle", "account", "giftcard_ask", "remote_access_id", "brand"]


@pytest.mark.parametrize("text,reason", [
    ("go to www.refund.com", "contains a link"),
    ("try https://pay.example/now", "contains a link"),
    ("call me at (214) 555-0147", "contains a phone number"),
    ("my email is marj@mail.example", "contains an email address"),
    ("my ssn is 123-45-6789", "contains an SSN-like number"),
    ("card is 4111 1111 1111 1111", "contains a long number (card, account or ID)"),
    ("As an AI I can't do that", "reveals it's an AI or Talon"),
    ("this is Talon speaking", "reveals it's an AI or Talon"),
    ("```print('hi')```", "contains code or markup"),
    ("I attached the receipt", "mentions an attachment"),
])
def test_rules_reject(text, reason):
    assert reason in safety_rules.check(text)


@pytest.mark.parametrize("text", [
    "oh dear, which company did you say you're with?",
    "my card got declined, is there another way to pay?",
    "I'm 72, I'm not good with these phones",
])
def test_rules_pass_normal_replies(text):
    assert safety_rules.check(text) == []


def test_tripwire_token_is_allowed_only_when_issued():
    text = "the code on the back is TW-AB2C-DE3F-GH4J"
    assert safety_rules.check(text, allowed_tokens=["TW-AB2C-DE3F-GH4J"]) == []


def test_forbidden_customer_data():
    assert "contains real customer data" in safety_rules.check("hi I'm Jane Doe", forbidden_strings=["Jane Doe"])


def test_too_long():
    assert any("longer than" in v for v in safety_rules.check("a" * 400))


def test_regex_extract_finds_all_kinds():
    text = ("Pay at toll-pay.example/x or call 1-888-555-0142, email help@desk.example, Cash App $TollDesk, "
            "wallet 0x9f2c4a1b7e3d5f60a8b2c4d6e8f0a1b3c5d7e9f1. Or buy two Google Play gift cards.")
    kinds = {i["kind"] for i in regex_extract(text)}
    assert {"url", "phone", "email", "payment_handle", "wallet", "giftcard_ask"} <= kinds
    assert not any(i["kind"] == "url" and "desk.example" in i["value"] for i in regex_extract(text))


def test_validate():
    text = "call 1-888-555-0142 now"
    assert validate("phone", "1-888-555-0142", text, KINDS) is None
    assert validate("phone", "1-888-555-0199", text, KINDS) == "value does not appear in the message"
    assert validate("wallet", "call", text, KINDS) == "value is not a valid wallet"
    assert validate("nonsense", "x", text, KINDS).startswith("unknown")


def test_parse_json_handles_wrapping():
    assert parse_json('<think>hmm</think>Sure: ```json\n{"a": {"b": 1}}\n```') == {"a": {"b": 1}}
    with pytest.raises(ValueError):
        parse_json("no json here")


def test_think_switch_merges_into_system_prompt():
    from talon_agents.llm import with_think_switch
    msgs = [{"role": "system", "content": "You are the handler."}, {"role": "user", "content": "hi"}]
    out = with_think_switch("nvidia/nvidia-nemotron-nano-9b-v2", msgs, reasoning=True)
    assert [m["role"] for m in out] == ["system", "user"]
    assert out[0]["content"] == "/think\nYou are the handler."
    assert with_think_switch("nvidia/llama-3.1-nemotron-safety-guard-8b-v3", msgs, False) == msgs


def test_brev_settings_from_env(monkeypatch):
    from talon_agents.config import Settings
    for k in ("NVIDIA_API_KEY", "TALON_FAKE_LLM"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("NEMOTRON_API_KEY", "brev-secret")
    monkeypatch.setenv("NEMOTRON_BASE_URL", "http://localhost:8000/v1")
    monkeypatch.setenv("SAFETY_BASE_URL", "http://localhost:8001/v1")
    s = Settings.from_env()
    assert s.api_key == "brev-secret" and not s.use_fake
    assert s.base_url_for("handler") == "http://localhost:8000/v1"
    assert s.base_url_for("safety") == "http://localhost:8001/v1"


def test_gold_eval_metrics():
    from talon_agents.eval_gold import baseline, detection
    m = detection([True, True, False, False], [True, False, True, False])
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (1, 1, 1, 1)
    assert m["precision"] == 0.5 and m["false_alarm_rate"] == 0.5
    assert baseline("URGENT: pay the fee now at toll.example") is True
    assert baseline("see you at dinner") is False


@pytest.mark.parametrize("text", [
    "What's the real company you're pretending to be?",
    "Hmm, that link won't open, maybe it's a trick?",
    "Or is that the tripwire he mentioned?",
    "TollDeskPay sounds like a made-up name",
    "my grandson said *Oklahoma Toll Roads* or something",
])
def test_rules_reject_breaking_character(text):
    assert safety_rules.check(text)


def test_handler_reasons_only_on_first_step():
    from talon_agents.engine import TalonEngine
    from talon_agents.llm import FakeLLM
    from talon_agents.config import Settings
    from talon_agents.cli import DEMO_OPENER
    llm = FakeLLM()
    engine = TalonEngine(llm=llm, settings=Settings(api_key=None))
    w = engine.receive_message("c", "+12145550137", DEMO_OPENER)
    engine.request_takeover(w["message_id"])
    flags = [c["reasoning"] for c in llm.calls if c["agent"] == "handler"]
    assert flags[0] is True and not any(flags[1:])


def test_spacetime_sql_decoding():
    from talon_agents.spacetime import _decode
    opt_str = {"Sum": {"variants": [{"name": {"some": "some"}, "algebraic_type": {"String": []}},
                                    {"name": {"some": "none"}, "algebraic_type": {"Product": {"elements": []}}}]}}
    assert _decode([0, "toll_fee"], opt_str) == "toll_fee"
    assert _decode([1, []], opt_str) is None
    ts = {"Product": {"elements": [{"name": {"some": "__timestamp_micros_since_unix_epoch__"},
                                    "algebraic_type": {"I64": []}}]}}
    assert _decode([1794107492715243], ts) == 1794107492715243


def test_mirror_maps_engine_writes_to_reducers():
    from talon_agents.cli import DEMO_OPENER
    from talon_agents.config import Settings
    from talon_agents.engine import TalonEngine
    from talon_agents.llm import FakeLLM
    from talon_agents.mirror import SpacetimeMirror

    class Recorder:
        def __init__(self):
            self.calls = []

        def call(self, reducer, *args):
            self.calls.append((reducer, args))

    engine = TalonEngine(llm=FakeLLM(), settings=Settings(api_key=None))
    rec = Recorder()
    mirror = SpacetimeMirror(rec, engine.store)
    w = engine.receive_message("cust_demo_a", "+14695550182", DEMO_OPENER)
    engine.request_takeover(w["message_id"], session_id="ses_phone", origin="phone")
    mirror.flush()
    names = [c[0] for c in rec.calls]
    assert names[:2] == ["receive_message", "add_agent_step"]
    assert "set_triage" in names and "add_turn" in names and "add_handler_plan" in names
    assert "request_takeover" not in names  # the phone already created the session
    assert all(c[1][1] == "ses_phone" for c in rec.calls if c[0] == "add_turn")
    assert not mirror.errors
