# HackRadar — Planned Changes

Status: **planning only, not yet implemented**. Waiting on gstack review before any code changes.

## 0. Context and baseline

Latest full scan (scan_id=4, 2026-04-08):

```
Phase 1 scrape        1014 raw items (8 source scrapers returned 0)
Phase 2 window        787
Phase 2 dedup         622
Phase 3 enrich        done (~10 min, bottlenecked by HF API)
Phase 4 pass 1        622 → 562 (only 60 filtered, ~10% cut rate)
Phase 5 pass 2        562 → 548 scored
Total runtime         1h 43m
```

Top 20 contained real signal (FEEL/EDA emotion recognition, THINGS-pseudo-fMRI brain data, Gemma-4 variants, browser-based robotics, Gaussian splatting), but also noise (one-person HF uploads scoring 8.8+ on pure recency bias).

**Three structural problems revealed by this scan:**

1. **Research-lab blogs contribute almost nothing.** Meta=1, DeepMind=1, everyone else=0. These are the sources most likely to drop a TRIBE-v2-class model, and 8 of them are broken.
2. **Pass 1 triage is a no-op.** 90% of items pass through because the prompt explicitly says "when in doubt, pass it through (score 5+)" and the threshold sits at the exact 5.0 midpoint.
3. **Firehoses dominate raw volume.** arxiv (290) + HF datasets (300) + HF models (125) + chrome_platform (100) = **80% of raw items**. Most of it is throwaway noise — random fine-tunes, schema tests, dataset uploads.

And the new requirement: **extend the lookback window from 48 hours to 14-30 days** so the catalog is actually useful for pre-hackathon prep, not just "what happened since yesterday."

---

## 1. Fix the 8 dead source scrapers (highest leverage)

**Files:** `hackradar/sources/base_blog.py`, `hackradar/sources/webdev_blog.py`, `hackradar/sources/kaggle_*.py`

**Broken sources:**

