"""Run one full "Let Talon handle it" takeover against a Talon SpacetimeDB database.

Exercises every runtime reducer in order, with fictional data:
scam text -> triage -> customer taps "Let Talon handle it" -> handler plan ->
Talon replies -> indicators -> campaign burns -> second customer blocked ->
insight -> impact card, with estimated origins for the map. Then checks the guards: Talon can't reply after the
session ends or with a reply that failed the safety guard.

Clears runtime tables first (reset_runtime), so don't run it during a live demo.
Leaves the rows in place so the dashboard has something to show.

Usage:
    python3 scripts/demo/takeover_smoke.py --server http://127.0.0.1:4000 --db talon-dev
"""

import argparse
import json
import shutil
import subprocess
import sys

NONE = {"none": []}


def some(v):
    return {"some": v}


def opt(v):
    return NONE if v is None else some(v)


def origin(city, state, lat, lng, source, confidence, country="US"):
    return {"city": opt(city), "state": opt(state), "country": opt(country),
            "lat": lat, "lng": lng, "source": source, "confidence": confidence}


class Db:
    def __init__(self, server, db):
        self.server, self.db = server, db

    def call(self, reducer, *args, anonymous=False, expect_error=None):
        cmd = ["spacetime", "call", "-y", "--server", self.server]
        if anonymous:
            cmd.append("--anonymous")
        cmd += [self.db, reducer, *(json.dumps(a) for a in args)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        out = (r.stderr or "") + (r.stdout or "")
        if expect_error:
            if r.returncode == 0 or expect_error not in out:
                sys.exit(f"FAIL {reducer}: expected error containing {expect_error!r}, got:\n{out}")
            print(f"  ok  {reducer} rejected: {expect_error}")
            return
        if r.returncode != 0:
            sys.exit(f"FAIL {reducer}:\n{out}")
        print(f"  ok  {reducer}")

    def sql(self, query):
        r = subprocess.run(["spacetime", "sql", "--server", self.server, self.db, query],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            sys.exit(f"FAIL sql {query}:\n{r.stderr}")
        rows = [line for line in r.stdout.splitlines() if line.strip() and not line.startswith("WARNING")]
        return [line.split("|") for line in rows[2:]]  # skip header and divider

    def count(self, table):
        return int(self.sql(f"SELECT COUNT(*) AS n FROM {table}")[0][0])


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--server", default="http://127.0.0.1:4000")
    p.add_argument("--db", default="talon-dev")
    args = p.parse_args()
    if not shutil.which("spacetime"):
        sys.exit("spacetime CLI not found on PATH")
    db = Db(args.server, args.db)

    print("setup")
    db.call("reset_runtime")
    db.call("upsert_persona", {
        "id": "p_dorothy", "name": "Dorothy Ellis", "age": 71, "city": "Garland", "state": "TX",
        "backstory": "Retired school librarian, slow with technology, very polite.",
        "quirks": ["asks the same question twice", "mentions her cat Biscuit"],
        "source": "nemotron-personas-usa",
    })
    db.call("upsert_customer", {"id": "cust_maria", "display_name": "Maria", "phone": "+12145550101",
                                "city": "Dallas", "state": "TX", "lat": some(32.7767), "lng": some(-96.7970)})
    db.call("upsert_customer", {"id": "cust_james", "display_name": "James", "phone": "+12145550102",
                                "city": "Plano", "state": "TX", "lat": some(33.0198), "lng": some(-96.6989)})

    print("scam arrives and is triaged")
    scam = ("NTTA: You have an unpaid toll balance of $6.85. To avoid a late fee of $50, "
            "pay by 11/12: ntta-tollpay.example/tx")
    db.call("receive_message", "msg_1", "cust_maria", "+14695550144", "sms", scam)
    db.call("set_triage", "msg_1", "scam", some("toll_fee"), 0.92,
            "Fake NTTA toll notice. Real tolls never ask for payment by text.")
    # Estimated origin for the map. Area codes are spoofable, so confidence is low.
    db.call("set_message_origin", "msg_1", origin("Dallas", "TX", 32.7767, -96.7970, "area_code", 0.3))
    db.call("set_message_origin", "msg_1", origin("Nowhere", "XX", 123.0, 0.0, "area_code", 0.3),
            expect_error="out of range")

    print("customer taps 'Let Talon handle it' (from the phone app, no admin rights)")
    db.call("request_takeover", "msg_1", "sess_1", anonymous=True)
    db.call("request_takeover", "msg_1", "sess_dup", anonymous=True, expect_error="already handling")
    db.call("assign_persona", "sess_1", "p_dorothy")

    print("conversation")
    db.call("add_turn", "t1", "sess_1", "scammer", scam, some("scam"), some(0.92), True)
    db.call("add_handler_plan", "sess_1", some("t1"), ["url"], "payment method", "payment_trouble",
            "We have their link. Say the card was declined to get another way to pay.")
    db.call("add_turn", "t2", "sess_1", "talon",
            "Oh dear, I tried that link but my card was declined. Is there another way I can pay?",
            NONE, NONE, True)
    db.call("add_turn", "t3", "sess_1", "scammer",
            "No problem ma'am. Send it by Zelle to tollpay.desk@ntta-billing.example or call 972-555-0158.",
            NONE, NONE, True)
    db.call("add_turn", "t_bad", "sess_1", "talon", "unsafe reply", NONE, NONE, False,
            expect_error="safety guard")

    print("extraction and campaign")
    db.call("add_indicator", "sess_1", "t1", "url", "ntta-tollpay.example/tx", 0.97)
    db.call("add_indicator", "sess_1", "t3", "email", "tollpay.desk@ntta-billing.example", 0.95)
    db.call("add_indicator", "sess_1", "t3", "phone", "972-555-0158", 0.93)
    db.call("upsert_campaign", "cmp_ntta", "toll_fee", "Fake NTTA unpaid toll", some("NTTA"), 3412)
    db.call("link_session", "sess_1", "cmp_ntta")
    db.call("issue_tripwire", "tw_1", "cmp_ntta", "sess_1", "account", "TW-ZELLE-0001")
    db.call("burn_campaign", "cmp_ntta")

    print("second customer is protected")
    db.call("receive_message", "msg_2", "cust_james", "+19725550133", "sms",
            "NTTA TollTag: Final notice. Outstanding toll $6.85. ntta-tollpay.example/hold")
    db.call("set_message_origin", "msg_2", origin("Dallas", "TX", 32.7767, -96.7970, "area_code", 0.3))
    db.call("add_customer_alert", "cmp_ntta", "cust_james", some("msg_2"), "blocked",
            "Talon shut this campaign down 40 seconds ago, thanks to a customer in Dallas.")

    ids = [int(r[0]) for r in db.sql("SELECT id FROM indicator")]
    db.call("add_insight", "ins_1", "cmp_ntta", "summary",
            "Fake NTTA toll texts moved victims from a link to Zelle when card payment failed.", ids, 0.8)
    db.call("add_insight", "ins_bad", "cmp_ntta", "summary", "cites nothing real", [999999], 0.5,
            expect_error="unknown indicator")
    db.call("hit_tripwire", "TW-ZELLE-0001", "Mock bank: transfer attempted to watched account")

    print("impact card ends the takeover")
    db.call("add_impact_card", "sess_1", some("cmp_ntta"), 3412,
            "The scammer who texted you was running a toll scam that hit 3,412 T-Mobile customers. "
            "You helped shut it down.")
    db.call("add_turn", "t_late", "sess_1", "talon", "one more thing", NONE, NONE, True,
            expect_error="can't reply")

    print("customer can stop a takeover at any time")
    db.call("receive_message", "msg_3", "cust_james", "+18885550193", "sms",
            "Amazon: Your order of an iPhone 17 Pro has been placed. Not you? Call 1-888-555-0193.")
    db.call("set_message_origin", "msg_3", origin(None, None, 25.7617, -80.1918, "network", 0.6, country="US"))
    db.call("request_takeover", "msg_3", "sess_2", anonymous=True)
    db.call("stop_takeover", "sess_2", anonymous=True)
    db.call("add_turn", "t_stopped", "sess_2", "talon", "hello?", NONE, NONE, True, expect_error="can't reply")

    print("checks")
    checks = {
        "SELECT status FROM inbound_message WHERE id = 'msg_1'": '"taken_over"',
        "SELECT status FROM inbound_message WHERE id = 'msg_2'": '"blocked"',
        "SELECT status FROM session WHERE id = 'sess_1'": '"completed"',
        "SELECT status FROM session WHERE id = 'sess_2'": '"stopped"',
        "SELECT turn_count FROM session WHERE id = 'sess_1'": "3",
        "SELECT status FROM campaign WHERE id = 'cmp_ntta'": '"burned"',
        "SELECT origin_source FROM session WHERE id = 'sess_1'": '(some = "area_code")',
        "SELECT origin_lat FROM session WHERE id = 'sess_2'": "(some = 25.7617)",
    }
    for query, want in checks.items():
        got = db.sql(query)[0][0].strip()
        if got != want:
            sys.exit(f"FAIL {query}: got {got}, want {want}")
        print(f"  ok  {query} -> {got}")
    for table, want in [("indicator", 3), ("impact_card", 1), ("customer_alert", 1), ("insight", 1)]:
        got = db.count(table)
        if got != want:
            sys.exit(f"FAIL {table}: {got} rows, want {want}")
        print(f"  ok  {table}: {got} rows")
    print("\nAll takeover checks passed.")


if __name__ == "__main__":
    main()
