# Method: RSS
# Feed: https://developer.nvidia.com/blog/feed/
#
# NVIDIA Developer Blog publishes a WordPress RSS feed that covers
# new GPU features, research model releases, CUDA libraries, and tool drops.

from hackradar.sources import register_source
from hackradar.sources.base_blog import scrape_rss

_RSS_URL = "https://developer.nvidia.com/blog/feed/"
_SOURCE = "NVIDIA Developer Blog"


@register_source("nvidia_blog")
def scrape(lookback_hours: int = 48):
    return scrape_rss(
        url=_RSS_URL,
        source_name=_SOURCE,
        lookback_hours=lookback_hours,
    )
