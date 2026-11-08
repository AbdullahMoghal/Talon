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

    # Start from a clean room: earlier runs may have blocked this scammer number for this customer.
    phone.call("reset_room", room)
    time.sleep(3)  # the runner notices the reset, starts a fresh engine and assigns new numbers

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

    def session():
        return phone.sql(f"SELECT * FROM session WHERE id = '{sid}'")[0]

    print("3. scammer keeps going until Talon ends it")
    for i, text in enumerate(DEMO_TURNS, start=2):
        if session()["status"] != "active":
            break
        time.sleep(0.8)  # scammer_send is rate limited per room
        phone.call("scammer_send", room, text)
        got = wait_for(lambda: (lambda ts: ts if len(ts) >= i or session()["status"] != "active" else None)(
            talon_turns(sid)), f"reply {i}")
        got.sort(key=lambda t: t["ts"])
        print(f"   scammer: {text[:50]}...\n   talon:   {got[-1]['text'][:90] if len(got) >= i else '(Talon ended it)'}")

    s = wait_for(lambda: [x for x in [session()] if x["status"] != "active"], "Talon to end the takeover itself")[0]
    card = wait_for(lambda: phone.sql(f"SELECT * FROM impact_card WHERE session_id = '{sid}'"), "impact card")[0]
    inds = sorted(phone.sql(f"SELECT * FROM indicator WHERE session_id = '{sid}'"), key=lambda i: i["id"])
    steps = phone.sql(f"SELECT * FROM agent_step WHERE session_id = '{sid}'")
    camps = phone.sql("SELECT * FROM campaign")
    print(f"   Talon ended it: {s['status']} after {s['turn_count']} turns, no Stop tapped")
    print(f"   impact card: {card['summary'][:140]}")
    print(f"   intel: {[i['kind'] for i in inds]} (first: {inds[0]['kind']} {inds[0]['value']})")
    print(f"   agent steps: {len(steps)} from {sorted({x['agent'] for x in steps})}; campaigns: {[c['status'] for c in camps]}")

    print("4. the scammer texts again, then hits a second customer")
    time.sleep(0.8)
    phone.call("scammer_send", room, "hello? you still there")
    again = wait_for(lambda: [m for m in phone.sql(f"SELECT * FROM inbound_message WHERE customer_id = '{cust_a}'")
                              if m["status"] == "blocked"], "follow-up blocked")[-1]
    print(f"   follow-up to the same customer: {again['status']}")
    time.sleep(0.8)
    phone.call("scammer_send", room2, SECOND_CUSTOMER_TEXT)
    # The runner also texts the second customer on its own (second_customer.py); wait for this text specifically.
    second = wait_for(lambda: [m for m in phone.sql(f"SELECT * FROM inbound_message WHERE customer_id = '{cust_b}'")
                               if m["text"] == SECOND_CUSTOMER_TEXT
                               and m["status"] in ("blocked", "warned", "delivered")], "second customer's message")[-1]
    auto = [m for m in phone.sql(f"SELECT * FROM inbound_message WHERE customer_id = '{cust_b}'")
            if m["text"] != SECOND_CUSTOMER_TEXT]
    print(f"   second customer: {second['status']} (plus {len(auto)} sent automatically: "
          f"{[m['status'] for m in auto]})")
    entry = [r for r in phone.sql("SELECT * FROM scam_catalog") if r["number"] == inds[0]["value"]]
    print(f"   catalog: {entry[0]['status'] if entry else 'MISSING'}, {len(entry[0]['intel']) if entry else 0} details")

    if s["status"] != "completed" or inds[0]["kind"] != "sender_number" or not entry:
        sys.exit("FAIL: expected an automatic end, the sender number first, and a catalog entry")

    errors = [m for m in phone.sql("SELECT * FROM scammer_message") if m["status"] == "error"]
    if errors:
        sys.exit(f"FAIL: scammer messages errored: {[(m['id'], m['error']) for m in errors]}")
    if second["status"] != "blocked":
        sys.exit(f"FAIL: second customer was {second['status']}, expected blocked")
    print("\nPASS: live loop works end to end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
