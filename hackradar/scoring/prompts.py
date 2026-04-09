"""Shared prompt + item formatting for HackRadar V2 scoring passes."""

from __future__ import annotations

import json
import textwrap
from typing import Any, Optional

from hackradar.models import Item

# ---------------------------------------------------------------------------
# Pass 1: cheap triage — novelty+wow composite only
# ---------------------------------------------------------------------------

PASS1_TRIAGE_SYSTEM = textwrap.dedent("""
You are the gatekeeper for a hackathon technology scout pipeline. Pass 2 is
expensive — your job is to DROP everything that clearly isn't impressive
open-source tech:
  - Incremental papers ("we improve X by 0.3%")
  - Routine dataset uploads (schema tests, cleanup forks, tiny resamples)
  - Random one-person fine-tunes with no paper and no demo
  - Narrow benchmarks that only beat one other paper
  - Paywalled products, closed APIs, marketing blog posts
  - Tutorial/explainer content, not releases

AUTO-DROP (score ≤2) — these categories are NEVER hackathon building blocks
regardless of quality, polish, or novelty:
  - Developer plumbing: auth/credential libraries, package managers,
    CI/CD configs, project scaffolding/boilerplate generators, SDK wrappers,
    API client libraries, deployment scripts, container configs, runbook
    libraries, documentation collections. These are things you USE while
    building, not things you BUILD ON TOP OF.
  - Survey / review / meta-analysis papers (titles with "survey", "review",
    "systematic study", "meta-analysis", "a comprehensive overview of").
  - Benchmark-only releases — a new eval suite with no new model or tool.
  - Ethics / policy / governance / alignment-theory frameworks with no
    buildable artifact.
  - Position papers, manifestos, opinion pieces, "call to action" papers.
  - Dataset-only releases UNLESS the dataset enables a clearly novel
    capability (new modality, first-of-its-kind labels, a domain nobody
    had data for). Routine dataset cleanups, resamples, and translations
    drop.
  - Papers reporting <5% metric improvement on an existing task with an
    existing architecture.
  - Version bumps, refactors, schema tests, library cleanups.

NOVELTY OVERRIDE — if an item looks like infrastructure but actually
introduces a new RESEARCH capability (e.g. "Project Telescope: exposing
internal agent state during inference", "a compiler that lets you run 70B
models on 8GB VRAM") then it is NOT plumbing. Pass it. The distinction is
"does this give me a new thing to demo?" vs "is this something I'd apt-get
install?"

PASS items that are:
  (a) Open-source, with code OR weights OR a paper with an artifact path,
  (b) Recent (last 30 days), and
  (c) Genuinely new capability — a model, architecture, tool, API, browser
      feature, dataset, SDK that a strong dev could build an impressive
      demo on. Cross-disciplinary AI bridges (neuroscience, audio, biology,
      robotics, creative tools) get a bias UP.

Score each item 1-10 on "is this plausibly impressive open-source tech":
  10 = obvious hit (brain activity FM, molecular viz, real-time audio
       separation by description, novel 3D/AR/spatial, cross-disciplinary)
  8  = strong signal, fresh open-source release with clear capability
  6  = interesting but might be incremental; marginal pass
  4  = weak signal, unclear if there's real meat
  2  = noise, junk, spam, mainstream, closed
  1  = definitely drop

When in doubt, DROP IT — a true gem will score 7+ easily, and the user would
rather miss marginal items than waste Pass 2 budget on noise. Pass 2 runs the
real rubric and will catch anything that sneaks through with a 6-7.

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
You are a TECHNOLOGY DISCOVERY scout. Your mission: surface impressive,
open-source, cutting-edge technology — models, papers with code, repos,
APIs, datasets, browser features, SDKs. You are NOT a product-ideation
engine. The user ideates himself. Your job is supplying mind-blowing
INGREDIENTS, not pre-cooked recipes.

CONTEXT ON THE HACKER:
- CS student. Ships React/Next.js, TypeScript, Python, PostgreSQL,
  React Three Fiber. Picks up new frameworks fast, especially with
  AI coding assistance (Claude Code).
- Has free T4 GPUs via Colab/Kaggle, free cloud tiers, M-series Mac.
- Wins by finding bleeding-edge niche tech nobody else has built products
  on — then building interactive demos. The TECH is the win, not the demo.
- Example win: took Meta's TRIBE v2 brain activity prediction model
  (released 12 days before the hackathon, zero existing products) and
  built an interactive 3D brain viz comparing how images activate
  different neural regions. TRIBE v2 was a 10/10 in every dimension —
  code + weights + inference script + foundation model for a surprising
  domain (neuroscience) with zero community adoption.
- Interested in ALL domains: neuro, audio, robotics, biology, chemistry,
  vision, NLP, creative tools, hardware, browser APIs, dev tools, AR/VR.

SCORING — four criteria, each 1-10:

1. USABILITY (weight 30%) — can I actually build with this TODAY?
   STRICT calibration anchored on ARTIFACT STATE (not "is it free"):
     10 = code + weights + working demo + inference script. Runs on
          Colab T4 or M-series Mac. Drop-in ready. (e.g. TRIBE v2)
     8  = code + weights on consumer HW with decent docs. No demo yet
          but clear inference path.
     6  = code + weights but complex multi-step setup (compile CUDA,
          download 40GB checkpoints, assemble pipeline from 3 repos).
     4  = paper + weights but NO code, OR code but NO weights. You'd
          have to implement inference yourself from the paper.
     2  = paper only. PDF + claims, no artifact. Research-only.
     1  = closed API / paywalled / enterprise-only / behind waitlist.
   A pure research paper CANNOT score above 2. A closed API CANNOT
   score above 1. This is the floor that pushes papers below the fold.

2. INNOVATION (weight 35%) — is the underlying tech genuinely new?
   THIS IS THE DOMINANT RANKER. When in doubt on ordering, Innovation
   is the score that matters most.
     10 = defines a new capability class. First of its kind. From a
          known research lab. Would change what's possible on a
          weekend project. (TRIBE v2, SAM, first diffusion model, etc.)
     8  = strong novel contribution, recognizable author/lab, clearly
          ahead of prior art in one dimension.
     6  = interesting new angle on an existing problem, genuine but
          incremental improvement, solid paper from a credible author.
     4  = yet-another fine-tune, incremental distillation, small tweak
          to a known architecture, minor benchmark delta.
     2  = cleanup, refactor, schema test, dataset resample, version
          bump with no new capability.

3. UNDEREXPLOITED (weight 25%) — has nobody built products on this yet?
     10 = released <7 days ago, zero products, zero community buzz
          beyond the authors' own repo.
     8  = released <14 days, maybe 1-2 basic community experiments.
     6  = released <30 days, small growing awareness.
     4  = released 1-3 months ago, moderate adoption, several forks.
     2  = well-known, widely adopted, many products. Everyone at
          the hackathon has heard of it.
   When in doubt, score LOWER — if lots of people already know about
   it, it's not useful for hackathon differentiation.

4. WOW (weight 10%) — does the TECH itself provoke "wait, what?"
   Not demo sizzle. Not UI polish. The tech itself.
     10 = cross-disciplinary, mind-bending (brain activity prediction,
          molecular viz, real-time audio separation by voice description,
          novel 3D/AR/spatial primitives, AI bridging a surprising domain).
     7  = technically impressive, clearly interesting at a glance.
     5  = solid tech, nothing jaw-dropping.
     3  = narrow utility, incremental.
     1  = purely theoretical, no capability to point at.

TOTAL = usability*0.30 + innovation*0.35 + underexploited*0.25 + wow*0.10

Compute it yourself as total_score. The downstream code will recompute and
override, but giving a self-consistent total in the response helps debugging.

OUTPUT — the flagship content is a TECH EXPLAINER, not a product pitch:

For ALL items, regardless of score, provide:
  - "summary": ONE sentence. What the tech is + why it exists.

For items where total_score >= 6.5, ALSO provide (these are required):
  - "what_the_tech_does": 4-6 sentences of concrete technical substance.
    Cover: what kind of model/architecture/API it is, what inputs/outputs
    it handles, any SOTA or benchmark claim, the closest prior work or
    how this differs, the license + artifact state. Write it like a
    senior engineer explaining to another senior engineer — name actual
    model classes, datasets, techniques. No marketing language.
  - "key_capabilities": 3-5 short bullets. Each bullet is ONE concrete
    fact: hardware requirement, license, a benchmark number, a model
    size, a notable capability. Be specific.
  - "idea_sparks": EXACTLY 3 complete PRODUCT CONCEPTS (not features, not
    research directions, not visualization ideas). Each must follow this
    template in a single sentence, under 40 words:

      "[Product type] for [specific user] that [does what] — only
       possible now because [this tech enables what was previously
       impossible]"

    BAD: "Visualize agent decision trees in real time."
    GOOD: "An AI agent replay debugger for developers where you paste an
    execution trace and get an interactive visual timeline of every tool
    call and failure point — only possible now because Project Telescope
    captures agent internals that were previously opaque."

    BAD: "Build apps that query satellite data by location only."
    GOOD: "A climate-change timelapse generator for journalists where you
    type any GPS coordinate and get a 10-year satellite animation of that
    spot — only possible now because LIANet reconstructs imagery from
    coordinates without needing raw data access."

    Each spark MUST name a specific user (developers, designers,
    journalists, students, marketers, clinicians, musicians, etc.) AND
    explain why this SPECIFIC tech unlocks it. A spark that could describe
    any model in the same space has failed. The "only possible now
    because" clause is non-negotiable — it's what separates a product
    concept from a feature list.

For items where total_score < 6.5:
  - Set what_the_tech_does, key_capabilities, and idea_sparks to null.
  - The 1-sentence summary is sufficient for below-the-fold items.

ANTI-PATTERNS — do NOT do any of these:
  - Do NOT write "Hackathon idea: build a Next.js webapp that..." as
    the flagship content. The tech explainer is the flagship.
  - Do NOT enumerate tech stacks for the user ("use Next.js + FastAPI").
  - Do NOT give Usability 10 to a paper because it's "free to read."
    Usability is about BUILDING, not reading.
  - Do NOT give Innovation 10 just because it's from a big lab.
    Innovation is about the TECH, not the badge.
  - Do NOT give Underexploited 10 just because the item is recent.
    Underexploited is about community adoption, not publish date alone.
  - Do NOT pad idea_sparks to 5. Stop at 2-3.
  - Do NOT leave the required fields null when total_score >= 6.5.

Respond ONLY in valid JSON matching the schema. No markdown, no preamble,
no text outside the JSON object.
""").strip()


