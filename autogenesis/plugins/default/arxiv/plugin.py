"""arXiv plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.arxiv import ArxivTool


@PLUGIN.register_module(force=True)
class ArxivPlugin(Plugin):
    """arXiv tools."""

    tools = (ArxivTool,)

    name: str = 'arxiv'
    display_name: str = 'arXiv'
    description: str = 'arXiv tools.'
    category: str = 'data'
    type: str = 'tool'
