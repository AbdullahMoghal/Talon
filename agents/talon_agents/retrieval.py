"""Retrieval over known scam patterns, used when triage is unsure (agentic RAG).

The corpus is the taxonomy (brands, hooks, asks per category) plus first messages from
earlier sessions. It never includes data/gold_test.jsonl: that set is for final scoring only.

Offline this is keyword overlap. Build step 2 swaps in the Llama Nemotron embedding model
behind the same `search()` method.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .taxonomy import Taxonomy

WORD = re.compile(r"[a-z0-9]+")
STOP = set("a an the to of and or for your you is are be on in at it this that by with from now our we".split())


def tokens(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if w not in STOP and len(w) > 2}


@dataclass
class ScamRetriever:
    taxonomy: Taxonomy
    extra_docs: list[dict] = field(default_factory=list)  # {"category": ..., "text": ...}

    def _docs(self) -> list[dict]:
        docs = []
        for cat in self.taxonomy.raw["categories"]:
            text = " ".join([cat["name"], cat["description"], *cat["brands"], *cat["hooks"], *cat["asks"]])
            docs.append({"category": cat["id"], "text": text, "source": "taxonomy"})
        return docs + self.extra_docs

    def add(self, category: str, text: str, source: str = "session") -> None:
        self.extra_docs.append({"category": category, "text": text, "source": source})

    def search(self, query: str, k: int = 3) -> list[dict]:
        q = tokens(query)
        scored = []
        for doc in self._docs():
            d = tokens(doc["text"])
            overlap = q & d
            if overlap:
                scored.append({"category": doc["category"], "source": doc["source"],
                               "score": round(len(overlap) / (len(q) ** 0.5 * len(d) ** 0.5), 3),
                               "matched": sorted(overlap)[:8]})
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:k]
