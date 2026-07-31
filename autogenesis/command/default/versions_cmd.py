"""/versions — show the version history of one capability (CONTROL, read-only)."""
from typing import List, Optional

from autogenesis.registry import COMMAND
from autogenesis.command.types import Command, CommandType, CommandContext
from autogenesis.response.types import Response


@COMMAND.register_module(force=True)
class VersionsCommand(Command):
    name: str = "versions"
    description: str = "Show the version history of a capability."
    type: CommandType = CommandType.CONTROL
    usage: str = "/versions <type> <name>"
    permission_mode: str = "read_only"

    async def __call__(self, args: List[str], ctx: Optional[CommandContext] = None) -> Response:
        if len(args) < 2:
            return self.fail(f"usage: {self.usage}")
        ctype, name = args[0], args[1]

        from autogenesis.version import version_manager
        hist = await version_manager.get_version_history(ctype, name)
        if hist is None:
            return self.fail(f"No version history for {ctype}/{name}.")

        cur = await version_manager.get_current_version(ctype, name)
        versions = hist.list_versions() if hasattr(hist, "list_versions") else list(getattr(hist, "versions", []))
        lines = [f"{ctype}/{name} — current: {cur or '?'}"]
        for v in versions:
            marker = " *" if v == cur else ""
            lines.append(f"  - {v}{marker}")
        return self.ok("\n".join(lines), data={"current": cur, "versions": versions})
