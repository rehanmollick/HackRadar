"""HuggingFace Daily Papers scraper — curated high-signal paper list."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

HF_PAPERS_URL = "https://huggingface.co/papers"

# Must match the label in config.HIGH_TRUST_SOURCES exactly. Changing
# this string without also updating HIGH_TRUST_SOURCES silently breaks
# the Pass 1 bypass for HF curated papers.
_SOURCE = "HuggingFace Papers"


@register_source("huggingface_papers")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    try:
        headers = {"User-Agent": "HackRadar/1.0 (hackathon tech scout)"}
        resp = requests.get(HF_PAPERS_URL, timeout=config.REQUEST_TIMEOUT, headers=headers)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # HF papers page: each paper is in an article element
        articles = soup.find_all("article")

        for article in articles:
            try:
                # Title link
                title_tag = article.find("h3") or article.find("h2")
                if not title_tag:
                    continue

                link_tag = title_tag.find("a") or article.find("a", href=True)
                if not link_tag:
                    continue

                title = title_tag.get_text(strip=True)
                href = link_tag.get("href", "")
                if not href:
                    continue

                if href.startswith("/"):
                    source_url = f"https://huggingface.co{href}"
                else:
                    source_url = href

                # Extract arxiv link if present
                paper_url = None
                arxiv_link = article.find("a", href=lambda h: h and "arxiv.org" in h)
                if arxiv_link:
                    paper_url = arxiv_link["href"]

                # Description: grab the abstract/summary text
                desc_tag = article.find("p")
                description = desc_tag.get_text(strip=True)[:800] if desc_tag else ""

                # HF papers page doesn't reliably expose dates per card in HTML,
                # so we use now (papers appear day-of). For the lookback we check
                # if the paper appeared today or yesterday by page structure.
                # As a pragmatic fallback: treat all visible papers as "recent"
                # (the page itself only shows last 1-2 days of papers).
                date = datetime.now(timezone.utc)

                item = Item(
                    title=title,
                    description=description,
                    date=date,
                    source=_SOURCE,
                    source_url=source_url,
                    paper_url=paper_url,
                    category="ai_research",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"hf_papers item error: {e}")

    except Exception as e:
        errors.append(f"huggingface_papers scrape failed: {e}")
        logger.exception("huggingface_papers scrape failed")

    logger.info("huggingface_papers: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)
