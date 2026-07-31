---
id: spider
name: Spider
category: data
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [SPIDER_API_KEY]
requirements: [spider]
version: "1.0.0"
---
# Spider

Spider tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `spider.spider` | Spider Web Crawler & Scraper | ✅ | Spider API for web crawling and scraping. |

All 1 tools are implemented.

## Credentials

`SPIDER_API_KEY`, an `api_key` argument on the call, or a `spider_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
