"""Data contracts for the canvas module.

The canvas edits a **flow graph** stored as JSON — the editable source of
truth, holding every node's invocation parameters plus purely visual state.
Publishing compiles the graph to ``<workflow>`` HTML (the build artifact) and
registers it with ``workflow_manager``; running compiles in memory and starts
the workflow runtime directly. The canvas has no executor of its own.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


DOCUMENT_VERSION = 2

# Step ids must satisfy the workflow compiler's id rule.
NODE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

CALLABLE_STEPS = {"tool", "agent", "skill", "workflow", "datasource", "process", "data", "knowledge", "benchmark"}
STRUCTURAL_STEPS = {"map", "branch", "loop", "reduce", "verify", "checkpoint"}
STEP_TYPES = CALLABLE_STEPS | STRUCTURAL_STEPS

NodeType = Literal["step", "input", "output"]
Slot = Literal["body", "then", "else"]
ParamType = Literal["string", "number", "boolean", "select", "json"]

# Data-flow port types (a small closed set; Langflow-style colored handles).
# A connection is valid when the two port types are equal or either is ``any``.
PortType = Literal["text", "list", "object", "any"]


def ports_compatible(source: str, target: str) -> bool:
    return source == target or source == "any" or target == "any"


class Position(BaseModel):
    x: float = 0.0
    y: float = 0.0


class PortSpec(BaseModel):
    """One typed connection point on a node.

    ``name`` is the handle id used by edges: an input port is ``task`` /
    ``items`` / ``value`` / ``arg:<param>``; an output port is ``message`` /
    ``data`` / ``files`` / ``out`` and names the sub-path the edge compiles to
    (``${node.<name>}``; ``out`` means the whole value ``${node}``).
    """

    name: str
    label: str
    type: PortType = "any"
    description: str = ""


class ParamSpec(BaseModel):
    """One form field on a palette node (compiled into an ``<arg>``)."""

    name: str
    label: str
    type: ParamType = "string"
    required: bool = False
    default: Any = None
    options: Optional[List[str]] = None
    multiline: bool = False
    description: str = ""
    connectable: bool = True


class NodeSpec(BaseModel):
    """A palette entry the frontend renders and the compiler understands.

    ``id`` is ``<category>/<name>`` (e.g. ``tool/bash_tool``, ``step/map``,
    ``io/input``). Callable specs carry the capability ``target``.
    """

    id: str
    # Palette group: agent/workflow/structural/io, or a tool's canvas_category
    # (data/processing/files/knowledge) for standalone deterministic tool nodes.
    category: str
    step_type: Optional[str] = None
    target: Optional[str] = None
    label: str
    description: str = ""
    # Per-node lucide icon name (Langflow-style: every node has its own glyph).
    # The frontend resolves it, falling back to the category icon.
    icon: str = ""
    params: List[ParamSpec] = Field(default_factory=list)
    has_task: bool = False
    has_items: bool = False
    container: bool = False
    # Typed data-flow ports the frontend renders (colored handles) and the
    # compiler binds. Config params (concurrency, target, …) are NOT ports.
    inputs: List[PortSpec] = Field(default_factory=list)
    outputs: List[PortSpec] = Field(default_factory=list)
    # For agent specs: which capability rosters can be mounted (scoped) on this
    # agent — one of tools/skills/connectors/agents/environments. The frontend
    # renders a search+select picker per capability type; the selection compiles to the
    # agent step's ``<arg name="<type>">`` allowlist.
    mount_types: List[str] = Field(default_factory=list)
    # For migrated Langflow *plugin* tools: the plugin this node belongs to, so
    # the palette can nest tools under a collapsible plugin group (Langflow's
    # "Bundles" sidebar section). ``plugin`` is the id (e.g. ``youtube``),
    # ``plugin_label`` the display name (e.g. ``YouTube``). Empty for non-plugin
    # nodes.
    plugin: str = ""
    plugin_label: str = ""


class GraphNode(BaseModel):
    """One placed node. Fields are a union over the three kinds:

    - ``step``: ``step_type``/``target``/``task``/``args``/``items``/``attrs``
    - ``input``: ``name``/``input_type``/``required``/``default``/``description``
    - ``output``: ``name``/``value``
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str
    #: Accepts the old ``kind`` spelling too. ``extra="ignore"`` means a flow
    #: saved before the rename would otherwise load with every node silently
    #: defaulting to ``step`` — inputs and outputs turning into steps, and their
    #: edges vanishing with the ports that no longer existed.
    type: NodeType = Field(default="step", validation_alias=AliasChoices("type", "kind"))
    step_type: Optional[str] = None
    target: Optional[str] = None
    task: str = ""
    args: Dict[str, Any] = Field(default_factory=dict)
    items: str = ""
    attrs: Dict[str, Any] = Field(default_factory=dict)
    # For agent steps: capability names mounted (scoped) on this agent, keyed by
    # type (tools/skills/connectors/agents/environments). Compiles to the agent
    # step's allowlist args; an empty/absent list means "use the agent's defaults".
    mounts: Dict[str, List[str]] = Field(default_factory=dict)
    # Freeze: when frozen and a captured output is present, the compiler drops
    # this node's step and substitutes ``frozen_output`` as a literal wherever it
    # is referenced — so it is not re-executed, its last result is reused.
    frozen: bool = False
    frozen_output: Optional[Dict[str, Any]] = None
    name: str = ""
    input_type: str = "string"
    required: bool = False
    default: Any = None
    description: str = ""
    value: str = ""
    parent: Optional[str] = None
    slot: Slot = "body"
    position: Position = Field(default_factory=Position)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not NODE_ID.fullmatch(value):
            raise ValueError(f"Node id must match {NODE_ID.pattern}: {value!r}")
        return value


