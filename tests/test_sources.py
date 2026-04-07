"""tests/test_sources.py — Unit tests for hackradar/sources/base_blog.py.

Uses the `responses` library to mock HTTP calls made by requests.get,
and patches feedparser.parse directly since feedparser manages its own
HTTP internally.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import responses as responses_lib

from hackradar.models import Item, ScrapeResult
from hackradar.sources.base_blog import scrape_html, scrape_rss
from tests.conftest import make_item


# ---------------------------------------------------------------------------
# Shared mock content
# ---------------------------------------------------------------------------

VALID_RSS_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Meta AI Blog</title>
    <link>https://ai.meta.com/blog/</link>
    <description>Meta AI research blog</description>
    <item>
      <title>TRIBE v2: A Brain Predictive Foundation Model</title>
      <link>https://ai.meta.com/blog/tribe-v2-brain-predictive-foundation-model/</link>
      <pubDate>Wed, 26 Mar 2026 10:00:00 +0000</pubDate>
      <description>Meta FAIR releases TRIBE v2, an open-source foundation model that
        predicts brain activity from images and video stimuli.</description>
    </item>
    <item>
      <title>Segment Anything Model 3 Released</title>
      <link>https://ai.meta.com/blog/sam-3/</link>
      <pubDate>Thu, 27 Mar 2026 08:00:00 +0000</pubDate>
      <description>SAM 3 extends zero-shot segmentation to 3D point clouds.</description>
    </item>
  </channel>
</rss>
"""

MALFORMED_RSS_XML = """\
<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Broken Feed</title>
    <!-- unclosed tag below — bozo feed -->
    <item>
      <title>Some Post
      <link>https://example.com/post
    </item>
  </channel>
"""

VALID_HTML_PAGE = """\
<!DOCTYPE html>
<html>
<body>
  <article>
    <h2><a href="https://ai.meta.com/blog/tribe-v2/">TRIBE v2 Brain Model</a></h2>
    <time datetime="2026-03-26T10:00:00Z">March 26, 2026</time>
    <p>An open-source brain activity prediction foundation model from Meta FAIR.</p>
  </article>
  <article>
    <h2><a href="https://ai.meta.com/blog/sam-3/">SAM 3 Released</a></h2>
    <time datetime="2026-03-27T08:00:00Z">March 27, 2026</time>
    <p>SAM 3 extends segmentation to 3D point clouds and video.</p>
  </article>
</body>
</html>
"""

