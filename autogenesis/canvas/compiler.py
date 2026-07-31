"""Compile a canvas flow graph (JSON) into a runnable ``WorkflowDefinition``.

One direction only: the JSON graph is the canvas's editable source of truth.
Compilation emits a transient ``<workflow>`` document (never persisted — the
canvas stores nothing as HTML) that mirrors the hand-written workflows under
``autogenesis/workflow/default/`` and is validated by the real
``WorkflowCompiler``, so the resulting definition is guaranteed to run. Callers
run it ephemerally on the shared runtime; the canvas is isolated from the agent
system's HTML workflows under ``extension/workflow/``.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple
from xml.sax.saxutils import escape, quoteattr

from autogenesis.canvas.types import (
    CALLABLE_STEPS,
    FlowGraph,
    GraphNode,
    STEP_TYPES,
    workflow_name_for,
)
from autogenesis.workflow.compiler import WorkflowCompiler
from autogenesis.workflow.types import WorkflowDefinition


class CanvasCompileError(ValueError):
    """A graph cannot be compiled; the message lists every problem found."""


class CanvasCompiler:
    """Compile a canvas :class:`FlowGraph` to ``<workflow>`` HTML (and validate
    it through the real :class:`WorkflowCompiler`). Mirrors that class's shape —
    a stateless compiler used via the shared :data:`canvas_compiler` singleton.
    """

    _REF = re.compile(r"\$\{([A-Za-z][A-Za-z0-9_-]*)")

    # Graph attrs (python names) -> workflow HTML attribute names.
    _ATTR_NAMES = {
        "retries": "retries",
        "retry_delay": "retry-delay",
        "retry_backoff": "retry-backoff",
        "timeout": "timeout",
        "concurrency": "concurrency",
        "max_rounds": "max-rounds",
        "no_progress_limit": "no-progress-limit",
        "min_votes": "min-votes",
    }

    def compile(self, graph: FlowGraph) -> Tuple[str, WorkflowDefinition]:
        """Return ``(html, compiled_definition)`` or raise ``CanvasCompileError``.

        The canvas keeps JSON as its source of truth and stores nothing as HTML;
        the ``html`` here is a transient validation artifact, and callers use the
        ``WorkflowDefinition`` to run the flow ephemerally on the shared runtime.
        """
        errors: List[str] = []
        nodes = {node.id: node for node in graph.nodes}
        if len(nodes) != len(graph.nodes):
            errors.append("Duplicate node ids")

        steps = [node for node in graph.nodes if node.type == "step"]
        inputs = [node for node in graph.nodes if node.type == "input"]
        outputs = [node for node in graph.nodes if node.type == "output"]
        if not steps:
            errors.append("The flow has no steps")
        for node in steps:
            if node.step_type not in STEP_TYPES:
                errors.append(f"Node {node.id} has an unsupported step type: {node.step_type!r}")
            if node.step_type in CALLABLE_STEPS and not node.target:
                errors.append(f"Node {node.id} ({node.step_type}) has no capability selected")
        for node in inputs:
            if not node.name:
                errors.append(f"Input node {node.id} has no name")
        seen_inputs: Set[str] = set()
        for node in inputs:
            if node.name in seen_inputs:
                errors.append(f"Duplicate input name: {node.name}")
            seen_inputs.add(node.name)

        bindings: Dict[Tuple[str, str], str] = {}
        for edge in graph.edges:
            source, target = nodes.get(edge.source), nodes.get(edge.target)
            if source is None or target is None:
                errors.append(f"Edge {edge.id} references a missing node")
                continue
            if source.type == "output":
                errors.append(f"Edge {edge.id} starts at an output node")
                continue
            # Agent capability mounts (mount:<type>) accept MANY capability edges
            # and are collected into allowlist args below, not as data bindings.
            if edge.param.startswith("mount:"):
                continue
            port = edge.source_port or "out"
            # Control-flow outputs (Langflow model) are not ordinary data refs:
            #  - branch true/false are CONTROL edges — they define body membership
            #    (see _assign_bodies) and carry no data binding.
            #  - loop/map "item" edge → the body reads the current item variable.
            #  - "done" edge → the aggregated/final result (the whole node value).
            if source.step_type in ("branch", "loop", "map") and port in ("true", "false"):
                continue
            key = (edge.target, edge.param)
            if key in bindings:
                errors.append(f"{edge.target}.{edge.param} has more than one incoming edge")
            # A frozen source with a captured output substitutes a literal (JSON)
            # in place of a ${...} reference, so the frozen node need not run.
            if self._is_frozen(source):
                bindings[key] = self._frozen_literal(source, edge.source_port)
            elif source.step_type in ("map", "loop") and port == "item":
                item_name = str((source.attrs or {}).get("item_name") or "item")
                bindings[key] = f"${{{item_name}}}"
            elif source.step_type in ("branch", "loop", "map") and port == "done":
                bindings[key] = f"${{{source.id}}}"
            else:
                bindings[key] = self._ref(source, edge.source_port)
            if edge.param.startswith("arg:"):
                arg_name = edge.param[4:]
                literal = target.args.get(arg_name)
                if isinstance(literal, str) and literal.strip():
                    errors.append(
                        f"{edge.target}.{arg_name} is both connected and set to a literal value; clear one"
                    )
        if errors:
            raise CanvasCompileError("; ".join(errors))

        self._assign_bodies(graph)
        ordered = self._ordered_children(graph, parent=None, slot="body")
        lines: List[str] = []
        self._emit_steps(ordered, graph, bindings, lines, indent=4)

        name = workflow_name_for(graph)
        html = self._document(graph, name, inputs, outputs, bindings, lines, source_comment=None)
        try:
            definition = WorkflowCompiler().compile(html)
        except Exception as exc:
            raise CanvasCompileError(f"Compiled workflow failed validation: {exc}") from exc
        return html, definition

    @staticmethod
    def _is_frozen(node: GraphNode) -> bool:
        """A node whose last output is captured and pinned — skip re-execution."""
        return bool(getattr(node, "frozen", False)) and getattr(node, "frozen_output", None) is not None

    @staticmethod
    def _frozen_literal(node: GraphNode, source_port: str = "out") -> str:
        """The frozen node's captured sub-value as a literal arg (JSON for non-text)."""
        output = node.frozen_output or {}
        value = output if (source_port == "out" or not source_port) else output.get(source_port)
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)

    @staticmethod
    def _ref(node: GraphNode, source_port: str = "out") -> str:
        """Reference to a source node's output port.

        ``message``/``data``/``files`` compile to ``${node.<port>}`` (a sub-path
        into the capability's ``{message, data, files}`` result); ``out`` (or an
        input node, which has no sub-ports) compiles to the whole ``${node}``.
        """
        base = f"inputs.{node.name}" if node.type == "input" else node.id
        if source_port and source_port != "out" and node.type != "input":
            return f"${{{base}.{source_port}}}"
        return f"${{{base}}}"

    # Control-flow output ports (branch true/false, loop/map item) → nested body.
    _CF_PORTS: Dict[str, List[Tuple[str, str]]] = {
        "branch": [("true", "then"), ("false", "else")],
        "map": [("item", "body")],
        "loop": [("item", "body")],
    }

    def _assign_bodies(self, graph: FlowGraph) -> None:
        """Derive each step's (parent, slot) from control-flow output edges — the
        Langflow model (regular nodes wired by ports) mapped onto the runtime's
        nested then/else/body so ``_emit_steps`` is unchanged.

        A node belongs to a control-flow node CF's body via output port P when the
        (CF, P) edges are a *cut* for it: removing them makes the node unreachable
        from the graph roots. Nesting resolves to the innermost owner (the CF with
        the smallest body). Reference-only ``${id}`` bodies still work because the
        connected canvas uses real edges from the control node's output ports.
        """
        step_ids = {node.id for node in graph.nodes if node.type == "step"}
        nodes_by_id = {node.id: node for node in graph.nodes}
        out_edges: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
        for edge in graph.edges:
            out_edges[edge.source].append((edge.target, edge.source_port or "out"))
        targets = {edge.target for edge in graph.edges}
        roots = [node.id for node in graph.nodes if node.id not in targets]

        def reach(exclude: Set[Tuple[str, str]]) -> Set[str]:
            seen, stack = set(roots), list(roots)
            while stack:
                current = stack.pop()
                for target_id, port in out_edges.get(current, []):
                    if (current, port) in exclude or target_id in seen:
                        continue
                    seen.add(target_id)
                    stack.append(target_id)
            return seen

        reachable_all = reach(set())
        claims: Dict[str, List[Tuple[int, str, str]]] = defaultdict(list)
        for cf in graph.nodes:
            if cf.type != "step" or cf.step_type not in self._CF_PORTS:
                continue
            for port, slot in self._CF_PORTS[cf.step_type]:
                body = ((reachable_all - reach({(cf.id, port)})) - {cf.id}) & step_ids
                for node_id in body:
                    claims[node_id].append((len(body), cf.id, slot))
        for node_id, options in claims.items():
            options.sort()  # smallest body first → the innermost enclosing control node
            _, cf_id, slot = options[0]
            node = nodes_by_id.get(node_id)
            if node is not None:
                node.parent = cf_id
                node.slot = slot

    def _ordered_children(self, graph: FlowGraph, parent: str | None, slot: str) -> List[GraphNode]:
        """Steps under one container slot, topologically ordered by data references
        (bindings + inline ``${id}`` text refs), position as the tiebreaker."""
        children = [
            node for node in graph.nodes
            if node.type == "step" and node.parent == parent and (parent is None or node.slot == slot)
        ]
        ids = {node.id for node in children}
        incoming: Dict[str, Set[str]] = defaultdict(set)
        for edge in graph.edges:
            if edge.target in ids and edge.source in ids:
                incoming[edge.target].add(edge.source)
        for node in children:
            for text in (node.task, node.items, *[str(v) for v in node.args.values()]):
                for match in self._REF.finditer(text or ""):
                    if match.group(1) in ids and match.group(1) != node.id:
                        incoming[node.id].add(match.group(1))

        remaining = {node.id: node for node in children}
        ordered: List[GraphNode] = []
        while remaining:
            ready = [node for node in remaining.values() if not (incoming[node.id] & remaining.keys())]
            if not ready:  # reference cycle — keep a stable order; the runtime will report it
                ready = list(remaining.values())
            ready.sort(key=lambda node: (node.position.y, node.position.x, node.id))
            first = ready[0]
            ordered.append(first)
            del remaining[first.id]
        return ordered

    def _emit_steps(self, nodes: List[GraphNode], graph: FlowGraph,
                    bindings: Dict[Tuple[str, str], str], lines: List[str], indent: int) -> None:
        pad = " " * indent
        for node in nodes:
            if self._is_frozen(node):
                continue  # its output is inlined as a literal; the step does not run
            tag = node.step_type or "tool"
            attrs: List[str] = [f"id={quoteattr(node.id)}"]
            if node.target:
                attrs.append(f"name={quoteattr(node.target)}")
            # A connected task input (e.g. map/loop item edge → child task) binds
            # here; a typed task is the fallback.
            task = (bindings.get((node.id, "task")) or node.task or "").strip()
            if task:
                attrs.append(f"task={quoteattr(task)}")
            items = bindings.get((node.id, "items")) or (node.items or "").strip()
            if items:
                attrs.append(f"items={quoteattr(items)}")
            raw_attrs = node.attrs or {}
            if raw_attrs.get("item_name"):
                attrs.append(f"as={quoteattr(str(raw_attrs['item_name']))}")
            condition = str(raw_attrs.get("condition") or "").strip()
            if tag == "branch" and condition:
                attrs.append(f"test={quoteattr(condition)}")
            elif tag == "loop" and condition:
                mode = "while" if raw_attrs.get("condition_mode") == "while" else "until"
                attrs.append(f"{mode}={quoteattr(condition)}")
            for python_name, html_name in self._ATTR_NAMES.items():
                value = raw_attrs.get(python_name)
                if value is None or value == "":
                    continue
                attrs.append(f"{html_name}={quoteattr(str(value))}")

            args = {
                name: str(value)
                for name, value in (node.args or {}).items()
                if value is not None and str(value).strip() != ""
            }
            for (target_id, param), ref in bindings.items():
                if target_id == node.id and param.startswith("arg:"):
                    args[param[4:]] = ref

            # Agent capability mounts → allowlist args (tools/skills/connectors/...).
            # A non-empty selection scopes the agent to exactly those; an empty one
            # is omitted so the agent keeps its defaults. The runtime lifts these
            # args into ctx.extra["<type>_allowlist"].
            if tag == "agent":
                # Two ways to mount a capability, merged: the node's picker
                # selection (node.mounts) AND edges wired into the agent's
                # mount:<type> input ports (Langflow-style — connect a tool node
                # to the agent). Each edge contributes its source capability name.
                mounted: Dict[str, List[str]] = {k: list(v) for k, v in (node.mounts or {}).items()}
                nodes_by_id = {other.id: other for other in graph.nodes}
                for edge in graph.edges:
                    if edge.target == node.id and edge.param.startswith("mount:"):
                        mount_type = edge.param[len("mount:"):]
                        src = nodes_by_id.get(edge.source)
                        cap = (src.target if src and src.target else edge.source) if src else edge.source
                        mounted.setdefault(mount_type, []).append(cap)
                for mount_type, names in mounted.items():
                    selected = [str(n) for n in names if str(n).strip()]
                    if selected:
                        args[mount_type] = ",".join(dict.fromkeys(selected))

            children_then = self._ordered_children(graph, parent=node.id, slot="then" if tag == "branch" else "body")
            children_else = self._ordered_children(graph, parent=node.id, slot="else") if tag == "branch" else []
            has_body = bool(args or children_then or children_else)
            opening = f"{pad}<{tag} {' '.join(attrs)}"
            if not has_body:
                lines.append(opening + " />")
                continue
            lines.append(opening + ">")
            for name, value in args.items():
                lines.append(f"{pad}  <arg name={quoteattr(name)} value={quoteattr(value)} />")
            if tag == "branch":
                lines.append(f"{pad}  <then>")
                self._emit_steps(children_then, graph, bindings, lines, indent + 4)
                lines.append(f"{pad}  </then>")
                if children_else:
                    lines.append(f"{pad}  <else>")
                    self._emit_steps(children_else, graph, bindings, lines, indent + 4)
                    lines.append(f"{pad}  </else>")
            else:
                self._emit_steps(children_then, graph, bindings, lines, indent + 2)
            lines.append(f"{pad}</{tag}>")

    def _document(self, graph: FlowGraph, name: str, inputs: List[GraphNode], outputs: List[GraphNode],
                  bindings: Dict[Tuple[str, str], str], flow_lines: List[str],
                  source_comment: Optional[str] = None) -> str:
        input_lines: List[str] = []
        for node in sorted(inputs, key=lambda item: (item.position.y, item.position.x)):
            attrs = [
                f"name={quoteattr(node.name)}",
                f"type={quoteattr(node.input_type or 'string')}",
                f"required={quoteattr('true' if node.required else 'false')}",
            ]
            if node.default not in (None, ""):
                attrs.append(f"default={quoteattr(str(node.default))}")
            if node.description:
                attrs.append(f"description={quoteattr(node.description)}")
            input_lines.append(f"    <input {' '.join(attrs)} />")

        output_lines: List[str] = []
        for node in sorted(outputs, key=lambda item: (item.position.y, item.position.x)):
            value = bindings.get((node.id, "value")) or (node.value or "").strip()
            if not value:
                continue
            # Output names are workflow identifiers: slugify whatever the user
            # typed (e.g. "code agent" -> "code_agent") so it never fails validation.
            safe = re.sub(r"[^A-Za-z0-9_]+", "_", node.name or "output").strip("_") or "output"
            if not safe[0].isalpha():
                safe = f"out_{safe}"
            output_lines.append(f"    <output name={quoteattr(safe)} value={quoteattr(value)} />")

        description = graph.description or f"Canvas flow: {graph.name}"
        parts = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="UTF-8">',
            f"  <meta name=\"name\" content={quoteattr(name)}>",
            f"  <meta name=\"description\" content={quoteattr(description)}>",
            f"  <meta name=\"version\" content={quoteattr(graph.version)}>",
            '  <meta name="generated-by" content="canvas">',
            f"  <title>{escape(graph.name)} · Canvas Workflow</title>",
            "</head>",
            "<body>",
            "<!-- Generated by the Autogenesis canvas. Do not edit by hand: open the flow",
            "     in the canvas instead — this file is overwritten on every publish. -->",
            "<workflow",
            f"  name={quoteattr(name)}",
            '  schema-version="1.1.0"',
            f"  version={quoteattr(graph.version)}",
            f"  description={quoteattr(description)}",
            # Canvas flows republish through extension_manager.add_component, whose
            # evolvable gate refuses frozen components — so they must stay evolvable.
            '  enable-evolving="true">',
        ]
        if input_lines:
            parts.append("  <inputs>")
            parts.extend(input_lines)
            parts.append("  </inputs>")
        parts.append("  <flow>")
        parts.extend(flow_lines)
        parts.append("  </flow>")
        if output_lines:
            parts.append("  <outputs>")
            parts.extend(output_lines)
            parts.append("  </outputs>")
        parts.append("</workflow>")
        if source_comment:
            parts.append(source_comment)
        parts.extend(["</body>", "</html>"])
        return "\n".join(parts) + "\n"


canvas_compiler = CanvasCompiler()

__all__ = ["CanvasCompileError", "CanvasCompiler", "canvas_compiler"]
