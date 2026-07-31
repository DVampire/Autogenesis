---
id: supabase
name: Supabase
category: data
type: vectorstore
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [OPENAI_API_KEY]
requirements: [langchain_community, langchain_openai, supabase]
version: "1.0.0"
---
# Supabase

Supabase tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `supabase.supabase` | Supabase | ✅ | Supabase Vector Store with search capabilities |

All 1 tools are implemented.

## Credentials

`OPENAI_API_KEY`, an `api_key` argument on the call, or a `supabase_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
