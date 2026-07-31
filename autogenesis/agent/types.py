"""Agent Context Protocol (agent manager) Types

Core type definitions for the Agent Context Protocol and common Agent
abstractions, aligned with the design of `autogenesis.tool.types`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime
from enum import Enum
from functools import lru_cache
from typing import Any, Dict, List, Optional, Type


from pydantic import BaseModel, ConfigDict, Field

from autogenesis.config import config
from autogenesis.dynamic import dynamic_manager
from autogenesis.logger import logger
from autogenesis.memory import memory_manager
from autogenesis.message import Message
from autogenesis.prompt import prompt_manager
from autogenesis.tool import tool_manager
from autogenesis.skill import skill_manager
from autogenesis.connector import connector_manager
from autogenesis.constraint import (
    constraint_manager,
    render_status_text,
    StepConstraint,
    TokenConstraint,
    WallTimeConstraint,
)
from autogenesis.session import BaseContext
from autogenesis.constraint import Constraint
from autogenesis.registry import CONSTRAINT
from autogenesis.response import Response
from autogenesis.utils import (
    assemble_workspace_path,
    get_extension_root,
    get_package_root,
)

# Tools that mutate the framework / deliverables. A read_only agent (e.g. an evaluator)
# is refused these at dispatch time — a coarse guard so a "read-only" agent cannot edit
# source, commit, deploy, or roll back evolution. Read/inspect/probe tools (and calling
# the target under test) stay allowed so evaluators still work. Op-level enforcement
# (allow reads, deny writes per call) is future work.
_READ_ONLY_DENIED_TOOLS = {
    "write_file_tool", "edit_file_tool", "git_tool", "deploy_tool", "evolution_tool",
}


@lru_cache(maxsize=1)
def _runtime_facts() -> Dict[str, str]:
    """Describe the interpreter shell commands will actually run under.

    ``bash_tool`` prepends this interpreter's ``bin`` directory to PATH, so
    ``python``/``pip`` in a command resolve here.  Telling the agent up front
    saves it from spending steps probing the environment (``conda env list``,
    ``which python``, import checks) on every run.  Constant per process.
    """
    import platform
    import sys

    prefix = sys.prefix
    env_name = os.environ.get("CONDA_DEFAULT_ENV") or os.path.basename(prefix)
    return {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "python_env": env_name,
        "platform": f"{platform.system()} {platform.machine()}",
    }


class AgentContext(BaseContext):
    """Context passed into agent manager and individual agent instances."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for this agent invocation.")
    name: Optional[str] = Field(default=None, description="Human-readable label for this agent invocation.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input payload passed to the agent.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this agent context.")
    parent_session_id: Optional[str] = Field(default=None, description="Name of the parent MetaAgent, used by trace and escalation hooks.")
    subtask_id: Optional[str] = Field(default=None, description="ID of the subtask record in the parent MetaAgent's plan.")

class InputArgs(BaseModel):
    task: str = Field(description="The task to complete.")
    files: Optional[List[str]] = Field(default=None, description="The files to attach to the task.")

class AgentType(str, Enum):
    """Execution contract used by an agent."""

    TOOL_CALLING = "tool_calling"
    PROCEDURAL = "procedural"

    @classmethod
    def _missing_(cls, value):
        """Map legacy agent-type strings to a valid member (Enum lookup fallback).

        Preserves backward compatibility for configs written under the old informal
        ``"workflow"`` name, now folded into ``PROCEDURAL``. Returns ``None`` for any
        other unknown value so the Enum raises the usual ``ValueError``.
        """
        # Backward compatibility for configs created under the old informal name.
        if value == "workflow":
            return cls.PROCEDURAL
        return None


class AgentConfig(BaseModel):
    """Agent configuration for registration, similar to `ToolConfig`."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="The name of the agent")
    description: str = Field(description="The description of the agent")
    version: str = Field(default="1.0.0", description="Version of the agent")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    enable_evolving: bool = Field(default=False, description="Whether the agent may be evolved (self-optimized)")
    permission_mode: str = Field(default="workspace_write", description="Permission mode: read_only / workspace_write / danger_full_access")
    agent_type: AgentType = Field(default=AgentType.TOOL_CALLING, description="Agent execution contract")

    cls: Optional[Any] = None
    config: Optional[Dict[str, Any]] = Field(default_factory=dict,description="The initialization configuration of the agent",)
    instance: Optional[Any] = None
    
    code: Optional[str] = Field(default=None, description="Source code for dynamically generated agent classes (used when cls cannot be imported from a module)")

    function_calling: Optional[Dict[str, Any]] = Field(
        default=None, description="Default function calling representation"
    )
    text: Optional[str] = Field(
        default=None, description="Default text representation of the agent"
    )
    args_schema: Optional[Type[BaseModel]] = Field(
        default=None, description="Default args schema (BaseModel type)"
    )

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Dump the model to a dictionary, recursively serializing nested Pydantic models."""
        
        result = {
            "name": self.name,
            "description": self.description,
            "metadata": self.metadata,
            "version": self.version,
            "enable_evolving": self.enable_evolving,
            
            "permission_mode": self.permission_mode,
            "agent_type": self.agent_type.value,

            "cls": dynamic_manager.get_class_string(self.cls) if self.cls else None,
            "config": self.config,
            "instance": None,
            "code": self.code,

            "function_calling": self.function_calling,
            "text": self.text,
            "args_schema": dynamic_manager.serialize_args_schema(self.args_schema) if self.args_schema else None,
        }

        return result
    
    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> 'AgentConfig':
        """Validate the model from a dictionary."""
        name = data.get("name")
        description = data.get("description")
        metadata = data.get("metadata", {})
        version = data.get("version")
        enable_evolving = data.get("enable_evolving", False)
        permission_mode = data.get("permission_mode", "workspace_write")
        agent_type = AgentType(data.get("agent_type", AgentType.TOOL_CALLING))

        cls_ = None
        code = data.get("code")
        if code:
            class_name = dynamic_manager.extract_class_name_from_code(code)
            if class_name:
                try:
                    cls_ = dynamic_manager.load_class(
                        code, 
                        class_name=class_name,
                        base_class=Agent,
                        context="agent"
                    )
                except Exception:
                    cls_ = None
            else:
                cls_ = None
        else:
            cls_ = None
            
        config = data.get("config", {})
        instance = data.get("instance", None)

        function_calling = data.get("function_calling")
        text = data.get("text")
        _raw_schema = data.get("args_schema")
        args_schema = dynamic_manager.deserialize_args_schema(_raw_schema) if _raw_schema is not None else None
        
        return cls(
            name=name,
            description=description,
            metadata=metadata,
            version=version,
            enable_evolving=enable_evolving,
            permission_mode=permission_mode,
            agent_type=agent_type,
            cls=cls_,
            config=config,
            instance=instance,
            function_calling=function_calling,
            text=text,
            args_schema=args_schema,
        )

    def __str__(self) -> str:
        return (
            f"AgentConfig(name={self.name}, "
            f"description={self.description}, "
            f"enable_evolving={self.enable_evolving})"
        )

    def __repr__(self) -> str:
        return self.__str__()


# ---------------------------------------------------------------------------
# Event-driven run: one unified loop for every agent (leaf actors AND orchestrators)
# ---------------------------------------------------------------------------
# The runtime pump drives every agent the same way: on_start kicks the first turn and
# returns None; each turn (_advance) runs _think then dispatches the batch as background
# tasks that post _ActionDone back to THIS agent's own inbox; on_event collects them and,
# when the round drains, advances to the next turn or concludes. round == turn.
#
# An orchestrator (MetaAgent) is not special: it just has ``agent`` capabilities in its
# roster, so some of its dispatched actions are sub-agents. A sub-agent that blocks
# escalates to its parent via the escalation channel → the parent's inbox → on_event — which
# works precisely because every agent (parent included) runs this same event-driven loop.

from autogenesis.runtime.types import BaseMessage as _BaseMessage
from autogenesis.protocol.types import ControlMessage as _ControlMessage, QueryMessage as _QueryMessage


