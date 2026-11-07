"""Gate 1 smoke test: one Nemotron call returns, and one reducer call lands in SpacetimeDB.

Usage:
    python scripts/smoke.py                 # both checks
    python scripts/smoke.py --list-models   # print model ids your NVIDIA key can use
    python scripts/smoke.py --skip-nemotron # only check SpacetimeDB
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services"))

from talon.config import settings  # noqa: E402
from talon.ids import new_id  # noqa: E402
from talon.nemotron import Nemotron  # noqa: E402
from talon.spacetime import Spacetime  # noqa: E402


def check_nemotron() -> bool:
    if not settings.nvidia_api_key and "integrate.api.nvidia.com" in settings.nemotron_base_url:
        print("FAIL nemotron: set NVIDIA_API_KEY in .env (or point NEMOTRON_BASE_URL at a local NIM)")
        return False
    try:
        reply = Nemotron().chat(
            [{"role": "user", "content": "Reply with exactly: talon ok"}], max_tokens=20, temperature=0
        )
    except Exception as e:  # noqa: BLE001 - report any failure plainly
        print(f"FAIL nemotron ({settings.nemotron_model}): {e}")
        return False
    print(f"ok   nemotron ({settings.nemotron_model}): {reply.strip()[:60]!r}")
    return True


def check_spacetime() -> bool:
    db = Spacetime()
    conversation_id, turn_id = new_id(), new_id()
    try:
        db.call("start_conversation", conversation_id, 1, "sms", "smoke")
        db.call("add_turn", turn_id, conversation_id, "scammer", "smoke test turn", "", 0.0, True)
        rows = db.sql(f"SELECT * FROM turn WHERE id = {turn_id}")
    except Exception as e:  # noqa: BLE001
        print(f"FAIL spacetime ({settings.spacetime_url}, db {settings.spacetime_db}): {e}")
        return False
    if len(rows) != 1:
        print(f"FAIL spacetime: wrote turn {turn_id} but read back {len(rows)} rows")
        return False
    print(f"ok   spacetime: turn {turn_id} written and read back")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-models", action="store_true")
    ap.add_argument("--skip-nemotron", action="store_true")
    ap.add_argument("--skip-spacetime", action="store_true")
    args = ap.parse_args()

    if args.list_models:
        for m in Nemotron().models():
            if "nemotron" in m.lower():
                print(m)
        return 0

    ok = True
    if not args.skip_nemotron:
        ok &= check_nemotron()
    if not args.skip_spacetime:
        ok &= check_spacetime()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
