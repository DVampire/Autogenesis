---
name: agent
description: "Defines executable agents and their lifecycle. `Agent` provides the event-driven run loop; `ProceduralAgent` supports deterministic procedures; `AgentManagerServer` exposes agents to callers and multi-agent orchestrators."
version: 1.0.0
type: module
category: agent
requirements: []
metadata: {}
---
# Agent

Defines executable agents and their lifecycle. `Agent` provides the event-driven run loop;
`ProceduralAgent` supports deterministic procedures; `AgentManagerServer` exposes agents
to callers and multi-agent orchestrators.

| Path | Responsibility |
|---|---|
| `types.py` | Agent contracts, contexts, execution loop, and dispatch behavior |
| `context.py` | Registration, construction, versions, and instance lifecycle |
| `server.py` | Stable manager API, execution, and capability schemas |
| `native_tools.py` | Compose callable capabilities and their dispatch routes |
| `actor/`, `generator/`, `evaluator/`, `optimizer/` | Built-in agent roles |

Agent owns single-agent behavior. Cross-agent scheduling belongs to Runtime, Protocol, and
Workflow rather than to an Agent subtype.
