"""Command types — the pluggable control layer.

A *command* is a named operation the human (or MetaAgent) triggers with a `/name`
syntax. Unlike a tool (which the model calls mid-reasoning), commands run at the
session's control plane, *before* the agent loop:

- ``CONTROL`` commands run deterministically and never touch the model — they operate
  on the framework itself (list the registry, checkpoint versions, roll back, …). Same
  result every time; this is the stable control surface over a self-evolving system.
- ``SKILL`` commands expand into a task and dispatch it to an agent, so they *do* go
  through the model — a human-facing shortcut for a packaged workflow (e.g. ``/evolve``).

Each command is one file + one class under ``default/``, registered via
``@COMMAND.register_module``, mirroring how tools/agents are defined.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.session import BaseContext
from autogenesis.response.types import Response, ResponseType


class CommandType(str, Enum):
    """How a command executes."""
    CONTROL = "control"   # deterministic, runs locally, never touches the model
    SKILL = "skill"       # expands into a task and dispatches it to an agent (goes through the model)


class CommandContext(BaseContext):
    """Context passed into command dispatch and individual command instances."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default="", description="Unique identifier for this command invocation.")
    name: str = Field(default="", description="Name of the command being invoked.")
    raw: str = Field(default="", description="The full raw input line, e.g. '/rollback tool foo 1.2'.")
    workspace_root: Optional[str] = Field(default=None, description="Working directory available to the command.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this context.")


class Command(BaseModel):
    """Base class for all commands.

    Subclasses set ``name`` / ``description`` / ``type`` / ``usage`` and implement
    ``__call__(args, ctx) -> Response``.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="Command name, invoked as '/<name>'.")
    description: str = Field(description="One-line description of what the command does.")
    type: CommandType = Field(default=CommandType.CONTROL, description="control (deterministic) or skill (routes to an agent).")
    usage: str = Field(default="", description="Usage hint, e.g. '/rollback <type> <name> <version>'.")
    permission_mode: str = Field(default="workspace_write", description="read_only / workspace_write / danger_full_access")

    async def __call__(self, args: List[str], ctx: Optional[CommandContext] = None) -> Response:
        """Run the command. ``args`` is the whitespace-split tail after the command name."""
        raise NotImplementedError("All commands must implement __call__")

    # Convenience for building results with the right ResponseType.
    def ok(self, message: str, data: Optional[Dict[str, Any]] = None) -> Response:
        return Response(type=ResponseType.COMMAND, success=True, message=message, data=data)

    def fail(self, message: str, data: Optional[Dict[str, Any]] = None) -> Response:
        return Response(type=ResponseType.COMMAND, success=False, message=message, data=data)


class SkillCommand(Command):
    """Base for SKILL-type commands — thin wrapper that dispatches a task to an agent."""
    type: CommandType = Field(default=CommandType.SKILL)
    target_agent: str = Field(default="", description="Name of the agent this command dispatches to.")

    async def dispatch_agent(self, task: str, ctx: Optional[CommandContext] = None) -> Response:
        """Send ``task`` to ``target_agent`` via the agent manager and return its Response."""
        from autogenesis.agent.server import agent_manager  # lazy import to avoid import cycles
        # Preserve the caller's session roots so tools invoked by the agent retain
        # the same filesystem boundary as the command that launched it.
        result = await agent_manager(self.target_agent, input={"task": task}, ctx=ctx)
        if isinstance(result, Response):
            return result
        return self.ok(f"Dispatched to {self.target_agent}.", data={"result": result})


__all__ = [
    "CommandType",
    "Command",
    "SkillCommand",
    "CommandContext",
]
