# Talon web

Next.js app with Google sign-in (NextAuth).

## Run

```bash
cp .env.example .env.local   # then fill secrets
npm install
npm run dev
```

Open [http://localhost:3000/login](http://localhost:3000/login).

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
  page.tsx        Blank home + Log out (auth required)
  api/auth/       NextAuth Google handler
lib/auth.ts       Auth config
middleware.ts     Protects /
```
