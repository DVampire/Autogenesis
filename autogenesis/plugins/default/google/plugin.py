"""Google plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.bq_sql_executor import GoogleBqSqlExecutorTool
from .tools.drive import GoogleDriveTool
from .tools.drive_search import GoogleDriveSearchTool
from .tools.generative_ai import GoogleGenerativeAiTool
from .tools.generative_ai_embeddings import GoogleGenerativeAiEmbeddingsTool
from .tools.gmail import GoogleGmailTool
from .tools.oauth_token import GoogleOauthTokenTool
from .tools.search_api_core import GoogleSearchApiCoreTool
from .tools.serper_api_core import GoogleSerperApiCoreTool


@PLUGIN.register_module(force=True)
class GooglePlugin(Plugin):
    """Google tools."""

    tools = (
        GoogleGmailTool,
        GoogleBqSqlExecutorTool,
        GoogleDriveTool,
        GoogleDriveSearchTool,
        GoogleGenerativeAiTool,
        GoogleGenerativeAiEmbeddingsTool,
        GoogleOauthTokenTool,
        GoogleSearchApiCoreTool,
        GoogleSerperApiCoreTool,
    )

    name: str = 'google'
    display_name: str = 'Google'
    description: str = 'Google tools.'
    category: str = 'data'
    type: str = 'tool'
