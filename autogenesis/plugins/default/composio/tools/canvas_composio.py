"""Canvas (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioCanvasComposioTool(ComposioPluginTool):
    """Canvas."""

    name: str = 'canvas_composio'
    display_name: str = 'Canvas'
    description: str = 'Execute Canvas actions via Composio.'
    app_name: str = 'canvas'