class _ActionDone(_BaseMessage):
    """One dispatched action finished — posted back to the agent's OWN inbox so the
    event-driven round loop can collect it. The agent is both dispatcher and receiver;
    its pump drains these exactly like any other message."""

    call_id: str = ""
    name: str = ""
    output: Optional[str] = None   # the action's observable output (a sub-agent's message,
                                   # a tool's message …) — what an orchestrator shows/inspects
    result: Optional[str] = None   # the completion result (only meaningful when is_done)
    error: Optional[str] = None
    is_done: bool = False          # this call was done_tool (the completion signal)
    reasoning: Optional[str] = None


class _AgentRun:
    """Mutable per-run state for the event-driven loop (one per active runtime ref)."""

    def __init__(self, task, files, ctx, ref, task_id, extra_kwargs):
        self.task = task
        self.files = files
        self.ctx = ctx
        self.ref = ref
        self.task_id = task_id
        self.extra_kwargs = extra_kwargs or {}
        self.step = 0
        self.action_errors: List[str] = []
        # the round currently in flight (this turn's batch)
        self.round_step = 0
        self.decision: Optional[Dict[str, Any]] = None
        self.messages: Any = None
        self.outstanding: set = set()
        self.round_tasks: Dict[str, asyncio.Task] = {}
        self.step_plan: List[Dict[str, Any]] = []
        self.round_errors: List[str] = []
        # Every finished action of the current round: {name, result, error, is_done}.
        # Leaf agents ignore this (observations flow through memory); orchestrators read
        # it to build their "what changed" prompt and to inspect sub-agent verdicts.
        self.round_outcomes: List[Dict[str, Any]] = []
        self.round_done = False
        self.round_result: Optional[str] = None
        self.round_reasoning: Optional[str] = None
        # final outcome
        self.done = False
        self.result: Optional[str] = None
        self.reasoning: Optional[str] = None
        self.stopped_by_constraint = False
        self.paused = False   # control channel: when True, don't start the next turn
        # MetaAgent uses these fields to detect an unchanged action batch.  They live on
        # the run (not the Agent singleton) so concurrent sessions never share state.
        self.previous_action_signature: Optional[str] = None
        self.repeated_action_rounds = 0
        # Successful action evidence used by the shared no-progress guard.  State is
        # run-local so parallel agents/sessions never suppress one another.
        self.action_evidence: Dict[str, Dict[str, Any]] = {}
        self.no_progress_rounds = 0


