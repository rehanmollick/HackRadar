# Method: RSS
# Feed: https://www.microsoft.com/en-us/research/feed/
#
# Microsoft Research publishes a standard WordPress RSS feed covering
# new papers, model drops, tools, and framework releases.

from hackradar.sources import register_source
from hackradar.sources.base_blog import scrape_rss

_RSS_URL = "https://www.microsoft.com/en-us/research/feed/"
_SOURCE = "Microsoft Research Blog"


@register_source("microsoft_research_blog")
def scrape(lookback_hours: int = 48):
    return scrape_rss(
        url=_RSS_URL,
        source_name=_SOURCE,
        lookback_hours=lookback_hours,
    )
