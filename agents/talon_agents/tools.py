"""Tools the Handler and Campaign Analyst agents call, with OpenAI-style schemas.

Guardrails live here, in code: an unknown tactic is refused, and a campaign can't be burned
without enough evidence, whatever the model asks for.
"""

from __future__ import annotations

import random
import string
from dataclasses import dataclass
from typing import Callable

from .retrieval import ScamRetriever
from .state import PAYMENT_KINDS, SessionState
from .store import Store, normalize_value
from .taxonomy import Taxonomy


def fn(name: str, description: str, properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties or {}, "required": required or []}}}


# ---------------------------------------------------------------------------
# Triage
# ---------------------------------------------------------------------------

TRIAGE_TOOLS = [
    fn("search_similar_scams", "Search known scam patterns and earlier campaigns for messages like this one. "
       "Only call this when you are unsure of the verdict or the category.",
       {"query": {"type": "string", "description": "The message text or its key phrases"}}, ["query"]),
]


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

HANDLER_TOOLS = [
    fn("get_intel_gaps", "What we want from this scammer (from the category's indicators and asks) vs what we have."),
    fn("get_category_playbook", "The taxonomy playbook for a scam category: brands, hooks, asks, indicators, decoy tactics. "
       "Call it when the category is new to you this session or seems to have changed.",
       {"category": {"type": "string"}}, ["category"]),
    fn("lookup_indicator", "Check campaign memory for an indicator value (link, number, wallet...). "
       "Only worth calling when a new indicator appeared this turn.",
       {"value": {"type": "string"}}, ["value"]),
    fn("choose_tactic", "Pick this turn's decoy tactic. Must be one of the taxonomy's decoy tactics.",
       {"tactic_id": {"type": "string"}, "note": {"type": "string", "description": "Why this tactic, in a few words"}},
       ["tactic_id", "note"]),
    fn("issue_tripwire", "Create a fictional, trackable gift card code for the persona to hand over. "
       "Use when the scammer is asking for gift card codes.",
       {"kind": {"type": "string", "enum": ["giftcard"]}}, ["kind"]),
    fn("flag_bot_suspected", "Flag that the scammer looks like an automated bot.",
       {"reason": {"type": "string"}}, ["reason"]),
    fn("end_takeover", "End the takeover: goals met, scammer gone, or continuing is risky.",
       {"reason": {"type": "string"}}, ["reason"]),
]


@dataclass
class HandlerToolbox:
    state: SessionState
    store: Store
    taxonomy: Taxonomy

    def run(self, name: str, args: dict) -> dict:
        impl: Callable[..., dict] | None = getattr(self, f"_{name}", None)
        if impl is None:
            return {"error": f"unknown tool {name!r}"}
        try:
            return impl(**args)
        except TypeError as e:
            return {"error": f"bad arguments for {name}: {e}"}

    def _get_intel_gaps(self) -> dict:
        cat = self.taxonomy.category(self.state.category) or {}
        wanted = list(dict.fromkeys([*cat.get("indicators", []), "payment_method"]))
        have = {i["kind"] for i in self.store.indicators_for(self.state.session_id)}
        collected = sorted(have)
        missing = [w for w in wanted if w not in have and not (w == "payment_method" and have & set(PAYMENT_KINDS))]
        return {"wanted": wanted, "collected": collected, "missing": missing,
                "scammer_asks_for": cat.get("asks", []), "tactics_used": self.state.tactics_used,
                "turn": self.state.turn_count}

    def _get_category_playbook(self, category: str) -> dict:
        return self.taxonomy.playbook(category)

    def _lookup_indicator(self, value: str) -> dict:
        hits = self.store.find_indicator(value, exclude_session=self.state.session_id)
        campaigns = sorted({h["campaign_id"] for h in hits if h["campaign_id"]})
        return {"value": value, "seen_in_other_sessions": len({h["session_id"] for h in hits}),
                "campaign_ids": campaigns,
                "burned": [c for c in campaigns if self.store.campaigns.get(c, {}).get("status") == "burned"]}

    def _choose_tactic(self, tactic_id: str, note: str = "") -> dict:
        if tactic_id not in self.taxonomy.tactics:
            return {"error": f"{tactic_id!r} is not a decoy tactic", "allowed": sorted(self.taxonomy.tactics)}
        self.state.chosen_tactic = {"tactic": tactic_id, "note": note}
        return {"ok": True, "tactic": tactic_id, "description": self.taxonomy.tactics[tactic_id],
                "times_used_before": self.state.tactics_used.count(tactic_id)}

    def _issue_tripwire(self, kind: str = "giftcard") -> dict:
        if kind != "giftcard":
            return {"error": "only giftcard tripwires are supported"}
        # Letters and digits in groups of 4 with a fixed TW marker: clearly fictional internally,
        # and short digit runs so it never looks like a real card number.
        groups = ["".join(random.choices(string.ascii_uppercase + "23456789", k=4)) for _ in range(3)]
        token = "-".join(["TW", *groups])
        row = self.store.issue_tripwire(self.state.session_id, kind, token)
        self.state.tripwire_tokens.append(token)
        return {"ok": True, "tripwire_id": row["id"], "code_for_persona": token,
                "note": "Fictional code. The persona may read it out exactly as given."}

    def _flag_bot_suspected(self, reason: str) -> dict:
        self.state.bot_suspected = True
        self.store.update_session(self.state.session_id, is_bot_suspected=True)
        return {"ok": True}

    def _end_takeover(self, reason: str) -> dict:
        self.state.end_reason = f"handler: {reason}"
        return {"ok": True, "ending": True}


