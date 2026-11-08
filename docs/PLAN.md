# Talon — Build and Demo Plan

Nov 7, 2026 · Working plan for the hackathon build: what we're building, how it meets both tracks, the live demo setup, status and who builds what.

## Summary

**When a T-Mobile customer gets a scam text, one tap hands the conversation to Talon. Talon's agents keep the scammer talking, extract their payment details and callback numbers, shut the campaign down across the network, and show the customer who they protected.**

Two tracks judge it: T-Mobile ("protect customers from scams in ways we haven't thought of yet") and the NVIDIA Nemotron track ("use Nemotron beyond a chatbot"). The concept is strong for both. The risk is execution and scope, not the idea: a flawless 3-minute demo that survives a judge going off script beats a long list of half-working components.

## How Talon meets the briefs

### T-Mobile

| Prompt | Talon | Strength |
| --- | --- | --- |
| Ways we haven't thought of yet | Customers start the counter-attack; their consent is the trigger | Strong, if pitched as crowdsourcing (below) |
| Detection is core, not the whole product | Triage is 1 of 6 agents | Strong |
| Beyond classification: safeguards, customer experiences | Takeover, auto-block on other phones, impact card | Strong |
| Clear next steps | Taxonomy `next_steps` on every warning | Good |
| Honest confidence | Confidence on the warning; gold set and its hard subset reported separately | Good, if the numbers are real |
| Privacy by design | Customer data never enters a model prompt; persona invents every detail; takeover only on a tap | Strong |

### NVIDIA Nemotron

Required: beyond a chatbot, multi-step workflows, tool integration (external APIs and services), real-world applicability. What wins: multi-agent systems, agentic RAG (deciding *when* to retrieve), ReAct loops, tool calling, multi-modal agents, agent simulation and eval.

| Pattern | Talon | Status |
| --- | --- | --- |
| Multi-agent | Triage, Extractor, Handler, Persona, Safety, Campaign Analyst | Built (offline) |
| Agentic RAG | Triage retrieves similar scams only when unsure; Handler looks up campaign memory only for new indicators | Built; embeddings next |
| ReAct | Handler: reason → act → observe, max 4 tool calls per turn | Built |
| Tool calling | Handler and Analyst tools | Built, but internal only (see gap below) |
| Simulation and eval | Self-play arena: scammer agent vs Talon, scored by a judge agent | Not started; treat as must-have |
| Multi-modal | Scam images (QR codes, fake invoices) read by a Nemotron vision model | Not started; after the core |

**Gap: external tool integration.** Our data rules forbid real scam links and numbers, so real reputation lookups can't run on demo data. Fixes: NVIDIA services as tools (safety model, embeddings), real lookups that work on fictional data (area code to region), and mock partner APIs (carrier blocklist, exchange wallet flag, bank alert) as a separate HTTP service with real interfaces, labeled as mocks.

**Use the whole Nemotron stack** (slide 12, "models, datasets, techniques, tooling"): Nano and Super, the safety model, embeddings, possibly the vision model; Nemotron-Personas-USA for personas; NeMo Data Designer for synthetic data; LangGraph (the official tutorial uses it); Brev for self-hosting the final demo runs.

## Risks and how we answer them

1. **Scope.** The docs describe about 15 components. Cut voice, canaries, replay, the scam-bot probe, separate TypeScript workers and fine-tuning. Move them to the roadmap slide.
2. **"T-Mobile already runs honeypots."** Lead with the network effect: every customer becomes a sensor, and even 1% of customers tapping beats any honeypot's volume.
3. **Retaliation.** The scammer has the customer's real number. When a takeover ends, Talon offers to turn on account protection (port-out / SIM-swap lock, Scam Shield blocks). "The customer ends up better protected than before they tapped."
4. **"Burning a campaign" must be concrete.** Show the link blocked, the callback number blocked, the wallet reported to a (mock) partner, and other customers warned.
5. **Multi-agent theater.** Make decisions visible: the handler targets what's missing, the safety reviewer rejects and rewrites, the analyst refuses to burn on weak evidence. Arena numbers prove it beyond one lucky run.
6. **Latency.** Several model calls per turn. Persona and safety stay on the reply path; the analyst runs in the background; a typing indicator covers the wait. Measure early on real Nemotron.
7. **Synthetic-data skepticism.** Report the hand-written gold set and its hard subset separately; never put an inflated synthetic-split score on a slide.

