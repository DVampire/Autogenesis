from types import SimpleNamespace

import pytest

from autogenesis.capability import CapabilitySchema
from autogenesis.agent.context import AgentContextManager
from autogenesis.agent.server import AgentManagerServer
from autogenesis.connector.server import ConnectorManagerServer
from autogenesis.environment.server import EnvironmentManagerServer
from autogenesis.skill.server import SkillManagerServer
from autogenesis.tool.server import ToolManagerServer
from autogenesis.workflow import WorkflowContextManager


class _InfoManagerMixin:
    async def get_info(self, name):
        return self._test_info

    async def list(self):
        return [self._test_info.name]


def _manager(cls, info):
    derived = type(f"Test{cls.__name__}", (_InfoManagerMixin, cls), {})
    instance = derived()
    object.__setattr__(instance, "_test_info", info)
    return instance


def _assert_formats(json_schema, markdown, expected_name):
    assert json_schema["function"]["name"] == expected_name
    assert json_schema["function"]["parameters"]["type"] == "object"
    assert markdown.startswith(f"## `{expected_name}`")
    assert "### Parameters" in markdown


@pytest.mark.asyncio
async def test_all_callable_managers_expose_json_and_markdown_schema(tmp_path):
    parameters = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }

    tool = _manager(ToolManagerServer, SimpleNamespace(
        name="sample_tool", description="tool", type=None,
        function_calling={"type": "function", "function": {
            "name": "sample_tool", "description": "tool", "parameters": parameters,
        }},
    ))
    agent = _manager(AgentManagerServer, SimpleNamespace(name="sample_agent", description="agent"))
    skill = _manager(SkillManagerServer, SimpleNamespace(
        name="sample_skill", description="skill", type="worker", type_tags=["worker"],
        input_schema=parameters,
    ))
    connector = _manager(ConnectorManagerServer, SimpleNamespace(
        name="sample_connector", description="connector", actions=["query"],
        action_schemas={"query": parameters},
    ))
    action = SimpleNamespace(description="environment action", function_calling={
        "type": "function", "function": {"parameters": parameters},
    }, args_schema=None)
    environment = _manager(EnvironmentManagerServer, SimpleNamespace(
        name="sample_environment", actions={"act": action},
    ))

    checks = [
        (tool, "sample_tool", None, "sample_tool"),
        (agent, "sample_agent", None, "sample_agent"),
        (skill, "sample_skill", None, "sample_skill"),
        (connector, "sample_connector", "query", "sample_connector__query"),
        (environment, "sample_environment", "act", "sample_environment__act"),
    ]
    for manager, name, action_name, function_name in checks:
        json_schema = await manager.get_schema(name, action=action_name, format="json")
        markdown = await manager.get_schema(name, action=action_name, format="md")
        _assert_formats(json_schema, markdown, function_name)
        projected = await manager.function_callings()
        assert projected[0][0] == json_schema

    workflow = WorkflowContextManager(
        builtin_dir=tmp_path / "missing", evaluation_path=tmp_path / "evaluations.json",
    )
    workflow.register("""
    <workflow name="complex_flow" description="complex">
      <inputs><input name="files" required="true"><schema for="files">
        {"type":"array","items":{"type":"string"},"minItems":1}
      </schema></inputs>
      <flow><agent name="general_agent" /></flow>
    </workflow>
    """)
    json_schema = await workflow.get_schema("complex_flow", format="json")
    markdown = await workflow.get_schema("complex_flow", format="md")
    _assert_formats(json_schema, markdown, "workflow__complex_flow")
    assert json_schema["function"]["parameters"]["properties"]["files"]["items"] == {"type": "string"}


def test_capability_schema_rejects_invalid_required_and_strictness():
    with pytest.raises(ValueError, match="required"):
        CapabilitySchema(name="bad", parameters={
            "type": "object", "properties": {}, "required": ["missing"],
            "additionalProperties": False,
        })
    with pytest.raises(ValueError, match="additionalProperties"):
        CapabilitySchema(name="bad", strict=True, parameters={"type": "object", "properties": {}})


def test_agent_manager_supplies_workspace_without_mutating_caller_config(tmp_path):
    class SampleAgent:
        model_fields = {"name": SimpleNamespace(default="sample_agent")}

    manager = AgentContextManager(base_dir=str(tmp_path))
    original = {"model_name": "test-model"}
    prepared = manager._prepare_instance_config(SampleAgent, original)

    assert original == {"model_name": "test-model"}
    assert prepared["base_dir"] == str(tmp_path / "sample_agent")
    assert manager._prepare_instance_config(
        SampleAgent, {"base_dir": "/explicit"},
    )["base_dir"] == "/explicit"
