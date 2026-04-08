"""Smoke + integration tests for the FastAPI backend.

Uses FastAPI's TestClient with a per-test temp DB. The scan endpoint runs the
real run_scan, so we patch get_all_sources / providers / enrich just like the
TRIBE v2 validation gate does.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from hackradar import config, db
from hackradar.api import app
from hackradar.models import (
    Item,
    ScoredItemResponse,
    ScoringBatchResponse,
    ScrapeResult,
    TriageBatchResponse,
    TriageResponse,
)


# ---------------------------------------------------------------------------
# Fakes — minimal scrapers + providers shared across tests
# ---------------------------------------------------------------------------

def _fake_scrape(lookback_hours: int) -> ScrapeResult:
    return ScrapeResult(
        items=[
            Item(
                title="TRIBE v2: Brain Predictive FM",
                description="Meta FAIR brain activity foundation model.",
                date=datetime(2026, 3, 26, 9, 0, tzinfo=timezone.utc),
                source="meta_ai_blog",
                source_url="https://ai.meta.com/blog/tribe-v2-brain-predictive-foundation-model/",
                category="ai_research",
                github_url="https://github.com/facebookresearch/tribev2",
            )
        ],
        errors=[],
    )


def _fake_get_all_sources():
    return [("meta_ai_blog", _fake_scrape)]


class _FakeProvider:
    def __init__(self, name: str, response):
        self.name = name
        self.model = "fake"
        self._response = response

    async def call_batch(self, items, prompt, response_schema):
        return self._response

    async def chat_stream(self, messages, system) -> AsyncIterator[str]:
        yield ""  # pragma: no cover


def _fake_pass1():
    return [
        _FakeProvider(
            "fake_groq",
            TriageBatchResponse(
                items=[
                    TriageResponse(
                        title="placeholder", triage_score=10.0, reason="ok"
                    )
                ]
            ),
        )
    ]


def _fake_pass2():
    return [
        _FakeProvider(
            "fake_cerebras",
            ScoringBatchResponse(
                items=[
                    ScoredItemResponse(
                        title="TRIBE v2: Brain Predictive FM",
                        open_score=9.0,
                        novelty_score=10.0,
                        wow_score=9.0,
                        build_score=8.0,
                        total_score=9.15,
                        summary="Brain activity foundation model from Meta FAIR.",
                        hackathon_idea="Interactive 3D brain heatmap web app.",
                        tech_stack="Python + FastAPI + Next.js",
                        why_now="Released yesterday, zero apps built on it.",
                        effort_estimate="2 days prep + 24h hackathon",
                    )
                ]
            ),
        )
    ]


# ---------------------------------------------------------------------------
# Fixture: TestClient with isolated DB + mocked keys
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "api.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "GROQ_API_KEY", "fake")
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "fake")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "fake")
    monkeypatch.setitem(config.REQUIRED_KEYS, "GROQ_API_KEY", "fake")
    monkeypatch.setitem(config.REQUIRED_KEYS, "CEREBRAS_API_KEY", "fake")
    monkeypatch.setitem(config.REQUIRED_KEYS, "ANTHROPIC_API_KEY", "fake")

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------

def test_health_returns_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert "db_path" in body
    assert "sources_count" in body


# ---------------------------------------------------------------------------
# /api/scans round-trip (create → poll → fetch items)
# ---------------------------------------------------------------------------

def test_scan_create_and_fetch(client):
    with patch("hackradar.api.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.enrich_items", side_effect=lambda items: items), \
         patch("hackradar.main.build_pass1_providers", side_effect=_fake_pass1), \
         patch("hackradar.main.build_pass2_providers", side_effect=_fake_pass2):
        r = client.post(
            "/api/scans",
            json={"from_date": "2026-03-25", "to_date": "2026-03-27", "enrich": False},
        )
        assert r.status_code == 202, r.text
        body = r.json()
        scan_id = body["scan_id"]
        assert body["status"] == "running"

        # BackgroundTasks runs synchronously inside TestClient on context exit,
        # so by the time we fetch the scan it should be done.
        r2 = client.get(f"/api/scans/{scan_id}")
        assert r2.status_code == 200
        scan_body = r2.json()
        assert scan_body["scan"]["id"] == scan_id
        assert scan_body["scan"]["status"] == "done"
        assert len(scan_body["items"]) == 1
        top = scan_body["items"][0]
        assert "tribe" in top["title"].lower()
        assert top["total_score"] >= 9.0


def test_scan_list_returns_history(client):
    with patch("hackradar.api.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.enrich_items", side_effect=lambda items: items), \
         patch("hackradar.main.build_pass1_providers", side_effect=_fake_pass1), \
         patch("hackradar.main.build_pass2_providers", side_effect=_fake_pass2):
        client.post(
            "/api/scans",
            json={"from_date": "2026-03-25", "to_date": "2026-03-27", "enrich": False},
        )
        r = client.get("/api/scans")
        assert r.status_code == 200
        scans = r.json()["scans"]
        assert len(scans) >= 1
        assert scans[0]["status"] == "done"


def test_scan_latest_endpoint(client):
    with patch("hackradar.api.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.enrich_items", side_effect=lambda items: items), \
         patch("hackradar.main.build_pass1_providers", side_effect=_fake_pass1), \
         patch("hackradar.main.build_pass2_providers", side_effect=_fake_pass2):
        client.post(
            "/api/scans",
            json={"from_date": "2026-03-25", "to_date": "2026-03-27", "enrich": False},
        )
        r = client.get("/api/scans/latest")
        assert r.status_code == 200
        body = r.json()
        assert body["scan"]["status"] == "done"
        assert len(body["items"]) >= 1


def test_scan_latest_404_when_no_scans(client):
    r = client.get("/api/scans/latest")
    assert r.status_code == 404


def test_scan_get_404_for_unknown_id(client):
    r = client.get("/api/scans/9999")
    assert r.status_code == 404


def test_scan_create_412_when_keys_missing(client, monkeypatch):
    monkeypatch.setitem(config.REQUIRED_KEYS, "GROQ_API_KEY", "")
    r = client.post(
        "/api/scans",
        json={"from_date": "2026-03-25", "to_date": "2026-03-27"},
    )
    assert r.status_code == 412
    assert "GROQ_API_KEY" in r.json()["detail"]


def test_scan_create_404_for_unknown_source(client):
    r = client.post(
        "/api/scans",
        json={"source": "this_source_does_not_exist"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/items
# ---------------------------------------------------------------------------

def test_item_get_404_for_unknown_id(client):
    r = client.get("/api/items/9999")
    assert r.status_code == 404


def test_item_get_after_scan(client):
    with patch("hackradar.api.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.enrich_items", side_effect=lambda items: items), \
         patch("hackradar.main.build_pass1_providers", side_effect=_fake_pass1), \
         patch("hackradar.main.build_pass2_providers", side_effect=_fake_pass2):
        post = client.post(
            "/api/scans",
            json={"from_date": "2026-03-25", "to_date": "2026-03-27", "enrich": False},
        )
        scan_id = post.json()["scan_id"]
        scan = client.get(f"/api/scans/{scan_id}").json()
        assert scan["items"], "scan returned no items"
        item_id = scan["items"][0]["id"]

        r = client.get(f"/api/items/{item_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["item"]["id"] == item_id
        assert body["chats"] == []


# ---------------------------------------------------------------------------
# /api/sources/health
# ---------------------------------------------------------------------------

def test_sources_health_starts_empty(client):
    r = client.get("/api/sources/health")
    assert r.status_code == 200
    assert r.json() == {"sources": []}


# ---------------------------------------------------------------------------
# /api/items/{id}/chat — Pass 3 streaming chat
# ---------------------------------------------------------------------------

class _FakeAnthropic:
    name = "anthropic"
    model = "fake-claude"

    def __init__(self, chunks=None, raise_exc=None):
        self._chunks = chunks or ["Hello", " from", " fake", " Claude."]
        self._raise = raise_exc

    async def call_batch(self, items, prompt, response_schema):
        raise NotImplementedError

    async def chat_stream(self, messages, system) -> AsyncIterator[str]:
        if self._raise:
            raise self._raise
        for c in self._chunks:
            yield c


def _seed_item(client) -> int:
    """Run a fake scan so an item exists in the DB. Return its id."""
    with patch("hackradar.api.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.enrich_items", side_effect=lambda items: items), \
         patch("hackradar.main.build_pass1_providers", side_effect=_fake_pass1), \
         patch("hackradar.main.build_pass2_providers", side_effect=_fake_pass2):
        post = client.post(
            "/api/scans",
            json={"from_date": "2026-03-25", "to_date": "2026-03-27", "enrich": False},
        )
        scan_id = post.json()["scan_id"]
        scan = client.get(f"/api/scans/{scan_id}").json()
    return scan["items"][0]["id"]


def test_chat_streams_chunks_and_persists_history(client):
    item_id = _seed_item(client)
    fake = _FakeAnthropic(chunks=["Tribe", " v2", " is", " fascinating."])

    with patch("hackradar.api._provider_factory", return_value=fake):
        with client.stream(
            "POST",
            f"/api/items/{item_id}/chat",
            json={"message": "Tell me more"},
        ) as resp:
            assert resp.status_code == 200
            body = b"".join(resp.iter_bytes()).decode()

    # SSE body should contain each chunk + a [DONE] terminator
    assert "Tribe" in body
    assert "fascinating" in body
    assert "[DONE]" in body

    # User + assistant turns are now in chats
    item_resp = client.get(f"/api/items/{item_id}").json()
    chats = item_resp["chats"]
    assert any(c["role"] == "user" and c["content"] == "Tell me more" for c in chats)
    assert any(c["role"] == "assistant" and "fascinating" in c["content"] for c in chats)


def test_chat_404_for_unknown_item(client):
    with patch("hackradar.api._provider_factory", return_value=_FakeAnthropic()):
        r = client.post("/api/items/9999/chat", json={"message": "hi"})
    assert r.status_code == 404


def test_chat_rate_limited_when_quota_exhausted(client, monkeypatch):
    item_id = _seed_item(client)
    monkeypatch.setattr(config, "PASS3_RATE_LIMIT_PER_HOUR", 1)
    fake = _FakeAnthropic(chunks=["ok"])

    with patch("hackradar.api._provider_factory", return_value=fake):
        # First turn goes through
        r1 = client.post(
            f"/api/items/{item_id}/chat", json={"message": "first"}
        )
        # Drain the stream so the user turn gets persisted
        list(r1.iter_bytes())
        assert r1.status_code == 200

        # Second turn trips the rate limit
        r2 = client.post(
            f"/api/items/{item_id}/chat", json={"message": "second"}
        )
    assert r2.status_code == 429


def test_chat_provider_error_surfaces_in_stream(client):
    from hackradar.scoring.providers.base import ProviderError as PE

    item_id = _seed_item(client)
    fake = _FakeAnthropic(raise_exc=PE("boom"))

    with patch("hackradar.api._provider_factory", return_value=fake):
        with client.stream(
            "POST",
            f"/api/items/{item_id}/chat",
            json={"message": "hi"},
        ) as resp:
            assert resp.status_code == 200
            body = b"".join(resp.iter_bytes()).decode()
    assert "provider_error" in body
    assert "boom" in body


def test_sources_health_after_scan(client):
    with patch("hackradar.api.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.get_all_sources", side_effect=_fake_get_all_sources), \
         patch("hackradar.main.enrich_items", side_effect=lambda items: items), \
         patch("hackradar.main.build_pass1_providers", side_effect=_fake_pass1), \
         patch("hackradar.main.build_pass2_providers", side_effect=_fake_pass2):
        client.post(
            "/api/scans",
            json={"from_date": "2026-03-25", "to_date": "2026-03-27", "enrich": False},
        )
        r = client.get("/api/sources/health")
        assert r.status_code == 200
        sources = r.json()["sources"]
        assert any(s["source"] == "meta_ai_blog" for s in sources)
