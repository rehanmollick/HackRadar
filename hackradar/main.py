"""HackRadar V2 CLI — interactive hackathon tech discovery.

Usage:
    hackradar scan                                 # Last 48h window, all sources
    hackradar scan --from 2026-03-25 --to 2026-03-27
    hackradar scan --dry-run                       # Skip DB writes, print to stdout
    hackradar scan --source meta_ai_blog           # Single-source debug
    hackradar scan --no-enrich                     # Skip GitHub/HF enrichment
    hackradar serve                                # Start FastAPI + Next.js
    hackradar db init                              # Create the DB schema
    hackradar db health                            # Print source health table

The scan command is also reused by the FastAPI backend — importing and calling
run_scan(...) directly. Same code path, one scan function.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from hackradar import config, db
from hackradar.dedup import deduplicate
from hackradar.enrich import enrich_items
from hackradar.models import Item, ScoredItem, ScrapeResult
from hackradar.scoring.passes import pass1_triage, pass2_score, run_scraper_tracked
from hackradar.scoring.providers.base import LLMProvider
from hackradar.scoring.providers.cerebras import CerebrasProvider
from hackradar.scoring.providers.groq import GroqProvider
from hackradar.scoring.providers.openrouter import OpenRouterProvider
from hackradar.sources import get_all_sources

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hackradar")


# ---------------------------------------------------------------------------
# Provider chains
# ---------------------------------------------------------------------------

def build_pass1_providers() -> list[LLMProvider]:
    """Pass 1 fallback chain for cheap triage.

    Order matters (tries each in sequence on failure):
      1. Cerebras llama3.1-8b  — 60K TPM, 10x Groq's ceiling.
      2. Groq llama-3.1-8b-instant — same model, 6K TPM, kept as soft fallback.
      3. OpenRouter llama-3.3-70b  — unlimited-ish free fallback, bigger model.
    """
    chain: list[LLMProvider] = []
    if config.CEREBRAS_API_KEY:
        chain.append(
            CerebrasProvider(
                model=config.PASS1_CEREBRAS_MODEL,
                name="cerebras_llama8b",
                # Pass 1 TriageResponse is just title + score + 1 sentence.
                # ~80 tokens/item is realistic; reserve 150 for safety.
                # The default 1200 (sized for Pass 2) would overflow the
                # 8K context window of llama3.1-8b on free tier.
                response_tokens_per_item=150,
            )
        )
    if config.GROQ_API_KEY:
        chain.append(GroqProvider())
    if config.OPENROUTER_API_KEY:
        chain.append(
            OpenRouterProvider(
                model=config.PASS1_OPENROUTER_MODEL,
                name="openrouter_pass1",
            )
        )
    return chain


def build_pass2_providers() -> list[LLMProvider]:
    """Pass 2 fallback chain for full 4-criterion scoring.

    Order matters:
      1. Cerebras qwen-3-235b  — primary, 64K ctx, 30K TPM.
      2. OpenRouter gpt-oss-120b — free fallback when Cerebras is throttled.
    """
    chain: list[LLMProvider] = []
    if config.CEREBRAS_API_KEY:
        chain.append(
            CerebrasProvider(
                model=config.PASS2_MODEL,
                name="cerebras_qwen235b",
            )
        )
    if config.OPENROUTER_API_KEY:
        chain.append(
            OpenRouterProvider(
                model=config.PASS2_OPENROUTER_MODEL,
                name="openrouter_pass2",
            )
        )
    return chain


# ---------------------------------------------------------------------------
# Core scan orchestration
# ---------------------------------------------------------------------------

async def run_scan(
    *,
    window_start: datetime,
    window_end: datetime,
    source_filter: Optional[str] = None,
    dry_run: bool = False,
    enrich: bool = True,
    scan_id: Optional[int] = None,
) -> tuple[list[ScoredItem], Optional[int]]:
    """Execute the full V2 scan pipeline.

    Steps: scrape → dedup → enrich → pass1 triage → pass2 scoring.
    Returns (scored_items_sorted_desc, scan_id).

    When dry_run=True, no SQLite writes happen and scan_id will be None.
    When dry_run=False, a scan row is created (if scan_id is not already
    passed in by the FastAPI caller) and items/scores are persisted.
    """
    lookback_hours = int((window_end - window_start).total_seconds() / 3600)

    logger.info(
        "Scan window: %s → %s (%d hours)",
        window_start.isoformat(), window_end.isoformat(), lookback_hours,
    )

    # Phase 1: Scrape.
    sources = get_all_sources()
    if source_filter:
        sources = [(n, fn) for n, fn in sources if n == source_filter]
        if not sources:
            logger.error("Unknown source: %s", source_filter)
            return [], scan_id

    source_names = [n for n, _ in sources]

    # Create scan row (unless caller already created one via the API).
    if not dry_run and scan_id is None:
        await db.init()
        scan_id = await db.create_scan(
            window_start=window_start.isoformat(),
            window_end=window_end.isoformat(),
            sources=source_names,
        )
        logger.info("Created scan id=%d", scan_id)

    record_health = db.record_source_health if not dry_run else None

    async def _scrape_one(name: str, fn) -> tuple[str, ScrapeResult]:
        result = await run_scraper_tracked(
            name, fn, lookback_hours=lookback_hours, db_record_health=record_health
        )
        return name, result

    scrape_tasks = [_scrape_one(name, fn) for name, fn in sources]
    scrape_results = await asyncio.gather(*scrape_tasks, return_exceptions=True)

    all_items: list[Item] = []
    failed_sources: list[str] = []
    for entry in scrape_results:
        if isinstance(entry, Exception):
            logger.error("Scrape task crashed: %s", entry)
            continue
        name, result = entry
        all_items.extend(result.items)
        if result.errors and not result.items:
            failed_sources.append(name)
        logger.info("[%s] %d items scraped", name, len(result.items))

    logger.info("Phase 1 scrape: %d raw items (%d failed sources)",
                len(all_items), len(failed_sources))

    if not all_items:
        logger.warning("No items scraped. Finishing scan.")
        if not dry_run and scan_id is not None:
            await db.finish_scan(scan_id, status="done", items_found=0, items_scored=0)
        return [], scan_id

    # Phase 1b: filter to the requested window.
    all_items = [i for i in all_items if _within_window(i, window_start, window_end)]
    logger.info("After window filter: %d items", len(all_items))

    # Phase 2: Dedup (reuses V1's dedup module, unchanged).
    deduped = deduplicate(all_items)
    logger.info("Phase 2 dedup: %d → %d items", len(all_items), len(deduped))

    # Phase 3: Enrich (can be skipped for debug speed).
    if enrich:
        enriched = enrich_items(deduped)
        logger.info("Phase 3 enrich: done")
    else:
        enriched = deduped
        logger.info("Phase 3 enrich: SKIPPED (--no-enrich)")

    # Phase 4: Pass 1 triage.
    triaged = await pass1_triage(enriched, build_pass1_providers())
    logger.info("Phase 4 pass1: %d → %d items", len(enriched), len(triaged))

    # Phase 5: Pass 2 scoring.
    scored = await pass2_score(triaged, build_pass2_providers())
    scored.sort(key=lambda s: s.total_score, reverse=True)
    logger.info("Phase 5 pass2: %d items scored", len(scored))

    # Phase 6: Persist (unless dry-run).
    if not dry_run and scan_id is not None:
        for s in scored:
            item_id = await db.upsert_item(_item_to_dict(s.item))
            await db.record_score(
                item_id=item_id,
                scan_id=scan_id,
                pass_num=2,
                provider=config.PASS2_PROVIDER,
                model=config.PASS2_MODEL,
                usability_score=s.usability_score,
                innovation_score=s.innovation_score,
                underexploited_score=s.underexploited_score,
                wow_score=s.wow_score,
                total_score=s.total_score,
                summary=s.summary,
                what_the_tech_does=s.what_the_tech_does,
                key_capabilities=s.key_capabilities,
                idea_sparks=s.idea_sparks,
                prompt_version=config.PROMPT_VERSION,
            )
        await db.finish_scan(
            scan_id,
            status="done",
            items_found=len(all_items),
            items_scored=len(scored),
        )
        logger.info("Scan %d persisted: %d items scored", scan_id, len(scored))

    return scored, scan_id


def _within_window(item: Item, window_start: datetime, window_end: datetime) -> bool:
    """Check if an item's date is within the scan window."""
    item_date = item.date
    if item_date.tzinfo is None:
        item_date = item_date.replace(tzinfo=timezone.utc)
    return window_start <= item_date <= window_end


