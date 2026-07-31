"""Cleanlab plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.evaluator import CleanlabEvaluatorTool
from .tools.rag_evaluator import CleanlabRagEvaluatorTool
from .tools.remediator import CleanlabRemediatorTool


@PLUGIN.register_module(force=True)
class CleanlabPlugin(Plugin):
    """Cleanlab tools."""

    tools = (CleanlabEvaluatorTool, CleanlabRagEvaluatorTool, CleanlabRemediatorTool,)

    name: str = 'cleanlab'
    display_name: str = 'Cleanlab'
    description: str = 'Cleanlab tools.'
    category: str = 'evaluation'
    type: str = 'tool'
