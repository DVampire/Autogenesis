"""Azure OpenAI plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.openai import AzureOpenaiTool
from .tools.openai_embeddings import AzureOpenaiEmbeddingsTool


@PLUGIN.register_module(force=True)
class AzurePlugin(Plugin):
    """Azure OpenAI tools."""

    tools = (AzureOpenaiTool, AzureOpenaiEmbeddingsTool,)

    name: str = 'azure'
    display_name: str = 'Azure OpenAI'
    description: str = 'Azure OpenAI tools.'
    category: str = 'data'
    type: str = 'model'
