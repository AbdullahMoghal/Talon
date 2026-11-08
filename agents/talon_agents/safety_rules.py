"""Deterministic outbound rules: enforced in code, not only in the prompt.

Every persona reply must pass these before the Nemotron safety model even sees it.
Outbound text is plain text only: no links, phone numbers, emails, personal-data patterns,
code or attachments, no offers of a call or meeting (Talon is text-only), and the persona never
says it's an AI or Talon.
"""

from __future__ import annotations

import re

MAX_REPLY_CHARS = 320  # two SMS segments
MAX_SENTENCES = 3

RULES: list[tuple[str, re.Pattern]] = [
    ("contains a link", re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:com|net|org|example|test|invalid|io|co|us|info|xyz|ly|app|site)\b", re.I)),
    ("contains an email address", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("contains a phone number", re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")),
    ("contains an SSN-like number", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    # The Nemotron safety guard passes a speaker sharing their own address (seen in a live check), so this is
    # enforced here: the persona never gives a street address, even a made-up one.
    ("gives a street address", re.compile(
        r"\b\d{1,6}\s+(?:[a-z]+\s+){1,3}(?:street|st|avenue|ave|road|rd|lane|ln|drive|dr|boulevard|blvd|court|ct|"
        r"way|place|pl|terrace|circle|cir|parkway|pkwy|highway|hwy)\b", re.I)),
    ("contains a long number (card, account or ID)", re.compile(r"\d(?:[\s-]?\d){7,}")),
    ("contains code or markup", re.compile(r"```|<\s*/?\s*[a-z]+[^>]*>|\{\s*\"|;\s*$|\bimport\s+\w+|\bfunction\s*\(", re.I)),
    ("mentions an attachment", re.compile(r"\b(?:attached|attachment|see file|\.pdf|\.zip|\.exe|\.apk)\b", re.I)),
    ("reveals it's an AI or Talon", re.compile(
        r"\b(?:as an ai|i(?:'m| am) (?:an? )?(?:ai|bot|robot|language model|assistant)|language model|chatgpt|nemotron|talon|"
        r"artificial intelligence|this is an automated)\b", re.I)),
    # The persona is a believer. Sounding suspicious ends the conversation and wastes the takeover.
    ("breaks character (sounds suspicious)", re.compile(
        r"\b(?:scam\w*|fake|fraud\w*|pretend\w*|trick\w*|tripwire|handler|made[- ]up|phishing|suspicious|"
        r"sketchy|shady|dodgy|fishy|bogus|sus)\b", re.I)),
    ("uses formatting", re.compile(r"\*\w|\w\*|^\s*[-•]\s|^\s*#{1,6}\s|^\s*\d+[.)]\s", re.M)),
    # Tells that give away an AI agent (see test_humanlike.py). A real person texting doesn't write these.
    ("uses an em dash", re.compile("[\u2014\u2013]")),
    ("writes in more than one paragraph", re.compile(r"\n")),
    ("sounds like an AI assistant", re.compile(
        r"^\s*(?:certainly|absolutely|of course)[!,.]|\bi'?d be (?:more than )?(?:happy|glad|delighted) to\b|"
        r"\bgreat question\b|\bi understand your (?:concern|frustration)\b|\bapologi[sz]e for (?:the|any) "
        r"(?:confusion|inconvenience|misunderstanding)\b|\bhow (?:can|may) i (?:help|assist)\b|"
        r"\bis there anything else\b|\bfeel free to\b|\bhope this helps\b|\bi hope that helps\b|"
        r"\byou(?:'re| are) (?:absolutely|completely) right\b", re.I | re.M)),
    ("uses essay transitions", re.compile(
        r"\b(?:in conclusion|furthermore|moreover|additionally|it is (?:important|worth) (?:to note|noting|"
        r"to remember)|in summary|that being said)\b", re.I)),
    ("mentions tools, systems or looking things up", re.compile(
        r"\b(?:let me|i'?ll|i will|i'?m going to) (?:check|search|look up|query|pull up|scan) (?:the|my|our) "
        r"(?:system|database|records|server|logs|knowledge)\b|\b(?:searching|querying|checking) (?:the )?"
        r"(?:database|web|internet|browser|system)\b|\btool call\b|\bmy (?:database|knowledge base|training "
        r"data|programming|instructions)\b", re.I)),
    ("refuses like a policy bot", re.compile(
        r"\bi (?:can ?not|can'?t|am unable to|'?m unable to) (?:fulfill|comply with|assist with|help with) "
        r"(?:this|that|your) request\b|\bi(?:'m| am) (?:not able|programmed|designed|not permitted) to\b|"
        r"\bagainst my (?:guidelines|policy|policies|programming)\b", re.I)),
    ("says it has no body or life", re.compile(
        r"\bi (?:don'?t|do not) have (?:a (?:physical )?body|personal (?:experiences|memories|opinions|feelings|"
        r"preferences)|feelings|emotions)\b|\bi(?:'m| am) not (?:a real person|human|a person)\b", re.I)),
    ("hedges instead of picking a side", re.compile(
        r"\b(?:it'?s|that'?s|it is|that is) (?:really |all |just )?(?:a matter of|up to) (?:personal )?"
        r"(?:preference|taste|opinion)\b|\bsome people (?:love|like|prefer|enjoy)\b.{0,60}\bwhile others\b|"
        r"\bthere(?:'s| is) no right (?:or wrong )?answer\b", re.I)),
    # Talon is text-only: it can't take over a call, so it must never steer the scammer toward one.
    ("offers a phone call or meeting", re.compile(
        r"\b(?:call|ring|phone)\s+(?:you|me|u|them|that number|this number|the number|your number|back|"
        r"the office|your office|the billing office)\b|\b(?:phone|video|voice)\s?call\b|\bface ?time\b|"
        r"\bgive (?:me|you) a (?:call|ring)\b|\b(?:talk|speak) (?:on|over) the phone\b|\bmeet (?:up|in person|you)\b|"
        r"\bnumber (?:i|to) (?:can )?call\b", re.I)),
]


# Payment methods, each with the ways people write it. A reply may only name one the scammer already brought up.
PAYMENT_METHODS: dict[str, re.Pattern] = {
    "gift card": re.compile(r"\bgift\s?cards?\b|\b(?:itunes|google play|steam)\s+cards?\b", re.I),
    "Cash App": re.compile(r"\bcash\s?app\b|\bcashapp\b", re.I),
    "Zelle": re.compile(r"\bzelle\b", re.I),
    "Venmo": re.compile(r"\bvenmo\b", re.I),
    "PayPal": re.compile(r"\bpay\s?pal\b", re.I),
    "crypto": re.compile(r"\b(?:bitcoin|btc|crypto\w*|ethereum|eth|usdt|tether|coinbase)\b", re.I),
    "wire or bank transfer": re.compile(r"\bwire(?:d|\s+transfer)?\b|\bbank\s+transfer\b|\bach\b|\bwestern union\b|"
                                        r"\bmoneygram\b", re.I),
}


def leading_payment(text: str, scammer_history: str) -> list[str]:
    """Payment methods the reply names that the scammer hasn't mentioned. A real victim doesn't suggest how to
    pay, and offering a method (seen on live Nano: "can you try gift card instead?") can tip the scammer off."""
    return [f"names a payment method the scammer hasn't mentioned ({name}); ask how they want to be paid instead"
            for name, pattern in PAYMENT_METHODS.items()
            if pattern.search(text) and not pattern.search(scammer_history)]


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
    # A casual text is a sentence or two. A run of sentences reads like an AI data dump.
    if len(re.findall(r"[.!?]+(?:\s|$)", text.strip())) > MAX_SENTENCES:
        violations.append(f"more than {MAX_SENTENCES} sentences; a text should be one or two")
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
