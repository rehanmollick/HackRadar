"""Unit tests for hackradar.db — schema init, content_hash, upsert, source health."""

from __future__ import annotations

import json

import pytest

from hackradar import db


def test_content_hash_priority_github_over_hf():
    h = db.compute_content_hash(
        github_url="https://github.com/facebookresearch/tribev2",
        huggingface_url="https://huggingface.co/facebook/tribev2",
        paper_url=None,
        source_url="https://ai.meta.com/blog/tribe-v2",
        title="TRIBE v2",
    )
    expected = db.compute_content_hash(
        github_url="https://github.com/facebookresearch/tribev2",
        huggingface_url=None,
        paper_url=None,
        source_url=None,
        title="unrelated title",
    )
    assert h == expected


def test_content_hash_priority_hf_when_no_github():
    h = db.compute_content_hash(
        github_url=None,
        huggingface_url="https://huggingface.co/facebook/tribev2",
        paper_url="https://arxiv.org/abs/2603.12345",
        source_url=None,
        title="anything",
    )
    expected = db.compute_content_hash(
        github_url=None,
        huggingface_url="https://huggingface.co/facebook/tribev2",
        paper_url=None,
        source_url=None,
        title="anything",
    )
    assert h == expected


def test_content_hash_all_null_urls_falls_back_to_title():
    h = db.compute_content_hash(
        github_url=None,
        huggingface_url=None,
        paper_url=None,
        source_url=None,
        title="Cool New Thing!  ",
    )
    h2 = db.compute_content_hash(
        github_url=None,
        huggingface_url=None,
        paper_url=None,
        source_url=None,
        title="cool new thing",
    )
    assert h == h2


async def test_init_idempotent(tmp_path, monkeypatch):
    from hackradar import config

    path = tmp_path / "hackradar.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    await db.init()
    await db.init()  # Must not raise
    assert path.exists()


async def test_create_scan_returns_id(temp_db):
    scan_id = await db.create_scan(
        window_start="2026-03-25T00:00:00+00:00",
        window_end="2026-03-27T00:00:00+00:00",
        sources=["meta_ai_blog", "arxiv"],
    )
    assert isinstance(scan_id, int) and scan_id > 0

    row = await db.get_scan(scan_id)
    assert row is not None
    assert row["status"] == "running"
    assert json.loads(row["sources"]) == ["meta_ai_blog", "arxiv"]


async def test_finish_scan_writes_status_and_counts(temp_db):
    scan_id = await db.create_scan(
        window_start="2026-03-25T00:00:00+00:00",
        window_end="2026-03-27T00:00:00+00:00",
        sources=["meta_ai_blog"],
    )
    await db.finish_scan(scan_id, status="done", items_found=450, items_scored=87)
    row = await db.get_scan(scan_id)
    assert row["status"] == "done"
    assert row["items_found"] == 450
    assert row["items_scored"] == 87
    assert row["finished_at"] is not None


async def test_upsert_item_first_insert(temp_db):
    item_id = await db.upsert_item(
        {
            "title": "TRIBE v2",
            "description": "Brain predictive FM",
            "date": "2026-03-26T00:00:00+00:00",
            "category": "ai_research",
            "source": "meta_ai_blog",
            "source_url": "https://ai.meta.com/blog/tribe-v2",
            "all_sources": ["meta_ai_blog"],
        }
    )
    assert item_id > 0
    row = await db.get_item(item_id)
    assert row is not None
    assert row["title"] == "TRIBE v2"
    assert row["github_url"] is None


async def test_content_hash_stable_across_scans(temp_db):
    """THE CRITICAL REGRESSION TEST.

    Scan #1 finds TRIBE v2 on the Meta AI blog (only source_url set).
    Scan #2 finds it again on HuggingFace + GitHub. Because the dedup
    layer produces a merged Item with the same title, upsert MUST merge
    the new URLs into the existing row, NOT recompute the hash.
    """
    # Scan #1: just the blog
    id1 = await db.upsert_item(
        {
            "title": "TRIBE v2 Brain Model",
            "description": "FAIR announces TRIBE v2",
            "date": "2026-03-26T00:00:00+00:00",
            "category": "ai_research",
            "source": "meta_ai_blog",
            "source_url": "https://ai.meta.com/blog/tribe-v2",
            "all_sources": ["meta_ai_blog"],
        }
    )

    # Scan #2: dedup has merged blog + HF + GitHub into one candidate with
    # the canonical source_url still pointing at the blog.
    id2 = await db.upsert_item(
        {
            "title": "TRIBE v2 Brain Model",
            "description": "FAIR announces TRIBE v2",
            "date": "2026-03-26T00:00:00+00:00",
            "category": "ai_research",
            "source": "meta_ai_blog",
            "source_url": "https://ai.meta.com/blog/tribe-v2",
            "github_url": "https://github.com/facebookresearch/tribev2",
            "huggingface_url": "https://huggingface.co/facebook/tribev2",
            "all_sources": ["meta_ai_blog", "github_research_orgs", "huggingface_models"],
        }
    )

    assert id1 == id2  # Same row, URLs merged in place.

    row = await db.get_item(id1)
    assert row["github_url"] == "https://github.com/facebookresearch/tribev2"
    assert row["huggingface_url"] == "https://huggingface.co/facebook/tribev2"
    assert row["source_url"] == "https://ai.meta.com/blog/tribe-v2"
    sources = json.loads(row["all_sources"])
    assert set(sources) == {"meta_ai_blog", "github_research_orgs", "huggingface_models"}


