"""Unit tests for GroqProvider. Uses respx to mock httpx calls."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from hackradar.models import Item, TriageBatchResponse
from hackradar.scoring.prompts import build_pass1_prompt
from hackradar.scoring.providers.base import (
    ProviderError,
    RateLimitError,
    SchemaValidationError,
    TransientError,
)
from hackradar.scoring.providers.groq import GroqProvider

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _make_groq_response(items: list[dict]) -> dict:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps({"items": items}),
                }
            }
        ]
    }


def _sample_items() -> list[Item]:
    from datetime import datetime, timezone

    return [
        Item(
            title="TRIBE v2",
            description="Brain activity prediction foundation model",
            date=datetime(2026, 3, 26, tzinfo=timezone.utc),
            source="meta_ai_blog",
            source_url="https://ai.meta.com/blog/tribe-v2",
            category="ai_research",
        ),
        Item(
            title="Some minor CSS tweak",
            description="Incremental improvement to flexbox gap",
            date=datetime(2026, 3, 26, tzinfo=timezone.utc),
            source="chrome_platform",
            source_url="https://chromestatus.com/x",
            category="browser",
        ),
    ]


@respx.mock
async def test_call_batch_happy_path():
    items = _sample_items()
    mock_response = _make_groq_response(
        [
            {"title": "TRIBE v2", "triage_score": 9.5, "reason": "brand new brain FM"},
            {"title": "Some minor CSS tweak", "triage_score": 3.0, "reason": "incremental"},
        ]
    )
    respx.post(GROQ_URL).mock(return_value=httpx.Response(200, json=mock_response))

    provider = GroqProvider(api_key="test-key")
    result = await provider.call_batch(items, build_pass1_prompt(items), TriageBatchResponse)

    assert isinstance(result, TriageBatchResponse)
    assert len(result.items) == 2
    assert result.items[0].title == "TRIBE v2"
    assert result.items[0].triage_score == 9.5


@respx.mock
async def test_call_batch_429_raises_rate_limit():
    items = _sample_items()
    respx.post(GROQ_URL).mock(
        return_value=httpx.Response(429, json={"error": {"message": "Rate limit"}})
    )

    provider = GroqProvider(api_key="test-key")
    with pytest.raises(RateLimitError):
        await provider.call_batch(items, build_pass1_prompt(items), TriageBatchResponse)


@respx.mock
async def test_call_batch_500_raises_transient():
    items = _sample_items()
    respx.post(GROQ_URL).mock(return_value=httpx.Response(500, text="upstream error"))

    provider = GroqProvider(api_key="test-key")
    with pytest.raises(TransientError):
        await provider.call_batch(items, build_pass1_prompt(items), TriageBatchResponse)


@respx.mock
async def test_call_batch_400_raises_provider_error():
    items = _sample_items()
    respx.post(GROQ_URL).mock(return_value=httpx.Response(400, text="bad request"))

    provider = GroqProvider(api_key="test-key")
    with pytest.raises(ProviderError):
        await provider.call_batch(items, build_pass1_prompt(items), TriageBatchResponse)


@respx.mock
async def test_call_batch_timeout_raises_transient():
    items = _sample_items()
    respx.post(GROQ_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    provider = GroqProvider(api_key="test-key")
    with pytest.raises(TransientError):
        await provider.call_batch(items, build_pass1_prompt(items), TriageBatchResponse)


@respx.mock
async def test_call_batch_malformed_json_raises_schema_error():
    items = _sample_items()
    mock_response = {
        "choices": [{"message": {"content": "this is not JSON"}}]
    }
    respx.post(GROQ_URL).mock(return_value=httpx.Response(200, json=mock_response))

    provider = GroqProvider(api_key="test-key")
    with pytest.raises(SchemaValidationError):
        await provider.call_batch(items, build_pass1_prompt(items), TriageBatchResponse)


@respx.mock
async def test_call_batch_pydantic_validation_failure_raises_schema_error():
    items = _sample_items()
    # Valid JSON but wrong shape — missing required 'reason' field
    mock_response = _make_groq_response([{"title": "x", "triage_score": 7.0}])
    respx.post(GROQ_URL).mock(return_value=httpx.Response(200, json=mock_response))

    provider = GroqProvider(api_key="test-key")
    with pytest.raises(SchemaValidationError):
        await provider.call_batch(items, build_pass1_prompt(items), TriageBatchResponse)


async def test_missing_api_key_raises_provider_error():
    provider = GroqProvider(api_key="")
    with pytest.raises(ProviderError, match="GROQ_API_KEY"):
        await provider.call_batch(_sample_items(), "prompt", TriageBatchResponse)
