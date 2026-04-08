# HackRadar V2 — Getting Started

Zero-to-running walkthrough. Every step names the exact file, the exact line, and the exact thing to click. No guessing.

---

## Step 0 — Where you are

All paths in this guide are absolute so you can't get lost:

```
/Users/rehan/Documents/HackRadar/                   ← repo root
├── .env.example                                    ← template you'll copy
├── .env                                            ← YOU CREATE THIS in Step 2
├── requirements.txt                                ← python deps
├── hackradar/                                      ← backend code
│   ├── config.py                                   ← reads env vars
│   ├── main.py                                     ← CLI entry (scan, serve, db)
│   └── api.py                                      ← FastAPI app
├── frontend/                                       ← Next.js app
│   ├── package.json
│   └── app/                                        ← pages
├── migrations/0001_initial.sql                     ← DB schema
└── tests/                                          ← 88 tests
```

Your SQLite DB will land at `~/.hackradar/hackradar.db` (auto-created).

---

## Step 1 — Get the three API keys

Open each link in a browser. Copy each key to a scratch file. You'll paste them into `.env` in Step 2.

### Key 1 of 3: Groq (free)

What it's for: **Pass 1 triage** — a cheap 8B Llama model that filters obvious noise before anything expensive runs.

1. Go to **https://console.groq.com/**
2. Sign in (email or GitHub).
3. Left sidebar → **API Keys**.
4. Click **Create API Key**.
5. Name it `hackradar`. Click **Submit**.
6. Copy the value that starts with `gsk_...`. **You can't see it again after closing the dialog.**
7. Paste it into a scratch text file for now, labeled `GROQ_API_KEY`.

Free tier: ~14,400 requests/day on `llama-3.1-8b-instant`. You'll use maybe 30/day.

---

### Key 2 of 3: Cerebras (free)

What it's for: **Pass 2 full scoring** — Qwen 3 32B, gives the 4-criterion scores and hackathon pitches.

1. Go to **https://cloud.cerebras.ai/**
2. Sign in.
3. Top-right user menu → **API Keys** (or left sidebar depending on layout).
4. Click **Generate API Key**.
5. Name it `hackradar`. Click **Create**.
6. Copy the value that starts with `csk-...`. Paste it to your scratch file as `CEREBRAS_API_KEY`.

Free tier: 30 requests/min. HackRadar paces Pass 2 to stay under this (see `PASS2_INTER_BATCH_SLEEP_S=2.0` in `.env.example`).

---

### Key 3 of 3: Anthropic (paid — do the safety step first)

What it's for: **Pass 3 deep-dive chat** — Claude Opus 4.6 streams the chat-with-item replies.

**SAFETY FIRST — set a hard spending cap before creating a key:**

1. Go to **https://console.anthropic.com/**
2. Sign in.
3. Left sidebar → **Settings** → **Limits** (or **Billing → Limits**).
4. Find **Monthly spend limit**. Set it to **$10.00**. Click **Save**.
5. If it asks for a separate hard cap vs soft cap, set BOTH to $10.

Now the key:

6. Left sidebar → **API Keys**.
7. Click **Create Key**.
8. Name it `hackradar`. Click **Create Key**.
9. Copy the value that starts with `sk-ant-...`. Paste it to your scratch file as `ANTHROPIC_API_KEY`.

Expected spend: single-digit cents per chat turn. The app enforces 20 user turns/hour by default.

---

### Keys 4 & 5 (optional but recommended)

**GitHub token** — bumps the enrichment rate limit from 60/hr to 5000/hr. Without it, scans of >60 GitHub-linked items will start failing the enrichment phase.

1. Go to **https://github.com/settings/tokens**
2. **Generate new token** → **Generate new token (classic)**.
3. Note: `hackradar enrichment`. Expiration: 90 days (or whatever).
4. **Do NOT check any scopes.** Read-only public access is all we need.
5. Scroll down, click **Generate token**.
6. Copy the `ghp_...` value to your scratch file as `GITHUB_TOKEN`.

**HuggingFace token** — helps enrichment on HF model cards.

1. Go to **https://huggingface.co/settings/tokens**
2. Click **+ Create new token**.
3. Name: `hackradar`. Type: **Read**.
4. Click **Create token**.
5. Copy the `hf_...` value to your scratch file as `HF_TOKEN`.

