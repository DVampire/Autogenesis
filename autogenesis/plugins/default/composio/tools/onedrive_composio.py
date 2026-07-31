"""OneDrive (Composio)."""

from autogenesis.plugins.types import ComposioPluginTool


class ComposioOnedriveComposioTool(ComposioPluginTool):
    """OneDrive."""

    name: str = 'onedrive_composio'
    display_name: str = 'OneDrive'
    description: str = 'Execute OneDrive actions via Composio.'
    app_name: str = 'one_drive'
