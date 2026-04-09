"""passes.py — multi-pass scoring orchestration.

Pass 1: cheap Groq Llama 3.1 8B triage. Batches of 20. Threshold 5.0.
  CRITICAL safety net: items whose source is in config.HIGH_TRUST_SOURCES
  bypass the triage filter entirely. An 8B model reading a terse scrape
  of "TRIBE v2: brain predictive FM" with no enrichment could easily
  mis-score it below the threshold. The allow-list protects the core
  hackathon use case.

Pass 2: full Cerebras Qwen3 32B 4-criterion scoring. Batches of 3 to
  stay under the 8K context window.
"""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from hackradar import config
from hackradar.models import (
    Item,
    ScoredItem,
    ScoredItemResponse,
    ScoringBatchResponse,
    ScrapeResult,
    TriageBatchResponse,
    TriageResponse,
)
from hackradar.scoring.prompts import build_pass1_prompt, build_pass2_prompt
from hackradar.scoring.providers.base import LLMProvider
from hackradar.scoring.resilient import call_with_fallback

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class TriagedItem:
    item: Item
    triage_score: float
    reason: str
    bypassed: bool  # True if advanced via HIGH_TRUST_SOURCES bypass


async def pass1_triage(
    items: list[Item],
    providers: list[LLMProvider],
    batch_size: Optional[int] = None,
    threshold: Optional[float] = None,
) -> list[TriagedItem]:
    """Run the Pass 1 cheap triage filter.

    Returns items where triage_score >= threshold, UNION items whose source
    is in HIGH_TRUST_SOURCES (regardless of score).

    Safety: if call_with_fallback returns None for every batch (all
    providers dead), we do NOT drop items — we pass everything through
    to Pass 2 so the pipeline still produces scored output. Pass 2's
    more capable model + full context will filter the actual noise.
    """
    if not items:
        return []

    batch_size = batch_size or config.PASS1_BATCH_SIZE
    threshold = threshold if threshold is not None else config.PASS1_TRIAGE_THRESHOLD

    # Partition: high-trust bypasses, others go through triage.
    # After dedup, an item's primary .source may be the firehose that
    # happened to scrape it first, but its all_sources may include a
    # high-trust source. Honor the bypass if ANY source in the merged
    # list is high-trust — that's the TRIBE v2 case where a research
    # blog + HF + GitHub all merge into one item.
    bypass_items: list[Item] = []
    to_triage: list[Item] = []
    for item in items:
        sources_to_check = set(item.all_sources or [item.source])
        sources_to_check.add(item.source)
        if sources_to_check & config.HIGH_TRUST_SOURCES:
            bypass_items.append(item)
        else:
            to_triage.append(item)

    logger.info(
        "Pass 1 triage: %d items total, %d high-trust bypass, %d to triage",
        len(items), len(bypass_items), len(to_triage),
    )

    triaged_results: dict[str, TriagedItem] = {}

    # High-trust bypass path.
    for item in bypass_items:
        key = item.title
        triaged_results[key] = TriagedItem(
            item=item,
            triage_score=10.0,  # synthetic high score; never actually gated on
            reason="high-trust source bypass",
            bypassed=True,
        )

    # Triage the rest in batches.
    # Pace between batches so we don't blow the provider's per-minute token
    # budget. Groq free tier is 6000 TPM on llama-3.1-8b-instant; unpaced
    # runs get killed by 429s after the first 2-3 batches.
    pass1_coordinator_dead = True  # flips False on first successful batch
    batch_starts = list(range(0, len(to_triage), batch_size))
    for batch_idx, start in enumerate(batch_starts):
        batch = to_triage[start : start + batch_size]
        response, provider_name = await call_with_fallback(
            providers=providers,
            items=batch,
            prompt_builder=build_pass1_prompt,
            response_schema=TriageBatchResponse,
        )
        if response is None:
            logger.warning("Pass 1 batch %d-%d: all providers failed", start, start + len(batch))
        else:
            pass1_coordinator_dead = False
            for triage_resp in _zip_triage_responses(batch, response):
                item, resp = triage_resp
                triaged_results[item.title] = TriagedItem(
                    item=item,
                    triage_score=resp.triage_score,
                    reason=resp.reason,
                    bypassed=False,
                )

        # Sleep between batches (skip after the final batch).
        if batch_idx < len(batch_starts) - 1 and config.PASS1_INTER_BATCH_SLEEP_S > 0:
            await asyncio.sleep(config.PASS1_INTER_BATCH_SLEEP_S)

    # Safety net: if Pass 1 coordinator died for EVERY batch, pass all
    # non-bypassed items through unfiltered. Better to waste a few Pass 2
    # calls than to drop everything.
    if pass1_coordinator_dead and to_triage:
        logger.warning(
            "Pass 1 coordinator dead across all batches — advancing all %d "
            "non-bypassed items to Pass 2 as a safety measure",
            len(to_triage),
        )
        for item in to_triage:
            if item.title not in triaged_results:
                triaged_results[item.title] = TriagedItem(
                    item=item,
                    triage_score=threshold,  # marginal passing score
                    reason="pass1 coordinator dead — safety bypass",
                    bypassed=False,
                )

    # Apply threshold filter to the non-bypassed items.
    filtered: list[TriagedItem] = []
    for triaged in triaged_results.values():
        if triaged.bypassed or triaged.triage_score >= threshold:
            filtered.append(triaged)
        else:
            logger.debug(
                "Pass 1 drop: %s (score=%.1f, reason=%s)",
                triaged.item.title, triaged.triage_score, triaged.reason,
            )

    logger.info(
        "Pass 1 complete: %d/%d items advanced to Pass 2",
        len(filtered), len(items),
    )
    return filtered


