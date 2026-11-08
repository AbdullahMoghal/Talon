"""Minimal SpacetimeDB HTTP client: call reducers and run SQL.

Python has no official SpacetimeDB SDK, so the engine uses the HTTP API:
  POST {server}/v1/database/{db}/call/{reducer}   body: JSON array of positional args
  POST {server}/v1/database/{db}/sql              body: SQL text
Options are sent as {"some": v} / {"none": []}. SQL rows come back with options as
[0, v] / [1, []] and timestamps as [micros]; `sql()` decodes both into plain Python.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

NONE = {"none": []}


def some(v):
    return {"some": v}


def opt(v):
    return NONE if v is None else some(v)


class SpacetimeError(RuntimeError):
    pass


class SpacetimeClient:
    def __init__(self, server: str, db: str, token: str | None = None, timeout: float = 15):
        self.server = server.rstrip("/")
        self.db = db
        self.token = token
        self.timeout = timeout

    @classmethod
    def new_identity(cls, server: str) -> tuple[str, str]:
        """Ask the server for a fresh identity. Returns (identity_hex, token)."""
        req = urllib.request.Request(f"{server.rstrip('/')}/v1/identity", method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read())
        return out["identity"], out["token"]

    def _post(self, path: str, body: bytes, content_type: str) -> bytes:
        req = urllib.request.Request(f"{self.server}/v1/database/{self.db}/{path}", data=body, method="POST",
                                     headers={"Content-Type": content_type})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise SpacetimeError(f"{path}: HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from None

    def call(self, reducer: str, *args) -> None:
        self._post(f"call/{reducer}", json.dumps(list(args)).encode("utf-8"), "application/json")

    def sql(self, query: str) -> list[dict]:
        out = json.loads(self._post("sql", query.encode("utf-8"), "text/plain"))
        rows: list[dict] = []
        for result in out:
            elements = result["schema"]["elements"]
            names = [e["name"].get("some") if isinstance(e["name"], dict) else e["name"] for e in elements]
            types = [e["algebraic_type"] for e in elements]
            for row in result["rows"]:
                rows.append({n: _decode(v, ty) for n, v, ty in zip(names, row, types)})
        return rows


def _decode(value, ty: dict):
    if "Sum" in ty:  # option<T>: [0, v] is some, [1, []] is none
        variants = ty["Sum"].get("variants", [])
        tags = [(v.get("name") or {}).get("some") for v in variants]
        if tags[:2] == ["some", "none"] and isinstance(value, list) and len(value) == 2:
            if value[0] == 1:
                return None
            return _decode(value[1], variants[0]["algebraic_type"])
        return value
    if "Product" in ty:  # timestamps arrive as [micros]
        elems = ty["Product"].get("elements", [])
        if len(elems) == 1 and isinstance(value, list) and len(value) == 1:
            name = (elems[0].get("name") or {}).get("some", "")
            if "micros" in name:
                return value[0]
        return value
    return value
