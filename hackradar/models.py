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
    """Full Pass 2 scoring response — rev 3.1 tech-discovery rubric.

    Four scores (1-10 each):
      usability_score    — can I actually build with this TODAY? (30%)
      innovation_score   — is the underlying tech genuinely new? (35%)
      underexploited_score — has nobody built products on this yet? (25%)
      wow_score          — does the tech itself provoke "wait, what?" (10%)

    Flagship content is a TECH EXPLAINER, not a product pitch:
      what_the_tech_does — 4-6 sentences covering model/architecture/capability
      key_capabilities   — 3-5 bullets: hardware req, license, SOTA claims
      idea_sparks        — 2-3 ONE-LINE brainstorm sparks. Not structured.

    `title` is optional because larger reasoning models (e.g. qwen-3-235b)
    sometimes omit it even when the prompt demands it. We fall back to
    positional matching in _zip_scored_responses when titles are missing.
    `summary` stays Optional because some models skip it on low-scoring
    items despite the schema.
    """

    title: Optional[str] = None
    usability_score: float
    innovation_score: float
    underexploited_score: float
    wow_score: float
    total_score: float = 0.0
    summary: Optional[str] = ""
    what_the_tech_does: Optional[str] = None
    key_capabilities: Optional[list[str]] = None
    idea_sparks: Optional[list[str]] = None


class ScoringBatchResponse(BaseModel):
    """Top-level Pass 2 response: a list of scored items."""

    items: list[ScoredItemResponse]


class TriageResponse(BaseModel):
    """Pass 1 cheap triage response. Novelty+wow composite only."""

    title: str
    triage_score: float  # 1-10 on novelty+wow composite
    reason: str  # one-line justification, helps debug Pass 1 misses


class TriageBatchResponse(BaseModel):
    """Top-level Pass 1 response: a list of triage items."""

    items: list[TriageResponse]


@dataclasses.dataclass
class ScoredItem:
    """An Item with its rev 3.1 scores attached."""

    item: Item
    usability_score: float
    innovation_score: float
    underexploited_score: float
    wow_score: float
    total_score: float
    summary: str
    what_the_tech_does: Optional[str] = None
    key_capabilities: Optional[list[str]] = None
    idea_sparks: Optional[list[str]] = None
