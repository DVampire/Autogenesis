"""Command Manager — thin wrapper over CommandContextManager.

Global ``command_manager`` is the single entry point every front-end uses:
- the human/session layer: ``await command_manager.dispatch("/checkpoint")``
- MetaAgent (via a control tool): same ``dispatch`` call
- orchestration code (the evolve loop): same ``dispatch`` call

One operation, one implementation, three callers.
"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from autogenesis.logger import logger
from autogenesis.response.types import Response
from autogenesis.command.types import Command, CommandContext
from autogenesis.command.context import CommandContextManager


class CommandManagerServer(BaseModel):
    """Manager for command registration and dispatch."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.command_context_manager: Optional[CommandContextManager] = None

    async def _ensure_context_manager(self) -> CommandContextManager:
        if getattr(self, "command_context_manager", None) is None:
            await self.initialize()
        return self.command_context_manager

    async def initialize(self, command_names: Optional[List[str]] = None):
        self.command_context_manager = CommandContextManager()
        await self.command_context_manager.initialize(command_names=command_names)
        logger.info("| ✅ Command Manager initialization completed")

    async def list(self) -> List[str]:
        cm = await self._ensure_context_manager()
        return await cm.list()

    async def get(self, name: str) -> Optional[Command]:
        cm = await self._ensure_context_manager()
        return await cm.get(name)

    async def help(self) -> str:
        cm = await self._ensure_context_manager()
        return await cm.help()

    async def dispatch(self, raw: str, ctx: Optional[CommandContext] = None) -> Response:
        """Parse and run a ``/command`` line, returning a uniform Response."""
        cm = await self._ensure_context_manager()
        return await cm.dispatch(raw, ctx=ctx)

    async def cleanup(self):
        if getattr(self, "command_context_manager", None) is not None:
            await self.command_context_manager.cleanup()


# Global Command Manager instance
command_manager = CommandManagerServer()
