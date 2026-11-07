"""Settings read from the environment (see .env.example at the repo root)."""

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv() -> None:
    """Load KEY=value lines from the repo's .env without overriding real env vars."""
    env = Path(__file__).resolve().parents[2] / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


@dataclass(frozen=True)
class Settings:
    nvidia_api_key: str = os.environ.get("NVIDIA_API_KEY", "")
    nemotron_base_url: str = os.environ.get("NEMOTRON_BASE_URL", "https://integrate.api.nvidia.com/v1")
    # Check the exact model id on build.nvidia.com, or run `python scripts/smoke.py --list-models`.
    nemotron_model: str = os.environ.get("NEMOTRON_MODEL", "nvidia/nemotron-3-nano-30b-a3b")
    spacetime_url: str = os.environ.get("SPACETIME_URL", "http://localhost:3100")
    spacetime_db: str = os.environ.get("SPACETIME_DB", "talon")
    spacetime_token: str = os.environ.get("SPACETIME_TOKEN", "")


settings = Settings()
