"""
Base blog scraper utilities.

Provides two functions used by all blog source modules:
  - scrape_rss:  for sources that publish a proper RSS/Atom feed
  - scrape_html: for sources that must be scraped with BeautifulSoup

Both return a ScrapeResult and never raise — all errors are captured
in ScrapeResult.errors so a single bad source cannot kill the pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
from bs4 import BeautifulSoup

from hackradar import config
from hackradar.models import Item, ScrapeResult

log = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; HackRadar/1.0; "
    "+https://github.com/rehanmollick/HackRadar)"
)

_HEADERS = {"User-Agent": _USER_AGENT}


# ---------------------------------------------------------------------------
# Date parsing helpers
# ---------------------------------------------------------------------------

def _parse_date(raw: Any) -> datetime | None:
    """Try to parse a date from a variety of input types.

    Accepts:
    - datetime objects
    - time.struct_time (from feedparser)
    - strings (ISO 8601, RFC 2822, or anything dateutil can handle)
    Returns a timezone-aware datetime in UTC, or None on failure.
    """
    if raw is None:
        return None

    # Already a datetime
    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc)
        return raw.astimezone(timezone.utc)

    # feedparser gives time.struct_time
    import time as _time
    if isinstance(raw, _time.struct_time):
        try:
            ts = _time.mktime(raw)
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None

    # String — try dateutil first, then stdlib
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return None
        try:
            from dateutil import parser as du_parser
            dt = du_parser.parse(raw, fuzzy=True)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
        # Fallback: common ISO format
        for fmt in (
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(raw, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                continue

    return None


def _within_window(dt: datetime | None, lookback_hours: int) -> bool:
    """Return True if *dt* is within the lookback window from now."""
    if dt is None:
        # No date info — include it so we don't silently drop real items
        return True
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback_hours)
    return dt >= cutoff


def _get(url: str) -> requests.Response:
    """HTTP GET with standard headers and timeout."""
    return requests.get(url, headers=_HEADERS, timeout=config.REQUEST_TIMEOUT)


# ---------------------------------------------------------------------------
# RSS scraper
# ---------------------------------------------------------------------------

def scrape_rss(
    url: str,
    source_name: str,
    category: str = "ai_research",
    lookback_hours: int = config.LOOKBACK_HOURS,
    *,
    fallback_html_fn=None,
) -> ScrapeResult:
    """Parse an RSS/Atom feed and return Items within the lookback window.

    Parameters
    ----------
    url:
        The RSS feed URL.
    source_name:
        Human-readable source label stored in Item.source.
    category:
        Item category (default 'ai_research').
    lookback_hours:
        How far back to look. Items older than this are discarded.
    fallback_html_fn:
        Optional zero-argument callable that returns a ScrapeResult.
        Called if feedparser returns zero items (feed may be dead).
    """
    import feedparser  # imported here so the rest of the module works without it

    items: list[Item] = []
    errors: list[str] = []

    try:
        # feedparser handles the HTTP request itself, but we want our User-Agent
        feed = feedparser.parse(url, request_headers={"User-Agent": _USER_AGENT})

        if feed.bozo and not feed.entries:
            msg = f"[{source_name}] RSS feed error: {feed.bozo_exception}"
            log.warning(msg)
            errors.append(msg)

        if not feed.entries and fallback_html_fn is not None:
            log.info("[%s] RSS returned 0 entries — trying HTML fallback", source_name)
            return fallback_html_fn()

        for entry in feed.entries:
            try:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                if not title or not link:
                    continue

                # Date: prefer published_parsed, then updated_parsed
                raw_date = (
                    entry.get("published_parsed")
                    or entry.get("updated_parsed")
                    or entry.get("published")
                    or entry.get("updated")
                )
                dt = _parse_date(raw_date)

                if not _within_window(dt, lookback_hours):
                    continue

                # Description: summary or content
                description = ""
                if entry.get("summary"):
                    description = BeautifulSoup(
                        entry["summary"], "html.parser"
                    ).get_text(" ", strip=True)
                elif entry.get("content"):
                    description = BeautifulSoup(
                        entry["content"][0].get("value", ""), "html.parser"
                    ).get_text(" ", strip=True)

                # Truncate very long descriptions
                if len(description) > 1000:
                    description = description[:1000].rsplit(" ", 1)[0] + "…"

                items.append(
                    Item(
                        title=title,
                        description=description,
                        date=dt or datetime.now(tz=timezone.utc),
                        source=source_name,
                        source_url=link,
                        category=category,
                    )
                )
            except Exception as exc:
                msg = f"[{source_name}] Error parsing RSS entry: {exc}"
                log.warning(msg)
                errors.append(msg)

    except Exception as exc:
        msg = f"[{source_name}] Failed to fetch/parse RSS feed {url}: {exc}"
        log.error(msg)
        errors.append(msg)

        if fallback_html_fn is not None:
            log.info("[%s] Attempting HTML fallback after RSS exception", source_name)
            try:
                return fallback_html_fn()
            except Exception as fb_exc:
                errors.append(f"[{source_name}] Fallback also failed: {fb_exc}")

    log.info("[%s] RSS: %d items scraped, %d errors", source_name, len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


# ---------------------------------------------------------------------------
# HTML scraper
# ---------------------------------------------------------------------------

def scrape_html(
    url: str,
    source_name: str,
    category: str = "ai_research",
    selectors: dict[str, str] | None = None,
    lookback_hours: int = config.LOOKBACK_HOURS,
) -> ScrapeResult:
    """Scrape a blog's HTML listing page and return Items.

    Parameters
    ----------
    url:
        The blog index/listing URL.
    source_name:
        Human-readable source label.
    category:
        Item category.
    selectors:
        Dict with CSS selectors. Expected keys:
          article_selector   — wraps each post card / list item
          title_selector     — title text (within article)
          link_selector      — <a> tag (or same as title if title is a link)
          date_selector      — element containing publication date text
          description_selector — excerpt or summary text (optional)
        Any missing key falls back to reasonable defaults.
    lookback_hours:
        Lookback window.
    """
    sel = selectors or {}
    article_sel = sel.get("article_selector", "article")
    title_sel = sel.get("title_selector", "h2, h3, h1")
    link_sel = sel.get("link_selector", "a")
    date_sel = sel.get("date_selector", "time, [datetime]")
    desc_sel = sel.get("description_selector", "p")

    items: list[Item] = []
    errors: list[str] = []

    try:
        resp = _get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        articles = soup.select(article_sel)
        if not articles:
            # Gentle fallback: try common wrappers
            for fallback in ("article", ".post", ".blog-post", "li", ".card"):
                articles = soup.select(fallback)
                if articles:
                    break

        for article in articles:
            try:
                # --- Title ---
                title_el = article.select_one(title_sel)
                if title_el is None:
                    continue
                title = title_el.get_text(" ", strip=True)
                if not title:
                    continue

                # --- Link ---
                # Prefer an explicit link_selector, then first <a> in article
                link_el = article.select_one(link_sel) or article.select_one("a")
                if link_el is None:
                    continue
                href = link_el.get("href", "")
                if not href:
                    continue
                # Resolve relative URLs
                if href.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    href = f"{parsed.scheme}://{parsed.netloc}{href}"
                elif not href.startswith("http"):
                    href = url.rstrip("/") + "/" + href

                # --- Date ---
                date_el = article.select_one(date_sel)
                dt = None
                if date_el:
                    # <time datetime="..."> is most reliable
                    raw = date_el.get("datetime") or date_el.get_text(" ", strip=True)
                    dt = _parse_date(raw)

                if not _within_window(dt, lookback_hours):
                    continue

                # --- Description ---
                description = ""
                desc_el = article.select_one(desc_sel)
                if desc_el:
                    description = desc_el.get_text(" ", strip=True)
                if len(description) > 1000:
                    description = description[:1000].rsplit(" ", 1)[0] + "…"

                items.append(
                    Item(
                        title=title,
                        description=description,
                        date=dt or datetime.now(tz=timezone.utc),
                        source=source_name,
                        source_url=href,
                        category=category,
                    )
                )
            except Exception as exc:
                msg = f"[{source_name}] Error parsing article element: {exc}"
                log.warning(msg)
                errors.append(msg)

    except requests.HTTPError as exc:
        msg = f"[{source_name}] HTTP {exc.response.status_code} fetching {url}"
        log.error(msg)
        errors.append(msg)
    except Exception as exc:
        msg = f"[{source_name}] Failed to scrape {url}: {exc}"
        log.error(msg)
        errors.append(msg)

    log.info("[%s] HTML: %d items scraped, %d errors", source_name, len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)
