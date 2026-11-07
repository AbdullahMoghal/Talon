# Talon — PRD

Nov 7, 2026

## Summary

**Every scam text is an invitation. Talon accepts it.** When a T-Mobile customer receives a scam, Talon warns them, and if they tap **Let Talon handle it**, Talon's agent takes over that conversation as a synthetic persona. It extracts the scammer's payment method, callback numbers and links, burns the campaign network-wide, warns or blocks every other customer the campaign is hitting, and shows the original customer the impact they had. AI decoy numbers (canaries) are a second source of the same kind of session. The hackathon build is text-first and uses Nemotron models throughout. Background and reasoning: [PIVOT.md](PIVOT.md) (adopted Nov 7, 2026).

T-Mobile is not providing data for this track, so we create our own: a scam taxonomy ([TAXONOMY.md](TAXONOMY.md)), synthetic datasets ([DATA_SPEC.md](DATA_SPEC.md)) and a baseline classifier to measure against. No real customer data is used anywhere.

### Goals

1. **Let every customer fight back:** one tap hands a scam to Talon, the customer can stop it at any time, and they see the impact they had.
2. **Burn campaigns fast:** cut time-to-burn (first takeover or canary contact to network-wide block) to minutes, then warn or block the same scam for every other customer.
3. **Beat the baseline:** improve triage accuracy over our own simple baseline (keyword rules and TF-IDF), and keep improving it with labels from takeovers and canaries (each customer tap is a free, high-quality label).
4. **Attack cash-out:** hand scammers trackable payment details (tripwires) that reveal how money leaves.
5. **Privacy by design:** Talon only acts after the customer's tap, always speaks as a synthetic persona (never the customer's real details), stores no call audio, and runs on self-hosted models.

### Non-goals

- Identifying or prosecuting individual scammers.
- Sending links, files or code to scammers, or touching their devices.
- Monitoring real customers' calls or messages beyond what Scam Shield already does.
- Building real partner integrations (retailers, exchanges, banks) during the hackathon. These are mocked.

## Users and user stories

| User | Need | How they use Talon |
| --- | --- | --- |
| T-Mobile customer | Not be scammed; understand why something was flagged; fight back | Gets a warning with the scam type and what to do, taps **Let Talon handle it**, and receives an impact card |
| Fraud and trust-and-safety analyst | Spot new campaigns early and act on them | Uses the ops dashboard: campaigns, indicators, time-to-burn, tripwire hits, report export |
| Network and blocking team | Block bad numbers and URLs with low false positives | Gets indicators with confidence scores pushed to the blocking pipeline |
| Partners: retailers, exchanges, banks (production) | Catch fraud at cash-out | Receive tripwire hits and suspected mule-account reports |
| Hackathon judges | See creativity, impact and accuracy quickly | Watch the 3-minute demo and the metrics panel |

### User stories

1. As a **customer**, when I get a scam text, I see a clear warning naming the scam type, an honest confidence and the safe next step, with Delete, Report and **Let Talon handle it**.
2. As a **customer**, after I tap **Let Talon handle it**, I can watch Talon reply for me and stop it with one tap at any time.
3. As a **customer**, when the takeover ends, I see an impact card: what the scammer was after and how many customers the campaign hit.
4. As a **customer**, when I get a text from a campaign Talon already burned, it's blocked or warned on arrival.
5. As a **customer**, I can tap "Why was this flagged?" and see a plain explanation with an honest confidence level.
6. As an **analyst**, I see each new campaign within minutes of its first takeover or canary contact, with its indicators, taxonomy category and the handler's live plan.
7. As an **analyst**, I can see which canary (and so which planting source) was contacted, so I know which lead list leaked.
8. As an **analyst**, I can export an FTC/IC3-ready case summary in one click.
9. As an **analyst**, I get an alert when Talon is talking to an AI scam bot, with what the probe revealed.
10. As the **blocking team**, I only receive indicators above a confidence threshold, each traceable back to the conversation turn it came from.

## Functional requirements

