# HackRadar V2 Frontend

Next.js 14 (App Router) + TypeScript + Tailwind. Talks to the FastAPI backend
on `127.0.0.1:8000` via a Next rewrite (`next.config.mjs`), so you can hit
`/api/*` from the browser without dealing with CORS.

## Setup

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000.

## Pages

- `/` — latest scan + ranked items + scan trigger
- `/scans` — scan history table
- `/scans/[id]` — single scan view
- `/items/[id]` — item detail with deep-dive Claude chat
- `/sources` — source health dashboard

## Backend

Start the FastAPI backend in a second terminal:

```bash
hackradar serve
```

(or `python -m hackradar.main serve`)
