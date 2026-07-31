---
id: scrapegraph
name: ScrapeGraph
category: data
type: tool
icon: resources/icon.svg
tools: 3
implemented: 3
credentials: [SCRAPEGRAPH_API_KEY, SGAI_API_KEY]
requirements: [scrapegraph_py]
version: "1.0.0"
---
# ScrapeGraph

ScrapeGraph tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `scrapegraph.scrapegraph_markdownify_api` | ScrapeGraph Markdownify API | ✅ | Given a URL, it will return the markdownified content of the website. |
| `scrapegraph.scrapegraph_search_api` | ScrapeGraph Search API | ✅ | Given a search prompt, it will return search results using ScrapeGraph |
| `scrapegraph.scrapegraph_smart_scraper_api` | ScrapeGraph Smart Scraper API | ✅ | Given a URL, it will return the structured data of the website. |

All 3 tools are implemented.

## Credentials

`SCRAPEGRAPH_API_KEY`, `SGAI_API_KEY`, an `api_key` argument on the call, or a `scrapegraph_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
