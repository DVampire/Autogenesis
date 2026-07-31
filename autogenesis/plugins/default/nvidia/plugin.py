"""NVIDIA plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.embedding import NvidiaEmbeddingTool
from .tools.ingest import NvidiaIngestTool
from .tools.nvidia import NvidiaTool
from .tools.rerank import NvidiaRerankTool
from .tools.system_assist import NvidiaSystemAssistTool


@PLUGIN.register_module(force=True)
class NvidiaPlugin(Plugin):
    """NVIDIA tools."""

    tools = (
        NvidiaTool,
        NvidiaEmbeddingTool,
        NvidiaIngestTool,
        NvidiaRerankTool,
        NvidiaSystemAssistTool,
    )

    name: str = 'nvidia'
    display_name: str = 'NVIDIA'
    description: str = 'NVIDIA tools.'
    category: str = 'data'
    type: str = 'tool'
