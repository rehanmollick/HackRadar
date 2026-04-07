# Method: HTML scrape
# URL: https://www.anthropic.com/research
#
# Anthropic's research page lists papers and technical blog posts.
# The page is Next.js server-rendered so the initial HTML response
# contains the article listing we need.

from hackradar.sources import register_source
from hackradar.sources.base_blog import scrape_html

_URL = "https://www.anthropic.com/research"
_SOURCE = "Anthropic Research"

_SELECTORS = {
    # Anthropic uses a card grid; each card may be an <a> wrapping the content
    "article_selector": "article, [class*='PostCard'], [class*='ResearchCard'], [class*='card'], a[class*='post']",
    "title_selector": "h2, h3, h1, [class*='title'], [class*='heading']",
    "link_selector": "a",
    "date_selector": "time, [class*='date'], [class*='Date'], [class*='published'], [class*='PublishDate']",
    "description_selector": "p, [class*='excerpt'], [class*='description'], [class*='abstract']",
}


@register_source("anthropic_research")
def scrape(lookback_hours: int = 48):
    return scrape_html(
        url=_URL,
        source_name=_SOURCE,
        selectors=_SELECTORS,
        lookback_hours=lookback_hours,
    )
