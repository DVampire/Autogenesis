"""/rollback — restore one capability to a previous version (CONTROL, danger).

The deterministic undo. Delegates to the matching manager's ``restore`` — the same
mechanism the framework already uses for versioned components.
"""
from typing import List, Optional

from autogenesis.registry import COMMAND
from autogenesis.command.types import Command, CommandType, CommandContext
from autogenesis.response.types import Response
from autogenesis.command.default._helpers import get_manager, KNOWN_TYPES


@COMMAND.register_module(force=True)
class RollbackCommand(Command):
    name: str = "rollback"
    description: str = "Restore a capability to a previous version (deterministic undo)."
    type: CommandType = CommandType.CONTROL
    usage: str = "/rollback <type> <name> <version>"
    permission_mode: str = "danger_full_access"

    async def __call__(self, args: List[str], ctx: Optional[CommandContext] = None) -> Response:
        if len(args) < 3:
            return self.fail(f"usage: {self.usage}")
        ctype, name, version = args[0], args[1], args[2]

        mgr = get_manager(ctype)
        if mgr is None:
            return self.fail(f"Unknown type '{ctype}'. Known: {KNOWN_TYPES}")
        if not hasattr(mgr, "restore"):
            return self.fail(f"The {ctype} manager does not support rollback.")

        result = await mgr.restore(name, version)
        if result is None:
            return self.fail(f"Version {version} not found for {ctype}/{name}.")
        return self.ok(f"Rolled back {ctype}/{name} → {version}.",
                       data={"type": ctype, "name": name, "version": version})
