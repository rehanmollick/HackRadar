"""scorer.py — Score Items using Gemini 2.5 Flash.

Batches items (BATCH_SIZE at a time), sends them to the Gemini API with a
structured JSON response schema, parses the results, and returns ScoredItem
objects.

Retry logic:
  - Batch call fails → retry once
  - Retry fails → fall back to one individual call per item in the batch
  - Individual call fails → skip that item with a warning
"""

from __future__ import annotations

import json
import logging
import textwrap
from typing import Any

from google import genai
from google.genai import types

from hackradar import config
from hackradar.models import Item, ScoredItem, ScoredItemResponse, ScoringBatchResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy client (created on first use so missing API key doesn't crash imports)
# ---------------------------------------------------------------------------
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client

# ---------------------------------------------------------------------------
# Scoring prompt (from CLAUDE.md)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = textwrap.dedent("""
You are a technology scout for a hackathon competitor. Your job is to evaluate newly released technology — AI models, tools, APIs, browser features, datasets, SDKs, open-source projects, anything — and determine if it could be the basis of a winning hackathon project.

CONTEXT ON THE HACKER YOU'RE SCOUTING FOR:
- CS student who builds with React/Next.js, Python, TypeScript, PostgreSQL, React Three Fiber
- Comfortable picking up any new tool or framework quickly, especially with AI-assisted coding (Claude Code)
- Has access to free T4 GPUs (Google Colab/Kaggle) and free tiers of major cloud platforms
- Wins hackathons by finding bleeding-edge, niche technology that nobody else has built products around — then building impressive interactive demos
- Willing to invest days of prep time before a hackathon for complex setup. Has AI coding tools that dramatically speed up development. Don't underestimate what's buildable.
- Example winning project: took Meta's TRIBE v2 brain activity prediction model (released 12 days before hackathon, zero existing products) and built an interactive 3D brain visualisation app comparing how images activate different neural regions using React Three Fiber
- Interested in ALL domains without exception: neuroscience, audio, robotics, biology, chemistry, vision, NLP, creative tools, hardware, browser APIs, dev tools, games, AR/VR — anything that produces a wow-factor demo

SCORING CRITERIA (score each 1-10):

1. OPEN & FREE TO USE (weight: 20%)
   10 = fully open-source code + weights, runs on free-tier hardware, or generous free API. Ready to use today.
   7 = open-source but needs beefy GPU (>16GB VRAM), or free API with moderate rate limits
   5 = free tier exists but limited, or requires some paid infrastructure
   3 = mostly paid but has a trial or limited free access
   1 = closed source, paywalled, enterprise-only, or paper with no code

2. NOVELTY & UNEXPLOITED (weight: 35%)
   10 = released in last 7 days, zero products or demos built on it beyond authors' own
   8 = released in last 14 days, maybe 1-2 basic community experiments
   6 = released in last 30 days, small but growing community awareness
   4 = released in last 3 months, moderate adoption, some projects exist
   2 = well-known, widely adopted, many existing products
   THIS IS THE MOST IMPORTANT CRITERION. The entire strategy is finding things before others. When in doubt, score lower — if lots of people already know about it, it's not useful for hackathon differentiation.

3. WOW FACTOR & DEMO POTENTIAL (weight: 25%)
   10 = cross-disciplinary, visually stunning or mind-bending potential, would make judges say "wait, what?" Examples: brain activity prediction, real-time audio separation by voice description, molecular visualization, novel 3D/AR/spatial experiences, anything that bridges AI with a surprising domain
   7 = technically impressive with clear visual/interactive demo potential
   5 = solid tech, decent demo potential but not jaw-dropping
   3 = useful but incremental, hard to make visually exciting
   1 = purely theoretical, no demo potential, marginal improvement

4. BUILDABILITY (weight: 20%)
   10 = excellent docs, clear inference script or API, straightforward integration
   8 = good docs, some setup required but well-documented
   6 = moderate complexity, might need to read source code, but doable with AI coding assistance and some prep time
   4 = complex multi-step setup, sparse docs, but theoretically possible with significant effort
   2 = requires custom training from scratch, massive compute, or deep domain expertise with no shortcuts

   IMPORTANT: Do NOT be overly conservative here. The builder has Claude Code, automation tools, and is willing to spend days prepping before a hackathon. Complex setup is fine if the payoff is worth it. Score based on "could a strong developer with AI tools get this working in a few days of prep + a hackathon weekend" — not "could someone do this in 3 hours with no help."

CALCULATE total_score as weighted average: (open_score * 0.20) + (novelty_score * 0.35) + (wow_score * 0.25) + (build_score * 0.20)

FOR ITEMS WHERE total_score >= 6.5, also provide:
- "summary": 2-3 sentences on what this technology does and why it's interesting
- "hackathon_idea": A specific, concrete project idea. Not vague — describe the actual product, what a user would see/do, and why it's impressive.
- "tech_stack": Suggested stack for the demo
- "why_now": Why hasn't this been built yet? What's the timing opportunity?
- "effort_estimate": Rough estimate of setup + build time
- "links": All relevant URLs (paper, code, model, demo, docs)

FOR ITEMS WHERE total_score < 6.5:
- Just return scores and a 1-sentence summary. Leave hackathon_idea, tech_stack, why_now, effort_estimate, links as null.

Respond ONLY in valid JSON matching the schema. No markdown, no preamble, no explanation outside the JSON.
""").strip()


# ---------------------------------------------------------------------------
# Item formatting for the prompt
# ---------------------------------------------------------------------------

def _format_item(item: Item) -> dict[str, Any]:
    """Produce a compact dict representation of an item for the scoring prompt."""
    d: dict[str, Any] = {
        "title": item.title,
        "description": item.description[:1000],
        "category": item.category,
        "source_count": item.source_count,
        "sources": item.all_sources,
    }
    # URLs
    for field in ("source_url", "github_url", "huggingface_url", "demo_url", "paper_url"):
        val = getattr(item, field, None)
        if val:
            d[field] = val
    # Enrichment
    if item.stars is not None:
        d["github_stars"] = item.stars
    if item.language is not None:
        d["primary_language"] = item.language
    if item.license is not None:
        d["license"] = item.license
    if item.readme_excerpt:
        d["readme_excerpt"] = item.readme_excerpt[:300]
    if item.model_size is not None:
        d["model_size"] = item.model_size
    if item.downloads is not None:
        d["hf_downloads"] = item.downloads
    if item.has_demo_space is not None:
        d["has_hf_demo_space"] = item.has_demo_space
    return d


def _build_prompt(items: list[Item]) -> str:
    formatted = [_format_item(item) for item in items]
    items_json = json.dumps(formatted, ensure_ascii=False, indent=2)
    return (
        f"{_SYSTEM_PROMPT}\n\n"
        f"Here are the {len(items)} items to score:\n\n"
        f"{items_json}\n\n"
        "Return a JSON object with a single key 'items' containing an array of scored items, "
        "one entry per input item in the same order."
    )


# ---------------------------------------------------------------------------
# Gemini API call
# ---------------------------------------------------------------------------

def _call_gemini(prompt: str) -> ScoringBatchResponse:
    """
    Call Gemini 2.5 Flash with structured JSON output.

    Raises on any API or parse error (let the caller handle retries).
    """
    client = _get_client()
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=ScoringBatchResponse,
        ),
    )
    return ScoringBatchResponse.model_validate_json(response.text)


# ---------------------------------------------------------------------------
# Recalculate / validate scores
# ---------------------------------------------------------------------------

def _recompute_total(resp: ScoredItemResponse) -> float:
    """
    Recompute the weighted total from the four criterion scores.
    Overrides whatever the LLM calculated to ensure it's correct.
    """
    return (
        resp.open_score * config.WEIGHT_OPEN
        + resp.novelty_score * config.WEIGHT_NOVELTY
        + resp.wow_score * config.WEIGHT_WOW
        + resp.build_score * config.WEIGHT_BUILD
    )


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def _score_batch(batch: list[Item]) -> list[ScoredItem]:
    """
    Score a single batch. Retries once on failure, then falls back to
    individual calls.
    """
    prompt = _build_prompt(batch)

    # First attempt
    try:
        result = _call_gemini(prompt)
        return _zip_results(batch, result)
    except Exception as exc:
        logger.warning("Batch scoring failed (attempt 1): %s — retrying", exc)

    # Retry
    try:
        result = _call_gemini(prompt)
        return _zip_results(batch, result)
    except Exception as exc:
        logger.warning("Batch scoring failed (attempt 2): %s — falling back to individual calls", exc)

    # Fall back: score each item individually
    scored: list[ScoredItem] = []
    for item in batch:
        try:
            single_prompt = _build_prompt([item])
            result = _call_gemini(single_prompt)
            items_out = _zip_results([item], result)
            scored.extend(items_out)
        except Exception as item_exc:
            logger.warning("Individual scoring failed for %r: %s — skipping", item.title, item_exc)

    return scored


def _zip_results(items: list[Item], batch_response: ScoringBatchResponse) -> list[ScoredItem]:
    """
    Match scored responses back to their source Items.

    The LLM is asked to return results in the same order as the input,
    so we zip by position. If the counts differ (LLM hallucination), we
    match by title as a fallback.
    """
    responses = batch_response.items

    if len(responses) == len(items):
        # Happy path: same order, zip directly
        return [
            _make_scored_item(item, resp)
            for item, resp in zip(items, responses)
        ]

    # Mismatch: match by title similarity
    logger.warning(
        "Response count mismatch: sent %d items, got %d responses — matching by title",
        len(items), len(responses),
    )
    resp_by_title: dict[str, ScoredItemResponse] = {r.title.lower(): r for r in responses}
    scored: list[ScoredItem] = []
    for item in items:
        resp = resp_by_title.get(item.title.lower())
        if resp is None:
            # Try fuzzy match
            from rapidfuzz import process as rfprocess
            match = rfprocess.extractOne(
                item.title.lower(),
                list(resp_by_title.keys()),
                score_cutoff=70,
            )
            if match:
                resp = resp_by_title[match[0]]
        if resp is not None:
            scored.append(_make_scored_item(item, resp))
        else:
            logger.warning("No matching response for %r — skipping", item.title)
    return scored


def _make_scored_item(item: Item, resp: ScoredItemResponse) -> ScoredItem:
    total = _recompute_total(resp)
    return ScoredItem(
        item=item,
        open_score=resp.open_score,
        novelty_score=resp.novelty_score,
        wow_score=resp.wow_score,
        build_score=resp.build_score,
        total_score=total,
        summary=resp.summary,
        hackathon_idea=resp.hackathon_idea if total >= config.SCORE_THRESHOLD else None,
        tech_stack=resp.tech_stack if total >= config.SCORE_THRESHOLD else None,
        why_now=resp.why_now if total >= config.SCORE_THRESHOLD else None,
        effort_estimate=resp.effort_estimate if total >= config.SCORE_THRESHOLD else None,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_items(items: list[Item]) -> list[ScoredItem]:
    """
    Score all items using Gemini 2.5 Flash in batches of config.BATCH_SIZE.

    Returns a list of ScoredItem objects. Items that fail even individual
    fallback scoring are omitted with a warning.
    """
    if not items:
        return []

    if not config.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set — cannot score items")
        return []

    all_scored: list[ScoredItem] = []
    batch_size = config.BATCH_SIZE

    for batch_start in range(0, len(items), batch_size):
        batch = items[batch_start: batch_start + batch_size]
        logger.info(
            "Scoring batch %d/%d (%d items)",
            batch_start // batch_size + 1,
            (len(items) + batch_size - 1) // batch_size,
            len(batch),
        )
        try:
            scored = _score_batch(batch)
            all_scored.extend(scored)
        except Exception as exc:
            logger.error("Unexpected error scoring batch starting at index %d: %s", batch_start, exc)

    logger.info("Scored %d/%d items", len(all_scored), len(items))
    return all_scored
