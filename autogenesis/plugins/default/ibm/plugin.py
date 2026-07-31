"""IBM DB2 plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.db2_vector import IbmDb2VectorTool
from .tools.watsonx import IbmWatsonxTool
from .tools.watsonx_embeddings import IbmWatsonxEmbeddingsTool


@PLUGIN.register_module(force=True)
class IbmPlugin(Plugin):
    """IBM DB2 tools."""

    tools = (IbmDb2VectorTool, IbmWatsonxTool, IbmWatsonxEmbeddingsTool,)

    name: str = 'ibm'
    display_name: str = 'IBM DB2'
    description: str = 'IBM DB2 tools.'
    category: str = 'data'
    type: str = 'vectorstore'
