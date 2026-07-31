"""Couchbase plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.couchbase import CouchbaseTool


@PLUGIN.register_module(force=True)
class CouchbasePlugin(Plugin):
    """Couchbase tools."""

    tools = (CouchbaseTool,)

    name: str = 'couchbase'
    display_name: str = 'Couchbase'
    description: str = 'Couchbase tools.'
    category: str = 'data'
    type: str = 'vectorstore'
