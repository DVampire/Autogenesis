"""Cloudflare plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.cloudflare import CloudflareTool


@PLUGIN.register_module(force=True)
class CloudflarePlugin(Plugin):
    """Cloudflare tools."""

    tools = (CloudflareTool,)

    name: str = 'cloudflare'
    display_name: str = 'Cloudflare'
    description: str = 'Cloudflare tools.'
    category: str = 'knowledge'
    type: str = 'embedding'
