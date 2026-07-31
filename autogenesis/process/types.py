"""Type definitions for the process module.

A **processor** is a *pure* transform: ``(input, params) → output``, no network,
no side effects, no LLM. It sits between a ``datasource`` (which fetches) and a
``benchmark`` (which evaluates), reshaping records — select fields, filter, sort,
derive columns, etc. Like every other capability it returns the canonical
``{message, data, files}`` :class:`Response` envelope so it composes on the
canvas / in a workflow (``StepType.PROCESS``).
"""

from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.session import BaseContext
from autogenesis.response.types import Response


class ProcessContext(BaseContext):
    """Context passed into the process manager and individual processors."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default="", description="Unique identifier for this process call.")
    name: str = Field(default="", description="Name of the processor being called.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input payload passed to the processor.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this context.")


class Processor(BaseModel):
    """Base class for pure record transforms.

    Subclasses implement :meth:`__call__` and MUST be side-effect free: given the
    same input they return the same output. ``data`` on the returned Response
    carries the transformed payload (typically ``{"records": [...]}``).
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(default="", description="Registered processor name (e.g. ``select_fields``).")
    description: str = Field(default="", description="One-line description of the transform.")
    instruction: str = Field(default="", description="Full usage instruction, fetched on demand.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary processor metadata.")

    async def __call__(self, **kwargs) -> Response:
        """Run the pure transform and return a canonical Response."""
        raise NotImplementedError("All processors must implement __call__")


__all__ = ["Processor", "ProcessContext"]
