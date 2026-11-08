# Talon web

Next.js app with Google sign-in (NextAuth). The home page reads live dataset tables from SpacetimeDB **Maincloud** (`talon-prod`).

## Run

```bash
cp .env.example .env.local   # then fill secrets
npm install
npm run dev
```

Open [http://localhost:3000/login](http://localhost:3000/login). You do **not** need `spacetime start` — the app talks to prod.

- `/` — dataset dashboard (taxonomy + labeled messages)
- `/heatmap` — scammer-origin density map (`inbound_message` / `session` origin coords)

If the heatmap is empty, seed demo origins:

```bash
python3 scripts/demo/takeover_smoke.py --server maincloud --db talon-prod
```

## SpacetimeDB

```env
NEXT_PUBLIC_SPACETIMEDB_URI=https://maincloud.spacetimedb.com
NEXT_PUBLIC_SPACETIMEDB_DB=talon-prod
```

Regenerate client bindings after module schema changes:

```bash
cd ../spacetimedb && npm install && cd ..
spacetime generate --lang typescript --module-path spacetimedb --out-dir web/src/module_bindings -y
```

## Google Console

Authorized redirect URI:

```text
http://localhost:3000/api/auth/callback/google
```

Authorized JavaScript origin:

```text
http://localhost:3000
```

## Layout

```text
app/
  login/          Sign in
  page.tsx        Dataset dashboard (auth required)
  heatmap/        Scammer origin heatmap (auth required)
  api/auth/       NextAuth Google handler
components/       Dataset + heatmap UI, shared AppShell
lib/auth.ts       Auth config
middleware.ts     Protects / and /heatmap
```
