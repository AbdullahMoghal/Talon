"""Where the engine writes sessions, turns, the agent trace, indicators and campaigns.

`InMemoryStore` is used for tests and offline runs. A SpacetimeDB-backed store (HTTP reducer
calls) will implement the same methods in build step 3. IDs are caller-chosen strings,
because SpacetimeDB reducers can't return values.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class AgentStep:
    id: str
    session_id: str
    turn_id: str | None
    agent: str  # triage | extractor | handler | persona | safety | analyst | judge
    kind: str  # thought | tool_call | tool_result | output | rejection | retrieval_skipped
    content: dict
    latency_ms: int
    created_at: int


@dataclass
class Store:
    sessions: dict[str, dict] = field(default_factory=dict)
    turns: list[dict] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    indicators: list[dict] = field(default_factory=list)
    handler_plans: list[dict] = field(default_factory=list)
    campaigns: dict[str, dict] = field(default_factory=dict)
    customer_alerts: list[dict] = field(default_factory=list)
    impact_cards: list[dict] = field(default_factory=list)
    tripwires: list[dict] = field(default_factory=list)
    inbound_messages: list[dict] = field(default_factory=list)
    listeners: list[Callable[[str, object], None]] = field(default_factory=list)

    def _emit(self, table: str, row: object) -> None:
        for listener in self.listeners:
            listener(table, row)

    # inbound messages on customers' phones
    def add_inbound(self, customer_ref: str, sender: str, text: str, **fields) -> dict:
        row = {"id": new_id("msg"), "customer_ref": customer_ref, "sender": sender, "text": text,
               "status": "delivered", "received_at": now_ms(), **fields}
        self.inbound_messages.append(row)
        self._emit("inbound_message", row)
        return row

    def update_inbound(self, message_id: str, **fields) -> dict:
        row = next(m for m in self.inbound_messages if m["id"] == message_id)
        row.update(fields)
        self._emit("inbound_message", row)
        return row

    # sessions and turns
    def start_session(self, session_id: str | None = None, **fields) -> dict:
        session = {"id": session_id or new_id("ses"), "status": "active", "started_at": now_ms(), "ended_reason": None,
                   "campaign_id": None, "turn_count": 0, **fields}
        self.sessions[session["id"]] = session
        self._emit("session", session)
        return session

    def update_session(self, session_id: str, **fields) -> dict:
        session = self.sessions[session_id]
        session.update(fields)
        self._emit("session", session)
        return session

    def add_turn(self, session_id: str, sender: str, text: str, safety_passed: bool = True) -> dict:
        session = self.sessions[session_id]
        if sender == "talon" and (session["status"] != "active" or not safety_passed):
            # Mirrors the add_turn guard in the SpacetimeDB module.
            raise PermissionError("Talon can't reply: session not active or reply failed the safety guard")
        turn = {"id": new_id("turn"), "session_id": session_id, "sender": sender, "text": text,
                "safety_passed": safety_passed, "created_at": now_ms()}
        self.turns.append(turn)
        if sender == "scammer":
            session["turn_count"] += 1
        self._emit("turn", turn)
        return turn

    def turns_for(self, session_id: str) -> list[dict]:
        return [t for t in self.turns if t["session_id"] == session_id]

    # trace
    def add_agent_step(self, session_id, turn_id, agent, kind, content, latency_ms=0) -> AgentStep:
        step = AgentStep(new_id("step"), session_id, turn_id, agent, kind, content, latency_ms, now_ms())
        self.steps.append(step)
        self._emit("agent_step", step)
        return step

    def steps_for(self, session_id: str, agent: str | None = None, kind: str | None = None) -> list[AgentStep]:
        return [s for s in self.steps if s.session_id == session_id
                and (agent is None or s.agent == agent) and (kind is None or s.kind == kind)]

    def add_handler_plan(self, session_id, turn_id, plan: dict) -> dict:
        row = {"id": new_id("plan"), "session_id": session_id, "turn_id": turn_id, **plan, "created_at": now_ms()}
        self.handler_plans.append(row)
        self._emit("handler_plan", row)
        return row

    # indicators
    def add_indicator(self, session_id, turn_id, kind, value, confidence) -> dict:
        row = {"id": new_id("ind"), "session_id": session_id, "turn_id": turn_id, "kind": kind,
               "value": value, "confidence": confidence, "campaign_id": None, "created_at": now_ms()}
        self.indicators.append(row)
        self._emit("indicator", row)
        return row

    def indicators_for(self, session_id: str) -> list[dict]:
        return [i for i in self.indicators if i["session_id"] == session_id]

    def find_indicator(self, value: str, exclude_session: str | None = None) -> list[dict]:
        key = normalize_value(value)
        return [i for i in self.indicators
                if normalize_value(i["value"]) == key and i["session_id"] != exclude_session]

    # campaigns and customer-facing outputs
    def upsert_campaign(self, campaign_id: str | None = None, **fields) -> dict:
        if campaign_id and campaign_id in self.campaigns:
            self.campaigns[campaign_id].update(fields)
        else:
            campaign_id = campaign_id or new_id("cmp")
            self.campaigns[campaign_id] = {"id": campaign_id, "status": "active", "first_seen": now_ms(),
                                           "burned_at": None, "session_ids": [], "customers_targeted": 0, **fields}
        self._emit("campaign", self.campaigns[campaign_id])
        return self.campaigns[campaign_id]

    def link_session(self, campaign_id: str, session_id: str) -> dict:
        campaign = self.campaigns[campaign_id]
        if session_id not in campaign["session_ids"]:
            campaign["session_ids"].append(session_id)
        self.sessions[session_id]["campaign_id"] = campaign_id
        for ind in self.indicators_for(session_id):
            ind["campaign_id"] = campaign_id
        self._emit("campaign", campaign)
        return campaign

    def burn_campaign(self, campaign_id: str) -> dict:
        return self.upsert_campaign(campaign_id, status="burned", burned_at=now_ms())

    def add_customer_alert(self, campaign_id, customer_ref, kind, text, inbound_message_id=None) -> dict:
        row = {"id": new_id("alert"), "campaign_id": campaign_id, "customer_ref": customer_ref,
               "inbound_message_id": inbound_message_id, "kind": kind, "text": text, "shown_at": now_ms()}
        self.customer_alerts.append(row)
        self._emit("customer_alert", row)
        return row

    def add_impact_card(self, session_id, campaign_id, text, cited_indicator_ids) -> dict:
        row = {"id": new_id("impact"), "session_id": session_id, "campaign_id": campaign_id, "text": text,
               "cited_indicator_ids": list(cited_indicator_ids), "created_at": now_ms()}
        self.impact_cards.append(row)
        self._emit("impact_card", row)
        return row

    def issue_tripwire(self, session_id, kind, token) -> dict:
        row = {"id": new_id("trip"), "session_id": session_id, "kind": kind, "token": token, "issued_at": now_ms()}
        self.tripwires.append(row)
        self._emit("tripwire", row)
        return row


def normalize_value(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


class InMemoryStore(Store):
    pass


@dataclass
class Tracer:
    """Writes agent_step rows for one session. The engine sets `turn_id` as turns progress."""

    store: Store
    session_id: str
    turn_id: str | None = None

    def step(self, agent: str, kind: str, content: dict, latency_ms: int = 0) -> AgentStep:
        return self.store.add_agent_step(self.session_id, self.turn_id, agent, kind, content, latency_ms)
