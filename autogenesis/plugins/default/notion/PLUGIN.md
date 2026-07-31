---
id: notion
name: Notion
category: data
type: tool
icon: resources/icon.svg
tools: 8
implemented: 8
credentials: [NOTION_API_KEY, NOTION_INTEGRATION_TOKEN, NOTION_TOKEN]
requirements: [httpx]
version: "1.0.0"
---
# Notion

Notion tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `notion.add_content_to_page` | Add Content to Page  | ✅ | Convert markdown text to Notion blocks and append them to a Notion page. |
| `notion.create_page` | Create Page  | ✅ | A component for creating Notion pages. |
| `notion.list_database_properties` | List Database Properties  | ✅ | Retrieve properties of a Notion database. |
| `notion.list_pages` | List Pages  | ✅ | List Pages |
| `notion.list_users` | List Users  | ✅ | Retrieve users from Notion. |
| `notion.page_content_viewer` | Page Content Viewer  | ✅ | Retrieve the content of a Notion page as plain text. |
| `notion.search` | Search  | ✅ | Searches all pages and databases that have been shared with an integration. |
| `notion.update_page_property` | Update Page Property  | ✅ | Update the properties of a Notion page. |

All 8 tools are implemented.

## Credentials

`NOTION_API_KEY`, `NOTION_INTEGRATION_TOKEN`, `NOTION_TOKEN`, an `api_key` argument on the call, or a `notion_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