P0 = must ship for the demo. P1 = should ship. P2 = stretch or production only.

| ID | Component | Requirement | Priority |
| --- | --- | --- | --- |
| FR-0 | Data | Build the taxonomy, synthetic datasets and baseline defined in DATA_SPEC.md; all indicators fictional and non-working | P0 |
| FR-1 | Personas | Create synthetic personas from Nemotron-Personas-USA for Talon to speak as | P0 |
| FR-2 | Personas | Never let a persona contain real customer data; validate on creation | P0 |
| FR-3 | Ingest | Receive scammer texts for takeover sessions (from the scammer console) and canary numbers | P0 |
| FR-4 | Triage | Classify each inbound message: scam or not, taxonomy category, confidence, one-line reason | P0 |
| FR-5 | Triage | Report accuracy, precision, recall and F1 against the baseline on the synthetic test split, its hard negatives and the separately written gold set | P0 |
| FR-6 | Decoy agent | Reply in persona, with the tactic picked by taxonomy category; keep the scammer engaged up to a turn limit | P0 |
| FR-7 | Safety guard | Check every decoy reply for PII and leaks before sending; block and regenerate if it fails | P0 |
| FR-8 | Extraction | Pull indicators from each turn into structured JSON: URLs, phones, wallets, accounts, gift card asks, brand impersonated | P0 |
| FR-9 | Campaign engine | Cluster conversations into campaigns using embeddings plus shared indicators | P0 |
| FR-10 | Campaign engine | Compute and display time-to-burn per campaign | P0 |
| FR-11 | Customer shield | Match customer messages against burned campaigns and warn or block them on arrival, with scam type and next step | P0 |
| FR-12 | Ops dashboard | Show live sessions, the handler's plan, indicators, campaigns, time-to-burn and customers protected | P0 |
| FR-20 | Takeover | Customer phone shows the triage warning with Delete, Report and **Let Talon handle it**; the tap starts a takeover session | P0 |
| FR-21 | Takeover | The customer can stop a takeover at any time; Talon sends nothing after Stop (enforced in SpacetimeDB) | P0 |
| FR-22 | Takeover | Handler plans each turn (have, need, tactic) before the persona replies; the plan is shown live | P0 |
| FR-23 | Takeover | Impact card when a takeover ends: what the scammer was after and how many customers the campaign hit | P0 |
| FR-24 | Scammer console | Web page where a judge texts as the scammer during the demo | P0 |
| FR-25 | Self-play arena | Scam simulator vs Talon, scored by a Nemotron judge (yield, leaks, turns) | P1 |
| FR-13 | Scam-bot probe | Detect likely AI scam bots and run a scripted prompt-injection probe; log what it reveals | P1 |
| FR-14 | Tripwires | When payment is asked for, issue a mock trackable gift card code or wallet; show a hit when "redeemed" | P1 |
| FR-15 | Leaked-list tracing | Map a contacted canary to its planting source; list customers at risk from that source (simulated) | P1 |
| FR-16 | Reports | Generate an FTC/IC3-style case summary per campaign | P1 |
| FR-17 | Feedback loop | Add confirmed takeover and canary sessions to the training set and retrain triage on demand | P1 |
| FR-18 | Voice | "Let Talon answer" on an incoming scam call: streaming speech-to-text, then the same pipeline; audio is never stored | P2 |
| FR-19 | Partner APIs | Real tripwire partners, traceback requests and blocklist pushes | P2 |

## Non-functional requirements

The targets below are hackathon targets we set ourselves, not measured numbers. Adjust once the pipeline runs end to end.

