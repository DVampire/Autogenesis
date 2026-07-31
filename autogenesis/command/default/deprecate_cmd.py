"""/deprecate — mark a capability version as deprecated (CONTROL)."""
from typing import List, Optional

from autogenesis.registry import COMMAND
from autogenesis.command.types import Command, CommandType, CommandContext
from autogenesis.response.types import Response
from autogenesis.command.default._helpers import KNOWN_TYPES


@COMMAND.register_module(force=True)
class DeprecateCommand(Command):
    name: str = "deprecate"
    description: str = "Mark a specific capability version as deprecated."
    type: CommandType = CommandType.CONTROL
    usage: str = "/deprecate <type> <name> <version>"
    permission_mode: str = "workspace_write"

    async def __call__(self, args: List[str], ctx: Optional[CommandContext] = None) -> Response:
        if len(args) < 3:
            return self.fail(f"usage: {self.usage}")
        ctype, name, version = args[0], args[1], args[2]
        if ctype not in KNOWN_TYPES:
            return self.fail(f"Unknown type '{ctype}'. Known: {KNOWN_TYPES}")

        from autogenesis.version import version_manager
        await version_manager.deprecate_version(ctype, name, version)
        return self.ok(f"Deprecated {ctype}/{name}@{version}.")
