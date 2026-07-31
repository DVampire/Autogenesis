"""Astra DB Tool."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class DatastaxAstradbToolTool(PluginTool):
    """Astra DB Tool."""

    name: str = 'astradb_tool'
    display_name: str = 'Astra DB Tool'
    description: str = 'Tool to run hybrid vector and metadata search on DataStax Astra DB Collection'
    category: str = 'tool'

    async def __call__(self, tool_name: str = "", token: str = "", api_endpoint: str = "", **kwargs) -> Response:
        return self._fail("datastax.tool: this exposes an Astra DB collection AS an agent tool; use it as a "
                          "mounted capability on an agent node rather than a one-shot call.")
