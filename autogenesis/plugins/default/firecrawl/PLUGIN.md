---
id: firecrawl
name: Firecrawl
category: data
type: tool
icon: resources/icon.svg
tools: 4
implemented: 4
credentials: [FIRECRAWL_API_KEY]
requirements: [firecrawl]
version: "1.0.0"
---
# Firecrawl

Firecrawl tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `firecrawl.firecrawl_crawl_api` | Firecrawl Crawl API | ✅ | Crawls a URL and returns the results. |
| `firecrawl.firecrawl_map_api` | Firecrawl Map API | ✅ | Maps a URL and returns the results. |
| `firecrawl.firecrawl_scrape_api` | Firecrawl Scrape API | ✅ | Scrapes a URL and returns the results. |
| `firecrawl.firecrawl_search_api` | Firecrawl Search API | ✅ | Searches the web and returns the results. |

All 4 tools are implemented.

## Credentials

`FIRECRAWL_API_KEY`, an `api_key` argument on the call, or a `firecrawl_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
