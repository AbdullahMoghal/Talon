"""Loads data/taxonomy.json, the source of truth for categories, tactics and indicator types."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .config import REPO_ROOT

TAXONOMY_PATH = REPO_ROOT / "data" / "taxonomy.json"


@dataclass(frozen=True)
class Taxonomy:
    raw: dict

    @property
    def categories(self) -> dict[str, dict]:
        return {c["id"]: c for c in self.raw["categories"]}

    @property
    def tactics(self) -> dict[str, str]:
        return dict(self.raw["decoy_tactics"])

    @property
    def indicator_types(self) -> list[str]:
        return list(self.raw["indicator_types"])

    @property
    def shared_next_steps(self) -> list[str]:
        return list(self.raw["shared_next_steps"])

    def category(self, category_id: str | None) -> dict | None:
        return self.categories.get(category_id or "")

    def next_steps(self, category_id: str | None) -> list[str]:
        cat = self.category(category_id)
        return (cat["next_steps"] if cat else []) + self.shared_next_steps

    def playbook(self, category_id: str) -> dict:
        cat = self.category(category_id)
        if not cat:
            return {"error": f"unknown category {category_id!r}", "known": sorted(self.categories)}
        return {k: cat[k] for k in ("id", "name", "brands", "hooks", "asks", "indicators", "decoy_tactics")}


@lru_cache(maxsize=1)
def load_taxonomy(path: Path = TAXONOMY_PATH) -> Taxonomy:
    return Taxonomy(json.loads(path.read_text(encoding="utf-8")))
