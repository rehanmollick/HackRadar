# Method: HTML scrape
# URL: https://machinelearning.apple.com/
#
# Apple ML Research does not expose an RSS feed. The page uses a static listing
# of research papers and blog posts built on a custom React-style front-end.
# The initial HTML response contains <article> elements we can parse directly.

from hackradar.sources import register_source
from hackradar.sources.base_blog import scrape_html

_URL = "https://machinelearning.apple.com/"
_SOURCE = "Apple ML Research"

_SELECTORS = {
    "article_selector": "article, .result, [class*='tile'], [class*='card'], li[class*='post']",
    "title_selector": "h2, h3, h1, [class*='title']",
    "link_selector": "a",
    "date_selector": "time, [class*='date'], [class*='Date'], span[class*='published']",
    "description_selector": "p, [class*='abstract'], [class*='excerpt'], [class*='description']",
}


@register_source("apple_ml_blog")
def scrape(lookback_hours: int = 48):
    return scrape_html(
        url=_URL,
        source_name=_SOURCE,
        selectors=_SELECTORS,
        lookback_hours=lookback_hours,
    )
