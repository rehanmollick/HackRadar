# Method: HTML scrape
# URL: https://mistral.ai/news/
#
# Mistral AI publishes model and product announcements on their news page.
# No public RSS is available; the page renders article cards in static HTML
# that we parse with BeautifulSoup.

from hackradar.sources import register_source
from hackradar.sources.base_blog import scrape_html

_URL = "https://mistral.ai/news/"
_SOURCE = "Mistral Blog"

_SELECTORS = {
    "article_selector": "article, [class*='NewsCard'], [class*='post-card'], [class*='news-item'], li[class*='post']",
    "title_selector": "h2, h3, h1, [class*='title'], [class*='heading']",
    "link_selector": "a",
    "date_selector": "time, [class*='date'], [class*='Date'], [class*='published']",
    "description_selector": "p, [class*='excerpt'], [class*='description'], [class*='teaser']",
}


@register_source("mistral_blog")
def scrape(lookback_hours: int = 48):
    return scrape_html(
        url=_URL,
        source_name=_SOURCE,
        selectors=_SELECTORS,
        lookback_hours=lookback_hours,
    )
