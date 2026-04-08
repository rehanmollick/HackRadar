"""Shared prompt + item formatting for HackRadar V2 scoring passes."""

from __future__ import annotations

import json
import textwrap
from typing import Any

from hackradar.models import Item

# ---------------------------------------------------------------------------
# Pass 1: cheap triage — novelty+wow composite only
# ---------------------------------------------------------------------------

PASS1_TRIAGE_SYSTEM = textwrap.dedent("""
You are a fast triage filter for a hackathon technology scout. Your only job
is to answer: "Is this plausibly a hackathon-winning tech find, or noise?"

The downstream user wins hackathons by finding bleeding-edge, niche, unexploited
technology (released in the last 1-2 weeks, few or no existing products built on
it, open-source or generous free tier, visually impressive demo potential).

Score each item 1-10 on a NOVELTY + WOW composite:
  10 = brand new, zero products built, cross-disciplinary, visually stunning
       (e.g. brain activity prediction, molecular visualization, real-time audio
       separation, interactive 3D/AR/spatial experiences)
  7  = interesting tech, recent release, decent demo potential
  5  = solid but not jaw-dropping, or not that new
  3  = incremental improvement, narrow domain, boring from a demo standpoint
  1  = obviously not relevant, totally mainstream, or has no open access

IMPORTANT: Be permissive on wow factor. You are a cheap filter, not the final
scorer. When in doubt, pass it through (score 5+). The downstream pass will
apply the real scoring criteria.

Respond ONLY in valid JSON matching the schema. No markdown, no explanation.
""").strip()


def format_item_for_triage(item: Item) -> dict[str, Any]:
    """Compact representation for Pass 1. Tight token budget."""
    d: dict[str, Any] = {
        "title": item.title,
        "description": (item.description or "")[:400],
        "category": item.category,
        "source": item.source,
    }
    if item.github_url:
        d["github_url"] = item.github_url
    if item.huggingface_url:
        d["huggingface_url"] = item.huggingface_url
    if item.paper_url:
        d["paper_url"] = item.paper_url
    return d


def build_pass1_prompt(items: list[Item]) -> str:
    formatted = [format_item_for_triage(item) for item in items]
    items_json = json.dumps(formatted, ensure_ascii=False, indent=2)
    return (
        f"{PASS1_TRIAGE_SYSTEM}\n\n"
        f"Here are the {len(items)} items to triage:\n\n"
        f"{items_json}\n\n"
        'Return a JSON object with a single key "items" containing an array, '
        "one entry per input item in the same order. Each entry: "
        '{"title": str, "triage_score": float (1-10), "reason": str (≤15 words)}.'
    )


# ---------------------------------------------------------------------------
# Pass 2: full 4-criterion scoring
# ---------------------------------------------------------------------------

