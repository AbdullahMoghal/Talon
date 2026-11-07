# Talon SpacetimeDB module

TypeScript server module. It holds the scam taxonomy and the labeled message dataset (see `docs/TAXONOMY.md` and `docs/DATA_SPEC.md`). The runtime tables from `docs/ARCHITECTURE.md` come next.

## Tables

| Table | Rows from |
| --- | --- |
| `scam_category`, `legit_subtype`, `decoy_tactic`, `taxonomy_meta` | `data/taxonomy.json` |
| `dataset_message` | `data/*.jsonl` (gold set now, generated sets later) |
| `dataset_indicator` | Each message's indicators, keyed by `message_id` |
| `admin` (private) | The identity that published the module; only it can import |

Reducers: `import_taxonomy`, `import_messages` (replaces messages by id, so re-running is safe), `clear_dataset(split)`, `claim_admin`, `add_admin(identity)`.

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
