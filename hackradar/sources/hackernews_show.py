"""Hacker News Show HN scraper — new tools and projects shared by makers."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import requests

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

HN_SHOW_STORIES_URL = "https://hacker-news.firebaseio.com/v0/showstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"
HN_STORY_URL = "https://news.ycombinator.com/item?id={}"


@register_source("hackernews_show")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    cutoff_ts = int(cutoff.timestamp())

    headers = {"User-Agent": "HackRadar/1.0"}

    try:
        resp = requests.get(
            HN_SHOW_STORIES_URL,
            timeout=config.REQUEST_TIMEOUT,
            headers=headers,
        )
        resp.raise_for_status()
        story_ids: list[int] = resp.json()

    except Exception as e:
        errors.append(f"hackernews_show: failed to fetch story list: {e}")
        return ScrapeResult(items=[], errors=errors)

    # Fetch top N stories; HN API returns them sorted by rank (not date)
    # We fetch up to 100 to find ones within our time window
    fetch_ids = story_ids[:100]

    for story_id in fetch_ids:
        try:
            story_resp = requests.get(
                HN_ITEM_URL.format(story_id),
                timeout=config.REQUEST_TIMEOUT,
                headers=headers,
            )
            story_resp.raise_for_status()
            story = story_resp.json()

            if not story:
                continue

            # Time filter
            story_time = story.get("time", 0)
            if story_time < cutoff_ts:
                continue

            title = story.get("title", "").strip()
            if not title:
                continue

            url = story.get("url", "")
            score = story.get("score", 0)
            by = story.get("by", "")
            descendants = story.get("descendants", 0)  # comment count

            # Text is the post body (HTML); strip tags
            text_raw = story.get("text", "") or ""
            description = _strip_html(text_raw)[:500]
            if not description:
                description = f"Show HN by {by} — {score} points, {descendants} comments"

            source_url = HN_STORY_URL.format(story_id)

            # Determine if URL is GitHub
            github_url = url if url and "github.com" in url else None

            item = Item(
                title=title,
                description=description,
                date=datetime.fromtimestamp(story_time, tz=timezone.utc),
                source="hackernews_show",
                source_url=source_url,
                github_url=github_url,
                demo_url=url if url and "github.com" not in url else None,
                category="tool",
            )
            items.append(item)

        except Exception as e:
            errors.append(f"hackernews_show item error ({story_id}): {e}")

    logger.info("hackernews_show: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


def _strip_html(html: str) -> str:
    """Very simple HTML tag stripper."""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
