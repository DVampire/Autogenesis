"""MongoDB Atlas plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.atlas import MongodbAtlasTool


@PLUGIN.register_module(force=True)
class MongodbPlugin(Plugin):
    """MongoDB Atlas tools."""

    tools = (MongodbAtlasTool,)

    name: str = 'mongodb'
    display_name: str = 'MongoDB Atlas'
    description: str = 'MongoDB Atlas tools.'
    category: str = 'data'
    type: str = 'vectorstore'
