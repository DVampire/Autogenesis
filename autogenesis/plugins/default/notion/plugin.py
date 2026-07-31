"""Notion plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.add_content_to_page import NotionAddContentToPageTool
from .tools.create_page import NotionCreatePageTool
from .tools.list_database_properties import NotionListDatabasePropertiesTool
from .tools.list_pages import NotionListPagesTool
from .tools.list_users import NotionListUsersTool
from .tools.page_content_viewer import NotionPageContentViewerTool
from .tools.search import NotionSearchTool
from .tools.update_page_property import NotionUpdatePagePropertyTool


@PLUGIN.register_module(force=True)
class NotionPlugin(Plugin):
    """Notion tools."""

    tools = (
        NotionAddContentToPageTool,
        NotionCreatePageTool,
        NotionListDatabasePropertiesTool,
        NotionListPagesTool,
        NotionListUsersTool,
        NotionPageContentViewerTool,
        NotionSearchTool,
        NotionUpdatePagePropertyTool,
    )

    name: str = 'notion'
    display_name: str = 'Notion'
    description: str = 'Notion tools.'
    category: str = 'data'
    type: str = 'tool'
