# Talon — PRD

Nov 7, 2026

## Summary

Talon is a carrier-level system of AI decoy personas (canaries) on unused T-Mobile numbers. Canaries draw in scammers, extract their indicators (URLs, phone numbers, wallets, payment asks, scripts) and shut each campaign down network-wide. The hackathon build is text-first and uses Nemotron models throughout.

T-Mobile is not providing data for this track, so we create our own: a scam taxonomy ([TAXONOMY.md](TAXONOMY.md)), synthetic datasets ([DATA_SPEC.md](DATA_SPEC.md)) and a baseline classifier to measure against. No real customer data is used anywhere.

### Goals

1. **Burn campaigns fast:** cut time-to-burn (first canary contact to network-wide block) to minutes.
2. **Protect real customers first:** warn customers who are likely on the same leaked lead list before the scam reaches them.
3. **Beat the baseline:** improve triage accuracy over our own simple baseline (keyword rules and TF-IDF), and keep improving it with labels from canaries.
4. **Attack cash-out:** hand scammers trackable payment details (tripwires) that reveal how money leaves.
5. **Privacy by design:** no real customer data in canaries, no call audio stored, models self-hosted.

### Non-goals

- Identifying or prosecuting individual scammers.
- Sending links, files or code to scammers, or touching their devices.
- Monitoring real customers' calls or messages beyond what Scam Shield already does.
- Building real partner integrations (retailers, exchanges, banks) during the hackathon. These are mocked.

## Users and user stories

| User | Need | How they use Talon |
| --- | --- | --- |
| T-Mobile customer | Not be scammed; understand why something was flagged | Gets a warning on a matching message, with the scam type and what to do |
| Fraud and trust-and-safety analyst | Spot new campaigns early and act on them | Uses the ops dashboard: campaigns, indicators, time-to-burn, tripwire hits, report export |
| Network and blocking team | Block bad numbers and URLs with low false positives | Gets indicators with confidence scores pushed to the blocking pipeline |
| Partners: retailers, exchanges, banks (production) | Catch fraud at cash-out | Receive tripwire hits and suspected mule-account reports |
| Hackathon judges | See creativity, impact and accuracy quickly | Watch the 3-minute demo and the metrics panel |

### User stories

1. As a **customer**, when I get a text matching a burned campaign, I see a clear warning naming the scam type and the safe next step, so I don't reply or pay.
2. As a **customer**, I can tap "Why was this flagged?" and see a plain explanation with an honest confidence level.
3. As an **analyst**, I see each new campaign within minutes of its first canary contact, with its indicators and taxonomy category.
4. As an **analyst**, I can see which canary (and so which planting source) was contacted, so I know which lead list leaked.
5. As an **analyst**, I can export an FTC/IC3-ready case summary in one click.
6. As an **analyst**, I get an alert when a canary is talking to an AI scam bot, with what the probe revealed.
7. As the **blocking team**, I only receive indicators above a confidence threshold, each traceable back to the conversation turn it came from.

## Functional requirements

P0 = must ship for the demo. P1 = should ship. P2 = stretch or production only.

