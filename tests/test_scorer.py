"""tests/test_scorer.py — Unit tests for hackradar.scorer.

All Gemini API calls are mocked at _call_gemini, so no network requests are
made and no API key is needed.

conftest.py stubs google.genai before this module is collected, so the
top-level import of hackradar.scorer succeeds even without the real package.
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, call

from hackradar.models import Item, ScoredItem, ScoredItemResponse, ScoringBatchResponse
from hackradar import config

# Import scorer at module level — conftest has already stubbed google.genai.
# This ensures the module object is in sys.modules so patch() can resolve
# "hackradar.scorer._call_gemini" correctly.
import hackradar.scorer as scorer_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(title: str = "Test Item", source: str = "test_source") -> Item:
    return Item(
        title=title,
        description="A fascinating new open-source AI model for testing.",
        date=datetime(2026, 3, 27),
        source=source,
        source_url=f"https://example.com/{title.replace(' ', '-').lower()}",
        category="ai_research",
    )


def _make_scored_response(
    title: str,
    open_score: float = 9.0,
    novelty_score: float = 9.0,
    wow_score: float = 9.0,
    build_score: float = 9.0,
    hackathon_idea: str | None = "Build a 3D brain visualisation app",
    tech_stack: str | None = "React Three Fiber, Python, HuggingFace",
    why_now: str | None = "Just released with zero products built on it",
    effort_estimate: str | None = "2 days prep + 24h hackathon",
) -> ScoredItemResponse:
    """Return a high-scoring ScoredItemResponse (total ~9.0)."""
    total = (
        open_score * config.WEIGHT_OPEN
        + novelty_score * config.WEIGHT_NOVELTY
        + wow_score * config.WEIGHT_WOW
        + build_score * config.WEIGHT_BUILD
    )
    return ScoredItemResponse(
        title=title,
        open_score=open_score,
        novelty_score=novelty_score,
        wow_score=wow_score,
        build_score=build_score,
        total_score=total,
        summary="An impressive new model that does something mind-bending.",
        hackathon_idea=hackathon_idea,
        tech_stack=tech_stack,
        why_now=why_now,
        effort_estimate=effort_estimate,
        links={"code": "https://github.com/example/repo"},
    )


def _make_low_scored_response(title: str) -> ScoredItemResponse:
    """Return a low-scoring ScoredItemResponse (total ~4.2) with no idea fields."""
    open_score = 3.0
    novelty_score = 4.0
    wow_score = 5.0
    build_score = 5.0
    total = (
        open_score * config.WEIGHT_OPEN
        + novelty_score * config.WEIGHT_NOVELTY
        + wow_score * config.WEIGHT_WOW
        + build_score * config.WEIGHT_BUILD
    )
    return ScoredItemResponse(
        title=title,
        open_score=open_score,
        novelty_score=novelty_score,
        wow_score=wow_score,
        build_score=build_score,
        total_score=total,
        summary="An incremental improvement to an existing tool.",
        hackathon_idea=None,
        tech_stack=None,
        why_now=None,
        effort_estimate=None,
        links=None,
    )


def _batch_response(responses: list[ScoredItemResponse]) -> ScoringBatchResponse:
    return ScoringBatchResponse(items=responses)


# ---------------------------------------------------------------------------
# Test 1: batch of 8 items returns valid Pydantic-validated results
# ---------------------------------------------------------------------------

def test_batch_of_8_returns_scored_items():
    """8 items in → 8 ScoredItem objects out, all Pydantic-validated."""
    items = [_make_item(f"Item {i}") for i in range(8)]
    responses = [_make_scored_response(f"Item {i}") for i in range(8)]
    batch_resp = _batch_response(responses)

    with patch.object(scorer_module, "_call_gemini", return_value=batch_resp), \
         patch.object(config, "GEMINI_API_KEY", "fake-key"):
        result = scorer_module.score_items(items)

    assert len(result) == 8
    for scored in result:
        assert isinstance(scored, ScoredItem)
        assert isinstance(scored.open_score, float)
        assert isinstance(scored.novelty_score, float)
        assert isinstance(scored.wow_score, float)
        assert isinstance(scored.build_score, float)
        assert isinstance(scored.total_score, float)
        assert 0.0 <= scored.total_score <= 10.0


# ---------------------------------------------------------------------------
# Test 2: items above 6.5 include idea fields
# ---------------------------------------------------------------------------

def test_high_score_items_include_idea_fields():
    """Items with total_score >= 6.5 must have hackathon_idea, tech_stack, why_now."""
    item = _make_item("TRIBE v2")
    resp = _make_scored_response(
        "TRIBE v2",
        open_score=9.0,
        novelty_score=9.0,
        wow_score=9.0,
        build_score=8.0,
        hackathon_idea="Build an interactive 3D brain viz app",
        tech_stack="React Three Fiber, Python",
        why_now="Released yesterday, nobody has built with it yet",
        effort_estimate="2 days prep",
    )
    batch_resp = _batch_response([resp])

    with patch.object(scorer_module, "_call_gemini", return_value=batch_resp), \
         patch.object(config, "GEMINI_API_KEY", "fake-key"):
        result = scorer_module.score_items([item])

    assert len(result) == 1
    scored = result[0]
    assert scored.total_score >= config.SCORE_THRESHOLD
    assert scored.hackathon_idea is not None
    assert scored.tech_stack is not None
    assert scored.why_now is not None
    assert scored.effort_estimate is not None


# ---------------------------------------------------------------------------
# Test 3: items below 6.5 have no idea fields
# ---------------------------------------------------------------------------

def test_low_score_items_exclude_idea_fields():
    """Items with total_score < 6.5 must NOT have hackathon_idea etc."""
    item = _make_item("Boring Old Library v1.0.1")
    resp = _make_low_scored_response("Boring Old Library v1.0.1")
    batch_resp = _batch_response([resp])

    with patch.object(scorer_module, "_call_gemini", return_value=batch_resp), \
         patch.object(config, "GEMINI_API_KEY", "fake-key"):
        result = scorer_module.score_items([item])

    assert len(result) == 1
    scored = result[0]
    assert scored.total_score < config.SCORE_THRESHOLD
    assert scored.hackathon_idea is None
    assert scored.tech_stack is None
    assert scored.why_now is None
    assert scored.effort_estimate is None
    assert scored.summary  # always present


# ---------------------------------------------------------------------------
# Test 4: weighted score calculation is correct
# ---------------------------------------------------------------------------

def test_weighted_score_calculation():
    """Total must equal open*0.20 + novelty*0.35 + wow*0.25 + build*0.20."""
    open_s, novelty_s, wow_s, build_s = 8.0, 7.0, 6.0, 9.0
    expected_total = (
        open_s * 0.20
        + novelty_s * 0.35
        + wow_s * 0.25
        + build_s * 0.20
    )

    item = _make_item("Score Math Item")
    resp = ScoredItemResponse(
        title="Score Math Item",
        open_score=open_s,
        novelty_score=novelty_s,
        wow_score=wow_s,
        build_score=build_s,
        total_score=99.0,  # intentionally wrong — scorer must recompute it
        summary="Testing weighted score arithmetic.",
        hackathon_idea="Some idea",
        tech_stack="Python",
        why_now="Just released",
        effort_estimate="1 day",
    )
    batch_resp = _batch_response([resp])

    with patch.object(scorer_module, "_call_gemini", return_value=batch_resp), \
         patch.object(config, "GEMINI_API_KEY", "fake-key"):
        result = scorer_module.score_items([item])

    assert len(result) == 1
    assert abs(result[0].total_score - expected_total) < 1e-9


# ---------------------------------------------------------------------------
# Test 5: Gemini error → retry once → success on retry
# ---------------------------------------------------------------------------

def test_gemini_retry_once_then_success():
    """First _call_gemini call raises, second succeeds — result is returned."""
    item = _make_item("Retry Item")
    resp = _make_scored_response("Retry Item")
    batch_resp = _batch_response([resp])

    side_effects = [RuntimeError("Gemini 500"), batch_resp]

    with patch.object(scorer_module, "_call_gemini", side_effect=side_effects) as mock_call, \
         patch.object(config, "GEMINI_API_KEY", "fake-key"):
        result = scorer_module.score_items([item])

    assert mock_call.call_count == 2
    assert len(result) == 1
    assert result[0].item.title == "Retry Item"


# ---------------------------------------------------------------------------
# Test 6: batch fails twice → individual fallback scoring
# ---------------------------------------------------------------------------

def test_batch_fails_twice_falls_back_to_individual():
    """Two batch failures → individual call per item is attempted."""
    items = [_make_item("Fallback Item A"), _make_item("Fallback Item B")]
    resp_a = _make_scored_response("Fallback Item A")
    resp_b = _make_scored_response("Fallback Item B")

    # Calls: batch attempt 1 → fail, batch attempt 2 → fail,
    #        individual for item A → succeed, individual for item B → succeed
    side_effects = [
        RuntimeError("batch fail 1"),
        RuntimeError("batch fail 2"),
        _batch_response([resp_a]),
        _batch_response([resp_b]),
    ]

    with patch.object(scorer_module, "_call_gemini", side_effect=side_effects) as mock_call, \
         patch.object(config, "GEMINI_API_KEY", "fake-key"):
        result = scorer_module.score_items(items)

    # 2 batch attempts + 2 individual fallback attempts = 4 total calls
    assert mock_call.call_count == 4
    assert len(result) == 2
    titles = {r.item.title for r in result}
    assert "Fallback Item A" in titles
    assert "Fallback Item B" in titles


# ---------------------------------------------------------------------------
# Test 7: empty items list → empty list returned immediately
# ---------------------------------------------------------------------------

def test_empty_items_returns_empty_list():
    """score_items([]) must return [] without calling the API at all."""
    with patch.object(scorer_module, "_call_gemini") as mock_call, \
         patch.object(config, "GEMINI_API_KEY", "fake-key"):
        result = scorer_module.score_items([])

    assert result == []
    mock_call.assert_not_called()
