"""Builds the palette and mount rosters.

The canvas is agent-centric (matching Autogenesis): tools/skills/connectors
are not standalone palette nodes — they are *mounted* on an agent through its
capability picker. The palette therefore contains structural steps, io
declarations, the actor agents, and reusable workflows. Evolver agents
(generator/optimizer/evaluator) stay registered for the self-evolution system
but are hidden from the canvas.

The logic lives on :class:`Catalog` (used via the :data:`catalog` singleton);
the icon/port lookup tables below are plain data.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List

from autogenesis.canvas.types import NodeSpec, ParamSpec, PortSpec
from autogenesis.logger import logger

# Which capability rosters an agent node can mount (scope). All are optional:
# leaving a picker empty means the agent uses its configured defaults.
AGENT_MOUNT_TYPES = ["tools", "skills", "connectors", "agents", "environments", "workflows"]

# A capability result normalizes to {message, data, files} — so callable nodes
# expose these three typed output ports (each compiles to ${node.<name>}), plus
# ``out`` for the whole value.
_CAPABILITY_OUTPUTS = [
    PortSpec(name="message", label="Message", type="text", description="The text result."),
    PortSpec(name="data", label="Data", type="object", description="The structured result."),
    PortSpec(name="files", label="Files", type="list", description="Produced file paths."),
    PortSpec(name="out", label="Result", type="any", description="The whole {message, data, files}."),
]

# Tools opt into a standalone canvas node (grouped under this palette category)
# by setting ``metadata["canvas_category"]``. Uncategorized tools stay
# agent-mount-only. The value is also the NodeSpec.category.
CANVAS_TOOL_CATEGORIES = {"data", "files", "knowledge"}

# Per-node lucide icon names (Langflow gives every component its own glyph).
# Resolution order: exact node id → capability target → category fallback.
_ICON_BY_ID = {
    "io/input": "MessagesSquare", "io/output": "MessagesSquare",
    "step/map": "Repeat", "step/branch": "GitBranch", "step/loop": "RotateCw",
    "step/reduce": "Combine", "step/verify": "ShieldCheck", "step/checkpoint": "Flag",
    "data/dataset_save": "UploadCloud", "data/dataset_load": "DownloadCloud",
    "knowledge/knowledge_ingest": "BookPlus", "knowledge/knowledge_retrieve": "BookOpenText",
}
_ICON_BY_TARGET = {
    # data sources
    "yahoo": "CandlestickChart", "fmp": "TrendingUp", "http_request_tool": "Globe",
    # processing
    "select_fields": "Columns3", "head": "Rows3", "sort_records": "ArrowUpDown",
    "rename_fields": "PenLine", "filter_rows": "Filter", "derive_return": "Percent",
    "to_eval_records": "Shuffle",
    "split_text": "Scissors", "regex_extract": "Regex", "parse_json": "Braces",
    "type_convert": "Repeat2", "combine_text": "Merge", "extract_field": "KeyRound",
    "table_operations": "Table2",
    # evaluation
    "exact_match": "Target",
    # file tools
    "read_file_tool": "FileText", "write_file_tool": "FilePlus2", "edit_file_tool": "FilePen",
    "list_dir_tool": "FolderTree", "glob_search_tool": "FileSearch", "grep_search_tool": "Search",
    # actor agents
    "meta_agent": "Sparkles", "general_agent": "Bot", "code_agent": "Code",
    "reviewer_agent": "ShieldCheck", "monitor_agent": "Activity", "browser_agent": "Globe",
}
_ICON_BY_CATEGORY = {
    "io": "Cable", "structural": "Split", "agent": "Sparkles", "data": "Database",
    "process": "SlidersHorizontal", "evaluation": "Target", "files": "FileText",
    "knowledge": "BookOpen", "tool": "Wrench", "workflow": "Network",
}


class Catalog:
    """Assembles the canvas palette (node specs) and the agent mount rosters."""

    async def build(self) -> List[NodeSpec]:
        """Assemble the palette (structural + io + actor agents + capabilities)."""
        agent_names: List[str] = []
        try:
            from autogenesis.agent import agent_manager
            agent_names = await agent_manager.list()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"| ⚠️ Canvas palette: agent registry unavailable: {exc}")

        specs = self._structural_specs(agent_names)

        for name in agent_names:
            try:
                from autogenesis.agent import agent_manager
                info = await agent_manager.get_info(name)
                if info is not None and self._is_actor_agent(info):
                    specs.append(self._agent_spec(name, info))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"| ⚠️ Canvas palette: skipping agent {name}: {exc}")

        # Standalone deterministic tool nodes — only tools that opted in via
        # metadata["canvas_category"] (data/files/knowledge).
        try:
            from autogenesis.tool import tool_manager
            for name in await tool_manager.list():
                try:
                    info = await tool_manager.get_info(name)
                    metadata = getattr(info, "metadata", None) or {}
                    category = metadata.get("canvas_category") if isinstance(metadata, dict) else None
                    if info is not None and category in CANVAS_TOOL_CATEGORIES:
                        specs.append(self._tool_spec(name, info, category))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"| ⚠️ Canvas palette: skipping tool {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"| ⚠️ Canvas palette: tool registry unavailable: {exc}")

        # Data-pipeline nodes: datasource (plugin tools) → process (pure
        # transforms) → benchmark (evaluation). A plugin is a container, so what
        # lands on the canvas is each of its *tools*, as a semantic
        # ``datasource`` node.
        try:
            from autogenesis.plugins import plugin_manager
            for plugin in await plugin_manager.list_infos():
                if plugin.tools:
                    specs.extend(self._plugin_tool_spec(tool) for tool in plugin.tools.values())
                elif getattr(plugin.instance, "type", "") == "data_source":
                    # A plugin that is its own single capability, with no tools.
                    specs.append(self._capability_node_spec(
                        plugin.name, plugin.instance, category="data",
                        step_type="datasource", skip=("timeout",)))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"| ⚠️ Canvas palette: plugin registry unavailable: {exc}")

        try:
            from autogenesis.process import process_manager
            for processor in await process_manager.list_infos():
                specs.append(self._capability_node_spec(
                    processor.name, processor, category="process", step_type="process"))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"| ⚠️ Canvas palette: process registry unavailable: {exc}")

        # Dataset sink/source nodes (persist processed records, or load them back).
        specs.extend(self._data_node_specs())

        # Knowledge (RAG) nodes: ingest documents, retrieve top-k by query.
        try:
            from autogenesis.knowledge import knowledge_manager
            specs.extend(self._knowledge_node_specs(await knowledge_manager.list_types()))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"| ⚠️ Canvas palette: knowledge registry unavailable: {exc}")

        try:
            from autogenesis.benchmark import benchmark_manager
            for name in await benchmark_manager.list():
                try:
                    specs.append(self._benchmark_node_spec(name, await benchmark_manager.get_info(name)))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"| ⚠️ Canvas palette: skipping benchmark {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"| ⚠️ Canvas palette: benchmark registry unavailable: {exc}")

        try:
            from autogenesis.workflow import workflow_manager
            for name in workflow_manager.list():
                try:
                    specs.append(self._workflow_spec(name, workflow_manager.get(name)))
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"| ⚠️ Canvas palette: skipping workflow {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"| ⚠️ Canvas palette: workflow registry unavailable: {exc}")

        return [self._with_ports(spec) for spec in specs]

    async def build_mounts(self) -> Dict[str, List[Dict[str, str]]]:
        """Global capability rosters the agent capability picker selects from."""
        return {name: await self._roster(name) for name in AGENT_MOUNT_TYPES}

    async def _roster(self, mount_type: str) -> List[Dict[str, str]]:
        """Selectable capabilities of one type: [{name, description}]. Agents are
        restricted to actors (the same set the palette shows)."""
        try:
            if mount_type == "tools":
                from autogenesis.tool import tool_manager
                names, get_info = await tool_manager.list(), tool_manager.get_info
            elif mount_type == "skills":
                from autogenesis.skill import skill_manager
                names, get_info = await skill_manager.list(), skill_manager.get_info
            elif mount_type == "connectors":
                from autogenesis.connector import connector_manager
                names, get_info = await connector_manager.list(), connector_manager.get_info
            elif mount_type == "environments":
                from autogenesis.environment import environment_manager
                names, get_info = await environment_manager.list(), environment_manager.get_info
            elif mount_type == "agents":
                from autogenesis.agent import agent_manager
                names, get_info = await agent_manager.list(), agent_manager.get_info
            elif mount_type == "workflows":
                # Published canvas flows / registered workflows an agent can call
                # as a tool — the agent-centric equivalent of Langflow's Tool Mode.
                from autogenesis.workflow import workflow_manager
                names, get_info = workflow_manager.list(), workflow_manager.get
            else:
                return []
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"| ⚠️ Canvas roster: {mount_type} unavailable: {exc}")
            return []

        out: List[Dict[str, str]] = []
        for name in names:
            try:
                info = await get_info(name) if inspect.iscoroutinefunction(get_info) else get_info(name)
            except Exception:  # noqa: BLE001
                info = None
            if mount_type == "agents" and not self._is_actor_agent(info):
                continue
            out.append({"name": name, "description": str(getattr(info, "description", "") or "")})
        return sorted(out, key=lambda item: item["name"])

    # ----- spec builders (pure) ------------------------------------------------

    @staticmethod
    def _is_actor_agent(info: Any) -> bool:
        """True for the user-facing worker agents (autogenesis.agent.actor.*).

        Derived from the class module so the split is self-maintaining: a new
        actor appears automatically, a new evolver agent stays hidden.
        """
        cls = getattr(info, "cls", None)
        module = getattr(cls, "__module__", "") if cls is not None else ""
        if module:
            return ".agent.actor." in module or module.endswith(".agent.actor")
        return False

    @staticmethod
    def _param_from_schema(name: str, schema: Dict[str, Any], required: bool) -> ParamSpec:
        json_type = schema.get("type")
        options = schema.get("enum")
        if isinstance(options, list) and options:
            param_type, options = "select", [str(option) for option in options]
        elif json_type in {"integer", "number"}:
            param_type, options = "number", None
        elif json_type == "boolean":
            param_type, options = "boolean", None
        elif json_type == "string":
            param_type, options = "string", None
        else:
            param_type, options = "json", None
        return ParamSpec(
            name=name,
            label=name.replace("_", " ").capitalize(),
            type=param_type,
            required=required,
            default=schema.get("default"),
            options=options,
            multiline=param_type == "string" and name in {"command", "content", "code", "script", "text", "prompt", "body", "pattern"},
            description=str(schema.get("description", "")),
        )

    def _tool_spec(self, name: str, info: Any, category: str) -> NodeSpec:
        """A standalone deterministic tool node (params from the tool's schema)."""
        function_calling = getattr(info, "function_calling", None) or {}
        function = function_calling.get("function", {}) if isinstance(function_calling, dict) else {}
        parameters = function.get("parameters") if isinstance(function, dict) else None
        params: List[ParamSpec] = []
        if isinstance(parameters, dict):
            required = set(parameters.get("required") or [])
            properties = parameters.get("properties")
            if isinstance(properties, dict):
                params = [
                    self._param_from_schema(key, value if isinstance(value, dict) else {}, key in required)
                    for key, value in properties.items()
                ]
        return NodeSpec(
            id=f"tool/{name}", category=category, step_type="tool", target=name,
            label=name.removesuffix("_tool").replace("_", " ").capitalize(),
            description=str(getattr(info, "description", "") or ""),
            params=params,
        )

    @staticmethod
    def _icon_for(spec: NodeSpec) -> str:
        """Resolve a node's lucide icon: id → target → category → default."""
        return (
            _ICON_BY_ID.get(spec.id)
            or (_ICON_BY_TARGET.get(spec.target) if spec.target else None)
            or _ICON_BY_CATEGORY.get(spec.category)
            or "Box"
        )

    @staticmethod
    def _param_type_from_annotation(annotation: Any) -> str:
        """Best-effort map a ``__call__`` type hint to a canvas ParamType."""
        text = str(annotation)
        if "bool" in text:
            return "boolean"
        if "int" in text or "float" in text:
            return "number"
        if "List" in text or "list" in text or "Dict" in text or "dict" in text:
            return "json"
        if "str" in text:
            return "string"
        return "string"

    def _signature_params(self, instance: Any, skip: tuple = ()) -> List[ParamSpec]:
        """Derive a capability node's form params from its ``__call__`` signature.

        Plugins/processors have no JSON schema, but their ``__call__`` names,
        defaults and annotations are the contract — inspect them directly.
        """
        try:
            signature = inspect.signature(type(instance).__call__)
        except (TypeError, ValueError):
            return []
        params: List[ParamSpec] = []
        for pname, parameter in signature.parameters.items():
            if pname in {"self", "kwargs", "ctx"} or parameter.kind in (
                parameter.VAR_KEYWORD, parameter.VAR_POSITIONAL,
            ) or pname in skip:
                continue
            param_type = self._param_type_from_annotation(parameter.annotation)
            has_default = parameter.default is not inspect.Parameter.empty
            params.append(ParamSpec(
                name=pname,
                label=pname.replace("_", " ").capitalize(),
                type=param_type,
                required=not has_default,
                default=None if not has_default else parameter.default,
                multiline=param_type == "string" and pname in {"body", "text", "content", "pattern", "expression"},
            ))
        return params

    def _capability_node_spec(self, name: str, info: Any, category: str, step_type: str, skip: tuple = ()) -> NodeSpec:
        """A standalone callable node backed by a manager (params from __call__)."""
        return NodeSpec(
            id=f"{step_type}/{name}", category=category, step_type=step_type, target=name,
            label=name.replace("_", " ").capitalize(),
            description=str(getattr(info, "description", "") or ""),
            params=self._signature_params(info, skip=skip),
        )

    def _plugin_tool_spec(self, tool: Any) -> NodeSpec:
        """One tool of a plugin, as a canvas node.

        Nested in the palette's ``plugin`` section under its plugin (by
        ``plugin`` / ``plugin_label``) and carrying that plugin's glyph
        (``icon`` = ``plugin:<id>``, resolved to ``resources/icon.svg`` on the
        frontend). Addressed as ``<plugin>.<tool>``, and executed through the
        shared datasource → ``plugin_manager`` path, which splits the two halves
        and dispatches via the plugin.
        """
        info = tool.public()
        return NodeSpec(
            id=f"datasource/{info['id']}", category="plugin", step_type="datasource",
            target=info["id"],
            label=info["display_name"],
            description=info["description"],
            icon=info["icon"],
            plugin=info["plugin"],
            plugin_label=info["plugin_label"],
            params=self._signature_params(tool, skip=("timeout",)),
        )

    @staticmethod
    def _data_node_specs() -> List[NodeSpec]:
        """The dataset sink/source nodes: save upstream records, or load them back."""
        return [
            NodeSpec(
                id="data/dataset_save", category="data", step_type="data", target="dataset_save",
                label="Save dataset", description="Save records as a HuggingFace dataset (push to the Hub or save locally).",
                params=[
                    ParamSpec(name="repo", label="Repo / name", required=True, connectable=False,
                              description="Hub repo id (namespace/name) or local dataset name."),
                    ParamSpec(name="target", label="Target", type="select", options=["hub", "local"],
                              default="hub", connectable=False),
                    ParamSpec(name="split", label="Split", default="train", connectable=False),
                    ParamSpec(name="private", label="Private", type="boolean", connectable=False),
                    ParamSpec(name="token", label="HF token", connectable=False,
                              description="Hub token (else HF_TOKEN). Public datasets need none."),
                    ParamSpec(name="records", label="Records", type="json",
                              description="Records to save — connect from a process/datasource node."),
                ],
            ),
            NodeSpec(
                id="data/dataset_load", category="data", step_type="data", target="dataset_load",
                label="Load dataset", description="Load a HuggingFace dataset (Hub or local) into the flow.",
                params=[
                    ParamSpec(name="repo", label="Repo / name", required=True, connectable=False,
                              description="Hub repo id (namespace/name) or local dataset name."),
                    ParamSpec(name="source", label="Source", type="select", options=["hub", "local"],
                              default="hub", connectable=False),
                    ParamSpec(name="split", label="Split", default="train", connectable=False),
                    ParamSpec(name="token", label="HF token", connectable=False,
                              description="Hub token (else HF_TOKEN). Public datasets need none."),
                ],
            ),
        ]

    @staticmethod
    def _knowledge_node_specs(types: List[str]) -> List[NodeSpec]:
        """The RAG nodes: ingest documents into a base, retrieve top-k by query."""
        type_options = types or ["bm25"]
        return [
            NodeSpec(
                id="knowledge/knowledge_ingest", category="knowledge", step_type="knowledge", target="knowledge_ingest",
                label="Ingest", description="Add documents to a knowledge base (RAG).",
                params=[
                    ParamSpec(name="base", label="Knowledge base", required=True, connectable=False),
                    ParamSpec(name="type", label="RAG type", type="select", options=type_options,
                              default=type_options[0], connectable=False),
                    ParamSpec(name="text_field", label="Text field", default="text", connectable=False,
                              description="Which record field holds the document text."),
                    ParamSpec(name="documents", label="Documents", type="json",
                              description="Records/text to index — connect from a process/datasource node."),
                ],
            ),
            NodeSpec(
                id="knowledge/knowledge_retrieve", category="knowledge", step_type="knowledge", target="knowledge_retrieve",
                label="Retrieve", description="Retrieve the top-k most relevant documents by query.",
                params=[
                    ParamSpec(name="base", label="Knowledge base", required=True, connectable=False),
                    ParamSpec(name="query", label="Query", multiline=True,
                              description="The search query (connect a step or type text)."),
                    ParamSpec(name="top_k", label="Top K", type="number", default=4, connectable=False),
                ],
            ),
        ]

    @staticmethod
    def _benchmark_node_spec(name: str, info: Any) -> NodeSpec:
        """A benchmark (evaluation) node: takes upstream records, returns a score."""
        return NodeSpec(
            id=f"benchmark/{name}", category="evaluation", step_type="benchmark", target=name,
            label=name.replace("_", " ").capitalize(),
            description=str(getattr(info, "description", "") or ""),
            params=[
                ParamSpec(name="results", label="Results", type="json",
                          description="Records to evaluate: {task_id, prediction, ground_truth}."),
                ParamSpec(name="concurrency", label="Concurrency", type="number", default=10, connectable=False),
            ],
        )

    @staticmethod
    def _param_port_type(param_type: str) -> str:
        return {"string": "text", "json": "object"}.get(param_type, "any")

    def _with_ports(self, spec: NodeSpec) -> NodeSpec:
        """Populate a spec's typed input/output ports (and icon) from its shape."""
        inputs: List[PortSpec] = []
        if spec.has_items:
            inputs.append(PortSpec(name="items", label="Items", type="list"))
        if spec.has_task:
            inputs.append(PortSpec(name="task", label="Task", type="text"))
        if spec.id == "io/output":
            inputs.append(PortSpec(name="value", label="Value", type="any"))
        # Agent capability mount ports (Langflow-style): every agent can mount all
        # six capability kinds — wire nodes into the handle OR multi-select in the
        # box. Each accepts many edges; the compiler folds them into the allowlist.
        for mount_type in AGENT_MOUNT_TYPES:
            if mount_type in (spec.mount_types or []):
                inputs.append(PortSpec(name=f"mount:{mount_type}", label=mount_type.capitalize(), type="any"))
        for param in spec.params:
            if param.connectable:
                inputs.append(PortSpec(name=f"arg:{param.name}", label=param.label, type=self._param_port_type(param.type)))

        # Control-flow specs declare their own output ports (branch true/false,
        # map/loop item/done); honor those. Otherwise derive from the node shape.
        if spec.outputs:
            outputs = list(spec.outputs)
        elif spec.category == "agent" or spec.step_type in ("reduce", "tool", "datasource", "process", "data", "knowledge", "benchmark"):
            outputs = list(_CAPABILITY_OUTPUTS)
        elif spec.id == "io/input":
            outputs = [PortSpec(name="out", label="Value", type="any")]  # frontend colors by input_type
        elif spec.step_type == "verify":
            outputs = [PortSpec(name="out", label="Result", type="list")]
        elif spec.category == "workflow":
            outputs = [PortSpec(name="out", label="Result", type="object")]
        elif spec.id == "io/output":
            outputs = []
        else:  # checkpoint etc.
            outputs = [PortSpec(name="out", label="Result", type="any")]

        spec.inputs = inputs
        spec.outputs = outputs
        if not spec.icon:
            spec.icon = self._icon_for(spec)
        return spec

    @staticmethod
    def _agent_spec(name: str, info: Any) -> NodeSpec:
        return NodeSpec(
            id=f"agent/{name}", category="agent", step_type="agent", target=name,
            label=name.removesuffix("_agent").replace("_", " ").capitalize(),
            description=str(getattr(info, "description", "") or ""),
            has_task=True,
            mount_types=list(AGENT_MOUNT_TYPES),
        )

    @staticmethod
    def _workflow_spec(name: str, definition: Any) -> NodeSpec:
        params = [
            ParamSpec(
                name=input_name,
                label=input_name.replace("_", " ").capitalize(),
                type="string" if getattr(spec, "type", "string") == "string" else "json",
                required=bool(getattr(spec, "required", False)),
                default=getattr(spec, "default", None),
                description=str(getattr(spec, "description", "")),
            )
            for input_name, spec in (getattr(definition, "inputs", {}) or {}).items()
        ]
        return NodeSpec(
            id=f"workflow/{name}", category="workflow", step_type="workflow", target=name,
            label=name.replace("_", " ").capitalize(),
            description=str(getattr(definition, "description", "") or ""),
            params=params,
        )

    @staticmethod
    def _structural_specs(agent_names: List[str]) -> List[NodeSpec]:
        agent_options = sorted(agent_names) or None
        return [
            NodeSpec(
                id="io/input", category="io", label="Chat Input",
                description="Declares one workflow input; reference it anywhere as ${inputs.<name>}.",
                params=[
                    ParamSpec(name="name", label="Name", required=True, connectable=False),
                    ParamSpec(name="input_type", label="Type", type="select",
                              options=["string", "number", "boolean", "array", "object"], connectable=False),
                    ParamSpec(name="required", label="Required", type="boolean", connectable=False),
                    ParamSpec(name="default", label="Default", connectable=False),
                    ParamSpec(name="description", label="Description", multiline=True, connectable=False),
                ],
            ),
            NodeSpec(
                id="io/output", category="io", label="Chat Output",
                description="Publishes one value as a named workflow output.",
                params=[ParamSpec(name="name", label="Name", required=True, connectable=False)],
            ),
            # Control flow is expressed like Langflow: regular nodes with typed
            # output ports wired by edges (no drop-in containers). Map/Loop fan a
            # data input over an `item` output (connect the per-item body, whose
            # tail feeds back) and aggregate into `done`; Branch routes to `true`
            # / `false` output ports. The canvas compiler turns these edges back
            # into the runtime's map/loop/branch bodies.
            NodeSpec(
                id="step/map", category="structural", step_type="map", label="Map",
                description="Fan a list over the body (item output) and collect results (done).",
                has_items=True,
                params=[
                    ParamSpec(name="item_name", label="Item variable", default="item", connectable=False),
                    ParamSpec(name="concurrency", label="Concurrency", type="number", connectable=False),
                ],
                outputs=[
                    PortSpec(name="item", label="Item", type="any", description="The current item — connect the per-item body."),
                    PortSpec(name="done", label="Done", type="list", description="Aggregated results after all items."),
                ],
            ),
            NodeSpec(
                id="step/branch", category="structural", step_type="branch", label="Branch",
                description="Route to the True or False output by a ${...} test expression.",
                params=[ParamSpec(name="condition", label="Test", required=True, multiline=True,
                                  description="e.g. ${check} or a comparison over step results", connectable=False)],
                outputs=[
                    PortSpec(name="true", label="True", type="any", description="Taken when the test is truthy."),
                    PortSpec(name="false", label="False", type="any", description="Taken when the test is falsy."),
                ],
            ),
            NodeSpec(
                id="step/loop", category="structural", step_type="loop", label="Loop",
                description="Repeat the body (item output) until/while a condition; done emits the last result.",
                params=[
                    ParamSpec(name="max_rounds", label="Max rounds", type="number", required=True, connectable=False),
                    ParamSpec(name="condition", label="Condition", multiline=True, connectable=False),
                    ParamSpec(name="condition_mode", label="Mode", type="select",
                              options=["until", "while"], default="until", connectable=False),
                ],
                outputs=[
                    PortSpec(name="item", label="Item", type="any", description="The current round value — connect the body; its tail feeds back."),
                    PortSpec(name="done", label="Done", type="any", description="The value after the loop ends."),
                ],
            ),
            NodeSpec(
                id="step/reduce", category="structural", step_type="reduce", label="Reduce",
                description="Fold a list of results into one via an agent.",
                has_task=True, has_items=True,
                params=[ParamSpec(name="target", label="Agent", type="select", required=True,
                                  options=agent_options, connectable=False)],
            ),
            NodeSpec(
                id="step/verify", category="structural", step_type="verify", label="Verify",
                description="Independently verify each item via an agent.",
                has_task=True, has_items=True,
                params=[
                    ParamSpec(name="target", label="Agent", type="select", required=True,
                              options=agent_options, connectable=False),
                    ParamSpec(name="concurrency", label="Concurrency", type="number", connectable=False),
                    ParamSpec(name="min_votes", label="Min votes", type="number", connectable=False),
                ],
            ),
            NodeSpec(
                id="step/checkpoint", category="structural", step_type="checkpoint", label="Checkpoint",
                description="Persist run state so the workflow can resume from here.",
            ),
        ]


catalog = Catalog()

__all__ = ["AGENT_MOUNT_TYPES", "Catalog", "catalog"]
