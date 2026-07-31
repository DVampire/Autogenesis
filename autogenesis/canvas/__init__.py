"""Canvas: visual editor over the workflow module (JSON source → HTML artifact)."""

from autogenesis.canvas.server import CanvasManagerServer, canvas_manager
from autogenesis.canvas.types import FlowGraph, GraphEdge, GraphNode, NodeSpec, ParamSpec

__all__ = [
    "CanvasManagerServer",
    "canvas_manager",
    "FlowGraph",
    "GraphEdge",
    "GraphNode",
    "NodeSpec",
    "ParamSpec",
]
