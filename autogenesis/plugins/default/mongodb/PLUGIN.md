---
id: mongodb
name: MongoDB Atlas
category: data
type: vectorstore
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [OPENAI_API_KEY]
requirements: [langchain_mongodb, langchain_openai, pymongo]
version: "1.0.0"
---
# MongoDB Atlas

MongoDB Atlas tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `mongodb.mongodb_atlas` | MongoDB Atlas | ✅ | MongoDB Atlas Vector Store with search capabilities |

All 1 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `mongodb_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
