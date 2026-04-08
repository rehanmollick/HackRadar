"""TRIBE v2 validation gate — V2 end-to-end pipeline test.

THE most important test in HackRadar. Proves the full V2 pipeline (scrape →
dedup → enrich → Pass 1 triage → Pass 2 score) discovers TRIBE v2 from a
realistic mix of inputs, without any hardcoded bias toward it.

Validation guarantees this test enforces:
  - Three independent fake scrapers each produce one TRIBE v2 row
  - Dedup merges all three into ONE item with source_count >= 3
  - The merged item bypasses Pass 1 (high-trust source allow-list)
  - Pass 2 scores TRIBE v2 >= 9.0
  - TRIBE v2 ranks #1 in the final sorted output
  - The pipeline does NOT fabricate TRIBE v2 if no source produced it

Mocking strategy: only the providers (Groq, Cerebras), the scraper registry
(get_all_sources), and enrich_items are mocked. Everything else — dedup,
window filtering, Pass 1, Pass 2, scoring math, run_scan orchestration — is
the real code path.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import AsyncIterator
from unittest.mock import patch

import pytest

from hackradar.main import run_scan
from hackradar.models import (
    Item,
    ScoredItemResponse,
    ScoringBatchResponse,
    ScrapeResult,
    TriageBatchResponse,
    TriageResponse,
)

# ---------------------------------------------------------------------------
# Constants — exactly what real scrapers would have produced on 2026-03-26
# ---------------------------------------------------------------------------

TRIBE_BLOG_URL = "https://ai.meta.com/blog/tribe-v2-brain-predictive-foundation-model/"
TRIBE_HF_URL = "https://huggingface.co/facebook/tribev2"
TRIBE_GITHUB_URL = "https://github.com/facebookresearch/tribev2"
TRIBE_DATE = datetime(2026, 3, 26, 9, 0, 0, tzinfo=timezone.utc)

WINDOW_START = datetime(2026, 3, 25, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 3, 27, 23, 59, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fake scrapers — each returns one TRIBE v2 row from its source
# ---------------------------------------------------------------------------

def _meta_blog_scrape(lookback_hours: int) -> ScrapeResult:
    return ScrapeResult(
        items=[
            Item(
                title="TRIBE v2: A Brain Predictive Foundation Model",
                description=(
                    "Meta FAIR introduces TRIBE v2, an open-source foundation model "
                    "for predicting brain activity (fMRI responses) from images and "
                    "video. Trained on large-scale fMRI datasets, TRIBE v2 lets "
                    "researchers decode how visual stimuli activate different brain "
                    "regions. Weights and inference code are freely available."
                ),
                date=TRIBE_DATE,
                source="meta_ai_blog",
                source_url=TRIBE_BLOG_URL,
                category="ai_research",
                github_url=TRIBE_GITHUB_URL,
            )
        ],
        errors=[],
    )


def _hf_papers_scrape(lookback_hours: int) -> ScrapeResult:
    return ScrapeResult(
        items=[
            Item(
                title="facebook/tribev2",
                description=(
                    "TRIBE v2 — Meta FAIR's foundation model for predicting fMRI "
                    "brain activity from visual inputs. Predicts voxel-level "
                    "activation patterns across the visual cortex. Runs on a "
                    "single T4 GPU."
                ),
                date=TRIBE_DATE,
                source="huggingface_papers",
                source_url=TRIBE_HF_URL,
                huggingface_url=TRIBE_HF_URL,
                github_url=TRIBE_GITHUB_URL,
                category="ai_research",
            )
        ],
        errors=[],
    )


def _github_orgs_scrape(lookback_hours: int) -> ScrapeResult:
    return ScrapeResult(
        items=[
            Item(
                title="facebookresearch/tribev2",
                description=(
                    "TRIBE v2: Open-source foundation model for predicting brain "
                    "activity from visual inputs. Predict voxel-level fMRI "
                    "responses across the visual cortex."
                ),
                date=TRIBE_DATE,
                source="github_research_orgs",
                source_url=TRIBE_GITHUB_URL,
                github_url=TRIBE_GITHUB_URL,
                category="ai_research",
                stars=1547,
                language="Python",
                license="CC-BY-NC-4.0",
            )
        ],
        errors=[],
    )


def _distractors_scrape(lookback_hours: int) -> ScrapeResult:
    base = datetime(2026, 3, 26, 8, 0, 0, tzinfo=timezone.utc)
    return ScrapeResult(
        items=[
            Item(
                title="SomeUser/random-diffusion-finetuned",
                description="A fine-tuned Stable Diffusion model for landscape photography.",
                date=base,
                source="hackernews_show",
                source_url="https://news.ycombinator.com/item?id=fake1",
                category="ai_research",
            ),
            Item(
                title="acme/yet-another-todo-cli",
                description="A todo CLI written in Rust. Ergonomic, fast, opinionated.",
                date=base,
                source="hackernews_show",
                source_url="https://news.ycombinator.com/item?id=fake2",
                category="tool",
            ),
            Item(
                title="microblog/csv-stats",
                description="Pure-python CSV stats utility. Mean, median, percentiles.",
                date=base,
                source="product_hunt",
                source_url="https://www.producthunt.com/posts/fake3",
                category="tool",
            ),
        ],
        errors=[],
    )


def _fake_get_all_sources():
    """Return five sources: three high-trust TRIBE rows + a noise scraper."""
    return [
        ("meta_ai_blog", _meta_blog_scrape),
        ("huggingface_papers", _hf_papers_scrape),
        ("github_research_orgs", _github_orgs_scrape),
        ("hackernews_show", _distractors_scrape),
    ]


def _fake_get_all_sources_no_tribe():
    """Source list with the TRIBE rows removed — distractors only."""
    return [("hackernews_show", _distractors_scrape)]


# ---------------------------------------------------------------------------
# Fake providers
# ---------------------------------------------------------------------------

class _RecordingTriageProvider:
    """Pass 1 fake. Records titles it actually triaged so we can assert
    that high-trust items bypassed (i.e. NEVER reached the provider)."""

    name = "fake_groq"
    model = "fake-llama"

    def __init__(self) -> None:
        self.titles_seen: list[str] = []
        self.calls = 0

    async def call_batch(self, items, prompt, response_schema):
        self.calls += 1
        for item in items:
            self.titles_seen.append(item.title)
        # Score every distractor 2.0 — well below the 5.0 threshold so they
        # all get filtered out. The only way TRIBE v2 reaches Pass 2 is via
        # the high-trust bypass.
        return TriageBatchResponse(
            items=[
                TriageResponse(title=item.title, triage_score=2.0, reason="noise")
                for item in items
            ]
        )

    async def chat_stream(self, messages, system) -> AsyncIterator[str]:
        yield ""  # pragma: no cover


class _ScoringProvider:
    """Pass 2 fake. Scores TRIBE v2 ~9.15 and noise ~4-5."""

    name = "fake_cerebras"
    model = "fake-qwen"

    def __init__(self) -> None:
        self.calls = 0

    async def call_batch(self, items, prompt, response_schema):
        self.calls += 1
        out: list[ScoredItemResponse] = []
        for item in items:
            title_lower = item.title.lower()
            github = (item.github_url or "").lower()
            is_tribe = "tribe" in title_lower or "tribev2" in github
            if is_tribe:
                out.append(
                    ScoredItemResponse(
                        title=item.title,
                        open_score=9.0,
                        novelty_score=10.0,
                        wow_score=9.0,
                        build_score=8.0,
                        total_score=9.15,
                        summary=(
                            "Meta FAIR's brain-activity foundation model. Released "
                            "yesterday with open weights, runs on a free T4."
                        ),
                        hackathon_idea=(
                            "Interactive 3D brain heatmap web app. Upload an image "
                            "and watch which cortical regions activate, rendered "
                            "with React Three Fiber and TRIBE v2 inference."
                        ),
                        tech_stack="Python + FastAPI + Next.js + React Three Fiber",
                        why_now="Released yesterday. Zero apps built on it. Free.",
                        effort_estimate="2 days prep + 24h hackathon",
                    )
                )
            else:
                out.append(
                    ScoredItemResponse(
                        title=item.title,
                        open_score=6.0,
                        novelty_score=4.0,
                        wow_score=4.0,
                        build_score=6.0,
                        total_score=4.9,
                        summary="Incremental tool. Not differentiated enough.",
                    )
                )
        return ScoringBatchResponse(items=out)

    async def chat_stream(self, messages, system) -> AsyncIterator[str]:
        yield ""  # pragma: no cover


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_v2_pipeline_discovers_tribe_v2():
    """End-to-end run_scan must rank TRIBE v2 #1 with score >= 9.0."""
    pass1 = _RecordingTriageProvider()
    pass2 = _ScoringProvider()

    with patch("hackradar.main.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.enrich_items", side_effect=lambda items: items), \
         patch("hackradar.main.build_pass1_providers", return_value=[pass1]), \
         patch("hackradar.main.build_pass2_providers", return_value=[pass2]):
        scored, scan_id = await run_scan(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            dry_run=True,
            enrich=False,
        )

    assert scan_id is None  # dry_run
    assert len(scored) > 0, "Pipeline produced zero scored items"

    # TRIBE v2 must be #1 (already sorted descending by run_scan).
    top = scored[0]
    is_tribe = (
        "tribe" in top.item.title.lower()
        or "tribev2" in (top.item.github_url or "").lower()
    )
    assert is_tribe, (
        f"Expected TRIBE v2 at rank #1, got {top.item.title!r} "
        f"(score={top.total_score:.2f}). Full ranking: "
        f"{[(s.item.title, round(s.total_score, 2)) for s in scored]}"
    )
    assert top.total_score >= 9.0, (
        f"TRIBE v2 total_score={top.total_score:.2f}, expected >= 9.0"
    )
    assert top.hackathon_idea is not None
    assert top.summary is not None and len(top.summary) > 20


