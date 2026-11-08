# Talon agent engine

The multi-agent engine behind "Let Talon handle it". Python and LangGraph, running NVIDIA Nemotron through any
OpenAI-compatible endpoint: our own vLLM server on a Brev GPU (the demo setup), build.nvidia.com, or NIM.
Without a model key it runs on `FakeLLM`, fully offline, which is what the tests use.

## Run

```bash
cd agents
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m pytest                               # offline, no key needed
.venv/Scripts/python -m talon_agents.cli --demo              # scripted toll scam, every agent step printed
.venv/Scripts/python -m talon_agents.check                   # is the model endpoint working? (see below)
.venv/Scripts/python -m talon_agents.live --room PRACTICE    # the live demo runner against SpacetimeDB
```

Settings come from the environment or the repo-root `.env` (see `.env.example`); `--fake` forces FakeLLM.
Running the models on Brev: [docs/BREV.md](../docs/BREV.md). The live demo and its three screens:
[docs/LIVE_DEMO.md](../docs/LIVE_DEMO.md). Deployment keys: [docs/DEPLOY.md](../docs/DEPLOY.md).

## Agents

| Agent | Job | Tools and guardrails |
| --- | --- | --- |
| Triage | Scam or not, category, honest confidence, reason, with the sender's earlier texts as context | Decides **when to retrieve**: calls `search_similar_scams` only when unsure (agentic RAG). Next steps for the customer come from the taxonomy, never the model |
| Extractor | Links, numbers, emails, payment handles, wallets, gift card asks and brands from each scammer turn | Code drops anything not in the text or in the wrong format. The number the scam came from is recorded first, before the extractor runs |
| Handler | Plans each reply: what Talon has, what it still needs, which tactic | Reason, act, observe loop: `get_intel_gaps`, `get_category_playbook`, `lookup_indicator`, `choose_tactic`, `issue_tripwire`, `flag_bot_suspected`, `end_takeover` |
| Persona | Writes the reply as a synthetic person from NVIDIA Nemotron-Personas-USA | No tools, never sees customer data. Code catches repeated details, openers and pet names and asks for one rewrite |
| Safety | Checks every reply before it is sent | Deterministic rules, then the **Nemotron Safety Guard** (see below). Rejections go back to the persona with reasons; after 2 retries a canned safe line is sent |
| Campaign analyst | Links sessions into campaigns, shuts them down, warns other customers, writes the impact card and the analyst insight | `link_to_campaign`, `burn_campaign` (refuses weak evidence; applies the burn rule if the model hesitates), `warn_customers`. Every number, link and handle in the impact card and insight is checked against the data |

Every step writes an `agent_step` row (agent, kind, content, latency) for the dashboard's live trace.

### Safety agent: Nemotron Safety Guard

Every reply Talon is about to send goes through three checks, in order:

1. **Deterministic rules** (`safety_rules.py`): no links, phone numbers, emails, long numbers, code or
   attachments; no hint that it's an AI or Talon; nothing that breaks character; a length limit. Fictional
   tripwire codes the handler issued are the only exception.
2. **Llama 3.1 Nemotron Safety Guard 8B v3**, when `SAFETY_MODEL` is a guard model. The scammer's message and
   Talon's draft go in as a conversation, in the exact prompt template and 23-category taxonomy from the
   guard's model card. Talon's policy is then applied to the verdict:
   - Fraud/Deception, Manipulation, Needs Caution and Immoral/Unethical describe a decoy's job (playing a
     made-up person who believes the scammer), so they're logged on the dashboard but don't block.
   - Every other category blocks, including any the guard returns that aren't in its taxonomy.
   - The guard rates the whole conversation, so when the scammer's message is flagged too, the reply is
     re-checked on its own.
   - A missing or unreadable verdict blocks the reply (fail closed).
3. **Fallback:** if the guard can't be reached, Nemotron Nano reviews that turn with a short safety prompt,
   so a guard outage never stalls a takeover. Without a guard configured, this reviewer is the default.

Turning the guard on (it needs an 80 GB GPU alongside Nano, or NVIDIA's hosted API):

```bash
# On the Brev instance: serve Nano on :8000 and the guard on :8001
ENABLE_GUARD=1 NEMOTRON_API_KEY=$(cat ~/.talon_key) bash agents/brev/serve.sh
# In the engine's .env
SAFETY_MODEL=nvidia/Llama-3.1-Nemotron-Safety-Guard-8B-v3
SAFETY_BASE_URL=http://localhost:8001/v1
# Check: sends four labeled replies through the guard and fails if a verdict can't be read
.venv/Scripts/python -m talon_agents.check
```

## How a takeover runs

1. A text arrives for a customer. If the number was already blocked for them, or belongs to a campaign Talon
   shut down, it's blocked. Otherwise triage judges it; a scam shows the customer a T-Mobile Talon alert.
2. The customer taps **Let Talon handle it**. They can't take it back, and they never see the conversation
   or the scam's links: the full back-and-forth is on the dashboard only.
3. Each scammer turn runs the graph: extractor → handler → persona → safety (retry or fallback) → send. The
   analyst runs when new intel arrives, linking and shutting down campaigns.
4. Talon ends the takeover itself when it has what it came for (campaign shut down, nothing missing), when the
   scammer stops revealing anything new for 3 turns, or at the turn cap (6 in the live demo). The customer
   gets an impact card that explains the scam, its red flags and what to do next time, and the number is
   blocked for them.
5. Every scam attempt and everything collected goes into the scammer catalog (`scam_catalog`), keyed by the
   number it came from and kept across demo resets.

## Layout

```text
talon_agents/
  engine.py          customer flow, per-turn LangGraph, stop rules, number blocking
  agents/            triage, extractor, handler, persona, safety, analyst; base.py has the tool loop
  tools.py           tool schemas and implementations (guardrails live here)
  safety_rules.py    deterministic outbound rules
  llm.py             NemotronLLM (OpenAI-compatible) and FakeLLM
  fake_responders.py heuristic stand-ins per agent for FakeLLM
  indicators.py      indicator patterns and validation
  retrieval.py       scam-pattern retrieval (keyword overlap)
  state.py           session state and personas (data/personas.jsonl, from Nemotron-Personas-USA)
  store.py           in-memory store the engine works on, plus the agent trace
  mirror.py          copies every engine write to SpacetimeDB reducers, in order, on a background thread
  spacetime.py       SpacetimeDB HTTP client (reducers and SQL)
  live.py            live demo runner: phones' texts in, takeovers, resets, random numbers
  live_e2e.py        plays both phones against a running engine and checks the whole loop
  eval_gold.py       triage and extraction scored on the gold set against a keyword baseline
  check.py           smoke test for the configured model endpoints, including the guard
  cli.py             offline demo and interactive mode
brev/serve.sh        vLLM launcher for the Brev GPU (Nano, and the guard with ENABLE_GUARD=1)
tests/
```

## Not done yet

- The safety guard hasn't been run against a live guard model yet: `ENABLE_GUARD=1` needs testing on the A100.
- Nemotron embeddings for retrieval and campaign clustering; the self-play arena (Nemotron scammer vs Talon,
  with a Nemotron judge).
- Speed: most of each reply's 12-25 s is the handler's reasoning step.
