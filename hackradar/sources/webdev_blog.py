"""web.dev blog RSS scraper — new web capabilities and browser feature announcements."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta

import feedparser
import requests

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

FEED_URLS = [
    # Canonical web.dev blog feed (web.dev/feed.xml 301s here).
    "https://web.dev/static/blog/feed.xml",
    # Chrome Developers blog. The old /feeds/blog.xml path 404s.
    "https://developer.chrome.com/blog/feed.xml",
]


@register_source("webdev_blog")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    for feed_url in FEED_URLS:
        try:
            # feedparser handles fetching internally; set timeout via request_headers
            resp = requests.get(
                feed_url,
                timeout=config.REQUEST_TIMEOUT,
                headers={"User-Agent": "HackRadar/1.0"},
            )
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            if feed.bozo and not feed.entries:
                errors.append(f"webdev_blog: bad feed at {feed_url}: {feed.bozo_exception}")
                continue

            for entry in feed.entries:
                try:
                    published = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published:
                        pub_dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
                    else:
                        pub_dt = datetime.now(timezone.utc)

                    if pub_dt < cutoff:
                        continue

                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()

                    # Summary: strip HTML tags
                    summary_raw = entry.get("summary", "") or entry.get("content", [{}])[0].get("value", "")
                    description = _strip_html(summary_raw)[:600]

                    item = Item(
                        title=title,
                        description=description,
                        date=pub_dt,
                        source="webdev_blog",
                        source_url=link,
                        category="browser",
                    )
                    items.append(item)

                except Exception as e:
                    errors.append(f"webdev_blog entry error ({feed_url}): {e}")

        except Exception as e:
            errors.append(f"webdev_blog failed for {feed_url}: {e}")
            logger.exception("webdev_blog failed for %s", feed_url)

    logger.info("webdev_blog: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


def _strip_html(html: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
