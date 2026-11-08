"""Per-session state the engine carries between scammer turns."""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_PERSONA = {
    # Fictional. Build step 2+ seeds personas from Nemotron-Personas-USA.
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
    turn_count: int = 0

    @property
    def ended(self) -> bool:
        return self.end_reason is not None