| ID | Component | Requirement | Priority |
| --- | --- | --- | --- |
| FR-0 | Data | Build the taxonomy, synthetic datasets and baseline defined in DATA_SPEC.md; all indicators fictional and non-working | P0 |
| FR-1 | Canary registry | Create canary personas from Nemotron-Personas-USA, each with a unique ID, number and planting source | P0 |
| FR-2 | Canary registry | Never let a persona contain real customer data; validate on creation | P0 |
| FR-3 | Ingest | Receive inbound texts to canary numbers (simulated from our synthetic message set) | P0 |
| FR-4 | Triage | Classify each inbound message: scam or not, taxonomy category, confidence, one-line reason | P0 |
| FR-5 | Triage | Report accuracy, precision, recall and F1 against the baseline on the synthetic test split, its hard negatives and the separately written gold set | P0 |
| FR-6 | Decoy agent | Reply in persona, with the tactic picked by taxonomy category; keep the scammer engaged up to a turn limit | P0 |
| FR-7 | Safety guard | Check every decoy reply for PII and leaks before sending; block and regenerate if it fails | P0 |
| FR-8 | Extraction | Pull indicators from each turn into structured JSON: URLs, phones, wallets, accounts, gift card asks, brand impersonated | P0 |
| FR-9 | Campaign engine | Cluster conversations into campaigns using embeddings plus shared indicators | P0 |
| FR-10 | Campaign engine | Compute and display time-to-burn per campaign | P0 |
| FR-11 | Customer shield | Match customer messages against burned campaigns and show a warning with scam type and next step | P0 |
| FR-12 | Ops dashboard | Show live campaigns, indicators, contacted canaries, time-to-burn and customers protected | P0 |
| FR-13 | Scam-bot probe | Detect likely AI scam bots and run a scripted prompt-injection probe; log what it reveals | P1 |
| FR-14 | Tripwires | When payment is asked for, issue a mock trackable gift card code or wallet; show a hit when "redeemed" | P1 |
| FR-15 | Leaked-list tracing | Map a contacted canary to its planting source; list customers at risk from that source (simulated) | P1 |
| FR-16 | Reports | Generate an FTC/IC3-style case summary per campaign | P1 |
| FR-17 | Feedback loop | Add confirmed canary conversations to the training set and retrain triage on demand | P1 |
| FR-18 | Voice canary | Streaming speech-to-text, then the same pipeline; audio is never stored | P2 |
| FR-19 | Partner APIs | Real tripwire partners, traceback requests and blocklist pushes | P2 |

## Non-functional requirements

The targets below are hackathon targets we set ourselves, not measured numbers. Adjust once the pipeline runs end to end.

| Area | Requirement | Target |
| --- | --- | --- |
| Latency | Decoy reply time for a text (triage + generate + safety check) | Under 5 s; human-like delays added on purpose |
| Latency | Time-to-burn in the demo (first contact to campaign blocked) | Under 2 min, simulated |
| Latency | Voice canary, speech-to-text to reply (stretch) | Under 1.5 s per turn |
| Cost | Model cost per canary conversation | Tracked and shown; must stay below a set cap per campaign |
| Abuse limits | Maximum turns per conversation and conversations per campaign | Configurable; default 20 turns |
| Privacy | Real customer data in canaries | None; enforced at creation and on every reply |
| Privacy | Call audio | Never stored; streamed and discarded |
| Privacy | Raw canary text retention | Fixed window, then deleted; indicators kept |
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
| Time-to-burn | First canary contact to campaign blocked | Under 2 min in the demo |
| Customers protected | Simulated customers warned per burned campaign | Shown on the dashboard |

### Acceptance criteria (P0)

- [ ] The synthetic datasets pass validation: schema, indicators present in the text, and fictional-only indicators.
- [ ] A message from our synthetic set sent to a canary gets triaged with category, confidence and reason.
- [ ] The decoy replies in persona within 5 s, and every reply has passed the safety guard.
- [ ] Indicators appear on the dashboard within one turn of being mentioned.
- [ ] Two canaries hit by the same campaign are grouped into one campaign.
- [ ] A burned campaign triggers a warning on the customer phone mockup.
- [ ] The metrics panel shows our triage scores next to the baseline's.

## Scope and plan

Build the P0 loop first and get it running end to end. Then add the scam-bot probe and tripwires, which make the demo memorable.

### Phases

1. **Foundation:** generate the synthetic message set and personas, write the gold test set, build the baseline, stand up Nemotron hosting. Conversations, the attack set and scam-bot transcripts follow once the message pipeline works.
2. **Core loop (P0):** triage, then the decoy agent with the safety guard, then extraction, then campaign clustering. Wire into a basic dashboard.
3. **Customer shield (P0):** matching against burned campaigns, plus the phone mockup warning.
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
