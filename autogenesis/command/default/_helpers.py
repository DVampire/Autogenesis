"""Shared helpers for commands — map a capability type to its manager (lazy import)."""

# Every versioned capability type (all have list/get_info/copy/restore/unregister).
KNOWN_TYPES = ["tool", "agent", "skill", "connector", "environment", "prompt"]

# Types with generate/evaluate/optimize agents behind them (SKILL commands dispatch to these).
# 'prompt' is excluded — it has no *_generate_agent / *_evaluate_agent.
AGENT_BACKED_TYPES = ["tool", "agent", "skill", "connector", "environment"]


def get_manager(type_name: str):
    """Return the global manager for a capability type, or None if unknown.

    Lazy imports keep the command package free of import cycles with the managers.
    """
    if type_name == "tool":
        from autogenesis.tool.server import tool_manager
        return tool_manager
    if type_name == "agent":
        from autogenesis.agent.server import agent_manager
        return agent_manager
    if type_name == "skill":
        from autogenesis.skill.server import skill_manager
        return skill_manager
    if type_name == "connector":
        from autogenesis.connector.server import connector_manager
        return connector_manager
    if type_name == "environment":
        from autogenesis.environment.server import environment_manager
        return environment_manager
    if type_name == "prompt":
        from autogenesis.prompt.server import prompt_manager
        return prompt_manager
    return None
