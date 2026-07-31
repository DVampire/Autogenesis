"""Unstructured plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.unstructured import UnstructuredTool


@PLUGIN.register_module(force=True)
class UnstructuredPlugin(Plugin):
    """Unstructured tools."""

    tools = (UnstructuredTool,)

    name: str = 'unstructured'
    display_name: str = 'Unstructured'
    description: str = 'Unstructured tools.'
    category: str = 'files'
    type: str = 'tool'
