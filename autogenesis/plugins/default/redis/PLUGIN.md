---
id: redis
name: Redis
category: data
type: vectorstore
tools: 2
implemented: 2
credentials: [OPENAI_API_KEY]
requirements: [langchain_community, langchain_openai]
version: "1.0.0"
---
# Redis

Redis tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `redis.redis` | Redis | ✅ | Implementation of Vector Store using Redis |
| `redis.redis_chat` | Redis Chat Memory | ✅ | Retrieves and store chat messages from Redis. |

All 2 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `redis_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
