"""NVIDIA System-Assist."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class NvidiaSystemAssistTool(PluginTool):
    """NVIDIA System-Assist."""

    name: str = 'system_assist'
    display_name: str = 'NVIDIA System-Assist'
    description: str = ''
    category: str = 'agent'

    async def __call__(self, prompt: str = "", **kwargs) -> Response:
        return self._fail("nvidia.system_assist: this is a Langflow agent-framework component (NVIDIA G-Assist / RISE local SDK); it needs the "
                          "full agent runtime and is not available as a standalone one-shot tool. "
                          "Use Autogenesis's native agent nodes for equivalent capability.")
