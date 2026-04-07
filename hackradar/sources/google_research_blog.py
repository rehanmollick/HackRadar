# Method: RSS
# Feed: https://blog.research.google/feeds/posts/default?alt=rss
#
# Google Research Blog publishes papers, model releases, and tool announcements.
# The official Blogger RSS feed is clean and well-formed.

from hackradar.sources import register_source
from hackradar.sources.base_blog import scrape_rss

_RSS_URL = "https://blog.research.google/feeds/posts/default?alt=rss"
_SOURCE = "Google Research Blog"


@register_source("google_research_blog")
def scrape(lookback_hours: int = 48):
    return scrape_rss(
        url=_RSS_URL,
        source_name=_SOURCE,
        lookback_hours=lookback_hours,
    )
