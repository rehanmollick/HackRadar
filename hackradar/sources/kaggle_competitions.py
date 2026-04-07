"""Kaggle new competitions scraper — active competitions reveal interesting problem spaces."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta

import requests

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

KAGGLE_USERNAME = os.environ.get("KAGGLE_USERNAME", "")
KAGGLE_KEY = os.environ.get("KAGGLE_KEY", "")


@register_source("kaggle_competitions")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    if KAGGLE_USERNAME and KAGGLE_KEY:
        items, errors = _scrape_api(cutoff, errors)
    else:
        errors.append("KAGGLE_USERNAME/KAGGLE_KEY not set — falling back to web scrape")
        items, errors = _scrape_web(cutoff, errors)

    logger.info("kaggle_competitions: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


def _scrape_api(cutoff: datetime, errors: list[str]) -> tuple[list[Item], list[str]]:
    items: list[Item] = []

    try:
        from kaggle.api.kaggle_api_extended import KaggleApiExtended
        api = KaggleApiExtended()
        api.authenticate()

        competitions = api.competitions_list(sort_by="latestDeadline", category="all", search="")

        for comp in competitions:
            try:
                enable_team_ms = getattr(comp, "enabledDate", None) or getattr(comp, "enableTeamModelSubmissions", None)
                deadline = getattr(comp, "deadline", None)

                # Use enabling date if available
                created_at = getattr(comp, "enabledDate", None)
                if created_at is None:
                    created_at = datetime.now(timezone.utc)
                elif isinstance(created_at, str):
                    created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                elif created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)

                if created_at < cutoff:
                    continue

                title = getattr(comp, "title", "") or ""
                description = getattr(comp, "description", "") or getattr(comp, "subtitle", "") or ""
                ref = getattr(comp, "ref", "") or getattr(comp, "id", "")
                url = f"https://www.kaggle.com/competitions/{ref}" if ref else "https://www.kaggle.com/competitions"

                reward = getattr(comp, "reward", "") or ""
                if reward:
                    description = f"[Prize: {reward}] {description}"

                item = Item(
                    title=f"Kaggle Competition: {title}",
                    description=description[:600],
                    date=created_at,
                    source="kaggle_competitions",
                    source_url=url,
                    category="dataset",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"kaggle_competitions API item error: {e}")

    except Exception as e:
        errors.append(f"kaggle_competitions API failed: {e}")
        logger.exception("kaggle_competitions API failed")
        items, errors = _scrape_web(cutoff, errors)

    return items, errors


def _scrape_web(cutoff: datetime, errors: list[str]) -> tuple[list[Item], list[str]]:
    items: list[Item] = []

    try:
        headers = {"User-Agent": "HackRadar/1.0"}
        resp = requests.get(
            "https://www.kaggle.com/competitions",
            params={"sortBy": "latestDeadline", "category": "all", "reward": "all"},
            timeout=config.REQUEST_TIMEOUT,
            headers=headers,
        )
        resp.raise_for_status()

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        links = soup.find_all("a", href=lambda h: h and "/competitions/" in h and h.count("/") >= 2)
        seen = set()

        for link in links:
            try:
                href = link.get("href", "")
                if not href or href in seen:
                    continue
                # Filter to actual competition pages (not search/sort params)
                parts = href.strip("/").split("/")
                if len(parts) < 2 or parts[-1] in ("all", "entered", "hosting"):
                    continue

                seen.add(href)
                source_url = f"https://www.kaggle.com{href}" if href.startswith("/") else href

                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                item = Item(
                    title=f"Kaggle Competition: {title}",
                    description="New Kaggle competition",
                    date=datetime.now(timezone.utc),
                    source="kaggle_competitions",
                    source_url=source_url,
                    category="dataset",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"kaggle_competitions web item error: {e}")

    except Exception as e:
        errors.append(f"kaggle_competitions web scrape failed: {e}")

    return items, errors
