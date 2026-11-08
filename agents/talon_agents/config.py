"""Settings from environment variables, with a repo-root .env as a fallback.

No API key means the engine runs on FakeLLM, so everything works offline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

AGENTS = ("triage", "extractor", "handler", "persona", "safety", "analyst", "scammer", "judge")

# Best guesses until verified with GET /v1/models on our key (see handoff section 4).
DEFAULT_MODEL = "nvidia/nvidia-nemotron-nano-9b-v2"


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Minimal .env reader: KEY=VALUE lines, no overrides of variables already set."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    api_key: str | None = None
    base_url: str = "https://integrate.api.nvidia.com/v1"
    models: dict[str, str] = field(default_factory=dict)
    max_turns: int = 20
    max_handler_tool_calls: int = 4
    max_safety_retries: int = 2
    triage_threshold: float = 0.7
    # Triage retrieves similar scams only when its first answer lands in this band.
    retrieval_band: tuple[float, float] = (0.4, 0.8)

    def model_for(self, agent: str) -> str:
        return self.models.get(agent) or self.models.get("default") or DEFAULT_MODEL

    @property
    def use_fake(self) -> bool:
        return not self.api_key or os.environ.get("TALON_FAKE_LLM") == "1"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        models = {"default": os.environ.get("NEMOTRON_MODEL", DEFAULT_MODEL)}
        for agent in AGENTS:
            value = os.environ.get(f"{agent.upper()}_MODEL")
            if value:
                models[agent] = value
        return cls(
            api_key=os.environ.get("NVIDIA_API_KEY") or None,
            base_url=os.environ.get("NEMOTRON_BASE_URL", cls.base_url),
            models=models,
            triage_threshold=float(os.environ.get("TRIAGE_THRESHOLD", cls.triage_threshold)),
        )
