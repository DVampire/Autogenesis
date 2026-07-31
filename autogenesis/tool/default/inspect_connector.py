"""Inspect-connector tool — fetch a registered connector's live registry facts on demand."""
import os
from typing import Dict, Any
from pydantic import Field
from autogenesis.tool.types import Tool
from autogenesis.response.types import Response, ResponseType
from autogenesis.registry import TOOL

_DESCRIPTION = "Fetch a registered connector's live registry facts (registration status, version, evolvability/enable_evolving, MCP connection, actions, CONNECTOR.md path) by name."

_INSTRUCTION = """
## Function
Fetch a connector's live registry facts: whether it is registered, its version, whether it is evolvable (enable_evolving), its MCP connection (transport/url), the actions it exposes, and its directory + CONNECTOR.md path.

## Guidance
- Use this before optimizing or evaluating a connector named in your task: it reports the target's real state in the registry, which reading files alone cannot.
- Optimization requires enable_evolving=True. If inspect_connector_tool reports enable_evolving=False, the connector is frozen — do NOT edit it; refuse and report why.
- The returned connector_dir / CONNECTOR.md path tells you exactly which files to read/edit.

## Parameters
- name (str): The exact name of the connector to inspect.

## Example
{"name": "inspect_connector_tool", "args": {"name": "pubmed_connector"}}
"""


@TOOL.register_module(force=True)
class InspectConnector(Tool):
    """Return a registered connector's live registry facts on demand."""

    name: str = "inspect_connector_tool"
    description: str = _DESCRIPTION
    instruction: str = _INSTRUCTION
    metadata: Dict[str, Any] = Field(default={}, description="The metadata of the tool")
    enable_evolving: bool = Field(default=False, description="Whether the tool may be evolved (self-optimized)")

    def __init__(self, enable_evolving: bool = False, **kwargs):
        super().__init__(enable_evolving=enable_evolving, **kwargs)

    async def __call__(self, name: str, **kwargs) -> Response:
        """Return live registry facts for the named connector.

        Args:
            name (str): The exact name of the connector to inspect.
        """
        from autogenesis.connector.server import connector_manager  # local import avoids a circular import

        info = await connector_manager.get_info(name)

        lines = [f"- **Connector Name**: `{name}`"]
        if info is None:
            lines.append("- **Registered**: False (not found in registry)")
            available = await connector_manager.list()
            lines.append(f"\nAvailable connectors: {available}")
            return Response(
                type=ResponseType.TOOL, success=False, message="\n".join(lines),
                data={"connector": name, "registered": False, "enable_evolving": False},
            )

        connector_dir = getattr(info, "connector_dir", "") or ""
        md_path = os.path.join(connector_dir, "CONNECTOR.md") if connector_dir else ""
        connection = getattr(info, "connection", {}) or {}
        actions = getattr(info, "actions", []) or []
        lines.append("- **Registered**: True")
        lines.append(f"- **Description**: {info.description}")
        lines.append(f"- **Version**: {info.version}")
        lines.append(f"- **Evolvable (enable_evolving)**: {getattr(info, 'enable_evolving', False)}")
        lines.append(f"- **Transport**: {connection.get('transport', '(unknown)')}")
        lines.append(f"- **URL/Command**: {connection.get('url') or connection.get('command', '(none)')}")
        lines.append(f"- **Actions ({len(actions)})**: {', '.join(actions) if actions else '(none listed)'}")
        lines.append(f"- **Connector Directory**: `{connector_dir}` (exists: {os.path.isdir(connector_dir) if connector_dir else False})")
        lines.append(f"- **CONNECTOR.md**: `{md_path}` (exists: {os.path.exists(md_path) if md_path else False})")
        schemas = {}
        for action in actions:
            schemas[action] = await connector_manager.get_schema(name, action=action, format="json")
            schema_md = await connector_manager.get_schema(name, action=action, format="md")
            if schema_md:
                lines.append(f"\n{schema_md}")

        return Response(
            type=ResponseType.TOOL,
            success=True,
            message="\n".join(lines),
            data={
                "connector": name,
                "registered": True,
                "enable_evolving": bool(getattr(info, "enable_evolving", False)),
                "connector_dir": connector_dir,
                "actions": actions,
                "schemas": schemas,
            },
        )