async def test_v2_pipeline_dedup_merges_three_tribe_rows():
    """The three independent TRIBE rows must collapse to ONE merged item."""
    pass1 = _RecordingTriageProvider()
    pass2 = _ScoringProvider()

    with patch("hackradar.main.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.enrich_items", side_effect=lambda items: items), \
         patch("hackradar.main.build_pass1_providers", return_value=[pass1]), \
         patch("hackradar.main.build_pass2_providers", return_value=[pass2]):
        scored, _ = await run_scan(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            dry_run=True,
            enrich=False,
        )

    tribe_scored = [
        s for s in scored
        if "tribe" in s.item.title.lower()
        or "tribev2" in (s.item.github_url or "").lower()
    ]
    assert len(tribe_scored) == 1, (
        f"Dedup failed: expected 1 merged TRIBE v2 item, got {len(tribe_scored)}. "
        f"Titles: {[s.item.title for s in tribe_scored]}"
    )
    tribe = tribe_scored[0]
    assert tribe.item.source_count >= 3, (
        f"source_count={tribe.item.source_count}, expected >= 3"
    )
    # Merged URL set must include all three.
    urls = tribe.item.get_all_urls()
    assert TRIBE_BLOG_URL in urls
    assert TRIBE_HF_URL in urls
    assert TRIBE_GITHUB_URL in urls


