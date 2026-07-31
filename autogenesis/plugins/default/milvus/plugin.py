"""Milvus plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.milvus import MilvusTool


@PLUGIN.register_module(force=True)
class MilvusPlugin(Plugin):
    """Milvus tools."""

    tools = (MilvusTool,)

    name: str = 'milvus'
    display_name: str = 'Milvus'
    description: str = 'Milvus tools.'
    category: str = 'data'
    type: str = 'vectorstore'
