# Method: RSS with custom HTML fallback
# Feed: https://ai.meta.com/blog/rss/
# Fallback HTML: https://ai.meta.com/blog/
#
# Meta FAIR publishes model releases (e.g. TRIBE v2) as blog posts here
# before any aggregator picks them up. This is the highest-priority source.
#
# Meta's RSS feed is often malformed XML (bozo = True). When that happens we
# fall back to scraping the HTML listing, which IS present in the initial
# server response even though the page is a React SPA.
#
# Observed HTML structure (as of 2026):
#   <div class="_amd1"><a href="/blog/...">Title</a></div>
#   <div class="_amun">March 26, 2026</div>
# These obfuscated class names are stable across page loads.

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source
from hackradar.sources.base_blog import _parse_date, _USER_AGENT, _HEADERS

log = logging.getLogger(__name__)

_RSS_URL = "https://ai.meta.com/blog/rss/"
_HTML_URL = "https://ai.meta.com/blog/"
_SOURCE = "Meta AI Blog"


def _scrape_meta_html(lookback_hours: int = config.LOOKBACK_HOURS) -> ScrapeResult:
    """
    Scrape Meta AI blog listing HTML.

    Meta's page is a React SPA but all post cards are in the initial HTML.
    We extract blog links directly from <a> tags that contain /blog/<slug>/
    paths, then look for the nearest date element (_amun class or text node).
    """
    items: list[Item] = []
    errors: list[str] = []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)

    try:
        resp = requests.get(_HTML_URL, headers=_HEADERS, timeout=config.REQUEST_TIMEOUT)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Strategy 1: find title divs (_amd1) — each wraps the post link
        title_divs = soup.find_all("div", class_="_amd1")

        if not title_divs:
            # Strategy 2: fallback — any <a> pointing to a /blog/<slug> path
            # with meaningful text (title length > 15 chars)
            all_anchors = soup.find_all("a", href=True)
            title_divs = [
                a.parent
                for a in all_anchors
                if "/blog/" in a["href"]
                and len(a.get_text(strip=True)) > 15
                and a.parent
            ]

        for div in title_divs:
            try:
                anchor = div.find("a", href=True)
                if anchor is None:
                    continue

                title = anchor.get_text(" ", strip=True)
                href = anchor["href"]
                if not title or not href:
                    continue
                if not href.startswith("http"):
                    href = "https://ai.meta.com" + href

                # Date: _amun sibling div or nearest text matching a date
                dt = None
                # Walk up a few levels to find the card container, then look
                # for _amun (the date div) as a sibling or cousin.
                container = div
                for _ in range(5):
                    date_el = container.find("div", class_="_amun")
                    if date_el:
                        dt = _parse_date(date_el.get_text(strip=True))
                        break
                    if container.parent:
                        container = container.parent
                    else:
                        break

                # If no date found, include item (don't silently drop)
                if dt is not None and dt < cutoff:
                    continue

                items.append(
                    Item(
                        title=title,
                        description="",
                        date=dt or datetime.now(tz=timezone.utc),
                        source=_SOURCE,
                        source_url=href,
                        category="ai_research",
                    )
                )
            except Exception as exc:
                msg = f"[{_SOURCE}] Error parsing card: {exc}"
                log.warning(msg)
                errors.append(msg)

    except requests.HTTPError as exc:
        msg = f"[{_SOURCE}] HTTP {exc.response.status_code} fetching {_HTML_URL}"
        log.error(msg)
        errors.append(msg)
    except Exception as exc:
        msg = f"[{_SOURCE}] Failed to scrape HTML {_HTML_URL}: {exc}"
        log.error(msg)
        errors.append(msg)

    log.info("[%s] HTML: %d items, %d errors", _SOURCE, len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


@register_source("meta_ai_blog")
def scrape(lookback_hours: int = 48):
    """Try RSS first; fall back to custom HTML scraper if RSS is broken."""
    import feedparser
    from hackradar.sources.base_blog import scrape_rss

    result = scrape_rss(
        url=_RSS_URL,
        source_name=_SOURCE,
        lookback_hours=lookback_hours,
        fallback_html_fn=lambda: _scrape_meta_html(lookback_hours),
    )

    # If RSS returned items, great. If it returned nothing (common — Meta's
    # RSS is often malformed), the fallback already ran inside scrape_rss.
    return result
