"""Product Hunt scraper — developer tools and AI launches."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

PH_API_URL = "https://api.producthunt.com/v2/api/graphql"
PH_TOKEN = os.environ.get("PRODUCT_HUNT_TOKEN", "")
PH_HOME_URL = "https://www.producthunt.com/"


GRAPHQL_QUERY = """
query GetPosts($after: String) {
  posts(order: NEWEST, after: $after, first: 30) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      node {
        id
        name
        tagline
        description
        url
        website
        createdAt
        votesCount
        topics {
          edges {
            node {
              name
            }
          }
        }
      }
    }
  }
}
"""


@register_source("product_hunt")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    if PH_TOKEN:
        items, errors = _scrape_api(cutoff, errors)
    else:
        errors.append("PRODUCT_HUNT_TOKEN not set — falling back to HTML scrape")
        items, errors = _scrape_html(cutoff, errors)

    logger.info("product_hunt: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)


def _scrape_api(cutoff: datetime, errors: list[str]) -> tuple[list[Item], list[str]]:
    items: list[Item] = []
    headers = {
        "Authorization": f"Bearer {PH_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "HackRadar/1.0",
    }

    cursor = None
    while True:
        try:
            variables = {"after": cursor} if cursor else {}
            resp = requests.post(
                PH_API_URL,
                json={"query": GRAPHQL_QUERY, "variables": variables},
                headers=headers,
                timeout=config.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            posts_data = data.get("data", {}).get("posts", {})
            edges = posts_data.get("edges", [])

            if not edges:
                break

            for edge in edges:
                try:
                    node = edge.get("node", {})
                    created_str = node.get("createdAt", "")
                    if not created_str:
                        continue

                    created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    if created_at < cutoff:
                        return items, errors  # sorted newest first, stop here

                    topics = [
                        e["node"]["name"]
                        for e in node.get("topics", {}).get("edges", [])
                    ]

                    description = node.get("description") or node.get("tagline") or ""
                    if topics:
                        description = f"[{', '.join(topics)}] {description}"

                    item = Item(
                        title=node.get("name", ""),
                        description=description[:800],
                        date=created_at,
                        source="product_hunt",
                        source_url=node.get("url", ""),
                        demo_url=node.get("website") or None,
                        category="tool",
                    )
                    items.append(item)

                except Exception as e:
                    errors.append(f"product_hunt API item error: {e}")

            page_info = posts_data.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

        except Exception as e:
            errors.append(f"product_hunt API request failed: {e}")
            break

    return items, errors


def _scrape_html(cutoff: datetime, errors: list[str]) -> tuple[list[Item], list[str]]:
    items: list[Item] = []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; HackRadar/1.0)",
        "Accept": "text/html",
    }

    try:
        resp = requests.get(PH_HOME_URL, timeout=config.REQUEST_TIMEOUT, headers=headers)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Product Hunt renders as a React app; try to find product listings
        # Look for links that match the /posts/ pattern
        product_links = soup.find_all("a", href=lambda h: h and "/posts/" in h)

        seen = set()
        for link in product_links:
            try:
                href = link.get("href", "")
                if not href or href in seen:
                    continue
                seen.add(href)

                source_url = f"https://www.producthunt.com{href}" if href.startswith("/") else href

                # Title: the link text or a nearby heading
                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                # Description: look for sibling text
                parent = link.parent
                desc = ""
                if parent:
                    desc = parent.get_text(separator=" ", strip=True)
                    desc = desc.replace(title, "").strip()[:500]

                item = Item(
                    title=title,
                    description=desc,
                    date=datetime.now(timezone.utc),
                    source="product_hunt",
                    source_url=source_url,
                    category="tool",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"product_hunt HTML item error: {e}")

    except Exception as e:
        errors.append(f"product_hunt HTML scrape failed: {e}")
        logger.exception("product_hunt HTML scrape failed")

    return items, errors
