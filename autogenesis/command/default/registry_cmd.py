"""/registry — list all registered capabilities and their versions (CONTROL, read-only)."""
from typing import List, Optional

from autogenesis.registry import COMMAND
from autogenesis.command.types import Command, CommandType, CommandContext
from autogenesis.response.types import Response


@COMMAND.register_module(force=True)
class RegistryCommand(Command):
    name: str = "registry"
    description: str = "List all registered capabilities (tool/agent/skill/…) and their current versions."
    type: CommandType = CommandType.CONTROL
    usage: str = "/registry [type]"
    permission_mode: str = "read_only"

    async def __call__(self, args: List[str], ctx: Optional[CommandContext] = None) -> Response:
        from autogenesis.version import version_manager
        data = await version_manager.list()  # {type: {name: [versions]}}
        wanted = args[0] if args else None

        lines: List[str] = []
        for ctype, names in sorted(data.items()):
            if wanted and ctype != wanted:
                continue
            lines.append(f"{ctype} ({len(names)}):")
            for n, vers in sorted(names.items()):
                cur = await version_manager.get_current_version(ctype, n)
                shown = cur or (vers[-1] if vers else "?")
                lines.append(f"  - {n} @ {shown}  ({len(vers)} version(s))")

        if wanted and not lines:
            return self.fail(f"No components of type '{wanted}'. Known types: {sorted(data.keys())}")
        msg = "\n".join(lines) if lines else "No registered components."
        return self.ok(msg, data=data)
