"""MDN Web Docs — new and recently updated Web API documentation."""
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

# MDN blog RSS for new/updated docs announcements
MDN_BLOG_RSS = "https://developer.mozilla.org/en-US/blog/rss.xml"
# MDN also has a GitHub repo where new API docs are committed; we use the blog
# as the primary signal source since the repo is too noisy.
MDN_BLOG_URL = "https://developer.mozilla.org/en-US/blog/"


@register_source("mdn_new")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # Primary: RSS feed
    try:
        resp = requests.get(
            MDN_BLOG_RSS,
            timeout=config.REQUEST_TIMEOUT,
            headers={"User-Agent": "HackRadar/1.0"},
        )
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

        if feed.bozo and not feed.entries:
            errors.append(f"mdn_new: bad RSS feed: {feed.bozo_exception}")
        else:
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
                    if not link.startswith("http"):
                        link = f"https://developer.mozilla.org{link}"

                    summary_raw = entry.get("summary", "") or ""
                    description = _strip_html(summary_raw)[:600]

                    item = Item(
                        title=f"MDN: {title}",
                        description=description,
                        date=pub_dt,
                        source="mdn_new",
                        source_url=link,
                        category="browser",
                    )
                    items.append(item)

                except Exception as e:
                    errors.append(f"mdn_new RSS entry error: {e}")

    except Exception as e:
        errors.append(f"mdn_new RSS failed: {e}")
        logger.exception("mdn_new RSS failed")

    # Fallback/supplement: scrape MDN blog HTML for browser-compat entries
    if not items:
        try:
            resp = requests.get(
                MDN_BLOG_URL,
                timeout=config.REQUEST_TIMEOUT,
                headers={"User-Agent": "HackRadar/1.0"},
            )
            resp.raise_for_status()

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            articles = soup.find_all("article") or soup.find_all("li", class_=lambda c: c and "blog" in c)
            for article in articles:
                try:
                    title_tag = article.find(["h2", "h3", "h1"])
                    if not title_tag:
                        continue

                    link_tag = title_tag.find("a") or article.find("a", href=True)
                    if not link_tag:
                        continue

                    title = title_tag.get_text(strip=True)
                    href = link_tag.get("href", "")
                    source_url = href if href.startswith("http") else f"https://developer.mozilla.org{href}"

                    desc_tag = article.find("p")
                    description = desc_tag.get_text(strip=True)[:600] if desc_tag else ""

                    item = Item(
                        title=f"MDN: {title}",
                        description=description,
                        date=datetime.now(timezone.utc),
                        source="mdn_new",
                        source_url=source_url,
                        category="browser",
                    )
                    items.append(item)

                except Exception as e:
                    errors.append(f"mdn_new HTML item error: {e}")

        except Exception as e:
            errors.append(f"mdn_new HTML fallback failed: {e}")

    logger.info("mdn_new: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


def _strip_html(html: str) -> str:
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
