"""Home Assistant plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.home_assistant_control import HomeassistantHomeAssistantControlTool
from .tools.list_home_assistant_states import HomeassistantListHomeAssistantStatesTool


@PLUGIN.register_module(force=True)
class HomeassistantPlugin(Plugin):
    """Home Assistant tools."""

    tools = (HomeassistantHomeAssistantControlTool, HomeassistantListHomeAssistantStatesTool,)

    name: str = 'homeassistant'
    display_name: str = 'Home Assistant'
    description: str = 'Home Assistant tools.'
    category: str = 'data'
    type: str = 'tool'
