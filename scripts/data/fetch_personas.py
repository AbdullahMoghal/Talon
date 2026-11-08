"""Build data/personas.jsonl from NVIDIA's Nemotron-Personas-USA (CC BY 4.0).

    python scripts/data/fetch_personas.py            # 40 personas, aged 60+, one per state where possible
    python scripts/data/fetch_personas.py --count 60 --min-age 55

Talon speaks to scammers as one of these synthetic people, never as a real customer. The source
dataset is synthetic (no real people); we still keep first names only and drop any persona whose
text looks like it contains a phone number, email address or link. Pages are read from the public
Hugging Face datasets-server API at fixed pseudo-random offsets, so runs are reproducible.

Source: https://huggingface.co/datasets/nvidia/Nemotron-Personas-USA (NVIDIA, CC BY 4.0).
"""

from __future__ import annotations

import argparse
import ast
import json
import random
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "personas.jsonl"
API = "https://datasets-server.huggingface.co/rows?dataset=nvidia/Nemotron-Personas-USA&config=default&split=train"
TOTAL_ROWS = 1_000_000
UNSAFE = re.compile(r"https?://|www\.|@[\w-]+\.\w|\b\d{3}[\s.-]?\d{3}[\s.-]?\d{4}\b")

OCCUPATION_WORDS = {"or": "/", "and": "&"}


def fetch_page(offset: int) -> list[dict]:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(f"{API}&offset={offset}&length=100", timeout=30) as r:
                return [row["row"] for row in json.loads(r.read())["rows"]]
        except Exception:  # noqa: BLE001 - the public API is occasionally flaky
            time.sleep(2 * (attempt + 1))
    return []


def humanize(occupation: str) -> str:
    words = [OCCUPATION_WORDS.get(w, w) for w in (occupation or "").split("_")]
    return " ".join(words).replace(" / ", "/").strip()


def as_list(value) -> list[str]:
    """List columns arrive as Python-literal strings ("['Hiking', ...]")."""
    if isinstance(value, list):
        return [str(v) for v in value]
    try:
        parsed = ast.literal_eval(value or "[]")
        return [str(v) for v in parsed] if isinstance(parsed, (list, tuple)) else []
    except (ValueError, SyntaxError):
        return []


def to_talon(row: dict) -> dict | None:
    """Convert a Nemotron persona into Talon's persona card (see agents/talon_agents/state.py)."""
    text = " ".join(str(row.get(k) or "") for k in ("persona", "cultural_background", "hobbies_and_interests"))
    if UNSAFE.search(text):
        return None
    first = (row.get("persona") or "").split(" ")[0].strip(",.")
    if not first.isalpha():
        return None
    age = int(row["age"])
    job = humanize(row.get("occupation") or "")
    if job in ("not in workforce", "unemployed"):
        job = ""
    hobbies = [h for h in as_list(row.get("hobbies_and_interests_list")) if 3 < len(h) < 40][:2]
    background = [f"retired {job}" if job and age >= 66 else job or "retired"]
    if row.get("marital_status") == "widowed":
        background.append("widowed")
    elif row.get("marital_status") == "married_present":
        background.append("married")
    background += [f"enjoys {h[0].lower() + h[1:]}" for h in hobbies]
    voice = ["short, plain texts, mostly lowercase", "polite, cooperative, a little slow to catch on",
             "asks a simple question when something doesn't make sense"]
    if age >= 75:
        voice.append("the odd small typo")
    details = {"their name": [first.lower()], "their city": [row["city"].lower()]}
    if job:
        details["their job"] = [re.split(r"[ /&]+", job.lower())[-1]]  # the head noun: "teacher", "nurse"
    for h in hobbies:
        key = re.sub(r"[^a-z ]", "", h.lower()).split()
        if key:
            details[f"{h.lower()}"] = [max(key, key=len)]
    return {
        "id": f"np_{row['uuid'].replace('-', '')[:10]}",
        "source": "nemotron-personas-usa",
        "source_uuid": row["uuid"],
        "name": first,
        "age": age,
        "sex": row.get("sex"),
        "city": row["city"],
        "state": row["state"],
        "voice": voice,
        "background": background,
        "details": details,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--min-age", type=int, default=60)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    chosen: list[dict] = []
    states: dict[str, int] = {}
    pages = 0
    while len(chosen) < args.count and pages < 40:
        pages += 1
        for row in fetch_page(rng.randrange(0, TOTAL_ROWS - 100)):
            if int(row.get("age") or 0) < args.min_age:
                continue
            p = to_talon(row)
            if not p or states.get(p["state"], 0) >= 2 or any(c["name"] == p["name"] for c in chosen):
                continue
            states[p["state"]] = states.get(p["state"], 0) + 1
            chosen.append(p)
            if len(chosen) >= args.count:
                break
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for p in chosen:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"wrote {len(chosen)} personas from {pages} pages to {OUT.relative_to(ROOT)} "
          f"({len(states)} states, ages {min(p['age'] for p in chosen)}-{max(p['age'] for p in chosen)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
