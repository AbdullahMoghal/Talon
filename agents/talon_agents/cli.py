"""Talon CLI: play the scammer and watch the agents work.

    python -m talon_agents.cli              # interactive: you type as the scammer
    python -m talon_agents.cli --demo       # scripted 6-turn toll scam, then a second customer gets blocked
    python -m talon_agents.cli --fake       # force FakeLLM even if NVIDIA_API_KEY is set

Without NVIDIA_API_KEY (env or repo-root .env) it runs on FakeLLM, fully offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

from .config import Settings
from .engine import TalonEngine
from .store import AgentStep

DEMO_OPENER = ("E-ZPass: You have an unpaid toll balance of $6.85. Pay today to avoid a $50 late fee: "
               "ezpass-tollpay.example/pay")
DEMO_TURNS = [
    "Just open the link and enter your card details to pay the balance.",
    "The site is working fine. Try ezpass-billing.test/secure instead",
    "If your card doesn't work you can pay with Cash App $TollDeskPay or Zelle to tolls-dept@payhelp.example",
    "You can also call our billing office at (469) 555-0182",
    "Ok then buy a $100 Apple gift card and send me the code on the back",
    "Thank you. we will process it now",
]
# Same scammer, new number and new wording; only the payment handle Talon extracted gives it away.
SECOND_CUSTOMER_TEXT = ("Toll Services: final notice, your balance is overdue. "
                        "Send $6.85 by Cash App to $TollDeskPay today to avoid a late fee")

COLORS = {"triage": "36", "extractor": "35", "handler": "33", "persona": "32", "safety": "31", "analyst": "34",
          "engine": "37"}


def customer_ref(phone: str) -> str:
    return "cust_" + hashlib.sha256(phone.encode()).hexdigest()[:12]


def color(agent: str, text: str) -> str:
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return f"\033[{COLORS.get(agent, '37')}m{text}\033[0m"


def print_step(table: str, row: object) -> None:
    if table != "agent_step":
        return
    step: AgentStep = row  # type: ignore[assignment]
    c = step.content
    if step.kind == "tool_call":
        body = f"→ {c['tool']}({json.dumps(c['args'], ensure_ascii=False)})"
    elif step.kind == "tool_result":
        body = f"← {c['tool']}: {json.dumps(c['result'], ensure_ascii=False)[:220]}"
    else:
        body = json.dumps(c, ensure_ascii=False)[:260]
    ms = f" {step.latency_ms}ms" if step.latency_ms else ""
    print(color(step.agent, f"    [{step.agent}:{step.kind}{ms}] {body}"))


def show_warning(result: dict) -> None:
    t = result.get("triage", {})
    print(f"\n  📱 Customer phone: status={result['status']}")
    if result["status"] == "warned":
        print(f"     ⚠ Likely {t['category']} scam, {round(t['confidence'] * 100)}% confidence. {t['reason']}")
        for s in t["next_steps"]:
            print(f"       • {s}")
        print("     [Delete] [Report] [Let Talon handle it]")


def run(engine: TalonEngine, opener: str, turns: list[str] | None, scammer_number: str = "+12145550137") -> None:
    cust = customer_ref("+19725550101")
    print(f"\n💬 Scammer → customer: {opener}")
    result = engine.receive_message(cust, scammer_number, opener)
    show_warning(result)
    if result["status"] != "warned":
        print("  Not flagged as a scam above the threshold; no takeover offered.")
        return
    print("\n  👆 Customer taps \"Let Talon handle it\"")
    session, reply = engine.request_takeover(result["message_id"])
    sid = session["id"]
    print(f"\n🛡 Talon → scammer: {reply}")

    script = iter(turns) if turns is not None else None
    while engine.store.sessions[sid]["status"] == "active":
        if script is not None:
            text = next(script, None)
            if text is None:
                print("\n  👆 Customer taps Stop")
                engine.stop_takeover(sid)
                break
            print(f"\n💬 Scammer: {text}")
        else:
            try:
                text = input("\n💬 Scammer (/stop to tap Stop): ").strip()
            except EOFError:
                text = "/stop"
            if text == "/stop":
                engine.stop_takeover(sid)
                break
            if not text:
                continue
        reply = engine.handle_scammer_message(sid, text)
        if reply:
            print(f"\n🛡 Talon → scammer: {reply}")

    s = engine.store
    print(f"\n━━ Session ended: {s.sessions[sid]['ended_reason']}")
    print("   Indicators: " + ", ".join(f"{i['kind']}={i['value']}" for i in s.indicators_for(sid)))
    for c in s.campaigns.values():
        print(f"   Campaign {c['id']}: {c['status']}, sessions={len(c['session_ids'])}")
    for card in s.impact_cards:
        if card["session_id"] == sid:
            print(f"   🏅 Impact card: {card['text']}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--demo", action="store_true", help="run the scripted toll-scam demo")
    parser.add_argument("--fake", action="store_true", help="use FakeLLM even if an API key is set")
    parser.add_argument("--quiet", action="store_true", help="hide the agent trace")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.fake:
        os.environ["TALON_FAKE_LLM"] = "1"
    settings = Settings.from_env()
    engine = TalonEngine(settings=settings)
    if not args.quiet:
        engine.store.listeners.append(print_step)
    print(f"Talon engine · model: {'FakeLLM (offline)' if settings.use_fake else settings.model_for('handler')}")

    if args.demo:
        run(engine, DEMO_OPENER, DEMO_TURNS)
        print(f"\n💬 Same scam reaches a second customer: {SECOND_CUSTOMER_TEXT}")
        second = engine.receive_message(customer_ref("+19725550144"), "+12145550199", SECOND_CUSTOMER_TEXT)
        print(f"  📱 Second customer phone: status={second['status']}"
              + (" (Talon shut this campaign down)" if second["status"] == "blocked" else ""))
    else:
        opener = input("💬 Scammer's first text to the customer: ").strip() or DEMO_OPENER
        run(engine, opener, None)


if __name__ == "__main__":
    main()