def _zip_triage_responses(
    items: list[Item],
    response: TriageBatchResponse,
) -> list[tuple[Item, TriageResponse]]:
    """Match Pass 1 responses back to input items.

    Happy path: same length, zip by position. Mismatch: match by title.
    """
    if len(response.items) == len(items):
        return list(zip(items, response.items))

    logger.warning(
        "Pass 1 response count mismatch: sent %d, got %d — matching by title",
        len(items), len(response.items),
    )
    by_title = {r.title.lower(): r for r in response.items}
    out: list[tuple[Item, TriageResponse]] = []
    for item in items:
        resp = by_title.get(item.title.lower())
        if resp is not None:
            out.append((item, resp))
    return out


# ---------------------------------------------------------------------------
# Pass 2
# ---------------------------------------------------------------------------

async def pass2_score(
    triaged: list[TriagedItem],
    providers: list[LLMProvider],
    batch_size: Optional[int] = None,
    inter_batch_sleep_s: Optional[float] = None,
) -> list[ScoredItem]:
    """Run the Pass 2 full 4-criterion scorer on the triaged items."""
    if not triaged:
        return []

    batch_size = batch_size or config.PASS2_BATCH_SIZE
    sleep_s = inter_batch_sleep_s if inter_batch_sleep_s is not None else config.PASS2_INTER_BATCH_SLEEP_S

    items = [t.item for t in triaged]
    scored: list[ScoredItem] = []

    num_batches = (len(items) + batch_size - 1) // batch_size
    for batch_idx, start in enumerate(range(0, len(items), batch_size)):
        batch = items[start : start + batch_size]
        logger.info("Pass 2 batch %d/%d (%d items)", batch_idx + 1, num_batches, len(batch))

        response, provider_name = await call_with_fallback(
            providers=providers,
            items=batch,
            prompt_builder=build_pass2_prompt,
            response_schema=ScoringBatchResponse,
        )
        if response is None or not provider_name:
            logger.warning("Pass 2 batch %d: all providers failed", batch_idx + 1)
            continue

        for item, resp in _zip_scored_responses(batch, response):
            scored.append(_make_scored_item(item, resp, provider_name))

        # Natural pacing: sleep between batches to stay under Cerebras 30 RPM.
        if sleep_s > 0 and batch_idx < num_batches - 1:
            await asyncio.sleep(sleep_s)

    logger.info("Pass 2 complete: %d/%d items scored", len(scored), len(items))
    return scored


