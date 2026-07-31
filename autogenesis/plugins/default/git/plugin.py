"""Git plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.git import GitTool
from .tools.gitextractor import GitextractorTool


@PLUGIN.register_module(force=True)
class GitPlugin(Plugin):
    """Git tools."""

    tools = (GitTool, GitextractorTool,)

    name: str = 'git'
    display_name: str = 'Git'
    description: str = 'Git tools.'
    category: str = 'data'
    type: str = 'tool'
