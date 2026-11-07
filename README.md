# Talon

AI decoy personas ("canaries") that draw in scammers, extract their links, numbers and payment details, and turn each campaign into network-wide protection. Built on NVIDIA Nemotron and SpacetimeDB.

- [PRD](docs/PRD.md) · [Architecture](docs/ARCHITECTURE.md) · [Taxonomy](docs/TAXONOMY.md) · [Data spec](docs/DATA_SPEC.md)

## Layout

```text
data/             taxonomy.json, gold_test.jsonl (D8); generated datasets land here
docs/             PRD, architecture, taxonomy, data spec
scripts/data/     validate.py, baseline.py (generation scripts come next)
scripts/smoke.py  Gate 1 check: one Nemotron call + one SpacetimeDB write
services/         Python pipeline: ingest gateway (FastAPI), Nemotron and SpacetimeDB clients
spacetime/        SpacetimeDB module (Rust): all tables and reducers
web/              Next.js app: Google sign-in + live feed dashboard
```

## Setup

```bash
cp .env.example .env            # add NVIDIA_API_KEY
cp web/.env.example web/.env.local
```

### 1. SpacetimeDB (port 3100)

Needs the [SpacetimeDB CLI](https://spacetimedb.com/install) and Rust with the `wasm32-unknown-unknown` target.

```bash
docker compose up -d spacetimedb
spacetime server add talon-local --url http://localhost:3100 --no-fingerprint
cd spacetime && spacetime publish -s talon-local talon
```

SpacetimeDB runs on 3100 because the web app uses 3000.

### 2. Python pipeline (port 8000)

```bash
pip install -r services/requirements.txt
cd services && uvicorn app:app --reload --port 8000
```

### 3. Web app (port 3000)

```bash
cd web && npm install && npm run dev
```

Set `SPACETIME_URL=http://localhost:3100` in `web/.env.local` to show live rows; leave it empty for mock data.

## Gate 1 checks

```bash
python scripts/smoke.py                         # Nemotron call + SpacetimeDB write/read
python scripts/smoke.py --list-models           # Nemotron model ids your key can use
python scripts/data/validate.py data/gold_test.jsonl
python scripts/data/baseline.py                 # keyword baseline on the gold set
```

Then send a message and watch it appear in the web app:

```bash
curl -X POST localhost:8000/ingest/message -H "Content-Type: application/json" \
  -d '{"canary_id": 1, "text": "USPS: package on hold, update address: usps-help.example/a1"}'
```
