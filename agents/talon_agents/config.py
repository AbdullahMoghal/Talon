"""Settings from environment variables, with a repo-root .env as a fallback.

No API key means the engine runs on FakeLLM, so everything works offline.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

AGENTS = ("triage", "extractor", "handler", "persona", "safety", "analyst", "scammer", "judge")

# Best guesses until verified with GET /v1/models on our key (see handoff section 4).
DEFAULT_MODEL = "nvidia/nvidia-nemotron-nano-9b-v2"


def is_guard_model(model: str) -> bool:
    return bool(re.search(r"guard", model or "", re.I))


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
    # Per-agent endpoint overrides, e.g. the safety guard model on a second vLLM port.
    base_urls: dict[str, str] = field(default_factory=dict)
    max_turns: int = 20
    # End a takeover when the scammer has stopped revealing anything new for this many turns.
    max_stale_turns: int = 3
    typing_delay: bool = False  # human-like pause before each reply; the live runner turns it on
    max_handler_tool_calls: int = 4
    # How the handler reasons before planning each turn (HANDLER_REASONING):
    #   "full"   /think with up to 2048 tokens; on live Nano this was 7-28 s per turn, ~90% of the handler's time
    #   "budget" /think, but at most handler_reasoning_budget tokens; then it acts on its notes
    #   "off"    no reasoning step; the code guardrails (tactic list, tripwires, evidence rule) still apply
    handler_reasoning: str = "full"
    handler_reasoning_budget: int = 384
    max_safety_retries: int = 2
    triage_threshold: float = 0.7
    # Triage retrieves similar scams only when its first answer lands in this band.
    retrieval_band: tuple[float, float] = (0.4, 0.8)

    def model_for(self, agent: str) -> str:
        return self.models.get(agent) or self.models.get("default") or DEFAULT_MODEL

    def base_url_for(self, agent: str) -> str:
        return self.base_urls.get(agent) or self.base_url

    @property
    def safety_uses_guard(self) -> bool:
        """SAFETY_MODEL is a safety guard model (its own prompt template and verdict format), not a chat model."""
        return is_guard_model(self.model_for("safety"))

    @property
    def use_fake(self) -> bool:
        return not self.api_key or os.environ.get("TALON_FAKE_LLM") == "1"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        models = {"default": os.environ.get("NEMOTRON_MODEL", DEFAULT_MODEL)}
        base_urls = {}
        for agent in AGENTS:
            if value := os.environ.get(f"{agent.upper()}_MODEL"):
                models[agent] = value
            if value := os.environ.get(f"{agent.upper()}_BASE_URL"):
                base_urls[agent] = value
        return cls(
            # NEMOTRON_API_KEY is the key we set on our own vLLM server on Brev; NVIDIA_API_KEY is build.nvidia.com.
            api_key=os.environ.get("NEMOTRON_API_KEY") or os.environ.get("NVIDIA_API_KEY") or None,
            base_url=os.environ.get("NEMOTRON_BASE_URL") or cls.base_url,
            models=models,
            base_urls=base_urls,
            triage_threshold=float(os.environ.get("TRIAGE_THRESHOLD", cls.triage_threshold)),
            handler_reasoning=os.environ.get("HANDLER_REASONING") or cls.handler_reasoning,
            handler_reasoning_budget=int(os.environ.get("HANDLER_REASONING_BUDGET") or cls.handler_reasoning_budget),
        )