async def test_upsert_item_second_seen_preserves_existing_urls(temp_db):
    """New upsert cannot clobber an existing URL with null."""
    id1 = await db.upsert_item(
        {
            "title": "Thing",
            "date": "2026-03-26T00:00:00+00:00",
            "source": "x",
            "source_url": "https://x/y",
            "github_url": "https://github.com/a/b",
        }
    )
    id2 = await db.upsert_item(
        {
            "title": "Thing",
            "date": "2026-03-26T00:00:00+00:00",
            "source": "x",
            "source_url": "https://x/y",
            "github_url": None,  # must not wipe existing
        }
    )
    assert id1 == id2
    row = await db.get_item(id1)
    assert row["github_url"] == "https://github.com/a/b"


async def test_record_score_happy_path(temp_db):
    scan_id = await db.create_scan(
        window_start="2026-03-25T00:00:00+00:00",
        window_end="2026-03-27T00:00:00+00:00",
        sources=["meta_ai_blog"],
    )
    item_id = await db.upsert_item(
        {
            "title": "TRIBE v2",
            "date": "2026-03-26T00:00:00+00:00",
            "source": "meta_ai_blog",
            "source_url": "https://ai.meta.com/blog/tribe-v2",
        }
    )
    score_id = await db.record_score(
        item_id=item_id,
        scan_id=scan_id,
        pass_num=2,
        provider="cerebras",
        model="qwen-3-32b",
        open_score=9.0,
        novelty_score=10.0,
        wow_score=10.0,
        build_score=8.5,
        total_score=9.45,
        summary="A brain FM that runs on free GPUs.",
        hackathon_idea="3D brain visualizer comparing images",
    )
    assert score_id > 0

    rows = await db.get_items_for_scan(scan_id, min_score=8.0)
    assert len(rows) == 1
    assert rows[0]["title"] == "TRIBE v2"
    assert rows[0]["total_score"] == 9.45


async def test_source_health_success_clears_failures(temp_db):
    await db.record_source_health(source="meta_ai_blog", success=False, last_error="404")
    await db.record_source_health(source="meta_ai_blog", success=False, last_error="500")
    await db.record_source_health(source="meta_ai_blog", success=True)

    health = await db.get_all_source_health()
    assert len(health) == 1
    row = health[0]
    assert row["source"] == "meta_ai_blog"
    assert row["consecutive_failures"] == 0
    assert row["total_runs"] == 3
    assert row["total_failures"] == 2
    assert row["last_success"] is not None


async def test_source_health_failure_increments(temp_db):
    await db.record_source_health(source="stability_ai_blog", success=False, last_error="404 Not Found")
    await db.record_source_health(source="stability_ai_blog", success=False, last_error="Timeout")

    health = await db.get_all_source_health()
    row = next(r for r in health if r["source"] == "stability_ai_blog")
    assert row["consecutive_failures"] == 2
    assert row["last_error"] == "Timeout"
    assert row["total_failures"] == 2


async def test_get_items_for_scan_empty(temp_db):
    scan_id = await db.create_scan(
        window_start="2026-03-25T00:00:00+00:00",
        window_end="2026-03-27T00:00:00+00:00",
        sources=[],
    )
    assert await db.get_items_for_scan(scan_id) == []


async def test_chats_roundtrip(temp_db):
    item_id = await db.upsert_item(
        {
            "title": "Thing",
            "date": "2026-03-26T00:00:00+00:00",
            "source": "x",
            "source_url": "https://x/y",
        }
    )
    await db.append_chat(item_id, "user", "Tell me more about this.")
    await db.append_chat(item_id, "assistant", "Sure! Here's...")
    chats = await db.get_chats_for_item(item_id)
    assert len(chats) == 2
    assert chats[0]["role"] == "user"
    assert chats[1]["role"] == "assistant"


async def test_any_scan_running(temp_db):
    assert await db.any_scan_running() is False
    scan_id = await db.create_scan(
        window_start="2026-03-25T00:00:00+00:00",
        window_end="2026-03-27T00:00:00+00:00",
        sources=["x"],
    )
    assert await db.any_scan_running() is True
    await db.finish_scan(scan_id, status="done", items_found=0, items_scored=0)
    assert await db.any_scan_running() is False
