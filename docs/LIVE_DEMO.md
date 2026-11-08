# Running the live demo

Two judges use their own phones: one texts as the scammer, the other is the customer. The laptop shows
every agent step. Everything goes through SpacetimeDB; the phones never talk to the engine directly.

```text
scammer phone --scammer_send--> SpacetimeDB <--reducers/SQL-- engine runner (talon_agents.live)
customer phone --customer_send / request_takeover / stop_takeover--^        |
laptop: /agent-reasoning or /demo/live <--subscriptions-- every agent_step, turn, indicator, campaign
```

| Screen | URL | Who |
| --- | --- | --- |
| Scammer phone | `/demo/scammer?room=CODE` | Judge 1 |
| Customer phone | `/demo/phone?room=CODE` | Judge 2 |
| Second customer | `/demo/phone?room=CODE-2` | Nobody plays the scammer here; it's texted automatically (below) |
| Agent reasoning | `/agent-reasoning` (main dashboard tab) or `/demo/live?room=CODE` | Laptop |
| Room hub | `/demo?room=CODE` | Links to all of the above |

## Local run

```bash
# 1. Database (keep running)
spacetime start --listen-addr 127.0.0.1:4000
spacetime publish --server http://127.0.0.1:4000 --module-path spacetimedb talon-dev -y
# load the taxonomy (scripts/data/import_spacetimedb.py; it powers the warning's next steps)

# 2. Engine. --setup-admin once per database: makes an engine identity admin with your CLI login.
cd agents
.venv/Scripts/python -m talon_agents.live --server local --db talon-dev --room DEMO --setup-admin --reset --fake
#   drop --fake to use Nemotron (NEMOTRON_BASE_URL / NEMOTRON_API_KEY, see docs/BREV.md)

# 3. Web, pointed at the local database
cd web
NEXT_PUBLIC_SPACETIMEDB_URI=http://127.0.0.1:4000 NEXT_PUBLIC_SPACETIMEDB_DB=talon-dev npm run dev
```

Check the whole loop without a browser: `python -m talon_agents.live_e2e` plays both phones as non-admin
identities and fails loudly if any step breaks.

## Demo day (not done yet)

- Publish the module to Maincloud `talon-prod` (owner: Umair) and run the engine with an admin token:
  `python -m talon_agents.live --server maincloud --db talon-prod --room HACK --token <admin token>`.
- Host the web app (Vercel) so judges' phones can open it; QR codes for the two phone URLs.
- Run the engine on the Brev GPU next to vLLM for real Nemotron.

## What the phones can do

- **Scammer:** text anything (scam starters included). Talon's replies arrive once the customer hands over.
- **Customer:** text back normally. A scam gets a "T-Mobile Talon Alert: scam detected" message with
  **Let Talon handle it**, Report and Delete. During a takeover the customer's keyboard is locked (Talon is
  talking); **Stop** hands the conversation back and shows the impact card.
- **Second customer:** nobody plays the scammer, so the runner does. As soon as the first customer's scam
  is identified, the Nemotron scammer agent rewords it (keeping every link and handle) and it arrives from
  a different number; triage warns on it, and the burn later warns this customer too. Once the campaign
  is burned and someone has the second phone open (the page calls `phone_opened`; the row is dropped on
  disconnect), the scammer follows up a few seconds later from that number reusing the payment handle
  Talon extracted, and Talon blocks it on arrival with the reason. The block happens while someone watches. `--no-second-customer` turns this off; the
  dashboard button still sends one by hand.
- Open reducers (`scammer_send`, `customer_send`, `request_takeover`, `stop_takeover`, `dismiss_message`)
  need only the room code. They cap message length and rate-limit per room.
