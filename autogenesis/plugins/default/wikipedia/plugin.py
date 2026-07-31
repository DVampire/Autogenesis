"""Wikipedia plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.wikidata import WikipediaWikidataTool
from .tools.wikipedia import WikipediaTool


@PLUGIN.register_module(force=True)
class WikipediaPlugin(Plugin):
    """Wikipedia tools."""

    tools = (WikipediaWikidataTool, WikipediaTool,)

    name: str = 'wikipedia'
    display_name: str = 'Wikipedia'
    description: str = 'Wikipedia tools.'
    category: str = 'data'
    type: str = 'tool'
