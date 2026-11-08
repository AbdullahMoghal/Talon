"""Validate a Talon messages JSONL file against DATA_SPEC.md.

Checks the record schema, taxonomy labels, that every indicator appears
word for word in the text, and the safety rules for fictional indicators:
reserved-TLD domains only, 555-0100..0199 phone numbers only, and wallet
and routing numbers whose checksums are deliberately invalid.

Usage:
    python3 scripts/data/validate.py data/gold_test.jsonl
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY = ROOT / "data" / "taxonomy.json"

RESERVED_TLDS = {"example", "test", "invalid"}
SENDER_TYPES = {"long_code", "short_code", "email_gateway", "toll_free"}
TACTICS = {"urgency", "authority", "fear", "reward", "secrecy", "familiarity"}
DIFFICULTIES = {"easy", "medium", "hard"}
SPLITS = {"train", "val", "test", "gold", "live"}
AGE_BANDS = {"18-34", "35-54", "55+"}
REQUIRED = {
    "id": str, "text": str, "label": str, "category": (str, type(None)),
    "legit_subtype": (str, type(None)), "campaign_id": (str, type(None)),
    "sender": str, "sender_type": str, "brand": (str, type(None)),
    "hook": (str, type(None)), "tactics": list, "indicators": list,
    "difficulty": str, "target_profile": dict, "season": (str, type(None)),
    "generator": str, "split": str,
}

DOMAIN_RE = re.compile(
    r"(?<![@\w.-])(?:https?://)?((?:[a-z0-9-]+\.)+([a-z]{2,}))(?=[/\s?#:)\],!]|\.(?:\s|$)|$)",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[\w.+-]+@((?:[\w-]+\.)+([a-z]{2,}))", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?(\d{3})\)?[\s.-]?(\d{3})[\s.-]?(\d{4})(?!\d)")
BECH32_RE = re.compile(r"\bbc1[qpzry9x8gf2tvdw0s3jn54khce6mua7l]{25,62}\b")
TRON_RE = re.compile(r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b")
ROUTING_RE = re.compile(r"(?:rtg|routing)\s*#?:?\s*(\d{9})\b", re.IGNORECASE)
BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def bech32_valid(addr: str) -> bool:
    hrp, data = addr[:2], addr[3:]
    values = [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]
    values += [BECH32_CHARSET.index(c) for c in data]
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in values:
        top = chk >> 25
        chk = (chk & 0x1FFFFFF) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if (top >> i) & 1 else 0
    return chk in (1, 0x2BC830A3)  # bech32 or bech32m


def base58check_valid(addr: str) -> bool:
    n = 0
    for c in addr:
        n = n * 58 + B58.index(c)
    raw = n.to_bytes(25, "big") if n.bit_length() <= 200 else b""
    if len(raw) != 25:
        return False
    payload, checksum = raw[:-4], raw[-4:]
    return hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4] == checksum


def aba_valid(num: str) -> bool:
    d = [int(c) for c in num]
    return (3 * (d[0] + d[3] + d[6]) + 7 * (d[1] + d[4] + d[7]) + (d[2] + d[5] + d[8])) % 10 == 0


def safety_errors(text: str) -> list[str]:
    errs = []
    for m in EMAIL_RE.finditer(text):
        if m.group(2).lower() not in RESERVED_TLDS:
            errs.append(f"email domain not reserved: {m.group(0)}")
    for m in DOMAIN_RE.finditer(text):
        if m.group(2).lower() not in RESERVED_TLDS:
            errs.append(f"domain not reserved: {m.group(1)}")
    for m in PHONE_RE.finditer(text):
        exch, line = m.group(2), int(m.group(3))
        if exch != "555" or not 100 <= line <= 199:
            errs.append(f"phone not in 555-0100..0199: {m.group(0).strip()}")
    for m in BECH32_RE.finditer(text):
        if bech32_valid(m.group(0)):
            errs.append(f"wallet has a valid checksum: {m.group(0)}")
    for m in TRON_RE.finditer(text):
        if base58check_valid(m.group(0)):
            errs.append(f"wallet has a valid checksum: {m.group(0)}")
    for m in ROUTING_RE.finditer(text):
        if aba_valid(m.group(1)):
            errs.append(f"routing number has a valid checksum: {m.group(1)}")
    return errs


def validate(path: Path) -> int:
    tax = json.loads(TAXONOMY.read_text())
    categories = {c["id"] for c in tax["categories"]}
    subtypes = {s["id"] for s in tax["legit_subtypes"]}
    ind_types = set(tax["indicator_types"])

    errors, seen = [], set()
    records = []
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        where = f"line {lineno}"
        try:
            r = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"{where}: invalid JSON ({e})")
            continue
        records.append(r)
        where = f"line {lineno} ({r.get('id')})"
        e = lambda msg: errors.append(f"{where}: {msg}")

        for field, typ in REQUIRED.items():
            if field not in r:
                e(f"missing field {field}")
            elif not isinstance(r[field], typ):
                e(f"{field} has wrong type")
        if errors and errors[-1].startswith(where) and "missing" in errors[-1]:
            continue

        if r["id"] in seen:
            e("duplicate id")
        seen.add(r["id"])

        if r["label"] == "scam":
            if r["category"] not in categories:
                e(f"unknown category {r['category']}")
            if r["legit_subtype"] is not None:
                e("scam record has legit_subtype")
        elif r["label"] == "legit":
            if r["legit_subtype"] not in subtypes:
                e(f"unknown legit_subtype {r['legit_subtype']}")
            if r["category"] is not None or r["campaign_id"] is not None:
                e("legit record has category or campaign_id")
        else:
            e(f"bad label {r['label']}")

        if r["sender_type"] not in SENDER_TYPES:
            e(f"bad sender_type {r['sender_type']}")
        if not set(r["tactics"]) <= TACTICS:
            e(f"bad tactics {set(r['tactics']) - TACTICS}")
        if r["difficulty"] not in DIFFICULTIES:
            e(f"bad difficulty {r['difficulty']}")
        if r["split"] not in SPLITS:
            e(f"bad split {r['split']}")
        if r["target_profile"].get("age_band") not in AGE_BANDS:
            e("bad target_profile.age_band")
        if r["brand"] and r["brand"] not in r["text"]:
            e(f"brand not in text: {r['brand']}")

        for ind in r["indicators"]:
            if ind.get("type") not in ind_types:
                e(f"bad indicator type {ind.get('type')}")
            if ind.get("value") not in r["text"]:
                e(f"indicator not in text: {ind.get('value')}")

        for msg in safety_errors(r["text"]) + safety_errors(r["sender"]):
            e(msg)

    for msg in errors:
        print("ERROR", msg)

    labels = Counter(r.get("label") for r in records)
    print(f"\n{len(records)} records, {len(errors)} errors")
    print("labels:", dict(labels))
    print("scam categories:", dict(Counter(r.get("category") for r in records if r.get("label") == "scam")))
    print("legit subtypes:", dict(Counter(r.get("legit_subtype") for r in records if r.get("label") == "legit")))
    print("difficulty by label:", dict(Counter((r.get("label"), r.get("difficulty")) for r in records)))
    return 1 if errors else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    sys.exit(validate(parser.parse_args().path))
