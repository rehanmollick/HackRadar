"""Unit tests for CerebrasProvider, including the critical context overflow guard."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from hackradar.models import Item, ScoringBatchResponse
from hackradar.scoring.prompts import build_pass2_prompt
from hackradar.scoring.providers.base import ContextOverflowError, ProviderError
from hackradar.scoring.providers.cerebras import CerebrasProvider

CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"


def _make_cerebras_response(items: list[dict]) -> dict:
    return {
        "choices": [
            {"message": {"content": json.dumps({"items": items})}}
        ]
    }


def _scored_entry(title: str, total: float) -> dict:
    return {
        "title": title,
        "open_score": total,
        "novelty_score": total,
        "wow_score": total,
        "build_score": total,
        "total_score": total,
        "summary": "summary text",
        "hackathon_idea": "idea",
        "tech_stack": "stack",
        "why_now": "why",
        "effort_estimate": "1 weekend",
    }


def _tribe_item() -> Item:
    return Item(
        title="TRIBE v2",
        description="Brain activity prediction FM",
        date=datetime(2026, 3, 26, tzinfo=timezone.utc),
        source="meta_ai_blog",
        source_url="https://ai.meta.com/blog/tribe-v2",
        category="ai_research",
        huggingface_url="https://huggingface.co/facebook/tribev2",
        github_url="https://github.com/facebookresearch/tribev2",
    )


@respx.mock
async def test_call_batch_happy_path():
    items = [_tribe_item()]
    mock_response = _make_cerebras_response([_scored_entry("TRIBE v2", 9.5)])
    respx.post(CEREBRAS_URL).mock(return_value=httpx.Response(200, json=mock_response))

    provider = CerebrasProvider(api_key="test-key")
    result = await provider.call_batch(items, build_pass2_prompt(items), ScoringBatchResponse)

    assert len(result.items) == 1
    assert result.items[0].total_score == 9.5


async def test_context_overflow_raises_client_side_before_any_call():
    """CRITICAL: oversized batch must raise ContextOverflowError BEFORE the HTTP call."""
    # Build an absurdly large prompt that guarantees we blow the context budget.
    huge_prompt = "x" * 50000  # ~12500 tokens at 4 chars/token
    items = [_tribe_item()]

    provider = CerebrasProvider(api_key="test-key")
    with pytest.raises(ContextOverflowError, match="exceeds context budget"):
        # Note: no respx.mock — if this touches the network, it will fail loudly.
        await provider.call_batch(items, huge_prompt, ScoringBatchResponse)


async def test_missing_api_key_raises_provider_error():
    provider = CerebrasProvider(api_key="")
    with pytest.raises(ProviderError, match="CEREBRAS_API_KEY"):
        await provider.call_batch([_tribe_item()], "tiny prompt", ScoringBatchResponse)


@respx.mock
async def test_call_batch_multiple_items():
    items = [_tribe_item(), _tribe_item()]
    mock_response = _make_cerebras_response(
        [_scored_entry("TRIBE v2", 9.5), _scored_entry("TRIBE v2", 9.0)]
    )
    respx.post(CEREBRAS_URL).mock(return_value=httpx.Response(200, json=mock_response))

    provider = CerebrasProvider(api_key="test-key")
    result = await provider.call_batch(items, build_pass2_prompt(items), ScoringBatchResponse)
    assert len(result.items) == 2
