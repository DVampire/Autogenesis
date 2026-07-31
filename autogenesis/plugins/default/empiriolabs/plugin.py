"""EmpirioLabs plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.empiriolabs import EmpiriolabsTool
from .tools.image_generation import EmpiriolabsImageGenerationTool


@PLUGIN.register_module(force=True)
class EmpiriolabsPlugin(Plugin):
    """EmpirioLabs tools."""

    tools = (EmpiriolabsTool, EmpiriolabsImageGenerationTool,)

    name: str = 'empiriolabs'
    display_name: str = 'EmpirioLabs'
    description: str = 'EmpirioLabs tools.'
    category: str = 'agent'
    type: str = 'tool'