HTML_NO_ARTICLES = """\
<!DOCTYPE html>
<html>
<body>
  <div class="hero">Welcome to the blog</div>
  <footer>Contact us</footer>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# feedparser mock builder
# ---------------------------------------------------------------------------

def _make_fp_result(xml_string: str, bozo: bool = False, bozo_exception=None):
    """
    Build a minimal object that looks like a feedparser result.

    We parse the real XML so the entries are genuinely structured; we just
    swap in the bozo flag so we can simulate error conditions without
    crafting an entirely synthetic object graph.
    """
    import feedparser
    result = feedparser.parse(xml_string)
    result["bozo"] = bozo
    if bozo_exception is not None:
        result["bozo_exception"] = bozo_exception
    return result


# ---------------------------------------------------------------------------
# feedparser patch helper
# ---------------------------------------------------------------------------
# scrape_rss imports feedparser *inside* the function body with a local
# `import feedparser` statement, so patching `hackradar.sources.base_blog.feedparser`
# won't work.  We patch `feedparser.parse` at the top-level sys.modules entry
# instead, which is what the local import resolves to at runtime.

def _patch_feedparser_parse(return_value=None, side_effect=None):
    """Return a context manager that patches feedparser.parse in sys.modules."""
    import feedparser as _fp_mod
    kwargs = {}
    if side_effect is not None:
        kwargs["side_effect"] = side_effect
    else:
        kwargs["return_value"] = return_value
    return patch.object(_fp_mod, "parse", **kwargs)


# ---------------------------------------------------------------------------
# Test 1: RSS source — valid feed → list of Items
# ---------------------------------------------------------------------------

def test_scrape_rss_valid_feed():
    """A well-formed RSS feed should return Items with all core fields set."""
    fp_result = _make_fp_result(VALID_RSS_XML)

    with _patch_feedparser_parse(return_value=fp_result):
        result = scrape_rss(
            url="https://ai.meta.com/blog/rss.xml",
            source_name="meta_ai_blog",
            category="ai_research",
            lookback_hours=10_000,  # large window so both items pass
        )

    assert isinstance(result, ScrapeResult)
    assert len(result.errors) == 0, f"Unexpected errors: {result.errors}"
    assert len(result.items) == 2

    first = result.items[0]
    assert isinstance(first, Item)
    assert "TRIBE v2" in first.title
    assert first.source == "meta_ai_blog"
    assert first.source_url == "https://ai.meta.com/blog/tribe-v2-brain-predictive-foundation-model/"
    assert first.category == "ai_research"
    assert isinstance(first.date, datetime)
    assert first.description  # non-empty


# ---------------------------------------------------------------------------
# Test 2: RSS source — malformed feed → ScrapeResult with errors
# ---------------------------------------------------------------------------

def test_scrape_rss_malformed_feed():
    """A bozo feed with no parseable entries should surface an error."""
    bozo_exc = Exception("RSS parse error: malformed XML")
    # Simulate feedparser returning bozo=True with empty entries
    fp_result = MagicMock()
    fp_result.bozo = True
    fp_result.bozo_exception = bozo_exc
    fp_result.entries = []

    with _patch_feedparser_parse(return_value=fp_result):
        result = scrape_rss(
            url="https://broken.example.com/rss.xml",
            source_name="broken_source",
            lookback_hours=48,
        )

    assert isinstance(result, ScrapeResult)
    assert len(result.errors) >= 1, "Expected at least one error for a bozo feed"
    assert len(result.items) == 0


# ---------------------------------------------------------------------------
# Test 3: RSS source — connection timeout → ScrapeResult with errors
# ---------------------------------------------------------------------------

def test_scrape_rss_connection_timeout():
    """A connection-level exception must be caught and returned as an error."""
    with _patch_feedparser_parse(side_effect=ConnectionError("timed out")):
        result = scrape_rss(
            url="https://unreachable.example.com/rss.xml",
            source_name="timeout_source",
            lookback_hours=48,
        )

    assert isinstance(result, ScrapeResult)
    assert len(result.errors) >= 1
    assert len(result.items) == 0
    # The error message must mention the source name or URL
    combined = " ".join(result.errors)
    assert "timeout_source" in combined or "unreachable" in combined


# ---------------------------------------------------------------------------
# Test 4: HTML source — valid page → items parsed
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_scrape_html_valid_page():
    """A well-formed HTML page with <article> cards should yield Items."""
    responses_lib.add(
        responses_lib.GET,
        "https://ai.meta.com/blog/",
        body=VALID_HTML_PAGE,
        status=200,
        content_type="text/html; charset=utf-8",
    )

    result = scrape_html(
        url="https://ai.meta.com/blog/",
        source_name="meta_ai_blog",
        category="ai_research",
        selectors={
            "article_selector": "article",
            "title_selector": "h2",
            "link_selector": "a",
            "date_selector": "time",
            "description_selector": "p",
        },
        lookback_hours=10_000,
    )

    assert isinstance(result, ScrapeResult)
    assert len(result.items) == 2, f"Expected 2 items, got {len(result.items)}"

    titles = [item.title for item in result.items]
    assert any("TRIBE" in t for t in titles)
    assert any("SAM" in t for t in titles)

    for item in result.items:
        assert item.source == "meta_ai_blog"
        assert item.source_url.startswith("https://")
        assert isinstance(item.date, datetime)


# ---------------------------------------------------------------------------
# Test 5: HTML source — structure changed (no matching selectors) → empty + error
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_scrape_html_no_matching_selectors():
    """When the page contains no matching article elements, return empty items and log an error."""
    responses_lib.add(
        responses_lib.GET,
        "https://ai.meta.com/blog/",
        body=HTML_NO_ARTICLES,
        status=200,
        content_type="text/html; charset=utf-8",
    )

    # Use a very specific selector that won't match anything in the stub HTML
    result = scrape_html(
        url="https://ai.meta.com/blog/",
        source_name="meta_ai_blog",
        category="ai_research",
        selectors={
            "article_selector": ".nonexistent-class-xyz",
            "title_selector": "h2",
            "link_selector": "a",
            "date_selector": "time",
            "description_selector": "p",
        },
        lookback_hours=48,
    )

    assert isinstance(result, ScrapeResult)
    # The HTML fallback loop in scrape_html tries common selectors; if none
    # match a real article element we should end up with zero items.
    assert len(result.items) == 0, (
        f"Expected 0 items from a page with no matching structure, got {len(result.items)}"
    )


# ---------------------------------------------------------------------------
# Test 6: Items with all Optional fields None → doesn't crash dedup or enrichment
# ---------------------------------------------------------------------------

def test_item_all_optional_none_survives_dedup():
    """An Item where every Optional field is None must pass through dedup cleanly."""
    from hackradar.dedup import deduplicate

    sparse_item = Item(
        title="Sparse Item With No Optionals",
        description="No github, hf, demo, or paper URLs.",
        date=datetime(2026, 3, 26, tzinfo=timezone.utc),
        source="test_source",
        source_url="https://example.com/sparse",
        category="misc",
        # All optional fields left as None (default)
        github_url=None,
        huggingface_url=None,
        demo_url=None,
        paper_url=None,
    )

    # Should not raise
    result = deduplicate([sparse_item])
    assert len(result) == 1

    merged = result[0]
    assert merged.github_url is None
    assert merged.huggingface_url is None
    assert merged.demo_url is None
    assert merged.paper_url is None
    assert merged.stars is None
    assert merged.model_size is None


# ---------------------------------------------------------------------------
# Test 7 (bonus): HTTP 404 from HTML scraper produces error, not crash
# ---------------------------------------------------------------------------

@responses_lib.activate
def test_scrape_html_http_error():
    """A 4xx response must be caught and returned as an error, not raised."""
    responses_lib.add(
        responses_lib.GET,
        "https://ai.meta.com/blog/",
        status=404,
    )

    result = scrape_html(
        url="https://ai.meta.com/blog/",
        source_name="meta_ai_blog",
        category="ai_research",
        lookback_hours=48,
    )

    assert isinstance(result, ScrapeResult)
    assert len(result.errors) >= 1
    assert len(result.items) == 0
