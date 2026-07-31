"""OpenDsStar Agent."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class CodeagentsOpenDsStarAgentTool(PluginTool):
    """OpenDsStar Agent."""

    name: str = 'open_ds_star_agent'
    display_name: str = 'OpenDsStar Agent'
    description: str = 'A tool-based DS-Star agent using LangGraph for complex data science tasks.'

    async def __call__(self, input_value: str = "", **kwargs) -> Response:
        return self._fail("codeagents.ds_star: this is a Langflow agent-framework component (DS-STAR data-science agent); it needs the "
                          "full agent runtime and is not available as a standalone one-shot tool. "
                          "Use Autogenesis's native agent nodes for equivalent capability.")
