"""/copy — copy a capability to a new name/version (CONTROL)."""
from typing import List, Optional

from autogenesis.registry import COMMAND
from autogenesis.command.types import Command, CommandType, CommandContext
from autogenesis.response.types import Response
from autogenesis.command.default._helpers import get_manager, KNOWN_TYPES


@COMMAND.register_module(force=True)
class CopyCommand(Command):
    name: str = "copy"
    description: str = "Copy a capability to a new name (or bump version if no new name)."
    type: CommandType = CommandType.CONTROL
    usage: str = "/copy <type> <name> [new_name]"
    permission_mode: str = "workspace_write"

    async def __call__(self, args: List[str], ctx: Optional[CommandContext] = None) -> Response:
        if len(args) < 2:
            return self.fail(f"usage: {self.usage}")
        ctype, name = args[0], args[1]
        new_name = args[2] if len(args) > 2 else None

        mgr = get_manager(ctype)
        if mgr is None:
            return self.fail(f"Unknown type '{ctype}'. Known: {KNOWN_TYPES}")
        if not hasattr(mgr, "copy"):
            return self.fail(f"The {ctype} manager does not support copy.")

        result = await mgr.copy(name, new_name)
        target = getattr(result, "name", new_name or name)
        version = getattr(result, "version", "?")
        return self.ok(f"Copied {ctype}/{name} → {target}@{version}.",
                       data={"type": ctype, "name": target, "version": version})
