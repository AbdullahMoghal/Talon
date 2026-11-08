"""Seed talon-prod (or local) with enough fictional origin + customer rows for the heatmap.

Clears runtime tables first (reset_runtime), then writes ~100 inbound messages with
origins across US metros, a few campaigns (active + burned), customers with lat/lng,
and a handful of sessions/indicators so the hotspot drawer has something to show.

Usage:
    python3 scripts/demo/seed_map_demo.py --server maincloud --db talon-prod
    python3 scripts/demo/seed_map_demo.py --server http://127.0.0.1:4000 --db talon-dev
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys

NONE = {"none": []}


def some(v):
    return {"some": v}


def opt(v):
    return NONE if v is None else some(v)


def origin(city, state, lat, lng, source, confidence, country="US"):
    return {
        "city": opt(city),
        "state": opt(state),
        "country": opt(country),
        "lat": lat,
        "lng": lng,
        "source": source,
        "confidence": confidence,
    }


# City hubs: (city, state, lat, lng) — jitter applied per point
HUBS = [
    ("Dallas", "TX", 32.7767, -96.7970),
    ("Houston", "TX", 29.7604, -95.3698),
    ("Austin", "TX", 30.2672, -97.7431),
    ("Los Angeles", "CA", 34.0522, -118.2437),
    ("San Francisco", "CA", 37.7749, -122.4194),
    ("San Diego", "CA", 32.7157, -117.1611),
    ("Miami", "FL", 25.7617, -80.1918),
    ("Orlando", "FL", 28.5383, -81.3792),
    ("New York", "NY", 40.7128, -74.0060),
    ("Buffalo", "NY", 42.8864, -78.8784),
    ("Chicago", "IL", 41.8781, -87.6298),
    ("Atlanta", "GA", 33.7490, -84.3880),
    ("Seattle", "WA", 47.6062, -122.3321),
    ("Charlotte", "NC", 35.2271, -80.8431),
    ("Phoenix", "AZ", 33.4484, -112.0740),
]

CATEGORIES = [
    ("toll_fee", "Unpaid toll scam"),
    ("package_delivery", "Fake delivery hold"),
    ("bank_fraud_alert", "Bank fraud alert"),
    ("carrier_impersonation", "Carrier / SIM swap"),
    ("account_security", "Account lockout"),
    ("health_insurance", "Medicare / insurance"),
    ("investment_crypto", "Crypto investment"),
    ("job_task", "Job / task scam"),
]

SOURCES = [
    ("area_code", 0.25, 0.4),
    ("network", 0.5, 0.7),
    ("text", 0.35, 0.55),
    ("reported", 0.8, 0.95),
]

TEXTS = {
    "toll_fee": "NTTA: Unpaid toll ${amt}. Pay now: ntta-tollpay.example/{slug}",
    "package_delivery": "USPS: Package held. Confirm address: usps-help.example/{slug}",
    "bank_fraud_alert": "ALERT: Unusual charge of ${amt}. Call {phone} if this wasn't you.",
    "carrier_impersonation": "T-Mobile: SIM change requested. Not you? Call {phone}",
    "account_security": "Your account was locked. Verify at secure-login.example/{slug}",
    "health_insurance": "Medicare: Benefits update required. Reply YES or visit med-upd.example/{slug}",
    "investment_crypto": "Limited crypto allotment. Wallet setup: crypto-desk.example/{slug}",
    "job_task": "Paid task available today (${amt}). Start: task-pay.example/{slug}",
}


class Db:
    def __init__(self, server, db):
        self.server, self.db = server, db

    def call(self, reducer, *args, anonymous=False):
        cmd = ["spacetime", "call", "-y", "--server", self.server]
        if anonymous:
            cmd.append("--anonymous")
        cmd += [self.db, reducer, *(json.dumps(a) for a in args)]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            out = (r.stderr or "") + (r.stdout or "")
            sys.exit(f"FAIL {reducer}:\n{out}")

    def sql(self, query):
        r = subprocess.run(
            ["spacetime", "sql", "--server", self.server, self.db, query],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if r.returncode != 0:
            sys.exit(f"FAIL sql {query}:\n{r.stderr}")
        rows = [
            line
            for line in r.stdout.splitlines()
            if line.strip() and not line.startswith("WARNING")
        ]
        return [line.split("|") for line in rows[2:]]

    def count(self, table):
        return int(self.sql(f"SELECT COUNT(*) AS n FROM {table}")[0][0])


def jitter(lat, lng, rng, scale=0.35):
    # ~tens of km of jitter so hubs form visible heat clusters
    return lat + rng.uniform(-scale, scale), lng + rng.uniform(-scale, scale)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--server", default="maincloud")
    p.add_argument("--db", default="talon-prod")
    p.add_argument("--messages", type=int, default=100, help="inbound messages with origins")
    p.add_argument("--customers", type=int, default=36, help="customers with lat/lng")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    if not shutil.which("spacetime"):
        sys.exit("spacetime CLI not found on PATH")

    rng = random.Random(args.seed)
    db = Db(args.server, args.db)

    print(f"seeding {args.db} on {args.server}")
    print("reset_runtime")
    db.call("reset_runtime")

    print("persona")
    db.call(
        "upsert_persona",
        {
            "id": "p_map_demo",
            "name": "Dorothy Ellis",
            "age": 71,
            "city": "Garland",
            "state": "TX",
            "backstory": "Retired librarian used for map demo takeovers.",
            "quirks": ["asks twice", "mentions her cat"],
            "source": "demo",
        },
    )

    print(f"customers ({args.customers})")
    for i in range(args.customers):
        city, state, lat, lng = HUBS[i % len(HUBS)]
        jlat, jlng = jitter(lat, lng, rng, 0.2)
        db.call(
            "upsert_customer",
            {
                "id": f"cust_map_{i:03d}",
                "display_name": f"Customer {i + 1}",
                "phone": f"+1214555{1000 + i:04d}",
                "city": city,
                "state": state,
                "lat": some(round(jlat, 4)),
                "lng": some(round(jlng, 4)),
            },
        )

    # Three campaigns: two burned, one active
    campaigns = [
        ("cmp_map_toll", "toll_fee", "Fake NTTA unpaid toll", "NTTA", "burned", 3412),
        ("cmp_map_pkg", "package_delivery", "Fake USPS hold", "USPS", "burned", 890),
        ("cmp_map_bank", "bank_fraud_alert", "Fake bank fraud ring", "Chase", "active", 512),
    ]
    print("campaigns")
    for cid, cat, label, brand, status, hits in campaigns:
        db.call(
            "upsert_campaign",
            cid,
            cat,
            label,
            some(brand),
            hits,
        )
        if status == "burned":
            db.call("burn_campaign", cid)

    print(f"inbound messages + origins ({args.messages})")
    for i in range(args.messages):
        city, state, lat, lng = HUBS[i % len(HUBS)]
        jlat, jlng = jitter(lat, lng, rng)
        cat, _ = CATEGORIES[i % len(CATEGORIES)]
        source, c_lo, c_hi = SOURCES[i % len(SOURCES)]
        conf = round(rng.uniform(c_lo, c_hi), 2)
        cust_id = f"cust_map_{(i % args.customers):03d}"
        msg_id = f"msg_map_{i:03d}"
        phone = f"+1{rng.randint(200, 999)}555{rng.randint(1000, 9999)}"
        amt = rng.choice([6.85, 12.40, 49.99, 128.00])
        slug = f"{state.lower()}{i}"
        text = TEXTS[cat].format(amt=amt, slug=slug, phone=phone)
        sender = f"+1{rng.randint(200, 999)}555{rng.randint(1000, 9999)}"

        db.call("receive_message", msg_id, cust_id, sender, "sms", text)
        db.call(
            "set_triage",
            msg_id,
            "scam",
            some(cat),
            round(rng.uniform(0.82, 0.98), 2),
            f"Synthetic {cat} for map demo.",
        )
        db.call(
            "set_message_origin",
            msg_id,
            origin(city, state, round(jlat, 4), round(jlng, 4), source, conf),
        )

        # Take over every 4th message so the drawer has campaigns + indicators
        if i % 4 == 0:
            cmp_id = campaigns[i % len(campaigns)][0]
            sess_id = f"sess_map_{i:03d}"
            turn_id = f"t_map_{i}"
            db.call("request_takeover", msg_id, sess_id, anonymous=True)
            db.call("assign_persona", sess_id, "p_map_demo")
            db.call("link_session", sess_id, cmp_id)
            db.call(
                "add_turn",
                turn_id,
                sess_id,
                "scammer",
                f"Follow-up for {cat} demo.",
                some("scam"),
                some(0.9),
                True,
            )
            db.call(
                "add_indicator",
                sess_id,
                turn_id,
                rng.choice(["url", "phone", "wallet", "email"]),
                f"{cat}-pay.example/{i}",
                0.94,
            )

    print("counts")
    for table in (
        "inbound_message",
        "session",
        "customer",
        "campaign",
        "indicator",
    ):
        print(f"  {table}: {db.count(table)}")
    print("done — open /heatmap against talon-prod")


if __name__ == "__main__":
    main()
