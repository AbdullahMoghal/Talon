"""The Talon engine: customer flow plus the per-turn multi-agent graph.

Customer flow:   receive_message -> triage -> warning with [Delete] [Report] [Let Talon handle it]
                 request_takeover (only on the customer's tap) -> takeover session
Per scammer turn (LangGraph):

    triage? -> extract -> handler --(end_takeover)--> END
                             |
                             v
                          persona <--- rejected (max 2 retries) ---+
                             |                                      |
                             v                                      |
                          safety ---------------------------------->+
                             | passed            | out of retries
                             v                   v
                           send <------------ fallback (canned safe line)

After the reply: the Campaign Analyst runs whenever new indicators were stored.
Stop conditions: customer Stop, end_takeover, turn cap, 3 fallback turns in a row.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from .agents.analyst import run_analyst, write_impact_card
from .agents.extractor import run_extractor
from .agents.handler import run_handler
from .agents.persona import run_persona
from .agents.safety import SAFE_FALLBACK, run_safety
from .agents.triage import run_triage
from .config import Settings
from .llm import LLM, make_llm
from .retrieval import ScamRetriever
from .state import SessionState
from .store import InMemoryStore, Store, Tracer, normalize_value
from .taxonomy import Taxonomy, load_taxonomy
from .tools import STRONG_KINDS


class TurnState(TypedDict, total=False):
    session_id: str
    scammer_text: str
    turn_id: str
    new_indicators: list[dict]
    plan: dict
    draft: str
    feedback: list[str]
    attempts: int
    passed: bool
    reply: str | None
    used_fallback: bool


class TalonEngine:
    def __init__(self, *, llm: LLM | None = None, store: Store | None = None, settings: Settings | None = None,
                 taxonomy: Taxonomy | None = None, retriever: ScamRetriever | None = None, run_analyst_inline: bool = True):
        self.settings = settings or Settings.from_env()
        self.llm = llm or make_llm(self.settings)
        self.store = store or InMemoryStore()
        self.taxonomy = taxonomy or load_taxonomy()
        self.retriever = retriever or ScamRetriever(self.taxonomy)
        self.run_analyst_inline = run_analyst_inline
        self.sessions: dict[str, SessionState] = {}
        self.tracers: dict[str, Tracer] = {}
        self.graph = self._build_graph()

    # ------------------------------------------------------------------
    # Customer flow
    # ------------------------------------------------------------------

    def receive_message(self, customer_ref: str, sender: str, text: str) -> dict:
        """A text lands on a customer's phone. Blocked if a burned campaign sent it, else triaged."""
        earlier = [m["text"] for m in self.store.inbound_messages
                   if m["customer_ref"] == customer_ref and m["sender"] == sender][-4:]
        msg = self.store.add_inbound(customer_ref, sender, text)
        burned = self._burned_campaign_for(text)
        if burned:
            self.store.update_inbound(msg["id"], status="blocked", campaign_id=burned)
            self.store.add_customer_alert(burned, customer_ref, "blocked",
                                          "Blocked: Talon already shut down the scam campaign behind this message.",
                                          inbound_message_id=msg["id"])
            return {"message_id": msg["id"], "status": "blocked", "campaign_id": burned}

        tracer = Tracer(self.store, session_id=msg["id"])  # pre-session trace, keyed by the message
        triage = run_triage(llm=self.llm, text=text, taxonomy=self.taxonomy, retriever=self.retriever,
                            tracer=tracer, settings=self.settings, context=earlier)
        warned = triage["is_scam"] and triage["confidence"] >= self.settings.triage_threshold
        self.store.update_inbound(msg["id"], status="warned" if warned else "delivered", triage=triage)
        return {"message_id": msg["id"], "status": "warned" if warned else "delivered", "triage": triage,
                "buttons": ["delete", "report", "let_talon_handle_it"] if warned else []}

    def request_takeover(self, message_id: str, session_id: str | None = None,
                         origin: str = "engine") -> tuple[dict, str | None]:
        """The customer tapped "Let Talon handle it". The only way a takeover starts.

        session_id/origin: in the live demo the customer's phone creates the session itself
        (request_takeover reducer) and the engine adopts it with origin="phone".
        """
        msg = next(m for m in self.store.inbound_messages if m["id"] == message_id)
        if msg["status"] == "blocked":
            raise ValueError("message was already blocked")
        if msg.get("session_id"):
            raise ValueError("this message already has a takeover session")
        triage = msg.get("triage") or {}
        session = self.store.start_session(session_id=session_id, origin=origin, source="customer",
                                           customer_ref=msg["customer_ref"],
                                           inbound_message_id=message_id, scammer_number=msg["sender"],
                                           category=triage.get("category"), confidence=triage.get("confidence", 0.0))
        self.store.update_inbound(message_id, status="taken_over", session_id=session["id"])
        state = SessionState(session_id=session["id"], customer_ref=msg["customer_ref"],
                             category=triage.get("category"), confidence=float(triage.get("confidence") or 0))
        self.sessions[session["id"]] = state
        self.tracers[session["id"]] = Tracer(self.store, session["id"])
        if state.category:
            self.retriever.add(state.category, msg["text"])
        # Talon replies to the scam text the customer handed over.
        return session, self.handle_scammer_message(session["id"], msg["text"])

    def stop_takeover(self, session_id: str) -> dict | None:
        """The customer tapped Stop. No Talon reply is sent after this."""
        return self._end(self.sessions[session_id], "customer_stop")

    # ------------------------------------------------------------------
    # Scammer turns
    # ------------------------------------------------------------------

    def handle_scammer_message(self, session_id: str, text: str) -> str | None:
        state = self.sessions[session_id]
        if state.ended or self.store.sessions[session_id]["status"] != "active":
            return None
        turn = self.store.add_turn(session_id, "scammer", text)
        state.turn_count += 1
        tracer = self.tracers[session_id]
        tracer.turn_id = turn["id"]

        result = self.graph.invoke({"session_id": session_id, "scammer_text": text, "turn_id": turn["id"],
                                    "attempts": 0, "feedback": []})

        state.fallback_streak = state.fallback_streak + 1 if result.get("used_fallback") else 0
        if result.get("new_indicators") and self.run_analyst_inline:
            run_analyst(llm=self.llm, state=state, store=self.store, tracer=tracer, settings=self.settings,
                        retriever=self.retriever)

        if state.end_reason:
            self._end(state, state.end_reason)
        elif state.turn_count >= self.settings.max_turns:
            self._end(state, "turn_cap")
        elif state.fallback_streak >= 3:
            self._end(state, "safety_risk")
        return result.get("reply")

    def _end(self, state: SessionState, reason: str) -> dict | None:
        if self.store.sessions[state.session_id]["status"] != "active":
            return None
        state.end_reason = state.end_reason or reason
        self.store.update_session(state.session_id, status="ended", ended_reason=state.end_reason)
        self.tracers[state.session_id].step("engine", "output", {"session_ended": state.end_reason})
        return write_impact_card(llm=self.llm, state=state, store=self.store, taxonomy=self.taxonomy,
                                 tracer=self.tracers[state.session_id])

    def _burned_campaign_for(self, text: str) -> str | None:
        norm = normalize_value(text)
        for campaign in self.store.campaigns.values():
            if campaign["status"] != "burned":
                continue
            for sid in campaign["session_ids"]:
                for ind in self.store.indicators_for(sid):
                    v = normalize_value(ind["value"])
                    if ind["kind"] in STRONG_KINDS and len(v) >= 6 and v in norm:
                        return campaign["id"]
        return None

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------

    def _build_graph(self):
        g = StateGraph(TurnState)

        def ctx(ts: TurnState) -> tuple[SessionState, Tracer]:
            return self.sessions[ts["session_id"]], self.tracers[ts["session_id"]]

        def triage(ts: TurnState) -> dict:
            state, tracer = ctx(ts)
            if state.category is None:  # e.g. a canary session that never went through customer triage
                out = run_triage(llm=self.llm, text=ts["scammer_text"], taxonomy=self.taxonomy,
                                 retriever=self.retriever, tracer=tracer, settings=self.settings)
                state.category, state.confidence = out["category"], out["confidence"]
                self.store.update_session(state.session_id, category=state.category, confidence=state.confidence)
            return {}

        def extract(ts: TurnState) -> dict:
            state, tracer = ctx(ts)
            found = run_extractor(llm=self.llm, text=ts["scammer_text"], taxonomy=self.taxonomy, store=self.store,
                                  tracer=tracer, session_id=state.session_id, turn_id=ts["turn_id"],
                                  category=state.category)
            return {"new_indicators": found}

        def handler(ts: TurnState) -> dict:
            state, tracer = ctx(ts)
            plan = run_handler(llm=self.llm, state=state, store=self.store, taxonomy=self.taxonomy, tracer=tracer,
                               settings=self.settings, scammer_text=ts["scammer_text"],
                               new_indicators=ts.get("new_indicators", []), turn_id=ts["turn_id"])
            return {"plan": plan}

        def persona(ts: TurnState) -> dict:
            state, tracer = ctx(ts)
            recent = [{"from": t["sender"], "text": t["text"]} for t in self.store.turns_for(state.session_id)[-6:]]
            draft = run_persona(llm=self.llm, persona=state.persona, plan=ts["plan"], recent_turns=recent,
                                tracer=tracer, feedback=ts.get("feedback") or None)
            return {"draft": draft, "attempts": ts.get("attempts", 0) + 1}

        def safety(ts: TurnState) -> dict:
            state, tracer = ctx(ts)
            # A tripwire code the handler told the persona to read must appear exactly, not spelled out.
            required = [t for t in state.tripwire_tokens if t in ts["plan"].get("instructions_for_persona", "")]
            verdict = run_safety(llm=self.llm, text=ts["draft"], tracer=tracer, allowed_tokens=state.tripwire_tokens,
                                 required_tokens=required)
            return {"passed": verdict["passed"], "feedback": verdict["violations"]}

        def fallback(ts: TurnState) -> dict:
            _, tracer = ctx(ts)
            tracer.step("safety", "output", {"fallback": SAFE_FALLBACK, "why": "persona failed review too many times"})
            return {"draft": SAFE_FALLBACK, "used_fallback": True}

        def send(ts: TurnState) -> dict:
            state, _ = ctx(ts)
            if self.store.sessions[state.session_id]["status"] != "active":
                return {"reply": None}  # customer tapped Stop mid-turn
            self.store.add_turn(state.session_id, "talon", ts["draft"], safety_passed=True)
            return {"reply": ts["draft"]}

        for name, node in [("triage", triage), ("extract", extract), ("handler", handler), ("persona", persona),
                           ("safety", safety), ("fallback", fallback), ("send", send)]:
            g.add_node(name, node)
        g.add_edge(START, "triage")
        g.add_edge("triage", "extract")
        g.add_edge("extract", "handler")
        g.add_conditional_edges("handler", lambda ts: END if self.sessions[ts["session_id"]].ended else "persona")
        g.add_edge("persona", "safety")
        max_attempts = 1 + self.settings.max_safety_retries
        g.add_conditional_edges("safety", lambda ts: "send" if ts["passed"]
                                else ("persona" if ts["attempts"] < max_attempts else "fallback"))
        g.add_edge("fallback", "send")
        g.add_edge("send", END)
        return g.compile()
