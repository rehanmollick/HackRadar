"""HackRadar — Hackathon Technology Discovery Pipeline.

Usage:
    python -m hackradar.main                     # Full run: scrape → dedup → enrich → score → email
    python -m hackradar.main --dry-run            # Skip email, print results to stdout
    python -m hackradar.main --source meta_ai_blog --dry-run  # Single source test
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

from hackradar import config
from hackradar.dedup import deduplicate
from hackradar.emailer import send_email
from hackradar.enrich import enrich_items
from hackradar.models import Item, ScrapeResult
from hackradar.scorer import score_items
from hackradar.sources import get_all_sources

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("hackradar")

SEEN_PATH = Path(__file__).parent.parent / "data" / "seen.json"


def load_seen() -> dict[str, str]:
    """Load seen.json. Returns empty dict on missing or corrupted file."""
    if not SEEN_PATH.exists():
        return {}
    try:
        data = json.loads(SEEN_PATH.read_text())
        if isinstance(data, dict):
            return data
        logger.error("seen.json is not a dict, starting fresh")
        return {}
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load seen.json: %s — starting fresh", e)
        return {}


def save_seen(seen: dict[str, str]) -> None:
    """Atomic write of seen.json (write to tmp, then rename)."""
    SEEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = SEEN_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(seen, indent=2, sort_keys=True))
    tmp_path.rename(SEEN_PATH)


def is_seen(item: Item, seen: dict[str, str]) -> bool:
    """Check if any of the item's URLs are in seen.json."""
    for url in item.get_all_urls():
        if url in seen:
            return True
    return False


def mark_seen(item: Item, seen: dict[str, str]) -> None:
    """Mark item's canonical URL as seen with today's date."""
    seen[item.source_url] = datetime.now(tz=__import__('datetime').timezone.utc).strftime("%Y-%m-%d")


def run(dry_run: bool = False, source_filter: str | None = None) -> None:
    """Run the full pipeline."""
    logger.info("HackRadar pipeline starting")

    # Phase 1: Scrape
    all_items: list[Item] = []
    failed_sources: list[str] = []
    sources = get_all_sources()

    if source_filter:
        sources = [(name, fn) for name, fn in sources if name == source_filter]
        if not sources:
            logger.error("Unknown source: %s", source_filter)
            sys.exit(1)

    for name, scrape_fn in sources:
        logger.info("Scraping: %s", name)
        try:
            result: ScrapeResult = scrape_fn(lookback_hours=config.LOOKBACK_HOURS)
            all_items.extend(result.items)
            if result.errors:
                for err in result.errors:
                    logger.warning("[%s] %s", name, err)
                failed_sources.append(name)
            logger.info("[%s] %d items scraped", name, len(result.items))
        except Exception as e:
            logger.error("[%s] Scraper crashed: %s", name, e)
            failed_sources.append(name)

    logger.info("Phase 1 complete: %d raw items from %d sources (%d failed)",
                len(all_items), len(sources), len(failed_sources))

    if not all_items:
        logger.warning("No items scraped. Exiting.")
        return

    # Phase 2: Dedup
    deduped = deduplicate(all_items)
    logger.info("Phase 2 complete: %d → %d items after dedup", len(all_items), len(deduped))

    # Phase 3: Enrich
    enriched = enrich_items(deduped)
    logger.info("Phase 3 complete: enrichment done")

    # Phase 4: Score
    scored = score_items(enriched)
    scored.sort(key=lambda s: s.total_score, reverse=True)
    logger.info("Phase 4 complete: %d items scored", len(scored))

    # Phase 5: Filter & Email
    seen = load_seen()
    unseen = [s for s in scored if not is_seen(s.item, seen)]
    top = unseen[:config.TOP_N]

    if dry_run:
        logger.info("DRY RUN — printing top %d items:", len(top))
        for i, s in enumerate(top, 1):
            print(f"\n{'='*60}")
            print(f"#{i} [{s.total_score:.1f}] {s.item.title}")
            print(f"  Open={s.open_score:.0f} Novelty={s.novelty_score:.0f} "
                  f"Wow={s.wow_score:.0f} Build={s.build_score:.0f}")
            print(f"  Sources: {s.item.source_count} | {s.item.source_url}")
            print(f"  {s.summary}")
            if s.hackathon_idea:
                print(f"  💡 {s.hackathon_idea}")
        print(f"\n{'='*60}")
        print(f"Total scored: {len(scored)} | Unseen: {len(unseen)} | Showing top {len(top)}")
        if failed_sources:
            print(f"Failed sources: {', '.join(failed_sources)}")
    else:
        if top:
            send_email(top, failed_sources)
            logger.info("Email sent with %d items", len(top))
        else:
            logger.info("No new items to email")

        # Phase 6: Persist
        for s in top:
            mark_seen(s.item, seen)
        save_seen(seen)
        logger.info("seen.json updated (%d total entries)", len(seen))


def main():
    parser = argparse.ArgumentParser(description="HackRadar — Hackathon Technology Discovery")
    parser.add_argument("--dry-run", action="store_true", help="Print results instead of emailing")
    parser.add_argument("--source", type=str, default=None, help="Run only a specific source")
    args = parser.parse_args()
    run(dry_run=args.dry_run, source_filter=args.source)


if __name__ == "__main__":
    main()
