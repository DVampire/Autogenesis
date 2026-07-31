"""Firecrawl plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.crawl_api import FirecrawlCrawlApiTool
from .tools.map_api import FirecrawlMapApiTool
from .tools.scrape_api import FirecrawlScrapeApiTool
from .tools.search_api import FirecrawlSearchApiTool


@PLUGIN.register_module(force=True)
class FirecrawlPlugin(Plugin):
    """Firecrawl tools."""

    tools = (
        FirecrawlCrawlApiTool,
        FirecrawlMapApiTool,
        FirecrawlScrapeApiTool,
        FirecrawlSearchApiTool,
    )

    name: str = 'firecrawl'
    display_name: str = 'Firecrawl'
    description: str = 'Firecrawl tools.'
    category: str = 'data'
    type: str = 'tool'