class GraphEdge(BaseModel):
    """A typed binding: the target port's value becomes ``${source.<source_port>}``.

    ``param`` names the TARGET input port — ``arg:<name>`` (an argument),
    ``task``, ``items`` (map/verify/reduce input), or ``value`` (an output
    node). ``source_port`` names the SOURCE output port — ``message`` /
    ``data`` / ``files`` compile to ``${source.<port>}``, ``out`` (the default)
    to the whole ``${source}``. Inline ``${...}`` references typed into task
    text are part of the text itself, not edges.
    """

    id: str
    source: str
    target: str
    param: str
    source_port: str = "out"


class FlowGraph(BaseModel):
    """The persisted flow document (one JSON file per flow). Drafts may be
    structurally incomplete; full validation happens at publish/run time."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    name: str = "Untitled flow"
    description: str = ""
    version: str = "1.0.0"
    document_version: int = DOCUMENT_VERSION
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    # Sticky-note annotations — visual only; round-tripped through save/load but
    # never part of the compiled graph (the compiler iterates ``nodes`` only).
    notes: List[Dict[str, Any]] = Field(default_factory=list)
    published: bool = False
    program_hash: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def summary(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "published": self.published,
            "updated_at": self.updated_at,
            "node_count": len([node for node in self.nodes if node.type == "step"]),
        }


def workflow_name_for(graph: FlowGraph) -> str:
    """Derive the registry name for a graph: slugified, id-rule compliant."""
    slug = re.sub(r"[^A-Za-z0-9_]+", "_", graph.name.strip()).strip("_") or "canvas_flow"
    if not slug[0].isalpha():
        slug = f"flow_{slug}"
    return slug.lower()


__all__ = [
    "CALLABLE_STEPS",
    "DOCUMENT_VERSION",
    "FlowGraph",
    "GraphEdge",
    "GraphNode",
    "NODE_ID",
    "NodeSpec",
    "ParamSpec",
    "PortSpec",
    "PortType",
    "Position",
    "STEP_TYPES",
    "STRUCTURAL_STEPS",
    "ports_compatible",
    "workflow_name_for",
]
