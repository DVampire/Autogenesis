"""CodeAct Agent (Smolagents)."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import PluginTool


class CodeagentsCodeactAgentSmolagentsTool(PluginTool):
    """CodeAct Agent (Smolagents)."""

    name: str = 'codeact_agent_smolagents'
    display_name: str = 'CodeAct Agent (Smolagents)'
    description: str = 'A code-based agent using smolagents CodeAgent for complex tasks.'

    async def __call__(self, input_value: str = "", **kwargs) -> Response:
        return self._fail("codeagents.codeact: this is a Langflow agent-framework component (smolagents CodeAct agent); it needs the "
                          "full agent runtime and is not available as a standalone one-shot tool. "
                          "Use Autogenesis's native agent nodes for equivalent capability.")
