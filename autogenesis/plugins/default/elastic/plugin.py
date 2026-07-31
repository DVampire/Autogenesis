"""Elasticsearch plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.elasticsearch import ElasticsearchTool
from .tools.opensearch import ElasticOpensearchTool
from .tools.opensearch_multimodal import ElasticOpensearchMultimodalTool


@PLUGIN.register_module(force=True)
class ElasticPlugin(Plugin):
    """Elasticsearch tools."""

    tools = (ElasticsearchTool, ElasticOpensearchTool, ElasticOpensearchMultimodalTool,)

    name: str = 'elastic'
    display_name: str = 'Elasticsearch'
    description: str = 'Elasticsearch tools.'
    category: str = 'data'
    type: str = 'vectorstore'