# ---------------------------------------------------------------------------
# Campaign Analyst
# ---------------------------------------------------------------------------

ANALYST_TOOLS = [
    fn("link_to_campaign", "Link this session to a campaign using indicators shared with other sessions. "
       "Creates a new campaign if nothing matches."),
    fn("burn_campaign", "Shut a campaign down network-wide: its links and numbers get blocked. "
       "Refused unless evidence is strong.",
       {"campaign_id": {"type": "string"}, "reason": {"type": "string"}}, ["campaign_id", "reason"]),
    fn("warn_customers", "Warn or block other customers who received messages from a burned campaign.",
       {"campaign_id": {"type": "string"}}, ["campaign_id"]),
]

# sender_number: the number the scam came from, Talon's first data point on any scammer.
STRONG_KINDS = ("sender_number", "url", "phone", "email", *PAYMENT_KINDS, "remote_access_id")


@dataclass
class AnalystToolbox:
    state: SessionState
    store: Store
    retriever: ScamRetriever | None = None
    burn_min_sessions: int = 2
    burn_min_confidence: float = 0.9

    def run(self, name: str, args: dict) -> dict:
        impl = getattr(self, f"_{name}", None)
        if impl is None:
            return {"error": f"unknown tool {name!r}"}
        try:
            return impl(**args)
        except TypeError as e:
            return {"error": f"bad arguments for {name}: {e}"}

    def _link_to_campaign(self) -> dict:
        sid = self.state.session_id
        mine = [i for i in self.store.indicators_for(sid) if i["kind"] in STRONG_KINDS]
        shared, other_sessions = [], set()
        for ind in mine:
            for hit in self.store.find_indicator(ind["value"], exclude_session=sid):
                shared.append({"kind": ind["kind"], "value": ind["value"], "other_session": hit["session_id"]})
                other_sessions.add(hit["session_id"])
        existing = [self.store.sessions[s]["campaign_id"] for s in other_sessions if self.store.sessions[s].get("campaign_id")]
        campaign_id = self.store.sessions[sid].get("campaign_id") or (existing[0] if existing else None)
        if campaign_id is None:
            campaign = self.store.upsert_campaign(category=self.state.category)
            campaign_id = campaign["id"]
        for s in {sid, *other_sessions}:
            self.store.link_session(campaign_id, s)
        campaign = self.store.campaigns[campaign_id]
        met, rule = self.evidence(campaign_id)
        return {"campaign_id": campaign_id, "sessions": len(campaign["session_ids"]), "status": campaign["status"],
                "shared_indicators": shared, "payment_indicators": [i["value"] for i in mine if i["kind"] in PAYMENT_KINDS],
                "triage_confidence": self.state.confidence, "burn_evidence_met": met, "rule": rule}

    def evidence(self, campaign_id: str) -> tuple[bool, str]:
        """The burn rule, in one place: 2+ sessions, or a payment method from a high-confidence scam."""
        campaign = self.store.campaigns[campaign_id]
        sessions = len(campaign["session_ids"])
        has_payment = any(i["kind"] in PAYMENT_KINDS for s in campaign["session_ids"] for i in self.store.indicators_for(s))
        met = sessions >= self.burn_min_sessions or (has_payment and self.state.confidence >= self.burn_min_confidence)
        return met, (f"{sessions} session(s), payment indicator: {has_payment}, confidence {self.state.confidence:.2f}. "
                     f"Burn needs {self.burn_min_sessions}+ sessions, or a payment indicator with confidence >= "
                     f"{self.burn_min_confidence}.")

    def _burn_campaign(self, campaign_id: str, reason: str = "") -> dict:
        campaign = self.store.campaigns.get(campaign_id)
        if not campaign:
            return {"error": f"unknown campaign {campaign_id!r}"}
        if campaign["status"] == "burned":
            return {"ok": True, "already_burned": True}
        strong, rule = self.evidence(campaign_id)
        if not strong:
            return {"refused": True, "why": f"evidence too weak: {rule}"}
        self.store.burn_campaign(campaign_id)
        blocked = sorted({i["value"] for s in campaign["session_ids"] for i in self.store.indicators_for(s)
                          if i["kind"] in STRONG_KINDS})
        return {"ok": True, "campaign_id": campaign_id, "blocked_indicators": blocked, "reason": reason}

    def _warn_customers(self, campaign_id: str) -> dict:
        campaign = self.store.campaigns.get(campaign_id)
        if not campaign or campaign["status"] != "burned":
            return {"error": "only burned campaigns trigger customer warnings"}
        values = {normalize_value(i["value"]) for s in campaign["session_ids"] for i in self.store.indicators_for(s)
                  if i["kind"] in STRONG_KINDS}
        own = {self.store.sessions[s]["customer_ref"] for s in campaign["session_ids"]}
        warned = []
        for msg in self.store.inbound_messages:
            if msg["customer_ref"] in own or msg.get("warned_by") == campaign_id:
                continue
            if any(v and v in normalize_value(msg["text"]) for v in values):
                msg["warned_by"] = campaign_id
                self.store.add_customer_alert(campaign_id, msg["customer_ref"], "warned",
                                              "Talon shut down the scam campaign behind this message.",
                                              inbound_message_id=msg["id"])
                warned.append(msg["customer_ref"])
        campaign["customers_targeted"] = len(own) + len(warned)
        return {"ok": True, "customers_warned": len(warned), "customers_targeted": campaign["customers_targeted"]}