## The agents

Per scammer message, in a LangGraph:

| # | Agent | Job | Tools and decisions | Model |
| --- | --- | --- | --- | --- |
| 1 | Triage | Scam or not, category, confidence, reason; next steps come from the taxonomy | Calls `search_similar_scams` only when unsure (agentic RAG) | Nano, reasoning off |
| 2 | Extractor | Indicators from each turn, as JSON | Code drops anything not in the text or in the wrong format | Nano |
| 3 | Handler | Plans each reply: have vs need, which tactic | ReAct loop: `get_intel_gaps`, `get_category_playbook`, `lookup_indicator`, `choose_tactic`, `issue_tripwire`, `flag_bot_suspected`, `end_takeover` | Nano, reasoning on |
| 4 | Persona | Writes the reply in character | No tools; never sees customer data | Nano, reasoning off |
| 5 | Safety | Approves or rejects each reply | Rules, then the Nemotron safety model; rejects back to the Persona (2 retries, then a canned safe line) | Safety model |
| 6 | Campaign Analyst | Links campaigns, burns them, warns customers, writes the impact card | `link_to_campaign`, `burn_campaign` (refuses weak evidence), `warn_customers`, partner APIs (planned) | Super or Nano |

Arena (planned): **Scammer simulator** plays a category with hidden secrets; **Judge** scores secrets extracted, turns to the payment method, leaks (must be 0) and persona consistency.

Every step writes an `agent_step` row (agent, kind, content, latency). The trace is a core feature: it's what NVIDIA judges watch.

## Live demo: three screens

Judges play both sides from their own phones; the laptop shows Talon working.

```text
 Judge 1's phone              Judge 2's phone              Laptop (big screen)
 /scammer                     /phone                       /dashboard
 texting UI + scam card       texting UI + Talon warning   scam feed · agent trace · conversation · campaign
        │ send text                  │ tap Handle / Stop              │ watch only
        ▼                            ▼                                ▼
 ┌───────────────────────────────────────────────────────────────────────────────┐
 │ SpacetimeDB on Maincloud (talon-prod): live subscriptions for every screen    │
 └───────────────────────────────────▲───────────────────────────────────────────┘
                                     │ reads new texts and taps; writes results and trace
                            Python engine on the laptop ──► Nemotron (build.nvidia.com or Brev)
```

**Phones never connect to the laptop.** They load pages from Vercel and talk only to SpacetimeDB's cloud; the engine only makes outbound connections. Venue Wi-Fi isolation, firewalls and tunnels don't matter, and phones can use cellular data.

### Screens

**Scammer phone (`/scammer`).** iMessage-style thread with "Customer". A scam card with fictional details to use (link, wallet, callback number) and a quick-start opener. Replies come from "the customer" (the persona); nothing mentions Talon. A typing bubble shows while agents work.

**Customer phone (`/phone`).** The scam text arrives with Talon's warning: category, confidence, reason, next steps, and **[Delete] [Report] [Let Talon handle it]**. After the tap, a bar shows "Talon is handling this · Stop", and the judge watches both sides live, with Talon's replies labeled. At the end, the impact card and an offer to turn on account protection.

**Dashboard (`/dashboard`).**

| Panel | Shows |
| --- | --- |
| Scam feed | Every incoming text as it arrives: "New scam detected · toll · 97%", including ones never taken over |
| Agent pipeline (center) | Six agent cards; the active one lights up and its thoughts, tool calls, results and rejections stream in |
| Conversation | Mirror of the thread, scammer vs Talon |
| Intel and campaign | Indicators popping in, campaign active → **BURNED**, customers warned, tripwire code |
| Second customer | A phone mock that receives the same scam and shows **Blocked** (scripted button) |
| Joining | Two QR codes, "Play the scammer" and "Play the customer", carrying a room code |

### One round, step by step

