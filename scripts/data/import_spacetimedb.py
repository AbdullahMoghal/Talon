"""Import the taxonomy and message datasets into a Talon SpacetimeDB database.

Validates each dataset file first, then calls the module's admin-only
`import_taxonomy` and `import_messages` reducers through the `spacetime` CLI,
so the CLI's saved login is used. Importing is idempotent: messages are
replaced by id.

Usage:
    python3 scripts/data/import_spacetimedb.py --server http://127.0.0.1:4000 --db talon-dev
    python3 scripts/data/import_spacetimedb.py --server maincloud --db talon-prod
    python3 scripts/data/import_spacetimedb.py --db talon-dev data/gold_test.jsonl data/messages.jsonl
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAXONOMY = ROOT / "data" / "taxonomy.json"
DEFAULT_DATASETS = [ROOT / "data" / "gold_test.jsonl"]
BATCH = 50


def opt(value):
    """Encode an optional value the way SpacetimeDB's JSON format expects."""
    return {"none": []} if value is None else {"some": value}


def spacetime_call(server, db, reducer, *args):
    cmd = ["spacetime", "call", "-y", "--server", server, db, reducer, *(json.dumps(a) for a in args)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"{reducer} failed:\n{result.stderr or result.stdout}")


def taxonomy_args(tax):
    categories = [
        {
            "id": c["id"],
            "name": c["name"],
            "description": c["description"],
            "weight": c["weight"],
            "harm": c["harm"],
            "brands": c["brands"],
            "hooks": c["hooks"],
            "asks": c["asks"],
            "indicator_types": c["indicators"],
            "targets": c["targets"],
            "seasonality": c["seasonality"],
            "decoy_tactics": c["decoy_tactics"],
            "next_steps": c["next_steps"],
        }
        for c in tax["categories"]
    ]
    subtypes = [
        {"id": s["id"], "name": s["name"], "hard_negative_for": s["hard_negative_for"]}
        for s in tax["legit_subtypes"]
    ]
    tactics = [{"id": k, "description": v} for k, v in tax["decoy_tactics"].items()]
    return tax["version"], tax["updated"], tax["shared_next_steps"], categories, subtypes, tactics


def message_arg(r):
    return {
        "id": r["id"],
        "text": r["text"],
        "label": r["label"],
        "category": opt(r["category"]),
        "legit_subtype": opt(r["legit_subtype"]),
        "campaign_id": opt(r["campaign_id"]),
        "sender": r["sender"],
        "sender_type": r["sender_type"],
        "brand": opt(r["brand"]),
        "hook": opt(r["hook"]),
        "tactics": r["tactics"],
        "difficulty": r["difficulty"],
        "age_band": r["target_profile"]["age_band"],
        "state": r["target_profile"]["state"],
        "season": opt(r["season"]),
        "generator": r["generator"],
        "split": r["split"],
        "indicators": [{"kind": i["type"], "value": i["value"]} for i in r["indicators"]],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("datasets", nargs="*", type=Path, default=DEFAULT_DATASETS)
    parser.add_argument("--server", default="http://127.0.0.1:4000", help="server nickname or URL")
    parser.add_argument("--db", default="talon-dev", help="database name")
    args = parser.parse_args()

    if not shutil.which("spacetime"):
        sys.exit("spacetime CLI not found on PATH (try: export PATH=\"$HOME/.local/bin:$PATH\")")

    validator = ROOT / "scripts" / "data" / "validate.py"
    for path in args.datasets:
        check = subprocess.run([sys.executable, "-I", str(validator), str(path)], capture_output=True, text=True)
        if check.returncode != 0:
            sys.exit(f"{path} failed validation; fix it before importing:\n{check.stdout}")

    tax = json.loads(TAXONOMY.read_text())
    spacetime_call(args.server, args.db, "import_taxonomy", *taxonomy_args(tax))
    print(f"taxonomy v{tax['version']}: {len(tax['categories'])} categories, "
          f"{len(tax['legit_subtypes'])} legit subtypes, {len(tax['decoy_tactics'])} tactics")

    for path in args.datasets:
        records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        for start in range(0, len(records), BATCH):
            batch = [message_arg(r) for r in records[start:start + BATCH]]
            spacetime_call(args.server, args.db, "import_messages", batch)
        indicators = sum(len(r["indicators"]) for r in records)
        print(f"{path.name}: {len(records)} messages, {indicators} indicators")


if __name__ == "__main__":
    main()
