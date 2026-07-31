"""ClickHouse plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.clickhouse import ClickhouseTool


@PLUGIN.register_module(force=True)
class ClickhousePlugin(Plugin):
    """ClickHouse tools."""

    tools = (ClickhouseTool,)

    name: str = 'clickhouse'
    display_name: str = 'ClickHouse'
    description: str = 'ClickHouse tools.'
    category: str = 'data'
    type: str = 'vectorstore'
