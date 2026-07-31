"""Astra DB Graph."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class DatastaxAstradbGraphTool(PluginTool):
    """Astra DB Graph."""

    name: str = 'astradb_graph'
    display_name: str = 'Astra DB Graph'
    description: str = 'Implementation of Graph Vector Store using Astra DB'
    category: str = 'knowledge'

    async def __call__(self, collection_name: str = "", token: str = "", api_endpoint: str = "", **kwargs) -> Response:
        return self._fail("datastax.graph: the Astra DB graph vector store needs an embedding model and a "
                          "reachable collection; wire it via datastax.astradb_vectorstore for standalone use.")