def _derive_owner_org(item: Item) -> Optional[str]:
    """Infer the parent research org from an Item.

    Priority:
      1. If any source in the item's sources list is in SOURCE_TO_ORG,
         return the mapped org (e.g. 'Meta AI Blog' -> 'Meta FAIR').
      2. If the GitHub URL has a known research org prefix, return it.
      3. None — let the LLM reason from the URL shape alone.
    """
    from hackradar import config as _cfg

    sources_to_check = set(item.all_sources or [item.source])
    sources_to_check.add(item.source)
    for s in sources_to_check:
        if s in _cfg.SOURCE_TO_ORG:
            return _cfg.SOURCE_TO_ORG[s]

    # GitHub URL org prefix.
    gh = item.github_url or ""
    for org in _cfg.GITHUB_ORGS:
        if f"/{org}/" in gh or gh.endswith(f"/{org}"):
            return org
    # HuggingFace owner prefix (huggingface.co/<owner>/<name>).
    hf = item.huggingface_url or ""
    if "huggingface.co/" in hf:
        tail = hf.split("huggingface.co/", 1)[1].split("/")[0]
        if tail:
            return tail
    return None


def format_item_for_scoring(item: Item) -> dict[str, Any]:
    """Full representation for Pass 2.

    Rev 3.1: richer TECH-side context, lighter product-side.
    Description up to 1500 chars (abstract-class content), readme up to
    1000 chars (inference instructions, hardware reqs, license usually
    appear in the first ~1K chars of a model card). Owner org explicit.
    """
    d: dict[str, Any] = {
        "title": item.title,
        "description": (item.description or "")[:1500],
        "category": item.category,
        "source_count": item.source_count,
        "sources": item.all_sources,
    }
    owner = _derive_owner_org(item)
    if owner:
        d["owner_org"] = owner
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
        d["readme_excerpt"] = item.readme_excerpt[:1000]
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
        '      "usability_score": 9.0,\n'
        '      "innovation_score": 10.0,\n'
        '      "underexploited_score": 10.0,\n'
        '      "wow_score": 10.0,\n'
        '      "total_score": 9.70,\n'
        '      "summary": "<one-sentence description>",\n'
        '      "what_the_tech_does": "<4-6 sentences of technical substance: what kind of model/API it is, inputs/outputs, architecture, SOTA claim, prior-art comparison, license/artifact state.>",\n'
        '      "key_capabilities": [\n'
        '        "<one concrete fact: hardware requirement>",\n'
        '        "<one concrete fact: license>",\n'
        '        "<one concrete fact: benchmark number or capability>"\n'
        '      ],\n'
        '      "idea_sparks": [\n'
        '        "<product concept following the template, under 40 words>",\n'
        '        "<product concept following the template, under 40 words>",\n'
        '        "<product concept following the template, under 40 words>"\n'
        '      ]\n'
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
        f"EVERY item MUST include ALL of these fields: title (copy the exact "
        f"title string from the input), usability_score, innovation_score, "
        f"underexploited_score, wow_score, total_score, summary.\n\n"
        f"The three rich fields (what_the_tech_does, key_capabilities, "
        f"idea_sparks) are REQUIRED when total_score >= 6.5, otherwise set "
        f"them to null. key_capabilities must have 3-5 items. idea_sparks "
        f"must have EXACTLY 3 items, each a complete product concept under "
        f"40 words following the '[Product] for [user] that [does what] — "
        f"only possible now because [tech enables what was impossible]' "
        f"template. Each spark MUST name a specific user and a 'why now' "
        f"clause.\n\n"
        f"Shape example (for one item):\n{example}"
    )


# ---------------------------------------------------------------------------
# Context budgeting
# ---------------------------------------------------------------------------

def estimate_tokens(text: str) -> int:
    """Cheap token estimate. ~4 chars/token for English."""
    return max(1, len(text) // 4)
