"""Live demo runner: connects the engine to SpacetimeDB so phones and the dashboard work.

    python -m talon_agents.live --server http://127.0.0.1:4000 --db talon-dev --setup-admin
    python -m talon_agents.live --server maincloud --db talon-prod --room HACK

What it does, in a loop:
  1. Picks up texts typed on the scammer phone (scammer_message, status "queued").
     No takeover yet -> a new text on the customer's phone, triaged by the engine.
     Takeover running -> the next scammer turn for the agents.
  2. Adopts takeovers the customer started from their phone (request_takeover reducer):
     Talon replies to the original scam text.
  3. Ends takeovers the customer stopped from their phone, with the impact card.
Every engine write is mirrored back through reducers (mirror.py), including each agent step.

Rooms: ROOM pairs the scammer phone with customer A. ROOM-2 is customer B, used by the
dashboard's "send to a second customer" button to show a burned campaign being blocked.
The engine needs an admin identity: --setup-admin creates one with the local CLI (the
publisher's identity must be the CLI's current login), or pass --token / SPACETIMEDB_TOKEN.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .config import Settings, load_dotenv
from .engine import TalonEngine
from .mirror import SpacetimeMirror
from .spacetime import SpacetimeClient, SpacetimeError, opt, some
from .state import DEFAULT_PERSONA

TOKENS = Path(__file__).resolve().parents[1] / ".spacetime-tokens.json"  # gitignored
SERVERS = {"maincloud": "https://maincloud.spacetimedb.com", "local": "http://127.0.0.1:4000"}

# Fictional demo customers. Numbers are in the 555-01xx fiction range.
CUSTOMERS = [
    {"id": "cust_demo_a", "display_name": "Alex (demo)", "phone": "+12145550123", "city": "Dallas", "state": "TX",
     "lat": some(32.7767), "lng": some(-96.7970)},
    {"id": "cust_demo_b", "display_name": "Sam (demo)", "phone": "+12145550124", "city": "Plano", "state": "TX",
     "lat": some(33.0198), "lng": some(-96.6989)},
]
SCAMMER_NUMBER = "+14695550182"


def q(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


class LiveRunner:
    def __init__(self, client: SpacetimeClient, engine: TalonEngine, room: str, log=print):
        self.c = client
        self.engine = engine
        self.room = room
        self.rooms = {room: CUSTOMERS[0]["id"], f"{room}-2": CUSTOMERS[1]["id"]}
        self.log = log
        self.mirror = SpacetimeMirror(client, engine.store, log=log)

    def setup(self) -> None:
        for cust in CUSTOMERS:
            self.c.call("upsert_customer", cust)
        p = DEFAULT_PERSONA
        self.c.call("upsert_persona", {"id": "persona_default", "name": p["name"], "age": p["age"], "city": p["city"],
                                       "state": p["state"], "backstory": p["backstory"], "quirks": p["quirks"],
                                       "source": "talon-default"})
        for code, customer in self.rooms.items():
            self.c.call("open_demo_room", code, customer, SCAMMER_NUMBER)

    # ------------------------------------------------------------------ loop

    def tick(self) -> bool:
        """One pass. Returns True if anything happened."""
        busy = False
        for code, customer in self.rooms.items():
            for m in sorted(self.c.sql(f"SELECT * FROM scammer_message WHERE room_code = {q(code)} "
                                       f"AND status = 'queued'"), key=lambda r: r["id"]):
                busy = True
                self._scammer_text(m, customer)
        for s in self.c.sql("SELECT * FROM session WHERE status = 'active'"):
            if s["id"] not in self.engine.sessions and self._known_message(s.get("inbound_message_id")):
                busy = True
                self._adopt(s)
        for s in self.c.sql("SELECT * FROM session WHERE status = 'stopped'"):
            local = self.engine.store.sessions.get(s["id"])
            if local and local["status"] == "active":
                busy = True
                self.log(f"[live] customer stopped {s['id']}")
                self.engine.stop_takeover(s["id"])
        return busy

    def _known_message(self, message_id: str | None) -> bool:
        return bool(message_id) and any(m["id"] == message_id for m in self.engine.store.inbound_messages)

    def _active_session_for(self, customer: str) -> str | None:
        for sid, st in self.engine.sessions.items():
            if st.customer_ref == customer and self.engine.store.sessions[sid]["status"] == "active":
                return sid
        return None

    def _scammer_text(self, m: dict, customer: str) -> None:
        self.c.call("set_scammer_message_status", m["id"], "processing", opt(None))
        try:
            sid = self._active_session_for(customer)
            if sid:
                self.log(f"[live] scammer -> {sid}: {m['text'][:80]}")
                reply = self.engine.handle_scammer_message(sid, m["text"])
                self.log(f"[live] talon -> scammer: {reply}")
            else:
                self.log(f"[live] new text for {customer}: {m['text'][:80]}")
                out = self.engine.receive_message(customer, SCAMMER_NUMBER, m["text"])
                self.log(f"[live] {out['message_id']}: {out['status']}")
            self.mirror.flush()
            self.c.call("set_scammer_message_status", m["id"], "done", opt(None))
        except Exception as e:  # noqa: BLE001 - one bad message shouldn't stop the demo
            self.log(f"[live] error on scammer message {m['id']}: {e!r}")
            self.c.call("set_scammer_message_status", m["id"], "error", opt(str(e)[:200]))

    def _adopt(self, s: dict) -> None:
        self.log(f"[live] customer handed {s['inbound_message_id']} to Talon as {s['id']}")
        try:
            self.c.call("assign_persona", s["id"], "persona_default")
            _, reply = self.engine.request_takeover(s["inbound_message_id"], session_id=s["id"], origin="phone")
            self.log(f"[live] talon -> scammer: {reply}")
        except Exception as e:  # noqa: BLE001
            self.log(f"[live] could not adopt {s['id']}: {e!r}")
        self.mirror.flush()

    def run(self, interval: float = 0.5) -> None:
        self.log(f"[live] room {self.room} ready. Scammer phone: /demo/scammer?room={self.room}  "
                 f"Customer phone: /demo/phone?room={self.room}  Dashboard: /demo/live?room={self.room}")
        while True:
            try:
                if not self.tick():
                    time.sleep(interval)
            except SpacetimeError as e:
                self.log(f"[live] database error: {e}; retrying")
                time.sleep(2)


# ---------------------------------------------------------------------- setup

def load_token(server: str, db: str) -> str | None:
    if TOKENS.exists():
        return json.loads(TOKENS.read_text(encoding="utf-8")).get(f"{server}|{db}")
    return None


def save_token(server: str, db: str, token: str) -> None:
    data = json.loads(TOKENS.read_text(encoding="utf-8")) if TOKENS.exists() else {}
    data[f"{server}|{db}"] = token
    TOKENS.write_text(json.dumps(data, indent=2), encoding="utf-8")


def setup_admin(server_arg: str, server: str, db: str) -> str:
    """Create an identity for the engine and make it admin using the CLI's (publisher's) login."""
    exe = shutil.which("spacetime")
    if not exe:
        sys.exit("--setup-admin needs the spacetime CLI on PATH")
    identity, token = SpacetimeClient.new_identity(server)
    r = subprocess.run([exe, "call", "-y", "--server", server_arg, db, "add_admin",
                        json.dumps({"__identity__": "0x" + identity})], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        sys.exit(f"add_admin failed (is your CLI login an admin of {db}?):\n{r.stderr or r.stdout}")
    save_token(server, db, token)
    print(f"[live] engine identity {identity[:12]}... is now an admin of {db}; token saved to {TOKENS.name}")
    return token


def main() -> int:
    load_dotenv()  # repo-root .env: SPACETIMEDB_HOST, SPACETIMEDB_DB_NAME, SPACETIMEDB_TOKEN, NEMOTRON_*
    ap = argparse.ArgumentParser(description="Run Talon's engine against SpacetimeDB for the live demo.")
    ap.add_argument("--server", default=os.environ.get("SPACETIMEDB_HOST") or "local",
                    help="local, maincloud, or a URL (default: SPACETIMEDB_HOST)")
    ap.add_argument("--db", default=os.environ.get("SPACETIMEDB_DB_NAME") or "talon-dev",
                    help="database name (default: SPACETIMEDB_DB_NAME)")
    ap.add_argument("--room", help="room code (letters/digits); random if omitted")
    ap.add_argument("--token", default=os.environ.get("SPACETIMEDB_TOKEN"))
    ap.add_argument("--setup-admin", action="store_true", help="create and authorize an engine identity via the CLI")
    ap.add_argument("--reset", action="store_true", help="clear runtime tables first (reset_runtime)")
    ap.add_argument("--fake", action="store_true", help="use FakeLLM instead of Nemotron")
    args = ap.parse_args()

    server = SERVERS.get(args.server, args.server)
    # .env files often hold the WebSocket form (ws://localhost:4000); the HTTP API is the same host.
    server = server.replace("wss://", "https://", 1).replace("ws://", "http://", 1).rstrip("/")
    if server in ("http://localhost:4000",):
        server = "http://127.0.0.1:4000"
    token = args.token or load_token(server, args.db)
    if args.setup_admin or not token:
        if not args.setup_admin:
            sys.exit("No admin token. Pass --token, set SPACETIMEDB_TOKEN, or use --setup-admin (local publisher).")
        token = setup_admin("maincloud" if args.server == "maincloud" else server, server, args.db)

    room = (args.room or secrets.token_hex(2)).upper()
    if not re.fullmatch(r"[A-Z0-9]{2,8}", room):
        sys.exit("room code must be 2-8 letters or digits")

    settings = Settings.from_env()
    if args.fake:
        settings.api_key = None
    engine = TalonEngine(settings=settings)
    print(f"[live] model: {'FakeLLM' if settings.use_fake else settings.model_for('handler')}  db: {server} {args.db}")
    client = SpacetimeClient(server, args.db, token)
    if args.reset:
        client.call("reset_runtime")
    runner = LiveRunner(client, engine, room)
    runner.setup()
    try:
        runner.run()
    except KeyboardInterrupt:
        runner.mirror.flush()
        print("\n[live] stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
