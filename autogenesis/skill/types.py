"""Skill type definitions for the Skill Context Protocol."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field
from autogenesis.session import BaseContext
from autogenesis.response.types import Response, ResponseType


class SkillContext(BaseContext):
    """Context passed into skill manager and individual skill instances."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default="", description="Unique identifier for this skill invocation.")
    name: str = Field(default="", description="Name of the skill being invoked.")
    workspace_root: Optional[str] = Field(default=None, description="Working directory available to the skill.")
    input: Dict[str, Any] = Field(default_factory=dict, description="Input payload passed to the skill.")
    extra: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extra data attached to this skill context.")


class SkillConfig(BaseModel):
    """Configuration for a loaded skill, parsed from SKILL.md and its directory."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    name: str = Field(description="Skill name from YAML frontmatter")
    description: str = Field(description="Skill description from YAML frontmatter")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional YAML frontmatter fields")
    enable_evolving: bool = Field(default=False, description="Whether the skill is trainable")
    permission_mode: str = Field(default="workspace_write", description="Permission mode: read_only / workspace_write / danger_full_access")
    version: str = Field(default="1.0.0", description="Version of the skill")
    type: Union[str, List[str]] = Field(default="tool", description="Skill type label(s) from YAML frontmatter. May be a single label (e.g. 'worker') or a list of labels (e.g. ['orchestrator', 'worker']) for a skill that serves multiple roles.")
    input_schema: Dict[str, Any] = Field(
        default_factory=lambda: {"type": "object", "properties": {}, "additionalProperties": False},
        description="JSON Schema for native Skill invocation arguments",
    )

    skill_dir: str = Field(description="Absolute path to the skill directory")
    content: str = Field(default="", description="Full markdown body of SKILL.md (after frontmatter)")
    scripts: List[str] = Field(default_factory=list, description="Paths to files under scripts/")
    resources: List[str] = Field(default_factory=list, description="Paths to files under resources/")
    references: List[str] = Field(default_factory=list, description="Paths to reference docs under references/")
    examples: List[str] = Field(default_factory=list, description="Paths to example files under examples/")

    text: Optional[str] = Field(default=None, description="Pre-built text representation for prompt injection")

    @property
    def type_tags(self) -> List[str]:
        """Normalize ``type`` (str or list) to a list of labels for filtering/display."""
        return list(self.type) if isinstance(self.type, list) else [self.type]

    def model_dump(self, **kwargs) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "metadata": self.metadata,
            "enable_evolving": self.enable_evolving,
            "permission_mode": self.permission_mode,
            "version": self.version,
            "type": self.type,
            "input_schema": self.input_schema,
            "skill_dir": self.skill_dir,
            "content": self.content,
            "scripts": self.scripts,
            "resources": self.resources,
            "references": self.references,
            "examples": self.examples,
            "text": self.text,
        }


__all__ = [
    "SkillConfig",
    "SkillContext",
]
