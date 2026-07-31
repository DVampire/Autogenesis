"""Constraint types — Constraint base class, ConstraintConfig and ConstraintContext."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Type, Union
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from autogenesis.dynamic import dynamic_manager
from autogenesis.session import BaseContext
from autogenesis.response.types import Response, ResponseType


class ConstraintContext(BaseContext):
    """Context passed into constraint manager and individual constraint instances."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default="", description="Task ID — matches the task_id used throughout the agent loop.")
    name: str = Field(default="", description="Name of the constraint being checked.")
    workspace_root: Optional[str] = Field(default=None, description="Working directory available to the caller.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input payload for this constraint check.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this constraint context.")


class ConstraintStatus(BaseModel):
    """Standardized resource-budget snapshot carried in ``Response.data["status"]``.

    Every constraint check returns this alongside its legacy data keys, so the
    agent can surface remaining budgets to the LLM in the prompt.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="Constraint name this status belongs to.")
    used: float = Field(default=0, description="Amount of the resource consumed so far.")
    limit: float = Field(description="Effective limit for this task (may be overridden per call via input).")
    unit: str = Field(default="", description="Resource unit, e.g. 'steps', 'tokens', 'seconds'.")

    @property
    def remaining(self) -> float:
        return max(0.0, self.limit - self.used)

    @property
    def ratio(self) -> float:
        return self.used / self.limit if self.limit > 0 else 0.0

    def line(self) -> str:
        """One-line human/LLM-readable budget summary."""
        if self.unit == "seconds":
            return f"{self.name}: {self.used:.0f}s / {self.limit:.0f}s ({self.remaining:.0f}s remaining)"
        return f"{self.name}: {self.used:,.0f} / {self.limit:,.0f} ({self.remaining:,.0f} {self.unit} remaining)"


def render_status_text(statuses: List[Union[ConstraintStatus, Dict[str, Any]]],
                       tight_ratio: float = 0.6,
                       critical_ratio: float = 0.85) -> str:
    """Render constraint statuses (collected from check Responses) as a prompt-ready text block.

    Includes per-constraint budget lines plus an overall urgency tier
    (NORMAL / TIGHT / CRITICAL) driven by the most-consumed budget, with a
    policy hint so the LLM can plan around remaining resources.
    Returns "" when ``statuses`` is empty.
    """
    parsed = [s if isinstance(s, ConstraintStatus) else ConstraintStatus.model_validate(s) for s in statuses]
    if not parsed:
        return ""

    worst = max(s.ratio for s in parsed)
    if worst >= critical_ratio:
        tier = "CRITICAL"
        hint = "Wrap up NOW — consolidate what you have and finish with the best available partial result."
    elif worst >= tight_ratio:
        tier = "TIGHT"
        hint = "Stop broadening scope; prioritize the critical path and prepare to conclude."
    else:
        tier = "NORMAL"
        hint = "Proceed as planned."

    lines = [
        "You operate under hard resource limits. When any limit is hit the task is force-stopped immediately — an unfinished answer is lost. Budget accordingly.",
        "",
        "Current budget (used / limit, remaining):",
    ]
    lines.extend(f"- {s.line()}" for s in parsed)
    lines.append("")
    lines.append(f"Status: {tier}. {hint}")
    return "\n".join(lines)


class Constraint(BaseModel):
    """Base class for all constraints.

    Subclass and override ``__call__(input, ctx)`` to implement constraint logic.
    Return ``Response(success=False, ...)`` when violated, ``success=True`` when passing.
    Limit parameters may be overridden per call via ``input`` (e.g. ``{"max_step": 50}``);
    the effective limit is remembered in per-task state for subsequent checks.

    Include a ``ConstraintStatus`` dump under ``Response.data["status"]`` so callers
    can surface the remaining budget to the LLM (see ``render_status_text``).

    Per-task state lives in ``_state[task_id]`` — a plain dict lazily initialized
    on first use inside ``__call__``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="Unique name for this constraint.")
    description: str = Field(default="", description="The description of the constraint.")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="The metadata of the constraint.")
    enable_evolving: bool = Field(default=False, description="Whether the constraint may be evolved (self-optimized).")
    enabled: bool = Field(default=True, description="Set to False to temporarily disable without removing.")

    _state: Dict[str, Dict[str, Any]] = PrivateAttr(default_factory=dict)

    def _cleanup(self, task_id: str) -> None:
        self._state.pop(task_id, None)

    def _effective_limit(self, task_id: str, input: Dict[str, Any], key: str, default: float) -> float:
        """Resolve the effective limit for ``key``: input override > remembered > default.

        When ``input[key]`` is provided it is remembered in per-task state, so the
        agent can raise/lower its own budget mid-task and ``status()`` stays consistent.
        """
        state = self._state.setdefault(task_id, {})
        if input.get(key) is not None:
            state[key] = input[key]
        return state.get(key, default)

    async def __call__(self, input: Dict[str, Any], ctx: ConstraintContext) -> Response:
        return Response(type=ResponseType.CONSTRAINT, success=True, message="")