| Source | Symptom | Likely cause |
|---|---|---|
| google_research_blog | 0 items | RSS selector stale / site moved |
| microsoft_research_blog | 0 items | RSS feed URL changed |
| mistral_blog | 0 items | HTML selector stale (site redesign) |
| anthropic_research | 0 items | HTML selector stale |
| openai_research | 0 items | HTML selector stale (likely JS-rendered now, needs Playwright) |
| webdev_blog | 0 items | Feed URL moved, partial fix landed already but still 0 |
| kaggle_datasets | 0 items | KAGGLE_USERNAME/KAGGLE_KEY not set (falls back to web scrape which doesn't work) |
| kaggle_competitions | 0 items | Same auth issue |

**Plan:**

- Inspect each site live, rebuild selectors. For JS-rendered sites (likely openai/anthropic), fall back to a curated JSON feed if available (both labs publish arXiv listings and GitHub releases we can pivot to).
- Kaggle: get free API keys and put them in `.env`, stop trying to web-scrape.
- For each scraper, add one unit test that asserts "at least 1 item returned in last 30 days against a live fetch" — so we catch silent breakage next time.

**Acceptance:** all 10 research-lab blogs return >=1 item on a 14-day window.

**Why this is #1:** no amount of scoring tuning helps if the relevant items never enter the pipeline. This is the single biggest quality lever.

---

## 2. Pre-LLM quality gates on firehose sources

**Files:** `hackradar/sources/arxiv_source.py`, `hackradar/sources/huggingface_models.py`, `hackradar/sources/huggingface_datasets.py`, `hackradar/sources/chrome_platform.py`

**Current problem:** 80% of raw items come from 4 firehose sources. Most of it is junk that the LLM then has to waste tokens on. The Pass 1 triage is supposed to be the filter, but it's lax AND expensive (60K+ LLM tokens to throw away ~10% of items).

**Plan — hardcode cheap, deterministic filters BEFORE any LLM call:**

### huggingface_models
- Require **at least one of**: downloads > 50, OR owner in trusted orgs list (`facebookresearch`, `google`, `google-deepmind`, `mistralai`, `stability-ai`, `Qwen`, `deepseek-ai`, `nvidia`, `apple`, `microsoft`, `openai`, `anthropic`, `allenai`, `stabilityai`, etc.), OR linked demo Space exists.
- Drop everything else. Rationale: a random person's 0-download fine-tune is never going to win a hackathon.

### huggingface_datasets
- Require **at least one of**: downloads > 20, OR linked paper, OR owner in trusted orgs, OR dataset size > 1 MB.
- Drop obvious generated filenames (regex: `schema_test.*`, `test_.*`, `tmp_.*`).

### arxiv
- Keep subcategory filter as-is, but add **abstract keyword pre-filter**: require at least one hit from a curated regex list (`open.?source`, `we release`, `we introduce`, `available at`, `github\.com`, `huggingface\.co`, `demo`, `real-?time`, `interactive`, `novel architecture`, `first .* framework`, `state-of-the-art`, `outperforms`, etc.).
- Rationale: academic papers that will never have a hackathon-usable artifact don't belong in the pipeline.

### chrome_platform
- Filter to features with status `shipping`, `intent-to-ship`, `origin trial`, or `in development`. Drop `no active development`, `deprecated`, `parked`.

**Acceptance:** raw item volume drops 60%+ (from ~1000 → ~400 per 48h window), with zero loss of items scoring 8.0+ in the current scan 4 top-20. Verify by replaying scan 4 items through the new filter offline.

**Why this works:** the LLM is the expensive resource. Every item filtered cheaply here saves 3K tokens of Pass 2 scoring. If we cut 600 items from a 14-day scan, we save ~2 million tokens (hours of Pass 2 time).

---

## 3. Fix Pass 1 triage

**Files:** `hackradar/config.py:69`, `hackradar/scoring/prompts.py:32-34`

**Two coordinated changes:**

### Threshold bump
```python
# config.py:69
PASS1_TRIAGE_THRESHOLD = float(os.environ.get("PASS1_TRIAGE_THRESHOLD", "6.5"))
# was "5.0"
```

### Prompt rewrite
Current (in `prompts.py`, lines ~32-34):
> "IMPORTANT: Be permissive on wow factor. You are a cheap filter, not the final scorer. When in doubt, pass it through (score 5+). The downstream pass will apply the real scoring criteria."

Replace with:
> "You are the gatekeeper. Pass 2 is expensive — your job is to drop everything that is clearly not hackathon material: incremental papers, routine dataset uploads, random fine-tunes, narrow improvements to existing benchmarks, paywalled or closed products, marketing posts. When in doubt, drop it — a true gem will score 7+ easily. Only pass items that are (a) open-source or have a clear free path, (b) recent, and (c) have genuine demo potential for a weekend project."

**Acceptance:** Pass 1 cut rate goes from ~10% to 50-70% on non-bypass items. No loss of items scoring 8.0+ in scan 4 top-20 (verify offline against the stored scan 4 data).

**Note:** TRIBE-v2-class items from `meta_ai_blog` bypass Pass 1 entirely via `HIGH_TRUST_SOURCES`, so this change does not risk the validation test.

---

## 4. Calibrate Pass 2 novelty scoring

**File:** `hackradar/scoring/prompts.py` (Pass 2 prompt)

**Problem:** the LLM gives novelty=9-10 to anything published in the last 48 hours regardless of who published it. That's why `gimarchetti/clr-experiment-xvla-mps` (a single person's VLA experiment, zero community signal) scored 8.95 in scan 4.

**Fix:** add explicit calibration guidance to the Pass 2 novelty criterion:

> "Novelty = 10 means: published by a known research lab or well-known author, with the potential to define a new capability class nobody has built on yet. Novelty = 8 means: promising independent release with a published paper or working demo. Novelty ≤ 6 for solo-uploaded HF models/datasets with no accompanying paper, no demo, and fewer than 50 downloads — 'recent' alone is not novel."

Also pass in the enriched metadata (downloads, stars, owner org) explicitly to the LLM so it has something to ground its novelty judgment on.

**Acceptance:** re-score scan 4's top 20 offline against the new prompt. Expected result: one-person HF uploads drop to the 7.0-7.5 range, making room for the research-lab drops.

---

## 5. Extended lookback — 14 to 30 days — without blowing up runtime

This is the big architectural change. **Naive approach does not work.** Linear extrapolation of scan 4:

| Lookback | Raw items (est.) | Pass 2 batches | Pass 2 runtime |
|---|---:|---:|---:|
| 48h (current) | 1,014 | 141 | 1h 40m |
| 7 days | 3,500 | 500 | ~6h |
| 14 days | 7,000 | 1,000 | ~12h |
| 30 days | 15,000 | 2,150 | **~26h** |

Unacceptable.

### Strategy: persistent incremental scoring + pre-Pass-1 gates + smart scheduling

