from hackradar.models import ScrapeResult

ALL_SOURCES: list[tuple[str, callable]] = []


def register_source(name: str):
    """Decorator to register a scraper function."""
    def decorator(func):
        ALL_SOURCES.append((name, func))
        return func
    return decorator


def get_all_sources() -> list[tuple[str, callable]]:
    """Import all source modules to trigger registration, then return the list."""
    from hackradar.sources import (  # noqa: F401
        meta_ai_blog,
        deepmind_blog,
        google_research_blog,
        microsoft_research_blog,
        apple_ml_blog,
        stability_ai_blog,
        mistral_blog,
        nvidia_blog,
        anthropic_research,
        openai_research,
        arxiv_source,
        huggingface_models,
        huggingface_papers,
        papers_with_code,
        github_research_orgs,
        github_trending,
        hackernews_show,
        product_hunt,
        chrome_platform,
        webdev_blog,
        mdn_new,
        devhunt,
        kaggle_datasets,
        kaggle_competitions,
        huggingface_datasets,
    )
    return ALL_SOURCES
