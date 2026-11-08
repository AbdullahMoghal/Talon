"""Safety reviewer: deterministic rules first, then a Nemotron model.

Two model paths:
- Guard (SAFETY_MODEL is a guard model, e.g. Llama 3.1 Nemotron Safety Guard 8B v3): the scammer's message
  and Talon's draft go in as a conversation, in the guard's own prompt template and 23-category taxonomy.
  Talon's own policy then decides which categories block (see BLOCKING / DECOY_EXPECTED).
- Reviewer (the default): Nemotron Nano reviews the draft against a short safety prompt.
If the guard can't be reached, the reviewer takes over for that turn, so a down guard never stalls a takeover.

A rejection goes back to the persona with the reasons. The engine allows 2 retries, then sends a canned safe line.
"""

from __future__ import annotations

import re

from .. import safety_rules
from ..llm import LLM, parse_json
from ..store import Tracer

SAFE_FALLBACK = "sorry, my phone is acting up. what was that?"
TRIPWIRE_PLACEHOLDER = "[FICTIONAL TRIPWIRE CODE]"


def restore_tokens(text: str, tokens: list[str]) -> str:
    """Put each tripwire code back in its exact form. The persona texts in lowercase, so on live Nano it wrote
    "tw-5avg-c9c4-car7" and failed the exact-code check three times. Only case is forgiven: a code with any
    other change (spelled out, spaces, a swapped character) still doesn't match."""
    for token in tokens:
        text = re.sub(re.escape(token), token, text, flags=re.I)
    return text

SYSTEM = """You are a content safety reviewer. Talon's decoy persona is about to send the reply below to a
suspected scammer. Decide whether it is safe to send: no real personal data, no threats or harassment,
no instructions for anything harmful, nothing that reveals it is an AI.
[FICTIONAL TRIPWIRE CODE] marks a fake gift card or account code Talon issued on purpose to trace the
scammer. It is not real data and is safe to send.
Answer with JSON only: {"safe": true|false, "reason": "<short reason>"}"""

# The guard's taxonomy, in order (S1..S23), exactly as its model card lists it.
GUARD_CATEGORIES = [
    "Violence", "Sexual", "Criminal Planning/Confessions", "Guns and Illegal Weapons",
    "Controlled/Regulated Substances", "Suicide and Self Harm", "Sexual (minor)", "Hate/Identity Hate",
    "PII/Privacy", "Harassment", "Threat", "Profanity", "Needs Caution", "Other", "Manipulation",
    "Fraud/Deception", "Malware", "High Risk Gov Decision Making", "Political/Misinformation/Conspiracy",
    "Copyright/Trademark/Plagiarism", "Unauthorized Advice", "Illegal Activity", "Immoral/Unethical",
]

# The prompt template from the model card (nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3), sent as the user
# message; the server applies the model's chat template.
GUARD_TEMPLATE = (
    "Task: Check if there is unsafe content in the user or agent messages in the below conversation in "
    "accordance with our safety policy with the below categories. Provide a 'safe' or 'unsafe' rating for both "
    "the user message and the agent response. If there is unsafe content, please also provide a list of violated "
    "categories according to our safety policy below.\n\n"
    "<BEGIN UNSAFE CONTENT CATEGORIES>\n"
    + "".join(f"S{i}: {name}. \n" for i, name in enumerate(GUARD_CATEGORIES, 1))
    + "<END UNSAFE CONTENT CATEGORIES>\n\n"
    "<BEGIN CONVERSATION>\n\n"
    "user: {query}\n"
    "{response_block}"
    "<END CONVERSATION>\n\n"
    "Provide your safety assessment for the above conversation in the below output JSON format:\n"
    '{{"User Safety": safe or unsafe rating for the user message, "Response Safety": safe or unsafe rating for '
    'the agent response. Omit if no agent response present. "Safety Categories": a comma-separated list of '
    'applicable safety categories from the provided taxonomy. Omit if all safe.}}\n\n'
    "Do not include anything other than the output JSON in your response.\n"
    "Output JSON: "
)

# Talon's policy over the guard's taxonomy. The persona deceives scammers on purpose (a made-up person who
# "believes" them), so these describe the job, not a harm: logged, never blocking.
DECOY_EXPECTED = {"Fraud/Deception", "Manipulation", "Needs Caution", "Immoral/Unethical"}
# Everything else blocks, including anything the guard names that isn't in its taxonomy (fail closed).
BLOCKING = set(GUARD_CATEGORIES) - DECOY_EXPECTED


def guard_prompt(query: str, response: str | None = None) -> str:
    block = f"\nresponse: agent: {response}\n\n" if response is not None else "\n"
    return GUARD_TEMPLATE.format(query=query, response_block=block)


def parse_categories(raw) -> list[str]:
    """'S11: Threat, Fraud/Deception' or 'S16' -> canonical category names."""
    by_name = {c.lower(): c for c in GUARD_CATEGORIES}
    out: list[str] = []
    for part in re.split(r"[,;\n]", str(raw or "")):
        part = part.strip().strip(".").strip()
        if not part:
            continue
        code = re.match(r"^S(\d{1,2})\b\s*:?\s*(.*)$", part, re.I)
        if code:
            n, rest = int(code.group(1)), code.group(2).strip()
            name = by_name.get(rest.lower()) or (GUARD_CATEGORIES[n - 1] if 1 <= n <= len(GUARD_CATEGORIES) else part)
        else:
            name = by_name.get(part.lower(), part)
        if name not in out:
            out.append(name)
    return out


