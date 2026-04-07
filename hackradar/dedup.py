"""dedup.py — Deduplicate scraped items using URL overlap, fuzzy title matching,
and GitHub/HuggingFace repo-name matching.

Uses a union-find (disjoint-set) structure to build merge groups, then
produces one merged Item per group.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from rapidfuzz import fuzz

from hackradar import config
from hackradar.models import Item

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Union-Find helpers
# ---------------------------------------------------------------------------

class _UnionFind:
    def __init__(self, n: int) -> None:
        self._parent = list(range(n))
        self._rank = [0] * n

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path compression
            x = self._parent[x]
        return x

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self._rank[rx] < self._rank[ry]:
            rx, ry = ry, rx
        self._parent[ry] = rx
        if self._rank[rx] == self._rank[ry]:
            self._rank[rx] += 1

    def groups(self, n: int) -> dict[int, list[int]]:
        """Return {root_index: [member_indices]} for all n items."""
        result: dict[int, list[int]] = {}
        for i in range(n):
            root = self.find(i)
            result.setdefault(root, []).append(i)
        return result


# ---------------------------------------------------------------------------
# URL / repo-name helpers
# ---------------------------------------------------------------------------

def _normalise_url(url: str) -> str:
    """Strip trailing slashes and lowercase scheme+host for comparison."""
    url = url.strip().rstrip("/")
    parsed = urlparse(url)
    # Keep the original casing of the path (GitHub repo names are case-sensitive
    # in practice but we lowercase for matching only).
    return url.lower()


def _extract_repo_name(url: str) -> str | None:
    """
    Extract the final 'owner/repo' segment from a GitHub or HuggingFace URL.

    github.com/facebookresearch/tribev2  → facebookresearch/tribev2
    huggingface.co/facebook/tribev2      → facebook/tribev2
    Returns None if the URL doesn't look like a two-segment repo path.
    """
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if "github.com" not in host and "huggingface.co" not in host:
        return None
    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) >= 2:
        return f"{parts[0].lower()}/{parts[1].lower()}"
    return None


# ---------------------------------------------------------------------------
# Merge logic
# ---------------------------------------------------------------------------

def _merge(primary: Item, secondary: Item) -> Item:
    """
    Merge *secondary* into *primary*, returning a new Item.

    Rules:
    - Keep the longer description.
    - Combine all_urls and all_sources.
    - Copy non-None URL fields from secondary if primary's field is None.
    - Copy non-None enrichment fields from secondary if primary's field is None.
    - Increment source_count.
    """
    # Which item has the richer description?
    if len(secondary.description) > len(primary.description):
        primary, secondary = secondary, primary

    # Merge URL sets
    merged_urls = list(dict.fromkeys(primary.all_urls + secondary.all_urls))
    merged_sources = list(dict.fromkeys(primary.all_sources + secondary.all_sources))

    # Collect optional URL fields — prefer primary's value
    def _pick(a, b):
        return a if a is not None else b

    merged = Item(
        title=primary.title,
        description=primary.description,
        date=primary.date if primary.date <= secondary.date else secondary.date,  # earliest date
        source=primary.source,
        source_url=primary.source_url,
        category=primary.category,
        github_url=_pick(primary.github_url, secondary.github_url),
        huggingface_url=_pick(primary.huggingface_url, secondary.huggingface_url),
        demo_url=_pick(primary.demo_url, secondary.demo_url),
        paper_url=_pick(primary.paper_url, secondary.paper_url),
        source_count=len(merged_sources),
        all_sources=merged_sources,
        all_urls=merged_urls,
        # Enrichment
        stars=_pick(primary.stars, secondary.stars),
        language=_pick(primary.language, secondary.language),
        license=_pick(primary.license, secondary.license),
        readme_excerpt=_pick(primary.readme_excerpt, secondary.readme_excerpt),
        model_size=_pick(primary.model_size, secondary.model_size),
        downloads=_pick(primary.downloads, secondary.downloads),
        has_demo_space=_pick(primary.has_demo_space, secondary.has_demo_space),
    )
    return merged


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def deduplicate(items: list[Item]) -> list[Item]:
    """
    Deduplicate a list of Items using three strategies:

    1. Exact URL match — any shared URL (source_url, github_url, etc.)
    2. Fuzzy title match — rapidfuzz token_sort_ratio > FUZZY_MATCH_THRESHOLD
    3. GitHub / HuggingFace repo-name match — same owner/repo across sources

    Returns a new list with duplicates merged.
    """
    if not items:
        return []

    n = len(items)
    uf = _UnionFind(n)

    # -----------------------------------------------------------------------
    # Strategy 1: Exact URL match
    # -----------------------------------------------------------------------
    url_to_index: dict[str, int] = {}
    for i, item in enumerate(items):
        for raw_url in item.get_all_urls():
            norm = _normalise_url(raw_url)
            if norm in url_to_index:
                uf.union(i, url_to_index[norm])
            else:
                url_to_index[norm] = i

    # -----------------------------------------------------------------------
    # Strategy 2: Fuzzy title match
    # -----------------------------------------------------------------------
    titles = [item.title for item in items]
    for i in range(n):
        for j in range(i + 1, n):
            # Skip if already in the same group — saves cycles
            if uf.find(i) == uf.find(j):
                continue
            score = fuzz.token_sort_ratio(titles[i], titles[j])
            if score >= config.FUZZY_MATCH_THRESHOLD:
                logger.debug(
                    "Fuzzy match (%.0f): %r  ↔  %r", score, titles[i], titles[j]
                )
                uf.union(i, j)

    # -----------------------------------------------------------------------
    # Strategy 3: GitHub / HuggingFace repo-name match
    # -----------------------------------------------------------------------
    repo_to_index: dict[str, int] = {}
    for i, item in enumerate(items):
        for url in [item.github_url, item.huggingface_url]:
            if not url:
                continue
            repo = _extract_repo_name(url)
            if repo:
                if repo in repo_to_index:
                    uf.union(i, repo_to_index[repo])
                else:
                    repo_to_index[repo] = i

    # -----------------------------------------------------------------------
    # Build merged items from groups
    # -----------------------------------------------------------------------
    groups = uf.groups(n)
    result: list[Item] = []
    for root, members in groups.items():
        if len(members) == 1:
            result.append(items[members[0]])
            continue
        # Merge all members in the group into one item
        merged = items[members[0]]
        for idx in members[1:]:
            merged = _merge(merged, items[idx])
        logger.debug(
            "Merged %d items → %r (sources: %s)",
            len(members),
            merged.title,
            ", ".join(merged.all_sources),
        )
        result.append(merged)

    logger.info("Dedup: %d raw → %d unique items", n, len(result))
    return result
