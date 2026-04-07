"""HuggingFace recently-created model scraper."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from huggingface_hub import HfApi

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)


@register_source("huggingface_models")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    try:
        api = HfApi()

        # List models sorted by creation date, most recent first
        model_iter = api.list_models(
            sort="createdAt",
            direction=-1,
            limit=500,
            cardData=True,
        )

        for model in model_iter:
            try:
                created_at = model.created_at
                if created_at is None:
                    continue

                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)

                if created_at < cutoff:
                    break  # sorted descending, safe to stop

                # Filter: must have a pipeline_tag
                if not model.pipeline_tag:
                    continue

                # Filter: minimum downloads
                downloads = model.downloads or 0
                if downloads < config.HF_MIN_DOWNLOADS:
                    continue

                model_id = model.modelId or model.id
                hf_url = f"https://huggingface.co/{model_id}"

                description = ""
                if model.cardData:
                    description = str(model.cardData.get("description", ""))[:800]
                if not description:
                    description = f"{model.pipeline_tag} model on HuggingFace"

                item = Item(
                    title=model_id,
                    description=description,
                    date=created_at,
                    source="huggingface_models",
                    source_url=hf_url,
                    huggingface_url=hf_url,
                    category="ai_research",
                )
                items.append(item)

            except Exception as e:
                errors.append(f"hf_models item error: {e}")

    except Exception as e:
        errors.append(f"huggingface_models scrape failed: {e}")
        logger.exception("huggingface_models scrape failed")

    logger.info("huggingface_models: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)
