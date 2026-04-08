"""Unit tests for hackradar.scoring.passes — pass1_triage, pass2_score, health wrapper."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from hackradar import config
from hackradar.models import (
    Item,
    ScoredItemResponse,
    ScoringBatchResponse,
    ScrapeResult,
    TriageBatchResponse,
    TriageResponse,
)
from hackradar.scoring.passes import (
    pass1_triage,
    pass2_score,
    run_scraper_tracked,
)


class FakeProvider:
    def __init__(self, name: str, response):
        self.name = name
        self.model = "fake"
        self.response = response
        self.calls = 0

    async def call_batch(self, items, prompt, response_schema):
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        # Use whatever was pre-built (TriageBatchResponse or ScoringBatchResponse)
        return self.response

    async def chat_stream(self, messages, system) -> AsyncIterator[str]:
        yield ""  # pragma: no cover


def _make_item(title: str, source: str, **kwargs) -> Item:
    return Item(
        title=title,
        description=kwargs.get("description", "desc"),
        date=datetime(2026, 3, 26, tzinfo=timezone.utc),
        source=source,
        source_url=kwargs.get("source_url", f"https://x/{title}"),
        category=kwargs.get("category", "ai_research"),
    )


def _triage_resp(entries: list[tuple[str, float]]) -> TriageBatchResponse:
    return TriageBatchResponse(
        items=[
            TriageResponse(title=t, triage_score=s, reason=f"score={s}")
            for t, s in entries
        ]
    )


def _score_resp(entries: list[tuple[str, float]]) -> ScoringBatchResponse:
    return ScoringBatchResponse(
        items=[
            ScoredItemResponse(
                title=t,
                open_score=s,
                novelty_score=s,
                wow_score=s,
                build_score=s,
                total_score=s,
                summary=f"summary {t}",
                hackathon_idea=f"idea {t}" if s >= 6.5 else None,
                tech_stack="stack" if s >= 6.5 else None,
                why_now="why" if s >= 6.5 else None,
                effort_estimate="weekend" if s >= 6.5 else None,
            )
            for t, s in entries
        ]
    )


# ---------------------------------------------------------------------------
# Pass 1 triage
# ---------------------------------------------------------------------------

async def test_pass1_above_threshold_advances():
    items = [_make_item("Cool Tool", "hackernews_show")]
    provider = FakeProvider("fake", _triage_resp([("Cool Tool", 8.0)]))

    result = await pass1_triage(items, [provider], batch_size=20, threshold=5.0)

    assert len(result) == 1
    assert result[0].item.title == "Cool Tool"
    assert result[0].bypassed is False


async def test_pass1_below_threshold_filtered():
    items = [_make_item("Boring Thing", "hackernews_show")]
    provider = FakeProvider("fake", _triage_resp([("Boring Thing", 2.0)]))

    result = await pass1_triage(items, [provider], batch_size=20, threshold=5.0)

    assert result == []


async def test_pass1_high_trust_bypass_advances_regardless_of_score():
    """CRITICAL: item from Meta AI blog MUST advance even if triage would drop it.

    In the real TRIBE v2 scenario, an 8B model reading "TRIBE v2: Brain
    Predictive Foundation Model" from a terse blog scrape with no enrichment
    could easily score it low. The HIGH_TRUST_SOURCES allow-list is the safety
    net that guarantees research-lab drops reach Pass 2.
    """
    items = [
        _make_item("TRIBE v2 Brain Predictive FM", "meta_ai_blog"),
        _make_item("Unrelated noise", "hackernews_show"),
    ]
    # Triage only scores the non-bypassed item (noise). Returns score=2 for it.
    provider = FakeProvider("fake", _triage_resp([("Unrelated noise", 2.0)]))

    result = await pass1_triage(items, [provider], batch_size=20, threshold=5.0)

    # TRIBE v2 bypassed. Noise filtered out. Only TRIBE v2 remains.
    assert len(result) == 1
    assert result[0].item.title == "TRIBE v2 Brain Predictive FM"
    assert result[0].bypassed is True
    assert result[0].reason == "high-trust source bypass"


async def test_pass1_high_trust_with_hostile_triage_score_still_advances():
    """Even if we forced the triage model to return a low score for a high-trust
    source, the bypass happens BEFORE the triage call so the score is never consulted.
    """
    items = [_make_item("TRIBE v2", "meta_ai_blog")]
    # Provider returns nothing (empty response). If we weren't bypassing, Item
    # would be dropped. But bypass path never calls the provider for this item.
    provider = FakeProvider("fake", _triage_resp([]))

    result = await pass1_triage(items, [provider], batch_size=20, threshold=5.0)

    assert len(result) == 1
    assert result[0].bypassed is True
    # Provider should not have been called at all — everything was bypassed.
    assert provider.calls == 0


async def test_pass1_coordinator_dead_safety_advances_all():
    """If all providers die for every batch, non-bypassed items advance too."""
    items = [
        _make_item("Random tool", "hackernews_show"),
        _make_item("Another random thing", "product_hunt"),
    ]
    from hackradar.scoring.providers.base import ProviderError
    provider = FakeProvider("fake", ProviderError("dead"))

    result = await pass1_triage(items, [provider], batch_size=20, threshold=5.0)

    # Both items advanced via the safety bypass.
    assert len(result) == 2
    assert all(r.bypassed is False for r in result)
    assert all("coordinator dead" in r.reason for r in result)


async def test_pass1_empty_items_returns_empty():
    result = await pass1_triage([], [FakeProvider("fake", None)], batch_size=20)
    assert result == []


# ---------------------------------------------------------------------------
# Pass 2 scoring
# ---------------------------------------------------------------------------

async def test_pass2_happy_path():
    from hackradar.scoring.passes import TriagedItem

    item = _make_item("TRIBE v2", "meta_ai_blog")
    triaged = [TriagedItem(item=item, triage_score=10.0, reason="bypass", bypassed=True)]
    provider = FakeProvider("fake", _score_resp([("TRIBE v2", 9.5)]))

    result = await pass2_score(triaged, [provider], batch_size=3, inter_batch_sleep_s=0)

    assert len(result) == 1
    assert result[0].item.title == "TRIBE v2"
    assert result[0].total_score == 9.5
    assert result[0].hackathon_idea is not None  # above threshold


async def test_pass2_low_score_nulls_out_extras():
    from hackradar.scoring.passes import TriagedItem

    item = _make_item("Meh", "hackernews_show")
    triaged = [TriagedItem(item=item, triage_score=6.0, reason="ok", bypassed=False)]
    provider = FakeProvider("fake", _score_resp([("Meh", 4.0)]))

    result = await pass2_score(triaged, [provider], batch_size=3, inter_batch_sleep_s=0)

    assert len(result) == 1
    assert result[0].hackathon_idea is None  # below threshold


# ---------------------------------------------------------------------------
# Scraper tracked wrapper
# ---------------------------------------------------------------------------

async def test_run_scraper_tracked_success():
    records = []

    async def record(**kwargs):
        records.append(kwargs)

    def scrape(lookback_hours: int) -> ScrapeResult:
        return ScrapeResult(items=[_make_item("x", "y")], errors=[])

    result = await run_scraper_tracked(
        "test_source", scrape, lookback_hours=48, db_record_health=record
    )
    assert len(result.items) == 1
    assert records[-1]["source"] == "test_source"
    assert records[-1]["success"] is True


async def test_run_scraper_tracked_exception():
    records = []

    async def record(**kwargs):
        records.append(kwargs)

    def scrape(lookback_hours: int) -> ScrapeResult:
        raise ValueError("boom")

    result = await run_scraper_tracked(
        "broken_source", scrape, lookback_hours=48, db_record_health=record
    )
    assert result.items == []
    assert result.errors
    assert records[-1]["success"] is False
    assert "ValueError" in records[-1]["last_error"]


async def test_run_scraper_tracked_empty_with_errors_is_failure():
    """V1 treated 'empty result + errors' as success. V2 treats it as failure."""
    records = []

    async def record(**kwargs):
        records.append(kwargs)

    def scrape(lookback_hours: int) -> ScrapeResult:
        return ScrapeResult(items=[], errors=["404 Not Found"])

    result = await run_scraper_tracked(
        "quiet_fail_source", scrape, lookback_hours=48, db_record_health=record
    )
    assert records[-1]["success"] is False
    assert "404" in records[-1]["last_error"]


async def test_run_scraper_tracked_empty_no_errors_is_success():
    """Genuinely nothing new is NOT a failure."""
    records = []

    async def record(**kwargs):
        records.append(kwargs)

    def scrape(lookback_hours: int) -> ScrapeResult:
        return ScrapeResult(items=[], errors=[])

    result = await run_scraper_tracked(
        "slow_source", scrape, lookback_hours=48, db_record_health=record
    )
    assert records[-1]["success"] is True