def _zip_scored_responses(
    items: list[Item],
    response: ScoringBatchResponse,
) -> list[tuple[Item, ScoredItemResponse]]:
    """Match Pass 2 responses back to input items.

    Happy path: identical counts → zip by position. This is the most reliable
    strategy because Cerebras/OpenRouter sometimes omit or mangle the title
    field even when we demand it in the prompt.

    Fallback: counts differ → build a by-title index from responses that DO
    have titles, try exact match, then fuzzy match. Responses with no title
    can still be matched positionally if we can find an unused slot.
    """
    if len(response.items) == len(items):
        return list(zip(items, response.items))

    logger.warning(
        "Pass 2 response count mismatch: sent %d, got %d — matching by title",
        len(items), len(response.items),
    )

    # Build a by-title index from responses that actually carry a title.
    by_title: dict[str, ScoredItemResponse] = {}
    untitled: list[ScoredItemResponse] = []
    for r in response.items:
        if r.title:
            by_title[r.title.lower()] = r
        else:
            untitled.append(r)

    out: list[tuple[Item, ScoredItemResponse]] = []
    consumed_untitled = 0
    for idx, item in enumerate(items):
        resp = by_title.get(item.title.lower())
        if resp is None:
            # Fuzzy fallback on titled responses.
            try:
                from rapidfuzz import process as rfprocess

                match = rfprocess.extractOne(
                    item.title.lower(), list(by_title.keys()), score_cutoff=70
                )
                if match:
                    resp = by_title[match[0]]
            except ImportError:
                pass
        if resp is None and consumed_untitled < len(untitled):
            # Last resort: positional fallback using untitled responses.
            resp = untitled[consumed_untitled]
            consumed_untitled += 1
        if resp is not None:
            out.append((item, resp))
    return out


def _make_scored_item(
    item: Item, resp: ScoredItemResponse, provider_name: str
) -> ScoredItem:
    # Recompute the total server-side per rev 3.1 weights to guard
    # against LLM arithmetic drift.
    total = (
        resp.usability_score * config.WEIGHT_USABILITY
        + resp.innovation_score * config.WEIGHT_INNOVATION
        + resp.underexploited_score * config.WEIGHT_UNDEREXPLOITED
        + resp.wow_score * config.WEIGHT_WOW
    )
    # Usability floor: paper-only / non-buildable items cannot outrank
    # anything with working code. Without this, a U=2 / I=10 / Un=10 / W=10
    # paper computes to 8.20 and sits above buildable tech at 8.00. Cap such
    # items at 7.49 so they stay visible (and still get the tech explainer at
    # SCORE_THRESHOLD=6.5) but never tie a buildable item sitting at 7.50+.
    if resp.usability_score < 6:
        total = min(total, 7.49)
    # Gate the rich tech-explainer output so we don't waste UI space
    # on low-scoring items. The tech explainer IS the flagship content,
    # so SCORE_THRESHOLD (6.5) is the right cutoff — items below that
    # just get a 1-line summary.
    gated = total >= config.SCORE_THRESHOLD
    return ScoredItem(
        item=item,
        usability_score=resp.usability_score,
        innovation_score=resp.innovation_score,
        underexploited_score=resp.underexploited_score,
        wow_score=resp.wow_score,
        total_score=total,
        summary=resp.summary or "",
        what_the_tech_does=resp.what_the_tech_does if gated else None,
        key_capabilities=resp.key_capabilities if gated else None,
        idea_sparks=resp.idea_sparks if gated else None,
    )


# ---------------------------------------------------------------------------
# Scraper health wrapper
# ---------------------------------------------------------------------------

async def run_scraper_tracked(
    name: str,
    scrape_fn: Callable[..., ScrapeResult],
    *,
    lookback_hours: int,
    db_record_health: Optional[Callable[..., Awaitable[None]]] = None,
) -> ScrapeResult:
    """Wrap a sync scraper with async threading + source health tracking."""
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = await asyncio.to_thread(scrape_fn, lookback_hours=lookback_hours)
    except Exception as exc:
        logger.error("[%s] scraper crashed: %s", name, exc)
        if db_record_health:
            await db_record_health(
                source=name,
                success=False,
                last_error=f"{type(exc).__name__}: {exc}"[:500],
                at=started,
            )
        return ScrapeResult(items=[], errors=[f"{type(exc).__name__}: {exc}"])

    # Empty result + errors counts as failure (V1 treated this as success).
    if result.errors and not result.items:
        logger.warning("[%s] scraper returned empty with errors: %s", name, result.errors)
        if db_record_health:
            await db_record_health(
                source=name,
                success=False,
                last_error="; ".join(result.errors)[:500],
                at=started,
            )
    else:
        if db_record_health:
            await db_record_health(source=name, success=True, at=started)

    return result
