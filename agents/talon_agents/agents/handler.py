"""Handler agent: the planner. Reasons about what we have and still need, calls tools, picks a tactic.

Runs a reason -> act -> observe loop (max 4 tool calls per turn) with reasoning on.
Output: {goal, tactic, instructions_for_persona}. The tactic is whatever choose_tactic accepted,
so the model can't slip in a tactic the taxonomy doesn't allow.
"""

from __future__ import annotations

from ..config import Settings
from ..llm import LLM, parse_json
from ..state import SessionState
from ..store import Store, Tracer
from ..taxonomy import Taxonomy
from ..tools import HANDLER_TOOLS, LINK_TACTICS, HandlerToolbox
from .base import tool_loop, user_payload

SYSTEM = """You are Talon's handler agent. A customer handed a scam conversation to Talon. A persona (a
fictional, slow, cooperative older person) replies to the scammer; you plan each reply.

Goal: keep the scammer engaged and get them to reveal what Talon needs to shut the campaign down:
links, contact numbers, payment method (wallet, payment handle, account, gift card ask) and who they claim to be.

Each turn:
1. intel_gaps in the message shows what is still missing. Call get_intel_gaps only if you need it refreshed.
2. If a NEW indicator appeared this turn, call lookup_indicator on it. Don't look up values you've seen.
3. If you don't know this category's playbook yet, or the scam changed, call get_category_playbook.
4. Always call choose_tactic with one decoy tactic and a short note before your final answer. Prefer tactics
   that target what's missing and avoid repeating a tactic that already failed.
5. If the scammer asks for gift card codes, call issue_tripwire, then choose_tactic "issue_tripwire", and tell
   the persona to say they bought the card and read out the code.
6. Call end_takeover if goals are met, the scammer has gone, or continuing is risky.

Never name a payment method the scammer hasn't mentioned (no gift cards, Zelle, Cash App, crypto or wire unless
they brought it up). A real victim doesn't suggest how to pay. To learn how they want to be paid, have the persona
ask an open question, like "is there another way to pay?".
When the scammer asks for money, the persona plays along: agrees to pay and asks exactly where, how and to whom.
On turn 1 the persona is answering the scam text itself, so first react to what it says the way a worried,
believing person would (a fraud alert: "no, i didn't buy that! what do i do?"; a prize or credit: "oh nice, how do
i get it?"; a fee or fine: "oh no, how do i pay it?"). Don't jump ahead to asking where to send money.
Don't keep asking who they are or what company they're with; the first message usually says so.
If the scammer asks for a verification code, PIN, password or username, the persona never gives one, not even a
made-up one: it says no code came through (or it can't find it) and asks them to send it again or for another way.
Only a tripwire gift card code from issue_tripwire may ever be read out.
Never give the persona real personal data. The persona invents everything.
Talon is text-only: never tell the persona to offer, ask for or agree to a phone call, video call or meeting.
To get a contact, have the persona ask for another number to text, an email or a chat handle.
instructions_for_persona must keep the persona fully in character: the persona believes the scammer and must
never sound suspicious. Never mention scams, tripwires, Talon, the handler or the plan in those instructions.
Final answer, JSON only:
{"goal": "<what this reply should get from the scammer>", "tactic": "<tactic id>",
 "instructions_for_persona": "<one or two sentences telling the persona what to say>"}"""


