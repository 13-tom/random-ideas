# Site Analysis: anatomy-livid.vercel.app

URL analyzed: https://anatomy-livid.vercel.app/en

## What it is

An interactive educational website teaching human anatomy through visual,
"artist-focused" exploration of organs using 3D models. Deployed on Vercel,
built with Next.js (confirmed via `/_next/static/...` asset paths and
`data-dpl-id` deployment marker in the HTML head).

## Structure & navigation

- Top nav: **Explore**, **Systems**, **Lessons**, **Library**, **Notes**,
  with a logo mark ("MA").
- Locale-prefixed routing (`/en`, etc.) with 12 languages supported: English,
  Spanish, Hindi, Chinese, Arabic, Portuguese, French, German, Japanese,
  Russian, Indonesian, Korean.
- Tagline: "Learning is an act of curiosity."

## Main content

**Organ Library** — nine featured organs, each with a thumbnail and a link
into a detail page:
`heart`, `brain`, `lungs`, `liver`, `kidneys`, `eyeball`, `intestine`,
`pancreas`, `skin` (visible as preloaded `/anatomy/<organ>/thumb.webp`
assets).

**Per-organ detail page** (inspected via the heart page), containing:
- An interactive 3D specimen viewer — rotate, zoom, isolate parts.
- Clickable anatomical labels/hotspots (e.g. aorta, ventricles, valves).
- A "key facts" panel (size, weight, location, function).
- Microscopic tissue close-ups.
- Comparative-anatomy callouts (e.g. heart vs. brain).
- A function/animation demo.
- Clinical notes (associated conditions).
- System context (where the organ fits in its body system).

## Notable interaction patterns

- Drag-to-rotate 3D models with zoom/scroll controls.
- Layer comparison and cross-section toggles.
- CTAs: "View lesson", "View all organs", "See the system".

## Tech notes

- Next.js app on Vercel (per-deployment static asset hashing).
- Heavy custom webfont set (12+ preloaded `.woff2` files).
- Organ imagery served as `.webp` thumbnails, preloaded for the landing view.
