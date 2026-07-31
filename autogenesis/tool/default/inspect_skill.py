"""Inspect-skill tool — fetch a registered skill's live registry facts on demand."""
import os
from typing import Dict, Any
from pydantic import Field
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL

_DESCRIPTION = "Fetch a registered skill's live registry facts (registration status, version, evolvability/enable_evolving, skill directory + SKILL.md path) by name."

_INSTRUCTION = """
## Function
Fetch a skill's live registry facts: whether it is registered, its version and type, whether it is evolvable (enable_evolving), and its skill directory + SKILL.md path.

## Guidance
- Use this before optimizing or evaluating a skill named in your task: it reports the target's real state in the registry, which reading files alone cannot.
- Optimization requires enable_evolving=True. If inspect_skill_tool reports enable_evolving=False, the skill is frozen — do NOT optimize it; refuse and report why.
- The returned skill_dir / SKILL.md path tells you exactly which files to read/edit.

## Parameters
- name (str): The exact name of the skill to inspect.

## Example
{"name": "inspect_skill_tool", "args": {"name": "my_skill"}}
"""


@TOOL.register_module(force=True)
class InspectSkill(Tool):
    """Return a registered skill's live registry facts on demand."""

    name: str = "inspect_skill_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, name: str, **kwargs) -> Response:
        """Return live registry facts for the named skill.

        Args:
            name (str): The exact name of the skill to inspect.
        """
        from autogenesis.skill.server import skill_manager  # local import avoids a circular import

        info = await skill_manager.get_info(name)

        lines = [f"- **Skill Name**: `{name}`"]
        if info is None:
            lines.append("- **Registered**: False (not found in registry)")
            available = await skill_manager.list()
            lines.append(f"\nAvailable skills: {available}")
            return Response(
                type=ResponseType.TOOL, success=False, message="\n".join(lines),
                data={"skill": name, "registered": False, "enable_evolving": False},
            )

        skill_dir = getattr(info, "skill_dir", "") or ""
        md_path = os.path.join(skill_dir, "SKILL.md") if skill_dir else ""
        lines.append("- **Registered**: True")
        lines.append(f"- **Description**: {info.description}")
        lines.append(f"- **Version**: {info.version}")
        lines.append(f"- **Type**: {getattr(info, 'type', '')}")
        lines.append(f"- **Evolvable (enable_evolving)**: {getattr(info, 'enable_evolving', False)}")
        lines.append(f"- **Skill Directory**: `{skill_dir}` (exists: {os.path.isdir(skill_dir) if skill_dir else False})")
        lines.append(f"- **SKILL.md**: `{md_path}` (exists: {os.path.exists(md_path) if md_path else False})")
        schema_json = await skill_manager.get_schema(name, format="json")
        schema_md = await skill_manager.get_schema(name, format="md")
        if schema_md:
            lines.append(f"\n{schema_md}")

        return Response(
            type=ResponseType.TOOL,
            success=True,
            message="\n".join(lines),
            data={
                "skill": name,
                "registered": True,
                "enable_evolving": bool(getattr(info, "enable_evolving", False)),
                "skill_dir": skill_dir,
                "schema": schema_json,
            },
        )
