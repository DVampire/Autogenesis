"""skill manager Server — Skill Context Protocol.

Server implementation that mirrors the tool manager (Tool Context Protocol) pattern,
providing a unified interface for skill discovery, loading, registration,
update, and execution.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from autogenesis.logger import logger
from autogenesis.config import config
from autogenesis.skill.context import SkillContextManager
from autogenesis.skill.types import SkillConfig, SkillContext
from autogenesis.response.types import Response, ResponseType
from autogenesis.session import SessionContext
from autogenesis.utils import assemble_workspace_path
from autogenesis.capability import CapabilitySchema, SchemaSource


class SkillManagerServer(BaseModel):
    """skill manager Server for managing skill registration and context generation."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    base_dir: str = Field(default=None, description="Base directory for skill data")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.skill_context_manager: Optional[SkillContextManager] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _ensure_context_manager(self) -> SkillContextManager:
        """Lazily create the context manager so methods work before initialize() is called."""
        if self.skill_context_manager is None:
            self.skill_context_manager = SkillContextManager()
        return self.skill_context_manager

    async def initialize(self, skill_names: Optional[List[str]] = None):
        """Initialize skills by scanning default (and custom) skill directories.

        Args:
            skill_names: If provided, only these skills are loaded.
        """
        self.base_dir = assemble_workspace_path(os.path.join(config.log_root, "skill"))
        logger.info(
            f"| 📁 skill manager Server base directory: {self.base_dir} "
        )

        self.skill_context_manager = SkillContextManager(
            base_dir=self.base_dir,
        )
        await self._ensure_context_manager().initialize(skill_names=skill_names)

        logger.info("| ✅ Skills initialization completed")

    async def cleanup(self):
        """Release all skills."""
        await self._ensure_context_manager().cleanup()

    # ------------------------------------------------------------------
    # Register / Update / Unregister / Copy / Restore
    # ------------------------------------------------------------------

    async def register(
        self,
        skill_dir: str,
        override: bool = False,
        version: Optional[str] = None,
        enable_evolving: Optional[bool] = None,
    ) -> SkillConfig:
        """Register a skill from a directory containing SKILL.md.

        Args:
            skill_dir: Path to the skill directory.
            override: If True, overwrite an existing skill with the same name.
            version: Explicit version string.
            enable_evolving: If not None, override the frontmatter-parsed evolvability flag.

        Returns:
            The registered SkillConfig.
        """
        return await self._ensure_context_manager().register(
            skill_dir=skill_dir,
            override=override,
            version=version,
            enable_evolving=enable_evolving,
        )

    async def update(
        self,
        name: str,
        skill_dir: Optional[str] = None,
        new_version: Optional[str] = None,
        description: Optional[str] = None,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SkillConfig:
        """Update an existing skill and create a new version.

        Args:
            name: Skill name.
            skill_dir: If provided, re-parse this directory.
            new_version: Explicit new version string.
            description: Override description.
            content: Override SKILL.md body content.
            metadata: Override metadata dict.

        Returns:
            Updated SkillConfig.
        """
        return await self._ensure_context_manager().update(
            name=name,
            skill_dir=skill_dir,
            new_version=new_version,
            description=description,
            content=content,
            metadata=metadata,
        )

    async def unregister(self, name: str) -> bool:
        """Remove a skill.

        Args:
            name: Skill name.

        Returns:
            True if removed, False if not found.
        """
        return await self._ensure_context_manager().unregister(name)

    async def copy(
        self,
        name: str,
        new_name: Optional[str] = None,
        new_version: Optional[str] = None,
        new_skill_dir: Optional[str] = None,
    ) -> SkillConfig:
        """Copy an existing skill, optionally under a new name.

        Args:
            name: Source skill name.
            new_name: Name for the copy.
            new_version: Version for the copy.
            new_skill_dir: If provided, physically copies the skill directory.

        Returns:
            New SkillConfig.
        """
        return await self._ensure_context_manager().copy(
            name=name,
            new_name=new_name,
            new_version=new_version,
            new_skill_dir=new_skill_dir,
        )

    async def restore(self, name: str, version: str) -> Optional[SkillConfig]:
        """Restore a specific version of a skill from history.

        Args:
            name: Skill name.
            version: Version string to restore.

        Returns:
            Restored SkillConfig, or None if not found.
        """
        return await self._ensure_context_manager().restore(name, version)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    async def get(self, skill_name: str) -> Optional[SkillConfig]:
        """Get a loaded skill by name."""
        return await self._ensure_context_manager().get(skill_name)

    async def get_info(self, skill_name: str) -> Optional[SkillConfig]:
        """Get skill configuration by name."""
        return await self._ensure_context_manager().get_info(skill_name)

    async def list(self) -> List[str]:
        """List all loaded skill names."""
        return await self._ensure_context_manager().list()

    # ------------------------------------------------------------------
    # Context & Contract
    # ------------------------------------------------------------------

    async def get_instruction(self, allowlist: Optional[List[str]] = None, types: Optional[List[str]] = None) -> str:
        """Assemble the skill instruction text for prompt injection.

        `allowlist` (skill names) selects which skills to include (None = all, [] = none).
        `types` filters by frontmatter type (["worker"] for sub-agents, ["orchestrator"]
        for the MetaAgent). Cached per (allowlist, types) until the registry changes.
        """
        return await self._ensure_context_manager().get_instruction(allowlist=allowlist, types=types)

    async def function_callings(
        self, allowlist: Optional[List[str]] = None, types: Optional[List[str]] = None
    ) -> List[Tuple[Dict[str, Any], Tuple[Any, ...]]]:
        """Native tool-calling schemas for the selected skills, each paired with its
        dispatch route. Arguments come from SKILL.md ``input_schema``; an omitted
        declaration means a strict no-argument Skill. The name is the skill's own
        registered name (already ``*_skill``, no prefixing).

        ``types`` filters by frontmatter type (["worker"] for sub-agents, ["orchestrator"]
        for the MetaAgent). Returns ``[(function_calling, ("skill", name)), ...]``.
        """
        names = allowlist if allowlist is not None else await self.list()
        allowed = set(types) if types else None
        out: List[Tuple[Dict[str, Any], Tuple[Any, ...]]] = []
        for n in names:
            info = await self.get_info(n)
            if info is None:
                continue
            stype = getattr(info, "type", None)
            if allowed and stype:
                have = {stype} if isinstance(stype, str) else set(stype)
                if not (have & allowed):
                    continue
            fc = await self.get_schema(n, format="json")
            out.append((fc, ("skill", n)))
        return out

    async def get_schema(self, name: str, action: Optional[str] = None, format: str = "json"):
        """Return the SKILL.md frontmatter input_schema as JSON or Markdown."""
        info = await self.get_info(name)
        if info is None:
            return None
        parameters = getattr(info, "input_schema", None) or {
            "type": "object", "properties": {}, "additionalProperties": False,
        }
        return CapabilitySchema(
            name=name, description=getattr(info, "description", "") or name,
            parameters=parameters,
            strict=parameters.get("additionalProperties") is False,
            source=SchemaSource.DECLARED,
        ).render(format)

    # ------------------------------------------------------------------
    # Skill execution
    # ------------------------------------------------------------------

    async def __call__(
        self,
        name: str,
        input: Dict[str, Any],
        ctx: SkillContext = None,
        **kwargs,
    ) -> Response:
        """Execute a skill by name.

        Args:
            name: Skill name.
            input: User-provided arguments.
            ctx: Skill context.
        """
        # Ensure ctx is always an SkillContext instance
        ctx = SkillContext.from_context(ctx) if ctx else SkillContext(name=name, input=input)

        return await self._ensure_context_manager()(
            name=name,
            input=input,
            ctx=ctx,
            **kwargs,
        )


# Global skill manager instance
skill_manager = SkillManagerServer()
