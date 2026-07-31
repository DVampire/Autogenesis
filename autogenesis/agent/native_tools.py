"""Native tool-calling assembly — compose every capability into one flat tool list.

For the native tool-calling run loop (see ``Agent._think`` / ``Agent._dispatch``),
the model must see all of the agent's capabilities as functions in a single
``tools`` list. Each capability MANAGER owns the projection of its own entities
into native function-calling schemas (``*.function_callings(allowlist, types)``);
this module only COMPOSES those per-manager outputs and builds one routing table
(function name → owning manager) so a returned tool_call can be dispatched back.

No renaming happens here. Entity names already carry their type in the name
(``bash_tool`` / ``done_tool`` / ``general_agent`` / ``self_evolving_skill``), so the
raw name is used verbatim. ``done_tool`` is an ordinary registered tool, so it
arrives through ``tool_manager`` like any other — there is no synthetic ``done``.

Each schema is carried by a schema-only ``_SchemaTool`` (a ``Tool`` subclass) so the
existing per-provider ``serialize_tools`` — which reads ``tool.function_calling`` —
work unchanged. The shim is never executed; the run loop routes tool_calls back to
the real manager by name via the routing table.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from autogenesis.tool.types import Tool

# Routing table value: a tuple describing how to dispatch a tool_call by name:
#   ("tool", name) | ("skill", name) | ("connector", name, action)
#   | ("environment", name, action) | ("env", action) | ("agent", name)
#   | ("workflow", name)
Route = Tuple[Any, ...]


class _SchemaTool(Tool):
    """Schema-only shim carrying one capability's ``function_calling`` for the model."""

    async def __call__(self, **kwargs):  # pragma: no cover - never invoked
        raise RuntimeError("schema-only tool shim is not directly callable")


def _fc(name: str, description: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Build a canonical OpenAI function-calling dict (used for env actions)."""
    return {"type": "function", "function": {"name": name, "description": description or name, "parameters": parameters}}


def _shim(fc: Dict[str, Any]) -> _SchemaTool:
    """Wrap one function-calling dict in a schema-only ``_SchemaTool`` so serialization
    can read ``tool.function_calling`` uniformly; the shim itself is never executed."""
    fn = fc.get("function", {})
    return _SchemaTool(name=fn.get("name", ""), description=fn.get("description", ""), function_calling=fc)


async def assemble_native_tools(
    agent: Any, ctx: Any, *, include_agents: bool = False
) -> Tuple[List[_SchemaTool], Dict[str, Route]]:
    """Compose the agent's capabilities into (tools, routing).

    ``tools`` is a flat list of ``_SchemaTool`` to pass as ``input["tools"]``.
    ``routing`` maps each function name to its dispatch descriptor (see ``Route``).

    Every per-entity schema comes from that entity's OWN manager
    (``*.function_callings``); this function only concatenates them and keys the
    routing table by name. ``include_agents=True`` also projects every registered
    sub-agent (except the caller) as a callable — used by MetaAgent, which dispatches
    agents; ordinary sub-agents leave it off.
    """
    from autogenesis.tool.server import tool_manager
    from autogenesis.skill.server import skill_manager
    from autogenesis.connector.server import connector_manager
    from autogenesis.environment.server import environment_manager

    extra = getattr(ctx, "extra", None) or {}
    pairs: List[Tuple[Dict[str, Any], Route]] = []

    # tools (done_tool arrives here like any other tool)
    pairs += await tool_manager.function_callings(extra.get("tool_allowlist"))

    # skills — honor this agent's allowed skill types (worker vs orchestrator)
    types = list(agent._allowed_skill_types()) if hasattr(agent, "_allowed_skill_types") else None
    pairs += await skill_manager.function_callings(extra.get("skill_allowlist"), types=types)

    # connector actions
    pairs += await connector_manager.function_callings(extra.get("connector_allowlist"))

    # selected environment actions; names are namespace-qualified to avoid collisions.
    pairs += await environment_manager.function_callings(extra.get("environment_allowlist"))

    # environment actions — hook, default none (env-bound agents override)
    if hasattr(agent, "_native_env_tools"):
        try:
            for ns, params, desc, route in await agent._native_env_tools(ctx):
                pairs.append((_fc(ns, desc, params), route))
        except Exception:
            pass

    # Sub-agents are MetaAgent-only. Workflow projection is a separate seam because
    # a read-only Workflow evaluator must execute the target without gaining access
    # to arbitrary sub-agent delegation.
    if include_agents:
        from autogenesis.agent.server import agent_manager
        pairs += await agent_manager.function_callings(
            extra.get("agent_allowlist"), exclude=getattr(agent, "name", None)
        )

    include_workflows = include_agents or (
        hasattr(agent, "_include_workflows") and agent._include_workflows()
    ) or bool(extra.get("workflow_allowlist"))  # a canvas "Tool Mode" mount opts in explicitly
    if include_workflows:
        from autogenesis.workflow import workflow_manager
        pairs += await workflow_manager.function_callings(extra.get("workflow_allowlist"))

    tools = [_shim(fc) for fc, _ in pairs]
    routing = {fc["function"]["name"]: route for fc, route in pairs}
    return tools, routing


__all__ = ["assemble_native_tools", "_SchemaTool"]
