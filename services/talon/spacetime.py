"""Minimal SpacetimeDB HTTP client for the Python pipeline.

SpacetimeDB's official client SDKs are Rust, C# and TypeScript, so Python calls
reducers over the HTTP API instead:

    POST {url}/v1/database/{db}/call/{reducer}   body: JSON array of arguments
    POST {url}/v1/database/{db}/sql              body: SQL text

Check these paths against the SpacetimeDB version you install.
"""

from typing import Any

import httpx

from .config import settings


class SpacetimeError(RuntimeError):
    pass


class Spacetime:
    def __init__(self, url: str | None = None, db: str | None = None, token: str | None = None):
        self.base = f"{(url or settings.spacetime_url).rstrip('/')}/v1/database/{db or settings.spacetime_db}"
        token = token if token is not None else settings.spacetime_token
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.http = httpx.Client(headers=headers, timeout=10)

    def call(self, reducer: str, *args: Any) -> None:
        r = self.http.post(f"{self.base}/call/{reducer}", json=list(args))
        if r.status_code >= 400:
            raise SpacetimeError(f"{reducer} failed ({r.status_code}): {r.text}")

    def sql(self, query: str) -> list[dict]:
        """Run a SQL query and return rows as dicts (first statement only)."""
        r = self.http.post(f"{self.base}/sql", content=query, headers={"Content-Type": "text/plain"})
        if r.status_code >= 400:
            raise SpacetimeError(f"sql failed ({r.status_code}): {r.text}")
        results = r.json()
        if not results:
            return []
        first = results[0]
        names = [_column_name(el, i) for i, el in enumerate(first["schema"]["elements"])]
        return [dict(zip(names, row)) for row in first["rows"]]


def _column_name(element: dict, index: int) -> str:
    name = element.get("name")
    if isinstance(name, dict):  # Option<String> encoded as {"some": "..."}
        name = name.get("some")
    return name or f"col{index}"
