"""End-to-end check of the live demo loop: plays both phones against a running `talon_agents.live`.

    python -m talon_agents.live_e2e --server http://127.0.0.1:4000 --db talon-dev --room DEMO

Phones are plain (non-admin) identities, like the real web pages. Uses only reducers
the pages use: scammer_send, request_takeover, stop_takeover.
"""

from __future__ import annotations

import argparse
import sys
import time

from .cli import DEMO_OPENER, DEMO_TURNS, SECOND_CUSTOMER_TEXT
from .live import room_customers
from .spacetime import SpacetimeClient


def wait_for(fn, what: str, timeout: float = 180):
    end = time.time() + timeout
    while time.time() < end:
        out = fn()
        if out:
            return out
        time.sleep(0.3)
    sys.exit(f"FAIL: timed out waiting for {what}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="http://127.0.0.1:4000")
    ap.add_argument("--db", default="talon-dev")
    ap.add_argument("--room", default="DEMO")
    args = ap.parse_args()
    _, token = SpacetimeClient.new_identity(args.server)
    phone = SpacetimeClient(args.server, args.db, token)  # not an admin
    room, room2 = args.room, f"{args.room}-2"
    cust_a, cust_b = (c["id"] for c in room_customers(room))

    def talon_turns(sid):
        return [t for t in phone.sql(f"SELECT * FROM turn WHERE session_id = '{sid}'") if t["sender"] == "talon"]

    print("1. scammer texts the customer")
    phone.call("scammer_send", room, DEMO_OPENER)
    msg = wait_for(lambda: [m for m in phone.sql(f"SELECT * FROM inbound_message WHERE customer_id = '{cust_a}'")
                            if m["status"] == "warned"], "triage warning")[-1]
    print(f"   warned: {msg['category']} {msg['confidence']:.2f} - {msg['reason'][:70]}")
    steps = phone.sql(f"SELECT * FROM agent_step WHERE session_id = '{msg['id']}'")
    print(f"   triage trace steps: {[s['kind'] for s in steps]}")

    print("2. customer taps 'Let Talon handle it'")
    sid = "ses_e2e_" + str(int(time.time()))
    phone.call("request_takeover", msg["id"], sid)
    first = wait_for(lambda: talon_turns(sid), "Talon's first reply")
    print(f"   talon: {first[-1]['text']}")

    print("3. scammer keeps going")
    for i, text in enumerate(DEMO_TURNS[:5], start=2):
        time.sleep(0.8)  # scammer_send is rate limited per room
        phone.call("scammer_send", room, text)
        got = wait_for(lambda: (lambda ts: ts if len(ts) >= i else None)(talon_turns(sid)), f"reply {i}")
        got.sort(key=lambda t: t["ts"])
        print(f"   scammer: {text[:50]}...\n   talon:   {got[-1]['text'][:90]}")

    inds = phone.sql(f"SELECT * FROM indicator WHERE session_id = '{sid}'")
    plans = phone.sql(f"SELECT * FROM handler_plan WHERE session_id = '{sid}'")
    steps = phone.sql(f"SELECT * FROM agent_step WHERE session_id = '{sid}'")
    camps = phone.sql("SELECT * FROM campaign")
    print(f"   indicators: {sorted({i['kind'] for i in inds})}")
    print(f"   handler plans: {len(plans)}, agent steps: {len(steps)} from {sorted({s['agent'] for s in steps})}")
    print(f"   campaigns: {[(c['id'], c['status']) for c in camps]}")

    print("4. same scam reaches a second customer")
    time.sleep(0.8)
    phone.call("scammer_send", room2, SECOND_CUSTOMER_TEXT)
    second = wait_for(lambda: [m for m in phone.sql(f"SELECT * FROM inbound_message WHERE customer_id = '{cust_b}'")
                               if m["status"] in ("blocked", "warned", "delivered")], "second customer's message")[-1]
    print(f"   second customer: {second['status']}")

    print("5. customer taps Stop")
    phone.call("stop_takeover", sid)
    card = wait_for(lambda: phone.sql(f"SELECT * FROM impact_card WHERE session_id = '{sid}'"), "impact card")[0]
    print(f"   impact card: {card['summary'][:120]}")
    session = phone.sql(f"SELECT * FROM session WHERE id = '{sid}'")[0]
    print(f"   session status: {session['status']}, turns: {session['turn_count']}")

    errors = [m for m in phone.sql("SELECT * FROM scammer_message") if m["status"] == "error"]
    if errors:
        sys.exit(f"FAIL: scammer messages errored: {[(m['id'], m['error']) for m in errors]}")
    if second["status"] != "blocked":
        sys.exit(f"FAIL: second customer was {second['status']}, expected blocked")
    print("\nPASS: live loop works end to end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
