"""Icosa plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.combinatorial_reasoner import IcosacomputingCombinatorialReasonerTool


@PLUGIN.register_module(force=True)
class IcosacomputingPlugin(Plugin):
    """Icosa tools."""

    tools = (IcosacomputingCombinatorialReasonerTool,)

    name: str = 'icosacomputing'
    display_name: str = 'Icosa'
    description: str = 'Icosa tools.'
    category: str = 'agent'
    type: str = 'tool'
