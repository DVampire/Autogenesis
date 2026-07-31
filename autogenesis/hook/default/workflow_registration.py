"""Register generated/evolved Workflow HTML through the extension lifecycle."""

import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from autogenesis.hook.types import Hook, HookContext, HookResult
from autogenesis.logger import logger
from autogenesis.registry import HOOK


@HOOK.register_module(force=True)
class WorkflowRegistrationHook(Hook):
    """Resolve one staged HTML artifact and register it as a live extension."""

    name: str = "workflow_registration_hook"
    description: str = "Validates and registers generated Workflow HTML as an active extension."
    priority: int = 10

    async def handle(self, ctx: HookContext) -> HookResult:
        """Locate the generated Workflow HTML, activate and compile it, then register it.

        Fired after a workflow-generating run calls ``done_tool``. Resolves the
        staged ``.html`` artifact, verifies it is a complete ``<html>`` document
        containing a ``<workflow>`` element, marks that element ``active`` and
        ``enable-evolving``, and compiles it to validate before atomically
        rewriting the file. The (possibly promoted) artifact is then registered
        as a live workflow extension.

        Args:
            ctx: Hook context whose ``input`` carries ``target_name``,
                ``artifact_path``, ``reasoning`` and ``extension_root``.

        Returns:
            ``HookResult.allow()`` on success, or ``HookResult.block(reason)``
            when the HTML cannot be located, is malformed, or fails to compile.
        """
        extra = ctx.input or {}
        path = self._resolve(
            extra.get("target_name"), extra.get("artifact_path"),
            extra.get("reasoning") or "", extra.get("extension_root") or "",
        )
        if not path:
            return HookResult.block(
                "[registration failed] Could not locate the generated Workflow HTML. "
                "Include its absolute extension/workflow/*.html path in done_tool reasoning."
            )
        try:
            # Match Tool/Skill evolution: a validated registration is live immediately.
            from lxml import html
            from autogenesis.workflow import workflow_compiler
            from autogenesis.sandbox.project import is_staged_extension_root, validate_staged_extension

            if is_staged_extension_root(extra.get("extension_root") or ""):
                validate_staged_extension(extra["extension_root"])

            source_path = Path(path)
            raw_source = source_path.read_text(encoding="utf-8")
            if not re.match(r"^\s*<!DOCTYPE\s+html", raw_source, re.IGNORECASE):
                raise ValueError("Generated Workflow must be a complete HTML document with DOCTYPE")
            tree = html.fromstring(raw_source)
            if tree.tag.lower() != "html":
                raise ValueError("Generated Workflow root element must be <html>")
            node = tree if tree.tag == "workflow" else tree.find(".//workflow")
            if node is None:
                raise ValueError("HTML must contain a <workflow> element")
            node.set("status", "active")
            node.set("enable-evolving", "true")
            doctype = tree.getroottree().docinfo.doctype
            source = html.tostring(tree, encoding="unicode", pretty_print=True)
            if doctype:
                source = f"{doctype}\n{source}"
            workflow_compiler.compile(source)  # validate before mutating the artifact
            fd, temporary = tempfile.mkstemp(prefix=f".{source_path.name}-", dir=source_path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(source)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, source_path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)

            if is_staged_extension_root(extra.get("extension_root") or ""):
                from autogenesis.hook.promotion import promote_approved_component
                path = promote_approved_component(extra["extension_root"], path)

            from autogenesis.extension import extension_manager
            name = await extension_manager.add_component("workflow", path)
            logger.info(f"| 🔄 WorkflowRegistrationHook: registered active '{name}' from {path}")
            return HookResult.allow()
        except Exception as exc:
            logger.warning(f"| ⚠️ WorkflowRegistrationHook: {exc}")
            return HookResult.block(f"[registration failed] {exc}")

    @staticmethod
    def _resolve(
        target_name: Optional[str], artifact_path: Optional[str], reasoning: str,
        extension_root: str,
    ) -> Optional[str]:
        """Find the generated Workflow ``.html`` file referenced by the run.

        Considers an explicit ``artifact_path`` first, then any ``*.html`` path
        (quoted or bare) mentioned in the reasoning, keeping only candidates whose
        path contains ``workflow``; relative paths are resolved against
        ``extension_root``. Falls back to the staged path from ``target_name``.

        Returns:
            The existing Workflow HTML path, or ``None`` if none resolves.
        """
        candidates = [artifact_path] if artifact_path else []
        for match in re.finditer(
            r"(?P<quote>[`'\"])(?P<path>.+?\.html)(?P=quote)|(?P<bare>\S+\.html)",
            reasoning,
        ):
            candidates.append(match.group("path") or match.group("bare"))
        for raw in candidates:
            candidate = str(raw).strip("`'\".,;:()")
            if candidate.endswith(".html") and "workflow" in candidate:
                if not os.path.isabs(candidate):
                    candidate = os.path.join(extension_root, candidate.removeprefix("extension/"))
                if os.path.isfile(candidate):
                    return candidate
        if target_name:
            from autogenesis.extension import extension_manager
            candidate = extension_manager.stage_path("workflow", f"{target_name}.html")
            return candidate if os.path.isfile(candidate) else None
        return None
