"""Deterministic outbound rules: enforced in code, not only in the prompt.

Every persona reply must pass these before the Nemotron safety model even sees it.
Outbound text is plain text only: no links, phone numbers, emails, personal-data patterns,
code or attachments, and the persona never says it's an AI or Talon.
"""

from __future__ import annotations

import re

MAX_REPLY_CHARS = 320  # two SMS segments

RULES: list[tuple[str, re.Pattern]] = [
    ("contains a link", re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:com|net|org|example|test|invalid|io|co|us|info|xyz|ly|app|site)\b", re.I)),
    ("contains an email address", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("contains a phone number", re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")),
    ("contains an SSN-like number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("contains a long number (card, account or ID)", re.compile(r"\d(?:[\s-]?\d){7,}")),
    ("contains code or markup", re.compile(r"```|<\s*/?\s*[a-z]+[^>]*>|\{\s*\"|;\s*$|\bimport\s+\w+|\bfunction\s*\(", re.I)),
    ("mentions an attachment", re.compile(r"\b(?:attached|attachment|see file|\.pdf|\.zip|\.exe|\.apk)\b", re.I)),
    ("reveals it's an AI or Talon", re.compile(
        r"\b(?:as an ai|i(?:'m| am) (?:an? )?(?:ai|bot|robot|language model|assistant)|language model|chatgpt|nemotron|talon|"
        r"artificial intelligence|this is an automated)\b", re.I)),
]


def check(text: str, allowed_tokens: list[str] | None = None, forbidden_strings: list[str] | None = None) -> list[str]:
    """Return the list of rule violations (empty means the reply passes).

    allowed_tokens: fictional tripwire tokens the handler deliberately issued; they're exempt.
    forbidden_strings: defense in depth, e.g. the real customer's name or number, which the
    engine never gives the persona but which must never appear even by accident.
    """
    violations: list[str] = []
    if not text or not text.strip():
        return ["empty reply"]
    if len(text) > MAX_REPLY_CHARS:
        violations.append(f"longer than {MAX_REPLY_CHARS} characters")
    scrubbed = text
    for token in allowed_tokens or []:
        scrubbed = scrubbed.replace(token, " ")
    for reason, pattern in RULES:
        if pattern.search(scrubbed):
            violations.append(reason)
    for s in forbidden_strings or []:
        if s and s.lower() in text.lower():
            violations.append("contains real customer data")
    return violations
