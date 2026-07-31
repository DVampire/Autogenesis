"""Astra DB plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.astradb_chatmemory import DatastaxAstradbChatmemoryTool
from .tools.astradb_cql import DatastaxAstradbCqlTool
from .tools.astradb_data_api import DatastaxAstradbDataApiTool
from .tools.astradb_graph import DatastaxAstradbGraphTool
from .tools.astradb_tool import DatastaxAstradbToolTool
from .tools.astradb_vectorize import DatastaxAstradbVectorizeTool
from .tools.astradb_vectorstore import DatastaxAstradbVectorstoreTool
from .tools.dotenv import DatastaxDotenvTool
from .tools.graph_rag import DatastaxGraphRagTool
from .tools.hcd import DatastaxHcdTool


@PLUGIN.register_module(force=True)
class DatastaxPlugin(Plugin):
    """Astra DB tools."""

    tools = (
        DatastaxAstradbChatmemoryTool,
        DatastaxAstradbCqlTool,
        DatastaxAstradbDataApiTool,
        DatastaxAstradbGraphTool,
        DatastaxAstradbToolTool,
        DatastaxAstradbVectorizeTool,
        DatastaxAstradbVectorstoreTool,
        DatastaxDotenvTool,
        DatastaxGraphRagTool,
        DatastaxHcdTool,
    )

    name: str = 'datastax'
    display_name: str = 'Astra DB'
    description: str = 'Astra DB tools.'
    category: str = 'data'
    type: str = 'tool'
