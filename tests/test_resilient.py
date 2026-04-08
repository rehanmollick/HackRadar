"""Unit tests for the resilient coordinator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator, Type, TypeVar
from unittest.mock import AsyncMock

import pytest

from hackradar.models import Item, TriageBatchResponse, TriageResponse
from hackradar.scoring.prompts import build_pass1_prompt
from hackradar.scoring.providers.base import (
    ContextOverflowError,
    ProviderError,
    RateLimitError,
    SchemaValidationError,
    TransientError,
)
from hackradar.scoring.resilient import call_with_fallback

T = TypeVar("T")


class FakeProvider:
    """Minimal fake LLMProvider for unit testing resilient.py."""

    def __init__(self, name: str, behaviors: list):
        """behaviors: list of exceptions or TriageBatchResponse to return in sequence."""
        self.name = name
        self.model = "fake"
        self.behaviors = list(behaviors)
        self.calls = 0

    async def call_batch(self, items, prompt, response_schema):
        self.calls += 1
        if not self.behaviors:
            raise ProviderError(f"{self.name}: no more behaviors")
        behavior = self.behaviors.pop(0)
        if isinstance(behavior, Exception):
            raise behavior
        return behavior

    async def chat_stream(self, messages, system) -> AsyncIterator[str]:
        yield ""  # pragma: no cover


def _items(n: int = 2) -> list[Item]:
    return [
        Item(
            title=f"Item {i}",
            description=f"desc {i}",
            date=datetime(2026, 3, 26, tzinfo=timezone.utc),
            source="meta_ai_blog",
            source_url=f"https://x/{i}",
            category="ai_research",
        )
        for i in range(n)
    ]


def _triage_response(titles: list[str]) -> TriageBatchResponse:
    return TriageBatchResponse(
        items=[
            TriageResponse(title=t, triage_score=7.5, reason="ok")
            for t in titles
        ]
    )


async def test_first_provider_success():
    items = _items(2)
    success = _triage_response(["Item 0", "Item 1"])
    p1 = FakeProvider("p1", [success])
    p2 = FakeProvider("p2", [])

    result, name = await call_with_fallback([p1, p2], items, build_pass1_prompt, TriageBatchResponse)

    assert name == "p1"
    assert result is not None
    assert len(result.items) == 2
    assert p1.calls == 1
    assert p2.calls == 0


async def test_transient_retries_then_succeeds():
    items = _items(2)
    success = _triage_response(["Item 0", "Item 1"])
    p1 = FakeProvider("p1", [TransientError("timeout"), success])

    result, name = await call_with_fallback([p1], items, build_pass1_prompt, TriageBatchResponse)

    assert name == "p1"
    assert p1.calls == 2  # retried once


async def test_rate_limit_skips_retry_falls_through():
    items = _items(2)
    success = _triage_response(["Item 0", "Item 1"])
    p1 = FakeProvider("p1", [RateLimitError("429")])
    p2 = FakeProvider("p2", [success])

    result, name = await call_with_fallback([p1, p2], items, build_pass1_prompt, TriageBatchResponse)

    assert name == "p2"
    assert p1.calls == 1  # did NOT retry
    assert p2.calls == 1


async def test_context_overflow_falls_through_immediately():
    items = _items(2)
    success = _triage_response(["Item 0", "Item 1"])
    p1 = FakeProvider("p1", [ContextOverflowError("too big")])
    p2 = FakeProvider("p2", [success])

    result, name = await call_with_fallback([p1, p2], items, build_pass1_prompt, TriageBatchResponse)

    assert name == "p2"
    assert p1.calls == 1


async def test_schema_validation_falls_through():
    items = _items(2)
    success = _triage_response(["Item 0", "Item 1"])
    p1 = FakeProvider("p1", [SchemaValidationError("bad json")])
    p2 = FakeProvider("p2", [success])

    result, name = await call_with_fallback([p1, p2], items, build_pass1_prompt, TriageBatchResponse)

    assert name == "p2"


async def test_all_providers_dead_splits_to_individual_then_returns_empty():
    items = _items(3)
    # p2 fails the batch, then fails every individual call too.
    p1 = FakeProvider("p1", [ProviderError("batch fail")])
    p2 = FakeProvider("p2", [
        ProviderError("batch fail"),  # main batch
        ProviderError("indiv 0"),
        ProviderError("indiv 1"),
        ProviderError("indiv 2"),
    ])

    result, name = await call_with_fallback([p1, p2], items, build_pass1_prompt, TriageBatchResponse)

    assert result is None
    assert name is None
    # p2 gets 1 batch attempt + 3 individual attempts = 4
    assert p2.calls == 4


async def test_last_provider_batch_fail_splits_to_individual_partial_success():
    items = _items(3)
    # p1 fails, p2's batch fails but 2 of 3 individuals succeed.
    r0 = _triage_response(["Item 0"])
    r2 = _triage_response(["Item 2"])
    p1 = FakeProvider("p1", [ProviderError("p1 batch")])
    p2 = FakeProvider("p2", [
        ProviderError("p2 batch"),
        r0,                                        # Item 0 individual OK
        ProviderError("Item 1 individual fail"),   # Item 1 fails
        r2,                                        # Item 2 individual OK
    ])

    result, name = await call_with_fallback([p1, p2], items, build_pass1_prompt, TriageBatchResponse)

    assert name == "p2"
    assert result is not None
    assert len(result.items) == 2
    assert {r.title for r in result.items} == {"Item 0", "Item 2"}


async def test_empty_items_returns_none():
    result, name = await call_with_fallback([], [], build_pass1_prompt, TriageBatchResponse)
    assert result is None
    assert name is None
