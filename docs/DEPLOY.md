# Deployment: environments and keys

Three things run on demo day. No secret ever goes in git; the `*.local` files below are gitignored.

| Piece | Where it runs | Its env lives in |
| --- | --- | --- |
| Web app (phones, dashboard, Agent Reasoning) | Vercel | Vercel project settings (source: `web/.env.production.local`) |
| SpacetimeDB module | Maincloud, database `talon-prod` | none (published with the CLI by the owner) |
| Engine runner + Nemotron (vLLM) | Brev GPU `talon-gpu` | `~/Talon/.env` on the instance (source: `.env.engine.local`) |

## Keys

| Variable | Used by | Where it comes from | Owner | Status |
| --- | --- | --- | --- | --- |
| `NEXTAUTH_URL` | web | The deployed URL, e.g. `https://talon-xyz.vercel.app` | whoever deploys | after first deploy |
| `NEXTAUTH_SECRET` | web | Random 32 bytes (`openssl rand -base64 32`). Separate from dev. | — | generated in `web/.env.production.local` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | web | Google Cloud Console > Credentials > the OAuth client | Abdullah | have them; **add the prod redirect URI** (below) |
| `NEXT_PUBLIC_SPACETIMEDB_URI` / `_DB` | web | `https://maincloud.spacetimedb.com` / `talon-prod` | — | set |
| `SPACETIMEDB_HOST` / `SPACETIMEDB_DB_NAME` | engine | `https://maincloud.spacetimedb.com` / `talon-prod` | — | set |
| `SPACETIMEDB_TOKEN` | engine | Token of the engine's own identity (made with `POST /v1/identity`), which a `talon-prod` admin must authorize with `add_admin` | Umair (admin) | token made; **needs add_admin** |
| `NEMOTRON_API_KEY` | engine | The key `serve.sh` was started with: `~/.talon_key` on the Brev instance. Not a Brev account token. | — | set |
| `NEMOTRON_BASE_URL` | engine | `http://localhost:8000/v1` (engine and vLLM on the same instance) | — | set |

The Brev CLI itself uses `brev login`; nothing Brev-related goes in an env file.

## Steps

1. **Umair: authorize the engine and publish the module** (after reviewing PR #12):
   ```bash
   spacetime call --server maincloud talon-prod add_admin '{"__identity__": "0x<engine identity>"}'
   spacetime publish --server maincloud --module-path spacetimedb talon-prod -y
   ```
   The engine identity is in `agents/.engine-identity-talon-prod.txt` (not secret, but not committed). Publishing
   only adds tables and reducers; existing data stays.
2. **Google Console** (OAuth client): add `https://<deployed-host>/api/auth/callback/google` as a redirect URI and
   `https://<deployed-host>` as a JavaScript origin.
3. **Vercel:** import the repo with root directory `web`, paste the variables from `web/.env.production.local`,
   deploy, then set `NEXTAUTH_URL` to the real URL and redeploy.
4. **Brev:** `brev start talon-gpu`, copy the engine env and start both processes:
   ```bash
   brev copy .env.engine.local talon-gpu:/home/ubuntu/Talon/.env
   brev exec talon-gpu "cd ~/Talon && git pull && NEMOTRON_API_KEY=\$(cat ~/.talon_key) nohup bash agents/brev/serve.sh > ~/talon-logs/serve.out 2>&1 &"
   # when vLLM is ready:
   brev exec talon-gpu "cd ~/Talon/agents && nohup .venv/bin/python -m talon_agents.live --room HACK > ~/talon-logs/live.out 2>&1 &"
   ```
5. **Check:** open `https://<deployed-host>/demo?room=HACK` on two phones and the Agent Reasoning tab on the laptop.
   `python -m talon_agents.live_e2e --server https://maincloud.spacetimedb.com --db talon-prod --room HACK`
   exercises the whole loop from a laptop.
