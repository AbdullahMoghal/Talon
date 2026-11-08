"""Score triage and the extractor on the gold test set, against a keyword baseline.

    python -m talon_agents.eval_gold            # whatever model .env points at (FakeLLM if no key)
    python -m talon_agents.eval_gold --limit 20 # quick look

The gold set (data/gold_test.jsonl) is for measurement only. Never change prompts, thresholds or
fake responders because of a specific gold message: that turns these numbers into a memory test.
Results go to agents/results/ so runs can be compared.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agents.extractor import run_extractor
from .agents.triage import run_triage
from .config import REPO_ROOT, Settings
from .fake_responders import LINK_OR_NUMBER, PAYMENT, URGENCY
from .llm import make_llm
from .retrieval import ScamRetriever
from .store import InMemoryStore, Tracer
from .taxonomy import load_taxonomy

GOLD = REPO_ROOT / "data" / "gold_test.jsonl"
RESULTS = Path(__file__).resolve().parents[1] / "results"
BUCKETS = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.01)]


def load_gold(limit: int | None = None) -> list[dict]:
    with GOLD.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return rows[:limit] if limit else rows


def baseline(text: str) -> bool:
    """What a simple keyword filter would do: two or more of urgency, payment words, link or number."""
    return sum(bool(p.search(text)) for p in (URGENCY, PAYMENT, LINK_OR_NUMBER)) >= 2


def _norm(value: str) -> str:
    value = re.sub(r"^(https?://)?(www\.)?", "", value.strip().lower())
    return "".join(ch for ch in value if ch.isalnum())


def run_one(row: dict, llm, settings: Settings, taxonomy, retriever) -> dict:
    store = InMemoryStore()
    tracer = Tracer(store, row["id"], None)
    start = time.perf_counter()
    try:
        t = run_triage(llm=llm, text=row["text"], taxonomy=taxonomy, retriever=retriever, tracer=tracer,
                       settings=settings)
        error = None
    except Exception as e:  # noqa: BLE001 - one bad call shouldn't sink the run
        t, error = {"is_scam": False, "category": None, "confidence": 0.5, "retrieved": False}, repr(e)[:200]
    triage_ms = int((time.perf_counter() - start) * 1000)

    extracted = None
    if row["label"] == "scam":
        try:
            found = run_extractor(llm=llm, text=row["text"], taxonomy=taxonomy, store=store, tracer=tracer,
                                  session_id=row["id"], turn_id="t0", category=row["category"])
            extracted = [{"kind": i["kind"], "value": i["value"]} for i in found]
        except Exception as e:  # noqa: BLE001
            extracted, error = [], error or repr(e)[:200]

    return {"id": row["id"], "label": row["label"], "category": row["category"], "difficulty": row["difficulty"],
            "pred_scam": t["is_scam"], "pred_category": t["category"], "confidence": t["confidence"],
            "retrieved": t.get("retrieved", False), "baseline_scam": baseline(row["text"]),
            "gold_indicators": [{"kind": i["type"], "value": i["value"]} for i in row["indicators"]],
            "extracted": extracted, "triage_ms": triage_ms, "error": error}


def detection(preds: list[bool], labels: list[bool]) -> dict:
    tp = sum(p and y for p, y in zip(preds, labels))
    fp = sum(p and not y for p, y in zip(preds, labels))
    fn = sum(not p and y for p, y in zip(preds, labels))
    tn = sum(not p and not y for p, y in zip(preds, labels))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"accuracy": round((tp + tn) / len(labels), 3), "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(2 * precision * recall / (precision + recall), 3) if precision + recall else 0.0,
            "false_alarm_rate": round(fp / (fp + tn), 3) if fp + tn else 0.0,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def summarize(rows: list[dict]) -> dict:
    labels = [r["label"] == "scam" for r in rows]
    out: dict = {
        "n": len(rows),
        "errors": sum(bool(r["error"]) for r in rows),
        "talon": detection([r["pred_scam"] for r in rows], labels),
        "baseline": detection([r["baseline_scam"] for r in rows], labels),
    }
    caught = [r for r in rows if r["label"] == "scam" and r["pred_scam"]]
    out["category_accuracy_on_caught_scams"] = (
        round(sum(r["pred_category"] == r["category"] for r in caught) / len(caught), 3) if caught else None)

    # Honest confidence: within each confidence band, how often is the message really a scam?
    out["calibration"] = []
    for lo, hi in BUCKETS:
        band = [r for r in rows if lo <= r["confidence"] < hi]
        if band:
            out["calibration"].append({"confidence": f"{lo:.1f}-{min(hi, 1.0):.1f}", "n": len(band),
                                       "actually_scam": round(sum(r["label"] == "scam" for r in band) / len(band), 3)})
    out["brier"] = round(statistics.fmean((r["confidence"] - (r["label"] == "scam")) ** 2 for r in rows), 4)
    out["retrieval_rate"] = round(sum(r["retrieved"] for r in rows) / len(rows), 3)

    by_diff = defaultdict(list)
    for r in rows:
        by_diff[r["difficulty"]].append(r)
    out["by_difficulty"] = {d: detection([r["pred_scam"] for r in rs], [r["label"] == "scam" for r in rs])
                            for d, rs in sorted(by_diff.items())}

    # Extraction: every gold indicator found (recall); every extracted item in gold (precision).
    hit = total_gold = matched_pred = total_pred = 0
    per_kind: Counter = Counter()
    per_kind_hit: Counter = Counter()
    for r in rows:
        if r["extracted"] is None:
            continue
        pred = {(i["kind"], _norm(i["value"])) for i in r["extracted"]}
        gold = {(i["kind"], _norm(i["value"])) for i in r["gold_indicators"]}
        for g in gold:
            per_kind[g[0]] += 1
            if any(p[0] == g[0] and (p[1] == g[1] or g[1] in p[1] or p[1] in g[1]) for p in pred if p[1]):
                hit += 1
                per_kind_hit[g[0]] += 1
        total_gold += len(gold)
        total_pred += len(pred)
        matched_pred += sum(any(p[0] == g[0] and (p[1] == g[1] or g[1] in p[1] or p[1] in g[1]) for g in gold)
                            for p in pred if p[1])
    out["extraction"] = {
        "recall": round(hit / total_gold, 3) if total_gold else None,
        "precision": round(matched_pred / total_pred, 3) if total_pred else None,
        "gold_indicators": total_gold, "extracted": total_pred,
        "recall_by_kind": {k: f"{per_kind_hit[k]}/{n}" for k, n in per_kind.most_common()},
    }
    ms = sorted(r["triage_ms"] for r in rows)
    out["triage_latency_ms"] = {"p50": ms[len(ms) // 2], "p95": ms[int(len(ms) * 0.95) - 1] if len(ms) > 1 else ms[0]}
    return out


def print_report(s: dict, model: str) -> None:
    t, b = s["talon"], s["baseline"]
    print(f"\nGold set: {s['n']} messages, model {model}, {s['errors']} errors")
    print(f"{'':22}{'Talon':>8}{'Keyword baseline':>18}")
    for k in ("accuracy", "precision", "recall", "f1", "false_alarm_rate"):
        print(f"{k:22}{t[k]:>8}{b[k]:>18}")
    print(f"\nCategory right on caught scams: {s['category_accuracy_on_caught_scams']}")
    print(f"Retrieved similar scams on {s['retrieval_rate']:.0%} of messages (agent's choice)")
    print("Calibration (confidence band -> share that really were scams):")
    for c in s["calibration"]:
        print(f"  {c['confidence']}: {c['actually_scam']:.0%} of {c['n']}")
    print(f"Brier score: {s['brier']} (lower is better; 0.25 = always saying 50%)")
    print("By difficulty (Talon recall / false alarms):")
    for d, m in s["by_difficulty"].items():
        print(f"  {d:7} recall {m['recall']:.0%}, false alarms {m['false_alarm_rate']:.0%}")
    e = s["extraction"]
    print(f"Extraction: recall {e['recall']}, precision {e['precision']} "
          f"({e['extracted']} extracted vs {e['gold_indicators']} gold)  {e['recall_by_kind']}")
    print(f"Triage latency: p50 {s['triage_latency_ms']['p50']} ms, p95 {s['triage_latency_ms']['p95']} ms")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--fake", action="store_true")
    args = ap.parse_args()

    settings = Settings.from_env()
    if args.fake:
        settings.api_key = None
    llm = make_llm(settings)
    model = "FakeLLM" if settings.use_fake else settings.model_for("triage")
    taxonomy = load_taxonomy()
    retriever = ScamRetriever(taxonomy)
    gold = load_gold(args.limit)

    with ThreadPoolExecutor(max_workers=1 if settings.use_fake else args.workers) as pool:
        rows = list(pool.map(lambda r: run_one(r, llm, settings, taxonomy, retriever), gold))

    summary = summarize(rows)
    print_report(summary, model)
    RESULTS.mkdir(exist_ok=True)
    name = re.sub(r"[^a-z0-9]+", "-", model.lower()).strip("-")
    path = RESULTS / f"gold_{name}_{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({"model": model, "summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print(f"\nSaved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
