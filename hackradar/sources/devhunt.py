"""DevHunt scraper — developer tool launches."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

DEVHUNT_URL = "https://devhunt.org/"
DEVHUNT_API_URL = "https://devhunt.org/api/tools"  # May exist; try it


@register_source("devhunt")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HackRadar/1.0)",
        "Accept": "text/html,application/json",
    }

    # Try JSON API first
    api_success = False
    try:
        resp = requests.get(
            DEVHUNT_API_URL,
            timeout=config.REQUEST_TIMEOUT,
            headers={**headers, "Accept": "application/json"},
        )
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
            data = resp.json()
            tools = data if isinstance(data, list) else data.get("tools", data.get("results", []))

            for tool in tools:
                try:
                    name = tool.get("name", "").strip()
                    if not name:
                        continue

                    desc = tool.get("description", "") or tool.get("tagline", "")
                    slug = tool.get("slug", "") or tool.get("id", "")
                    tool_url = tool.get("url", "") or f"{DEVHUNT_URL}tool/{slug}"
                    demo_url = tool.get("website", "") or tool.get("demo_url", "") or None

                    # Date parsing
                    date_str = tool.get("created_at", "") or tool.get("launchedAt", "") or ""
                    date = _try_parse(date_str) or datetime.now(timezone.utc)

                    if date < cutoff:
                        continue

                    item = Item(
                        title=name,
                        description=desc[:600],
                        date=date,
                        source="devhunt",
                        source_url=tool_url,
                        demo_url=demo_url if demo_url and "github.com" not in (demo_url or "") else None,
                        github_url=demo_url if demo_url and "github.com" in (demo_url or "") else None,
                        category="tool",
                    )
                    items.append(item)
                    api_success = True

                except Exception as e:
                    errors.append(f"devhunt API item error: {e}")

    except Exception as e:
        errors.append(f"devhunt API attempt failed: {e}")

    if api_success:
        logger.info("devhunt (API): %d items, %d errors", len(items), len(errors))
        return ScrapeResult(items=items, errors=errors)

    # Fallback: scrape HTML
    try:
        resp = requests.get(DEVHUNT_URL, timeout=config.REQUEST_TIMEOUT, headers=headers)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # DevHunt lists tools as cards/articles
        cards = (
            soup.select("article")
            or soup.select(".tool-card, .product-card, [class*='tool']")
            or soup.find_all("li")
        )

        for card in cards:
            try:
                title_tag = card.find(["h2", "h3", "h1"])
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                link_tag = card.find("a", href=True)
                if not link_tag:
                    continue

                href = link_tag.get("href", "")
                source_url = href if href.startswith("http") else f"https://devhunt.org{href}"

                desc_tag = card.find("p")
                description = desc_tag.get_text(strip=True)[:500] if desc_tag else ""

                # External link (the actual tool website)
                external_link = None
                ext_tag = card.find("a", href=lambda h: h and h.startswith("http") and "devhunt.org" not in h)
                if ext_tag:
                    external_link = ext_tag.get("href", "")

                item = Item(
                    title=title,
                    description=description,
                    date=datetime.now(timezone.utc),
                    source="devhunt",
                    source_url=source_url,
                    demo_url=external_link if external_link and "github.com" not in (external_link or "") else None,
                    github_url=external_link if external_link and "github.com" in (external_link or "") else None,
                    category="tool",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"devhunt HTML item error: {e}")

    except Exception as e:
        errors.append(f"devhunt HTML scrape failed: {e}")
        logger.exception("devhunt scrape failed")

    logger.info("devhunt: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


def _try_parse(date_str: str) -> datetime | None:
    if not date_str:
        return None
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str[:26], fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
