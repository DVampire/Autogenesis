"""/create — dispatch a generate agent to create a new capability (SKILL)."""
from typing import List, Optional

from autogenesis.registry import COMMAND
from autogenesis.command.types import SkillCommand, CommandContext
from autogenesis.response.types import Response
from autogenesis.command.default._helpers import AGENT_BACKED_TYPES


@COMMAND.register_module(force=True)
class CreateCommand(SkillCommand):
    name: str = "create"
    description: str = "Dispatch the matching generate agent to create a new capability."
    usage: str = "/create <type> <description...>"
    permission_mode: str = "workspace_write"

    async def __call__(self, args: List[str], ctx: Optional[CommandContext] = None) -> Response:
        if len(args) < 2:
            return self.fail(f"usage: {self.usage}")
        ctype = args[0]
        desc = " ".join(args[1:])
        if ctype not in AGENT_BACKED_TYPES:
            return self.fail(f"Can't create type '{ctype}'. Options: {AGENT_BACKED_TYPES}")

        self.target_agent = f"{ctype}_generate_agent"
        return await self.dispatch_agent(f"Create a new {ctype}: {desc}", ctx)
