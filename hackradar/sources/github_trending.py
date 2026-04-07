"""GitHub Trending scraper — daily trending repos across multiple language filters."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

TRENDING_URLS = [
    ("https://github.com/trending", "all"),
    ("https://github.com/trending/python", "python"),
    ("https://github.com/trending/typescript", "typescript"),
]


@register_source("github_trending")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []
    seen_urls: set[str] = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HackRadar/1.0)",
        "Accept": "text/html",
    }

    for url, lang_label in TRENDING_URLS:
        try:
            resp = requests.get(url, timeout=config.REQUEST_TIMEOUT, headers=headers)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "html.parser")
            repo_cards = soup.select("article.Box-row")

            for card in repo_cards:
                try:
                    # Repo name link
                    h2 = card.find("h2")
                    if not h2:
                        continue

                    link_tag = h2.find("a")
                    if not link_tag:
                        continue

                    href = link_tag.get("href", "").strip()
                    if not href:
                        continue

                    github_url = f"https://github.com{href}"
                    if github_url in seen_urls:
                        continue
                    seen_urls.add(github_url)

                    # Title: "owner / repo"
                    title_text = link_tag.get_text(separator="/", strip=True)
                    # Clean up whitespace/newlines
                    title = re.sub(r"\s+", " ", title_text).strip().replace("/ ", "/").replace(" /", "/")

                    # Description
                    desc_tag = card.find("p")
                    description = desc_tag.get_text(strip=True) if desc_tag else ""

                    # Stars today
                    stars_today_tag = card.find("span", class_=lambda c: c and "d-inline-block" in c and "float-sm-right" in c)
                    stars_today_text = stars_today_tag.get_text(strip=True) if stars_today_tag else ""

                    # Total stars
                    star_link = card.find("a", href=lambda h: h and "/stargazers" in h)
                    stars = None
                    if star_link:
                        star_text = star_link.get_text(strip=True).replace(",", "")
                        try:
                            stars = int(star_text)
                        except ValueError:
                            pass

                    # Language
                    lang_tag = card.find("span", itemprop="programmingLanguage")
                    language = lang_tag.get_text(strip=True) if lang_tag else lang_label

                    full_desc = description
                    if stars_today_text:
                        full_desc = f"{description} [{stars_today_text} stars today]".strip()

                    item = Item(
                        title=title,
                        description=full_desc,
                        date=datetime.now(timezone.utc),
                        source="github_trending",
                        source_url=github_url,
                        github_url=github_url,
                        category="tool",
                        stars=stars,
                        language=language,
                    )
                    items.append(item)

                except Exception as e:
                    errors.append(f"github_trending item error ({lang_label}): {e}")

        except Exception as e:
            errors.append(f"github_trending failed for {url}: {e}")
            logger.exception("github_trending failed for %s", url)

    logger.info("github_trending: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)