def _item_to_dict(item: Item) -> dict:
    """Convert an Item dataclass to the dict shape expected by db.upsert_item."""
    return {
        "title": item.title,
        "description": item.description,
        "date": item.date.isoformat() if isinstance(item.date, datetime) else str(item.date),
        "category": item.category,
        "source": item.source,
        "source_url": item.source_url,
        "github_url": item.github_url,
        "huggingface_url": item.huggingface_url,
        "demo_url": item.demo_url,
        "paper_url": item.paper_url,
        "all_sources": item.all_sources,
        "stars": item.stars,
        "language": item.language,
        "license": item.license,
        "readme_excerpt": item.readme_excerpt,
        "model_size": item.model_size,
        "downloads": item.downloads,
        "has_demo_space": item.has_demo_space,
    }


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> datetime:
    """Parse YYYY-MM-DD into a UTC-aware datetime at midnight."""
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


async def _cmd_scan(args) -> int:
    # Validate required keys early.
    missing = config.validate_keys()
    if missing:
        logger.error(
            "Missing required API keys: %s. Copy .env.example to .env and fill them in.",
            ", ".join(missing),
        )
        return 2

    if args.from_date and args.to_date:
        window_start = _parse_date(args.from_date)
        window_end = _parse_date(args.to_date) + timedelta(hours=23, minutes=59)
    else:
        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(hours=config.LOOKBACK_HOURS)

    scored, scan_id = await run_scan(
        window_start=window_start,
        window_end=window_end,
        source_filter=args.source,
        dry_run=args.dry_run,
        enrich=not args.no_enrich,
    )

    top = scored[: config.TOP_N]
    print(f"\n{'=' * 70}")
    print(f"  HackRadar scan: {len(scored)} items scored. Showing top {len(top)}.")
    if scan_id is not None:
        print(f"  scan_id={scan_id}")
    print(f"{'=' * 70}")
    for i, s in enumerate(top, 1):
        print(f"\n#{i}  [{s.total_score:.2f}]  {s.item.title}")
        print(
            f"    Use={s.usability_score:.0f} Inno={s.innovation_score:.0f} "
            f"Under={s.underexploited_score:.0f} Wow={s.wow_score:.0f}"
        )
        print(f"    {s.item.source}  |  {s.item.source_url}")
        if s.summary:
            print(f"    {s.summary}")
        if s.what_the_tech_does:
            print(f"    TECH: {s.what_the_tech_does[:200]}...")
        if s.idea_sparks:
            for spark in s.idea_sparks[:3]:
                print(f"      • {spark}")
    print()
    return 0


