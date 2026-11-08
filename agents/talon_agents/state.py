"""Per-session state the engine carries between scammer turns."""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_PERSONA = {
    # Fictional. Build step 2+ seeds personas from Nemotron-Personas-USA.
    "name": "Marjorie",
    "age": 72,
    "city": "Tulsa",
    "state": "OK",
    "backstory": "Retired school librarian, lives alone with a cat named Biscuit, not great with phones.",
    "quirks": ["types slowly", "asks people to repeat things", "mentions her grandson who 'does computers'"],
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
