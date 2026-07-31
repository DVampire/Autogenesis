"""Compile a constrained HTML workflow document into safe internal instructions."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from lxml import html
from jsonschema import Draft202012Validator

from .types import StepType, WorkflowDefinition, WorkflowInput, WorkflowStatus, WorkflowStep

_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
_SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_EXPRESSION = re.compile(r"\$\{([^{}]+)\}")
_STEP_TAGS = {item.value for item in StepType}


class WorkflowCompileError(ValueError):
    pass


class WorkflowCompiler:
    """Parser for Workflow HTML schema version 1.x.

    The compiler deliberately accepts only orchestration tags. It never evaluates
    embedded JavaScript, Python, event handlers, or arbitrary template code.
    """

    SCHEMA_VERSION = "1.1.0"
    def compile_file(self, path: str | Path) -> WorkflowDefinition:
        """Compile a persisted Workflow HTML file into a WorkflowDefinition.

        Persisted artifacts must be complete ``<!DOCTYPE html>`` documents rooted at
        ``<html>`` (unlike ephemeral fragments accepted by :meth:`compile`).

        Args:
            path: Filesystem path to the Workflow HTML document.

        Returns:
            The compiled definition, with ``source_path`` set to the resolved path.

        Raises:
            WorkflowCompileError: If the file is not a complete HTML document or fails
                compilation.
        """
        path = Path(path).resolve()
        source = path.read_text(encoding="utf-8")
        if not re.match(r"^\s*<!DOCTYPE\s+html", source, re.IGNORECASE):
            raise WorkflowCompileError("Persisted Workflow must be a complete HTML document with DOCTYPE")
        if html.fromstring(source).tag.lower() != "html":
            raise WorkflowCompileError("Persisted Workflow root element must be <html>")
        definition = self.compile(source)
        return definition.model_copy(update={"source_path": str(path)})

    def compile(self, source: str) -> WorkflowDefinition:
        """Parse and validate a Workflow HTML source string into a WorkflowDefinition.

        Enforces the restricted HTML language: exactly one ``<workflow>`` root with a
        ``<flow>`` section, valid identifiers, semantic versions, a compatible schema
        major version, outputs that reference only inputs or guaranteed top-level steps,
        and bounded budget attributes. A stable ``program_hash`` is computed over the
        executable contract so later registrations and checkpoints can detect drift.

        Args:
            source: The Workflow HTML source (document or fragment).

        Returns:
            The compiled definition with its executable ``program_hash`` populated.

        Raises:
            WorkflowCompileError: On any malformed, unsafe, or unbounded program.
        """
        try:
            root = html.fromstring(source)
        except Exception as exc:
            raise WorkflowCompileError(f"Invalid workflow HTML: {exc}") from exc
        workflows = [root] if root.tag == "workflow" else root.findall(".//workflow")
        if len(workflows) != 1:
            raise WorkflowCompileError("Document must contain exactly one <workflow> root")
        workflow = workflows[0]
        self._validate_html_shell(root)
        name = workflow.get("name", "")
        if not _ID.fullmatch(name):
            raise WorkflowCompileError("workflow@name must be a valid identifier")
        flow = workflow.find("flow")
        if flow is None:
            raise WorkflowCompileError("Workflow requires a <flow> section")

        seen: set[str] = set()
        counter = [0]
        program = self._steps(flow, seen, counter)
        if not program:
            raise WorkflowCompileError("Workflow flow cannot be empty")
        inputs = self._inputs(workflow.find("inputs"))
        outputs = self._outputs(workflow.find("outputs"))
        guaranteed_outputs = {step.id for step in program}
        for output_name, value in outputs.items():
            for reference in _EXPRESSION.findall(value):
                root_name = reference.strip().split(".", 1)[0]
                if root_name != "inputs" and root_name not in guaranteed_outputs:
                    raise WorkflowCompileError(
                        f"Output {output_name!r} must reference a guaranteed top-level step; "
                        f"got {root_name!r}"
                    )
        tags = [" ".join(item.itertext()).strip() for item in workflow.findall("./applicability/tag")]
        applicability_node = workflow.find("applicability")
        applicability = " ".join(applicability_node.itertext()).strip() if applicability_node is not None else ""
        try:
            status = WorkflowStatus(workflow.get("status", "active"))
        except ValueError as exc:
            raise WorkflowCompileError(f"Invalid Workflow status: {workflow.get('status')!r}") from exc
        schema_version = workflow.get("schema-version", self.SCHEMA_VERSION)
        if schema_version.split(".", 1)[0] != self.SCHEMA_VERSION.split(".", 1)[0]:
            raise WorkflowCompileError(
                f"Unsupported workflow schema-version {schema_version}; compiler supports {self.SCHEMA_VERSION}"
            )
        version = workflow.get("version", "1.0.0")
        if not _SEMVER.fullmatch(version):
            raise WorkflowCompileError(f"Invalid semantic workflow version: {version!r}")
        definition = WorkflowDefinition(
            name=name,
            schema_version=schema_version,
            description=workflow.get("description", ""),
            version=version,
            status=status,
            tags=[tag for tag in tags if tag],
            applicability=applicability,
            inputs=inputs,
            program=program,
            outputs=outputs,
            max_agents=self._integer(workflow, "max-agents", 1000, 1, 1000),
            max_concurrency=self._integer(workflow, "max-concurrency", 16, 1, 64),
            max_depth=self._integer(workflow, "max-depth", 8, 1, 32),
            timeout=self._number(workflow.get("timeout")),
            enable_evolving=workflow.get("enable-evolving", "false").lower() == "true",
            source=source,
        )
        digest_payload = definition.model_dump(
            mode="json", exclude={"source", "source_path", "program_hash"},
        )
        program_hash = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        return definition.model_copy(update={"program_hash": program_hash})

    def _steps(
        self, parent, seen: set[str], counter: List[int], *, parent_tag: str | None = None,
    ) -> List[WorkflowStep]:
        """Compile direct children without mutating the parsed HTML tree."""
        result = []
        for element in parent:
            if not isinstance(element.tag, str):
                continue
            tag = element.tag.lower()
            if tag not in _STEP_TAGS:
                label = parent_tag or getattr(parent, "tag", "flow")
                raise WorkflowCompileError(f"Unsupported <{tag}> inside <{label}>")
            counter[0] += 1
            step_id = element.get("id") or f"{tag}_{counter[0]}"
            if not _ID.fullmatch(step_id) or step_id in seen:
                raise WorkflowCompileError(f"Invalid or duplicate step id: {step_id!r}")
            seen.add(step_id)
            children, else_children = [], []
            if tag == "branch":
                then = element.find("then")
                otherwise = element.find("else")
                children = self._steps(then, seen, counter) if then is not None else []
                else_children = self._steps(otherwise, seen, counter) if otherwise is not None else []
            else:
                children = self._steps_from_direct_children(element, seen, counter)
            args = {
                arg.get("name"): arg.get("value", "")
                for arg in element.findall("arg") if arg.get("name")
            }
            if tag in {"connector", "environment"} and element.get("action"):
                args.setdefault("action", element.get("action"))
            step = WorkflowStep(
                type=StepType(tag), id=step_id,
                target=element.get("name") or element.get("agent") or element.get("target"),
                task=element.get("task") or self._child_text(element, "task"),
                args=args,
                items=element.get("items"), item_name=element.get("as", "item"),
                condition=element.get("test") or element.get("until") or element.get("while"),
                condition_mode=("while" if element.get("while") is not None else "until"),
                concurrency=self._optional_integer(element, "concurrency", 1, 64),
                max_rounds=self._optional_integer(element, "max-rounds", 1, 100),
                no_progress_limit=self._integer(element, "no-progress-limit", 0, 0, 20),
                retries=self._integer(element, "retries", 0, 0, 10),
                retry_delay=self._nonnegative_number(element.get("retry-delay"), 0.0),
                retry_backoff=self._number(element.get("retry-backoff")) or 2.0,
                timeout=self._number(element.get("timeout")),
                min_votes=self._integer(element, "min-votes", 1, 1, 100),
                children=children, else_children=else_children,
            )
            self._validate_step(step)
            result.append(step)
        return result

    def _steps_from_direct_children(self, element, seen, counter):
        """Compile a step's nested instructions, skipping ``<arg>``/``<task>`` wrappers."""
        wrappers = {"arg", "task"}
        candidates = [child for child in element if isinstance(child.tag, str) and child.tag.lower() not in wrappers]
        return self._steps(candidates, seen, counter, parent_tag=element.tag) if candidates else []

    @staticmethod
    def _validate_step(step: WorkflowStep) -> None:
        """Enforce per-step structural requirements (targets, items, bounds, actions).

        Raises:
            WorkflowCompileError: If a step is missing a mandatory attribute for its
                type, e.g. a callable without a target, a loop without ``max-rounds``,
                a branch without ``test``, or a connector/environment without an action.
        """
        callable_types = {
            StepType.AGENT, StepType.TOOL, StepType.SKILL, StepType.CONNECTOR,
            StepType.ENVIRONMENT, StepType.WORKFLOW, StepType.REDUCE, StepType.VERIFY,
        }
        if step.type in callable_types and not step.target:
            raise WorkflowCompileError(f"<{step.type.value} id='{step.id}'> requires name/agent")
        if step.type in {StepType.MAP, StepType.VERIFY, StepType.REDUCE} and step.items is None:
            raise WorkflowCompileError(f"<{step.type.value} id='{step.id}'> requires items")
        if step.type == StepType.MAP and not step.children and not step.target:
            raise WorkflowCompileError(f"<map id='{step.id}'> requires a child step or agent")
        if step.type == StepType.LOOP and step.max_rounds is None:
            raise WorkflowCompileError(f"<loop id='{step.id}'> requires bounded max-rounds")
        if step.type == StepType.BRANCH and step.condition is None:
            raise WorkflowCompileError(f"<branch id='{step.id}'> requires test")
        if step.type in {StepType.CONNECTOR, StepType.ENVIRONMENT} and not step.args.get("action"):
            raise WorkflowCompileError(f"<{step.type.value} id='{step.id}'> requires action")

    @staticmethod
    def _inputs(node) -> Dict[str, WorkflowInput]:
        """Compile the ``<inputs>`` section into a name-keyed WorkflowInput map.

        Simple inputs use HTML attributes; complex array/object contracts attach an
        inert sibling ``<schema for="name">`` carrying Draft 2020-12 JSON Schema. Each
        schema is validated, matched to exactly one input, and reconciled against the
        input's declared type.

        Args:
            node: The ``<inputs>`` element, or None if the workflow declares no inputs.

        Returns:
            Mapping of input name to its compiled contract.

        Raises:
            WorkflowCompileError: On invalid/duplicate names, malformed schemas,
                type conflicts, or a schema targeting an unknown input.
        """
        if node is None:
            return {}
        result = {}
        schemas: Dict[str, Any] = {}
        for schema_node in node.findall("schema"):
            target = schema_node.get("for", "")
            if not _ID.fullmatch(target):
                raise WorkflowCompileError(f"Invalid schema target: {target!r}")
            if target in schemas:
                raise WorkflowCompileError(f"Duplicate schema for input: {target!r}")
            schemas[target] = schema_node
        for item in node.findall("input"):
            name = item.get("name", "")
            if not _ID.fullmatch(name):
                raise WorkflowCompileError(f"Invalid input name: {name!r}")
            if name in result:
                raise WorkflowCompileError(f"Duplicate input name: {name!r}")
            # <input> is an HTML void element, so complex schemas are siblings:
            # <input name="files" ...><schema for="files">{...}</schema>.
            schema_node = schemas.pop(name, None)
            if schema_node is not None:
                try:
                    parameter_schema = json.loads("".join(schema_node.itertext()).strip())
                except Exception as exc:
                    raise WorkflowCompileError(f"Invalid JSON Schema for input {name!r}: {exc}") from exc
                if not isinstance(parameter_schema, dict):
                    raise WorkflowCompileError(f"Input {name!r} schema must be a JSON object")
                try:
                    Draft202012Validator.check_schema(parameter_schema)
                except Exception as exc:
                    raise WorkflowCompileError(f"Invalid JSON Schema for input {name!r}: {exc}") from exc
                declared_type = parameter_schema.get("type")
                attribute_type = item.get("type")
                if declared_type and attribute_type and declared_type != attribute_type:
                    raise WorkflowCompileError(
                        f"Input {name!r} type conflicts with its JSON Schema"
                    )
                schema_source = "declared"
            else:
                parameter_schema = {"type": item.get("type", "string")}
                schema_source = (
                    "legacy_fallback" if parameter_schema["type"] in {"array", "object"}
                    else "declared"
                )
            description = item.get("description", "")
            if description:
                parameter_schema.setdefault("description", description)
            result[name] = WorkflowInput(
                name=name, type=item.get("type", "string"),
                required=item.get("required", "false").lower() in {"true", "required", "1"},
                default=WorkflowCompiler._parse_default(item.get("default"), parameter_schema),
                description=description,
                parameter_schema=parameter_schema,
                schema_source=schema_source,
            )
        if schemas:
            raise WorkflowCompileError(f"Schema targets unknown input: {next(iter(schemas))!r}")
        return result

    @staticmethod
    def _parse_default(raw, schema):
        """Parse an input ``default`` attribute, decoding JSON for non-string types.

        Raises:
            WorkflowCompileError: If a non-string default is not valid JSON.
        """
        if raw is None or schema.get("type") == "string":
            return raw
        try:
            return json.loads(raw)
        except Exception as exc:
            raise WorkflowCompileError(f"Invalid JSON default value: {raw!r}") from exc

    @staticmethod
    def _validate_html_shell(root) -> None:
        """Reject executable preview content while allowing the shared renderer."""
        forbidden_elements = {"iframe", "object", "embed", "base", "form"}
        for element in root.iter():
            if not isinstance(element.tag, str):
                continue
            tag = element.tag.lower()
            if tag in forbidden_elements:
                raise WorkflowCompileError(f"Preview element <{tag}> is forbidden")
            if tag == "meta" and element.get("http-equiv"):
                raise WorkflowCompileError("meta http-equiv is forbidden in Workflow previews")
            for key, value in element.attrib.items():
                if key.lower().startswith("on"):
                    raise WorkflowCompileError(f"Event handler attribute {key!r} is forbidden")
                if key.lower() in {"href", "src"}:
                    parsed = urlparse(str(value).strip())
                    if parsed.scheme or parsed.netloc or str(value).strip().startswith("//"):
                        raise WorkflowCompileError("Remote or executable preview URLs are forbidden")
            if tag == "script":
                src = element.get("src", "")
                if (element.text or "").strip() or not src.endswith("visual/js/workflow.js"):
                    raise WorkflowCompileError("Only the shared external Workflow renderer script is allowed")

    @staticmethod
    def _outputs(node) -> Dict[str, str]:
        """Compile the ``<outputs>`` section into a name-to-value-expression map.

        Args:
            node: The ``<outputs>`` element, or None if the workflow declares no outputs.

        Returns:
            Mapping of output name to its raw ``${...}`` value expression.

        Raises:
            WorkflowCompileError: On invalid/duplicate output names or a missing value.
        """
        if node is None:
            return {}
        result: Dict[str, str] = {}
        for item in node.findall("output"):
            name, value = item.get("name", ""), item.get("value")
            if not _ID.fullmatch(name):
                raise WorkflowCompileError(f"Invalid output name: {name!r}")
            if name in result:
                raise WorkflowCompileError(f"Duplicate output name: {name!r}")
            if value is None:
                raise WorkflowCompileError(f"Output {name!r} requires value")
            result[name] = value
        return result

    @staticmethod
    def _child_text(element, name: str) -> str:
        """Return the collapsed text of a named child element, or "" if absent."""
        child = element.find(name)
        return " ".join(child.itertext()).strip() if child is not None else ""

    @staticmethod
    def _integer(element, name, default, minimum, maximum):
        """Read an integer attribute, applying a default and enforcing an inclusive range."""
        try:
            value = int(element.get(name, default))
        except (TypeError, ValueError) as exc:
            raise WorkflowCompileError(f"{name} must be an integer") from exc
        if not minimum <= value <= maximum:
            raise WorkflowCompileError(f"{name} must be between {minimum} and {maximum}")
        return value

    def _optional_integer(self, element, name, minimum, maximum):
        """Read a range-checked integer attribute, or None when the attribute is absent."""
        return None if element.get(name) is None else self._integer(element, name, 0, minimum, maximum)

    @staticmethod
    def _number(value):
        """Parse an optional positive float (e.g. a timeout); None passes through.

        Raises:
            WorkflowCompileError: If the value is non-numeric or not strictly positive.
        """
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise WorkflowCompileError("Numeric value is invalid") from exc
        if result <= 0:
            raise WorkflowCompileError("Timeout must be positive")
        return result

    @staticmethod
    def _nonnegative_number(value, default=0.0):
        """Parse an optional non-negative float (e.g. retry delay), falling back to default.

        Raises:
            WorkflowCompileError: If the value is negative.
        """
        if value is None:
            return default
        result = float(value)
        if result < 0:
            raise WorkflowCompileError("Numeric value must be non-negative")
        return result


workflow_compiler = WorkflowCompiler()

__all__ = ["WorkflowCompileError", "WorkflowCompiler", "workflow_compiler"]
