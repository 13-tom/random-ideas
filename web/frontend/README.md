# KatGai Reel — frontend

Next.js (App Router) + TypeScript + Tailwind CSS frontend for KatGai Reel.
Talks to the FastAPI backend in `web/backend/` per `web/API_CONTRACT.md`.

## Stack

- Next.js 15 (App Router), React 18, TypeScript
- Tailwind CSS 3 for styling
- `@supabase/supabase-js` for client-side magic-link auth
- No component library — kept intentionally lean for Vercel's free tier

## Setup

```bash
npm install
cp .env.local.example .env.local   # fill in the three vars
npm run dev
```

Required env vars (see `.env.local.example`):

- `NEXT_PUBLIC_API_URL` — FastAPI backend base URL, no trailing slash
- `NEXT_PUBLIC_SUPABASE_URL` — Supabase project URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` — Supabase anon/public key

## Structure

- `app/page.tsx` — marketing landing page
- `app/login/page.tsx` — Supabase magic-link sign-in
- `app/upload/page.tsx` — authenticated: file upload (direct PUT to the
  presigned R2 URL, never proxied through the backend) + clip options form
- `app/jobs/page.tsx` — authenticated: list of the user's past jobs
- `app/jobs/[id]/page.tsx` — authenticated: polls job status every ~2.5s
  until `done`/`failed`, then loads and renders the clips grid
- `lib/api.ts` — thin typed client for every `web/API_CONTRACT.md` endpoint;
  attaches `Authorization: Bearer <supabase JWT>` automatically. No business
  logic lives here.
- `lib/supabase.ts` / `lib/auth-context.tsx` — browser Supabase client +
  React auth context (session, loading, signOut)
- `components/AuthGuard.tsx` — client-side redirect-to-`/login` guard used
  by every authenticated page
- `app/fonts/` — self-hosted OFL font files (Outfit, Work Sans) via
  `next/font/local`, so the production build never depends on reaching
  Google Fonts at build time

## Build

```bash
npm run build
```

## Deploying

Targets Vercel's free tier. Set the three env vars above in the Vercel
project settings before deploying.
