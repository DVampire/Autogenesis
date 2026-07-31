"""Command Context Manager — discovers commands from the COMMAND registry and dispatches them.

Dispatch is the whole point: given a raw line like ``/rollback tool foo 1.2``, parse the
command name + args, look it up, and run it. CONTROL commands execute here deterministically;
SKILL commands hand off to an agent. Either way the caller gets a uniform ``Response``.
"""
from typing import Dict, List, Optional, Type

from pydantic import BaseModel, ConfigDict

from autogenesis.logger import logger
from autogenesis.registry import COMMAND
from autogenesis.response.types import Response, ResponseType
from autogenesis.permission import permission_manager, PermissionMode
from autogenesis.command.types import Command, CommandContext


class CommandContextManager(BaseModel):
    """Registry-backed manager for all commands."""
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._commands: Dict[str, Command] = {}

    async def initialize(self, command_names: Optional[List[str]] = None):
        """Discover command classes from the COMMAND registry and instantiate them."""
        import autogenesis.command  # noqa: F401 — triggers default/* imports so decorators run

        command_classes: List[Type[Command]] = list(COMMAND._module_dict.values())
        logger.info(f"| 🔍 Discovering {len(command_classes)} commands from COMMAND registry")

        for cmd_cls in command_classes:
            try:
                instance = cmd_cls()
                if command_names is not None and instance.name not in command_names:
                    continue
                self._commands[instance.name] = instance
                permission_manager.register(
                    entity_name=instance.name,
                    mode=PermissionMode(instance.permission_mode),
                )
                logger.info(f"| 🔧 Command /{instance.name} [{instance.type.value}] ready")
            except Exception as e:
                logger.error(f"| ❌ Failed to register command {cmd_cls.__name__}: {e}")

        logger.info(f"| ✅ Commands initialization completed ({len(self._commands)} commands)")

    async def list(self) -> List[str]:
        return list(self._commands.keys())

    async def get(self, name: str) -> Optional[Command]:
        return self._commands.get(name)

    async def help(self) -> str:
        """Render a one-line-per-command help listing, grouped by type."""
        lines: List[str] = []
        for t in ("control", "skill"):
            group = [c for c in self._commands.values() if c.type.value == t]
            if not group:
                continue
            lines.append(f"[{t}]")
            for c in sorted(group, key=lambda x: x.name):
                usage = c.usage or f"/{c.name}"
                lines.append(f"  {usage}  —  {c.description}")
        return "\n".join(lines)

    def _parse(self, raw: str):
        """'/rollback tool foo 1.2' -> ('rollback', ['tool', 'foo', '1.2'])."""
        parts = raw.strip().lstrip("/").split()
        if not parts:
            return None, []
        return parts[0], parts[1:]

    async def dispatch(self, raw: str, ctx: Optional[CommandContext] = None) -> Response:
        """Parse ``raw``, look up the command, and run it. Never raises — errors come back as a Response."""
        name, args = self._parse(raw)
        if name is None:
            return Response(type=ResponseType.COMMAND, success=False, message="Empty command.")

        if name in ("help", "?"):
            return Response(type=ResponseType.COMMAND, success=True, message=await self.help())

        cmd = self._commands.get(name)
        if cmd is None:
            available = ", ".join(f"/{n}" for n in sorted(self._commands))
            return Response(type=ResponseType.COMMAND, success=False,
                            message=f"Unknown command /{name}. Available: {available}")

        if ctx is None:
            ctx = CommandContext(name=name, raw=raw)

        if cmd.permission_mode == PermissionMode.DANGER_FULL_ACCESS.value:
            logger.warning(f"| ⚠️ /{name} is a danger_full_access command — {cmd.description}")

        try:
            logger.info(f"| ▶️ Dispatching /{name} [{cmd.type.value}] args={args}")
            return await cmd(args, ctx)
        except Exception as e:
            logger.error(f"| ❌ /{name} failed: {e}")
            return Response(type=ResponseType.COMMAND, success=False, message=f"/{name} failed: {e}")

    async def cleanup(self):
        self._commands.clear()
