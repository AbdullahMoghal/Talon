"""Thin client for Nemotron through an OpenAI-compatible endpoint.

Works with NVIDIA's hosted API (build.nvidia.com) and with a self-hosted NIM or
vLLM server: point NEMOTRON_BASE_URL at whichever you use.
"""

import httpx

from .config import settings


class Nemotron:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        self.base = (base_url or settings.nemotron_base_url).rstrip("/")
        self.model = model or settings.nemotron_model
        key = api_key if api_key is not None else settings.nvidia_api_key
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        self.http = httpx.Client(headers=headers, timeout=60)

    def chat(self, messages: list[dict], **params) -> str:
        body = {"model": self.model, "messages": messages, "temperature": 0.6, "max_tokens": 512, **params}
        r = self.http.post(f"{self.base}/chat/completions", json=body)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"] or ""

    def models(self) -> list[str]:
        r = self.http.get(f"{self.base}/models")
        r.raise_for_status()
        return sorted(m["id"] for m in r.json().get("data", []))
