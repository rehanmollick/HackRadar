"""Papers With Code — latest papers with linked code repos."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

PWC_URL = "https://paperswithcode.com/latest"
PWC_API_URL = "https://paperswithcode.com/api/v1/papers/"


@register_source("papers_with_code")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # Try the API first (cleaner, structured data)
    try:
        headers = {"User-Agent": "HackRadar/1.0"}
        resp = requests.get(
            PWC_API_URL,
            params={"ordering": "-published", "items_per_page": 50},
            timeout=config.REQUEST_TIMEOUT,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        for paper in results:
            try:
                published_str = paper.get("published", "") or ""
                if not published_str:
                    continue

                # Format: "2024-03-15" or ISO with time
                pub_date = _parse_date(published_str)
                if pub_date is None:
                    continue

                if pub_date < cutoff:
                    break  # ordered by date descending

                title = paper.get("title", "").strip()
                abstract = (paper.get("abstract", "") or "")[:800]
                arxiv_id = paper.get("arxiv_id", "")
                paper_url = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else None
                pwc_url = paper.get("url_pdf") or paper.get("url_abs") or ""
                source_url = f"https://paperswithcode.com/paper/{paper.get('id', '')}"

                # Only include papers that have code
                if not paper.get("has_code", False) and not paper.get("github_url"):
                    continue

                github_url = paper.get("github_url") or None

                item = Item(
                    title=title,
                    description=abstract,
                    date=pub_date,
                    source="papers_with_code",
                    source_url=source_url,
                    paper_url=paper_url,
                    github_url=github_url,
                    category="ai_research",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"pwc item error: {e}")

        return ScrapeResult(items=items, errors=errors)

    except Exception as e:
        errors.append(f"pwc API failed, falling back to scrape: {e}")

    # Fallback: scrape the HTML
    try:
        headers = {"User-Agent": "HackRadar/1.0"}
        resp = requests.get(PWC_URL, timeout=config.REQUEST_TIMEOUT, headers=headers)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Paper cards on the page
        cards = soup.select(".paper-card, .infinite-item, article")
        for card in cards:
            try:
                title_tag = card.find(["h1", "h2", "h3", "h4"])
                if not title_tag:
                    continue

                link_tag = title_tag.find("a") or card.find("a", href=True)
                if not link_tag:
                    continue

                title = title_tag.get_text(strip=True)
                href = link_tag.get("href", "")
                if not href:
                    continue

                source_url = (
                    f"https://paperswithcode.com{href}"
                    if href.startswith("/")
                    else href
                )

                # GitHub link
                github_link = card.find("a", href=lambda h: h and "github.com" in h)
                github_url = github_link["href"] if github_link else None

                if not github_url:
                    continue  # only care about papers with code

                desc_tag = card.find("p")
                description = desc_tag.get_text(strip=True)[:800] if desc_tag else ""

                item = Item(
                    title=title,
                    description=description,
                    date=datetime.now(timezone.utc),
                    source="papers_with_code",
                    source_url=source_url,
                    github_url=github_url,
                    category="ai_research",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"pwc scrape item error: {e}")

    except Exception as e:
        errors.append(f"pwc HTML scrape failed: {e}")
        logger.exception("papers_with_code scrape failed")

    logger.info("papers_with_code: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


def _parse_date(date_str: str) -> datetime | None:
    """Parse a date string into a timezone-aware datetime."""
    import re
    from datetime import datetime

    date_str = date_str.strip()
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None
