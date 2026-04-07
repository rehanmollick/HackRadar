"""HuggingFace recently-created datasets scraper."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from huggingface_hub import HfApi

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)


@register_source("huggingface_datasets")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    try:
        api = HfApi()

        dataset_iter = api.list_datasets(
            sort="createdAt",
            direction=-1,
            limit=300,
            cardData=True,
        )

        for dataset in dataset_iter:
            try:
                created_at = dataset.created_at
                if created_at is None:
                    continue

                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)

                if created_at < cutoff:
                    break  # sorted descending

                dataset_id = dataset.id
                hf_url = f"https://huggingface.co/datasets/{dataset_id}"

                description = ""
                if dataset.cardData:
                    description = str(dataset.cardData.get("description", ""))[:600]
                if not description:
                    description = f"New dataset on HuggingFace: {dataset_id}"

                # Get task categories if available
                task_categories = []
                if dataset.cardData:
                    task_categories = dataset.cardData.get("task_categories", [])
                if task_categories:
                    description = f"[{', '.join(task_categories[:3])}] {description}"

                # License
                license_info = None
                if dataset.cardData:
                    lic = dataset.cardData.get("license", "")
                    license_info = str(lic) if lic else None

                item = Item(
                    title=dataset_id,
                    description=description[:700],
                    date=created_at,
                    source="huggingface_datasets",
                    source_url=hf_url,
                    huggingface_url=hf_url,
                    category="dataset",
                    license=license_info,
                )
                items.append(item)

            except Exception as e:
                errors.append(f"hf_datasets item error: {e}")

    except Exception as e:
        errors.append(f"huggingface_datasets scrape failed: {e}")
        logger.exception("huggingface_datasets scrape failed")

    logger.info("huggingface_datasets: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)
