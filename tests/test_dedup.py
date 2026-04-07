"""tests/test_dedup.py — Unit tests for hackradar/dedup.py."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hackradar.dedup import deduplicate
from hackradar.models import Item
from tests.conftest import make_item


# ---------------------------------------------------------------------------
# 1. Exact URL match merges two items that share the same source_url
# ---------------------------------------------------------------------------

def test_exact_url_match_merges():
    """Two items with identical source_url must collapse into one."""
    shared_url = "https://ai.meta.com/blog/tribe-v2/"
    item_a = make_item(title="TRIBE v2 Blog Post", source="meta_ai_blog", source_url=shared_url)
    item_b = make_item(title="TRIBE v2 Blog Post", source="twitter", source_url=shared_url)

    result = deduplicate([item_a, item_b])

    assert len(result) == 1, "Expected the two items to merge into one"
    merged = result[0]
    assert merged.source_count == 2
    assert shared_url in merged.all_urls


# ---------------------------------------------------------------------------
# 2. Fuzzy title match (token_sort_ratio >= 85) merges items
# ---------------------------------------------------------------------------

def test_fuzzy_title_match_merges():
    """Items whose titles score >= 85 on token_sort_ratio should be merged."""
    item_a = make_item(
        title="TRIBE v2: A Brain Predictive Foundation Model",
        source="meta_ai_blog",
        source_url="https://ai.meta.com/blog/tribe-v2/",
    )
    item_b = make_item(
        title="TRIBE v2 Brain Predictive Foundation Model",  # no colon, very similar
        source="huggingface_papers",
        source_url="https://huggingface.co/papers/2603.12345",
    )

    result = deduplicate([item_a, item_b])

    assert len(result) == 1, "Fuzzy title match should merge the two items"
    assert result[0].source_count == 2


# ---------------------------------------------------------------------------
# 3. Fuzzy near-miss (~83) does NOT merge
# ---------------------------------------------------------------------------

def test_fuzzy_title_near_miss_does_not_merge():
    """Items whose fuzzy title score is below threshold must stay separate."""
    # Deliberately different-enough titles that score below 85
    item_a = make_item(
        title="TRIBE v2 Brain Predictive Foundation Model for Neural Decoding",
        source="meta_ai_blog",
        source_url="https://ai.meta.com/blog/tribe-v2/",
    )
    item_b = make_item(
        title="Cortex Mapper Decoding Visual Stimuli with Deep Learning",
        source="arxiv",
        source_url="https://arxiv.org/abs/9999.00001",
    )

    result = deduplicate([item_a, item_b])

    assert len(result) == 2, "Near-miss titles must NOT be merged"


# ---------------------------------------------------------------------------
# 4. GitHub repo-name match across blog + HF sources merges
# ---------------------------------------------------------------------------

def test_github_repo_name_match_merges():
    """Items sharing the same GitHub owner/repo path should merge."""
    item_blog = make_item(
        title="facebookresearch Releases TRIBE v2",
        source="meta_ai_blog",
        source_url="https://ai.meta.com/blog/tribe-v2/",
        github_url="https://github.com/facebookresearch/tribev2",
    )
    item_hf = make_item(
        title="TRIBE v2 on HuggingFace",
        source="huggingface_models",
        source_url="https://huggingface.co/facebook/tribev2",
        github_url="https://github.com/facebookresearch/tribev2",
    )

    result = deduplicate([item_blog, item_hf])

    assert len(result) == 1, "Shared GitHub repo must trigger a merge"
    merged = result[0]
    assert "https://github.com/facebookresearch/tribev2" in merged.get_all_urls()


# ---------------------------------------------------------------------------
# 5. Three-way merge: blog + arXiv + HF model into one item with 3 source URLs
# ---------------------------------------------------------------------------

def test_three_way_merge(tribe_blog_item, tribe_hf_item, tribe_arxiv_item):
    """Three items representing the same release should collapse into one."""
    result = deduplicate([tribe_blog_item, tribe_hf_item, tribe_arxiv_item])

    assert len(result) == 1, "All three TRIBE v2 entries must merge into one item"
    merged = result[0]
    # All three unique source URLs must be present
    all_urls = merged.get_all_urls()
    assert tribe_blog_item.source_url in all_urls
    assert tribe_hf_item.source_url in all_urls
    assert tribe_arxiv_item.source_url in all_urls


# ---------------------------------------------------------------------------
# 6. source_count incremented correctly after merge
# ---------------------------------------------------------------------------

def test_source_count_after_merge():
    """source_count must equal the number of unique sources merged."""
    items = [
        make_item(
            title="Cool New Model",
            source=f"source_{i}",
            source_url=f"https://example{i}.com/post",
            github_url="https://github.com/someorg/coolmodel",
        )
        for i in range(3)
    ]

    result = deduplicate(items)

    assert len(result) == 1
    assert result[0].source_count == 3
    assert set(result[0].all_sources) == {"source_0", "source_1", "source_2"}


# ---------------------------------------------------------------------------
# 7. Items with no overlap stay separate
# ---------------------------------------------------------------------------

def test_no_overlap_stays_separate():
    """Completely unrelated items must not be merged."""
    item_a = make_item(
        title="New Robotics Framework for Grasping Objects",
        source="arxiv",
        source_url="https://arxiv.org/abs/0001.11111",
        github_url="https://github.com/roboticslab/graspnet",
    )
    item_b = make_item(
        title="AudioSep Real-Time Sound Source Separation",
        source="huggingface_models",
        source_url="https://huggingface.co/audio/audiosep",
        github_url="https://github.com/audio-lab/audiosep",
    )
    item_c = make_item(
        title="Browser WebGPU Compute Shader Benchmarks",
        source="chrome_platform",
        source_url="https://chromestatus.com/feature/12345",
    )

    result = deduplicate([item_a, item_b, item_c])

    assert len(result) == 3, "Three unrelated items must all survive dedup"


# ---------------------------------------------------------------------------
# Edge case: empty input
# ---------------------------------------------------------------------------

def test_empty_input_returns_empty():
    assert deduplicate([]) == []


# ---------------------------------------------------------------------------
# Edge case: single item returns unchanged
# ---------------------------------------------------------------------------

def test_single_item_unchanged():
    item = make_item(title="Only Item", source_url="https://example.com/only")
    result = deduplicate([item])
    assert len(result) == 1
    assert result[0].source_url == item.source_url
