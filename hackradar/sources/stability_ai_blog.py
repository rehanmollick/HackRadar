# Method: HTML scrape
# URL: https://stability.ai/news-updates  (the old /blog path now 404s)
#
# Stability AI moved to a Squarespace site. The selectors below target the
# article card grid present in the static HTML response.

from hackradar.sources import register_source
from hackradar.sources.base_blog import scrape_html

_URL = "https://stability.ai/news-updates"
_SOURCE = "Stability AI Blog"

_SELECTORS = {
    "article_selector": "article, .post-card, [class*='PostCard'], [class*='blog-post'], li[class*='post']",
    "title_selector": "h2, h3, h1, [class*='title'], [class*='heading']",
    "link_selector": "a",
    "date_selector": "time, [class*='date'], [class*='Date'], [class*='published-at']",
    "description_selector": "p, [class*='excerpt'], [class*='description'], [class*='preview']",
}


@register_source("stability_ai_blog")
def scrape(lookback_hours: int = 48):
    return scrape_html(
        url=_URL,
        source_name=_SOURCE,
        selectors=_SELECTORS,
        lookback_hours=lookback_hours,
    )
