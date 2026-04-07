# Method: HTML scrape
# URL: https://openai.com/research
#
# OpenAI's research index is a Next.js page. The initial HTML contains
# research post cards that we can scrape without JavaScript execution.
# If OpenAI blocks static scrapers, add a Playwright fallback.

from hackradar.sources import register_source
from hackradar.sources.base_blog import scrape_html

_URL = "https://openai.com/research"
_SOURCE = "OpenAI Research"

_SELECTORS = {
    # OpenAI uses a React-rendered grid; cards often have class names like
    # "research-item" or are generic <li> elements with article content.
    "article_selector": "article, li[class*='research'], [class*='ResearchCard'], [class*='post-card'], [class*='card']",
    "title_selector": "h2, h3, h1, [class*='title'], [class*='heading']",
    "link_selector": "a",
    "date_selector": "time, [class*='date'], [class*='Date'], [class*='published'], [class*='pubdate']",
    "description_selector": "p, [class*='excerpt'], [class*='description'], [class*='abstract'], [class*='teaser']",
}


@register_source("openai_research")
def scrape(lookback_hours: int = 48):
    return scrape_html(
        url=_URL,
        source_name=_SOURCE,
        selectors=_SELECTORS,
        lookback_hours=lookback_hours,
    )
