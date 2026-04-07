# Method: HTML scrape
# URL: https://deepmind.google/discover/blog/
#
# DeepMind does not publish a clean public RSS feed. Their blog is rendered
# with a mix of static and JS-hydrated markup; the selectors below target the
# static HTML skeleton which is present in the initial response.

from hackradar.sources import register_source
from hackradar.sources.base_blog import scrape_html

_URL = "https://deepmind.google/discover/blog/"
_SOURCE = "Google DeepMind Blog"

_SELECTORS = {
    # Each post is wrapped in a <li> inside a grid; some themes use <article>
    "article_selector": "li[class*='card'], article, .glue-card, [class*='BlogCard'], [class*='post-card']",
    "title_selector": "h2, h3, h4, [class*='title'], [class*='heading']",
    "link_selector": "a",
    "date_selector": "time, [class*='date'], [class*='Date'], [class*='published']",
    "description_selector": "p, [class*='description'], [class*='excerpt'], [class*='summary']",
}


@register_source("deepmind_blog")
def scrape(lookback_hours: int = 48):
    return scrape_html(
        url=_URL,
        source_name=_SOURCE,
        selectors=_SELECTORS,
        lookback_hours=lookback_hours,
    )
