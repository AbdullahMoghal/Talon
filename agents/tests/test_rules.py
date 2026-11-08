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