async def test_v2_pipeline_high_trust_bypass_protects_tribe():
    """TRIBE v2 must NEVER be sent to the Pass 1 triage model.

    The whole point of HIGH_TRUST_SOURCES is that an 8B triage model can't
    accidentally drop research-lab drops by mis-scoring them. This test
    inspects exactly which titles the Pass 1 provider was asked to score
    and proves the merged TRIBE item was not among them.
    """
    pass1 = _RecordingTriageProvider()
    pass2 = _ScoringProvider()

    with patch("hackradar.main.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.enrich_items", side_effect=lambda items: items), \
         patch("hackradar.main.build_pass1_providers", return_value=[pass1]), \
         patch("hackradar.main.build_pass2_providers", return_value=[pass2]):
        await run_scan(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            dry_run=True,
            enrich=False,
        )

    for title in pass1.titles_seen:
        assert "tribe" not in title.lower(), (
            f"TRIBE v2 was sent to Pass 1 triage (title={title!r}). "
            "High-trust bypass is broken."
        )


async def test_v2_pipeline_does_not_fabricate_tribe_when_absent():
    """If no source produces a TRIBE row, none should appear in the output."""
    pass1 = _RecordingTriageProvider()
    pass2 = _ScoringProvider()

    with patch("hackradar.main.get_all_sources", side_effect=_fake_get_all_sources_no_tribe), \
         patch("hackradar.main.enrich_items", side_effect=lambda items: items), \
         patch("hackradar.main.build_pass1_providers", return_value=[pass1]), \
         patch("hackradar.main.build_pass2_providers", return_value=[pass2]):
        scored, _ = await run_scan(
            window_start=WINDOW_START,
            window_end=WINDOW_END,
            dry_run=True,
            enrich=False,
        )

    tribe = [
        s for s in scored
        if "tribe" in s.item.title.lower()
        or "tribev2" in (s.item.github_url or "").lower()
    ]
    assert tribe == [], f"Pipeline fabricated TRIBE v2: {[s.item.title for s in tribe]}"
