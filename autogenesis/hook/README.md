---
name: hook
description: "Provides lifecycle interception points for tracing, compaction, registration, promotion, and other cross-cutting behavior."
version: 1.0.0
type: module
category: hook
requirements: []
metadata: {}
---
# Hook

Provides lifecycle interception points for tracing, compaction, registration, promotion,
and other cross-cutting behavior.

| File | Responsibility |
|---|---|
| `types.py` | Events, decisions, contexts, and hook contracts |
| `context.py` | Hook configuration and registration state |
| `server.py` | Ordered hook dispatch facade |
| `promotion.py` | Registration/promotion helpers |
| `default/` | Built-in hooks |

Built-in hooks (`default/`):

| Hook | Responsibility |
|---|---|
| `trace_hook` | Emits structured TraceEvents for every agent lifecycle event |
| `trajectory_hook` | Builds step-level training trajectories from lifecycle events |
| `memory_hook` | Feeds lifecycle events into the memory systems |
| `constraint_hook` | Enforces per-step resource budgets |
| `no_progress_hook` | Blocks unchanged successful Agent action batches before execution |
| `snapshot_hook` | Saves each step's rendered messages as HTML |
| `compact` | Generic summariser for compressing record lists |
| `tool_registration_hook` | Registers a generated tool file |
| `skill_registration_hook` | Registers a generated skill directory |
| `agent_registration_hook` | Registers a generated agent class (and prompt) |
| `environment_registration_hook` | Registers a generated environment class |
| `connector_registration_hook` | Registers a generated connector directory |
| `workflow_registration_hook` | Validates and registers generated Workflow HTML |

Hooks observe or gate lifecycle events; core business logic stays in the owning module.
The no-progress hook is stateless: evidence and escalation counters are stored on each
Agent run, preventing concurrent sessions from affecting one another. It is wired into the
base `Agent._prepare_round`, so the guard applies to every agent uniformly rather than
being opted into per agent.
