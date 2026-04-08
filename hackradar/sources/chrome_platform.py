"""Chrome Platform Status scraper — new and shipping web platform features."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

import requests

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

# Chromestatus has a JSON API for features
CHROMESTATUS_API = "https://chromestatus.com/api/v0/features"
CHROMESTATUS_FEATURE_URL = "https://chromestatus.com/feature/{}"


@register_source("chrome_platform")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    headers = {
        "User-Agent": "HackRadar/1.0",
        "Accept": "application/json",
    }

    try:
        # Fetch features with "in development" or "shipping" status
        # The API supports ?q= for query and returns a JSON list
        params = {
            "q": "",  # all features
            "num": 100,
            "start": 0,
        }

        resp = requests.get(
            CHROMESTATUS_API,
            params=params,
            timeout=config.REQUEST_TIMEOUT,
            headers=headers,
        )
        resp.raise_for_status()
        # Chromestatus prefixes responses with the XSSI anti-CSRF token `)]}'`
        # which trips up resp.json(). Strip it before parsing.
        text = resp.text.lstrip()
        if text.startswith(")]}'"):
            text = text[4:].lstrip()
        data = json.loads(text)

        features = data if isinstance(data, list) else data.get("features", [])

        for feature in features:
            try:
                # Check if it's new enough using created or updated time
                # Chromestatus uses epoch seconds or ISO strings
                updated_str = (
                    feature.get("updated", {}).get("when", "")
                    if isinstance(feature.get("updated"), dict)
                    else feature.get("updated", "")
                )
                created_str = (
                    feature.get("created", {}).get("when", "")
                    if isinstance(feature.get("created"), dict)
                    else feature.get("created", "")
                )

                feature_date = _try_parse(updated_str) or _try_parse(created_str)
                if feature_date is None:
                    # Fall back to shipping milestone check
                    feature_date = datetime.now(timezone.utc)

                if feature_date < cutoff:
                    continue

                feature_id = feature.get("id", "")
                name = feature.get("name", "").strip()
                if not name:
                    continue

                summary = feature.get("summary", "") or feature.get("motivation", "") or ""
                summary = summary[:600]

                # Only include features that have some milestone shipping info
                # or are "in development"
                stage = (feature.get("feature_type", "") or feature.get("category", "")).lower()

                source_url = CHROMESTATUS_FEATURE_URL.format(feature_id) if feature_id else "https://chromestatus.com/features"

                # Look for a spec link
                spec_link = feature.get("spec_link") or feature.get("explainer_links", [None])[0] if feature.get("explainer_links") else None

                item = Item(
                    title=f"Chrome: {name}",
                    description=summary,
                    date=feature_date,
                    source="chrome_platform",
                    source_url=source_url,
                    demo_url=spec_link if spec_link and "github.com" not in (spec_link or "") else None,
                    github_url=spec_link if spec_link and "github.com" in (spec_link or "") else None,
                    category="browser",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"chrome_platform item error: {e}")

    except Exception as e:
        errors.append(f"chrome_platform scrape failed: {e}")
        logger.exception("chrome_platform scrape failed")
        # Fallback: try the RSS feed if the API fails
        items, errors = _scrape_rss_fallback(cutoff, items, errors)

    logger.info("chrome_platform: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


def _try_parse(date_str: str) -> datetime | None:
    if not date_str:
        return None
    formats = [
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str[:26], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    # Try numeric timestamp
    try:
        return datetime.fromtimestamp(float(date_str), tz=timezone.utc)
    except (ValueError, OSError):
        return None


def _scrape_rss_fallback(
    cutoff: datetime, items: list[Item], errors: list[str]
) -> tuple[list[Item], list[str]]:
    """Fallback: scrape chromestatus new features page."""
    try:
        import feedparser
        feed = feedparser.parse("https://chromestatus.com/features.xml")
        for entry in feed.entries:
            try:
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    import time
                    pub_dt = datetime.fromtimestamp(time.mktime(published), tz=timezone.utc)
                else:
                    pub_dt = datetime.now(timezone.utc)

                if pub_dt < cutoff:
                    continue

                item = Item(
                    title=f"Chrome: {entry.get('title', '')}",
                    description=entry.get("summary", "")[:600],
                    date=pub_dt,
                    source="chrome_platform",
                    source_url=entry.get("link", "https://chromestatus.com"),
                    category="browser",
                )
                items.append(item)
            except Exception as e:
                errors.append(f"chrome_platform RSS item error: {e}")
    except Exception as e:
        errors.append(f"chrome_platform RSS fallback failed: {e}")

    return items, errors