class ConstraintConfig(BaseModel):
    """Constraint configuration"""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="The name of the constraint")
    description: str = Field(default="", description="The description of the constraint")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="The metadata of the constraint")
    enable_evolving: bool = Field(default=False, description="Whether the constraint may be evolved (self-optimized)")
    enabled: bool = Field(default=True, description="Whether the constraint is enabled")
    version: str = Field(default="1.0.0", description="Version of the constraint")

    cls: Optional[Type[Constraint]] = Field(default=None, description="The class of the constraint")
    config: Optional[Dict[str, Any]] = Field(default={}, description="The initialization configuration of the constraint")
    instance: Optional[Constraint] = Field(default=None, description="The instance of the constraint")
    code: Optional[str] = Field(default=None, description="Source code for dynamically generated constraint classes (used when cls cannot be imported from a module)")
    path: Optional[str] = Field(default=None, description="Absolute path to the constraint's source file")

    # Default representations
    function_calling: Optional[Dict[str, Any]] = Field(default=None, description="Default function calling representation")
    text: Optional[str] = Field(default=None, description="Default text representation")
    args_schema: Optional[Type[BaseModel]] = Field(default=None, description="Default args schema (BaseModel type)")

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        """Dump the model to a dictionary, recursively serializing nested Pydantic models."""

        result = {
            "name": self.name,
            "description": self.description,
            "metadata": self.metadata,
            "enable_evolving": self.enable_evolving,
            "enabled": self.enabled,
            "version": self.version,

            "cls": dynamic_manager.get_class_string(self.cls) if self.cls else None,
            "config": self.config,
            "instance": None,
            "code": self.code,
            "path": self.path,

            "function_calling": self.function_calling,
            "text": self.text,
            "args_schema": dynamic_manager.serialize_args_schema(self.args_schema) if self.args_schema else None,
        }

        return result

    @classmethod
    def model_validate(cls, data: Dict[str, Any]) -> 'ConstraintConfig':
        """Validate the model from a dictionary."""
        name = data.get("name")
        description = data.get("description", "")
        metadata = data.get("metadata")
        enable_evolving = data.get("enable_evolving", False)
        enabled = data.get("enabled", True)
        version = data.get("version")

        cls_ = None
        code = data.get("code")
        if code:
            class_name = dynamic_manager.extract_class_name_from_code(code)
            if class_name:
                try:
                    cls_ = dynamic_manager.load_class(
                        code,
                        class_name=class_name,
                        base_class=Constraint,
                        context="constraint"
                    )
                except Exception:
                    cls_ = None
            else:
                cls_ = None
        else:
            cls_ = None

        config = data.get("config")
        instance = data.get("instance", None)

        function_calling = data.get("function_calling")
        text = data.get("text")
        args_schema = dynamic_manager.deserialize_args_schema(data.get("args_schema"))

        return cls(name=name,
            description=description,
            metadata=metadata,
            enable_evolving=enable_evolving,
            enabled=enabled,
            version=version,
            cls=cls_,
            config=config,
            instance=instance,
            code=code,
            function_calling=function_calling,
            text=text,
            args_schema=args_schema,
        )


__all__ = ["ConstraintContext", "Constraint", "ConstraintConfig", "ConstraintStatus", "render_status_text"]