1. Scammer sends a text: `scammer_send` (new, open to phones) writes an outbox row.
2. Engine picks it up (polling about every 0.5 s): `receive_message` → triage → `set_triage`. Customer phone shows the warning; dashboard feed shows the new scam.
3. Customer taps: `request_takeover` (already open) creates the session; the engine sees it.
4. Each turn: extractor → handler → persona → safety, each writing `add_agent_step`; then `add_turn` with Talon's reply, which appears on the scammer phone.
5. In the background, the analyst links, burns and alerts: dashboard shows BURNED; the second customer is blocked.
6. Stop, or the handler ends it: the impact card appears on the customer phone.

## Status

| Piece | Status |
| --- | --- |
| Taxonomy, gold test set, validator, dataset import | Done (earlier PRs) |
| SpacetimeDB module with runtime tables and reducers | Done (PR #7) |
| Next.js app with Google sign-in | Done; home page blank |
| Agent engine (`agents/`): six agents, handler tool loop, safety retry, trace, campaign burn, impact card, CLI, 38 tests | Done on FakeLLM (offline) |
| Engine on real Nemotron | Not started: needs the API key and verified model IDs |
| Engine writing to SpacetimeDB | Not started |
| Demo pages (`/scammer`, `/phone`, `/dashboard`) | Not started |
| Arena, partner API mocks, image scams, baseline and metrics | Not started |

## What needs building

### SpacetimeDB module (Umair)

- `agent_step` table and `add_agent_step` reducer (the dashboard trace depends on it).
- `scammer_send(room, text)`, open to phones, writing a `scammer_outbox` row; the engine processes it, so pipeline writes stay admin-only.
- `demo_room` table: a room code pairing a scammer phone with a customer.
- Caller-chosen string IDs for indicators, so impact cards can cite them.
- Align session end states: the module uses `stopped`/`completed`, the engine uses `ended`.

### Engine (agents/)

- SpacetimeDB store: same interface as the in-memory store, writing through reducers over HTTP.
- Runner loop: polls the outbox and session changes, calls the engine; idle timeout.
- Analyst in the background; extractor alongside the handler if latency needs it.
- Real Nemotron: verify model IDs (`GET /v1/models`), the reasoning switch and the safety model's output format.
- Embedding retrieval, mock partner API service, self-play arena, keyword baseline and metrics.
- Demo controls: reset (`reset_runtime`), scripted second customer.

### Web (Abdullah)

- `/scammer`, `/phone` (mobile texting UI: bubbles, typing indicator, warning banner, impact card) and `/dashboard`.
- SpacetimeDB TypeScript bindings (`spacetime generate --lang typescript`), subscriptions filtered by room.
- QR codes and the agent-pipeline animation.

The current middleware only protects `/`, so the new pages are public by default.

### Setup and hosting

- Install the SpacetimeDB CLI; deploy the web app to Vercel; use `talon-prod` on Maincloud with an admin token for the engine.
- NVIDIA API key from build.nvidia.com; Brev for the final demo runs if rate limits or the self-hosting story call for it.

## Build order

1. Engine on real Nemotron; measure latency per turn.
2. Module changes (`agent_step`, `scammer_send`, rooms, string IDs) and the engine's SpacetimeDB store and runner.
3. Demo pages, ugly but working end to end across three devices.
4. Campaign burn made concrete: partner API mocks, second-customer block.
5. Arena and metrics panel (triage vs baseline on the gold set and hard subset; leak test; extraction yield).
6. Image scams with the vision model; personas from Nemotron-Personas-USA; move hosting to Brev.
7. Polish, rehearse with people going off script, record a backup run.

## Demo risks

- **Latency:** cover with the typing indicator; measure early.
- **Judges going off script** ("are you a bot?"): a showcase for the safety reviewer, but rehearse it.
- **Open reducers can be spammed:** room codes, rate limits, a reset button.
- **Venue internet:** recorded backup of a full run.

## Decisions needed

- [ ] SpacetimeDB as the live hub (recommended) vs a FastAPI WebSocket server on the laptop behind a tunnel.
- [ ] Who builds the demo pages: Abdullah, or someone else with his agreement.
- [ ] Second customer: scripted on the dashboard (recommended) or a third judge's phone.
- [ ] Campaign analyst in the Python engine (recommended, one process, simpler to trace) vs the TypeScript workers in ARCHITECTURE.md.
- [ ] Final model IDs, the triage threshold and the evidence rule for burning a campaign.
