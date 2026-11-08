"""Plain, human text for anything a person reads: persona replies, alerts, impact cards, insights.

Models love em dashes, and an em dash in a text message is one of the easiest ways to spot a bot.
Prompts ask for none; this removes any that slip through, so it never depends on the model obeying.
"""

from __future__ import annotations

import re

_RANGE = re.compile(r"(?<=\d)\s*[–—]\s*(?=\d)")          # 10–20 -> 10-20
_DASH = re.compile(r"\s*(?:[—–―]|--+)\s*")            # — – ― -- between words
_SPACES = re.compile(r"[ \t]{2,}")


def no_dashes(text: str) -> str:
    """Replace em/en dashes with what a person would type: a comma (or a hyphen in number ranges)."""
    if not text:
        return text
    text = _RANGE.sub("-", text)
    text = _DASH.sub(", ", text)
    text = re.sub(r",\s*([,.!?])", r"\1", text)      # "word —." -> "word."
    text = re.sub(r"^\s*,\s*", "", text)               # leading dash
    text = re.sub(r"\s*,\s*$", "", text)               # trailing dash
    return _SPACES.sub(" ", text).strip()


def typing_seconds(text: str) -> float:
    """How long a slow, older texter takes to type this: a short pause plus ~6 characters a second."""
    return min(12.0, 2.0 + len(text or "") / 6.0)