| Area | Requirement | Target |
| --- | --- | --- |
| Latency | Decoy reply time for a text (triage + generate + safety check) | Under 5 s; human-like delays added on purpose |
| Latency | Time-to-burn in the demo (first contact to campaign blocked) | Under 2 min, simulated |
| Latency | Voice takeover, speech-to-text to reply (stretch) | Under 1.5 s per turn |
| Cost | Model cost per session | Tracked and shown; must stay below a set cap per campaign |
| Abuse limits | Maximum turns per conversation and conversations per campaign | Configurable; default 20 turns |
| Privacy | Real customer data in what Talon says | None; enforced at creation and on every reply |
| Privacy | Call audio | Never stored; streamed and discarded |
| Privacy | Raw session text retention | Fixed window, then deleted; indicators kept |
| Privacy | Model hosting | Self-hosted Nemotron (NIM or vLLM); no third-party model APIs for conversation content |
| Safety | Outbound content to scammers | Text only; no links, files or code ever |
| Safety | Leak rate under the attack set | 0 real-data leaks |
| Explainability | Every flag and indicator | Has a confidence score and a link to its source turn |
| Reliability | Demo | Recorded backup of the full demo run |

## Success metrics and acceptance criteria

The build is done when every P0 requirement passes its check below and the demo runs end to end twice in a row without manual fixes.

### Success metrics

| Metric | Definition | Target |
| --- | --- | --- |
| Triage F1 | Scam vs. legit on the synthetic test split, its hard negatives and the gold set, each reported separately | Above the baseline on all three |
| Category macro-F1 | Taxonomy label correct, averaged across categories | Above the baseline |
| Indicator recall | Share of labeled indicators extracted | At least 90% |
| Indicator precision | Share of extracted indicators that are real | At least 95%; false indicators cause wrongful blocks |
| Leak rate | Real-data leaks under the attack set | 0 |
| Bot-probe success | Share of simulated scam bots that reveal instructions or payment details | Report as measured |
| Time-to-burn | First takeover or canary contact to campaign blocked | Under 2 min in the demo |
| Customers protected | Simulated customers warned per burned campaign | Shown on the dashboard |

### Acceptance criteria (P0)

- [ ] The synthetic datasets pass validation: schema, indicators present in the text, and fictional-only indicators.
- [ ] A scam texted from the scammer console reaches the customer phone and is triaged with category, confidence and reason.
- [ ] Tapping **Let Talon handle it** starts a takeover; tapping Stop ends it, and no Talon reply is sent after Stop.
- [ ] The decoy replies in persona within 5 s, and every reply has passed the safety guard.
- [ ] Indicators appear on the dashboard within one turn of being mentioned.
- [ ] Two sessions hit by the same campaign are grouped into one campaign.
- [ ] A burned campaign blocks or warns the same scam on a second customer phone.
- [ ] The first customer sees an impact card when the takeover ends.
- [ ] The metrics panel shows our triage scores next to the baseline's.

## Scope and plan

Build the P0 loop first and get it running end to end. Then add the scam-bot probe and tripwires, which make the demo memorable.

### Phases

1. **Foundation:** generate the synthetic message set and personas, write the gold test set, build the baseline, stand up Nemotron hosting. Conversations, the attack set and scam-bot transcripts follow once the message pipeline works.
2. **Core loop (P0):** triage, then the decoy agent with the safety guard, then extraction, then campaign clustering. Wire into a basic dashboard.
3. **Takeover and customer shield (P0):** phone mockup with the warning and **Let Talon handle it**, takeover and Stop states, impact card, second phone with auto-block, scammer console.
4. **Wow features (P1):** scam-bot detection and probe, mock tripwires, leaked-list tracing, case report export.
5. **Evaluate and polish:** run the metrics, the attack set and the leak test, rehearse the demo, record the backup.

### Team split (3 to 4 people)

| Person | Owns |
| --- | --- |
| ML lead | Synthetic data pipeline, baseline, triage fine-tune, evaluation |
| Agent lead | Decoy agent, safety guard, extraction, scam-bot probe |
| Backend | Ingest, campaign engine, data store, APIs, tripwire mock |
| Frontend and pitch | Ops dashboard, customer mockup, demo script, slides |

### Open questions

- [ ] Is there GPU access for self-hosting and data generation, or do we use NVIDIA's hosted API for the hackathon only?
- [ ] Do we demo voice (recorded) or leave it as slides?