async def _cmd_db(args) -> int:
    if args.db_cmd == "init":
        await db.init()
        print(f"DB initialized at {config.DB_PATH}")
        return 0
    if args.db_cmd == "health":
        rows = await db.get_all_source_health()
        if not rows:
            print("No source health data yet. Run a scan first.")
            return 0
        print(f"{'SOURCE':<30} {'STATUS':<8} {'CONS_FAIL':<10} {'LAST_ERROR'}")
        print("-" * 80)
        for row in rows:
            status = "RED" if row["consecutive_failures"] >= 2 else "OK"
            err = (row["last_error"] or "")[:40]
            print(f"{row['source']:<30} {status:<8} {row['consecutive_failures']:<10} {err}")
        return 0
    logger.error("Unknown db subcommand: %s", args.db_cmd)
    return 2


def _cmd_serve(args) -> int:
    """Start the FastAPI backend (Next.js is started separately via bin/hackradar).

    Must be sync: uvicorn.run() internally calls asyncio.run(), which fails if
    we're already inside a running event loop.
    """
    import uvicorn

    asyncio.run(db.init())
    uvicorn.run("hackradar.api:app", host="127.0.0.1", port=8000, reload=args.reload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="hackradar", description="HackRadar V2")
    sub = parser.add_subparsers(dest="cmd", required=True)

    scan_parser = sub.add_parser("scan", help="Run a scan pipeline")
    scan_parser.add_argument("--from", dest="from_date", help="Window start (YYYY-MM-DD)")
    scan_parser.add_argument("--to", dest="to_date", help="Window end (YYYY-MM-DD)")
    scan_parser.add_argument("--source", default=None, help="Single source filter")
    scan_parser.add_argument("--dry-run", action="store_true", help="Print without DB writes")
    scan_parser.add_argument("--no-enrich", action="store_true", help="Skip enrichment phase")

    db_parser = sub.add_parser("db", help="Database admin")
    db_parser.add_argument("db_cmd", choices=["init", "health"])

    serve_parser = sub.add_parser("serve", help="Start the FastAPI backend")
    serve_parser.add_argument("--reload", action="store_true")

    args = parser.parse_args()

    if args.cmd == "scan":
        return asyncio.run(_cmd_scan(args))
    if args.cmd == "db":
        return asyncio.run(_cmd_db(args))
    if args.cmd == "serve":
        return _cmd_serve(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
