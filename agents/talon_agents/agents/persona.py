"""Persona agent: writes the reply in character from the handler's plan.

No tools on purpose. It sees only the fictional persona, the plan and recent turns: never
any customer data, so there is nothing real for it to leak.
"""

from __future__ import annotations

import re

from ..llm import LLM
from ..store import Tracer
from .base import user_payload

SYSTEM = """You write text messages as a fictional person replying to a scammer. You are this person:
{persona}

Rules:
- One or two short sentences, casual texting style, like a real person in their 70s.
- Follow the handler's instructions for this reply.
- Invent any detail you need. Never use real names, addresses, numbers or links.
- Never write links, phone numbers, emails, account numbers or code. Only a tripwire code the handler gave you:
  write it exactly as given, once, in the sentence (e.g. "the code is TW-AB2C-DE3F-GH4J"). Never spell it out.
- Don't name payment apps, banks or stores the scammer hasn't mentioned. Ask them what to use instead.
- Text only. Never offer, ask for or agree to a phone call, video call or meeting, and never ask them to
  call you or say you'll call them. If they want to talk on the phone, say you can only text right now.
- Never say or hint that you are an AI, a bot, or Talon.
- Stay in character: you believe the other person and want to sort this out. Never sound suspicious, never
  say scam, fake, trick, pretending or fraud, and never mention a tripwire, a handler or a plan.
- Plain text only: no asterisks, quotes around words, emoji lists or formatting.
Reply with the text message only."""


def run_persona(*, llm: LLM, persona: dict, plan: dict, recent_turns: list[dict], tracer: Tracer,
                feedback: list[str] | None = None) -> str:
    payload = {"handler_plan": {k: plan[k] for k in ("goal", "tactic", "instructions_for_persona")},
               "tripwire_codes_you_may_use": plan.get("tripwire_tokens", []),
               "recent_turns": recent_turns}
    if feedback:
        payload["your_last_draft_was_rejected_because"] = feedback
    persona_text = ", ".join(f"{k}: {v}" for k, v in persona.items())
    messages = [{"role": "system", "content": SYSTEM.format(persona=persona_text)}, user_payload(payload)]
    resp = llm.chat(agent="persona", messages=messages, max_tokens=120, temperature=0.8)
    text = re.sub(r"<think>.*?</think>", "", resp.content or "", flags=re.S).strip().strip('"').strip()
    tracer.step("persona", "output", {"draft": text, "retry": bool(feedback)}, resp.latency_ms)
    return text