class Agent(BaseModel):
    """Base class for all agents, mirroring the design of `Tool`."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="The name of the agent.")
    description: str = Field(description="The description of the agent.")
    metadata: Dict[str, Any] = Field(description="The metadata of the agent.")
    version: str = Field(default="1.0.0", description="Version of the agent")
    enable_evolving: bool = Field(default=False, description="Whether the agent may be evolved (self-optimized)")
    permission_mode: str = Field(default="workspace_write", description="Permission mode: read_only / workspace_write / danger_full_access")
    agent_type: AgentType = Field(default=AgentType.TOOL_CALLING, description="Agent execution contract")

    def __init__(
        self,
        base_dir: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,
        prompt_name: Optional[str] = None,
        memory_name: Optional[str] = None,
        max_actions: int = 10,
        max_step: int = 20,
        max_token: Optional[int] = None,
        timeout: Optional[float] = None,
        review_steps: int = 5,
        enable_evolving: bool = False,
        use_memory: bool = True,
        constraints: Optional[List[Constraint]] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)

        # Set default values
        self.name = name or self.name
        self.description = description or self.description
        self.metadata = metadata or self.metadata
        self.enable_evolving = enable_evolving

        # Set working directory
        self.base_dir = base_dir

        # Set prompt name and modules
        self.prompt_name = prompt_name
        self.memory_name = memory_name
        self.use_memory = use_memory
        self.model_name = model_name

        # Setup steps
        self.max_step = max_step if max_step > 0 else int(1e8)
        self.max_actions = max_actions

        self.review_steps = review_steps

        # Resource budgets — fed into constraint checks as per-call overrides,
        # so agent-level limits take precedence over constraint defaults.
        self.max_token = max_token
        self.timeout = timeout

        # Runtime constraints — accept Constraint instances or mmengine-style dicts
        # e.g. {"type": "StepConstraint", "max_step": 20}
        # Registration with the constraint manager happens in `initialize` (async).
        self.constraints: List[Constraint] = self._build_constraints(constraints)

        # Auto-attach constraints for explicitly requested budgets
        # StepConstraint only DISPLAYS the step budget: the loop (`while step < max_step`)
        # stops at the same value first, so it never blocks early — no off-by-one kill.
        if max_step and max_step > 0 and not any(isinstance(c, StepConstraint) for c in self.constraints):
            self.constraints.append(StepConstraint(max_step=max_step))
        if max_token is not None and not any(isinstance(c, TokenConstraint) for c in self.constraints):
            self.constraints.append(TokenConstraint(max_token=max_token))
        if timeout is not None and not any(isinstance(c, WallTimeConstraint) for c in self.constraints):
            self.constraints.append(WallTimeConstraint(max_second=timeout))
        # Tokens consumed by the previous step, fed into the next constraint check (keyed by task_id)
        self._pending_step_tokens: Dict[str, int] = {}
        # Per-run event-driven state, keyed by runtime ref name (one entry per active run).
        self._runs: Dict[str, "_AgentRun"] = {}

    @staticmethod
    def _build_constraints(raw: Optional[List]) -> List[Constraint]:
        """Normalize a mixed constraint spec into concrete ``Constraint`` instances.

        Accepts already-built ``Constraint`` objects (kept as-is) and dict specs (built
        via the ``CONSTRAINT`` registry), so an agent can be configured with either form.

        Raises:
            TypeError: If an item is neither a ``Constraint`` nor a dict.
        """
        if not raw:
            return []
        result = []
        for item in raw:
            if isinstance(item, Constraint):
                result.append(item)
            elif isinstance(item, dict):
                result.append(CONSTRAINT.build(item))
            else:
                raise TypeError(f"Unsupported constraint type: {type(item)}")
        return result

    async def initialize(self) -> None:
        """Initialize the agent."""
        logger.info(f"| 📁 Agent working directory: {self.base_dir}")

        # Register runtime constraints with the global constraint manager
        for c in self.constraints:
            await constraint_manager.register(c)

    def __str__(self) -> str:
        return f"Agent(name={self.name}, model={self.model_name}, prompt_name={self.prompt_name})"

    def __repr__(self) -> str:
        return self.__str__()

    async def _get_agent_context(self,
                                 task: str,
                                 step_number: int = 0,
                                 ctx: Optional[AgentContext] = None,
                                 **kwargs) -> Dict[str, Any]:
        """Get the agent context."""
        time_str = datetime.now().isoformat()
        step_info_body = (
            f"Step {step_number + 1} of {self.max_step} max possible steps\n"
            f"Current date and time: {time_str}"
        )

        # Clean per-section bodies (no "### " prefix) — each is rendered as its own
        # agent_context sub-module (see code_agent.html and the agent prompts).
        memory_body = "[Memory is disabled.]"
        if self.use_memory and self.memory_name:
            try:
                memory_info = await memory_manager.get_info(self.memory_name)
                if memory_info and memory_info.instance is not None:
                    session_id = ctx.id if ctx else ""
                    mem_text = await memory_info.instance.get(
                        session_id=session_id,
                        short_term_n=self.review_steps,
                    )
                    memory_body = mem_text if mem_text else "[No memory recorded yet.]"
            except Exception:
                pass

        # Resource budgets collected from the previous step's constraint checks
        constraint_status = kwargs.get("constraint_status") or []
        constraint_text = render_status_text(constraint_status) if constraint_status else "[No active budget.]"

        # Errors from the previous step (shown only when the last step failed) — a
        # universal agent-context sub-module, provided here so subclasses don't each
        # re-derive it. Same for the live workspace snapshot below.
        action_errors = kwargs.get("action_errors") or []
        errors_body = "\n".join(f"- {e}" for e in action_errors) if action_errors else ""

        # Running todo — injected every step (like memory) when the agent uses todo_tool,
        # so its plan/checklist is always visible without spending a `show` action.
        todo_body = ""
        if ctx is not None:
            try:
                todo_info = await tool_manager.get_info("todo_tool")
                if todo_info and todo_info.instance is not None:
                    todo_body = await todo_info.instance.content(ctx.id)
            except Exception:
                todo_body = ""

        return {
            "step_info": step_info_body,
            "memory_context": memory_body,
            "constraint_text": constraint_text,
            "workspace": self._workspace_snapshot(ctx),
            "errors": errors_body,
            "todo": todo_body,
        }

    async def _get_tool_context(self, ctx: AgentContext, **kwargs) -> Dict[str, Any]:
        """Get the tool context.

        Honors an optional per-run allowlist in ``ctx.extra["tool_allowlist"]`` (a list
        of tool names) — used to run a "with-tool" vs "baseline" agent over the same task.
        ``None`` (default) = all loaded tools; an empty list = no tools (the baseline).
        """
        allowlist = ctx.extra.get("tool_allowlist") if (ctx is not None and getattr(ctx, "extra", None)) else None
        content = await tool_manager.get_instruction(allowlist=allowlist)
        available_tools = content if content else "[No tools loaded.]"
        tool_context = f"### Available Tools\n{available_tools}"
        return {"tool_context": tool_context, "available_tools": available_tools}

    def _allowed_skill_types(self) -> List[str]:
        """Which skill types this agent may see. Workers see 'worker' skills;
        the MetaAgent overrides this to ['orchestrator']. This is the hard
        guardrail that keeps the two skill audiences separate regardless of which
        skills a run happens to load."""
        return ["worker"]

    async def _get_skill_context(self, ctx: AgentContext, **kwargs) -> Dict[str, Any]:
        """Get the skill context from loaded skills via skill manager.

        Honors an optional per-run allowlist in ``ctx.extra["skill_allowlist"]`` (a list
        of skill names) — used by skill evaluation to run a "with-skill" vs a "baseline"
        agent over the same task. ``None`` (default) = all skills of the allowed type;
        an empty list = no skills (the baseline). Normal runs never set it, so behavior
        is unchanged.
        """
        allowlist = ctx.extra.get("skill_allowlist") if (ctx is not None and getattr(ctx, "extra", None)) else None
        skill_content = await skill_manager.get_instruction(
            allowlist=allowlist, types=self._allowed_skill_types()
        )
        available_skills = skill_content if skill_content else "[No skills loaded.]"
        skill_context = f"### Available Skills\n{available_skills}"
        return {"skill_context": skill_context, "available_skills": available_skills}

    async def _get_connector_context(self, ctx: AgentContext, **kwargs) -> Dict[str, Any]:
        """Get the connector context from loaded connectors (MCP servers) via connector manager.

        Concise by design (name/description/actions + CONNECTOR.md path). The agent
        reads a connector's CONNECTOR.md on demand for per-action argument details.

        Honors an optional per-run allowlist in ``ctx.extra["connector_allowlist"]`` —
        ``None`` (default) = all loaded connectors; an empty list = none (baseline).
        """
        allowlist = ctx.extra.get("connector_allowlist") if (ctx is not None and getattr(ctx, "extra", None)) else None
        connector_content = await connector_manager.get_instruction(allowlist=allowlist)
        available_connectors = connector_content if connector_content else "[No connectors loaded.]"
        connector_context = f"### Available Connectors\n{available_connectors}"
        return {"connector_context": connector_context, "available_connectors": available_connectors}

    async def _get_workflow_context(self, ctx: AgentContext, **kwargs) -> Dict[str, Any]:
        """Workflow discovery is opt-in; worker agents do not orchestrate workflows."""
        return {"workflow_context": "", "available_workflows": ""}

    async def _resolve_workspace_root(self, ctx: AgentContext, **kwargs) -> str:
        """Resolve the workspace_root surfaced in the prompt's `{{ workspace_root }}` slot.

        Prefer ctx.workspace_root (injected by MetaAgent for sub-agents) over
        self.base_dir so all agents in a MetaAgent run share the same directory.
        Under Model X the whole agent runs inside the project container, so this
        path is already the in-container working directory. When a peer sandbox is
        bound (e.g. a programbench task cleanroom), tools execute in that container,
        so surface *its* working directory (e.g. /workspace) — not the host path.
        """
        sandbox = (getattr(ctx, "extra", None) or {}).get("sandbox")
        container_ws = getattr(sandbox, "container_workspace", None) if sandbox is not None else None
        if container_ws:
            return container_ws
        return assemble_workspace_path(config.workspace_root or self.base_dir)

    def _workspace_snapshot(self, ctx: Optional[AgentContext]) -> str:
        """A live listing of the working directory's files, refreshed each step.

        Lets an agent see what's currently in its scratch directory without
        spending a tool call. Opt-in: agents that do file work expose this as a
        `workspace` sub-module from their `_get_agent_context` override.
        """
        # With a peer sandbox bound, the working directory lives in that container;
        # a synchronous host listing would show the wrong (empty host) directory, so
        # surface the container path and let the agent list it with list_dir.
        sandbox = (getattr(ctx, "extra", None) or {}).get("sandbox")
        container_ws = getattr(sandbox, "container_workspace", None) if sandbox is not None else None
        if container_ws:
            return f"{container_ws}\n  (sandboxed — use list_dir to inspect)"
        workspace_root = os.path.abspath(config.workspace_root or self.base_dir)
        try:
            entries = sorted(os.listdir(workspace_root))
            lines = [
                f"  {name}{'/' if os.path.isdir(os.path.join(workspace_root, name)) else ''}"
                for name in entries
            ]
            snapshot = "\n".join(lines) if lines else "  (empty)"
        except Exception:
            snapshot = "  (unavailable)"
        return f"{workspace_root}\n{snapshot}"

    def _task_with_input_files(self, task: str, **kwargs) -> str:
        """Append the input files the user attached to the task body.

        Input files are part of the assignment (static), so they live inside the
        `task` module rather than a separate block. Only existing paths are shown.
        """
        files = kwargs.get("files") or []
        existing = [f for f in files if os.path.exists(f)]
        if not existing:
            return task
        listing = "\n".join(f"- {f}" for f in existing)
        return f"{task}\n\n**Input files:**\n{listing}"

    async def _get_messages(self,
                            task: str,
                            ctx: AgentContext,
                            **kwargs) -> List[Message]:
        """Build system+agent messages using prompt templates and context."""

        workspace_root = await self._resolve_workspace_root(ctx=ctx, **kwargs)
        roots = getattr(ctx, "extra", {}) or {}
        extension_root = str(roots.get("extension_root") or get_extension_root())
        package_root = str(roots.get("package_root") or get_package_root())
        project_root = str(roots.get("project_root") or getattr(config, "project_root", ""))
        log_root = str(roots.get("log_root") or getattr(config, "log_root", ""))
        system_modules = dict(
            max_actions=self.max_actions,
            extension_root=extension_root,
            package_root=package_root,
            project_root=project_root,
            workspace_root=workspace_root,
            log_root=log_root,
            **_runtime_facts(),
        )
        agent_message_modules = dict(task=self._task_with_input_files(task, **kwargs))

        agent_message_modules.update(await self._get_agent_context(task, ctx=ctx, **kwargs))
        agent_message_modules.update(await self._get_tool_context(ctx=ctx))
        agent_message_modules.update(await self._get_skill_context(ctx=ctx))
        agent_message_modules.update(await self._get_connector_context(ctx=ctx))
        agent_message_modules.update(await self._get_workflow_context(ctx=ctx))
        
        response = await prompt_manager(
            name=self.prompt_name,
            input={
                "system_modules": system_modules,
                "agent_modules": agent_message_modules,
            },
        )
        if not response.success:
            raise ValueError(response.message)

        return response.data["messages"]

    async def _handle_env_action(
        self,
        action_name: str,
        action_args: Dict[str, Any],
        ctx: "AgentContext",
    ) -> Any:
        """Execute an `env`-type action. Agents bound to an environment override this.

        Implementations should raise on failure so the error reaches
        `action_errors` and is surfaced to the LLM in the next step.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support env actions"
        )

    # ------------------------------------------------------------------
    # Shared execution loop — all tool-calling agents use this
    # ------------------------------------------------------------------

    async def _constraint_check(self, task_id: str, ctx: "AgentContext"):
        """Run the per-step resource-budget check via the constraint hook, exactly once.

        The agent owns its token accounting: it pops the previous step's tokens
        and passes the per-call budget in; the hook runs the checks, blocks on a
        violation, and returns the budget snapshot.

        Returns ``(violation_reason, status_list)``:
          - ``violation_reason``: a string when a budget is exhausted (the caller
            should stop the task), else ``None``;
          - ``status_list``: the budget snapshot to render into the prompt.

        Stateful (step/token counters increment per call), so every agent calls it
        exactly once per step — at the top of the loop, before ``_get_messages`` —
        and never inside ``_think_and_act``. See the canonical loop in
        ``_think_and_act``'s docstring.
        """
        if not self.constraints:
            return None, []
        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookDecision, HookEvent
        result = await hook_manager(
            name="constraint_hook",
            input={
                "event": HookEvent.PRE_STEP,
                "agent_name": self.name,
                "task_id": task_id,
                "constraint_names": [c.name for c in self.constraints],
                "check_input": {
                    "token": self._pending_step_tokens.pop(task_id, 0),
                    "max_step": self.max_step,
                    "max_token": self.max_token,
                    "max_second": self.timeout,
                },
            },
            ctx=ctx,
        )
        if result.decision == HookDecision.BLOCK:
            for c in self.constraints:
                # Freed by the key the constraint actually counts under (ctx.id).
                # This passed task_id — a per-invocation uuid the constraint never
                # sees — so nothing was ever released and a session's budget only
                # ever went up.
                c._cleanup(ctx.id)
            self._pending_step_tokens.pop(task_id, None)
            return result.reason, []
        return None, result.constraint_status or []

    async def _think_and_act(
        self,
        messages: List[Message],
        task_id: str,
        step_number: int,
        ctx: "AgentContext",
        **kwargs,
    ) -> Dict[str, Any]:
        """One step of the think-and-act loop (native tool use): the model sees the
        agent's capabilities as native tools, emits tool_calls, and this dispatches
        each back to its owning manager. Returns done/result/reasoning/action_errors.

        Reasoning is the model's thinking/text; completion is an explicit ``done``
        tool call (never inferred from plain text — a text-only turn is nudged to
        act or call done). Tool args arrive as structured objects validated by each
        tool's schema (no JSON-string double-encoding).

        The per-step resource-budget check is the CALLER's responsibility — every
        agent runs ``_constraint_check`` BEFORE building ``messages`` (so the prompt
        reflects the current budget) and stops on a violation. The check is stateful
        (counts a step), so it must run exactly once per step and is NOT repeated
        here. Canonical loop every agent follows::

            step = 0
            action_errors = []
            while step < self.max_step:
                reason, status = await self._constraint_check(task_id, ctx)
                if reason is not None:
                    response = {"done": True, "result": reason,
                                "stopped_by_constraint": True}
                    break
                messages = await self._get_messages(
                    task, ctx=ctx, step_number=step,
                    action_errors=action_errors, constraint_status=status)
                response = await self._think_and_act(messages, task_id, step, ctx=ctx)
                step += 1
                action_errors = response.get("action_errors") or []
                if response["done"]:
                    break
        """
        # THINK: one LLM turn → a batch of tool_calls (+ routing). Pure decision.
        decision = await self._think(messages, task_id, step_number, ctx)

        # DISPATCH: run this turn's batch concurrently, each call routed to its manager.
        outcome = await self._dispatch(decision, task_id, step_number, ctx)

        # Per-step lifecycle: POST_STEP + snapshot + trajectory capture.
        await self._post_step(task_id, step_number, ctx, messages,
                              reasoning=decision["reasoning"], plan=outcome["plan"],
                              step_tokens=decision["step_tokens"], done=outcome["done"])

        return {"done": outcome["done"], "result": outcome["result"], "reasoning": outcome["reasoning"],
                "action_errors": outcome["action_errors"], "constraint_status": [], "stopped_by_constraint": False}

    async def _post_step(self, task_id, step_number, ctx, messages, *, reasoning, plan, step_tokens, done):
        """Fire the per-step POST_STEP lifecycle (memory / trace / snapshot / trajectory)
        and carry token usage forward. Shared by the blocking ``_think_and_act`` path
        (BrowserAgent) and the event-driven round loop, so a step is recorded identically
        however it was driven.
        """
        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookEvent
        await hook_manager(
            name="memory_hook",
            input={"event": HookEvent.POST_STEP, "agent_name": self.name, "step_number": step_number, "task_id": task_id, "reasoning": reasoning, "use_memory": self.use_memory, "memory_name": self.memory_name},
            ctx=ctx,
        )
        await hook_manager(
            name="trace_hook",
            input={"event": HookEvent.POST_STEP, "agent_name": self.name, "step_number": step_number, "task_id": task_id, "reasoning": reasoning},
            ctx=ctx,
        )
        await hook_manager(
            name="snapshot_hook",
            input={"event": HookEvent.POST_STEP, "agent_name": self.name, "step_number": step_number,
                   "task_id": task_id, "workspace_root": config.workspace_root,
                   "messages": messages, "reasoning": reasoning, "plan": plan},
            ctx=ctx,
        )
        await hook_manager(
            name="trajectory_hook",
            input={"event": HookEvent.POST_STEP, "agent_name": self.name, "step_number": step_number,
                   "task_id": task_id, "messages": messages, "reasoning": reasoning,
                   "plan": plan, "step_tokens": step_tokens},
            ctx=ctx,
        )
        self._pending_step_tokens[task_id] = step_tokens
        if done and self.constraints:
            for c in self.constraints:
                c._cleanup(ctx.id)  # the key it counts under; see _constraint_check
            self._pending_step_tokens.pop(task_id, None)

    # ------------------------------------------------------------------
    # The unified loop's two verbs: _think (decide) + _dispatch (act).
    # Shared verbatim by every agent — leaf actors AND the MetaAgent. The only
    # thing an orchestrator adds is a richer roster (include_agents / extra_tools)
    # and a different batch executor; the decision + per-call dispatch are identical.
    # ------------------------------------------------------------------

    async def _think(
        self,
        messages: List[Message],
        task_id: str,
        step_number: int,
        ctx: "AgentContext",
        *,
        include_agents: bool = False,
        extra_tools: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """One LLM turn (native tool use): project the agent's capabilities into a flat
        tool list + routing table, stream, and accumulate into a batch of tool_calls.

        Pure decision — no dispatch, no state mutation — so both the leaf-agent loop and
        MetaAgent call this same method. ``include_agents`` projects registered sub-agents
        into the roster; ``extra_tools`` appends any extra schema-only tools. Returns
        ``{tool_calls, routing, reasoning, step_tokens}``.
        """
        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookEvent
        from autogenesis.model import model_manager
        from autogenesis.model.types import accumulate_stream
        from autogenesis.agent.native_tools import assemble_native_tools

        await hook_manager(
            name="trace_hook",
            input={"event": HookEvent.PRE_STEP, "agent_name": self.name, "step_number": step_number, "task_id": task_id},
            ctx=ctx,
        )

        tools, routing = await assemble_native_tools(self, ctx, include_agents=include_agents)
        if extra_tools:
            tools = tools + list(extra_tools)

        reasoning = ""
        tool_calls: List[Any] = []
        step_tokens = 0
        try:
            acc = await accumulate_stream(
                model_manager.stream(
                    name=self.model_name,
                    input={"messages": messages, "tools": tools},
                    ctx=ctx,
                )
            )
            step_tokens = int((acc.get("usage") or {}).get("output_tokens", 0) or 0)
            reasoning = acc.get("thinking") or acc.get("text") or ""
            tool_calls = acc.get("tool_calls") or []
        except Exception as e:
            logger.error(f"| ❌ [{self.name}] Error in _think: {e}")

        logger.info(f"| 💭 [{self.name}] Reasoning: {reasoning[:200]}")
        logger.info(f"| 🔧 [{self.name}] Tool calls: {[c.name for c in tool_calls]}")

        return {"tool_calls": tool_calls, "routing": routing, "reasoning": reasoning, "step_tokens": step_tokens}

    async def _dispatch(
        self,
        decision: Dict[str, Any],
        task_id: str,
        step_number: int,
        ctx: "AgentContext",
    ) -> Dict[str, Any]:
        """Run this turn's batch of tool_calls CONCURRENTLY, each routed to its manager.

        A single turn's batch is parallel-safe by the function-calling contract — the
        model only puts independent calls in one batch; dependent work is emitted across
        turns — so we gather the whole batch. Returns
        ``{done, result, reasoning, action_errors, plan}``.
        """
        import json as _json

        tool_calls = decision["tool_calls"]
        routing = decision["routing"]
        reasoning = decision["reasoning"]
        action_errors: List[str] = []
        step_plan = [
            {"id": c.id, "description": "", "type": (routing.get(c.name) or ("tool",))[0],
             "name": c.name, "args": _json.dumps(c.input, ensure_ascii=False)}
            for c in tool_calls
        ]

        # A text-only turn is NOT completion — completion is an explicit `done` tool call,
        # never inferred from plain text. Nudge the model to act or call `done`.
        if not tool_calls:
            action_errors.append(
                "You produced text but called no tool. Take the next action by calling a tool, "
                "or if the task is COMPLETE call `done` with the result now. Do not answer in plain text."
            )
            logger.warning(f"| ⚠️ [{self.name}] No tool call — nudging to act or call done.")
            return {"done": False, "result": None, "reasoning": reasoning, "action_errors": action_errors, "plan": step_plan}

        outcomes = await asyncio.gather(*[
            self._run_one(call, i, routing, task_id, step_number, ctx)
            for i, call in enumerate(tool_calls)
        ])

        done = False
        result = None
        for o in outcomes:
            if o.get("error"):
                action_errors.append(f"Action '{o['name']}' failed: {o['error']}")
            if o.get("done"):
                done = True
                result = o.get("result")
                if o.get("reasoning"):
                    reasoning = o["reasoning"]
        return {"done": done, "result": result, "reasoning": reasoning, "action_errors": action_errors, "plan": step_plan}

    async def _run_one(
        self,
        call: Any,
        index: int,
        routing: Dict[str, Any],
        task_id: str,
        step_number: int,
        ctx: "AgentContext",
        parent_ref: Any = None,
    ) -> Dict[str, Any]:
        """Dispatch ONE tool_call, wrapped in its PRE_ACTION → invoke → POST_ACTION hooks.

        This is the atomic unit of action; the batch executor runs one per tool_call,
        concurrently. Keeping a call's hook pair inside one coroutine means the pairs
        stay correct even when the batch runs in parallel. ``parent_ref`` is this agent's
        own runtime ref, threaded through so an ``agent`` call can spawn its child with a
        parent to escalate to. Returns ``{name, done, result, reasoning, error}``.
        """
        import json as _json
        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookDecision, HookEvent

        route = routing.get(call.name)
        kind = route[0] if route else "tool"
        args_str = _json.dumps(call.input, ensure_ascii=False)
        logger.info(f"| 📝 [{self.name}] [{kind}] {call.name}: {call.input}")

        action_dict = {
            "index": index, "id": call.id, "description": "", "type": kind,
            "name": call.name, "args": args_str, "args_parsed": call.input,
        }

        done, result, reasoning, error, action_result = False, None, None, None, None

        pre_result = await hook_manager(
            name="trace_hook",
            input={"event": HookEvent.PRE_ACTION, "agent_name": self.name, "step_number": step_number, "action": action_dict, "task_id": task_id},
            ctx=ctx,
        )
        if pre_result.decision == HookDecision.BLOCK:
            logger.warning(f"| 🚫 [{self.name}] Action blocked by hook: {pre_result.reason}")
            return {"name": call.name, "done": False, "result": None, "reasoning": None, "error": None}

        try:
            if route is None:
                raise ValueError(f"Unknown tool '{call.name}' (not in the assembled tool set)")
            # read_only agents may not invoke framework-mutating tools.
            if (self.permission_mode == "read_only" and kind == "tool"
                    and route[1] in _READ_ONLY_DENIED_TOOLS
                    and not self._allow_read_only_tool_call(route[1], call.input or {})):
                raise PermissionError(
                    f"read_only agent '{self.name}' may not invoke framework-mutating "
                    f"tool '{route[1]}'. Report findings instead of modifying anything."
                )
            action_result, done, result, reasoning = await self._invoke_capability(route, call, ctx, parent_ref)
        except Exception as e:
            error = str(e)
            logger.error(f"| ❌ [{self.name}] Action '{call.name}' failed: {e}")

        await hook_manager(
            name="memory_hook",
            input={"event": HookEvent.POST_ACTION, "agent_name": self.name, "step_number": step_number, "action": action_dict, "action_result": action_result, "task_id": task_id, "error": error, "use_memory": self.use_memory, "memory_name": self.memory_name},
            ctx=ctx,
        )
        await hook_manager(
            name="trace_hook",
            input={"event": HookEvent.POST_ACTION, "agent_name": self.name, "step_number": step_number, "action": action_dict, "action_result": action_result, "task_id": task_id, "error": error},
            ctx=ctx,
        )
        await hook_manager(
            name="trajectory_hook",
            input={"event": HookEvent.POST_ACTION, "agent_name": self.name, "step_number": step_number, "action": action_dict, "action_result": action_result, "task_id": task_id, "error": error},
            ctx=ctx,
        )
        return {"name": call.name, "done": done, "result": result, "reasoning": reasoning,
                "error": error, "output": action_result}

    async def _invoke_capability(self, route: Any, call: Any, ctx: "AgentContext", parent_ref: Any = None):
        """Route ONE call to the manager that owns it — the single dispatch table that
        knows how each capability kind executes. Returns
        ``(action_result, done, result, reasoning)``.

        ``agent`` is a capability like any other: dispatching one runs a sub-agent to
        completion via the runtime, with this agent as its parent (so the child can
        escalate back up). This is what lets an orchestrator use the very same loop as a
        leaf actor — a sub-agent is just another tool it can call.
        """
        kind = route[0]
        if kind == "agent":
            from autogenesis.agent.server import agent_manager
            from autogenesis.protocol import protocol_manager
            child = await agent_manager.get(route[1])
            if child is None:
                raise ValueError(f"No registered agent named {route[1]!r}")
            inp = call.input or {}
            resp = await protocol_manager.delegate(
                child, inp.get("task", ""),
                files=inp.get("files"), target_name=inp.get("target_name"),
                allowlists={
                    k: inp.get(k) for k in (
                        "tool_allowlist", "skill_allowlist", "connector_allowlist",
                        "environment_allowlist", "workflow_allowlist",
                    )
                },
                parent_ref=parent_ref, workspace_root=config.workspace_root or self.base_dir,
            )
            if not resp.success:
                raise RuntimeError(resp.message or f"Sub-agent {route[1]!r} failed")
            logger.info(f"| ✅ [{self.name}] Sub-agent '{route[1]}' completed (success={resp.success})")
            return resp.message, False, None, None
        if kind == "workflow":
            from autogenesis.workflow import workflow_manager
            workflow_run = await workflow_manager.run(route[1], input=call.input or {}, ctx=ctx)
            if not workflow_run.successful:
                raise RuntimeError(workflow_run.error or f"Workflow {route[1]!r} failed")
            logger.info(f"| ✅ [{self.name}] Workflow '{route[1]}' completed")
            return json.dumps(workflow_run.output, ensure_ascii=False, default=str), False, None, None
        if kind == "skill":
            response = await skill_manager(name=route[1], input=call.input, ctx=ctx)
            if not response.success:
                raise RuntimeError(response.message or f"Skill {route[1]!r} failed")
            logger.info(f"| ✅ [{self.name}] Skill '{route[1]}' completed (success={response.success})")
            return response.message, False, None, None
        if kind == "connector":
            response = await connector_manager(name=route[1], input={"action": route[2], "args": call.input}, ctx=ctx)
            if not response.success:
                raise RuntimeError(response.message or f"Connector {route[1]!r} failed")
            logger.info(f"| ✅ [{self.name}] Connector '{route[1]}' action '{route[2]}' completed (success={response.success})")
            return response.message, False, None, None
        if kind == "environment":
            from autogenesis.environment.server import environment_manager
            action_result = await environment_manager(name=route[1], action=route[2], input=call.input, ctx=ctx)
            logger.info(f"| ✅ [{self.name}] Environment '{route[1]}' action '{route[2]}' completed")
            return action_result, False, None, None
        if kind == "env":
            action_result = await self._handle_env_action(route[1], call.input, ctx)
            logger.info(f"| ✅ [{self.name}] Env action '{route[1]}' completed")
            return action_result, False, None, None
        if kind == "tool":
            tool_response = await tool_manager(name=route[1], input=call.input, ctx=ctx)
            if not tool_response.success:
                raise RuntimeError(tool_response.message or f"Tool {route[1]!r} failed")
            logger.info(f"| ✅ [{self.name}] Tool '{route[1]}' completed")
            if route[1] == "done_tool":
                reasoning = (tool_response.data or {}).get("reasoning") if hasattr(tool_response, "data") else None
                return tool_response.message, True, tool_response.message, reasoning
            return tool_response.message, False, None, None
        raise ValueError(f"Unknown route kind {kind!r}")

    # ------------------------------------------------------------------
    # Path 1: Direct call
    # ------------------------------------------------------------------

    async def __call__(self,
                       task: Optional[str] = None,
                       files: Optional[List[str]] = None,
                       ctx: Optional[AgentContext] = None,
                       **kwargs: Any,
                       ) -> "Response":
        """Synchronous entry point: run this agent to completion and return its Response.

        Delegates to the runtime — spawn a pump, deliver the task, await the result — so
        the SAME event-driven loop (on_start → rounds → _conclude) runs whether the agent
        is called directly here or dispatched as a sub-agent by an orchestrator. Post-run
        work that used to live in a ``__call__`` override (generate/optimize registration)
        now hangs off ``_finalize_run``, so it fires on every path.
        """
        from autogenesis.runtime import runtime_manager
        return await runtime_manager.invoke(self, task=task, files=files, ctx=ctx, **kwargs)

    # ------------------------------------------------------------------
    # Path 2: Event-driven (runtime / mailbox)
    # ------------------------------------------------------------------

    async def on_start(self,
                       task: str,
                       files: Optional[List[str]],
                       ctx: Optional[AgentContext],
                       ref: Any,
                       **kwargs: Any,
                       ) -> Optional["Response"]:
        """Runtime pump entry: initialise the run, emit ON_START lifecycle hooks, and
        kick the first turn. Always returns ``None`` — the result is delivered later by
        ``_conclude`` (which resolves the caller's reply). This is THE loop every agent
        uses; orchestrators only widen the roster and override a couple of seams."""
        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookEvent
        from autogenesis.utils.name_utils import make_id

        logger.info(f"| 🚀 Starting {self.name}: {task}")
        if ctx is None:
            ctx = AgentContext()
        if not config.workspace_root:
            config.workspace_root = self.base_dir
        if files:
            logger.info(f"| 📂 Attached files: {files}")

        # Gateways already own a public task id.  Reuse it when supplied so task events,
        # trace events, memory, and cancellation all describe one execution identity.
        task_id = str(kwargs.pop("task_id", "") or make_id())
        run = _AgentRun(task, files, ctx, ref, task_id, kwargs)
        self._runs[ref.name] = run

        for hook_name in ("memory_hook", "trace_hook", "trajectory_hook"):
            await hook_manager(
                name=hook_name,
                input={"event": HookEvent.ON_START, "task": task, **self._lifecycle_input(run)},
                ctx=ctx,
            )

        await self._advance(run)
        return None

    async def on_event(self, msg: Any, ref: Any) -> None:
        """Runtime pump: collect a finished action (round bookkeeping) and, when the
        round drains, advance to the next turn or conclude. Non-action messages
        (escalations, progress) go to ``_handle_extra_event`` for orchestrators."""
        run = self._runs.get(ref.name)
        if run is None:
            return
        if isinstance(msg, _ActionDone):
            if msg.call_id in run.outstanding:
                run.outstanding.discard(msg.call_id)
                run.round_tasks.pop(msg.call_id, None)
                run.round_outcomes.append({"id": msg.call_id, "name": msg.name, "output": msg.output, "result": msg.result, "error": msg.error, "is_done": msg.is_done})
                if msg.error:
                    run.round_errors.append(f"Action '{msg.name}' failed: {msg.error}")
                if msg.is_done:
                    run.round_done = True
                    run.round_result = msg.result
                    run.round_reasoning = msg.reasoning
            if not run.outstanding:
                await self._on_round_complete(run)
        elif isinstance(msg, _ControlMessage):
            await self._handle_control(run, msg)
        elif isinstance(msg, _QueryMessage):
            if msg.reply_future is not None and not msg.reply_future.done():
                msg.reply_future.set_result(self._snapshot(run))
        else:
            await self._handle_extra_event(run, msg)

    async def _handle_control(self, run: "_AgentRun", msg: "_ControlMessage") -> None:
        """Control channel: cancel concludes gracefully; pause/resume gate advancing."""
        if msg.action == "cancel":
            logger.info(f"| ✋ [{self.name}] cancel requested: {msg.reason or '(no reason)'}")
            run.done = False
            run.result = f"Cancelled: {msg.reason}" if msg.reason else "Cancelled by parent."
            run.stopped_by_constraint = True  # treated as a non-success stop
            await self._conclude(run)
        elif msg.action == "pause":
            run.paused = True
            logger.info(f"| ⏸️ [{self.name}] paused")
        elif msg.action == "resume":
            run.paused = False
            logger.info(f"| ▶️ [{self.name}] resumed")
            if not run.outstanding and not run.done:
                await self._advance(run)

    def _snapshot(self, run: "_AgentRun") -> Dict[str, Any]:
        """Query channel: a small live status snapshot of this run."""
        return {
            "agent": self.name, "task_id": run.task_id, "step": run.step,
            "running_actions": len(run.outstanding), "paused": run.paused,
            "done": run.done, "result": run.result,
        }

    # ------------------------------------------------------------------
    # The event-driven loop body (shared by every agent)
    # ------------------------------------------------------------------

    def _lifecycle_input(self, run: "_AgentRun") -> Dict[str, Any]:
        """Assemble the common identity payload shared by ON_START/ON_STOP hook calls.

        Bundles the agent name, task id, memory settings, and the parent-session /
        subtask ids from the run context, so memory, trace, and trajectory hooks all
        receive a consistent lifecycle envelope.
        """
        return {
            "agent_name": self.name, "task_id": run.task_id,
            "memory_name": self.memory_name, "use_memory": self.use_memory,
            "parent_session_id": getattr(run.ctx, "parent_session_id", None),
            "subtask_id": getattr(run.ctx, "subtask_id", None),
        }

    async def _advance(self, run: "_AgentRun") -> None:
        """One turn: budget/step check → build messages → _think → dispatch the round.
        Concludes directly on a limit, or loops on a text-only (no-tool) turn."""
        if run.step >= self.max_step:
            logger.warning(f"| 🛑 [{self.name}] Reached max steps ({self.max_step})")
            run.done, run.result = False, "The task has not been completed."
            run.reasoning = "Reached the maximum number of steps."
            await self._conclude(run)
            return

        reason, cstatus = await self._constraint_check(run.task_id, run.ctx)
        if reason is not None:
            logger.warning(f"| 🛑 {self.name} constraint violated: {reason}")
            run.done, run.result, run.stopped_by_constraint = True, reason, True
            await self._conclude(run)
            return

        logger.info(f"| 🔄 [{self.name}] Step {run.step + 1}/{self.max_step}")
        messages = await self._get_messages(
            run.task, ctx=run.ctx, files=run.files, step_number=run.step,
            action_errors=run.action_errors, constraint_status=cstatus, _run=run, **run.extra_kwargs)
        decision = await self._think(
            messages, run.task_id, run.step, run.ctx,
            include_agents=self._include_agents(), extra_tools=self._extra_tools(run))
        run.decision = decision
        run.messages = messages

        calls = await self._prepare_round(run, decision)
        if calls is None:
            return  # a seam (e.g. MetaAgent) fully handled this turn (concluded / deferred)
        if not calls:
            # text-only turn: record the empty step, nudge, and try again next turn
            run.round_step = run.step
            run.step_plan = []
            await self._post_step(run.task_id, run.step, run.ctx, messages,
                                  reasoning=decision["reasoning"], plan=[], step_tokens=decision["step_tokens"], done=False)
            run.action_errors = [
                "You produced text but called no tool. Take the next action by calling a tool, "
                "or if the task is COMPLETE call `done_tool` with the result now."]
            run.step += 1
            await self._advance(run)
            return
        self._dispatch_round(run, calls, decision["routing"])

    def _dispatch_round(self, run: "_AgentRun", calls: List[Any], routing: Dict[str, Any]) -> None:
        """Launch this turn's batch as concurrent background tasks, each posting its
        result to this agent's own inbox. This turn's batch == one round."""
        import json as _json
        run.round_step = run.step
        run.outstanding = set()
        run.round_tasks = {}
        run.round_errors = []
        run.round_done = False
        run.round_result = None
        run.round_reasoning = None
        run.round_outcomes = []
        run.step_plan = [
            {"id": c.id, "description": "", "type": (routing.get(c.name) or ("tool",))[0],
             "name": c.name, "args": _json.dumps(c.input, ensure_ascii=False)} for c in calls]
        for i, call in enumerate(calls):
            run.outstanding.add(call.id)
            run.round_tasks[call.id] = asyncio.create_task(
                self._run_one_bg(run, call, i, routing), name=f"action-{call.id}")

    async def _run_one_bg(self, run: "_AgentRun", call: Any, index: int, routing: Dict[str, Any]) -> None:
        """Run one action, then post an _ActionDone back to this agent's inbox."""
        try:
            outcome = await self._run_one(call, index, routing, run.task_id, run.round_step, run.ctx, parent_ref=run.ref)
        except asyncio.CancelledError:
            return
        except Exception as e:  # pragma: no cover - defensive
            outcome = {"name": call.name, "done": False, "result": None, "reasoning": None, "error": str(e)}
        try:
            await run.ref._inbox.put(_ActionDone(
                call_id=call.id, name=call.name, output=outcome.get("output"), result=outcome.get("result"),
                error=outcome.get("error"), is_done=outcome.get("done", False), reasoning=outcome.get("reasoning")))
        except Exception:
            pass

    async def _on_round_complete(self, run: "_AgentRun") -> None:
        """A round's whole batch has drained: record the step, then advance or conclude."""
        decision = run.decision
        self._record_action_evidence(run)
        await self._post_step(run.task_id, run.round_step, run.ctx, run.messages,
                              reasoning=decision["reasoning"], plan=getattr(run, "step_plan", []),
                              step_tokens=decision["step_tokens"], done=run.round_done)
        run.action_errors = list(run.round_errors)
        run.step = run.round_step + 1
        if run.round_done:
            run.done = True
            run.result = run.round_result
            if run.round_reasoning:
                run.reasoning = run.round_reasoning
            await self._conclude(run)
            return
        if run.paused:
            return  # control channel: hold here until a resume advances us
        await self._advance(run)

    async def _conclude(self, run: "_AgentRun") -> None:
        """Finish a run: cancel stragglers, emit ON_STOP hooks, build the Response, run
        the post-run finalize hook, resolve the caller's reply, then on_end."""
        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookEvent
        from autogenesis.response import ResponseType

        for t in list(run.round_tasks.values()):
            if not t.done():
                t.cancel()
        if run.round_tasks:
            await asyncio.gather(*run.round_tasks.values(), return_exceptions=True)
        run.round_tasks.clear()
        run.outstanding.clear()

        success = run.done and not run.stopped_by_constraint
        for hook_name in ("memory_hook", "trace_hook", "trajectory_hook"):
            await hook_manager(
                name=hook_name,
                input={"event": HookEvent.ON_STOP, "result": run.result, "success": success, **self._lifecycle_input(run)},
                ctx=run.ctx,
            )
        logger.info(f"| ✅ {self.name} completed after {run.step}/{self.max_step} steps")

        data = {"done": run.done, "result": run.result, "reasoning": run.reasoning,
                "stopped_by_constraint": run.stopped_by_constraint, "task_id": run.task_id}
        response = Response(type=ResponseType.AGENT, success=success, message=run.result or "", data=data)
        response = await self._finalize_run(response, run.ctx)

        ref = run.ref
        if ref is not None and ref._pending_reply is not None and not ref._pending_reply.done():
            ref._pending_reply.set_result(response)
            ref._pending_reply = None
        self._runs.pop(run.ref.name, None)
        await self.on_end(response, run.ctx, run)

    # ------------------------------------------------------------------
    # Seams — leaf actors use the defaults; orchestrators (MetaAgent) override
    # ------------------------------------------------------------------

    def _include_agents(self) -> bool:
        """Whether to project registered sub-agents into this agent's roster (agent__*).
        False for leaf actors; MetaAgent overrides to True."""
        return False

    def _include_workflows(self) -> bool:
        """Whether this Agent may invoke registered Workflows directly."""
        return False

    def _allow_read_only_tool_call(self, name: str, input: Dict[str, Any]) -> bool:
        """Narrow opt-in for non-mutating actions exposed by a mixed-action Tool."""
        return False

    def _target_capability_allowlists(self, target_name: Optional[str]) -> Dict[str, Any]:
        """Optional least-privilege allowlists derived from an evolution target."""
        return {}

    def _extra_tools(self, run: "_AgentRun") -> Optional[List[Any]]:
        """Extra schema-only tools to append beyond the projected capabilities. Default:
        none (orchestration control like reply is an ordinary registered tool now)."""
        return None

    async def _prepare_round(self, run: "_AgentRun", decision: Dict[str, Any]) -> Optional[List[Any]]:
        """Apply the shared no-progress guard before dispatching a round.

        Defined on the base ``Agent`` and called on the single round path every agent's
        loop flows through, so the guard applies to all agents uniformly; subclasses that
        override this (only ``MetaAgent``) must chain to ``super()`` to keep it.

        Detection is delegated to a stateless hook (``no_progress_hook``); evidence and
        escalation counters stay on the run.  The first two blocked proposals are returned
        to the model as corrective context.  A third unchanged proposal terminates honestly
        instead of consuming the entire step budget.
        """
        calls = decision["tool_calls"]
        if not calls:
            return calls

        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookDecision, HookEvent

        routing = decision.get("routing") or {}
        actions = []
        for call in calls:
            route = routing.get(call.name) or ("tool", call.name)
            signature = self._action_signature(route[0], call.name, call.input or {})
            actions.append({
                "name": call.name,
                "kind": route[0],
                "signature": signature,
                "policy": await self._progress_policy(route),
            })
        guard = await hook_manager(
            name="no_progress_hook",
            input={
                "event": HookEvent.PRE_ACTION,
                "agent_name": self.name,
                "task_id": run.task_id,
                "actions": actions,
                "evidence": run.action_evidence,
                "workspace_fingerprint": self._workspace_fingerprint(run.ctx),
            },
            ctx=run.ctx,
        )
        if guard.decision != HookDecision.BLOCK:
            run.no_progress_rounds = 0
            return calls

        run.no_progress_rounds += 1
        reason = guard.reason or "No-progress guard blocked an unchanged successful action."
        if run.no_progress_rounds >= 3:
            run.done = False
            run.result = (
                "Stopped after three no-progress action proposals. Existing successful "
                "evidence is preserved in Memory, but the agent did not finish or choose "
                "a materially different action."
            )
            run.reasoning = reason
            await self._conclude(run)
            return None

        run.round_step = run.step
        await self._post_step(
            run.task_id, run.step, run.ctx, run.messages,
            reasoning=decision["reasoning"], plan=[],
            step_tokens=decision["step_tokens"], done=False,
        )
        suffix = (
            " This is the second blocked proposal. Stop inspecting: take a state-changing "
            "action (run/execute your code, edit a file) or call done_tool now — the next "
            "repeated proposal will terminate this agent."
            if run.no_progress_rounds == 2 else ""
        )
        run.action_errors = [reason + suffix]
        run.step += 1
        await self._advance(run)
        return None

    @staticmethod
    def _action_signature(kind: str, name: str, args: Dict[str, Any]) -> str:
        """Return a deterministic signature for one capability invocation."""
        payload = {"kind": kind, "name": name, "args": args}
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    async def _progress_policy(route: Any) -> Optional[str]:
        """Read an explicit Tool policy; other capability kinds use hook defaults."""
        if not route or route[0] != "tool":
            return None
        info = await tool_manager.get_info(route[1])
        if info is None:
            return None
        instance = getattr(info, "instance", None)
        return getattr(instance, "progress_policy", None) or getattr(info, "progress_policy", None)

    @staticmethod
    def _workspace_fingerprint(ctx: Optional["AgentContext"]) -> str:
        """Fingerprint observable workspace state without reading file contents.

        Paths, sizes, and nanosecond mtimes detect ordinary edits cheaply. Large cache
        trees are skipped and traversal is bounded to keep the guard lightweight.
        """
        root_value = config.workspace_root
        if not root_value:
            return ""
        root = os.path.abspath(root_value)
        digest = hashlib.sha256()
        seen = 0
        skipped = {".git", "__pycache__", "node_modules", ".venv"}
        try:
            for current, dirs, files in os.walk(root):
                dirs[:] = sorted(d for d in dirs if d not in skipped)
                # Directory mtimes catch creation/removal of empty directories, which
                # matters for list/inspection actions even when no file exists yet.
                for name in dirs:
                    directory = os.path.join(current, name)
                    try:
                        stat = os.stat(directory, follow_symlinks=False)
                    except OSError:
                        continue
                    relative = os.path.relpath(directory, root)
                    digest.update(f"{relative}/\0{stat.st_mtime_ns}\n".encode())
                for name in sorted(files):
                    path = os.path.join(current, name)
                    try:
                        stat = os.stat(path, follow_symlinks=False)
                    except OSError:
                        continue
                    relative = os.path.relpath(path, root)
                    digest.update(f"{relative}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode())
                    seen += 1
                    if seen >= 4096:
                        digest.update(b"<truncated>")
                        return digest.hexdigest()
        except OSError:
            return ""
        return digest.hexdigest()

    def _record_action_evidence(self, run: "_AgentRun") -> None:
        """Remember successful results from the drained round at its final workspace state."""
        plans = {item.get("id"): item for item in run.step_plan}
        fingerprint = self._workspace_fingerprint(run.ctx)
        for outcome in run.round_outcomes:
            if outcome.get("error") or outcome.get("is_done"):
                continue
            plan = plans.get(outcome.get("id"))
            if not plan:
                continue
            try:
                args = json.loads(plan.get("args") or "{}")
            except (TypeError, ValueError):
                args = {}
            signature = self._action_signature(
                str(plan.get("type") or "tool"), str(plan.get("name") or ""), args,
            )
            run.action_evidence[signature] = {
                "success": True,
                "workspace_fingerprint": fingerprint,
                "output": outcome.get("output"),
            }

    async def _handle_extra_event(self, run: "_AgentRun", msg: Any) -> None:
        """Handle a non-action inbox message (escalation, progress). Leaf agents receive
        none; orchestrators override. Default: ignore."""
        return

    async def _finalize_run(self, response: "Response", ctx: Optional[AgentContext]) -> "Response":
        """Post-run hook, called by ``_conclude`` BEFORE the caller's reply is resolved so
        it can still adjust the Response. Default: passthrough. generate/optimize agents
        override to register the produced artifact (and fail the response on error)."""
        return response

    async def on_end(self,
                     result: "Response",
                     ctx: Optional[AgentContext],
                     run: Optional["_AgentRun"] = None,
                     ) -> None:
        """Third of the lifecycle triad (``on_start`` / ``on_event`` / ``on_end``):
        called once the run resolves — cleanup / teardown hook.

        The framework's ``_conclude`` calls this (with the finished ``run``) after it
        has resolved the caller's reply. ``run`` is ``None`` only on the synchronous
        ``handle`` path (an agent whose ``on_start`` returned a Response directly, e.g.
        BrowserAgent). Distinct from ``HookEvent.ON_STOP`` (a hook event fired around
        completion) — this is the overridable Python method.

        Default behaviour: no-op.  Override to emit extra teardown / trace / reset state.
        """

    # ------------------------------------------------------------------
    # Framework dispatcher — do NOT override in subclasses
    # ------------------------------------------------------------------

    async def handle(self, msg: Any, ref: Any) -> None:
        """Runtime pump dispatcher.

        Routes each inbox message to the appropriate lifecycle method:
          * TaskMessage          → on_start → [on_end if resolved synchronously]
          * Everything else      → on_event

        This method is part of the framework layer.  Subclasses should
        implement ``on_start``, ``on_event``, and ``on_end`` instead of
        overriding ``handle``.
        """
        from autogenesis.runtime.types import TaskMessage
        if isinstance(msg, TaskMessage):
            ctx = msg.kwargs.get("ctx")
            ref._pending_reply = msg.reply_future      # hand ownership to ref
            try:
                extra_kwargs = {k: v for k, v in msg.kwargs.items() if k not in ("ctx", "files")}
                result = await self.on_start(
                    task=msg.task or "",
                    files=msg.kwargs.get("files"),
                    ctx=ctx,
                    ref=ref,
                    **extra_kwargs,
                )
                if result is not None:
                    if ref._pending_reply is not None and not ref._pending_reply.done():
                        ref._pending_reply.set_result(result)
                        ref._pending_reply = None
                    await self.on_end(result, ctx)
            except asyncio.CancelledError:
                if ref._pending_reply is not None and not ref._pending_reply.done():
                    ref._pending_reply.cancel()
                raise
            except Exception as exc:
                logger.error(f"| ❌ {self.name} task failed: {exc}", exc_info=True)
                if ref._pending_reply is not None and not ref._pending_reply.done():
                    ref._pending_reply.set_exception(exc)
        else:
            await self.on_event(msg, ref)


class ProceduralAgent(Agent):
    """Deterministic Agent subtype driven by code instead of the LLM loop.

    Subclasses implement :meth:`run_procedure`. The inherited ``__call__`` remains
    the only public entry point, so direct calls and delegated runtime calls follow
    the same mailbox lifecycle.
    """

    agent_type: AgentType = Field(default=AgentType.PROCEDURAL)

    def __init__(self, *args: Any, use_memory: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, use_memory=use_memory, **kwargs)

    async def run_procedure(
        self,
        task: str,
        files: Optional[List[str]],
        ctx: AgentContext,
        **kwargs: Any,
    ) -> "Response":
        """Run this procedural agent's deterministic logic once and return its Response.

        The single extension point for ``ProceduralAgent`` subclasses: ``on_start`` wraps
        it in the standard lifecycle hooks and reply resolution, so subclasses implement
        only the procedure itself.

        Raises:
            NotImplementedError: If a subclass does not override this method.
        """
        raise NotImplementedError(f"{type(self).__name__}.run_procedure is not implemented")

    async def on_start(
        self,
        task: str,
        files: Optional[List[str]],
        ctx: Optional[AgentContext],
        ref: Any,
        **kwargs: Any,
    ) -> Optional["Response"]:
        """Execute the deterministic workflow once and resolve synchronously."""
        from autogenesis.hook.server import hook_manager
        from autogenesis.hook.types import HookEvent
        from autogenesis.response import ResponseType

        ctx = ctx or AgentContext()
        if not config.workspace_root:
            config.workspace_root = self.base_dir
        task_id = str(uuid.uuid4())
        lifecycle = {
            "task_id": task_id,
            "agent_name": self.name,
            "agent_type": self.agent_type.value,
            "memory_name": self.memory_name,
            "use_memory": self.use_memory,
            "parent_session_id": ctx.parent_session_id,
            "subtask_id": ctx.subtask_id,
        }
        for hook_name in ("memory_hook", "trace_hook", "trajectory_hook"):
            await hook_manager(
                name=hook_name,
                input={"event": HookEvent.ON_START, "task": task, **lifecycle},
                ctx=ctx,
            )

        try:
            response = await self.run_procedure(task, files, ctx, **kwargs)
            if not isinstance(response, Response):
                response = Response(
                    type=ResponseType.AGENT,
                    success=True,
                    message=str(response),
                    data={"result": response},
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"| ❌ [{self.name}] Workflow failed: {exc}", exc_info=True)
            response = Response(type=ResponseType.AGENT, success=False, message=str(exc))

        response = await self._finalize_run(response, ctx)
        for hook_name in ("memory_hook", "trace_hook", "trajectory_hook"):
            await hook_manager(
                name=hook_name,
                input={
                    "event": HookEvent.ON_STOP,
                    "result": response.message,
                    "success": response.success,
                    **lifecycle,
                },
                ctx=ctx,
            )
        return response


__all__ = [
    "InputArgs",
    "AgentConfig",
    "AgentType",
    "Agent",
    "ProceduralAgent",
    "AgentContext",
]