**The key insight:** once an item has been scored, its score is immutable (the tech didn't change). We should never score the same item twice.

### A. Score cache across scans

**Files:** `hackradar/db.py`, `hackradar/main.py`, new function `db.get_existing_score(content_hash)`

Currently the `scores` table stores `(item_id, scan_id)` pairs — every scan re-records scores for every item, even if the item was already scored last week. The `items` table already dedupes by `content_hash` across scans.

**Change:** before sending an item to Pass 2, check if this item (by `content_hash`) was already scored in a previous scan within the last 30 days. If yes, reuse that score. If no, score it and save.

Effect: an incremental 14-day scan that overlaps with last week's 14-day scan only scores the ~7 days of NEW items. That's a 2x reduction at minimum.

### B. The 14-day cold-start scan

First run with 14-day lookback will be expensive — no cached scores to reuse. Estimated cost with **all fixes applied** (source repairs + pre-Pass-1 gates + Pass 1 threshold fix):

| Stage | Count | Notes |
|---|---:|---|
| Raw (firehoses pre-filtered) | ~1,800 | Down from ~7,000 naive |
| After window filter | ~1,500 | |
| After dedup | ~1,200 | |
| After Pass 1 (tightened) | ~300-400 | 70-80% cut rate |
| Pass 2 batches | ~75-100 | 4 items/batch |
| Pass 2 runtime | **~35-45 min** | 27s/batch |

Tolerable for a weekly manual run.

### C. Subsequent scans (incremental)

After the cold start, a second 14-day scan overlapping by 7 days only has ~7 days of genuinely new items to score:

| Stage | Count | Notes |
|---|---:|---|
| Raw (pre-filtered) | ~900 | 7 new days |
| After dedup + score cache hit | ~150-200 new items | Other ~700 reuse cached scores |
| After Pass 1 | ~40-60 | |
| Pass 2 runtime | **~8-15 min** | |

Effectively free after the cold start.

### D. Scheduling pattern

Since HackRadar is manual/weekly per the stored context, the natural pattern is:

1. **Cold start** (once): run with 14-day lookback, ~40 min
2. **Weekly refresh** (recurring): run with 10-day lookback (3-day overlap for safety at day boundaries), ~15 min
3. **Top-N view**: show the top items across the **full 14-day horizon**, not just the current scan window. Use the score cache to look back.

### E. Optional: 30-day mode

Expose `--lookback-days N` (default 14). For a one-time 30-day deep dive before a major hackathon, runtime would be ~80 min cold-start, ~15-20 min incremental. Acceptable as an occasional operation.

### Acceptance criteria

- `run_scan(lookback_days=14)` completes in under 50 minutes on a cold cache
- `run_scan(lookback_days=14)` completes in under 20 minutes when the previous scan was ≤7 days ago
- Top 20 results from a 14-day scan contain visibly more research-lab drops than the current 48h scan
- Score cache hit rate is observable in the log (e.g., `Pass 2: 120 new items, 340 reused from cache`)

---

## 6. UI: show score provenance + scan window

**File:** `frontend/components/ItemCard.tsx`

Small additions to the already-rebuilt dark ItemCard:

- Show the **scan window** this score is from, in small text, e.g., `scored 3 days ago (scan #5, 2026-04-05)`
- When an item's score is reused from an older scan, badge it so the user knows the score didn't update
- Add the raw **item publication date** alongside the score date

Acceptance: user can tell at a glance whether the item is fresh or cached, and which scan produced the score.

---

## Execution order (when you're ready to code)

Dependencies matter. Recommended sequence:

1. **#1 Fix dead scrapers** — unblocks everything else. Scans that actually pull from research lab blogs catch TRIBE-v2-class drops.
2. **#2 Pre-Pass-1 filters** — cuts raw volume by ~60% so runtime math works for the extended window.
3. **#3 Pass 1 threshold + prompt** — further cuts cost, eliminates lax triage.
4. **#4 Pass 2 novelty calibration** — raises signal-to-noise at the top.
5. **#5A Score cache** — enables incremental scans.
6. **#5D Scheduling pattern** — wire up the weekly cadence (just a CLI flag + docs, no cron).
7. **#6 UI polish** — after the backend changes are solid.

---

## What this will NOT do

- No daily cron / GitHub Actions / background automation. HackRadar stays a manual weekly run per user direction.
- No email delivery.
- No paid LLM services. Entire stack stays on free tiers (Cerebras qwen-3-235b + OpenRouter gpt-oss fallback).
- No source additions beyond the current 25. Depth over breadth — fix what we have first.

---

## Expected final state

After all fixes land:

- **Weekly workflow:** one 15-minute incremental scan, manually triggered, covering the last 14 days
- **Cold-start scan:** ~40 minutes, 1-2x a month when cache is stale
- **Result quality:** top 20 dominated by actual research-lab drops and genuinely novel tools, with random HF experiments falling below the fold
- **Full 14-day horizon visible in the UI**, ranked by score, filterable by source/category
- **Runtime predictable within 20%** because most cost is cached-score lookups, not LLM calls
- **Source health dashboard shows 25/25 sources green** (no silent breakage)
