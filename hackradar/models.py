from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


@dataclasses.dataclass
class Item:
    """A single technology discovery from any source."""

    title: str
    description: str
    date: datetime
    source: str
    source_url: str
    category: str  # ai_research | tool | api | browser | dataset | misc

    # Optional link fields
    github_url: Optional[str] = None
    huggingface_url: Optional[str] = None
    demo_url: Optional[str] = None
    paper_url: Optional[str] = None

    # Dedup tracking
    source_count: int = 1
    all_sources: list[str] = dataclasses.field(default_factory=list)
    all_urls: list[str] = dataclasses.field(default_factory=list)

    # Enrichment fields (populated by enrich.py)
    stars: Optional[int] = None
    language: Optional[str] = None
    license: Optional[str] = None
    readme_excerpt: Optional[str] = None
    model_size: Optional[str] = None
    downloads: Optional[int] = None
    has_demo_space: Optional[bool] = None

    def __post_init__(self):
        if not self.all_sources:
            self.all_sources = [self.source]
        if not self.all_urls:
            urls = [self.source_url]
            for url in [self.github_url, self.huggingface_url, self.demo_url, self.paper_url]:
                if url:
                    urls.append(url)
            self.all_urls = urls

    def get_all_urls(self) -> set[str]:
        """Return all known URLs for this item."""
        urls = set(self.all_urls)
        for url in [self.source_url, self.github_url, self.huggingface_url, self.demo_url, self.paper_url]:
            if url:
                urls.add(url)
        return urls


@dataclasses.dataclass
class ScrapeResult:
    """Return type for all scrapers."""

    items: list[Item]
    errors: list[str]


class ScoredItemResponse(BaseModel):
    """Pydantic model for Gemini scoring output. One per item in a batch."""

    title: str
    open_score: float
    novelty_score: float
    wow_score: float
    build_score: float
    total_score: float
    summary: str
    hackathon_idea: Optional[str] = None
    tech_stack: Optional[str] = None
    why_now: Optional[str] = None
    effort_estimate: Optional[str] = None


class ScoringBatchResponse(BaseModel):
    """Top-level response from Gemini: a list of scored items."""

    items: list[ScoredItemResponse]


@dataclasses.dataclass
class ScoredItem:
    """An Item with its scores attached, used after scoring phase."""

    item: Item
    open_score: float
    novelty_score: float
    wow_score: float
    build_score: float
    total_score: float
    summary: str
    hackathon_idea: Optional[str] = None
    tech_stack: Optional[str] = None
    why_now: Optional[str] = None
    effort_estimate: Optional[str] = None