def run_handler(*, llm: LLM, state: SessionState, store: Store, taxonomy: Taxonomy, tracer: Tracer,
                settings: Settings, scammer_text: str, new_indicators: list[dict], turn_id: str) -> dict:
    state.chosen_tactic = None
    toolbox = HandlerToolbox(state=state, store=store, taxonomy=taxonomy)
    cat = taxonomy.category(state.category) or {}
    recent = [{"from": t["sender"], "text": t["text"]} for t in store.turns_for(state.session_id)[-6:]]
    payload = {
        "turn": state.turn_count,
        "category": state.category,
        "category_tactics": cat.get("decoy_tactics", []),
        "scammer_message": scammer_text,
        "new_indicators": [{"kind": i["kind"], "value": i["value"]} for i in new_indicators],
        "tactics_used_so_far": state.tactics_used,
        "intel_gaps": {k: v for k, v in toolbox.run("get_intel_gaps", {}).items() if k in ("collected", "missing")},
        "recent_turns": recent,
        "max_turns": settings.max_turns,
    }
    messages = [{"role": "system", "content": SYSTEM}, user_payload(payload)]
    tokens_before = len(state.tripwire_tokens)
    resp, _ = tool_loop(llm=llm, agent="handler", messages=messages, tools=HANDLER_TOOLS, run_tool=toolbox.run,
                        tracer=tracer, max_calls=settings.max_handler_tool_calls,
                        reasoning=settings.handler_reasoning != "off", reason_steps=1, max_tokens=1024,
                        reason_budget=settings.handler_reasoning_budget if settings.handler_reasoning == "budget"
                        else None)

    if state.ended:
        plan = {"goal": "end the takeover", "tactic": None, "instructions_for_persona": "", "ended": state.end_reason}
        tracer.step("handler", "output", plan, resp.latency_ms)
        return plan

    try:
        plan = parse_json(resp.content)
    except ValueError:
        plan = {}
    if not state.chosen_tactic:
        usable = [t for t in cat.get("decoy_tactics", []) if t not in LINK_TACTICS or toolbox.has_link()]
        fallback = next((t for t in usable if t not in state.tactics_used), "play_confused")
        tracer.step("handler", "rejection", {"why": "no tactic chosen with choose_tactic; using a default",
                                             "default": fallback})
        state.chosen_tactic = {"tactic": fallback, "note": "default"}

    # The scammer asked for a gift card: hand over a tripwire code and make sure the persona reads it out.
    # On live Nano the handler issued the code, then picked another tactic, so the code never reached the scammer.
    if (any(i["kind"] == "giftcard_ask" for i in new_indicators) and not state.tripwire_tokens):
        result = toolbox.run("issue_tripwire", {"kind": "giftcard"})
        tracer.step("handler", "tool_call", {"tool": "issue_tripwire", "args": {"kind": "giftcard"}, "by": "policy"})
        tracer.step("handler", "tool_result", {"tool": "issue_tripwire", "result": result})
    new_tokens = state.tripwire_tokens[tokens_before:]
    if new_tokens:
        token = new_tokens[-1]
        if state.chosen_tactic["tactic"] != "issue_tripwire" or token not in str(plan.get("instructions_for_persona")):
            tracer.step("handler", "rejection", {"why": "a tripwire code was issued this turn, so the persona reads it out",
                                                 "replaced_tactic": state.chosen_tactic["tactic"]})
            state.chosen_tactic = {"tactic": "issue_tripwire", "note": "read the tripwire code to the scammer"}
            plan = {**plan, "goal": "get the scammer to take the tripwire gift card code",
                    # Written so the persona's first-person reply follows naturally ("i got the card...");
                    # "Say you bought..." made live Nano reply "You bought the gift card".
                    "instructions_for_persona": f"Tell them in your own words that you got the gift card they asked "
                                                f"for, and read them the code from the back exactly as written: "
                                                f"{token}. Ask if it went through."}
    tactic = state.chosen_tactic["tactic"]
    plan = {
        "goal": str(plan.get("goal") or "keep the scammer talking"),
        "tactic": tactic,
        "instructions_for_persona": str(plan.get("instructions_for_persona") or taxonomy.tactics[tactic]),
        "note": state.chosen_tactic.get("note", ""),
        "tripwire_tokens": list(state.tripwire_tokens),
    }
    state.tactics_used.append(tactic)

    gaps = toolbox.run("get_intel_gaps", {})
    store.add_handler_plan(state.session_id, turn_id, {"have": gaps["collected"], "need": ", ".join(gaps["missing"]),
                                                       "tactic": tactic, "note": plan["note"]})
    tracer.step("handler", "output", plan, resp.latency_ms)
    return plan