---

## Step 2 — Create `.env` with your keys

You now have 3–5 keys in a scratch file. Time to paste them into the real config.

### 2a. Copy the template

In a terminal:

```bash
cd /Users/rehan/Documents/HackRadar
cp .env.example .env
```

This creates `/Users/rehan/Documents/HackRadar/.env`. This file is gitignored — it will never get committed.

### 2b. Open `.env` in your editor

```bash
open -a "Visual Studio Code" /Users/rehan/Documents/HackRadar/.env
# or:
nano /Users/rehan/Documents/HackRadar/.env
```

### 2c. Fill in the real values

You'll see this exact content. Replace each `your_..._here` placeholder with the matching key from your scratch file.

**Before (what's in `.env.example` and your freshly copied `.env`):**

```env
# HackRadar V2 — environment variables. Copy to .env and fill in.

# Required: Pass 1 (triage)
GROQ_API_KEY=gsk_your_groq_key_here

# Required: Pass 2 (full scoring)
CEREBRAS_API_KEY=csk_your_cerebras_key_here

# Required: Pass 3 (chat-with-item)
# Set a $10/mo hard spending cap in the Anthropic console for safety.
ANTHROPIC_API_KEY=sk-ant-your_anthropic_key_here

# Optional fallbacks
OPENROUTER_API_KEY=
HF_TOKEN=

# Optional: increases GitHub API rate limit from 60/hr to 5000/hr for enrichment
GITHUB_TOKEN=
```

**After (what yours should look like — values are examples, use your real keys):**

```env
GROQ_API_KEY=gsk_abc123xyz...real...value...here
CEREBRAS_API_KEY=csk-abc123xyz...real...value...here
ANTHROPIC_API_KEY=sk-ant-api03-abc...real...value...here

OPENROUTER_API_KEY=
HF_TOKEN=hf_abc123xyz...optional
GITHUB_TOKEN=ghp_abc123xyz...optional
```

Rules:
- **No quotes** around values. `GROQ_API_KEY=gsk_abc` — NOT `GROQ_API_KEY="gsk_abc"`.
- **No space** around `=`.
- Leave a key blank (e.g. `OPENROUTER_API_KEY=`) if you don't have one.

Save the file. Close the editor.

### 2d. Verify it loads

```bash
cd /Users/rehan/Documents/HackRadar
python3 -c "from hackradar import config; print('missing:', config.validate_keys())"
```

**Expected output:**
```
missing: []
```

If you see `missing: ['GROQ_API_KEY', ...]`:
- Check `.env` is at `/Users/rehan/Documents/HackRadar/.env` (NOT in `hackradar/` subfolder)
- Check the lines have no quotes, no trailing spaces
- Re-run the command

---

## Step 3 — Install Python dependencies

```bash
cd /Users/rehan/Documents/HackRadar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.venv/` is gitignored. You'll need to `source .venv/bin/activate` every new terminal session.

**Verify:**
```bash
python -c "import hackradar.api, hackradar.db; print('ok')"
```
Should print `ok`.

---

## Step 4 — Run the test suite

**This is your smoke test.** If all 88 pass, the code is healthy before you spend any API credits.

```bash
cd /Users/rehan/Documents/HackRadar
source .venv/bin/activate
python -m pytest
```

**Expected output (last line):**
```
============================== 88 passed in 1.xx s ==============================
```

If anything fails: **stop**. Read the error. Common causes:
- Missing `.venv` activation → `which python` should show `.venv/bin/python`
- Missing dep → `pip install -r requirements.txt` again
- Stale `__pycache__` → `find . -name __pycache__ -exec rm -rf {} +`

---

## Step 5 — Initialize the database

```bash
cd /Users/rehan/Documents/HackRadar
python -m hackradar.main db init
```

**Expected output:**
```
DB initialized at /Users/rehan/.hackradar/hackradar.db
```

The schema comes from `/Users/rehan/Documents/HackRadar/migrations/0001_initial.sql`. Idempotent — safe to re-run.

**Verify the DB file exists:**
```bash
ls -la ~/.hackradar/hackradar.db
```

---

## Step 6 — Dry-run scan (no API spend)

Test the scrape + scoring pipeline against ONE source, without writing to the DB.

```bash
cd /Users/rehan/Documents/HackRadar
python -m hackradar.main scan --source meta_ai_blog --dry-run
```

**What this does:**
1. Reads `.env`
2. Scrapes https://ai.meta.com/blog/ (via `hackradar/sources/meta_ai_blog.py`)
3. Runs Pass 1 triage via Groq (real API call — maybe $0.0001)
4. Runs Pass 2 scoring via Cerebras (real API call — free tier)
5. Prints the top results to stdout
6. Writes nothing to the DB

**Expected output (example):**
```
2026-04-08 ... [INFO] hackradar: Scan window: ... → ... (48 hours)
2026-04-08 ... [INFO] hackradar: [meta_ai_blog] 3 items scraped
2026-04-08 ... [INFO] hackradar: Phase 2 dedup: 3 → 3 items
2026-04-08 ... [INFO] hackradar: Pass 1 triage: 3 items total, 3 high-trust bypass, 0 to triage
2026-04-08 ... [INFO] hackradar: Pass 2 complete: 3/3 items scored

======================================================================
  HackRadar scan: 3 items scored. Showing top 3.
======================================================================

#1  [8.45]  Some Meta AI Research Drop
    Open=9 Novelty=9 Wow=8 Build=8
    meta_ai_blog  |  https://ai.meta.com/blog/...
    Summary: ...
    IDEA: ...
```

If this runs cleanly, your API keys are live and the pipeline works. Go to Step 7.

If it errors: check the error message. 401 → bad key. 429 → rate limit (rare on first run). Connection error → network.

---

## Step 7 — Full scan (all sources)

```bash
cd /Users/rehan/Documents/HackRadar
python -m hackradar.main scan
```

Scans ~25 sources over the last 48 hours. Takes 30 seconds to 3 minutes. Writes to `~/.hackradar/hackradar.db`.

After it finishes, check source health:
```bash
python -m hackradar.main db health
```

Sources with 2+ consecutive failures show as `RED` — don't panic, a few always break for unrelated reasons (redesigns, rate limits). The pipeline survives.

---

## Step 8 — Start the web app (two terminals)

### Terminal 1: FastAPI backend

```bash
cd /Users/rehan/Documents/HackRadar
source .venv/bin/activate
python -m hackradar.main serve
```

**Expected output:**
```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Leave this terminal running.

**Sanity check in your browser:**
- http://127.0.0.1:8000/api/health → should return JSON `{"ok": true, ...}`
- http://127.0.0.1:8000/docs → interactive API explorer (FastAPI auto-generates this)

### Terminal 2: Next.js frontend

Open a NEW terminal window. (Command+T in Terminal.app or iTerm.)

```bash
cd /Users/rehan/Documents/HackRadar/frontend
npm install              # skip if you already did this — node_modules/ will exist
npm run dev
```

**Expected output:**
```
   ▲ Next.js 14.2.5
   - Local:        http://localhost:3000
   - Network:      ...

 ✓ Ready in 1.xs
```

Leave this terminal running too.

### Open the app

**http://localhost:3000**

You should see:
- HackRadar header with nav (Latest scan / Scan history / Source health)
- "Run a scan" card
- If Step 7 populated a scan, its top items are listed below

---

## Step 9 — Using the app

**Home (`http://localhost:3000/`)**
- Click **Scan** in the "Run a scan" card to kick off a scan
- A status banner appears: "Scan #N is running... polling every 2s"
- When it finishes, the item list updates automatically

**Click any item title** → `/items/{id}` detail page
- Full description, Pass 2 summary, hackathon pitch, all links
- Scroll down to **Deep dive (Claude)** chat panel
- Type a question, hit Enter → streams tokens from Claude Opus 4.6 live
- Ask things like:
  - "What would the demo look like?"
  - "What's the closest existing competitor?"
  - "Sketch a hackathon architecture."
  - "What are the setup gotchas?"

**Scan history** (`/scans`) — every scan, click an id to see its items
**Source health** (`/sources`) — which scrapers are working vs broken

---

## Step 10 — TRIBE v2 validation gate

Run this any time you're unsure HackRadar is healthy. It proves the whole pipeline works end-to-end with fake providers (no API spend):

```bash
cd /Users/rehan/Documents/HackRadar
source .venv/bin/activate
python -m pytest tests/test_tribe_v2_validation.py -v
```

**Expected output:**
```
tests/test_tribe_v2_validation.py::test_v2_pipeline_discovers_tribe_v2 PASSED
tests/test_tribe_v2_validation.py::test_v2_pipeline_dedup_merges_three_tribe_rows PASSED
tests/test_tribe_v2_validation.py::test_v2_pipeline_high_trust_bypass_protects_tribe PASSED
tests/test_tribe_v2_validation.py::test_v2_pipeline_does_not_fabricate_tribe_when_absent PASSED

============================== 4 passed in 0.xx s ==============================
```

All four must pass. If any fail, the pipeline can't reliably discover TRIBE-v2-style drops, and you should NOT ship.

---

## Troubleshooting

### "Missing required API keys: GROQ_API_KEY, ..."

**Cause:** `.env` not being loaded.

**Fix sequence:**
1. `ls /Users/rehan/Documents/HackRadar/.env` — does the file exist at the repo root?
2. `cat /Users/rehan/Documents/HackRadar/.env | head` — are the values there, no quotes?
3. Are you in the right directory when running the command? `pwd` should print `/Users/rehan/Documents/HackRadar`

### "A scan is already running. Wait for it to finish."

A previous scan crashed and left a row in `status='running'`.

```bash
sqlite3 ~/.hackradar/hackradar.db "UPDATE scans SET status='error' WHERE status='running';"
```

### Scan finishes but shows 0 items

Scrapers all failing. Check which:
```bash
python -m hackradar.main db health
```

Fix the RED ones (or just ignore them — pipeline survives missing sources).

### Chat returns HTTP 429

You hit the Pass 3 rate limit (20 user turns/hour default).

Option A: wait an hour.
Option B: bump the limit. Edit `/Users/rehan/Documents/HackRadar/.env`, add:
```env
PASS3_RATE_LIMIT_PER_HOUR=100
```
Restart the backend (Ctrl+C in Terminal 1, re-run the `serve` command).

### Frontend says "Failed to fetch" / "ECONNREFUSED"

Backend isn't running. Check Terminal 1 — is uvicorn still up? Restart it with `python -m hackradar.main serve`.

### Port 8000 or 3000 already in use

Kill whatever's squatting:
```bash
lsof -ti:8000 | xargs kill -9     # frees the backend port
lsof -ti:3000 | xargs kill -9     # frees the frontend port
```

---

## Tuning (optional)

All these live in `/Users/rehan/Documents/HackRadar/.env`. Add any you want — they override defaults in `hackradar/config.py`.

| Variable | Default | What it does |
|---|---|---|
| `LOOKBACK_HOURS` | `48` | Default scan window if no `--from`/`--to` |
| `TOP_N` | `20` | CLI printout row count |
| `PASS1_TRIAGE_THRESHOLD` | `5.0` | Items below this Pass 1 score get dropped (unless from a high-trust source) |
| `PASS2_BATCH_SIZE` | `3` | Cerebras items per call — 3 keeps us under 8K context |
| `PASS2_INTER_BATCH_SLEEP_S` | `2.0` | Pacing between Pass 2 calls — stays under Cerebras 30 RPM |
| `PASS3_RATE_LIMIT_PER_HOUR` | `20` | Max Claude chat turns per hour |
| `HACKRADAR_DB` | `~/.hackradar/hackradar.db` | SQLite file location |

Restart backend after changing `.env`.

---

## Quick reference

```bash
# Always cd + activate venv first
cd /Users/rehan/Documents/HackRadar
source .venv/bin/activate

# Tests
python -m pytest                                             # all 88
python -m pytest tests/test_tribe_v2_validation.py -v        # TRIBE gate only

# Scans
python -m hackradar.main scan                                # last 48h, all sources
python -m hackradar.main scan --source meta_ai_blog          # one source
python -m hackradar.main scan --from 2026-03-25 --to 2026-03-27
python -m hackradar.main scan --dry-run                      # no DB writes
python -m hackradar.main scan --no-enrich                    # faster debug

# DB admin
python -m hackradar.main db init                             # create schema
python -m hackradar.main db health                           # source health table

# Run the app
python -m hackradar.main serve                               # backend :8000
cd frontend && npm run dev                                   # frontend :3000
```

That's it. Done.
