"""arXiv new paper scraper — searches recent submissions across AI/ML categories."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import arxiv

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)


@register_source("arxiv")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    # Build query: search across all categories
    category_query = " OR ".join(f"cat:{cat}" for cat in config.ARXIV_CATEGORIES)

    try:
        client = arxiv.Client(
            page_size=200,
            delay_seconds=3,
            num_retries=3,
        )

        search = arxiv.Search(
            query=category_query,
            max_results=300,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )

        for result in client.results(search):
            try:
                # arxiv published dates are already timezone-aware
                pub_date = result.published
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)

                if pub_date < cutoff:
                    # Results are sorted descending; once we go past cutoff we can break
                    break

                # Pre-filter: abstract must contain at least one keyword
                abstract_lower = (result.summary or "").lower()
                title_lower = result.title.lower()
                combined = abstract_lower + " " + title_lower

                if not any(kw in combined for kw in config.ARXIV_KEYWORDS):
                    continue

                # Build github_url if mentioned in abstract
                github_url = None
                if "github.com" in abstract_lower:
                    # Try to extract a github URL from the abstract
                    import re
                    match = re.search(r"https?://github\.com/[\w\-]+/[\w\-\.]+", result.summary)
                    if match:
                        github_url = match.group(0).rstrip(".")

                item = Item(
                    title=result.title,
                    description=(result.summary or "")[:1000],
                    date=pub_date,
                    source="arxiv",
                    source_url=result.entry_id,
                    paper_url=result.pdf_url,
                    github_url=github_url,
                    category="ai_research",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"arxiv item error: {e}")

    except Exception as e:
        errors.append(f"arxiv scrape failed: {e}")
        logger.exception("arxiv scrape failed")

    logger.info("arxiv: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)
