"""Mirror the engine's store into SpacetimeDB, so phones and the dashboard see every step live.

The engine keeps working on its in-memory store (fast, testable). Each write it makes is
an event; this mirror turns events into reducer calls on a background thread, in order,
so a slow network never slows a takeover. Reducer errors are logged, never raised: the
module's own guards (e.g. Talon can't reply after Stop) still apply.
"""

from __future__ import annotations

import json
import queue
import threading
from dataclasses import asdict, is_dataclass

from .spacetime import SpacetimeClient, SpacetimeError, opt
from .store import Store

MAX_STEP_JSON = 6000  # keep agent_step rows small; the dashboard shows a summary anyway


class SpacetimeMirror:
    def __init__(self, client: SpacetimeClient, store: Store, log=print):
        self.client = client
        self.store = store
        self.log = log
        self.q: queue.Queue = queue.Queue()
        self.errors: list[str] = []
        # What has already been written, so repeated update events don't double-insert.
        self._messages: set[str] = set()
        self._triaged: set[str] = set()
        self._sessions: set[str] = set()
        self._stopped: set[str] = set()
        self._campaigns: set[str] = set()
        self._linked: set[tuple[str, str]] = set()
        self._burned: set[str] = set()
        self._thread = threading.Thread(target=self._run, name="spacetime-mirror", daemon=True)
        self._thread.start()
        store.listeners.append(self.on_event)

    # The store calls this synchronously; snapshot the row and hand it to the worker.
    def on_event(self, table: str, row) -> None:
        snap = asdict(row) if is_dataclass(row) else json.loads(json.dumps(row, default=str))
        self.q.put((table, snap))

    def flush(self, timeout: float = 30) -> None:
        """Block until every queued write has been sent (tests, CLI runs, shutdown)."""
        done = threading.Event()
        self.q.put(("__flush__", done))
        done.wait(timeout)

    def _run(self) -> None:
        while True:
            table, row = self.q.get()
            if table == "__flush__":
                row.set()
                continue
            try:
                getattr(self, f"_{table}")(row)
            except SpacetimeError as e:
                self.errors.append(f"{table}: {e}")
                self.log(f"[mirror] {table}: {e}")
            except Exception as e:  # noqa: BLE001 - never kill the worker
                self.errors.append(f"{table}: {e!r}")
                self.log(f"[mirror] {table}: {e!r}")

    # ------------------------------------------------------------------ tables

    def _inbound_message(self, m: dict) -> None:
        c = self.client
        if m["id"] not in self._messages:
            self._messages.add(m["id"])
            c.call("receive_message", m["id"], m["customer_ref"], m["sender"], m.get("channel", "sms"), m["text"])
        triage = m.get("triage")
        if triage and m["id"] not in self._triaged:
            self._triaged.add(m["id"])
            # "scam" makes the module show the warning; below the threshold it stays a plain text.
            label = "scam" if m["status"] == "warned" else ("suspicious" if triage.get("is_scam") else "legit")
            c.call("set_triage", m["id"], label, opt(triage.get("category")), float(triage.get("confidence") or 0),
                   triage.get("reason") or "")

    def _session(self, s: dict) -> None:
        if s["id"] not in self._sessions:
            self._sessions.add(s["id"])
            if s.get("origin") != "phone":  # the phone already created it with request_takeover
                self.client.call("request_takeover", s["inbound_message_id"], s["id"])
        if s["status"] == "ended" and s.get("ended_reason") == "customer_stop" and s["id"] not in self._stopped:
            self._stopped.add(s["id"])
            self.client.call("stop_takeover", s["id"])  # no-op if the phone already stopped it

    def _turn(self, t: dict) -> None:
        self.client.call("add_turn", t["id"], t["session_id"], t["sender"], t["text"], opt(None), opt(None),
                         bool(t.get("safety_passed", True)))

    def _agent_step(self, st: dict) -> None:
        content = json.dumps(st["content"], ensure_ascii=False, default=str)
        if len(content) > MAX_STEP_JSON:
            content = json.dumps({"truncated": content[:MAX_STEP_JSON]}, ensure_ascii=False)
        self.client.call("add_agent_step", st["session_id"], opt(st.get("turn_id")), st["agent"], st["kind"],
                         content, int(st.get("latency_ms") or 0))

    def _handler_plan(self, p: dict) -> None:
        self.client.call("add_handler_plan", p["session_id"], opt(p.get("turn_id")), list(p.get("have") or []),
                         str(p.get("need") or ""), str(p.get("tactic") or ""), str(p.get("note") or ""))

    def _indicator(self, i: dict) -> None:
        self.client.call("add_indicator", i["session_id"], i["turn_id"], i["kind"], i["value"],
                         float(i.get("confidence") or 0))

    def _campaign(self, cp: dict) -> None:
        c = self.client
        label = cp.get("label") or f"{(cp.get('category') or 'unknown').replace('_', ' ')} campaign"
        c.call("upsert_campaign", cp["id"], cp.get("category") or "unknown", label, opt(cp.get("brand")),
               int(cp.get("customers_targeted") or 0))
        self._campaigns.add(cp["id"])
        for sid in cp.get("session_ids") or []:
            if (cp["id"], sid) not in self._linked and sid in self._sessions:
                self._linked.add((cp["id"], sid))
                c.call("link_session", sid, cp["id"])
        if cp.get("status") == "burned" and cp["id"] not in self._burned:
            self._burned.add(cp["id"])
            c.call("burn_campaign", cp["id"])

    def _customer_alert(self, a: dict) -> None:
        self.client.call("add_customer_alert", a["campaign_id"], a["customer_ref"], opt(a.get("inbound_message_id")),
                         a["kind"], a["text"])

    def _impact_card(self, card: dict) -> None:
        campaign = self.store.campaigns.get(card.get("campaign_id") or "")
        protected = int(campaign["customers_targeted"]) if campaign else 1
        self.client.call("add_impact_card", card["session_id"], opt(card.get("campaign_id")), max(protected, 1),
                         card["text"])

    def _tripwire(self, tw: dict) -> None:
        session = self.store.sessions.get(tw["session_id"], {})
        self.client.call("issue_tripwire", tw["id"], session.get("campaign_id") or "", tw["session_id"], tw["kind"],
                         tw["token"])
