import asyncio
from typing import Any
from unittest.mock import patch

from pydantic import Field

from autogenesis.agent.types import (
    AgentConfig,
    AgentContext,
    AgentType,
    ProceduralAgent,
)
from autogenesis.response import Response, ResponseType
from autogenesis.runtime import runtime_manager


class EchoProcedure(ProceduralAgent):
    name: str = Field(default="echo_procedure")
    description: str = Field(default="Deterministic test procedure")
    metadata: dict[str, Any] = Field(default_factory=dict)

    async def run_procedure(self, task, files, ctx, **kwargs):
        return Response(
            type=ResponseType.AGENT,
            success=True,
            message=f"{task}:{ctx.workspace_root}:{kwargs.get('suffix', '')}",
        )


class FakeHooks:
    def __init__(self):
        self.events = []

    async def __call__(self, name, input, ctx):
        self.events.append((name, input["event"], input["agent_type"]))


def test_legacy_agent_type_value_migrates_to_procedural() -> None:
    assert AgentType("workflow") is AgentType.PROCEDURAL


def test_agent_config_round_trips_explicit_type() -> None:
    config = AgentConfig(
        name="procedure", description="test", agent_type=AgentType.PROCEDURAL,
    )
    restored = AgentConfig.model_validate(config.model_dump())
    assert restored.agent_type is AgentType.PROCEDURAL


def test_procedural_agent_uses_same_direct_and_runtime_path(tmp_path) -> None:
    async def check() -> None:
        hooks = FakeHooks()
        agent = EchoProcedure(base_dir=str(tmp_path))
        ctx = AgentContext(id="direct", workspace_root=str(tmp_path))
        with patch("autogenesis.hook.server.hook_manager", hooks):
            direct = await agent(task="direct", ctx=ctx, suffix="ok")
            delegated = await runtime_manager.invoke(
                agent, task="delegated", ctx=ctx, suffix="ok"
            )
        assert direct.success and direct.message.endswith(":ok")
        assert delegated.success and delegated.message.startswith("delegated:")
        assert len(hooks.events) == 12  # start/stop × three hooks × two runs
        assert all(event[2] == "procedural" for event in hooks.events)
        assert runtime_manager.list() == []

    asyncio.run(check())
