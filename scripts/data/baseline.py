"""Talon baselines from DATA_SPEC.md.

1. Keyword rules: flag a message as scam when it has a link or callback number
   plus urgency words, or a payment ask. Needs no training data, so it can
   score the gold set today.
2. TF-IDF + logistic regression: word 1-2-grams and char 3-5-grams, predicting
   scam vs. legit and the scam category. Trains on the `train` split of
   data/messages.jsonl once D1 exists; skipped until then.

Usage:
    python scripts/data/baseline.py                      # score data/gold_test.jsonl
    python scripts/data/baseline.py --eval data/messages.jsonl --split test
    python scripts/data/baseline.py --json results.json  # also write metrics as JSON
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data" / "gold_test.jsonl"
MESSAGES = ROOT / "data" / "messages.jsonl"

LINK_RE = re.compile(r"(https?://|www\.|\b[\w-]+\.(?:example|test|invalid|com|net|org|co|info|xyz|top)\b)", re.I)
PHONE_RE = re.compile(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
URGENCY_RE = re.compile(
    r"\b(urgent|immediately|now|today|within \d+\s*(h|hrs?|hours?|mins?|minutes?)|expire[sd]?|suspend(ed)?|"
    r"final (notice|warning)|last chance|act now|verify|locked|deadline|overdue|avoid|penalt(y|ies))\b",
    re.I,
)
PAYMENT_RE = re.compile(
    r"\b(gift ?cards?|bitcoin|btc|usdt|crypto|wallet|zelle|venmo|cash ?app|wire|western union|"
    r"pay (a |the )?(fee|toll|balance)|processing fee|routing number|account number)\b",
    re.I,
)


def load(path: Path, split: str | None = None) -> list[dict]:
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [r for r in rows if split is None or r.get("split") == split]


def keyword_predict(text: str) -> str:
    has_contact = bool(LINK_RE.search(text) or PHONE_RE.search(text))
    if PAYMENT_RE.search(text) or (has_contact and URGENCY_RE.search(text)):
        return "scam"
    return "legit"


def binary_metrics(gold: list[str], pred: list[str]) -> dict:
    tp = sum(g == p == "scam" for g, p in zip(gold, pred))
    fp = sum(g == "legit" and p == "scam" for g, p in zip(gold, pred))
    fn = sum(g == "scam" and p == "legit" for g, p in zip(gold, pred))
    acc = sum(g == p for g, p in zip(gold, pred)) / len(gold)
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"accuracy": acc, "precision": prec, "recall": rec, "f1": f1, "n": len(gold)}


def report(name: str, rows: list[dict], pred: list[str]) -> dict:
    gold = [r["label"] for r in rows]
    out = {"all": binary_metrics(gold, pred)}
    hard = [i for i, r in enumerate(rows) if r.get("difficulty") == "hard"]
    if hard:
        out["hard"] = binary_metrics([gold[i] for i in hard], [pred[i] for i in hard])
    print(f"\n{name}")
    for subset, m in out.items():
        print(f"  {subset:<5} n={m['n']:<4} acc={m['accuracy']:.3f} prec={m['precision']:.3f} "
              f"rec={m['recall']:.3f} f1={m['f1']:.3f}")
    return out


def tfidf_baseline(train: list[dict], evals: list[dict]) -> tuple[list[str], list[str]]:
    from scipy.sparse import hstack
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    word = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    char = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2, sublinear_tf=True)
    xs = [r["text"] for r in train]
    x_train = hstack([word.fit_transform(xs), char.fit_transform(xs)]).tocsr()
    x_eval = hstack([word.transform([r["text"] for r in evals]),
                     char.transform([r["text"] for r in evals])]).tocsr()

    binary = LogisticRegression(max_iter=2000, class_weight="balanced")
    binary.fit(x_train, [r["label"] for r in train])
    labels = list(binary.predict(x_eval))

    scams = [i for i, r in enumerate(train) if r["label"] == "scam"]
    cat = LogisticRegression(max_iter=2000, class_weight="balanced")
    cat.fit(x_train[scams], [train[i]["category"] for i in scams])
    cats = list(cat.predict(x_eval))
    return labels, cats


def macro_f1_categories(rows: list[dict], cats: list[str]) -> float:
    from sklearn.metrics import f1_score

    idx = [i for i, r in enumerate(rows) if r["label"] == "scam"]
    return f1_score([rows[i]["category"] for i in idx], [cats[i] for i in idx], average="macro")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--eval", type=Path, default=GOLD, help="JSONL file to score (default: gold set)")
    ap.add_argument("--split", default=None, help="only score rows with this split value")
    ap.add_argument("--train", type=Path, default=MESSAGES, help="D1 messages with a train split")
    ap.add_argument("--json", type=Path, default=None, help="write metrics to this file")
    args = ap.parse_args()

    rows = load(args.eval, args.split)
    if not rows:
        print(f"no rows to score in {args.eval}", file=sys.stderr)
        return 1
    results = {"eval": str(args.eval), "split": args.split}

    results["keyword"] = report("Keyword rules", rows, [keyword_predict(r["text"]) for r in rows])

    if args.train.exists():
        train = load(args.train, "train")
        if train:
            labels, cats = tfidf_baseline(train, rows)
            results["tfidf"] = report("TF-IDF + logistic regression", rows, labels)
            results["tfidf"]["category_macro_f1"] = macro_f1_categories(rows, cats)
            print(f"  category macro-F1={results['tfidf']['category_macro_f1']:.3f}")
    else:
        print(f"\nTF-IDF baseline skipped: {args.train.relative_to(ROOT)} doesn't exist yet (D1).")

    if args.json:
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