def _rating(value) -> str | None:
    v = str(value or "").strip().lower()
    return v if v in ("safe", "unsafe") else None


def _ask_guard(llm: LLM, query: str, response: str | None = None) -> tuple[dict, int]:
    resp = llm.chat(agent="safety", messages=[{"role": "user", "content": guard_prompt(query, response)}],
                    max_tokens=100, temperature=0.0)
    try:
        data = parse_json(resp.content)
    except ValueError:
        data = {}
    return ({"user": _rating(data.get("User Safety")), "response": _rating(data.get("Response Safety")),
             "categories": parse_categories(data.get("Safety Categories")), "raw": (resp.content or "")[:200]},
            resp.latency_ms)


def _guard_verdict(llm: LLM, masked: str, context: str | None) -> tuple[bool, list[str], dict, int]:
    """(passed, violations, details, latency_ms) from the guard."""
    first, ms = _ask_guard(llm, context or "(no message)", masked)
    details = {"scammer_message": first["user"], "reply": first["response"]}
    if first["user"] == "unsafe" and first["categories"]:
        details["scammer_categories"] = first["categories"]
    if first["response"] is None:
        return False, ["safety guard returned no verdict on the reply"], {**details, "raw": first["raw"]}, ms
    if first["response"] == "safe":
        return True, [], details, ms

    # The reply was flagged. The guard gives one category list for the whole conversation, so when the scammer's
    # message was flagged too, ask about the reply on its own to learn which categories are the reply's.
    cats = first["categories"]
    if first["user"] == "unsafe":
        alone, ms2 = _ask_guard(llm, masked)
        ms += ms2
        if alone["user"] == "safe":
            details["note"] = "flagged only alongside the scammer's message; the reply itself is safe"
            return True, [], details, ms
        cats = alone["categories"]
    details["reply_categories"] = cats
    if not cats:
        return False, ["safety guard flagged the reply without saying why"], details, ms
    blocking = [c for c in cats if c not in DECOY_EXPECTED]
    if blocking:
        return False, [f"safety guard: {c}" for c in blocking], details, ms
    details["note"] = f"expected for a decoy, not blocked: {', '.join(cats)}"
    return True, [], details, ms


def _reviewer_verdict(llm: LLM, masked: str, agent: str) -> tuple[bool, list[str], int]:
    resp = llm.chat(agent=agent, messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": masked}],
                    max_tokens=100, temperature=0.0)
    try:
        data = parse_json(resp.content)
    except ValueError:
        return False, ["safety model returned no verdict"], resp.latency_ms
    if "safe" in data:
        return bool(data["safe"]), ([] if data["safe"] else [str(data.get("reason") or "unsafe")]), resp.latency_ms
    return False, ["safety model returned no verdict"], resp.latency_ms


def _describe(details: dict) -> str:
    scammer = details.get("scammer_message")
    if scammer == "unsafe":
        cats = ", ".join(details.get("scammer_categories") or [])
        return "guard also rated the scammer's message unsafe" + (f" ({cats})" if cats else "")
    return f"guard rated the scammer's message {scammer}" if scammer else ""


def run_safety(*, llm: LLM, text: str, tracer: Tracer, allowed_tokens: list[str],
               forbidden_strings: list[str] | None = None, required_tokens: list[str] | None = None,
               guard: bool = False, context: str | None = None, scammer_history: str | None = None) -> dict:
    """Check a draft reply. guard: SAFETY_MODEL is a safety guard model. context: the scammer's message.
    scammer_history: everything the scammer has said, so the reply doesn't name a payment method first."""
    violations = safety_rules.check(text, allowed_tokens=allowed_tokens, forbidden_strings=forbidden_strings)
    if scammer_history is not None:
        violations += safety_rules.leading_payment(text, scammer_history)
    for token in required_tokens or []:
        if token not in text:
            violations.append(f"must include the tripwire code exactly as given, once: {token}")
    if violations:
        verdict = {"passed": False, "source": "rules", "violations": violations, "draft": text}
        tracer.step("safety", "rejection", verdict)
        return verdict

    masked = text
    for token in allowed_tokens:
        masked = masked.replace(token, TRIPWIRE_PLACEHOLDER)

    details: dict = {}
    source = "rules+model"
    if guard:
        try:
            passed, violations, details, ms = _guard_verdict(llm, masked, context)
            source = "rules+guard"
        except Exception as e:  # noqa: BLE001 - a down guard must not stall the takeover
            tracer.step("safety", "output", {"guard_unavailable": repr(e)[:200],
                                             "summary": "Safety guard unreachable; Nemotron Nano reviewed instead"})
            passed, violations, ms = _reviewer_verdict(llm, masked, agent="safety_review")
            source = "rules+model (guard unavailable)"
    else:
        passed, violations, ms = _reviewer_verdict(llm, masked, agent="safety")

    if not passed:
        # A rejection names the layer that rejected it: "guard" or "model" (rules rejections returned above).
        rejected_by = source.replace("rules+", "", 1)
        verdict = {"passed": False, "source": rejected_by, "violations": violations, "draft": text, **details}
        tracer.step("safety", "rejection", verdict, ms)
        return verdict
    if source == "rules+guard":
        extra = "; ".join(x for x in (details.get("note"), _describe(details)) if x)
        summary = "Passed rules and Nemotron Safety Guard" + (f" ({extra})" if extra else "")
    else:
        summary = "Passed rules and model review"
    verdict = {"passed": True, "source": source, "violations": [], "summary": summary, **details}
    tracer.step("safety", "output", verdict, ms)
    return verdict
