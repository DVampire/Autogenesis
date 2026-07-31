"""Mem0 Chat Memory."""

from typing import Any, List, Optional

from autogenesis.response.types import Response
from autogenesis.plugins.types import MemoryPluginTool


class Mem0ChatMemoryTool(MemoryPluginTool):
    """Mem0 Chat Memory."""

    name: str = 'mem0_chat_memory'
    display_name: str = 'Mem0 Chat Memory'
    description: str = 'Retrieves and stores chat messages using Mem0 memory storage.'

    def _history(self, session_id: str, **cfg: Any) -> Any:
        from mem0 import MemoryClient
        key = self._secret(cfg.get("api_key"), "MEM0_API_KEY")
        if not key:
            raise ValueError("Mem0 needs an API key (MEM0_API_KEY).")
        raise NotImplementedError("Mem0 uses a client API; use mem0.MemoryClient(api_key).search/add.")

    async def __call__(self, action: str = "get", session_id: str = "default", message: str = "",
                       role: str = "user", api_key: str = "", **kwargs) -> Response:
        return await self._memory(action=action, session_id=session_id, message=message, role=role,
                                  **{k: v for k, v in kwargs.items()})
