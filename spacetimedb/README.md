# Talon SpacetimeDB module

TypeScript server module, the only module for Talon's database. It holds:

- **Runtime tables** for the "Let Talon handle it" flow (`docs/PIVOT.md`, `docs/ARCHITECTURE.md`): personas, customers, canaries, inbound messages, sessions, turns, handler plans, indicators, campaigns, insights, tripwires, probe results, customer alerts, impact cards and recorded events.
- **Reference and dataset tables:** the scam taxonomy and the labeled message dataset (`docs/TAXONOMY.md`, `docs/DATA_SPEC.md`).

The full table and reducer list is in `docs/ARCHITECTURE.md` under "Data model" and "Reducers". Column names are snake_case.

## Dataset tables

| Table | Rows from |
| --- | --- |
| `scam_category`, `legit_subtype`, `decoy_tactic`, `taxonomy_meta` | `data/taxonomy.json` |
| `dataset_message` | `data/*.jsonl` (gold set now, generated sets later) |
| `dataset_indicator` | Each message's indicators, keyed by `message_id` |
| `admin` (private) | Identities allowed to import and to run the pipeline reducers |

Dataset reducers: `import_taxonomy`, `import_messages` (replaces messages by id, so re-running is safe), `clear_dataset(split)`, `claim_admin`, `add_admin(identity)`.

## Who can call what

- Everything the pipeline writes is **admin-only**, so run the pipeline with an admin identity.
- `request_takeover` and `stop_takeover` are the customer's two taps and are **open**, so the phone app can call them.
- `set_message_origin` / `set_session_origin` store the scammer's estimated location (lat/lng, city/state, source, confidence) for the map.
- `add_turn` rejects a Talon reply if the session isn't active (the customer tapped Stop, or it completed) or if the reply failed the safety guard.

## Try a full takeover

```bash
python3 scripts/demo/takeover_smoke.py --server http://127.0.0.1:4000 --db talon-dev
```

This runs one scripted takeover through every runtime reducer and checks the guards. It clears the runtime tables first (`reset_runtime`), then leaves its rows in place so the dashboard has data to show.

## Run locally

Install the CLI (`curl -sSf https://install.spacetimedb.com | sh`), then:

```bash
spacetime start --listen-addr 127.0.0.1:4000          # keep running; matches SPACETIMEDB_HOST in .env
cd spacetimedb && npm install && cd ..
spacetime publish --server http://127.0.0.1:4000 --module-path spacetimedb talon-dev -y
python3 scripts/data/import_spacetimedb.py --server http://127.0.0.1:4000 --db talon-dev
```

Check it:

```bash
spacetime sql --server http://127.0.0.1:4000 talon-dev "SELECT COUNT(*) AS n FROM dataset_message"
```

## Maincloud (`talon-prod`)

```bash
spacetime login                                        # browser sign-in, once
spacetime publish --server maincloud --module-path spacetimedb talon-prod -y
python3 scripts/data/import_spacetimedb.py --server maincloud --db talon-prod
```

## Admins

Only admins can run the import and clear reducers.

- A new database makes its publisher the admin (`init`).
- `init` doesn't run when publishing over an existing database. In that case, the first caller of `claim_admin` becomes admin; it fails once any admin exists. `talon-prod`'s admin was claimed this way.
- An admin can add a teammate: `spacetime call --server maincloud talon-prod add_admin '{"__identity__": "0x<their identity>"}'`. They can find their identity with `spacetime login show`.