PASS2_SCORING_SYSTEM = textwrap.dedent("""
You are a technology scout for a hackathon competitor. Evaluate newly released
technology — AI models, tools, APIs, browser features, datasets, SDKs, open-source
projects — and determine if it could be the basis of a winning hackathon project.

CONTEXT ON THE HACKER:
- CS student. Ships with React/Next.js, TypeScript, Python, PostgreSQL,
  React Three Fiber. Comfortable picking up any new framework, especially
  with AI coding assistance.
- Has free T4 GPUs via Colab/Kaggle and free cloud tiers.
- Wins by finding bleeding-edge niche tech nobody else has built products on,
  then building impressive interactive demos.
- Will invest days of prep before a hackathon for complex setup. Has Claude Code.
  Don't underestimate what's buildable.
- Example win: took Meta's TRIBE v2 brain activity prediction model (released
  12 days before the hackathon, zero existing products) and built an interactive
  3D brain visualization comparing how images activate different neural regions.
- Interested in ALL domains: neuroscience, audio, robotics, biology, chemistry,
  vision, NLP, creative tools, hardware, browser APIs, dev tools, games, AR/VR.

SCORING CRITERIA (each 1-10):

1. OPEN & FREE (weight 20%)
   10 = fully open source + weights, runs on free hardware, or generous free API
   7  = open but needs a big GPU, or free API with moderate limits
   5  = limited free tier
   3  = trial / limited free access
   1  = closed, paywalled, enterprise-only, or paper with no code

2. NOVELTY & UNEXPLOITED (weight 35%) ← most important
   10 = released in last 7 days, zero products built on it
   8  = last 14 days, 1-2 basic experiments
   6  = last 30 days, small growing awareness
   4  = last 3 months, moderate adoption
   2  = well-known, widely adopted, many existing products
   When in doubt, score lower — if lots of people already know about it,
   it's not useful for hackathon differentiation.

3. WOW FACTOR & DEMO POTENTIAL (weight 25%)
   10 = cross-disciplinary, visually stunning, would make judges say
        "wait, what?" (brain activity, molecular viz, real-time audio by voice
        description, novel 3D/AR/spatial, AI bridging a surprising domain)
   7  = technically impressive, clear visual/interactive potential
   5  = solid tech, decent demo
   3  = useful but incremental, hard to make visually exciting
   1  = theoretical, no demo potential

4. BUILDABILITY (weight 20%)
   10 = excellent docs, clear inference script or API
   8  = good docs, some setup but well documented
   6  = moderate complexity, doable with AI coding assistance + prep days
   4  = complex multi-step setup, sparse docs, but theoretically possible
   2  = requires custom training from scratch, massive compute, deep expertise
   Do NOT be conservative here. Assume the builder has Claude Code and days
   of prep time. Score based on "strong dev with AI tools over a prep weekend,"
   not "someone alone in 3 hours."

CALCULATE total_score = open_score*0.20 + novelty_score*0.35 + wow_score*0.25 + build_score*0.20

FOR ITEMS WHERE total_score >= 6.5, also provide:
- "summary": 2-3 sentences on what this does and why it's interesting
- "hackathon_idea": specific concrete project idea. Not vague — what does the
  user see/do, why is it impressive
- "tech_stack": suggested stack for the demo
- "why_now": why hasn't this been built yet? what's the timing opportunity?
- "effort_estimate": rough setup + build time

FOR ITEMS WHERE total_score < 6.5:
- Scores + 1-sentence summary only. Leave the other fields null.

Respond ONLY in valid JSON matching the schema. No markdown, no preamble.
""").strip()


def format_item_for_scoring(item: Item) -> dict[str, Any]:
    """Full representation for Pass 2. Respects Cerebras context budget:
    description ≤ 600 chars, readme_excerpt ≤ 300 chars.
    """
    d: dict[str, Any] = {
        "title": item.title,
        "description": (item.description or "")[:600],
        "category": item.category,
        "source_count": item.source_count,
        "sources": item.all_sources,
    }
    for field in ("source_url", "github_url", "huggingface_url", "demo_url", "paper_url"):
        val = getattr(item, field, None)
        if val:
            d[field] = val
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


def build_pass2_prompt(items: list[Item]) -> str:
    formatted = [format_item_for_scoring(item) for item in items]
    items_json = json.dumps(formatted, ensure_ascii=False, indent=2)
    n = len(items)
    example = (
        '{\n'
        '  "items": [\n'
        '    {\n'
        '      "title": "<exact title from input>",\n'
        '      "open_score": 7.0,\n'
        '      "novelty_score": 9.0,\n'
        '      "wow_score": 8.0,\n'
        '      "build_score": 7.0,\n'
        '      "total_score": 7.9,\n'
        '      "summary": "...",\n'
        '      "hackathon_idea": "..." | null,\n'
        '      "tech_stack": "..." | null,\n'
        '      "why_now": "..." | null,\n'
        '      "effort_estimate": "..." | null\n'
        '    }\n'
        '  ]\n'
        '}'
    )
    return (
        f"{PASS2_SCORING_SYSTEM}\n\n"
        f"Here are the {n} items to score:\n\n"
        f"{items_json}\n\n"
        f'Return a JSON object with a single key "items" containing an array of '
        f"EXACTLY {n} scored items, in the SAME ORDER as the input. Do not add, "
        f"drop, merge, or reorder items.\n\n"
        f"EVERY item MUST include all of these fields: title (copy the exact "
        f"title string from the input), open_score, novelty_score, wow_score, "
        f"build_score, total_score, summary. The remaining four fields "
        f"(hackathon_idea, tech_stack, why_now, effort_estimate) are required "
        f"only when total_score >= 6.5, otherwise set them to null.\n\n"
        f"Shape example (for one item):\n{example}"
    )


# ---------------------------------------------------------------------------
# Context budgeting
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Cheap token estimate. ~4 chars/token for English."""
    return max(1, len(text) // 4)
