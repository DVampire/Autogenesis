"""/unregister — remove a capability from the registry (CONTROL, danger)."""
from typing import List, Optional

from autogenesis.registry import COMMAND
from autogenesis.command.types import Command, CommandType, CommandContext
from autogenesis.response.types import Response
from autogenesis.command.default._helpers import get_manager, KNOWN_TYPES


@COMMAND.register_module(force=True)
class UnregisterCommand(Command):
    name: str = "unregister"
    description: str = "Remove a capability from the active registry."
    type: CommandType = CommandType.CONTROL
    usage: str = "/unregister <type> <name>"
    permission_mode: str = "danger_full_access"

    async def __call__(self, args: List[str], ctx: Optional[CommandContext] = None) -> Response:
        if len(args) < 2:
            return self.fail(f"usage: {self.usage}")
        ctype, name = args[0], args[1]

        mgr = get_manager(ctype)
        if mgr is None:
            return self.fail(f"Unknown type '{ctype}'. Known: {KNOWN_TYPES}")
        if not hasattr(mgr, "unregister"):
            return self.fail(f"The {ctype} manager does not support unregister.")

        ok = await mgr.unregister(name)
        if ok:
            return self.ok(f"Unregistered {ctype}/{name}.")
        return self.fail(f"{ctype}/{name} not found.")
