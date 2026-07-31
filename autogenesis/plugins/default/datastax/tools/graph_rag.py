"""Graph RAG."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class DatastaxGraphRagTool(PluginTool):
    """Graph RAG."""

    name: str = 'graph_rag'
    display_name: str = 'Graph RAG'
    description: str = 'Graph RAG traversal for vector store.'
    category: str = 'knowledge'

    async def __call__(self, query: str = "", token: str = "", api_endpoint: str = "", **kwargs) -> Response:
        return self._fail("datastax.graph_rag: GraphRAG traversal needs a built graph vector store + embedding; "
                          "ingest via a vector-store node first, then retrieve.")
