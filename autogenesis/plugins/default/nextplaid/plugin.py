"""NextPlaid plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.nextplaid import NextplaidTool
from .tools.vllm_multivector_embeddings import NextplaidVllmMultivectorEmbeddingsTool


@PLUGIN.register_module(force=True)
class NextplaidPlugin(Plugin):
    """NextPlaid tools."""

    tools = (NextplaidTool, NextplaidVllmMultivectorEmbeddingsTool,)

    name: str = 'nextplaid'
    display_name: str = 'NextPlaid'
    description: str = 'NextPlaid tools.'
    category: str = 'data'
    type: str = 'tool'
