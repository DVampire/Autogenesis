"""Composio plugin."""

from autogenesis.plugins.types import Plugin
from autogenesis.registry import PLUGIN

from .tools.agentql_composio import ComposioAgentqlComposioTool
from .tools.agiled_composio import ComposioAgiledComposioTool
from .tools.airtable_composio import ComposioAirtableComposioTool
from .tools.api import ComposioApiTool
from .tools.apollo_composio import ComposioApolloComposioTool
from .tools.asana_composio import ComposioAsanaComposioTool
from .tools.attio_composio import ComposioAttioComposioTool
from .tools.bitbucket_composio import ComposioBitbucketComposioTool
from .tools.bolna_composio import ComposioBolnaComposioTool
from .tools.brightdata_composio import ComposioBrightdataComposioTool
from .tools.calendly_composio import ComposioCalendlyComposioTool
from .tools.canva_composio import ComposioCanvaComposioTool
from .tools.canvas_composio import ComposioCanvasComposioTool
from .tools.coda_composio import ComposioCodaComposioTool
from .tools.contentful_composio import ComposioContentfulComposioTool
from .tools.digicert_composio import ComposioDigicertComposioTool
from .tools.discord_composio import ComposioDiscordComposioTool
from .tools.dropbox_compnent import ComposioDropboxCompnentTool
from .tools.elevenlabs_composio import ComposioElevenlabsComposioTool
from .tools.exa_composio import ComposioExaComposioTool
from .tools.figma_composio import ComposioFigmaComposioTool
from .tools.finage_composio import ComposioFinageComposioTool
from .tools.firecrawl_composio import ComposioFirecrawlComposioTool
from .tools.fireflies_composio import ComposioFirefliesComposioTool
from .tools.fixer_composio import ComposioFixerComposioTool
from .tools.flexisign_composio import ComposioFlexisignComposioTool
from .tools.freshdesk_composio import ComposioFreshdeskComposioTool
from .tools.github_composio import ComposioGithubComposioTool
from .tools.gmail_composio import ComposioGmailComposioTool
from .tools.googlebigquery_composio import ComposioGooglebigqueryComposioTool
from .tools.googlecalendar_composio import ComposioGooglecalendarComposioTool
from .tools.googleclassroom_composio import ComposioGoogleclassroomComposioTool
from .tools.googledocs_composio import ComposioGoogledocsComposioTool
from .tools.googlemeet_composio import ComposioGooglemeetComposioTool
from .tools.googlesheets_composio import ComposioGooglesheetsComposioTool
from .tools.googletasks_composio import ComposioGoogletasksComposioTool
from .tools.heygen_composio import ComposioHeygenComposioTool
from .tools.instagram_composio import ComposioInstagramComposioTool
from .tools.jira_composio import ComposioJiraComposioTool
from .tools.jotform_composio import ComposioJotformComposioTool
from .tools.klaviyo_composio import ComposioKlaviyoComposioTool
from .tools.linear_composio import ComposioLinearComposioTool
from .tools.listennotes_composio import ComposioListennotesComposioTool
from .tools.mem0_composio import ComposioMem0ComposioTool
from .tools.miro_composio import ComposioMiroComposioTool
from .tools.missive_composio import ComposioMissiveComposioTool
from .tools.notion_composio import ComposioNotionComposioTool
from .tools.onedrive_composio import ComposioOnedriveComposioTool
from .tools.outlook_composio import ComposioOutlookComposioTool
from .tools.pandadoc_composio import ComposioPandadocComposioTool
from .tools.peopledatalabs_composio import ComposioPeopledatalabsComposioTool
from .tools.perplexityai_composio import ComposioPerplexityaiComposioTool
from .tools.reddit_composio import ComposioRedditComposioTool
from .tools.serpapi_composio import ComposioSerpapiComposioTool
from .tools.slack_composio import ComposioSlackComposioTool
from .tools.slackbot_composio import ComposioSlackbotComposioTool
from .tools.snowflake_composio import ComposioSnowflakeComposioTool
from .tools.supabase_composio import ComposioSupabaseComposioTool
from .tools.tavily_composio import ComposioTavilyComposioTool
from .tools.timelinesai_composio import ComposioTimelinesaiComposioTool
from .tools.todoist_composio import ComposioTodoistComposioTool
from .tools.wrike_composio import ComposioWrikeComposioTool
from .tools.youtube_composio import ComposioYoutubeComposioTool


@PLUGIN.register_module(force=True)
class ComposioPlugin(Plugin):
    """Composio tools."""

    tools = (
        ComposioAgentqlComposioTool,
        ComposioAgiledComposioTool,
        ComposioAirtableComposioTool,
        ComposioApolloComposioTool,
        ComposioAsanaComposioTool,
        ComposioAttioComposioTool,
        ComposioBitbucketComposioTool,
        ComposioBolnaComposioTool,
        ComposioBrightdataComposioTool,
        ComposioCalendlyComposioTool,
        ComposioCanvaComposioTool,
        ComposioCanvasComposioTool,
        ComposioCodaComposioTool,
        ComposioApiTool,
        ComposioContentfulComposioTool,
        ComposioDigicertComposioTool,
        ComposioDiscordComposioTool,
        ComposioDropboxCompnentTool,
        ComposioElevenlabsComposioTool,
        ComposioExaComposioTool,
        ComposioFigmaComposioTool,
        ComposioFinageComposioTool,
        ComposioFirecrawlComposioTool,
        ComposioFirefliesComposioTool,
        ComposioFixerComposioTool,
        ComposioFlexisignComposioTool,
        ComposioFreshdeskComposioTool,
        ComposioGithubComposioTool,
        ComposioGmailComposioTool,
        ComposioGooglebigqueryComposioTool,
        ComposioGooglecalendarComposioTool,
        ComposioGoogleclassroomComposioTool,
        ComposioGoogledocsComposioTool,
        ComposioGooglemeetComposioTool,
        ComposioGooglesheetsComposioTool,
        ComposioGoogletasksComposioTool,
        ComposioHeygenComposioTool,
        ComposioInstagramComposioTool,
        ComposioJiraComposioTool,
        ComposioJotformComposioTool,
        ComposioKlaviyoComposioTool,
        ComposioLinearComposioTool,
        ComposioListennotesComposioTool,
        ComposioMem0ComposioTool,
        ComposioMiroComposioTool,
        ComposioMissiveComposioTool,
        ComposioNotionComposioTool,
        ComposioOnedriveComposioTool,
        ComposioOutlookComposioTool,
        ComposioPandadocComposioTool,
        ComposioPeopledatalabsComposioTool,
        ComposioPerplexityaiComposioTool,
        ComposioRedditComposioTool,
        ComposioSerpapiComposioTool,
        ComposioSlackComposioTool,
        ComposioSlackbotComposioTool,
        ComposioSnowflakeComposioTool,
        ComposioSupabaseComposioTool,
        ComposioTavilyComposioTool,
        ComposioTimelinesaiComposioTool,
        ComposioTodoistComposioTool,
        ComposioWrikeComposioTool,
        ComposioYoutubeComposioTool,
    )

    name: str = 'composio'
    display_name: str = 'Composio'
    description: str = 'Composio tools.'
    category: str = 'data'
    type: str = 'tool'
