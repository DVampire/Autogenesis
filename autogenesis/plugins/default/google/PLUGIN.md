---
id: google
name: Google
category: data
type: tool
icon: resources/icon.svg
tools: 9
implemented: 9
credentials: [GOOGLE_API_KEY, GOOGLE_CSE_ID, SERPER_API_KEY]
requirements: [google, langchain_community, langchain_google_community, langchain_google_genai, langchain_openai]
version: "1.0.0"
---
# Google

Google tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `google.gmail` | Gmail Loader | ✅ | Loads emails from Gmail using provided credentials. |
| `google.google_bq_sql_executor` | BigQuery | ✅ | Execute SQL queries on Google BigQuery. |
| `google.google_drive` | Google Drive Loader | ✅ | Loads documents from Google Drive using provided credentials. |
| `google.google_drive_search` | Google Drive Search | ✅ | Searches Google Drive files using provided credentials and query parameters. |
| `google.google_generative_ai` | Google Generative AI | ✅ | Generate text using Google Generative AI. |
| `google.google_generative_ai_embeddings` | Google Generative AI Embeddings | ✅ | Google Generative AI Embeddings |
| `google.google_oauth_token` | Google OAuth Token | ✅ | Generates a JSON string with your Google OAuth token. |
| `google.google_search_api_core` | Google Search API | ✅ | Call Google Search API and return results as a DataFrame. |
| `google.google_serper_api_core` | Google Serper API | ✅ | Call the Serper.dev Google Search API. |

All 9 tools are implemented.

## Credentials

`GOOGLE_API_KEY`, `GOOGLE_CSE_ID`, `SERPER_API_KEY`, an `api_key` argument on the call, or a `google_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
