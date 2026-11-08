"""Per-session state the engine carries between scammer turns."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

PERSONAS_FILE = Path(__file__).resolve().parents[2] / "data" / "personas.jsonl"

DEFAULT_PERSONA = {
    # Fictional fallback when data/personas.jsonl (Nemotron-Personas-USA) isn't there.
    "id": "persona_default",
    "source": "talon-default",
    "name": "Marjorie",
    "age": 72,
    "city": "Tulsa",
    "state": "OK",
    # How she texts. This shapes every message.
    "voice": ["short, plain texts, mostly lowercase", "polite, cooperative, a little slow to catch on",
              "asks a simple question when something doesn't make sense", "the odd small typo"],
    # Facts she knows. Background only: used when relevant, never as filler (see agents/persona.py).
    "background": ["retired school librarian", "lives alone with a cat named Biscuit",
                   "her grandson sometimes helps her with technology"],
    # How to spot each background detail in a reply, so it's brought up at most once per conversation.
    "details": {"the cat": ["biscuit", "cat", "kitty"], "the grandson": ["grandson", "grandkid", "grandchild"],
                "being a librarian": ["librar"], "the city": ["tulsa"], "her name": ["marjorie"]},
}

PAYMENT_KINDS = ("wallet", "payment_handle", "account", "giftcard_ask")


@lru_cache(maxsize=1)
def load_personas() -> tuple[dict, ...]:
    """Synthetic people Talon can speak as: data/personas.jsonl (from NVIDIA's Nemotron-Personas-USA,
    CC BY 4.0, see scripts/data/fetch_personas.py), or the built-in default if it's missing."""
    if PERSONAS_FILE.exists():
        with PERSONAS_FILE.open(encoding="utf-8") as f:
            personas = tuple(json.loads(line) for line in f if line.strip())
        if personas:
            return personas
    return (DEFAULT_PERSONA,)


def pick_persona(key: str) -> dict:
    """Same session, same person: chosen by a hash of the session id, not at random."""
    personas = load_personas()
    return dict(personas[int(hashlib.sha1(key.encode()).hexdigest(), 16) % len(personas)])


@dataclass
class SessionState:
    session_id: str
    customer_ref: str
    category: str | None
    confidence: float
    persona: dict = field(default_factory=lambda: dict(DEFAULT_PERSONA))
    tactics_used: list[str] = field(default_factory=list)
    tripwire_tokens: list[str] = field(default_factory=list)
    chosen_tactic: dict | None = None  # set by choose_tactic during the current turn
    bot_suspected: bool = False
    end_reason: str | None = None
    fallback_streak: int = 0
    stale_turns: int = 0  # scammer turns in a row that gave Talon nothing new
    turn_count: int = 0

    @property
    def ended(self) -> bool:
        return self.end_reason is not None
