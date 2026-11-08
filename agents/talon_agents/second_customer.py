"""The second customer: the same scam campaign reaching someone else, played automatically in the live demo.

Nobody plays the scammer for the second phone, so the live runner does, in two beats:
  1. As soon as the first customer's scam is identified, the scammer agent rewords it and it lands on the
     second customer's phone from a different number. Triage has to catch it on its own, and when the
     campaign burns, Talon warns this customer too (the reworded text keeps the campaign's link).
  2. Once the campaign is burned and someone has the second phone open, the scammer follows up from that
     same new number, reusing the payment handle (or link) Talon extracted in the takeover. Talon blocks it
     on arrival and says why. Waiting for a viewer means the block happens on screen, not unseen.
"""

from __future__ import annotations

from .indicators import regex_extract
from .llm import LLM
from .store import normalize_value

MAX_TEXT = 480  # scammer_send's limit in the module

SYSTEM = """You write test messages for a scam-detection demo. Rewrite the scam text below the way the same
scammer would send it to a different person: same scam type and same brand, different wording.
Keep every link, phone number, email address and payment handle exactly as written, character for character.
Plain text, one message, under 200 characters. Reply with the message only."""

# What a scammer can't easily change after rotating numbers: where the victim pays or clicks. Checked in this order.
REUSE_PRIORITY = ("wallet", "payment_handle", "account", "url", "email", "phone")


def reword(llm: LLM, text: str) -> tuple[str, str]:
    """The opener, reworded for a second victim. Returns (text, "model" | "fallback").

    The model's draft is only used if it kept every link, number and handle from the original, so the
    campaign stays linkable; otherwise a plain "second notice" of the original goes out.
    """
    must_keep = [i["value"] for i in regex_extract(text) if i["kind"] != "brand"]
    try:
        resp = llm.chat(agent="scammer", messages=[{"role": "system", "content": SYSTEM},
                                                   {"role": "user", "content": text}],
                        max_tokens=200, temperature=0.9)
        draft = " ".join((resp.content or "").split()).strip("\"'")
    except Exception:  # noqa: BLE001 - the demo must still send something
        draft = ""
    norm = normalize_value(draft)
    if (draft and len(draft) <= MAX_TEXT and norm != normalize_value(text)
            and all(normalize_value(v) in norm for v in must_keep)):
        return draft, "model"
    fallback = f"Second notice: {text}"
    return (fallback if len(fallback) <= MAX_TEXT else text), "fallback"


def pick_reused(intel: list[dict]) -> dict | None:
    """The extracted indicator the scammer's follow-up reuses: cash-out first, then contact points."""
    for kind in REUSE_PRIORITY:
        for ind in intel:
            if ind["kind"] == kind and len(normalize_value(ind["value"])) >= 6:
                return ind
    return None


def followup(kind: str, value: str) -> str:
    """The same scammer's next text: new wording, same cash-out. Talon should block it on arrival."""
    if kind == "wallet":
        return f"Final notice: your funds are on hold. Send the release fee to {value} today to unlock them"
    if kind == "payment_handle":
        return f"Final notice: your balance is overdue. Send the payment to {value} today to avoid a late fee"
    if kind == "account":
        return f"Final notice: your balance is overdue. Transfer the payment to account {value} today to avoid a late fee"
    if kind == "url":
        return f"Final notice: your account is on hold. Verify today at {value} to avoid suspension"
    if kind == "email":
        return f"Final notice: your account is on hold. Email {value} today to avoid suspension"
    return f"Final notice: your account is on hold. Text {value} today to avoid suspension"
