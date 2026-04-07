"""Kaggle new datasets scraper — interesting new datasets for hackathon projects."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta

import requests

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

KAGGLE_API_BASE = "https://www.kaggle.com/api/v1"
KAGGLE_USERNAME = os.environ.get("KAGGLE_USERNAME", "")
KAGGLE_KEY = os.environ.get("KAGGLE_KEY", "")


@register_source("kaggle_datasets")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    if KAGGLE_USERNAME and KAGGLE_KEY:
        items, errors = _scrape_api(cutoff, errors)
    else:
        errors.append("KAGGLE_USERNAME/KAGGLE_KEY not set — falling back to web scrape")
        items, errors = _scrape_web(cutoff, errors)

    logger.info("kaggle_datasets: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


def _scrape_api(cutoff: datetime, errors: list[str]) -> tuple[list[Item], list[str]]:
    items: list[Item] = []

    try:
        from kaggle.api.kaggle_api_extended import KaggleApiExtended
        api = KaggleApiExtended()
        api.authenticate()

        # Sort by newest, look through recent pages
        page = 1
        while True:
            datasets = api.dataset_list(
                sort_by="hottest",
                page=page,
                max_size=None,
                file_type="all",
                license_name="all",
                tag_ids="",
                search="",
                user="",
                mine=False,
            )

            if not datasets:
                break

            found_old = False
            for ds in datasets:
                try:
                    created_at = getattr(ds, "creationDate", None) or getattr(ds, "lastUpdated", None)
                    if created_at is None:
                        continue

                    if isinstance(created_at, str):
                        created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    elif created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)

                    if created_at < cutoff:
                        found_old = True
                        continue

                    ref = getattr(ds, "ref", "") or ""  # "owner/dataset-name"
                    title = getattr(ds, "title", "") or ref
                    description = getattr(ds, "subtitle", "") or getattr(ds, "description", "") or ""
                    url = f"https://www.kaggle.com/datasets/{ref}" if ref else "https://www.kaggle.com/datasets"

                    item = Item(
                        title=title,
                        description=description[:600],
                        date=created_at,
                        source="kaggle_datasets",
                        source_url=url,
                        category="dataset",
                    )
                    items.append(item)

                except Exception as e:
                    errors.append(f"kaggle_datasets API item error: {e}")

            if found_old or page >= 3:
                break
            page += 1

    except Exception as e:
        errors.append(f"kaggle_datasets API failed: {e}")
        logger.exception("kaggle_datasets API failed")
        items, errors = _scrape_web(cutoff, errors)

    return items, errors


def _scrape_web(cutoff: datetime, errors: list[str]) -> tuple[list[Item], list[str]]:
    """Fallback: use the unofficial Kaggle datasets JSON endpoint."""
    items: list[Item] = []

    try:
        headers = {"User-Agent": "HackRadar/1.0"}
        resp = requests.get(
            "https://www.kaggle.com/datasets",
            params={"sort": "hottest", "fileType": "all"},
            timeout=config.REQUEST_TIMEOUT,
            headers=headers,
        )
        resp.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        # Try to find dataset links
        links = soup.find_all("a", href=lambda h: h and "/datasets/" in h)

        seen = set()
        for link in links:
            try:
                href = link.get("href", "")
                if not href or href in seen:
                    continue
                # Skip non-dataset paths and category pages
                parts = href.strip("/").split("/")
                if len(parts) < 2:
                    continue

                seen.add(href)
                source_url = f"https://www.kaggle.com{href}" if href.startswith("/") else href

                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                item = Item(
                    title=title,
                    description="New Kaggle dataset",
                    date=datetime.now(timezone.utc),
                    source="kaggle_datasets",
                    source_url=source_url,
                    category="dataset",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"kaggle_datasets web item error: {e}")

    except Exception as e:
        errors.append(f"kaggle_datasets web scrape failed: {e}")

    return items, errors
