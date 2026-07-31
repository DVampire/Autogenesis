---
id: icosacomputing
name: Icosa
category: agent
type: tool
icon: resources/icon.svg
tools: 1
implemented: 1
credentials: [ICOSA_API_KEY]
requirements: [httpx]
version: "1.0.0"
---
# Icosa

Icosa tools.

## Tools

| id | name | status | what it does |
|----|------|--------|--------------|
| `icosacomputing.combinatorial_reasoner` | Combinatorial Reasoner | ✅ | Uses Combinatorial Optimization to construct an optimal prompt with embedded reasons. Sign up here:\\\\nhttps://forms.gle/oWNv2NKjBNaqqvCx6 |

All 1 tools are implemented.

## Credentials

`ICOSA_API_KEY`, an `api_key` argument on the call, or a `icosacomputing_plugin` block in the config. Resolved once by the plugin — the tools never look it up themselves.
