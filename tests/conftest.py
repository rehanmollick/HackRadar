"""Shared fixtures for HackRadar V2 test suite."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from hackradar.models import Item


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_item(
    title: str = "Test Item",
    description: str = "A short description.",
    source: str = "test_source",
    source_url: str = "https://example.com/post/1",
    category: str = "ai_research",
    date: datetime | None = None,
    github_url: str | None = None,
    huggingface_url: str | None = None,
    demo_url: str | None = None,
    paper_url: str | None = None,
) -> Item:
    """Return a fully-populated Item with sensible defaults."""
    return Item(
        title=title,
        description=description,
        date=date or datetime(2026, 3, 26, 12, 0, 0, tzinfo=timezone.utc),
        source=source,
        source_url=source_url,
        category=category,
        github_url=github_url,
        huggingface_url=huggingface_url,
        demo_url=demo_url,
        paper_url=paper_url,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def item_factory():
    """Return the make_item factory so individual tests can call it freely."""
    return make_item


@pytest.fixture
def tribe_blog_item():
    """Simulate the Meta AI blog post for TRIBE v2."""
    return make_item(
        title="TRIBE v2: A Brain Predictive Foundation Model",
        description=(
            "Meta FAIR releases TRIBE v2, a foundation model for predicting "
            "brain activity from images and video. Open-source, runs on free GPUs."
        ),
        source="meta_ai_blog",
        source_url="https://ai.meta.com/blog/tribe-v2-brain-predictive-foundation-model/",
        category="ai_research",
        github_url="https://github.com/facebookresearch/tribev2",
    )


@pytest.fixture
def tribe_hf_item():
    """Simulate the HuggingFace model card for TRIBE v2."""
    return make_item(
        title="TRIBE v2 Brain Predictive Foundation Model",
        description=(
            "Facebook TRIBE v2 model on HuggingFace. "
            "Predict fMRI brain activations from visual stimuli."
        ),
        source="huggingface_models",
        source_url="https://huggingface.co/facebook/tribev2",
        category="ai_research",
        huggingface_url="https://huggingface.co/facebook/tribev2",
        github_url="https://github.com/facebookresearch/tribev2",
    )


@pytest.fixture
async def temp_db(tmp_path, monkeypatch):
    """Point hackradar.config.DB_PATH at a throwaway file and init the schema."""
    from hackradar import config, db

    path = tmp_path / "hackradar.db"
    monkeypatch.setattr(config, "DB_PATH", path)
    await db.init()
    yield path


@pytest.fixture
def tribe_arxiv_item():
    """Simulate an arXiv paper entry for TRIBE v2."""
    return make_item(
        title="TRIBE: Brain Predictive Foundation Models for Neural Decoding",
        description=(
            "We present TRIBE v2, a foundation model trained on large-scale "
            "fMRI datasets to predict brain activity from visual inputs."
        ),
        source="arxiv",
        source_url="https://arxiv.org/abs/2603.12345",
        category="ai_research",
        paper_url="https://arxiv.org/abs/2603.12345",
        github_url="https://github.com/facebookresearch/tribev2",
    )
