"""Oracle plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.oracledb_embeddings import OracledbEmbeddingsTool
from .tools.oracledb_loaders import OracledbLoadersTool
from .tools.oraclevs import OraclevsTool


@PLUGIN.register_module(force=True)
class OraclePlugin(Plugin):
    """Oracle tools."""

    tools = (OracledbEmbeddingsTool, OracledbLoadersTool, OraclevsTool,)

    name: str = 'oracle'
    display_name: str = 'Oracle'
    description: str = 'Oracle tools.'
    category: str = 'data'
    type: str = 'embedding'
