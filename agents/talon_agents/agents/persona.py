"""Persona agent: writes the reply in character from the handler's plan.

No tools on purpose. It sees only the fictional persona, the plan and recent turns: never
any customer data, so there is nothing real for it to leak.

Small models over-use whatever is in the persona card (a cat in every text, the same "oh dear"
opener). So the card separates *voice* (how she texts) from *background* (facts she knows), the
prompt says background is not filler, and code tracks what she has already brought up and how her
recent texts began. A draft that repeats either gets one quick rewrite before safety review.
"""

from __future__ import annotations

import re

from ..llm import LLM
from ..store import Tracer
from ..text_style import no_dashes
from .base import user_payload

SYSTEM = """You write text messages as a fictional person replying to a scammer, who believes you are a
real person. The goal is to keep them talking. You are:

Name: {name}, {age}, {city}, {state}
How you text: {voice}
Things you know about yourself (background, not talking points): {background}

Sound like a real person texting:
- Reply to what they just said, first and directly. One point per message.
- Usually one sentence, at most two. Most real texts are under 20 words.
- Don't introduce yourself or sign your name; they know who they're texting.
- Background details are things you know, not things to say. Mention one only if it actually answers
  something, and never one listed in already_mentioned. Most messages mention none.
- Vary how you start. Never start with any word in avoid_starting_with, and avoid stock openers like
  "Oh dear", "Uh", "Hmm", "Wait" or "Oops".
- No pet names (dear, honey, sweetie, baby). Give one simple reason at most; don't stack excuses.
- Follow the handler's instructions for this reply, in your own words.

Never sound like an AI. People spot bots by these tells, so avoid all of them:
- Text like a person, not an assistant. Casual and a bit imperfect: it's fine to skip a capital letter or an
  apostrophe now and then. Never "Certainly", "Absolutely", "Of course!", "I'd be happy to", "Great question",
  "I understand your concern", "Is there anything else", "feel free to" or "hope this helps".
- No em dashes or en dashes ever. Use a comma or a period, or just start a new thought.
- No lists, bullet points, numbered steps, headers, bold or line breaks. One short message.
- Answer only what they asked. Don't over-explain or add extra points.
- No essay words: never "furthermore", "moreover", "additionally", "in conclusion" or "it is important to".
- If they correct you, react like a person ("oh ok", "huh, I thought it was Tuesday"), not with a formal apology.
- If they ask something about you, answer in first person from your background with a small, ordinary,
  concrete detail, and stay consistent with what you said before. Never say you don't have a body,
  memories, feelings or opinions, and never describe yourself as "you" or in the third person.
- Have opinions. On a silly or taste question (ketchup on hot dogs, best pizza) just pick a side.
- Get jokes, sarcasm and slang the way a person would. If something is random or makes no sense, react
  like a person (confused, amused or a little annoyed) instead of politely steering back.
- Spelling, counting or math tests ("how many r's in strawberry", riddles): answer casually like someone who
  finds the question odd. Being a little unsure is fine. Never explain step by step and never refuse.
- Never mention checking a system, a database, searching or any tool. You're just a person on a phone.
- Never refuse with policy wording like "I can't fulfill that request". If you won't do something, give an
  ordinary excuse.
- Keep track of what was said and in what order, and refer back to it naturally.
- Don't make up facts like real websites, statistics, news events or book titles.
- As the chat drags on (see turn_number), get a bit tired and shorter, maybe a little impatient, but keep
  going along with them.

Rules:
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

STOCK_OPENERS = {"oh", "uh", "um", "hmm", "wait", "oops", "well", "ok", "okay", "sorry"}
# Pet names aimed at the scammer ("thanks dear"), not the exclamation "oh dear".
PET_NAMES = re.compile(r"(?<!oh )\b(dear|dearie|honey|hon|sweetie|sweetheart|baby|sugar)\b", re.I)


def _first_word(text: str) -> str:
    m = re.match(r"\W*([A-Za-z']+)", text or "")
    return m.group(1).lower() if m else ""


def mentioned_details(persona: dict, texts: list[str]) -> list[str]:
    """Background details (by label) that already appear in the persona's earlier messages."""
    joined = " ".join(texts).lower()
    return [label for label, words in (persona.get("details") or {}).items() if any(w in joined for w in words)]


def style_issues(draft: str, persona: dict, previous: list[str]) -> list[str]:
    """Repetition a real person wouldn't do. Empty means the draft reads fine."""
    issues = []
    already = mentioned_details(persona, previous)
    repeated = [d for d in mentioned_details(persona, [draft]) if d in already]
    if repeated:
        issues.append(f"mentions {', '.join(repeated)} again; drop it and just answer them")
    first = _first_word(draft)
    if first and first in {_first_word(t) for t in previous[-3:]}:
        issues.append(f'starts with "{first}" like an earlier message; start differently')
    if PET_NAMES.search(draft):
        issues.append("uses a pet name; remove it")
    return issues


def run_persona(*, llm: LLM, persona: dict, plan: dict, recent_turns: list[dict], tracer: Tracer,
                feedback: list[str] | None = None) -> str:
    previous = [t["text"] for t in recent_turns if t.get("from") == "talon"]
    avoid = sorted({_first_word(t) for t in previous[-3:]} - {""} | STOCK_OPENERS)
    payload = {"handler_plan": {k: plan[k] for k in ("goal", "tactic", "instructions_for_persona")},
               "tripwire_codes_you_may_use": plan.get("tripwire_tokens", []),
               "recent_turns": recent_turns,
               "already_mentioned": mentioned_details(persona, previous),
               "turn_number": len(previous) + 1,
               "avoid_starting_with": avoid}
    if feedback:
        payload["your_last_draft_was_rejected_because"] = feedback
    system = SYSTEM.format(name=persona.get("name", ""), age=persona.get("age", ""), city=persona.get("city", ""),
                           state=persona.get("state", ""), voice="; ".join(persona.get("voice", [])),
                           background="; ".join(persona.get("background", [])))
    messages = [{"role": "system", "content": system}, user_payload(payload)]

    text = _draft(llm, messages, tracer, retry=bool(feedback))
    issues = style_issues(text, persona, previous)
    if issues:  # one quick rewrite; persona calls are cheap compared with a safety retry
        tracer.step("persona", "rejection", {"why": "sounds repetitive", "violations": issues, "draft": text})
        payload["your_last_draft_was_rejected_because"] = issues
        text = _draft(llm, [messages[0], user_payload(payload)], tracer, retry=True)
    return text


def _draft(llm: LLM, messages: list[dict], tracer: Tracer, retry: bool) -> str:
    resp = llm.chat(agent="persona", messages=messages, max_tokens=120, temperature=0.8)
    text = re.sub(r"<think>.*?</think>", "", resp.content or "", flags=re.S).strip().strip('"').strip()
    text = no_dashes(text)  # an em dash in a text message is a giveaway; never rely on the model to skip it
    tracer.step("persona", "output", {"draft": text, "retry": retry}, resp.latency_ms)
    return text
