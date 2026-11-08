# Talon agent engine

The multi-agent takeover engine behind "Let Talon handle it". Python, LangGraph, Nemotron through any
OpenAI-compatible endpoint (build.nvidia.com, OpenRouter, or vLLM/NIM on Brev). Without an API key it runs
on `FakeLLM`, fully offline.

## Run

```bash
cd agents
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt     # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m talon_agents.cli --demo              # scripted toll scam, watch every agent step
.venv/Scripts/python -m talon_agents.cli                     # you type as the scammer
.venv/Scripts/python -m pytest
```

Settings come from the environment or the repo-root `.env` (see `.env.example`). `--fake` forces FakeLLM.

Models run on Brev: see [docs/BREV.md](../docs/BREV.md). `brev/serve.sh` starts vLLM on the GPU instance and
`python -m talon_agents.check` confirms the endpoint does plain replies, JSON, tool calls and `/think`.

## Agents

| Agent | Job | Tools / decisions |
| --- | --- | --- |
| Triage | Scam or not, category, confidence, reason. Customer next steps come from the taxonomy | Decides **when to retrieve**: calls `search_similar_scams` only when unsure (agentic RAG) |
| Extractor | Indicators from each scammer turn, as JSON | Code drops anything not in the text or in the wrong format |
| Handler | Plans each reply: have vs need, which tactic | Reason → act → observe loop, max 4 calls: `get_intel_gaps`, `get_category_playbook`, `lookup_indicator`, `choose_tactic`, `issue_tripwire`, `flag_bot_suspected`, `end_takeover` |
| Persona | Writes the reply in character from the plan | No tools; never sees customer data |
| Safety | Rules first, then the Nemotron safety model | Rejects and sends back with reasons (2 retries, then a canned safe line) |
| Campaign Analyst | Links sessions into campaigns, burns them, warns customers, writes the impact card | `link_to_campaign`, `burn_campaign` (refuses weak evidence), `warn_customers`; impact-card numbers checked against the data |

Every step writes an `agent_step` row (agent, kind, content, latency) for the live trace.

## Layout

```text
talon_agents/
  engine.py          customer flow + per-turn LangGraph + stop conditions
  agents/            triage, extractor, handler, persona, safety, analyst; base.py has the tool loop
  tools.py           tool schemas and implementations (guardrails live here)
  llm.py             NemotronLLM (OpenAI-compatible) and FakeLLM
  fake_responders.py heuristic stand-ins per agent for FakeLLM
  safety_rules.py    deterministic outbound rules
  indicators.py      indicator patterns and validation
  retrieval.py       scam-pattern retrieval (keyword now, Nemotron embeddings next)
  store.py           InMemoryStore + Tracer; a SpacetimeDB store comes next
  check.py           smoke test for the configured model endpoint(s)
  cli.py
brev/serve.sh        vLLM launcher for the Brev GPU instance
tests/
```

## Not done yet

- Real Nemotron runs: nothing has run on Brev yet; `talon_agents.check` is the first thing to run there.
- SpacetimeDB store (needs `agent_step` and string indicator IDs in the module; talk to Umair).
- Embedding retrieval, mock partner APIs, self-play arena, idle-timeout stop condition.
